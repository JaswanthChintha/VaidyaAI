import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import TrendChart from '../src/components/TrendChart';


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
    const { container } = render(<TrendChart {...classified} />);
    const titles = [...container.querySelectorAll('.trend-chart__point title')]
      .map((t) => t.textContent);
    expect(titles).toHaveLength(3);
    expect(titles[1]).toMatch(/^6\.4 %/);
    expect(titles[1]).toMatch(/10 Apr 2026/);
  });

  it('names every reading in its summary while the list stays readable', () => {
    render(<TrendChart {...classified} />);
    const label = screen.getByRole('img').getAttribute('aria-label');
    expect(label).toMatch(/6\.1 %/);
    expect(label).toMatch(/6\.4 %/);
    expect(label).toMatch(/6\.8 %/);
  });

  it('falls back to the two ends when the series is long', () => {
    const many = Array.from({ length: 9 }, (_, i) => ({
      date: `2026-0${i + 1}-10T00:00:00Z`,
      value: 6 + i * 0.1,
      unit: '%',
    }));
    render(<TrendChart {...classified} points={many} />);
    const label = screen.getByRole('img').getAttribute('aria-label');
    expect(label).toMatch(/across 9 readings/);
    expect(label).not.toMatch(/6\.3 %/);
  });

  it('prints the scale it drew the slope against', () => {
    const { container } = render(<TrendChart {...classified} />);
    expect(container.querySelectorAll('.trend-chart__axis').length).toBeGreaterThanOrEqual(4);
  });

  it('reserves a gutter wide enough for its own axis labels', () => {
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
    expect(anchor - minX).toBeGreaterThanOrEqual(66);
  });

  it('takes a risk colour ONLY from a classified direction', () => {
    const { container } = render(<TrendChart {...classified} />);
    expect(paths(container)[0].getAttribute('stroke')).toBe('var(--rust)');
  });

  it('refuses a risk colour when no direction was classified', () => {
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
    const { container } = render(
      <TrendChart {...classified} classified={false} trend="worsening" />
    );
    expect(paths(container)[0].getAttribute('stroke')).toBe('var(--ink)');
    expect(screen.getByRole('img').getAttribute('aria-label')).toMatch(
      /No direction was classified/
    );
  });

  it('never prints a trend word it does not recognise, or a null one', () => {
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
    expect(markers(container)).toHaveLength(1);
  });

  it('says a change needs two readings, and never says "stable"', () => {
    const { container } = render(<TrendChart {...single} />);
    expect(
      screen.getByText(/no line is drawn, because a change needs two/i)
    ).toBeInTheDocument();
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
    const { container } = render(<TrendChart {...single} />);
    const axisText = [...container.querySelectorAll('.trend-chart__axis')]
      .map((node) => node.textContent)
      .join(' ');
    expect(axisText).not.toMatch(/6\.86|5\.34/);
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
    expect(markers(container)).toHaveLength(2);
    expect(gapMarkers(container)).toHaveLength(1);
    expect(screen.getByText('Not usable')).toBeInTheDocument();
    expect(
      screen.getAllByText(/not physiologically plausible/).length
    ).toBeGreaterThanOrEqual(1);
    const axisText = [...container.querySelectorAll('.trend-chart__axis')]
      .map((node) => node.textContent)
      .join(' ');
    expect(axisText).not.toContain('999');
    expect(paths(container)).toHaveLength(0);
  });

  it('calls a reading that could not be used "not usable", not "no reading"', () => {
    render(<TrendChart {...rejected} gaps={[{ date: D2, kind: 'unusable', reason: 'r' }]} />);
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

describe('TrendChart -- the significance span sets the scale', () => {
  const STABILITY = { significant_change_pct: 17, min_absolute_change: 5 };
  const POINTS = [
    { date: '2026-09-09', value: 186, unit: 'mg/dl' },
    { date: '2026-09-11', value: 172, unit: 'mg/dl' },
  ];

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
    expect(withBand).toBeLessThan(withoutBand / 2);
  });

  it('still prints the readings themselves, never the scale', () => {
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

describe('TrendChart -- a printed interval sets the scale and is not drawn', () => {
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
    expect(text).not.toMatch(/\b45\b/);
    expect(text).not.toMatch(/\b20\b/);
  });

  it('uses a one-sided range without inventing the missing half', () => {
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
