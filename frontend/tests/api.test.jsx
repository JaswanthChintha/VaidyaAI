import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/lib/api';

/**
 * The query string the timeline's two paired endpoints are called with.
 *
 * Tested at THIS layer because the rule lives here: the picker refuses to act
 * on a half-made choice, but `pairQuery` is what stops a half pair reaching
 * the backend from any future caller, and a guard nothing exercises is a
 * guard nobody knows is broken.
 */
describe('the comparison pair in the query string', () => {
  let calls;

  beforeEach(() => {
    calls = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        calls.push(String(url));
        return {
          ok: true,
          status: 200,
          json: async () => ({ success: true, data: {} }),
        };
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends both ids when both were chosen', async () => {
    await api.getComparison({ baseline: 'aaa', comparison: 'bbb' });
    expect(calls[0]).toContain('/timeline/comparison?baseline=aaa&comparison=bbb');
  });

  it('asks the progress score about the SAME pair', async () => {
    await api.getProgress({ baseline: 'aaa', comparison: 'bbb' });
    expect(calls[0]).toContain('/timeline/progress?baseline=aaa&comparison=bbb');
  });

  it('sends NOTHING when only one was chosen', async () => {
    // BOTH OR NEITHER. The backend refuses exactly one of the pair rather than
    // guessing the other, so a half pair turns a half-finished choice into an
    // error message instead of into the default comparison.
    await api.getComparison({ baseline: 'aaa' });
    await api.getComparison({ comparison: 'bbb' });
    expect(calls[0]).not.toContain('?');
    expect(calls[1]).not.toContain('?');
  });

  it('sends nothing at all when no pair was chosen', async () => {
    await api.getComparison();
    await api.getProgress(null);
    expect(calls[0]).not.toContain('?');
    expect(calls[1]).not.toContain('?');
  });

  it('escapes an id rather than pasting it into the URL', async () => {
    await api.getComparison({ baseline: 'a&b=c', comparison: 'd' });
    expect(calls[0]).toContain('baseline=a%26b%3Dc');
  });
});
