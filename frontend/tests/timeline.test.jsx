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
              // THE READING IS CARRIED, because the real payload carries it.
              // A feature with one usable reading arrives with one point --
              // the single-reading test below is driven by exactly that shape
              // off the live service. The fixture said `usable_point_count: 1`
              // and then supplied no point, which is a shape Module 28 does
              // not produce.
              points: [{ date: '2026-01-10T00:00:00Z', value: 6.1, unit: '%' }],
              gaps: [],
              reason:
                'hba1c: 1 usable reading(s). At least two are needed before any change can be described. This is not the same as no change having occurred.',
            },
          },
          summary: { improving: 0, worsening: 0, stable: 0, not_determinable: 1 },
        },
      },
    });

    // ON THE CHART, which is where the refusal is now stated. The table that
    // used to carry it under the word "No trend" is gone; the sentence itself
    // never moved, and it is the sentence that matters.
    expect(await screen.findByText('no direction')).toBeInTheDocument();
    // SCOPED TO THE CHART'S OWN "WHY" LINE. The chart states this three times
    // -- in that paragraph, in its accessible title, and in its no-line
    // notice -- so an unscoped match finds all three and fails on the
    // multiple. What this test needs is that the service's sentence reaches
    // the reader; where else the chart repeats it is the chart's own business.
    expect(document.querySelector('.trend-chart__why').textContent).toMatch(
      /not the same as no change having occurred/
    );
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
              points: [
                { date: '2026-09-01', value: 6.1, unit: '%' },
                { date: '2026-09-07', value: 6.4, unit: '%' },
                { date: '2026-09-11', value: 6.8, unit: '%' },
              ],
              gaps: [],
              change: { first_value: 6.1, last_value: 6.8 },
            },
          },
          summary: { improving: 0, worsening: 1, stable: 0, not_determinable: 0 },
        },
      },
    });

    expect(await screen.findByText('worsening')).toBeInTheDocument();
    // THE PAIR, ON THE SHUT ROW. This is the deleted table's
    // `First -> latest` column, the one part of it that came back -- a reader
    // scanning closed panels should not have to open one to learn from what
    // to what.
    const pair = document.querySelector('.disclosure__pair');
    expect(pair.textContent).toBe('6.1 → 6.8 %');
    // THE UNIT ONCE, AT THE END. On both ends it wrapped the longest rows.
    expect(pair.textContent.match(/%/g)).toHaveLength(1);
    // The middle reading is NOT in the pair -- first and latest, not every one.
    expect(pair.textContent).not.toContain('6.4');
    expect(document.querySelectorAll('.trend-chart__point')).toHaveLength(3);
  });

  it('prints no pair for a feature with one reading and no change', async () => {
    // INSUFFICIENT_DATA carries no `change`, so there is nothing to pair. An
    // arrow with one end missing would be the row inventing the other end.
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
              points: [{ date: '2026-01-10', value: 6.1, unit: '%' }],
              gaps: [],
              reason: 'hba1c: 1 usable reading(s). At least two are needed.',
            },
          },
          summary: { improving: 0, worsening: 0, stable: 0, not_determinable: 1 },
        },
      },
    });

    await screen.findByText('no direction');
    expect(document.querySelectorAll('.disclosure__pair')).toHaveLength(0);
    expect(document.querySelector('.trend-chart__block > summary').textContent).not.toContain(
      '→'
    );
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
              // Two usable readings means two points in the real payload.
              points: [
                { date: '2026-09-09T00:00:00Z', value: 9.2, unit: 'g/dl' },
                { date: '2026-09-13T00:00:00Z', value: 12.5, unit: 'g/dl' },
              ],
              gaps: [],
              reason: 'No direction of benefit is declared for hemoglobin.',
            },
          },
          summary: { improving: 0, worsening: 0, stable: 0, not_determinable: 1 },
        },
      },
    });

    // The refusal, and the service's own sentence for it, both on the chart.
    expect(await screen.findByText('no direction')).toBeInTheDocument();
    expect(
      screen.getByText(/No direction of benefit is declared/)
    ).toBeInTheDocument();
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

    await screen.findByText('no direction');
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

    // THE CARD, THEN THE ABSENCE. `age` is NOT_TRENDABLE, so it draws no
    // chart -- and with the table gone it has no row either, so the parameter
    // is not on this card at all. The line this test exists to prevent, a
    // person getting 24 years younger, cannot be drawn when nothing is.
    await screen.findByText(/Trends over time/);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(document.querySelectorAll('.trend-chart__line')).toHaveLength(0);
    expect(document.querySelectorAll('.trend-chart__block')).toHaveLength(0);
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

    await screen.findByText(/Trends over time/);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(document.querySelectorAll('.trend-chart__block')).toHaveLength(0);
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

    await screen.findByText(/Trends over time/);
    // An empty frame adds nothing, and there is no longer a row beside it to
    // add anything to either.
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(document.querySelectorAll('.trend-chart__block')).toHaveLength(0);
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

describe('comparison -- the rest of the report', () => {
  // Module 29 compares the features this platform assesses. The two real
  // reports carry 28 parameters between them and the card showed twelve, so
  // the reader counted them and asked where the others were -- the same
  // question, and the same answer, as the timeline.
  const labRow = (over = {}) => ({
    key: 'zbx',
    name: 'ZORBLEX',
    joinedFrom: null,
    previous: 12.1,
    current: 38.9,
    previousUnit: 'mg/L',
    currentUnit: 'mg/L',
    unit: 'mg/L',
    blocked: null,
    previousFlag: null,
    currentFlag: null,
    category: 'worsened',
    symbol: '↑',
    ...over,
  });

  const mountPair = (labRows, table = []) =>
    mount({ comparison: { comparison: { table }, labComparison: { rows: labRows, count: labRows.length } } });

  it('puts unassessed parameters in the SAME table, not a second one', async () => {
    mountPair([labRow()], [
      { feature: 'hba1c', description: 'HbA1c', unit: '%', previous: 5.4, current: 7, category: 'worsened' },
    ]);

    expect(await screen.findByText('ZORBLEX')).toBeInTheDocument();
    // One table on the card, carrying both kinds of row.
    expect(document.querySelectorAll('table.lab-table')).toHaveLength(1);
    const headings = [...document.querySelectorAll('table tbody th')].map((th) =>
      th.textContent.trim()
    );
    expect(headings).toContain('HbA1c');
    expect(headings.some((h) => h.startsWith('ZORBLEX'))).toBe(true);
  });

  it('counts every parameter on the card, both kinds', async () => {
    mountPair([labRow(), labRow({ key: 'frim', name: 'FRIMBULIN' })], [
      { feature: 'hba1c', description: 'HbA1c', unit: '%', previous: 5.4, current: 7, category: 'worsened' },
    ]);

    await screen.findByText('ZORBLEX');
    expect(screen.getByText(/3 parameters across these two reports/)).toBeInTheDocument();
  });

  it('shows BOTH units when the two reports disagree about them', async () => {
    // 101.9 U/L against 13 IU/L is the reason the row cannot be classified.
    // Hiding one unit would hide the reason.
    mountPair([
      labRow({
        previous: 101.9,
        current: 13,
        previousUnit: 'U/L',
        currentUnit: 'IU/L',
        unit: null,
        blocked: { reason: 'units_differ', units: ['U/L', 'IU/L'] },
        category: 'not_classifiable',
        symbol: null,
      }),
    ]);

    await screen.findByText('ZORBLEX');
    expect(screen.getByText('101.9 U/L')).toBeInTheDocument();
    expect(screen.getByText('13 IU/L')).toBeInTheDocument();
    expect(
      screen.getByText(/different units, so the readings were not compared/)
    ).toBeInTheDocument();
  });

  it('renders a parameter on only one of the two reports as not measured', async () => {
    mountPair([labRow({ current: null, currentUnit: null, category: 'not_classifiable', symbol: null })]);

    await screen.findByText('ZORBLEX');
    expect(screen.getByText('12.1 mg/L')).toBeInTheDocument();
    expect(screen.getByText('This parameter was not on that report.')).toBeInTheDocument();
    // NOT rendered as zero. The whole point of the Absent component.
    expect(screen.queryByText('0 mg/L')).not.toBeInTheDocument();
  });

  it('shows a non-numeric result as the text the laboratory printed', async () => {
    mountPair([
      labRow({
        previous: null,
        current: null,
        previousRaw: 'Negative',
        currentRaw: 'Negative',
        // A NON-NUMERIC RESULT CARRIES NO UNIT, and the first version of this
        // fixture left `mg/L` on it, so the cell read "Negative mg/L". The
        // fixture was wrong about the data, not the component about the text.
        previousUnit: null,
        currentUnit: null,
        unit: null,
        category: 'not_classifiable',
        symbol: null,
      }),
    ]);

    await screen.findByText('ZORBLEX');
    expect(screen.getAllByText('Negative').length).toBeGreaterThan(0);
  });

  it("uses Module 29's own category words for these rows too", async () => {
    // One vocabulary per table. `worsening` on the timeline is `worsened`
    // here, and these rows must not introduce a third set of words.
    mountPair([labRow({ category: 'worsened', symbol: '↑' })]);

    await screen.findByText('ZORBLEX');
    expect(screen.getByText(/worsened/)).toBeInTheDocument();
    expect(screen.queryByText(/worsening/)).not.toBeInTheDocument();
  });

  it('names the spellings it treated as one test', async () => {
    mountPair([labRow({ name: 'NEUTROPHILS', joinedFrom: ['Polymorphs', 'NEUTROPHILS'] })]);

    await screen.findByText(/NEUTROPHILS/);
    const heading = [...document.querySelectorAll('table tbody th')].find((th) =>
      th.textContent.includes('NEUTROPHILS')
    );
    expect(heading.textContent).toContain('2 names');
    expect(heading.querySelector('[title]').getAttribute('title')).toContain('Polymorphs');
  });

  it('never prints "unchanged" beside an arrow and two different numbers', async () => {
    // THE ROW WAS CONTRADICTING ITSELF ON SCREEN:
    //     EOSINOPHILS  5 %  ->  2 %   ↓ unchanged
    // The arrow says it moved, the numbers say it moved, the word says it did
    // not. What the category means is "it moved less than this test's own
    // variation", which is a much weaker claim, so it is said in words that
    // make that claim instead.
    mountPair([
      labRow({ name: 'EOSINOPHILS', previous: 5, current: 2, unit: '%', previousUnit: '%', currentUnit: '%', category: 'unchanged', symbol: '↓' }),
    ]);

    await screen.findByText('EOSINOPHILS');
    expect(screen.getByText(/no real change/)).toBeInTheDocument();
    expect(screen.queryByText(/unchanged/)).not.toBeInTheDocument();
    // The arrow stays. It is the true half of the row.
    expect(screen.getByText(/↓/)).toBeInTheDocument();
  });

  it("uses the same words for Module 29's own rows", async () => {
    // One table must not say "unchanged" for the assessed half and something
    // else for the rest.
    mountPair([], [
      { feature: 'bmi', description: 'Body mass index', unit: 'kg/m2', previous: 25.25, current: 25.25, category: 'unchanged', symbol: '→' },
    ]);

    await screen.findByText('Body mass index');
    expect(screen.getByText(/no real change/)).toBeInTheDocument();
    expect(screen.queryByText(/unchanged/)).not.toBeInTheDocument();
  });

  it('says nothing extra when there are no unassessed parameters', async () => {
    mountPair([], [
      { feature: 'hba1c', description: 'HbA1c', unit: '%', previous: 5.4, current: 7, category: 'worsened' },
    ]);

    await screen.findByText('HbA1c');
    expect(screen.getByText(/1 parameter across these two reports/)).toBeInTheDocument();
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
describe('the trends card names parameters for a reader', () => {
  const trends = (features) => ({
    trends: { features },
    history: { included: 3, considered: 3 },
  });

  // POINTS, BECAUSE A NAME NEEDS SOMETHING TO SIT ON.
  //
  // These fixtures used to carry no readings, because the table they were
  // written for printed a row per feature whether or not there was anything
  // to plot. The table is gone and the chart heading is the only name on this
  // card, so a feature with no point has no name to check. A real
  // TREND_CLASSIFIED feature always arrives with its points anyway -- this is
  // the producer's shape, not a convenience.
  const row = (feature) => ({
    feature,
    outcome: 'TREND_CLASSIFIED',
    trend: 'improving',
    canonical_unit: '%',
    points: [
      { date: '2026-09-07', value: 8.4, unit: '%' },
      { date: '2026-09-11', value: 5.2, unit: '%' },
    ],
    gaps: [],
    readings: [],
  });

  const titles = () =>
    [...document.querySelectorAll('.trend-chart__title')].map((h) =>
      h.textContent.trim()
    );

  it('shows the reader-facing name, not the feature key', async () => {
    // `smoking_history` WAS CHECKED HERE AND IS NOT ANY MORE, because it is
    // no longer on this card: it is a profile answer, it arrives NOT_NUMERIC,
    // and a feature with no trajectory now draws nothing rather than taking a
    // table row. It is still named for a reader in the comparison table
    // further down the page, which has its own test.
    mount({
      trends: trends({
        hba1c: row('hba1c'),
        vitamin_b12: row('vitamin_b12'),
      }),
    });

    await screen.findByText(/Trends over time/);
    expect(titles()).toContain('HbA1c (average blood sugar)');
    expect(titles()).toContain('Vitamin B12');
    for (const raw of ['hba1c', 'vitamin_b12']) {
      expect(titles()).not.toContain(raw);
    }
    // THE LEAK CLASS, NOT ONE OF ITS INSTANCES. This platform's keys are
    // snake_case and a reader's words never are, so an underscore anywhere in
    // the rendered card is this vocabulary escaping again -- the failure
    // MEMORY.md records on five separate surfaces.
    expect(document.body.textContent).not.toMatch(/\b[a-z]+_[a-z0-9_]+\b/);
  });

  it('falls back to the key rather than printing nothing', async () => {
    // A feature the label table has never heard of must still be nameable:
    // a blank heading is worse than an ugly one, because a reader cannot tell
    // which parameter the chart is about. The key is printed as it stands --
    // the capitalisation the deleted table applied went with it, and an
    // unlovely name a reader can match to their report beats no name.
    mount({ trends: trends({ some_new_marker: row('some_new_marker') }) });

    await screen.findByText(/Trends over time/);
    expect(titles()).toContain('some_new_marker');
  });

  it('counts the panels it actually renders, and the parts add up', async () => {
    // THE DEFECT THIS EXISTS FOR, and the reader spotted it on the screen.
    //
    // The line read `3 improving · 1 worsening · 3 stable · 5 not
    // determinable` -- Module 28's tally of its twelve ASSESSED features --
    // over a card showing twenty-six panels. It counted fourteen laboratory
    // panels not at all, and it counted `age`, `sex` and `smoking_history`,
    // which are no longer rendered anywhere on the card.
    //
    // A COUNT THAT CANNOT BE RECONCILED WITH THE ROWS UNDER IT is worse than
    // no count, because a reader who checks it stops trusting the ones that
    // are right. So the four parts must sum to the stated total.
    mount({
      trends: {
        history: { included: 2, considered: 2 },
        trends: {
          features: {
            hba1c: {
              feature: 'hba1c',
              outcome: 'TREND_CLASSIFIED',
              trend: 'worsening',
              canonical_unit: '%',
              points: [
                { date: '2026-09-01', value: 6.1, unit: '%' },
                { date: '2026-09-11', value: 6.8, unit: '%' },
              ],
              gaps: [],
            },
            // NOT_TRENDABLE: no chart, no row, and it must not be counted.
            age: {
              feature: 'age',
              outcome: 'NOT_TRENDABLE',
              trend: null,
              points: [
                { date: '2026-09-01', value: 58, unit: 'years' },
                { date: '2026-09-11', value: 58, unit: 'years' },
              ],
              gaps: [],
            },
          },
          // DELIBERATELY DISAGREEING with what is on the card, because this is
          // the payload field the old line trusted.
          summary: { improving: 9, worsening: 9, stable: 9, not_determinable: 9 },
        },
        labSeries: {
          series: [
            {
              key: 'zbx',
              name: 'ZORBLEX',
              unit: 'mg/L',
              blocked: null,
              points: [
                { date: '2026-09-01T00:00:00Z', value: 12.1, unit: 'mg/L' },
                { date: '2026-09-11T00:00:00Z', value: 38.9, unit: 'mg/L' },
              ],
              movementFrom: 12.1,
              movementTo: 38.9,
              movement: 'rose',
              trend: 'stable',
              classified: true,
            },
          ],
          readings: [
            {
              key: 'frim',
              name: 'FRIMBULIN',
              reason: 'one_report',
              rows: [{ date: '2026-09-11T00:00:00Z', valueRaw: '82', unit: '%', value: 82 }],
              latestFlag: 'high',
            },
          ],
        },
      },
    });

    await screen.findByText(/Trends over time/);
    const line = [...document.querySelectorAll('.card .hint')]
      .map((e) => e.textContent.replace(/\s+/g, ' ').trim())
      .find((t) => /improving/.test(t));

    // One assessed chart (hba1c, worsening), one lab series (stable), one lab
    // reading (no direction). `age` draws nothing and is not counted.
    expect(line).toMatch(/^3 parameters/);
    expect(line).toContain('0 improving');
    expect(line).toContain('1 worsening');
    expect(line).toContain('1 stable');
    expect(line).toContain('1 with no direction stated');
    // The payload's own summary said 9 of everything. It is not this line.
    expect(line).not.toContain('9');
  });

  it('does NOT repeat every chart in a table beneath it', async () => {
    // THE REMOVAL, PINNED. The card carried a
    // `Parameter / Direction / First -> latest / Readings` table under the
    // charts, and every row of it restated the direction word and the refusal
    // sentence already on the chart above. A test that asserts the old
    // wording is a test that will be satisfied by putting the table back, so
    // the four column headings and the row's own phrasing are listed here as
    // things that must not reappear on this card.
    mount({
      trends: trends({
        hba1c: row('hba1c'),
        vitamin_b12: row('vitamin_b12'),
      }),
    });

    await screen.findByText(/Trends over time/);
    expect(titles()).toHaveLength(2);
    for (const gone of ['Direction', 'First → latest', 'usable reading(s)', 'No trend']) {
      expect(screen.queryByText(gone)).not.toBeInTheDocument();
    }
    // The trends card holds no table at all now. The comparison table lower
    // down the page is a different section and is not mounted here.
    expect(document.querySelectorAll('table.lab-table')).toHaveLength(0);
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
describe('Timeline -- the laboratory\'s own repeated parameters', () => {
  const series = (name, points, blocked = null, unit = 'mg/L', overrides = {}) => {
    const mapped = points.map(([date, value]) => ({
      date: `${date}T00:00:00Z`,
      value,
      unit,
    }));
    const numeric = mapped.map((p) => p.value).filter((v) => v !== null);
    const paired = !blocked && numeric.length >= 2;
    return {
      key: name.toLowerCase(),
      name,
      unit: blocked ? null : unit,
      blocked,
      points: mapped,
      // THE PRODUCER SETS THESE ON EVERY NON-BLOCKED SERIES WITH TWO USABLE
      // READINGS, so the fixture does too -- and withholds them from a
      // blocked one exactly as `labSeriesService` does. A fixture that simply
      // omitted them would exercise a no-pair path the backend never returns,
      // which is the `basis.limitations` failure MEMORY.md 6w records: a
      // fixture written to the consumer's assumption cannot catch that
      // assumption being wrong.
      movementFrom: paired ? numeric[0] : null,
      movementTo: paired ? numeric[numeric.length - 1] : null,
      // DEFAULTED TO ABSENT, so every test that does not opt in exercises the
      // no-scale path -- which is what an older backend still returns.
      ...overrides,
    };
  };

  const reading = (name, rows, reason = 'one_report') => ({
    key: name.toLowerCase(),
    name,
    reason,
    rows: rows.map(([date, valueRaw, unit = null]) => ({
      date: `${date}T00:00:00Z`,
      valueRaw,
      unit,
      value: Number.isFinite(Number(valueRaw)) ? Number(valueRaw) : null,
    })),
  });

  const labSeries = (overrides = {}) => ({
    series: [],
    readings: [],
    consideredCount: 0,
    plottedCount: 0,
    blockedCount: 0,
    singleReportCount: 0,
    notNumericCount: 0,
    ...overrides,
  });

  const mountLab = (data) =>
    mount({ trends: { trends: { features: {} }, history: { included: 2 }, labSeries: data } });

  /** The one card these now live in, alongside the assessed parameters. */
  const card = () => screen.getByText(/Trends over time/).closest('section');

  it('appears in the SAME card as the assessed parameters', async () => {
    // Not a section of its own. The reader asked for these to sit with the
    // rest rather than under a heading setting them apart.
    mountLab(
      labSeries({
        series: [series('ZORBLEX FACTOR(ZBX)', [['2026-01-01', 12.1], ['2026-02-01', 38.9]])],
        consideredCount: 3,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(card().textContent).toMatch(/ZORBLEX FACTOR\(ZBX\)/);
  });

  it('prints the two readings on the shut row', async () => {
    // The pair a reader gets without opening anything. `12.1 -> 38.9` is
    // arithmetic on their own first and latest readings and says nothing
    // about meaning -- which is why it is uncoloured, like the movement word.
    mountLab(
      labSeries({
        series: [series('ZORBLEX FACTOR(ZBX)', [['2026-01-01', 12.1], ['2026-02-01', 38.9]])],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const pair = document.querySelector('.disclosure__pair');
    expect(pair).not.toBeNull();
    expect(pair.textContent).toBe('12.1 → 38.9 mg/L');
    // THE UNIT ONCE. Safe to state once only because `blocked` is exactly the
    // test that the two readings share a unit, and a blocked series gets no
    // pair -- the test below pins that half.
    expect(pair.textContent.match(/mg\/L/g)).toHaveLength(1);
    // NOT COLOURED LIKE A VERDICT. Green and rust mean better and worse on
    // this page, and two readings mean neither.
    expect(pair.className).not.toMatch(/improving|worsening|trend--/);
  });

  it('prints NO pair for a blocked series, only its numbers on opening', async () => {
    // 101.9 U/L and 13 IU/L with an arrow between them would assert the
    // comparison this feature refused to draw a line through. The word is
    // already withheld; the numbers must not claim it either.
    mountLab(
      labSeries({
        series: [
          series(
            'ZORBLEX FACTOR(ZBX)',
            [['2026-01-01', 101.9], ['2026-02-01', 13]],
            { reason: 'units_differ', units: ['U/L', 'IU/L'] }
          ),
        ],
        blockedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(document.querySelectorAll('.disclosure__pair')).toHaveLength(0);
    expect(
      document.querySelector('.trend-chart__block > summary').textContent
    ).not.toContain('→');
  });

  it('does not let the chart contradict the row above it', async () => {
    // FOUND ON SCREEN, NOT BY A TEST. NEUTROPHILS read `stable` on its row
    // while the chart inside the same panel said "No direction was classified
    // for them" -- because `classified` and `trend` were never passed down.
    // They were right to be absent before Module 35 existed and wrong the
    // moment it did.
    mountLab(
      labSeries({
        series: [
          series('Frimbulin', [['2026-01-01', 77], ['2026-02-01', 82]], null, '%', {
            trend: 'stable',
            classified: true,
            significantChangePct: 30,
          }),
        ],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const chart = document.querySelector('.trend-chart__block [aria-label]');
    expect(chart.getAttribute('aria-label')).toMatch(/stable/);
    expect(chart.getAttribute('aria-label')).not.toMatch(/No direction was classified/);
  });

  it('still says no direction was classified when there is no verdict', async () => {
    // The other half. A panel Module 35 refused, or one reached with a spent
    // quota, must keep saying so -- this is the state the page degrades to.
    mountLab(
      labSeries({
        series: [series('Frimbulin', [['2026-01-01', 77], ['2026-02-01', 82]])],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const chart = document.querySelector('.trend-chart__block [aria-label]');
    expect(chart.getAttribute('aria-label')).toMatch(/No direction was classified/);
  });

  it('names the printed spellings it treated as one test', async () => {
    // MODULE 36'S JOIN, MADE VISIBLE. The reader's report says one of these
    // and the panel is headed with the other, so without this line it reads
    // as a parameter they never had -- and a join nobody can see is the page
    // rewriting their report rather than regrouping it.
    mountLab(
      labSeries({
        series: [
          series('Frimbulin', [['2026-01-01', 12.1], ['2026-02-01', 38.9]], null, 'mg/L', {
            joinedFrom: ['Zorblex Factor', 'Frimbulin'],
          }),
        ],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const note = document.querySelector('.trend-chart__joined');
    expect(note).not.toBeNull();
    expect(note.textContent).toContain('Zorblex Factor');
    expect(note.textContent).toContain('Frimbulin');
  });

  it('says nothing about names when nothing was joined', async () => {
    // The commonest case by far, and it must stay silent -- a note on every
    // panel is the commentary the reader already asked to have removed.
    mountLab(
      labSeries({
        series: [series('Frimbulin', [['2026-01-01', 12.1], ['2026-02-01', 38.9]])],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(document.querySelectorAll('.trend-chart__joined')).toHaveLength(0);
  });

  it('prints no pair for a parameter on only one report', async () => {
    // One reading is not a change. Its value is shown in full when opened.
    mountLab(
      labSeries({
        readings: [reading('ZORBLEX FACTOR(ZBX)', [['2026-01-01', '82', '%']])],
        singleReportCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(document.querySelectorAll('.disclosure__pair')).toHaveLength(0);
  });

  // ================== the commentary that was removed ======================
  //
  // These sat above the panels: a heading naming them as tests this tool does
  // not assess, and three paragraphs about interpretation, the scale and the
  // reference range. The reader asked for all of it to go.
  //
  // PINNED SO IT CANNOT CREEP BACK. Every control those paragraphs described
  // is still enforced -- in labSeriesService, which emits no direction, and in
  // TrendChart, which draws no band. What was removed was the description, not
  // the guarantee, and the tests below are what keep that distinction honest.
  it('says nothing about assessing, interpreting, or the scale', async () => {
    mountLab(
      labSeries({
        series: [
          series('LYMPHOCYTES', [['2026-01-01', 15], ['2026-02-01', 14]], null, '%', {
            referenceScale: { low: 20, high: 45 },
            referenceAgreement: 'differ',
          }),
        ],
        readings: [reading('TSH', [['2026-01-01', '1.81', 'uIU/mL']])],
        consideredCount: 2,
        plottedCount: 1,
        singleReportCount: 1,
        scaledCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const text = card().textContent;
    for (const gone of [
      /Other parameters on your reports/,
      /does not assess/i,
      /Nothing here is interpreted/i,
      /no condition is derived/i,
      /reference range printed on/i,
      /No range is drawn/i,
      /parameters? considered/i,
      /Reported once, or not as a number/i,
      /even a small change looks large/i,
    ]) {
      expect(text).not.toMatch(gone);
    }
  });

  // =========================== the status these may carry ==================
  //
  // A reader asked why these showed no status when the assessed panels say
  // improving / worsening / stable. Those three need a polarity and a
  // stability band, and MODULE 35 NOW SUPPLIES BOTH -- from the test name
  // alone -- so a classified panel carries the clinical word like any other.
  //
  // WHAT THESE TESTS STILL PIN is the panel that was NOT classified: a spent
  // quota, a refused polarity and a variation figure outside the permitted
  // set all land there, and such a panel must show only what is true of it --
  // which way the numbers went, and the laboratory's own marking.

  it('shows which way the numbers went, without a clinical word', async () => {
    mountLab(
      labSeries({
        series: [
          series('ZORBLEX', [['2026-01-01', 12.1], ['2026-02-01', 38.9]], null, 'mg/L', {
            movement: 'rose',
            latestFlag: 'high',
          }),
        ],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    // SCOPED TO THE PANEL, NOT THE CARD, and the rescoping is the point.
    //
    // This asserted over the whole card and broke when the card gained its
    // own tally line -- `26 parameters · 4 improving · 2 worsening · 13
    // stable · 7 with no direction stated` -- which contains all three words
    // as LABELS FOR COUNTS. That is not a clinical claim about any parameter.
    //
    // What must never happen is one of those words appearing as THIS panel's
    // status when nothing classified it, so the panel is what is asserted on.
    const panel = document.querySelector('.trend-chart__block > summary');
    expect(panel.textContent).toMatch(/rose/);
    expect(panel.textContent).not.toMatch(/improving|worsening|stable/i);
  });

  it("shows the laboratory's own marking, attributed to the laboratory", async () => {
    mountLab(
      labSeries({
        series: [
          series('ZORBLEX', [['2026-01-01', 35], ['2026-02-01', 45]], null, 'mm/hr', {
            movement: 'rose',
            latestFlag: 'high',
          }),
        ],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const chip = card().querySelector('.lab-status__flag');
    expect(chip.textContent).toBe('High');
    // WHOSE JUDGEMENT IT IS, in the markup rather than only in a comment.
    expect(chip.getAttribute('title')).toMatch(/laboratory/i);
  });

  it('does NOT colour the movement word like a trend', async () => {
    // Green and rust mean better and worse on this page. "rose" is arithmetic
    // and must not borrow their ink.
    mountLab(
      labSeries({
        series: [
          series('ZORBLEX', [['2026-01-01', 1], ['2026-02-01', 99]], null, 'mg/L', {
            movement: 'rose',
            latestFlag: null,
          }),
        ],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const section = card();
    expect(section.querySelectorAll('.trend--worsening')).toHaveLength(0);
    expect(section.querySelectorAll('.trend--improving')).toHaveLength(0);
    expect(section.querySelector('.lab-status__move').className).not.toMatch(/trend--/);
  });

  it('shows NO marking chip when the laboratory marked nothing', async () => {
    // Null is "not checked". Rendering it as "In range" would be a laboratory
    // verdict nobody gave -- an absence becoming a reassurance.
    mountLab(
      labSeries({
        series: [
          series('ZORBLEX', [['2026-01-01', 34.4], ['2026-02-01', 37.9]], null, '%', {
            movement: 'rose',
            latestFlag: null,
          }),
        ],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const section = card();
    expect(section.querySelectorAll('.lab-status__flag')).toHaveLength(0);
    expect(section.textContent).not.toMatch(/In range/);
  });

  it('gives a blocked series no movement word', async () => {
    mountLab(
      labSeries({
        series: [
          series('FRIMBULATOR', [['2026-01-01', 101.9], ['2026-02-01', 13]], {
            reason: 'units_differ',
            units: ['U/L', 'IU/L'],
          }, 'U/L', { movement: null, latestFlag: 'normal' }),
        ],
        consideredCount: 1,
        blockedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(card().querySelectorAll('.lab-status__move')).toHaveLength(0);
  });

  it('shows improving/worsening/stable once Module 35 classifies it', async () => {
    mountLab(
      labSeries({
        series: [
          series('ZORBLEX', [['2026-01-01', 12.1], ['2026-02-01', 38.9]], null, 'mg/L', {
            movement: 'rose',
            latestFlag: 'high',
            trend: 'worsening',
            classified: true,
            significantChangePct: 57,
          }),
        ],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const badge = card().querySelector('.trend--worsening');
    expect(badge.textContent).toBe('worsening');
  });

  it('REPLACES the movement word rather than showing both', async () => {
    // "rose" and "worsening" in one row are two answers to one question, and
    // a reader would reasonably read them as two findings.
    mountLab(
      labSeries({
        series: [
          series('ZORBLEX', [['2026-01-01', 12.1], ['2026-02-01', 38.9]], null, 'mg/L', {
            movement: 'rose',
            trend: 'worsening',
            classified: true,
          }),
        ],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const section = card();
    expect(section.querySelectorAll('.lab-status__move')).toHaveLength(0);
    expect(section.textContent).not.toMatch(/\brose\b/);
  });

  it('branches on `classified`, never on the trend word alone', async () => {
    // §6z rendered the string "null" as a direction on exactly this mistake.
    // A trend word without a classification loses to the movement word.
    mountLab(
      labSeries({
        series: [
          series('ZORBLEX', [['2026-01-01', 12.1], ['2026-02-01', 38.9]], null, 'mg/L', {
            movement: 'rose',
            trend: 'worsening',
            classified: false,
          }),
        ],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const section = card();
    expect(section.querySelectorAll('.trend--worsening')).toHaveLength(0);
    expect(section.textContent).toMatch(/rose/);
  });

  it('falls back to the movement word when no classification arrives', async () => {
    // A spent quota, an unconfigured key and a service that is down all land
    // here. The panel keeps what it had before Module 35 existed.
    mountLab(
      labSeries({
        series: [
          series('ZORBLEX', [['2026-01-01', 12.1], ['2026-02-01', 38.9]], null, 'mg/L', {
            movement: 'rose',
            latestFlag: 'high',
          }),
        ],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const section = card();
    expect(section.textContent).toMatch(/rose/);
    expect(section.querySelectorAll('.trend--worsening')).toHaveLength(0);
  });

  it('gives it NO direction word, because there is no polarity for it', async () => {
    // THE PROPERTY IS THE BADGE, NOT THE WORDS. The removed paragraph used to
    // say "no direction is given"; what makes it true is that the service
    // emits none and this panel renders none.
    mountLab(
      labSeries({
        series: [series('ZORBLEX FACTOR(ZBX)', [['2026-01-01', 1], ['2026-02-01', 99]])],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const section = card();
    expect(section.querySelectorAll('.trend')).toHaveLength(0);
    expect(section.querySelectorAll('.trend-chart__nodirection')).toHaveLength(0);
    for (const summary of section.querySelectorAll('summary')) {
      expect(summary.textContent).not.toMatch(/improving|worsening|stable/i);
    }
  });

  it('shows the readings when the units disagree, and draws no line', async () => {
    // Two scales on one axis is the failure 6z caught once. No chart -- and
    // the values are still the reader's, so they are listed.
    mountLab(
      labSeries({
        series: [
          series('FRIMBULATOR', [['2026-01-01', 101.9], ['2026-02-01', 13]], {
            reason: 'units_differ',
            units: ['U/L', 'IU/L'],
          }, 'U/L'),
        ],
        consideredCount: 1,
        blockedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const section = card();
    expect(section.textContent).toMatch(/FRIMBULATOR/);
    expect(section.textContent).toMatch(/101\.9/);
    expect(section.textContent).toMatch(/13/);
    expect(section.querySelectorAll('svg')).toHaveLength(0);
  });

  it('never prints the reference range itself, or draws a band for it', async () => {
    // The interval is a scale, not a finding. Printing 20-45 beside a reading
    // would state one laboratory's range as though it were the test's.
    mountLab(
      labSeries({
        series: [
          series('LYMPHOCYTES', [['2026-01-01', 15], ['2026-02-01', 14]], null, '%', {
            referenceScale: { low: 20, high: 45 },
            referenceAgreement: 'differ',
          }),
        ],
        consideredCount: 1,
        plottedCount: 1,
        scaledCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const section = card();
    expect(section.textContent).not.toMatch(/20\s*[-–]\s*45/);
    expect(section.querySelectorAll('.trend-chart__band')).toHaveLength(0);
  });

  it('lists a parameter seen on one report, with its value and date', async () => {
    mountLab(
      labSeries({
        readings: [
          reading('TSH (Thyroid Stimulating Hormone)', [['2026-09-12', '3.51', 'ulU/mL']]),
        ],
        consideredCount: 1,
        singleReportCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const text = card().textContent;
    expect(text).toMatch(/TSH \(Thyroid Stimulating Hormone\)/);
    expect(text).toMatch(/3\.51 ulU\/mL/);
  });

  it('shows a NON-NUMERIC result as printed, not as a blank', async () => {
    mountLab(
      labSeries({
        readings: [
          reading(
            'Colour',
            [['2026-09-12', 'Pale Yellow'], ['2026-09-13', 'Negative']],
            'not_numeric'
          ),
        ],
        consideredCount: 1,
        notNumericCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const text = card().textContent;
    expect(text).toMatch(/Pale Yellow/);
    expect(text).toMatch(/Negative/);
  });

  it('draws NO chart for a listed reading', async () => {
    // One reading is not a trend. Nothing here may acquire a line by being
    // rendered beside things that have one.
    mountLab(
      labSeries({
        readings: [reading('TSH', [['2026-09-12', '1.81', 'uIU/mL']])],
        consideredCount: 1,
        singleReportCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const section = card();
    expect(section.querySelectorAll('svg')).toHaveLength(0);
    expect(section.querySelectorAll('.trend')).toHaveLength(0);
  });

  it('does NOT claim nothing could be followed when these are the only panels', async () => {
    // The card's empty state sat beside ten panels once the assessed features
    // were absent -- the page contradicting itself in two adjacent elements.
    mountLab(
      labSeries({
        series: [series('ZORBLEX', [['2026-01-01', 1], ['2026-02-01', 2]])],
        consideredCount: 1,
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(card().textContent).not.toMatch(/No parameters could be followed/);
  });

  it('renders no panels at all when there is nothing to show', async () => {
    mountLab(labSeries());
    await screen.findByText(/Trends over time/);
    expect(card().querySelectorAll('details')).toHaveLength(0);
  });

  it('survives the section being absent from an older payload', async () => {
    mount({ trends: { trends: { features: {} }, history: { included: 2 } } });
    await screen.findByText(/Trends over time/);
    expect(card().querySelectorAll('details')).toHaveLength(0);
  });
});
