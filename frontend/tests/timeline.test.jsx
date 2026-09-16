import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

function mount({ trends, comparison, progress, reports } = {}) {
  vi.spyOn(api, 'getTrends').mockResolvedValue(trends ?? { trends: {}, history: {} });
  vi.spyOn(api, 'getComparison').mockResolvedValue(comparison ?? { comparison: {} });
  vi.spyOn(api, 'getProgress').mockResolvedValue(progress ?? { progress: {} });
  vi.spyOn(api, 'listReports').mockResolvedValue(reports ?? { reports: [] });
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

  /**
   * THE CHART, DRIVEN THROUGH THE PAGE with Module 28's own field names --
   * `points[].date/value`, `gaps[].availability`, `polarity.optimal_*` --
   * rather than the chart's props. A fixture written against the consumer's
   * assumption instead of the producer's output cannot catch the consumer's
   * assumption being wrong, and on this project that has already happened
   * (MEMORY.md 6w: `basis.limitations`).
   */
  it('plots a classified trend and breaks the line across a gap', async () => {
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
              usable_point_count: 2,
              canonical_unit: '%',
              change: { first_value: 6.1, last_value: 6.8 },
              points: [
                { date: '2026-01-10T00:00:00Z', value: 6.1, unit: '%', questionable: false },
                { date: '2026-08-10T00:00:00Z', value: 6.8, unit: '%', questionable: false },
              ],
              gaps: [
                {
                  date: '2026-04-10T00:00:00Z',
                  availability: 'not_reported',
                  reason_code: 'NOT_REPORTED',
                  reason: 'That report did not carry a value for hba1c.',
                },
              ],
            },
          },
          summary: { improving: 0, worsening: 1, stable: 0, not_determinable: 0 },
        },
      },
    });

    const chart = await screen.findByRole('img');
    expect(chart.getAttribute('aria-label')).toMatch(/worsening/);
    expect(chart.getAttribute('aria-label')).toMatch(/1 report carried no usable reading/);
    // The middle report is a gap, so the two readings are never joined.
    expect(document.querySelectorAll('.trend-chart__line')).toHaveLength(0);
    expect(document.querySelectorAll('.trend-chart__point')).toHaveLength(2);
    expect(
      screen.getAllByText(/did not carry a value for hba1c/).length
    ).toBeGreaterThanOrEqual(1);
  });

  it('draws no line, and no chart at all, for a single reading', async () => {
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
              points: [{ date: '2026-01-10T00:00:00Z', value: 6.1, unit: '%' }],
              gaps: [],
              reason: 'hba1c: 1 usable reading(s). At least two are needed.',
            },
          },
          summary: { improving: 0, worsening: 0, stable: 0, not_determinable: 1 },
        },
      },
    });

    await screen.findByText('No trend');
    expect(document.querySelectorAll('.trend-chart__line')).toHaveLength(0);
    expect(document.querySelectorAll('.trend-chart__point')).toHaveLength(1);
    // The whole hazard, in one assertion -- scoped to the chart, because the
    // page's own summary line legitimately counts "0 stable".
    expect(
      document.querySelector('.trend-chart').textContent.toLowerCase()
    ).not.toContain('stable');
  });

  it('draws no band from a one-sided optimum, and no trend word without one', async () => {
    mount({
      trends: {
        history: { included: 2, considered: 2 },
        trends: {
          features: {
            total_cholesterol: {
              feature: 'total_cholesterol',
              // Two real readings, no classification: the service could not
              // place this change against its stability band.
              outcome: 'CHANGE_WITHIN_REFERENCE_INTERVAL',
              trend: null,
              usable_point_count: 2,
              canonical_unit: 'mg/dl',
              // A declared FLOOR and no declared ceiling. Drawn as a band it
              // would run to the top of the frame and assert a ceiling nobody
              // declared.
              polarity: { kind: 'lower_is_better', optimal_low: 200, optimal_high: null },
              points: [
                { date: '2026-01-10T00:00:00Z', value: 210, unit: 'mg/dl' },
                { date: '2026-08-10T00:00:00Z', value: 205, unit: 'mg/dl' },
              ],
              gaps: [],
              reason: 'Both readings sat inside the reference interval.',
            },
          },
          summary: {},
        },
      },
    });

    const chart = await screen.findByRole('img');
    expect(document.querySelector('.trend-chart__band')).toBeNull();
    expect(chart.getAttribute('aria-label')).toMatch(/No direction was classified/);
    expect(document.querySelector('.trend-chart__line').getAttribute('stroke')).toBe(
      'var(--ink)'
    );
  });

  it('takes the direction from the OUTCOME, not from a stray trend word', async () => {
    // The contradictory payload Module 28's model validator forbids: an
    // outcome that is not TREND_CLASSIFIED carrying a trend anyway. The page
    // derives `classified` from the outcome, so the word never becomes a
    // colour -- and this is the only shape that tells the two apart.
    mount({
      trends: {
        history: { included: 2, considered: 2 },
        trends: {
          features: {
            hba1c: {
              feature: 'hba1c',
              outcome: 'NO_STABILITY_BAND',
              trend: 'worsening',
              usable_point_count: 2,
              canonical_unit: '%',
              points: [
                { date: '2026-01-10T00:00:00Z', value: 6.1, unit: '%' },
                { date: '2026-08-10T00:00:00Z', value: 6.8, unit: '%' },
              ],
              gaps: [],
              reason: 'No stability band is declared for hba1c.',
            },
          },
          summary: {},
        },
      },
    });

    const chart = await screen.findByRole('img');
    expect(chart.getAttribute('aria-label')).toMatch(/No direction was classified/);
    expect(document.querySelector('.trend-chart__line').getAttribute('stroke')).toBe(
      'var(--ink)'
    );
  });

  it('draws no trend line for a parameter the service says has no trajectory', async () => {
    // Straight from a real payload: `age` arrives NOT_TRENDABLE with two
    // perfectly good points, and on the live data those points are 58 and 34
    // -- two different synthetic patients. Charted, that is a person getting
    // 24 years younger, drawn beside a sentence refusing to describe a trend.
    mount({
      trends: {
        history: { included: 2, considered: 2 },
        trends: {
          features: {
            age: {
              feature: 'age',
              outcome: 'NOT_TRENDABLE',
              trend: null,
              usable_point_count: 2,
              canonical_unit: 'years',
              points: [
                { date: '2026-09-07T04:00:14Z', value: 58, unit: 'years' },
                { date: '2026-09-11T04:26:10Z', value: 34, unit: 'years' },
              ],
              gaps: [],
              reason: 'age is not a parameter a trend is reported for.',
            },
          },
          summary: {},
        },
      },
    });

    await screen.findByText('No trend');
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(document.querySelectorAll('.trend-chart__line')).toHaveLength(0);
  });

  it('renders no chart for a feature with gaps but no reading at all', async () => {
    // `gender`, live: NOT_NUMERIC, no points, two gaps. An axis with nothing
    // on it is not a chart, and the row below already says why.
    mount({
      trends: {
        history: { included: 2, considered: 2 },
        trends: {
          features: {
            gender: {
              feature: 'gender',
              outcome: 'NOT_NUMERIC',
              trend: null,
              usable_point_count: 0,
              points: [],
              gaps: [
                {
                  date: '2026-09-07T04:00:14Z',
                  availability: 'unusable',
                  reason_code: 'NON_NUMERIC_VALUE',
                  reason: 'The stored reading is not a finite number.',
                },
              ],
              reason: 'gender is not numeric, so no change can be measured.',
            },
          },
          summary: {},
        },
      },
    });

    await screen.findByText('No trend');
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('renders no chart for a feature with neither a reading nor a gap', async () => {
    mount({
      trends: {
        history: { included: 2, considered: 2 },
        trends: {
          features: {
            hemoglobin: {
              feature: 'hemoglobin',
              outcome: 'NOT_TRENDABLE',
              trend: null,
              usable_point_count: 0,
              points: [],
              gaps: [],
              reason: 'hemoglobin is not a trendable parameter.',
            },
          },
          summary: {},
        },
      },
    });

    await screen.findByText('No trend');
    // An empty frame adds nothing to the refusal sentence beside it.
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
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


describe('choosing which two reports to compare', () => {
  const A = '6a9e36ced9a53914342f3734';
  const B = '6aa382e2027fc0e96193d253';
  const C = '6bb111111111111111111111';

  const HISTORY = {
    reports: [
      { reportId: A, chronoDate: '2026-09-07T04:00:14.776Z', status: 'processed' },
      { reportId: B, chronoDate: '2026-09-11T04:26:10.910Z', status: 'processed' },
      { reportId: C, chronoDate: '2026-09-12T04:26:10.910Z', status: 'processed' },
    ],
  };

  const comparisonFor = (baseline, comparison) => ({
    history: HISTORY,
    comparison: {
      pair: {
        baseline_report_id: baseline,
        comparison_report_id: comparison,
        baseline_date: '2026-09-07T04:00:14.776Z',
        comparison_date: '2026-09-11T04:26:10.910Z',
        selection: 'first_vs_latest',
        chronological: true,
      },
      table: [{ feature: 'hba1c', previous: 8.4, current: 5.2, unit: '%', category: 'improved' }],
    },
  });

  const REPORTS = {
    reports: [
      { id: A, originalName: '06-lab-flagged.pdf' },
      { id: B, originalName: '01-all-normal.pdf' },
      { id: C, originalName: '02-diabetes.pdf' },
    ],
  };

  it('offers every report on the account, named as the reader uploaded it', async () => {
    mount({ comparison: comparisonFor(A, B), reports: REPORTS });
    await screen.findByText('Comparing two reports');

    const selects = document.querySelectorAll('.pair-picker select');
    expect(selects).toHaveLength(2);
    // The filename, not just a date -- an account with four reports from the
    // same week is four identical options otherwise.
    expect(screen.getAllByText(/06-lab-flagged\.pdf/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/02-diabetes\.pdf/).length).toBeGreaterThan(0);
  });

  it('shows the pair ACTUALLY on screen, not a guess', async () => {
    // With no explicit choice the service picks first-vs-latest. Seeding the
    // selects from its answer is what stops the control naming a comparison
    // the table below is not showing.
    mount({ comparison: comparisonFor(A, B), reports: REPORTS });
    await screen.findByText('Comparing two reports');

    const [baseline, comparison] = document.querySelectorAll('.pair-picker select');
    expect(baseline.value).toBe(A);
    expect(comparison.value).toBe(B);
  });

  it('never offers a report against itself', async () => {
    mount({ comparison: comparisonFor(A, B), reports: REPORTS });
    await screen.findByText('Comparing two reports');

    const [baseline, comparison] = document.querySelectorAll('.pair-picker select');
    const second = [...comparison.options].map((o) => o.value);
    expect(second).not.toContain(baseline.value);
    expect(second).toHaveLength(2);
  });

  it('re-asks BOTH sections about the new pair', async () => {
    // A table describing one pair beside a score computed from another is two
    // answers to different questions presented as one screen.
    mount({ comparison: comparisonFor(A, B), reports: REPORTS });
    await screen.findByText('Comparing two reports');

    api.getComparison.mockClear();
    api.getProgress.mockClear();

    const [, comparison] = document.querySelectorAll('.pair-picker select');
    fireEvent.change(comparison, { target: { value: C } });

    await waitFor(() => expect(api.getComparison).toHaveBeenCalledTimes(1));
    expect(api.getComparison).toHaveBeenCalledWith({ baseline: A, comparison: C });
    expect(api.getProgress).toHaveBeenCalledWith({ baseline: A, comparison: C });
  });

  it('does not redraw the trends section, which is about every report', async () => {
    mount({ comparison: comparisonFor(A, B), reports: REPORTS });
    await screen.findByText('Comparing two reports');
    api.getTrends.mockClear();

    const [, comparison] = document.querySelectorAll('.pair-picker select');
    fireEvent.change(comparison, { target: { value: C } });

    await waitFor(() => expect(api.getComparison).toHaveBeenCalled());
    expect(api.getTrends).not.toHaveBeenCalled();
  });

  it('clears the old table before the new one arrives', async () => {
    // Leaving the previous numbers under a changed picker states that they
    // are the comparison the control now names, which they are not.
    let release;
    mount({ comparison: comparisonFor(A, B), reports: REPORTS });
    await screen.findByText('Comparing two reports');
    api.getComparison.mockImplementation(
      () => new Promise((resolve) => { release = resolve; })
    );

    const [, comparison] = document.querySelectorAll('.pair-picker select');
    fireEvent.change(comparison, { target: { value: C } });

    await waitFor(() =>
      expect(screen.queryByText(/improved/)).not.toBeInTheDocument()
    );
    release(comparisonFor(A, C));
  });

  it('swaps rather than doing nothing when the two sides would collide', async () => {
    // ON AN ACCOUNT WITH TWO REPORTS this is the ONLY change available, and
    // the first version refused it: choosing the other report as the baseline
    // necessarily equals the current comparison, so the control visibly did
    // nothing when clicked. A reader naming the later report as the baseline
    // is asking for the comparison the other way round, which Module 29
    // supports and reports as `chronological: false`.
    mount({ comparison: comparisonFor(A, B), reports: REPORTS });
    await screen.findByText('Comparing two reports');
    api.getComparison.mockClear();

    const [baseline] = document.querySelectorAll('.pair-picker select');
    fireEvent.change(baseline, { target: { value: B } });

    await waitFor(() => expect(api.getComparison).toHaveBeenCalledTimes(1));
    expect(api.getComparison).toHaveBeenCalledWith({ baseline: B, comparison: A });
  });

  it('does not end the out-of-order sentence with two full stops', async () => {
    // Invisible until the picker made an out-of-order comparison reachable:
    // the conditional clause carried its own full stop and another was
    // printed after it regardless.
    mount({
      comparison: {
        history: HISTORY,
        comparison: {
          pair: {
            baseline_report_id: B,
            comparison_report_id: A,
            baseline_date: '2026-09-11T04:26:10.910Z',
            comparison_date: '2026-09-07T04:00:14.776Z',
            chronological: false,
          },
          table: [],
        },
      },
      reports: REPORTS,
    });

    const line = await screen.findByText(/out of date order/);
    expect(line.textContent).toMatch(/reversed\.$/);
    expect(line.textContent).not.toMatch(/\.\./);
  });

  it('is absent when there is nothing to choose between', async () => {
    mount({
      comparison: {
        history: { reports: [{ reportId: A, chronoDate: '2026-09-07T04:00:14.776Z' }] },
        comparison: {},
      },
      reports: REPORTS,
    });
    await screen.findByText('Comparing two reports');
    expect(document.querySelector('.pair-picker')).toBeNull();
  });

  it('falls back to dates when the report names could not be loaded', async () => {
    // The names are a nicety; the picker is not. A failed list must cost the
    // labels and nothing else.
    vi.spyOn(api, 'listReports').mockRejectedValue(new Error('nope'));
    mount({ comparison: comparisonFor(A, B) });
    await screen.findByText('Comparing two reports');
    expect(document.querySelectorAll('.pair-picker select')).toHaveLength(2);
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

/**
 * THE PROGRESS CARD, AFTER THE PROSE WAS CUT.
 *
 * Everything removed from this card was removed because it repeated something
 * already on screen, or described this platform's own configuration. What was
 * NOT removed is the caveat and the coverage line, and these tests are what
 * stops the next tidy-up taking them.
 */
describe('the progress score card', () => {
  const progress = (extra = {}) => ({
    outcome: 'SCORE_COMPUTED',
    score: 62.5,
    band: {
      label: 'More favourable movement than unfavourable',
      description:
        'Across the parameters that could be assessed, more of the movement was in the direction recorded as favourable.',
    },
    scale: {
      direction: 'higher_is_better',
      direction_text:
        'A higher number means more of your results moved in the better direction between the two reports.',
    },
    coverage: {
      contributing_count: 8,
      features_examined: 12,
      excluded_count: 4,
      minimum_required: 3,
    },
    warnings: ['A change has to be big enough to count at all.'],
    what_this_is_not:
      'This number is not a health score, not a risk score and not a diagnosis.',
    ...extra,
  });

  it("prints the service's sentence and adds NOTHING in front of it", async () => {
    // The card printed the literal "Higher is better." immediately in front of
    // `direction_text`, which itself opened "The scale runs from 0 to 100 and
    // HIGHER IS BETTER" -- the card said it twice in one breath.
    //
    // MUTATION-FOUND WEAKNESS: the first version of this test counted
    // occurrences of "higher is better" and allowed one. Putting the literal
    // back SURVIVED it, because the rewritten service sentence does not
    // contain that phrase, so the prefix was the only copy and the count was
    // still 1. Counting a phrase cannot catch a page prepending its own
    // wording to an author's sentence; equality can.
    const data = progress();
    mount({ progress: { progress: data } });

    await screen.findByText(/Progress score/);
    const meaning = document.querySelector('.progress__meaning');
    expect(meaning.textContent.trim()).toBe(data.scale.direction_text);
  });

  it('does not print the band description, which restates the band label', async () => {
    mount({ progress: { progress: progress() } });

    await screen.findByText(/More favourable movement than unfavourable/);
    expect(
      screen.queryByText(/in the direction recorded as favourable/)
    ).not.toBeInTheDocument();
  });

  it('KEEPS the caveat', async () => {
    // Section 6ag: shortening is not the same decision as dropping. This
    // platform has found this class of sentence missing three times.
    mount({ progress: { progress: progress() } });

    expect(
      await screen.findByText(/not a health score, not a risk score and not a diagnosis/)
    ).toBeInTheDocument();
  });

  it('KEEPS the coverage line, in words that agree with their own numbers', async () => {
    // An absence: four results are not in the number, and the card says so.
    mount({ progress: { progress: progress() } });

    const said = await screen.findByText(/Worked out from 8 of your 12 results/);
    expect(said.textContent).toMatch(/other 4 could not be compared/);
    expect(said.textContent).toMatch(/they are not in the number/);
    // The placeholder plural is gone from this card.
    expect(said.textContent).not.toMatch(/\(s\)/);
  });

  it('uses a singular pronoun when exactly one result is excluded', async () => {
    mount({ progress: { progress: progress({
        coverage: {
          contributing_count: 8,
          features_examined: 9,
          excluded_count: 1,
          minimum_required: 3,
        },
      }) } });

    const said = await screen.findByText(/Worked out from 8 of your 9 results/);
    expect(said.textContent).toMatch(/it is not in the number/);
  });

  it('mentions the minimum only when it is the reason there is no score', async () => {
    // "At least 3 are needed" under a score built from 8 answers a question
    // nobody asked. Under a refusal it is the whole explanation.
    mount({ progress: { progress: progress() } });
    await screen.findByText(/Worked out from 8 of your 12 results/);
    expect(screen.queryByText(/At least 3 are needed/)).not.toBeInTheDocument();
  });

  it('places the score on the scale, and never in a risk colour', async () => {
    // The card's own text says this is not a risk score. A green marker at 80
    // and a rust one at 20 would contradict that from two inches away.
    mount({ progress: { progress: progress() } });

    await screen.findByText(/Progress score/);
    const mark = document.querySelector('.scorescale__mark');
    expect(mark).not.toBeNull();
    expect(mark.getAttribute('fill')).toBe('var(--brand)');
    // 62.5 on a 10..250 track.
    expect(Number(mark.getAttribute('cx'))).toBeCloseTo(160, 0);
  });

  it('draws no scale marker for a score outside the declared 0-100', async () => {
    mount({ progress: { progress: progress({ score: 140 }) } });
    await screen.findByText(/Progress score/);
    expect(document.querySelector('.scorescale')).toBeNull();
  });

  it('does not repeat a warning the comparison card already showed', async () => {
    // Module 30 inherits Module 29's warnings, so the intermediate-report
    // sentence arrived on both cards and printed twice on one screen.
    const shared = 'This comparison uses two of your reports.';
    mount({
      comparison: { comparison: { warnings: [shared], parameters: {} } },
      progress: { progress: progress({ warnings: [shared, 'A change has to be big enough to count at all.'] }) } });

    await screen.findByText(/Progress score/);
    const hits = screen.getAllByText(new RegExp(shared.replace(/\./g, '\\.')));
    expect(hits).toHaveLength(1);
  });

  it('still shows a warning that ONLY the progress payload carries', async () => {
    // The filter must not swallow this card's own warnings.
    mount({
      comparison: {
        comparison: {
          warnings: ['This comparison uses two of your reports.'],
          parameters: {},
        },
      },
      progress: {
        progress: progress({
          warnings: [
            'This comparison uses two of your reports.',
            'Only progress says this.',
          ],
        }),
      },
    });

    expect(await screen.findByText(/Only progress says this/)).toBeInTheDocument();
  });
});

/**
 * NO INTERNAL NAME REACHES THE TRENDS TABLE.
 *
 * `PATIENT_LABEL` was imported on this page and used for the chart headings,
 * while the table below them printed `trend.feature` raw -- so one screen
 * carried "HbA1c (average blood sugar)" as a title and `hba1c`,
 * `blood_glucose`, `vitamin_b12`, `smoking_history` as row headings.
 *
 * Found while auditing the comparison table one row down, which was showing
 * "Self-described gender as stored by Module 2." That makes this the FIFTH
 * surface where this platform's own vocabulary has reached a reader
 * (MEMORY.md 6u, 6w, 6af, 6an-e). The standing rule from 6af is that it is
 * never one surface; the corollary this adds is that finding one is a reason
 * to sweep the screen it is on.
 */
describe('the trends table names parameters for a reader', () => {
  const trends = (features) => ({
    trends: { features },
    history: { included: 3, considered: 3 },
  });

  const row = (feature) => ({
    feature,
    outcome: 'TREND_CLASSIFIED',
    trend: 'improving',
    readings: [],
  });

  it('shows the reader-facing name, not the feature key', async () => {
    mount({
      trends: trends({
        hba1c: row('hba1c'),
        vitamin_b12: row('vitamin_b12'),
        smoking_history: row('smoking_history'),
      }),
    });

    await screen.findByText(/Trends over time/);
    const headings = [...document.querySelectorAll('table tbody th')].map((th) =>
      th.textContent.trim()
    );
    expect(headings).toContain('HbA1c (average blood sugar)');
    expect(headings).toContain('Vitamin B12');
    // The shared table stores this lower case for mid-sentence use; a row
    // heading raises the first letter without editing the shared table.
    expect(headings).toContain('Smoking history');
    for (const raw of ['hba1c', 'vitamin_b12', 'smoking_history']) {
      expect(headings).not.toContain(raw);
    }
  });

  it('falls back to the key rather than printing nothing', async () => {
    // A feature the label table has never heard of must still be nameable:
    // a blank row heading is worse than an ugly one, because a reader cannot
    // tell which parameter the row is about.
    mount({ trends: trends({ some_new_marker: row('some_new_marker') }) });

    await screen.findByText(/Trends over time/);
    const headings = [...document.querySelectorAll('table tbody th')].map((th) =>
      th.textContent.trim()
    );
    expect(headings).toContain('Some_new_marker');
  });
});

/**
 * THE TREND CHARTS, COLLAPSED.
 *
 * Nine charts at ~200px each were most of this page. The condition that makes
 * closing them safe is the same one the profile questions have: THE SUMMARY
 * STATES THE FINDING. A shut list that hid its own directions would make a
 * reader open nine boxes to learn what the open list told them at a glance.
 */
describe('the trend charts collapse', () => {
  const chartable = (feature, trend, outcome = 'TREND_CLASSIFIED') => ({
    feature,
    outcome,
    trend,
    canonical_unit: '%',
    points: [
      { date: '2026-09-07', value: 8.4, unit: '%' },
      { date: '2026-09-11', value: 5.2, unit: '%' },
    ],
  });

  const charts = () =>
    [...document.querySelectorAll('.trend-chart__block')];

  it('starts closed and still says which way each parameter moved', async () => {
    mount({
      trends: {
        trends: { features: { hba1c: chartable('hba1c', 'improving') } },
        history: { included: 2, considered: 2 },
      },
    });

    await screen.findByText(/Trends over time/);
    const block = charts()[0];
    expect(block.tagName).toBe('DETAILS');
    expect(block.hasAttribute('open')).toBe(false);
    const summary = block.querySelector('summary');
    expect(summary.textContent).toMatch(/HbA1c \(average blood sugar\)/);
    expect(summary.textContent).toMatch(/improving/);
  });

  it('never summarises a direction the service did not classify', async () => {
    // MEMORY 6z: a payload carrying `trend` without a classification printed
    // the string "null" as a direction once already. The summary reads the
    // same two-part predicate the table does, and absence wins.
    mount({
      trends: {
        trends: {
          features: {
            hba1c: chartable('hba1c', 'improving', 'INSUFFICIENT_DATA'),
          },
        },
        history: { included: 2, considered: 2 },
      },
    });

    await screen.findByText(/Trends over time/);
    const summary = charts()[0].querySelector('summary');
    expect(summary.textContent).toMatch(/no direction/);
    expect(summary.textContent).not.toMatch(/improving/);
  });

  it('keeps the chart itself inside the disclosure', async () => {
    mount({
      trends: {
        trends: { features: { hba1c: chartable('hba1c', 'improving') } },
        history: { included: 2, considered: 2 },
      },
    });

    await screen.findByText(/Trends over time/);
    const block = charts()[0];
    expect(block.querySelector('svg')).not.toBeNull();
    expect(block.querySelector('summary svg')).toBeNull();
  });
});


/**
 * WHY A CHART HAS NO DIRECTION, ON THE CHART.
 *
 * Found by a reader looking at their own blood-sugar chart: a line climbing
 * from 88 to 168 under the words "no direction". The service had already
 * explained itself -- Module 28 returned
 *
 *   NOT_COMPARABLE_SAMPLE_TIMING
 *   "Blood glucose readings were taken under different sample timings
 *    (fasting, random). Those are not comparable quantities, so no trend is
 *    reported."
 *
 * -- and the page was already rendering that sentence, in the TABLE further
 * down. Which is no use at all to someone looking at the picture.
 *
 * The refusal itself is correct: on that account the first two readings are
 * fasting and the last two random, so most of the climb is the change of
 * test rather than a change in the reader.
 */
describe('Module 28 -- the chart says why it has no direction', () => {
  const noDirection = (feature, outcome, reason) => ({
    feature,
    outcome,
    trend: null,
    reason,
    canonical_unit: 'mg/dl',
    points: [
      { date: '2026-09-09', value: 88, unit: 'mg/dl' },
      { date: '2026-09-13', value: 168, unit: 'mg/dl' },
    ],
  });

  const TIMING = 'Blood glucose readings were taken under different sample '
    + 'timings (fasting, random). Those are not comparable quantities, so no '
    + 'trend is reported.';

  it('puts the service sentence on the panel, not only in the table', async () => {
    mount({
      trends: {
        trends: {
          features: {
            blood_glucose: noDirection(
              'blood_glucose',
              'NOT_COMPARABLE_SAMPLE_TIMING',
              TIMING
            ),
          },
        },
        history: { included: 4, considered: 4 },
      },
    });

    await screen.findByText(/Trends over time/);
    const block = [...document.querySelectorAll('.trend-chart__block')][0];
    const why = block.querySelector('.trend-chart__why');
    expect(why).not.toBeNull();
    expect(why.textContent).toMatch(/different sample timings/);
    expect(why.textContent).toMatch(/fasting, random/);
  });

  it('says nothing extra when the direction WAS classified', async () => {
    // A panel that explains itself when there is nothing to explain is noise.
    mount({
      trends: {
        trends: {
          features: {
            hba1c: {
              feature: 'hba1c',
              outcome: 'TREND_CLASSIFIED',
              trend: 'improving',
              reason: 'A sentence the panel must NOT show, because there is a direction.',
              canonical_unit: '%',
              points: [
                { date: '2026-09-07', value: 8.4, unit: '%' },
                { date: '2026-09-11', value: 5.2, unit: '%' },
              ],
            },
          },
        },
        history: { included: 2, considered: 2 },
      },
    });

    await screen.findByText(/Trends over time/);
    const block = [...document.querySelectorAll('.trend-chart__block')][0];
    expect(block.querySelector('.trend-chart__why')).toBeNull();
  });

  it('adds nothing when the service gave no sentence', async () => {
    // The fallback wording belongs to the table row, which has a column to
    // fill. A panel invents nothing.
    mount({
      trends: {
        trends: {
          features: {
            blood_glucose: noDirection('blood_glucose', 'INSUFFICIENT_DATA', undefined),
          },
        },
        history: { included: 1, considered: 1 },
      },
    });

    await screen.findByText(/Trends over time/);
    const block = [...document.querySelectorAll('.trend-chart__block')][0];
    expect(block.querySelector('.trend-chart__why')).toBeNull();
  });
});

/**
 * "STABLE" IS THE OTHER CASE WHERE THE WORDS AND THE PICTURE DISAGREE.
 *
 * It does not mean the line is flat. It means the movement is inside the band
 * where this test's own variation lives: cholesterol 186 -> 172 is -7.53 %
 * against a 17 % band -- a real fall, and smaller than the noise. The reader
 * saw a steep line labelled "stable" with nothing to reconcile them.
 */
describe('Module 28 -- a stable panel says what stable means', () => {
  const REASON =
    'TOTAL cholesterol went from 186 to 172 mg/dl between 2026-09-09 and '
    + '2026-09-11 (2 days apart), a change of -14 mg/dl, -7.53 %. That is '
    + 'within the declared stability band for this feature (17 % and 5 mg/dl), '
    + 'so the series is reported as stable.';

  const stable = (reason) => ({
    feature: 'cholesterol',
    outcome: 'TREND_CLASSIFIED',
    trend: 'stable',
    reason,
    canonical_unit: 'mg/dl',
    stability: { significant_change_pct: 17, min_absolute_change: 5 },
    change: { first_value: 186, last_value: 172 },
    points: [
      { date: '2026-09-09', value: 186, unit: 'mg/dl' },
      { date: '2026-09-11', value: 172, unit: 'mg/dl' },
    ],
  });

  it('explains what stable means, on the panel', async () => {
    mount({
      trends: {
        trends: { features: { cholesterol: stable(REASON) } },
        history: { included: 2, considered: 2 },
      },
    });

    await screen.findByText(/Trends over time/);
    const block = [...document.querySelectorAll('.trend-chart__block')][0];
    const why = block.querySelector('.trend-chart__why');
    expect(why).not.toBeNull();
    expect(why.textContent).toMatch(/within the declared stability band/);
    expect(why.textContent).toMatch(/17 %/);
  });

  it('still calls it stable in the summary', async () => {
    // The explanation qualifies the word; it does not replace it.
    mount({
      trends: {
        trends: { features: { cholesterol: stable(REASON) } },
        history: { included: 2, considered: 2 },
      },
    });

    await screen.findByText(/Trends over time/);
    const summary = [...document.querySelectorAll('.trend-chart__block')][0]
      .querySelector('summary');
    expect(summary.textContent).toMatch(/stable/);
  });

  it('invents nothing when the service gave no sentence', async () => {
    mount({
      trends: {
        trends: { features: { cholesterol: stable(undefined) } },
        history: { included: 2, considered: 2 },
      },
    });

    await screen.findByText(/Trends over time/);
    const block = [...document.querySelectorAll('.trend-chart__block')][0];
    expect(block.querySelector('.trend-chart__why')).toBeNull();
  });
});

/**
 * THE LABORATORY'S OWN REPEATED PARAMETERS, ON THE TIMELINE.
 *
 * Module 28 trends canonical features, so everything this platform does not
 * assess was absent from the page entirely -- a reader with reports full of
 * such parameters asked why none of them appeared.
 *
 * EVERY NAME BELOW IS INVENTED. The feature must work for any report carrying
 * any unknown parameter; a fixture drawn from this project's own reports
 * would let the suite pass by recognising them.
 */
describe('Timeline -- parameters this platform does not assess', () => {
  const series = (name, points, blocked = null, unit = 'mg/L') => ({
    key: name.toLowerCase(),
    name,
    unit: blocked ? null : unit,
    blocked,
    points: points.map(([date, value]) => ({ date: `${date}T00:00:00Z`, value, unit })),
  });

  const labSeries = (overrides = {}) => ({
    series: [],
    consideredCount: 0,
    plottedCount: 0,
    blockedCount: 0,
    singleReportCount: 0,
    notNumericCount: 0,
    ...overrides,
  });

  const mountLab = (data) =>
    mount({ trends: { trends: { features: {} }, history: { included: 2 }, labSeries: data } });

  it('shows a parameter the platform does not assess', async () => {
    mountLab(
      labSeries({
        series: [series('ZORBLEX FACTOR(ZBX)', [['2026-01-01', 12.1], ['2026-02-01', 38.9]])],
        consideredCount: 3,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Other parameters on your reports/);
    expect(screen.getByText('ZORBLEX FACTOR(ZBX)')).toBeInTheDocument();
  });

  it('gives it NO direction word, because there is no polarity for it', async () => {
    mountLab(
      labSeries({
        series: [series('ZORBLEX FACTOR(ZBX)', [['2026-01-01', 1], ['2026-02-01', 99]])],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Other parameters on your reports/);
    const section = screen.getByText(/Other parameters on your reports/).closest('section');
    // THE PROPERTY IS THE BADGE, NOT THE WORDS. The section's own caveat says
    // "no direction is given", which is the point rather than a violation of
    // it -- so this asserts that no panel carries a direction ELEMENT.
    expect(section.querySelectorAll('.trend')).toHaveLength(0);
    expect(section.querySelectorAll('.trend-chart__nodirection')).toHaveLength(0);
    for (const summary of section.querySelectorAll('summary')) {
      expect(summary.textContent).not.toMatch(/improving|worsening|stable/i);
    }
  });

  it('shows the readings when the units disagree, and says why there is no line', async () => {
    mountLab(
      labSeries({
        series: [
          series('FRIMBULATOR', [['2026-01-01', 101.9], ['2026-02-01', 13]], {
            reason: 'units_differ',
            units: ['U/L', 'IU/L'],
          }),
        ],
        consideredCount: 1,
        blockedCount: 1,
      })
    );

    await screen.findByText(/Other parameters on your reports/);
    const text = screen.getByText(/Other parameters on your reports/).closest('section').textContent;
    expect(text).toMatch(/FRIMBULATOR/);
    expect(text).toMatch(/101\.9/);
    expect(text).toMatch(/13/);
    expect(text).toMatch(/different units/);
    expect(text).toMatch(/U\/L and IU\/L|IU\/L and U\/L/);
  });

  it('counts what it considered, so ten panels do not imply ten parameters', async () => {
    mountLab(
      labSeries({
        series: [series('ZORBLEX', [['2026-01-01', 1], ['2026-02-01', 2]])],
        consideredCount: 22,
        plottedCount: 1,
        singleReportCount: 10,
      })
    );

    await screen.findByText(/Other parameters on your reports/);
    expect(screen.getByText(/22 parameters considered/)).toBeInTheDocument();
    expect(screen.getByText(/10 appeared on only one report/)).toBeInTheDocument();
  });

  it('warns that the scale covers only the readings', async () => {
    // These have no stability band and no reference interval, so the axis
    // cannot mean anything more than the two points on it.
    mountLab(
      labSeries({
        series: [series('ZORBLEX', [['2026-01-01', 1], ['2026-02-01', 2]])],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Other parameters on your reports/);
    expect(screen.getByText(/even a small change looks large/)).toBeInTheDocument();
  });

  it('renders nothing at all when there is nothing to show', async () => {
    mountLab(labSeries());
    await screen.findByText(/Trends over time/);
    expect(screen.queryByText(/Other parameters on your reports/)).toBeNull();
  });

  it('survives the section being absent from an older payload', async () => {
    mount({ trends: { trends: { features: {} }, history: { included: 2 } } });
    await screen.findByText(/Trends over time/);
    expect(screen.queryByText(/Other parameters on your reports/)).toBeNull();
  });
});
