import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import TrendChart from '../src/components/TrendChart';

/**
 * The trend chart, tested on the four things it has to keep apart:
 * a real change, fewer than two readings, a gap, and a rejected reading.
 *
 * A FLAT LINE AND "WE HAVE NO DATA" LOOK IDENTICAL IF YOU LET THEM, so almost
 * every assertion here is about ink that must NOT be on the screen. Each one
 * has been mutation-tested: flip the guard it names and this test dies.
 */

const D1 = '2026-01-10T00:00:00Z';
const D2 = '2026-04-10T00:00:00Z';
const D3 = '2026-08-10T00:00:00Z';

function paths(container) {
  return container.querySelectorAll('.trend-chart__line');
}
function markers(container) {
  return container.querySelectorAll('.trend-chart__point');
}
function gapMarkers(container) {
  return container.querySelectorAll('.trend-chart__gap');
}

describe('a real change', () => {
  const classified = {
    label: 'hba1c',
    unit: '%',
    points: [
      { date: D1, value: 6.1, unit: '%' },
      { date: D2, value: 6.4, unit: '%' },
      { date: D3, value: 6.8, unit: '%' },
    ],
    classified: true,
    trend: 'worsening',
  };

  it('draws one unbroken line through three readings', () => {
    const { container } = render(<TrendChart {...classified} />);
    expect(paths(container)).toHaveLength(1);
    expect(markers(container)).toHaveLength(3);
  });

  it('states the movement in words, with both dates and both values', () => {
    render(<TrendChart {...classified} />);
    const title = screen.getByRole('img').getAttribute('aria-label');
    expect(title).toMatch(/worsening/);
    expect(title).toMatch(/6\.1 %/);
    expect(title).toMatch(/6\.8 %/);
    expect(title).toMatch(/across 3 readings/);
  });

  it('gives every dot its own tooltip, not the whole chart summary', () => {
    // READ OFF A REAL THREE-POINT CHART. With only the SVG-level <title>,
    // pointing at any dot showed "8.4 % on 7 Sept to 5.2 % on 11 Sept" -- so
    // the MIDDLE reading, which the axis does not label either (two dates,
    // not a ruler), could not be read off the chart at all.
    const { container } = render(<TrendChart {...classified} />);
    const titles = [...container.querySelectorAll('.trend-chart__point title')]
      .map((t) => t.textContent);
    expect(titles).toHaveLength(3);
    expect(titles[1]).toMatch(/^6\.4 %/);
    expect(titles[1]).toMatch(/10 Apr 2026/);
  });

  it('names every reading in its summary while the list stays readable', () => {
    // The middle value was absent from the one sentence describing the
    // series, so a screen reader user got the two ends and a count.
    render(<TrendChart {...classified} />);
    const label = screen.getByRole('img').getAttribute('aria-label');
    expect(label).toMatch(/6\.1 %/);
    expect(label).toMatch(/6\.4 %/);
    expect(label).toMatch(/6\.8 %/);
  });

  it('falls back to the two ends when the series is long', () => {
    // A sentence naming fourteen dates is not a summary; the per-point
    // tooltips carry the detail there.
    const many = Array.from({ length: 9 }, (_, i) => ({
      date: `2026-0${i + 1}-10T00:00:00Z`,
      value: 6 + i * 0.1,
      unit: '%',
    }));
    render(<TrendChart {...classified} points={many} />);
    const label = screen.getByRole('img').getAttribute('aria-label');
    expect(label).toMatch(/across 9 readings/);
    // The fourth reading is not spelled out.
    expect(label).not.toMatch(/6\.3 %/);
  });

  it('prints the scale it drew the slope against', () => {
    const { container } = render(<TrendChart {...classified} />);
    // Both axis ends, or the slope can be made to say anything by padding.
    expect(container.querySelectorAll('.trend-chart__axis').length).toBeGreaterThanOrEqual(4);
  });

  it('reserves a gutter wide enough for its own axis labels', () => {
    // FOUND BY LOOKING AT THE RENDERED CHART, not by reading it: at a
    // `0 0 560 196` viewBox, "186 mg/dl" -- right-anchored 8 units left of the
    // plot -- ran off the left edge and rendered as "16 mg/dl". A clipped
    // label on a chart does not look broken, it looks like a smaller number.
    const { container } = render(
      <TrendChart
        label="Blood sugar"
        unit="mg/dl"
        points={[
          { date: D1, value: 186, unit: 'mg/dl' },
          { date: D3, value: 88, unit: 'mg/dl' },
        ]}
        classified={false}
      />
    );
    const [minX] = container.querySelector('svg').getAttribute('viewBox').split(' ').map(Number);
    const anchor = Number(container.querySelector('.trend-chart__axis').getAttribute('x'));
    // Room for the longest label this chart can produce, at ~6 units a glyph.
    expect(anchor - minX).toBeGreaterThanOrEqual(66);
  });

  it('takes a risk colour ONLY from a classified direction', () => {
    const { container } = render(<TrendChart {...classified} />);
    expect(paths(container)[0].getAttribute('stroke')).toBe('var(--rust)');
  });

  it('refuses a risk colour when no direction was classified', () => {
    // Two real readings, no classification: the readings are real, the
    // direction is not, and colour in this palette is categorical.
    const { container } = render(
      <TrendChart {...classified} classified={false} trend={null} />
    );
    expect(paths(container)).toHaveLength(1);
    expect(paths(container)[0].getAttribute('stroke')).toBe('var(--ink)');
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(
      /No direction was classified/
    );
  });

  it('refuses a trend word that arrives WITHOUT the classification', () => {
    // The contradictory shape: `classified: false` carrying a direction
    // anyway. Module 28's own model validator forbids it; if it ever arrives,
    // the unclassified reading wins. `classified={false} trend={null}` cannot
    // test this clause -- with a null trend the colour branch is false either
    // way, which is one condition tested and two conditions written.
    const { container } = render(
      <TrendChart {...classified} classified={false} trend="worsening" />
    );
    expect(paths(container)[0].getAttribute('stroke')).toBe('var(--ink)');
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(
      /No direction was classified/
    );
  });

  it('never prints a trend word it does not recognise, or a null one', () => {
    // `classified: true` with `trend: null` printed the string "null" as the
    // direction before the two halves were checked together.
    render(<TrendChart {...classified} classified trend={null} />);
    const title = screen.getByRole('img').getAttribute('aria-label');
    expect(title).not.toMatch(/null|undefined/);
    expect(title).toMatch(/No direction was classified/);
  });

  it('gives "stable" no risk colour, because it did not earn one', () => {
    const { container } = render(
      <TrendChart {...classified} trend="stable" />
    );
    expect(paths(container)[0].getAttribute('stroke')).toBe('var(--ink)');
  });
});

describe('a genuinely flat line', () => {
  it('prints its one reading once, not twice and not never', () => {
    // Two identical readings: a flat line that EARNED it, `stable` from the
    // service. High and low are the same number, so a naive pair of labels
    // either stacks it on itself or -- with a not-equal guard -- prints no
    // scale at all beside a flat line, which is the one shape most easily
    // mistaken for an empty chart.
    const { container } = render(
      <TrendChart
        label="BMI"
        unit="kg/m2"
        points={[
          { date: D1, value: 26.42, unit: 'kg/m2' },
          { date: D3, value: 26.42, unit: 'kg/m2' },
        ]}
        classified
        trend="stable"
      />
    );
    const labels = [...container.querySelectorAll('.trend-chart__axis')]
      .map((n) => n.textContent)
      .filter((t) => t.includes('26.42'));
    expect(labels).toHaveLength(1);
    expect(paths(container)).toHaveLength(1);
  });
});

describe('fewer than two readings', () => {
  const single = {
    label: 'hba1c',
    unit: '%',
    points: [{ date: D1, value: 6.1, unit: '%' }],
    classified: false,
    trend: null,
  };

  it('draws NO LINE AT ALL for one reading', () => {
    const { container } = render(<TrendChart {...single} />);
    expect(paths(container)).toHaveLength(0);
    // The reading itself is still shown -- hiding it is the same failure from
    // the other side.
    expect(markers(container)).toHaveLength(1);
  });

  it('says a change needs two readings, and never says "stable"', () => {
    const { container } = render(<TrendChart {...single} />);
    expect(
      screen.getByText(/no line is drawn, because a change needs two/i)
    ).toBeInTheDocument();
    // Said both on the page and in the SVG's own words, hence getAllByText.
    expect(
      screen.getAllByText(/not the same as no change having occurred/i).length
    ).toBeGreaterThan(0);
    expect(container.textContent.toLowerCase()).not.toContain('stable');
  });

  it('says in words that one reading is not a change', () => {
    render(<TrendChart {...single} />);
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(
      /one reading only/i
    );
  });

  it('prints NO y scale around a single reading', () => {
    // The domain there is a 10% nudge either side of the only value. Printing
    // 5.34 and 6.86 around a lone 6.1 offers a scale nobody chose and nothing
    // was compared against.
    const { container } = render(<TrendChart {...single} />);
    const axisText = [...container.querySelectorAll('.trend-chart__axis')]
      .map((node) => node.textContent)
      .join(' ');
    expect(axisText).not.toMatch(/6\.86|5\.34/);
    // The date it was taken on is still shown: that is a fact, not a scale.
    expect(axisText).toMatch(/10 Jan 2026/);
  });

  it('prints the scale when a declared band gives it a meaning', () => {
    const { container } = render(<TrendChart {...single} band={{ low: 4, high: 5.6 }} />);
    const axisText = [...container.querySelectorAll('.trend-chart__axis')]
      .map((node) => node.textContent)
      .join(' ');
    expect(axisText).toMatch(/\d/);
    expect(container.querySelector('.trend-chart__band')).not.toBeNull();
  });
});

describe('a gap where a reading was expected', () => {
  const withGap = {
    label: 'hba1c',
    unit: '%',
    points: [
      { date: D1, value: 6.1, unit: '%' },
      { date: D3, value: 6.8, unit: '%' },
    ],
    gaps: [
      {
        date: D2,
        kind: 'not_reported',
        reason: 'This report did not carry a value for hba1c.',
      },
    ],
    classified: true,
    trend: 'worsening',
  };

  it('BREAKS the line across the gap instead of drawing through it', () => {
    const { container } = render(<TrendChart {...withGap} />);
    // Two readings with a gap between them are two runs of one point each,
    // and a run of one point is not a line. Drawing straight through would
    // assert the value moved smoothly through a period nobody measured.
    expect(paths(container)).toHaveLength(0);
    expect(markers(container)).toHaveLength(2);
  });

  it('keeps the line where the evidence is continuous', () => {
    const { container } = render(
      <TrendChart
        {...withGap}
        points={[
          { date: D1, value: 6.1, unit: '%' },
          { date: D2, value: 6.3, unit: '%' },
          { date: D3, value: 6.8, unit: '%' },
        ]}
        gaps={[{ date: '2026-09-10T00:00:00Z', kind: 'not_reported', reason: 'x' }]}
      />
    );
    expect(paths(container)).toHaveLength(1);
  });

  it('draws the gap as a dashed, unfilled marker outside the plot', () => {
    const { container } = render(<TrendChart {...withGap} />);
    const gap = gapMarkers(container)[0];
    expect(gap.getAttribute('fill')).toBe('none');
    expect(gap.getAttribute('stroke')).toBe('var(--mono)');
    expect(gap.getAttribute('stroke-dasharray')).toBe('2 2');
    // Below the axis: an absence has no y position, and inside the plot it
    // would have acquired one.
    expect(Number(gap.getAttribute('cy'))).toBeGreaterThan(134);
  });

  it('never lets a gap reach the plotted markers or the reading count', () => {
    const { container } = render(<TrendChart {...withGap} />);
    expect(markers(container)).toHaveLength(2);
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(
      /1 report carried no usable reading/
    );
  });

  it('gives the gap marker its own tooltip too', () => {
    // Same reason as the readings: the lane sits below the axis with no date
    // label of its own, so pointing at it has to say which report it is.
    const { container } = render(<TrendChart {...withGap} />);
    const title = container.querySelector('.trend-chart__gap title');
    expect(title).not.toBeNull();
    expect(title.textContent).toMatch(/No reading/);
    expect(title.textContent).toMatch(/10 Apr 2026/);
    expect(title.textContent).toMatch(/did not carry a value for hba1c/);
  });

  it('gives the reason a report carried nothing', () => {
    render(<TrendChart {...withGap} />);
    expect(screen.getByText('No reading')).toBeInTheDocument();
    // Twice on purpose now: once in the marker's own tooltip, once in the
    // list below, so pointing at the gap and reading the page both work.
    expect(
      screen.getAllByText(/did not carry a value for hba1c/).length
    ).toBeGreaterThanOrEqual(2);
  });
});

describe('a rejected reading', () => {
  const rejected = {
    label: 'creatinine',
    unit: 'mg/dL',
    points: [
      { date: D1, value: 1.0, unit: 'mg/dL' },
      { date: D3, value: 1.1, unit: 'mg/dL' },
    ],
    gaps: [
      {
        date: D2,
        kind: 'rejected',
        reason: 'A value of 999 is not physiologically plausible.',
      },
    ],
    classified: true,
    trend: 'stable',
  };

  it('never plots it, and says why it was refused', () => {
    const { container } = render(<TrendChart {...rejected} />);
    // A rejected 999 is not a high result; it is not a result. If it reached
    // the domain the axis maximum would be 999 and both real readings would
    // flatten onto the floor.
    expect(markers(container)).toHaveLength(2);
    expect(gapMarkers(container)).toHaveLength(1);
    expect(screen.getByText('Not usable')).toBeInTheDocument();
    expect(
      screen.getAllByText(/not physiologically plausible/).length
    ).toBeGreaterThanOrEqual(1);
    // The refused number appears ONLY inside the service's reason sentence.
    // It must never have reached the scale: an axis topping out at 999 would
    // flatten both real readings onto the floor of the chart.
    const axisText = [...container.querySelectorAll('.trend-chart__axis')]
      .map((node) => node.textContent)
      .join(' ');
    expect(axisText).not.toContain('999');
    // And it breaks the line like any other gap: a refused reading is a
    // report that contributed nothing, not a reading of some other value.
    expect(paths(container)).toHaveLength(0);
  });

  it('calls a reading that could not be used "not usable", not "no reading"', () => {
    render(<TrendChart {...rejected} gaps={[{ date: D2, kind: 'unusable', reason: 'r' }]} />);
    // "No reading" would claim the report was silent. It was not.
    expect(screen.getByText('Not usable')).toBeInTheDocument();
    expect(screen.queryByText('No reading')).not.toBeInTheDocument();
  });

  it('claims neither for an availability code it does not recognise', () => {
    render(<TrendChart {...rejected} gaps={[{ date: D2, kind: 'something_new', reason: 'r' }]} />);
    expect(screen.getByText('No usable reading')).toBeInTheDocument();
    expect(screen.queryByText('No reading')).not.toBeInTheDocument();
    expect(screen.queryByText('Not usable')).not.toBeInTheDocument();
  });
});

describe('the reference band', () => {
  const base = {
    label: 'bmi',
    points: [
      { date: D1, value: 26 },
      { date: D3, value: 27 },
    ],
    classified: true,
    trend: 'worsening',
  };

  it('is drawn when the service declared both ends', () => {
    const { container } = render(<TrendChart {...base} band={{ low: 18.5, high: 24.9 }} />);
    expect(container.querySelector('.trend-chart__band')).not.toBeNull();
  });

  it('is NOT drawn from a one-sided optimum', () => {
    // A floor with no declared ceiling drawn as a band runs to the edge of the
    // frame and asserts a ceiling nobody declared.
    const { container } = render(<TrendChart {...base} band={{ low: 200, high: null }} />);
    expect(container.querySelector('.trend-chart__band')).toBeNull();
  });
});

describe('readings in two different units', () => {
  const mixed = {
    label: 'glucose',
    points: [
      { date: D1, value: 100, unit: 'mg/dL' },
      { date: D3, value: 7.2, unit: 'mmol/L' },
    ],
    classified: false,
    trend: null,
  };

  it('are never placed on one axis at all', () => {
    const { container } = render(<TrendChart {...mixed} />);
    expect(paths(container)).toHaveLength(0);
    // Not even as two dots. A shared y scale makes the comparison whether or
    // not a line joins them: 7.2 mmol/L would sit at the floor and 100 mg/dL
    // at the ceiling, and that is the same measurement twice.
    expect(markers(container)).toHaveLength(0);
    expect(container.querySelector('svg')).toBeNull();
  });

  it('say so, rather than leaving two unexplained dots', () => {
    render(<TrendChart {...mixed} />);
    expect(screen.getByText(/more than one unit/i)).toBeInTheDocument();
    expect(screen.getByText(/mg\/dL, mmol\/L/)).toBeInTheDocument();
  });
});

describe('nothing at all', () => {
  it('renders no empty frame when there is neither a reading nor a gap', () => {
    const { container } = render(
      <TrendChart label="hba1c" points={[]} gaps={[]} classified={false} />
    );
    expect(container.querySelector('svg')).toBeNull();
    // Not an empty figure either: a frame with nothing in it is not a chart,
    // and the table beside it already carries the service's own refusal.
    expect(container.querySelector('.trend-chart')).toBeNull();
  });

  it('counts a reading it could not place rather than dropping it', () => {
    render(
      <TrendChart
        label="hba1c"
        points={[
          { date: D1, value: 6.1 },
          { date: null, value: 6.5 },
        ]}
        classified={false}
      />
    );
    expect(screen.getByText(/1 further reading\(s\) could not be placed/)).toBeInTheDocument();
  });
});

/**
 * THE AXIS IS THE SCALE A CHANGE IS JUDGED AGAINST.
 *
 * Found by a reader looking at their cholesterol chart: 186 -> 172 drawn from
 * ceiling to floor, labelled "stable". Both were true. The service reports
 * -7.53 % against a 17 % stability band, so "stable" is correct -- and an axis
 * spanning only the two readings stretches any change, however small, across
 * the whole box. The picture said collapse, the label said stable, and the
 * picture is what a reader believes.
 */
describe('TrendChart -- the significance span sets the scale', () => {
  const STABILITY = { significant_change_pct: 17, min_absolute_change: 5 };
  const POINTS = [
    { date: '2026-09-09', value: 186, unit: 'mg/dl' },
    { date: '2026-09-11', value: 172, unit: 'mg/dl' },
  ];

  /** Vertical distance between the two plotted readings, in svg units. */
  const dropHeight = () => {
    const dots = [...document.querySelectorAll('circle')].filter(
      (c) => c.getAttribute('r') && !c.getAttribute('stroke-dasharray')
    );
    const ys = dots.map((c) => Number(c.getAttribute('cy'))).filter(Number.isFinite);
    return ys.length >= 2 ? Math.abs(Math.max(...ys) - Math.min(...ys)) : null;
  };

  it('draws a within-band change as a SHALLOW line, not a cliff', () => {
    const { unmount } = render(
      <TrendChart label="Total cholesterol" unit="mg/dl" points={POINTS} />
    );
    const withoutBand = dropHeight();
    unmount();

    render(
      <TrendChart
        label="Total cholesterol"
        unit="mg/dl"
        points={POINTS}
        stability={STABILITY}
        baseline={186}
      />
    );
    const withBand = dropHeight();

    expect(withoutBand).toBeGreaterThan(0);
    expect(withBand).toBeGreaterThan(0);
    // THE WHOLE POINT: the same two readings, drawn against what would have
    // counted, occupy a fraction of the height they did before.
    expect(withBand).toBeLessThan(withoutBand / 2);
  });

  it('still prints the readings themselves, never the scale', () => {
    // Every number on this chart is a reading somebody took. Widening the
    // domain must not start labelling the axis with the band's edges.
    render(
      <TrendChart
        label="Total cholesterol"
        unit="mg/dl"
        points={POINTS}
        stability={STABILITY}
        baseline={186}
      />
    );
    const text = document.body.textContent;
    expect(text).toMatch(/186/);
    expect(text).toMatch(/172/);
    // 186 +/- 17 % is about 154 and 218. Neither is a reading and neither may
    // appear.
    expect(text).not.toMatch(/154/);
    expect(text).not.toMatch(/218/);
  });

  it('is unchanged when the service declared no stability band', () => {
    const { unmount } = render(
      <TrendChart label="Total cholesterol" unit="mg/dl" points={POINTS} />
    );
    const plain = dropHeight();
    unmount();

    render(
      <TrendChart label="Total cholesterol" unit="mg/dl" points={POINTS} stability={null} />
    );
    expect(dropHeight()).toBe(plain);
  });
});

/**
 * THE SAME FIX FOR THE CHARTS THAT HAVE NO BAND.
 *
 * The parameters this platform does not assess have no polarity and no
 * stability figure, so neither `band` nor `stability` exists for them and
 * their axes still spanned the readings alone. What they DO have is the
 * interval their own laboratory printed beside the value, and `scaleOnly`
 * carries it in.
 *
 * It SETS THE SCALE AND IS NEVER DRAWN, for two independent reasons: the
 * reader's reports disagree about the range on most parameters, so there is
 * no single interval a band could represent; and `band` is this platform's
 * own declared optimal range, so drawing a laboratory's interval in the same
 * ink would merge two authors' claims into one rectangle.
 */
describe('TrendChart -- a printed interval sets the scale and is not drawn', () => {
  // Lymphocytes 15 -> 14 % against a union range of 20-45: a one-point move
  // in a test whose usual range is 25 points wide.
  const POINTS = [
    { date: '2026-09-09', value: 15, unit: '%' },
    { date: '2026-09-11', value: 14, unit: '%' },
  ];

  const dropHeight = () => {
    const dots = [...document.querySelectorAll('circle')].filter(
      (c) => c.getAttribute('r') && !c.getAttribute('stroke-dasharray')
    );
    const ys = dots.map((c) => Number(c.getAttribute('cy'))).filter(Number.isFinite);
    return ys.length >= 2 ? Math.abs(Math.max(...ys) - Math.min(...ys)) : null;
  };

  const rects = () => [...document.querySelectorAll('rect')].length;

  it('draws a small move as a shallow line once the printed range is the scale', () => {
    const { unmount } = render(<TrendChart label="LYMPHOCYTES" unit="%" points={POINTS} />);
    const unscaled = dropHeight();
    unmount();

    render(
      <TrendChart
        label="LYMPHOCYTES"
        unit="%"
        points={POINTS}
        scaleOnly={{ low: 20, high: 45 }}
      />
    );
    expect(unscaled).toBeGreaterThan(0);
    expect(dropHeight()).toBeLessThan(unscaled / 2);
  });

  it('DRAWS NOTHING for it -- no band rectangle appears', () => {
    const { unmount } = render(<TrendChart label="LYMPHOCYTES" unit="%" points={POINTS} />);
    const before = rects();
    unmount();

    render(
      <TrendChart
        label="LYMPHOCYTES"
        unit="%"
        points={POINTS}
        scaleOnly={{ low: 20, high: 45 }}
      />
    );
    // A `band` of the same numbers WOULD add one; this must not.
    expect(rects()).toBe(before);
  });

  it('labels the axis with readings only, never the printed range', () => {
    render(
      <TrendChart
        label="LYMPHOCYTES"
        unit="%"
        points={POINTS}
        scaleOnly={{ low: 20, high: 45 }}
      />
    );
    const text = document.body.textContent;
    expect(text).toMatch(/15/);
    expect(text).toMatch(/14/);
    // Neither bound is a reading anybody took.
    expect(text).not.toMatch(/\b45\b/);
    expect(text).not.toMatch(/\b20\b/);
  });

  it('uses a one-sided range without inventing the missing half', () => {
    // `< 6 mg/l` is a high and no low. The high must still widen the scale.
    const crp = [
      { date: '2026-09-09', value: 12.1, unit: 'mg/L' },
      { date: '2026-09-11', value: 38.9, unit: 'mg/L' },
    ];
    const { unmount } = render(<TrendChart label="CRP" unit="mg/L" points={crp} />);
    const unscaled = dropHeight();
    unmount();

    render(
      <TrendChart label="CRP" unit="mg/L" points={crp} scaleOnly={{ low: null, high: 6 }} />
    );
    const scaled = dropHeight();

    // Lower than before, because the domain now reaches down to 6 -- but a
    // tripling is a real change and must still read as one.
    expect(scaled).toBeLessThan(unscaled);
    expect(scaled).toBeGreaterThan(unscaled / 2);
  });

  it('is unchanged when no printed range reached the page', () => {
    const { unmount } = render(<TrendChart label="PCV" unit="%" points={POINTS} />);
    const plain = dropHeight();
    unmount();

    for (const scaleOnly of [null, undefined, { low: null, high: null }]) {
      const view = render(
        <TrendChart label="PCV" unit="%" points={POINTS} scaleOnly={scaleOnly} />
      );
      expect(dropHeight()).toBe(plain);
      view.unmount();
    }
  });
});
