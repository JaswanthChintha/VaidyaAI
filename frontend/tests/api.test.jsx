import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/lib/api';

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
