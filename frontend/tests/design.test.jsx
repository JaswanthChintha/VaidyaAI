import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import RiskGauge from '../src/components/RiskGauge';
import CoverageRadar from '../src/components/CoverageRadar';
import RangeChart from '../src/components/RangeChart';
import ThemeToggle from '../src/components/ThemeToggle';
import { applyTheme, currentTheme, setTheme } from '../src/lib/theme';

/**
 * The design system, tested on the one thing a picture can get wrong that a
 * sentence cannot: MAKING AN ABSENCE LOOK LIKE A VALUE.
 *
 * A gauge has a resting position and it is "low". A radar vertex at the centre
 * looks like a bad score. A bar chart with no bar looks like zero. Each of
 * those is the same defect this codebase has spent its whole life refusing in
 * prose, arriving through a different door.
 */

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('the risk gauge', () => {
  it('draws no needle when nothing could be assessed', () => {
    // THE WHOLE REASON THIS COMPONENT EXISTS. Parking the needle at its rest
    // position would put it on "Low" and tell a reader whose report could not
    // be read that their risk is low.
    const { container } = render(<RiskGauge risk={null} assessed={false} />);
    expect(container.querySelector('.gauge__needle')).toBeNull();
    expect(screen.getByText('Not assessed')).toBeInTheDocument();
  });

  it('refuses a risk word that arrives with assessed false', () => {
    // Defence in depth against a payload that contradicts itself: absence is
    // the safer of the two readings, so absence wins.
    const { container } = render(<RiskGauge risk="Low" assessed={false} />);
    expect(container.querySelector('.gauge__needle')).toBeNull();
    expect(screen.getByText('Not assessed')).toBeInTheDocument();
  });

  it.each([
    ['Low', -60],
    ['Medium', -10],
    ['High', 38],
  ])('points at %s and holds that angle statically', (risk, angle) => {
    const { container } = render(<RiskGauge risk={risk} assessed />);
    const needle = container.querySelector('.gauge__needle');
    // The angle is an inline transform, NOT only a keyframe end state. Under
    // `prefers-reduced-motion` the animation is switched off entirely, and a
    // needle whose angle lived only in the keyframe would rest pointing at
    // "low" on a high-risk report.
    expect(needle.getAttribute('style')).toContain(`rotate(${angle}deg)`);
    // The verdict word, not the printed scale beneath it -- the axis carries
    // all three words permanently, the way a dial face does.
    expect(document.querySelector('.gauge__verdict').textContent).toBe(risk);
  });

  it('states the finding in words for a screen reader', () => {
    render(<RiskGauge risk="High" assessed />);
    expect(screen.getByRole('img', { name: /overall risk: high/i })).toBeInTheDocument();
  });

  it('says in words that nothing was assessed, not just visually', () => {
    render(<RiskGauge risk={null} assessed={false} />);
    expect(
      screen.getByRole('img', { name: /nothing on this report could be assessed/i })
    ).toBeInTheDocument();
  });
});

describe('the coverage radar', () => {
  const TOPICS = [
    { name: 'Diabetes', assessed: true, coverage: 0.95 },
    { name: 'Anemia', assessed: true, coverage: 0.55 },
    { name: 'Kidney Disease', assessed: false },
  ];

  it('draws an unassessed topic as a dashed, unfilled point', () => {
    const { container } = render(<CoverageRadar topics={TOPICS} />);
    const absent = container.querySelectorAll('.radar__vertex--absent');
    expect(absent).toHaveLength(1);
    // Dashed and hollow -- never a small filled dot, which is what a genuinely
    // low score looks like.
    expect(absent[0].getAttribute('fill')).toBe('none');
    expect(absent[0].getAttribute('stroke-dasharray')).toBe('2 2');
    expect(absent[0].getAttribute('stroke')).toBe('var(--mono)');
  });

  it('pins an unassessed topic to zero even if a coverage number arrives', () => {
    // A contradictory payload must not be able to draw a filled shape over a
    // topic nothing was measured for.
    const { container } = render(
      <CoverageRadar topics={[{ name: 'Kidney Disease', assessed: false, coverage: 0.9 }]} />
    );
    const vertex = container.querySelector('.radar__vertex--absent');
    // The centre of the mockup's pentagon.
    expect(vertex.getAttribute('cx')).toBe('139');
    expect(vertex.getAttribute('cy')).toBe('106');
  });

  it('drops the axis label of an unassessed topic to the absence colour', () => {
    const { container } = render(<CoverageRadar topics={TOPICS} />);
    const labels = [...container.querySelectorAll('.radar__label')];
    const kidney = labels.find((n) => n.textContent === 'Kidney Disease');
    expect(kidney.classList.contains('radar__label--absent')).toBe(true);
  });

  it('says in words that a zero is an absence, not a low score', () => {
    render(<CoverageRadar topics={TOPICS} />);
    expect(
      screen.getByRole('img', { name: /which is not a low score/i })
    ).toBeInTheDocument();
  });
});

describe('the range chart', () => {
  const ROW = {
    name: 'HbA1c',
    state: 'measured',
    value: 8.4,
    unit: '%',
    low: 4,
    high: 5.6,
    flagged: true,
  };

  it('draws a marker and an excess bar for a value past its range', () => {
    const { container } = render(<RangeChart rows={[ROW]} />);
    expect(container.querySelector('.range__marker')).not.toBeNull();
    expect(container.querySelector('.range__excess')).not.toBeNull();
    expect(screen.getByText('8.4 %')).toBeInTheDocument();
  });

  it('draws NO excess bar for a value inside its range', () => {
    // The bar is the visual sentence "by this much". One of zero length, or
    // one under an in-range value, claims an overshoot that did not happen.
    const { container } = render(
      <RangeChart rows={[{ ...ROW, value: 5.1, flagged: false }]} />
    );
    expect(container.querySelector('.range__excess')).toBeNull();
    expect(container.querySelector('.range__marker')).not.toBeNull();
  });

  it('draws NO marker at all for a value not on the report', () => {
    // A marker at zero is a measurement of zero. The band becomes a dashed
    // outline with no fill and the value column an em dash.
    const { container } = render(
      <RangeChart rows={[{ name: 'Vitamin D', state: 'not_on_report' }]} />
    );
    expect(container.querySelector('.range__marker')).toBeNull();
    expect(container.querySelector('.range__band--absent')).not.toBeNull();
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('Not on report')).toBeInTheDocument();
  });

  it('never plots a rejected reading, and says why it was refused', () => {
    const { container } = render(
      <RangeChart
        rows={[
          {
            name: 'Creatinine',
            state: 'rejected',
            value: 999,
            unit: 'mg/dl',
            note: 'Outside the physiologically possible range.',
          },
        ]}
      />
    );
    expect(container.querySelector('.range__marker')).toBeNull();
    expect(screen.queryByText(/999/)).not.toBeInTheDocument();
    expect(screen.getByText('Not usable')).toBeInTheDocument();
    expect(screen.getByText(/physiologically possible/)).toBeInTheDocument();
  });

  it('draws NO band for a measured value whose report printed no interval', () => {
    // THREE STATES, NOT TWO. A dashed empty band means "the value is missing".
    // A real value with no printed interval is the opposite: the value is
    // there, the comparison is not -- and on a report that prints no ranges
    // (which is most of the fixtures) the two-state version marked EVERY row
    // as absent while showing its number beside it.
    const { container } = render(
      <RangeChart rows={[{ name: 'HbA1c', state: 'measured', value: 8.4, unit: '%' }]} />
    );
    expect(container.querySelector('.range__band')).toBeNull();
    expect(container.querySelector('.range__band--absent')).toBeNull();
    // The value itself is still plotted and still printed.
    expect(container.querySelector('.range__marker')).not.toBeNull();
    expect(screen.getByText('8.4 %')).toBeInTheDocument();
  });

  it('keeps the dashed band for a value that is genuinely absent', () => {
    const { container } = render(
      <RangeChart rows={[{ name: 'Vitamin D', state: 'not_on_report' }]} />
    );
    expect(container.querySelector('.range__band--absent')).not.toBeNull();
  });

  it('says once, not per row, that no intervals were printed', () => {
    render(
      <RangeChart
        rows={[{ name: 'HbA1c', state: 'measured', value: 8.4, unit: '%' }]}
        note="This report printed no reference intervals."
      />
    );
    expect(screen.getByText(/printed no reference intervals/)).toBeInTheDocument();
  });

  it('hides the decorative bars from assistive tech', () => {
    // The results table below the chart is the real record; without this a
    // screen reader reads every value twice with a shape in between.
    const { container } = render(<RangeChart rows={[ROW]} />);
    expect(container.querySelector('.range__track').getAttribute('aria-hidden')).toBe('true');
    // The name and the value are NOT hidden -- they are the usable summary.
    expect(screen.getByText('8.4 %')).toBeInTheDocument();
    expect(screen.getByText(/HbA1c/)).toBeInTheDocument();
  });

  it('never renders an absence in a risk colour', () => {
    const { container } = render(
      <RangeChart rows={[{ name: 'Vitamin D', state: 'not_on_report' }]} />
    );
    const value = container.querySelector('.range__value');
    expect(value.getAttribute('style')).toContain('var(--mono)');
    expect(value.getAttribute('style')).not.toContain('--green');
    expect(value.getAttribute('style')).not.toContain('--rust');
  });
});

describe('the theme toggle', () => {
  it('switches the theme and remembers the choice', () => {
    applyTheme('light');
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole('button'));
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(localStorage.getItem('vaidyaai-theme')).toBe('dark');

    fireEvent.click(screen.getByRole('button'));
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(localStorage.getItem('vaidyaai-theme')).toBe('light');
  });

  it('says which theme the button will switch TO, not which is on', () => {
    // A sun and a moon are read both ways by roughly half of people each. The
    // word settles it, and `aria-pressed` says it again for a screen reader.
    setTheme('dark');
    render(<ThemeToggle />);
    const button = screen.getByRole('button');
    expect(button).toHaveTextContent('Light');
    expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('follows the system when the reader has never chosen', () => {
    localStorage.clear();
    expect(['light', 'dark']).toContain(currentTheme());
    expect(localStorage.getItem('vaidyaai-theme')).toBeNull();
  });

  it('survives storage that throws rather than taking the app down', () => {
    // A private window, or site data blocked: the ACCESSOR throws, it does not
    // return null. A theme preference must never be able to break the app.
    const original = Object.getOwnPropertyDescriptor(window, 'localStorage');
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('blocked');
      },
    });
    try {
      expect(() => render(<ThemeToggle />)).not.toThrow();
      expect(() => fireEvent.click(screen.getByRole('button'))).not.toThrow();
    } finally {
      if (original) Object.defineProperty(window, 'localStorage', original);
    }
  });
});
