import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Timeline from '../src/pages/Timeline';
import { api } from '../src/lib/api';


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

    expect(await screen.findByText('one report only')).toBeInTheDocument();
    expect(document.querySelector('.trend-chart__why').textContent).toMatch(
      /not the same as no change having occurred/
    );
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
    const pair = document.querySelector('.disclosure__pair');
    expect(pair.textContent).toBe('6.1 → 6.8 %');
    expect(pair.textContent.match(/%/g)).toHaveLength(1);
    expect(pair.textContent).not.toContain('6.4');
    expect(document.querySelectorAll('.trend-chart__point')).toHaveLength(3);
  });

  it('prints no pair for a feature with one reading and no change', async () => {
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

    await screen.findByText('one report only');
    expect(document.querySelectorAll('.disclosure__pair')).toHaveLength(0);
    expect(document.querySelector('.trend-chart__block > summary').textContent).not.toContain(
      '→'
    );
  });

  it('shows CLINICAL_DIRECTION_UNKNOWN as a refusal, not a direction', async () => {
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

    expect(await screen.findByText('no direction')).toBeInTheDocument();
    expect(
      screen.getByText(/No direction of benefit is declared/)
    ).toBeInTheDocument();
    expect(screen.queryByText('improving')).not.toBeInTheDocument();
  });

  it('says "fasting vs random" when the two samples were not comparable (2026-10-02)', async () => {
    mount({
      trends: {
        trends: {
          features: {
            blood_glucose: {
              feature: 'blood_glucose',
              outcome: 'NOT_COMPARABLE_SAMPLE_TIMING',
              trend: null,
              usable_point_count: 2,
              canonical_unit: 'mg/dl',
              points: [
                { date: '2026-09-11T00:00:00Z', value: 88, unit: 'mg/dl', sample_timing: 'fasting' },
                { date: '2026-09-13T00:00:00Z', value: 168, unit: 'mg/dl', sample_timing: 'random' },
              ],
              gaps: [],
              reason: 'Blood glucose readings were taken under different sample timings.',
            },
          },
          summary: { improving: 0, worsening: 0, stable: 0, not_determinable: 1 },
        },
      },
    });

    expect(await screen.findByText('fasting vs random')).toBeInTheDocument();
    expect(screen.queryByText('no direction')).not.toBeInTheDocument();
  });

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

    await screen.findByText('one report only');
    expect(document.querySelectorAll('.trend-chart__line')).toHaveLength(0);
    expect(document.querySelectorAll('.trend-chart__point')).toHaveLength(1);
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
              outcome: 'CHANGE_WITHIN_REFERENCE_INTERVAL',
              trend: null,
              usable_point_count: 2,
              canonical_unit: 'mg/dl',
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

    await screen.findByText(/Trends over time/);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(document.querySelectorAll('.trend-chart__line')).toHaveLength(0);
    expect(document.querySelectorAll('.trend-chart__block')).toHaveLength(0);
  });

  it('renders no chart for a feature with gaps but no reading at all', async () => {
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
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(document.querySelectorAll('.trend-chart__block')).toHaveLength(0);
  });

  it('shows the history accounting, including reports dropped by the cap', async () => {
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
    expect(screen.getAllByText(/06-lab-flagged\.pdf/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/02-diabetes\.pdf/).length).toBeGreaterThan(0);
  });


  it('labels an option with the date the reader gave for the report', async () => {
    const dated = {
      reports: [
        { reportId: A, chronoDate: '2026-09-13T00:00:00Z', reportDate: '2026-09-13T00:00:00Z', status: 'processed' },
        { reportId: B, chronoDate: '2026-09-11T04:26:10.910Z', reportDate: '2026-09-11T04:26:10.910Z', status: 'processed' },
      ],
    };
    mount({
      comparison: { ...comparisonFor(A, B), history: dated },
      reports: REPORTS,
    });
    await screen.findByText('Comparing two reports');

    const printed = new Date('2026-09-13T00:00:00Z').toLocaleDateString();
    const option = [...document.querySelectorAll('.pair-picker option')].find((o) =>
      o.textContent.includes('06-lab-flagged.pdf')
    );
    expect(option.textContent).toContain(printed);
    expect(option.textContent).not.toMatch(/uploaded/i);
  });

  it('says UPLOADED on an option whose report carried no date', async () => {
    const undated = {
      reports: [
        { reportId: A, chronoDate: '2026-09-19T04:22:13Z', reportDate: null, status: 'processed' },
        { reportId: B, chronoDate: '2026-09-11T04:26:10.910Z', reportDate: '2026-09-11T04:26:10.910Z', status: 'processed' },
      ],
    };
    mount({
      comparison: { ...comparisonFor(A, B), history: undated },
      reports: REPORTS,
    });
    await screen.findByText('Comparing two reports');

    const option = [...document.querySelectorAll('.pair-picker option')].find((o) =>
      o.textContent.includes('06-lab-flagged.pdf')
    );
    expect(option.textContent).toMatch(/uploaded/i);
    expect(option.textContent).toContain(
      new Date('2026-09-19T04:22:13Z').toLocaleDateString()
    );
  });

  it('marks an option whose typed date the document contradicts', async () => {
    const conflicting = {
      reports: [
        { reportId: A, chronoDate: '2026-09-09T00:00:00Z', reportDate: '2026-09-09T00:00:00Z', printedDate: '2026-09-05T00:00:00Z', printedDateStatus: 'read', status: 'processed' },
        { reportId: B, chronoDate: '2026-09-05T00:00:00Z', reportDate: null, printedDate: '2026-09-05T00:00:00Z', printedDateStatus: 'read', status: 'processed' },
      ],
    };
    mount({ comparison: { ...comparisonFor(A, B), history: conflicting }, reports: REPORTS });
    await screen.findByText('Comparing two reports');

    const utcDay = (iso) => new Date(iso).toLocaleDateString(undefined, { timeZone: 'UTC' });
    const optionFor = (name) =>
      [...document.querySelectorAll('.pair-picker option')].find((o) => o.textContent.includes(name));

    const typed = optionFor('06-lab-flagged.pdf').textContent;
    expect(typed).toContain(utcDay('2026-09-09T00:00:00Z'));
    expect(typed).toContain(`report prints ${utcDay('2026-09-05T00:00:00Z')}`);

    const printed = optionFor('01-all-normal.pdf').textContent;
    expect(printed).toContain(utcDay('2026-09-05T00:00:00Z'));
    expect(printed).not.toMatch(/uploaded|report prints/i);
  });

  it('shows the pair ACTUALLY on screen, not a guess', async () => {
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

  it('keeps the LATEST choice when an earlier answer arrives last', async () => {
    const withRow = (baseline, comparison, current, category) => {
      const response = comparisonFor(baseline, comparison);
      response.comparison.table = [{ feature: 'hba1c', previous: 8.4, current, unit: '%', category }];
      return response;
    };
    let releaseFirst;
    mount({ comparison: comparisonFor(A, B), trends: { trends: {}, history: HISTORY }, reports: REPORTS });
    await screen.findByText('Comparing two reports');
    api.getComparison.mockImplementation((pair) =>
      pair.comparison === C
        ? new Promise((resolve) => { releaseFirst = () => resolve(withRow(A, C, 1.1, 'improved')); })
        : Promise.resolve(withRow(A, B, 7.7, 'worsened'))
    );

    const select = () => document.querySelectorAll('.pair-picker select')[1];
    fireEvent.change(select(), { target: { value: C } });
    await waitFor(() => expect(api.getComparison).toHaveBeenCalledWith({ baseline: A, comparison: C }));
    fireEvent.change(select(), { target: { value: B } });
    await screen.findByText(/7\.7/);

    releaseFirst();
    await new Promise((r) => setTimeout(r, 20));

    expect(select().value).toBe(B);
    expect(screen.getByText(/7\.7/)).toBeInTheDocument();
    expect(screen.queryByText(/1\.1/)).not.toBeInTheDocument();
    expect(screen.queryByText('Comparing…')).not.toBeInTheDocument();
  });

  it('swaps rather than doing nothing when the two sides would collide', async () => {
    mount({ comparison: comparisonFor(A, B), reports: REPORTS });
    await screen.findByText('Comparing two reports');
    api.getComparison.mockClear();

    const [baseline] = document.querySelectorAll('.pair-picker select');
    fireEvent.change(baseline, { target: { value: B } });

    await waitFor(() => expect(api.getComparison).toHaveBeenCalledTimes(1));
    expect(api.getComparison).toHaveBeenCalledWith({ baseline: B, comparison: A });
  });

  it('does not end the out-of-order sentence with two full stops', async () => {
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
    vi.spyOn(api, 'listReports').mockRejectedValue(new Error('nope'));
    mount({ comparison: comparisonFor(A, B) });
    await screen.findByText('Comparing two reports');
    expect(document.querySelectorAll('.pair-picker select')).toHaveLength(2);
  });
});

describe('comparison -- the rest of the report', () => {
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

    expect(await screen.findByText('Zorblex')).toBeInTheDocument();
    expect(document.querySelectorAll('table.lab-table')).toHaveLength(1);
    const headings = [...document.querySelectorAll('table tbody th')].map((th) =>
      th.textContent.trim()
    );
    expect(headings).toContain('HbA1c');
    expect(headings.some((h) => h.startsWith('Zorblex'))).toBe(true);
  });

  it('counts every parameter on the card, both kinds', async () => {
    mountPair([labRow(), labRow({ key: 'frim', name: 'FRIMBULIN' })], [
      { feature: 'hba1c', description: 'HbA1c', unit: '%', previous: 5.4, current: 7, category: 'worsened' },
    ]);

    await screen.findByText('Zorblex');
    expect(screen.getByText(/3 parameters across these two reports/)).toBeInTheDocument();
  });

  it('shows BOTH units when the two reports disagree about them', async () => {
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

    await screen.findByText('Zorblex');
    expect(screen.getByText('101.9 U/L')).toBeInTheDocument();
    expect(screen.getByText('13 IU/L')).toBeInTheDocument();
    expect(
      screen.getByText(/different units, so the readings were not compared/)
    ).toBeInTheDocument();
  });


  it('still says different units when they really do differ', async () => {
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

    await screen.findByText('Zorblex');
    expect(screen.getByText(/in different units/)).toBeInTheDocument();
    expect(screen.queryByText(/did not print a unit/)).not.toBeInTheDocument();
  });

  it('renders a parameter on only one of the two reports as not measured', async () => {
    mountPair([labRow({ current: null, currentUnit: null, category: 'not_classifiable', symbol: null })]);

    await screen.findByText('Zorblex');
    expect(screen.getByText('12.1 mg/L')).toBeInTheDocument();
    expect(screen.getByText('This parameter was not on that report.')).toBeInTheDocument();
    expect(screen.queryByText('0 mg/L')).not.toBeInTheDocument();
  });

  it('shows a non-numeric result as the text the laboratory printed', async () => {
    mountPair([
      labRow({
        previous: null,
        current: null,
        previousRaw: 'Negative',
        currentRaw: 'Negative',
        previousUnit: null,
        currentUnit: null,
        unit: null,
        category: 'not_classifiable',
        symbol: null,
      }),
    ]);

    await screen.findByText('Zorblex');
    expect(screen.getAllByText('Negative').length).toBeGreaterThan(0);
  });

  it("uses Module 29's own category words for these rows too", async () => {
    mountPair([labRow({ category: 'worsened', symbol: '↑' })]);

    await screen.findByText('Zorblex');
    expect(screen.getByText(/worsened/)).toBeInTheDocument();
    expect(screen.queryByText(/worsening/)).not.toBeInTheDocument();
  });

  it('names the spellings it treated as one test', async () => {
    mountPair([labRow({ name: 'NEUTROPHILS', joinedFrom: ['Polymorphs', 'NEUTROPHILS'] })]);

    await screen.findByText(/Neutrophils/);
    const heading = [...document.querySelectorAll('table tbody th')].find((th) =>
      th.textContent.includes('Neutrophils')
    );
    expect(heading.textContent).toContain('2 names');
    expect(heading.querySelector('[title]').getAttribute('title')).toContain('Polymorphs');
  });

  it('never prints "unchanged" beside an arrow and two different numbers', async () => {
    mountPair([
      labRow({ name: 'EOSINOPHILS', previous: 5, current: 2, unit: '%', previousUnit: '%', currentUnit: '%', category: 'unchanged', symbol: '↓' }),
    ]);

    await screen.findByText('Eosinophils');
    expect(screen.getByText('↓ went down · within normal variation')).toBeInTheDocument();
    expect(screen.queryByText(/unchanged/)).not.toBeInTheDocument();
    expect(screen.queryByText(/no real change/)).not.toBeInTheDocument();
  });

  it('says which way the number moved and whether it counts, in words (2026-10-04)', async () => {
    mountPair([
      labRow({ name: 'GLUCOSE', previous: 168, current: 110, unit: 'mg/dl', previousUnit: 'mg/dl', currentUnit: 'mg/dl', category: 'improved', symbol: '↓' }),
      labRow({ key: 'esr', name: 'ESR', previous: 30, current: 32, unit: 'mm/hr', previousUnit: 'mm/hr', currentUnit: 'mm/hr', category: 'unchanged', symbol: '↑' }),
    ]);

    await screen.findByText('Glucose');
    expect(screen.getByText('↓ went down · improved')).toBeInTheDocument();
    expect(screen.getByText('↑ went up · within normal variation')).toBeInTheDocument();
    expect(
      screen.getByText(/the arrow shows which way the number moved; the\s+words after the dot say whether that move counts/)
    ).toBeInTheDocument();
  });

  it('leaves age, sex and smoking out of the table (2026-10-02)', async () => {
    mountPair([labRow()], [
      { feature: 'hba1c', description: 'HbA1c', unit: '%', previous: 5.4, current: 7, category: 'worsened' },
      { feature: 'age', description: 'Age in whole years', unit: 'years', previous: 34, current: 20, category: 'not_classifiable' },
      { feature: 'gender', description: 'Self-described gender', unit: null, previous: null, current: null, category: 'not_classifiable' },
      { feature: 'smoking_history', description: 'Smoking history', unit: null, previous: null, current: null, category: 'not_classifiable' },
    ]);

    await screen.findByText('Zorblex');
    const headings = [...document.querySelectorAll('table tbody th')].map((th) => th.textContent);
    expect(headings.some((h) => /Age in whole years|gender|Smoking/.test(h))).toBe(false);
    expect(screen.getByText(/2 parameters across these two reports/)).toBeInTheDocument();
  });

  it("uses the same words for Module 29's own rows", async () => {
    mountPair([], [
      { feature: 'bmi', description: 'Body mass index', unit: 'kg/m2', previous: 25.25, current: 25.25, category: 'unchanged', symbol: '→' },
    ]);

    await screen.findByText('Body mass index');
    expect(screen.getByText('→ no change')).toBeInTheDocument();
    expect(screen.queryByText(/unchanged|within normal variation/)).not.toBeInTheDocument();
  });

  it('never prints "changed direction only", which reads as its opposite', async () => {
    mountPair([], [
      { feature: 'hemoglobin', description: 'Haemoglobin concentration', unit: 'g/dl', previous: 9.2, current: 13.6, category: 'changed_direction_only', symbol: '↑' },
    ]);

    await screen.findByText('Haemoglobin concentration');
    expect(
      screen.getByText('↑ went up · real change, not rated better or worse')
    ).toBeInTheDocument();
    expect(screen.queryByText(/direction only/)).not.toBeInTheDocument();
    expect(screen.queryByText(/within normal variation/)).not.toBeInTheDocument();
  });

  it('uses the same words for a laboratory row that moved with no polarity', async () => {
    mountPair([
      labRow({ name: 'ESR', previous: 35, current: 45, unit: 'mm/hr', previousUnit: 'mm/hr', currentUnit: 'mm/hr', category: 'changed_direction_only', symbol: '↑' }),
    ]);

    await screen.findByText('ESR');
    expect(screen.getByText(/real change, not rated better or worse/)).toBeInTheDocument();
    expect(screen.queryByText(/direction only/)).not.toBeInTheDocument();
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
    expect(screen.getByText('70')).toBeInTheDocument();
  });
});

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
    mount({ progress: { progress: progress() } });

    expect(
      await screen.findByText(/not a health score, not a risk score and not a diagnosis/)
    ).toBeInTheDocument();
  });

  it('KEEPS the coverage line, without a total that disagrees with the page', async () => {
    mount({ progress: { progress: progress() } });

    const said = await screen.findByText(/Worked out from 8 results/);
    expect(said.textContent).toMatch(/could be judged/);
    expect(said.textContent).toMatch(/Everything else above is not in the number/);
    expect(said.textContent).not.toMatch(/of your 12/);
    expect(said.textContent).not.toMatch(/\(s\)/);
  });

  it('uses the singular for exactly one contributing result', async () => {
    mount({ progress: { progress: progress({
        coverage: {
          contributing_count: 1,
          features_examined: 9,
          excluded_count: 8,
          minimum_required: 1,
        },
      }) } });

    const said = await screen.findByText(/Worked out from 1 result:/);
    expect(said.textContent).not.toMatch(/1 results/);
  });

  it('mentions the minimum only when it is the reason there is no score', async () => {
    mount({ progress: { progress: progress() } });
    await screen.findByText(/Worked out from 8 results/);
    expect(screen.queryByText(/At least 3 are needed/)).not.toBeInTheDocument();
  });

  it('places the score on the scale, and never in a risk colour', async () => {
    mount({ progress: { progress: progress() } });

    await screen.findByText(/Progress score/);
    const mark = document.querySelector('.scorescale__mark');
    expect(mark).not.toBeNull();
    expect(mark.getAttribute('fill')).toBe('var(--brand)');
    expect(Number(mark.getAttribute('cx'))).toBeCloseTo(160, 0);
  });

  it('draws no scale marker for a score outside the declared 0-100', async () => {
    mount({ progress: { progress: progress({ score: 140 }) } });
    await screen.findByText(/Progress score/);
    expect(document.querySelector('.scorescale')).toBeNull();
  });

  it('does not repeat a warning the comparison card already showed', async () => {
    const shared = 'This comparison uses two of your reports.';
    mount({
      comparison: { comparison: { warnings: [shared], parameters: {} } },
      progress: { progress: progress({ warnings: [shared, 'A change has to be big enough to count at all.'] }) } });

    await screen.findByText(/Progress score/);
    const hits = screen.getAllByText(new RegExp(shared.replace(/\./g, '\\.')));
    expect(hits).toHaveLength(1);
  });

  it('still shows a warning that ONLY the progress payload carries', async () => {
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

describe('the trends card names parameters for a reader', () => {
  const trends = (features) => ({
    trends: { features },
    history: { included: 3, considered: 3 },
  });

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
    expect(document.body.textContent).not.toMatch(/\b[a-z]+_[a-z0-9_]+\b/);
  });

  it('falls back to the key rather than printing nothing', async () => {
    mount({ trends: trends({ some_new_marker: row('some_new_marker') }) });

    await screen.findByText(/Trends over time/);
    expect(titles()).toContain('some_new_marker');
  });

  it('counts the panels it actually renders, and the parts add up', async () => {
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

    expect(line).toMatch(/^3 parameters/);
    expect(line).toContain('0 improving');
    expect(line).toContain('1 worsening');
    expect(line).toContain('1 stable');
    expect(line).toContain('1 with no direction stated');
    expect(line).not.toContain('9');
  });

  it('does NOT repeat every chart in a table beneath it', async () => {
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
    expect(document.querySelectorAll('table.lab-table')).toHaveLength(0);
  });
});

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
      movementFrom: paired ? numeric[0] : null,
      movementTo: paired ? numeric[numeric.length - 1] : null,
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

  const card = () => screen.getByText(/Trends over time/).closest('section');

  it('appears in the SAME card as the assessed parameters', async () => {
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
    expect(pair.textContent.match(/mg\/L/g)).toHaveLength(1);
    expect(pair.className).not.toMatch(/improving|worsening|trend--/);
  });

  it('prints NO pair for a blocked series, only its numbers on opening', async () => {
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


  it('states the threshold on the panel, without the provenance clause', async () => {
    mountLab(
      labSeries({
        series: [
          series('Frimbulin', [['2026-01-01', 35], ['2026-02-01', 45]], null, 'mm/hr', {
            trend: 'stable',
            classified: true,
            significantChangePct: 62,
            trendSource: 'table',
            trendVerified: false,
          }),
        ],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const panel = document.querySelector('.trend-chart__threshold');
    expect(panel.textContent).toMatch(/Counted as a change only past 62%/);
    expect(panel.textContent).not.toMatch(/variation table/);
    expect(panel.textContent).not.toMatch(/checked against/);
  });

  it('says once, on the card, that the thresholds are unchecked', async () => {
    mountLab(
      labSeries({
        series: [
          series('Frimbulin', [['2026-01-01', 35], ['2026-02-01', 45]], null, 'mm/hr', {
            trend: 'stable',
            classified: true,
            significantChangePct: 62,
            trendSource: 'table',
            trendVerified: false,
          }),
        ],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(card().textContent).toMatch(
      /change thresholds used here have not been checked against a published source/i
    );
  });

  it('says it ONCE even with many panels -- the whole point of the change', async () => {
    mountLab(
      labSeries({
        series: [1, 2, 3, 4, 5].map((n) =>
          series(`Frimbulin ${n}`, [['2026-01-01', 35], ['2026-02-01', 45]], null, 'mm/hr', {
            trend: 'stable',
            classified: true,
            significantChangePct: 62,
            trendSource: 'table',
            trendVerified: false,
          })
        ),
        plottedCount: 5,
      })
    );

    await screen.findByText(/Trends over time/);
    const hits = card().textContent.match(/have not been checked against a published source/g);
    expect(hits).toHaveLength(1);
    expect(document.querySelectorAll('.trend-chart__threshold')).toHaveLength(5);

    document
      .querySelectorAll('.trend-chart__threshold, .trend-chart__joined')
      .forEach((el) => {
        expect(el.textContent).not.toMatch(/checked|variation table|reviewable source/i);
      });
  });

  it('says nothing at all when every figure has been reviewed', async () => {
    mountLab(
      labSeries({
        series: [
          series('Frimbulin', [['2026-01-01', 35], ['2026-02-01', 45]], null, 'mm/hr', {
            trend: 'stable',
            classified: true,
            significantChangePct: 62,
            trendSource: 'table',
            trendVerified: true,
          }),
        ],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(card().textContent).not.toMatch(/have not been checked/);
  });

  it('keeps the stronger wording when a model invented the figure', async () => {
    mountLab(
      labSeries({
        series: [
          series('Frimbulin', [['2026-01-01', 35], ['2026-02-01', 45]], null, 'mm/hr', {
            trend: 'stable',
            classified: true,
            significantChangePct: 62,
          }),
        ],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(card().textContent).toMatch(
      /produced by a language model from the test name alone/i
    );
  });

  it('names the unit equivalences too, and only when unverified', async () => {
    mountLab(
      labSeries({
        series: [
          series('Frimbulin', [['2026-01-01', 30.8], ['2026-02-01', 33]], null, '%', {
            unitEquivalence: { label: 'grams per decilitre', verified: false },
          }),
        ],
        plottedCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(card().textContent).toMatch(/both meaning grams per decilitre/);
    expect(card().textContent).toMatch(/unit equivalences used here have not been checked/i);
    const panel = document.querySelector('.trend-chart__joined');
    expect(panel.textContent).not.toMatch(/checked against/);
  });

  it('names the printed spellings it treated as one test', async () => {
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
    mountLab(
      labSeries({
        readings: [reading('ZORBLEX FACTOR(ZBX)', [['2026-01-01', '82', '%']])],
        singleReportCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    expect(document.querySelectorAll('.disclosure__pair')).toHaveLength(0);
  });

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
    expect(chip.getAttribute('title')).toMatch(/laboratory/i);
  });

  it('does NOT colour the movement word like a trend', async () => {
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
    expect(section.textContent).toMatch(/Frimbulator/);
    expect(section.querySelector('.trend-chart__nodirection')?.textContent).toBe('units differ');
    expect(section.textContent).toMatch(/101\.9/);
    expect(section.textContent).toMatch(/13/);
    expect(section.querySelectorAll('svg')).toHaveLength(0);
  });

  it('a single reading says "one report only", not its flag', async () => {
    mountLab(
      labSeries({
        readings: [{ ...reading('C-REACTIVE PROTEIN(CRP)', [['2026-09-13', '38.9', 'mg/L']]), latestFlag: 'high' }],
        consideredCount: 1,
        singleReportCount: 1,
      })
    );

    await screen.findByText(/Trends over time/);
    const panel = card().querySelector('details.trend-chart__block');
    const row = panel.querySelector('summary');
    expect(row.querySelector('.trend-chart__nodirection').textContent).toBe('one report only');
    expect(row.textContent).not.toMatch(/High|In range/);
    expect(row.querySelector('.lab-status__flag')).toBeNull();
    expect(row.textContent).toMatch(/C-reactive protein \(CRP\)/);
  });

  it('keeps the printed-range position inside the panel, naming no agent', async () => {
    mountLab(
      labSeries({
        readings: [
          { ...reading('ESR', [['2026-09-13', '45', 'mm/hr']]), latestFlag: 'high' },
          { ...reading('SGPT', [['2026-09-13', '13', 'IU/L']]), latestFlag: 'normal' },
          { ...reading('AVERAGE BLOOD GLUCOSE', [['2026-09-13', '154', 'mg/dL']]), latestFlag: null },
        ],
        consideredCount: 3,
        singleReportCount: 3,
      })
    );

    await screen.findByText(/Trends over time/);
    const bodies = [...card().querySelectorAll('details.trend-chart__block')].map((d) => d.textContent);
    expect(bodies[0]).toMatch(/Above the range printed on the report\./);
    expect(bodies[1]).toMatch(/Within the range printed on the report\./);
    expect(bodies[2]).not.toMatch(/range printed on the report/);
    for (const text of bodies) expect(text).not.toMatch(/laboratory's own/i);
  });

  it("a charted panel's flag tooltip names the range, not who marked it", async () => {
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
    const title = card().querySelector('.lab-status__flag').getAttribute('title');
    expect(title).toBe('The latest reading against the range printed on that laboratory report');
    expect(title).not.toMatch(/own marking/i);
  });

  it('never prints the reference range itself, or draws a band for it', async () => {
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
