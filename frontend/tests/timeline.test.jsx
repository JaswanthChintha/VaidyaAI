import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Timeline from '../src/pages/Timeline';
import { api } from '../src/lib/api';

/**
 * Modules 28/29/30 at the rendering layer.
 *
 * THE WORD THIS SCREEN MUST NEVER PRINT WITHOUT EARNING IS "stable". Module
 * 28 reserves it for a change measured against a declared stability band;
 * fewer than two usable readings is `INSUFFICIENT_DATA` with `trend: null`.
 * A timeline with nothing on it looks exactly like a timeline that did not
 * move, which is why this is the easiest place in the whole product to state
 * something nobody measured.
 */

function mount({ trends, comparison, progress } = {}) {
  vi.spyOn(api, 'getTrends').mockResolvedValue(trends ?? { trends: {}, history: {} });
  vi.spyOn(api, 'getComparison').mockResolvedValue(comparison ?? { comparison: {} });
  vi.spyOn(api, 'getProgress').mockResolvedValue(progress ?? { progress: {} });
  return render(
    <MemoryRouter>
      <Timeline />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('trends', () => {
  it('never renders INSUFFICIENT_DATA as "stable"', async () => {
    mount({
      trends: {
        history: { included: 1, considered: 1 },
        trends: {
          features: {
            hba1c: {
              feature: 'hba1c',
              outcome: 'INSUFFICIENT_DATA',
              trend: null,
              usable_point_count: 1,
              canonical_unit: '%',
              reason:
                'hba1c: 1 usable reading(s). At least two are needed before any change can be described. This is not the same as no change having occurred.',
            },
          },
          summary: { improving: 0, worsening: 0, stable: 0, not_determinable: 1 },
        },
      },
    });

    expect(await screen.findByText('No trend')).toBeInTheDocument();
    expect(
      screen.getByText(/not the same as no change having occurred/)
    ).toBeInTheDocument();
    // The dangerous word must not appear as this feature's answer.
    expect(screen.queryByText('stable')).not.toBeInTheDocument();
  });

  it('renders a real classified trend', async () => {
    mount({
      trends: {
        history: { included: 3, considered: 3 },
        trends: {
          features: {
            hba1c: {
              feature: 'hba1c',
              outcome: 'TREND_CLASSIFIED',
              trend: 'worsening',
              direction: 'rising',
              usable_point_count: 3,
              canonical_unit: '%',
              change: { first_value: 6.1, last_value: 6.8 },
            },
          },
          summary: { improving: 0, worsening: 1, stable: 0, not_determinable: 0 },
        },
      },
    });

    expect(await screen.findByText('worsening')).toBeInTheDocument();
    expect(screen.getByText('6.1 %')).toBeInTheDocument();
    expect(screen.getByText('6.8 %')).toBeInTheDocument();
  });

  it('shows CLINICAL_DIRECTION_UNKNOWN as a refusal, not a direction', async () => {
    // A feature whose polarity is undeclared reports direction only. Calling
    // that "improving" would be a guess about what is better.
    mount({
      trends: {
        history: { included: 2, considered: 2 },
        trends: {
          features: {
            hemoglobin: {
              feature: 'hemoglobin',
              outcome: 'CLINICAL_DIRECTION_UNKNOWN',
              trend: null,
              usable_point_count: 2,
              canonical_unit: 'g/dl',
              reason: 'No direction of benefit is declared for hemoglobin.',
            },
          },
          summary: { improving: 0, worsening: 0, stable: 0, not_determinable: 1 },
        },
      },
    });

    expect(await screen.findByText('No trend')).toBeInTheDocument();
    expect(screen.queryByText('improving')).not.toBeInTheDocument();
  });

  it('shows the history accounting, including reports dropped by the cap', async () => {
    // A timeline built from 50 of 55 reports and one built from a patient's
    // only 50 look identical without this.
    mount({
      trends: {
        history: {
          included: 50,
          considered: 58,
          excludedCount: 3,
          droppedByCap: 5,
          cap: 50,
          truncated: true,
        },
        trends: { features: {}, summary: {} },
      },
    });

    // Asserted on the sentence, not on the bare number: "50" appears twice
    // (the included count and the cap), so matching it alone is ambiguous and
    // would pass for the wrong reason.
    expect(
      await screen.findByText(/5 older report\(s\) fell outside the most recent/)
    ).toBeInTheDocument();
    expect(screen.getByText(/3 could not contribute/)).toBeInTheDocument();
  });
});

describe('comparison', () => {
  it('renders a parameter missing from one report as absent, not as 0', async () => {
    mount({
      comparison: {
        comparison: {
          table: [
            {
              feature: 'vitamin_b12',
              description: 'Vitamin B12',
              unit: 'pg/ml',
              previous: 420,
              current: null,
              category: 'not_classifiable',
            },
          ],
        },
      },
    });

    expect(await screen.findByText('Vitamin B12')).toBeInTheDocument();
    expect(screen.getByText('420 pg/ml')).toBeInTheDocument();
    expect(screen.queryByText('0 pg/ml')).not.toBeInTheDocument();
    expect(
      screen.getByText('This parameter was not on the later report.')
    ).toBeInTheDocument();
  });

  it('warns when a named pair is out of date order', async () => {
    mount({
      comparison: {
        comparison: {
          pair: {
            baseline_date: '2024-06-01T00:00:00Z',
            comparison_date: '2024-01-01T00:00:00Z',
            chronological: false,
          },
          table: [],
        },
      },
    });

    expect(
      await screen.findByText(/direction of every change is reversed/)
    ).toBeInTheDocument();
  });
});

describe('progress score', () => {
  it('renders a refusal as "no score", never as 50 or 0', async () => {
    // Below the coverage floor the service returns `score: null`. A midpoint
    // would read as "average progress", which nobody measured.
    mount({
      progress: {
        progress: {
          outcome: 'INSUFFICIENT_COVERAGE',
          score: null,
          band: null,
          coverage: {
            contributing_count: 2,
            features_examined: 7,
            excluded_count: 5,
            minimum_required: 3,
          },
          summary: {
            headline:
              'Two parameters could be compared, which is below the minimum of three.',
          },
        },
      },
    });

    expect(await screen.findByText('No score')).toBeInTheDocument();
    expect(screen.queryByText('50')).not.toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    expect(screen.getByText(/below the minimum of three/)).toBeInTheDocument();
  });

  it('renders a computed score with its band', async () => {
    mount({
      progress: {
        progress: {
          outcome: 'SCORE_COMPUTED',
          score: 66.7,
          band: {
            key: 'more_favourable_than_unfavourable',
            label: 'More favourable movement than unfavourable',
          },
          scale: { direction_text: 'A higher score means more parameters moved favourably.' },
          coverage: {
            contributing_count: 6,
            features_examined: 7,
            excluded_count: 1,
            minimum_required: 3,
          },
        },
      },
    });

    expect(await screen.findByText('66.7')).toBeInTheDocument();
    expect(
      screen.getByText('More favourable movement than unfavourable')
    ).toBeInTheDocument();
  });

  it('one failing section does not blank the other two', async () => {
    vi.spyOn(api, 'getTrends').mockRejectedValue(new Error('trends unavailable'));
    vi.spyOn(api, 'getComparison').mockResolvedValue({ comparison: { table: [] } });
    vi.spyOn(api, 'getProgress').mockResolvedValue({
      progress: { outcome: 'SCORE_COMPUTED', score: 70, band: { label: 'Good' } },
    });

    render(
      <MemoryRouter>
        <Timeline />
      </MemoryRouter>
    );

    expect(await screen.findByText('trends unavailable')).toBeInTheDocument();
    // The other two still rendered.
    expect(screen.getByText('70')).toBeInTheDocument();
  });
});
