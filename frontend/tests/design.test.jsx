import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import RiskGauge from '../src/components/RiskGauge';
import CoverageRadar from '../src/components/CoverageRadar';
import RangeChart from '../src/components/RangeChart';
import ThemeToggle from '../src/components/ThemeToggle';
import PercentileBar from '../src/components/PercentileBar';
import { applyTheme, currentTheme, setTheme } from '../src/lib/theme';


beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('the risk gauge', () => {
  it('draws no needle when nothing could be assessed', () => {
    const { container } = render(<RiskGauge risk={null} assessed={false} />);
    expect(container.querySelector('.gauge__needle')).toBeNull();
    expect(screen.getByText('Not assessed')).toBeInTheDocument();
  });

  it('refuses a risk word that arrives with assessed false', () => {
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
    expect(needle.getAttribute('style')).toContain(`rotate(${angle}deg)`);
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
    { name: 'Diabetes', assessed: true, coverage: 0.625, available: 5, cited: 8 },
    { name: 'Anemia', assessed: true, coverage: 1, available: 1, cited: 1 },
    { name: 'Kidney Disease', assessed: false },
  ];

  it('draws an unassessed topic as a dashed, unfilled point', () => {
    const { container } = render(<CoverageRadar topics={TOPICS} />);
    const absent = container.querySelectorAll('.radar__vertex--absent');
    expect(absent).toHaveLength(1);
    expect(absent[0].getAttribute('fill')).toBe('none');
    expect(absent[0].getAttribute('stroke-dasharray')).toBe('2 2');
    expect(absent[0].getAttribute('stroke')).toBe('var(--mono)');
  });

  it('pins an unassessed topic to zero even if a coverage number arrives', () => {
    const { container } = render(
      <CoverageRadar topics={[{ name: 'Kidney Disease', assessed: false, coverage: 0.9 }]} />
    );
    const vertex = container.querySelector('.radar__vertex--absent');
    expect(vertex.getAttribute('cx')).toBe('139');
    expect(vertex.getAttribute('cy')).toBe('106');
    expect(container.querySelector('.radar__shape').getAttribute('points'))
      .toBe('139.0,106.0');
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

  it('says each topic’s coverage as a fraction, not only as a distance', () => {
    render(<CoverageRadar topics={TOPICS} />);
    const label = screen.getByRole('img').getAttribute('aria-label');
    expect(label).toMatch(/Diabetes 5 of 8/);
    expect(label).toMatch(/Anemia 1 of 1/);
  });

  it('places the vertex at the coverage, not at the verdict', () => {
    const { container } = render(
      <CoverageRadar
        topics={[
          { name: 'Diabetes', assessed: true, coverage: 0.5, available: 2, cited: 4 },
          { name: 'Anemia', assessed: true, coverage: 1, available: 1, cited: 1 },
        ]}
      />
    );
    const vertices = container.querySelectorAll('.radar__vertex');
    expect(Number(vertices[0].getAttribute('cy'))).toBeCloseTo(64, 0);
    expect(Number(vertices[0].getAttribute('cy'))).toBeGreaterThan(22);
  });

  it('shows the dotted-point caption ONLY when a dotted point is drawn', () => {
    const caption = 'A dotted point sits at zero because nothing was measured.';

    const withAbsence = render(<CoverageRadar topics={TOPICS} absenceCaption={caption} />);
    expect(withAbsence.container.querySelector('figcaption')).not.toBeNull();
    withAbsence.unmount();

    const allAssessed = render(
      <CoverageRadar
        topics={TOPICS.filter((t) => t.assessed === true)}
        absenceCaption={caption}
      />
    );
    expect(allAssessed.container.querySelector('.radar__vertex--absent')).toBeNull();
    expect(allAssessed.container.querySelector('figcaption')).toBeNull();
  });

  it('gives its longest axis label room inside the frame', () => {
    const { container } = render(
      <CoverageRadar
        topics={[
          { name: 'Diabetes', assessed: true, coverage: 1, available: 1, cited: 1 },
          { name: 'Kidney', assessed: true, coverage: 1, available: 1, cited: 1 },
          { name: 'Heart', assessed: true, coverage: 1, available: 1, cited: 1 },
          { name: 'Cholesterol', assessed: true, coverage: 1, available: 1, cited: 1 },
          { name: 'Haemoglobin (high)', assessed: true, coverage: 1, available: 1, cited: 1 },
        ]}
      />
    );
    const [minX] = container.querySelector('svg').getAttribute('viewBox').split(' ').map(Number);
    expect(9.1 - minX).toBeGreaterThanOrEqual(110);
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

  const BANDED = { name: 'Vitamin B12', state: 'measured', value: 420, unit: 'pg/ml', low: 200, high: 900 };

  it('draws a marker and an excess bar for a value past its range', () => {
    const { container } = render(<RangeChart rows={[ROW]} />);
    expect(container.querySelector('.range__marker')).not.toBeNull();
    expect(container.querySelector('.range__excess')).not.toBeNull();
    expect(screen.getByText('8.4 %')).toBeInTheDocument();
  });

  it('draws NO excess bar for a value inside its range', () => {
    const { container } = render(
      <RangeChart rows={[{ ...ROW, value: 5.1, flagged: false }]} />
    );
    expect(container.querySelector('.range__excess')).toBeNull();
    expect(container.querySelector('.range__marker')).not.toBeNull();
  });

  it('draws NO marker at all for a value not on the report', () => {
    const { container } = render(
      <RangeChart rows={[BANDED, { name: 'Vitamin D', state: 'not_on_report' }]} />
    );
    expect(container.querySelectorAll('.range__marker')).toHaveLength(1);
    expect(container.querySelector('.range__band--absent')).not.toBeNull();
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('Not on report')).toBeInTheDocument();
  });

  it('never plots a rejected reading, and says why it was refused', () => {
    const { container } = render(
      <RangeChart
        rows={[
          BANDED,
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
    expect(container.querySelectorAll('.range__marker')).toHaveLength(1);
    expect(screen.queryByText(/999/)).not.toBeInTheDocument();
    expect(screen.getByText('Not usable')).toBeInTheDocument();
    expect(screen.getByText(/physiologically possible/)).toBeInTheDocument();
  });

  it('draws NO band for a measured value whose report printed no interval', () => {
    const { container } = render(
      <RangeChart rows={[BANDED, { name: 'HbA1c', state: 'measured', value: 8.4, unit: '%' }]} />
    );
    const rows = container.querySelectorAll('.range__row');
    const bandless = rows[1];
    expect(bandless.querySelector('.range__band')).toBeNull();
    expect(bandless.querySelector('.range__band--absent')).toBeNull();
    expect(bandless.querySelector('.range__marker')).not.toBeNull();
    expect(screen.getByText('8.4 %')).toBeInTheDocument();
  });

  it('keeps the dashed band for a value that is genuinely absent', () => {
    const { container } = render(
      <RangeChart rows={[BANDED, { name: 'Vitamin D', state: 'not_on_report' }]} />
    );
    expect(container.querySelector('.range__band--absent')).not.toBeNull();
  });

  it('draws NOTHING when not one row has a reference range', () => {
    const { container } = render(
      <RangeChart
        rows={[
          { name: 'HbA1c', state: 'measured', value: 8.4, unit: '%' },
          { name: 'Blood sugar', state: 'measured', value: 186, unit: 'mg/dl' },
          { name: 'Heart disease history', state: 'not_on_report' },
        ]}
      />
    );
    expect(container.querySelector('.range')).toBeNull();
    expect(screen.queryByText(/Shaded band/i)).not.toBeInTheDocument();
  });

  it('needs BOTH ends of an interval before it calls a row comparable', () => {
    const { container } = render(
      <RangeChart
        rows={[
          { name: 'Total cholesterol', state: 'measured', value: 268, unit: 'mg/dl', low: 200 },
          { name: 'HbA1c', state: 'measured', value: 8.4, unit: '%' },
        ]}
      />
    );
    expect(container.querySelector('.range')).toBeNull();
  });

  it('draws the chart as soon as ONE row has something to compare against', () => {
    const { container } = render(
      <RangeChart
        rows={[
          { name: 'HbA1c', state: 'measured', value: 8.4, unit: '%' },
          BANDED,
        ]}
      />
    );
    expect(container.querySelector('.range')).not.toBeNull();
    expect(container.querySelectorAll('.range__row')).toHaveLength(2);
  });

  it('hides the decorative bars from assistive tech', () => {
    const { container } = render(<RangeChart rows={[ROW]} />);
    expect(container.querySelector('.range__track').getAttribute('aria-hidden')).toBe('true');
    expect(screen.getByText('8.4 %')).toBeInTheDocument();
    expect(screen.getByText(/HbA1c/)).toBeInTheDocument();
  });

  it('never renders an absence in a risk colour', () => {
    const { container } = render(
      <RangeChart rows={[BANDED, { name: 'Vitamin D', state: 'not_on_report' }]} />
    );
    const value = container.querySelectorAll('.range__value')[1];
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

describe('the stylesheet, as source', () => {
  const css = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8');

  const plainNavRuleOffsets = () => {
    const out = [];
    const re = /^\.nav\s*\{/gm;
    let m;
    while ((m = re.exec(css)) !== null) out.push(m.index);
    return out;
  };

  const mobileNavBlockOffset = () => css.indexOf('@media (max-width: 560px)', css.indexOf('THE HEADER ON A PHONE'));

  it('declares .nav exactly ONCE', () => {
    expect(plainNavRuleOffsets()).toHaveLength(1);
  });

  it('keeps the header on the --header band, not the panel colour', () => {
    const m = css.match(/^\.nav\s*\{([^}]*)\}/m);
    expect(m).not.toBeNull();
    expect(m[1]).toMatch(/background:\s*var\(--header\)/);
    expect(m[1]).toMatch(/border-bottom:\s*1px solid var\(--header-line\)/);
    expect(m[1]).toMatch(/display:\s*flex/);
    expect(m[1]).toMatch(/align-items:\s*center/);
  });

  it('keeps the header links out of the browser default underline', () => {
    const m = css.match(/^\.nav a\s*\{([^}]*)\}/m);
    expect(m).not.toBeNull();
    expect(m[1]).toMatch(/text-decoration:\s*none/);
  });

  it('keeps the spacer that pushes the controls right', () => {
    expect(css).toMatch(/\.nav__spacer\s*\{[^}]*flex:\s*1/);
  });

  it('puts the phone header rules AFTER every plain .nav rule', () => {
    const mobile = mobileNavBlockOffset();
    expect(mobile).toBeGreaterThan(-1);
    const plains = plainNavRuleOffsets();
    expect(plains.length).toBeGreaterThan(0);
    for (const offset of plains) expect(mobile).toBeGreaterThan(offset);
  });

  it('lets the header wrap on a phone', () => {
    const mobile = mobileNavBlockOffset();
    const block = css.slice(mobile, mobile + 1400);
    expect(block).toMatch(/flex-wrap:\s*wrap/);
  });

  it('turns the nav spacer into a full-width line break on a phone', () => {
    const mobile = mobileNavBlockOffset();
    const block = css.slice(mobile, mobile + 1400);
    expect(block).toMatch(/\.nav__spacer\s*\{[^}]*flex-basis:\s*100%/);
  });

  it('truncates the signed-in identity at EVERY width, not just on a phone', () => {
    const mobile = mobileNavBlockOffset();
    const base = css.slice(0, mobile);
    const m = base.match(/\.nav__user\s*\{([^}]*text-overflow[^}]*)\}/);
    expect(m).not.toBeNull();
    expect(m[1]).toMatch(/text-overflow:\s*ellipsis/);
    expect(m[1]).toMatch(/white-space:\s*nowrap/);
    expect(m[1]).toMatch(/min-width:\s*0/);
  });

  it('draws an unchecked chip with NO FILL and a dashed border', () => {
    const m = css.match(/\.chip--unassessed\s*\{([^}]*)\}/);
    expect(m).not.toBeNull();
    expect(m[1]).toMatch(/background:\s*none/);
    expect(m[1]).toMatch(/border:\s*1px dashed var\(--band-line\)/);
  });

  it('draws a cleared chip filled and solid, so the two cannot be confused', () => {
    const m = css.match(/\.chip--clear\s*\{([^}]*)\}/);
    expect(m).not.toBeNull();
    expect(m[1]).toMatch(/background:\s*var\(--panel\)/);
    expect(m[1]).toMatch(/border:\s*1px solid/);
    expect(m[1]).not.toMatch(/dashed/);
    expect(m[1]).toMatch(/color:\s*var\(--ink\)/);
  });

  it('keeps the unchecked topic NAME readable rather than dimming it', () => {
    const m = css.match(/\.chip--unassessed\s*\{([^}]*)\}/);
    expect(m[1]).toMatch(/color:\s*var\(--body\)/);
    expect(m[1]).not.toMatch(/color:\s*var\(--mono\)/);
  });

  it('spends no risk colour on the shared list rows', () => {
    const row = css.match(/\.bullets\s*>\s*li\s*\{([^}]*)\}/);
    const mark = css.match(/\.bullets\s*>\s*li::before\s*\{([^}]*)\}/);
    expect(row).not.toBeNull();
    expect(mark).not.toBeNull();
    const risk = /--green\b|--amber\b|--rust\b|--low\b|--medium\b|--high\b/;
    expect(row[1]).not.toMatch(risk);
    expect(mark[1]).not.toMatch(risk);
    expect(row[1]).toMatch(/border-top:[^;]*var\(--hairline\)/);
  });

  it('keeps ONE definition of the shared list rows', () => {
    const defs = [...css.matchAll(/^\.bullets\s*\{/gm)];
    expect(defs).toHaveLength(1);
    expect(css).not.toMatch(/\.\w[\w-]*\s+\.bullets\s*>\s*li\s*\{/);
  });

  it('gives a hint room below it, so it cannot touch what follows', () => {
    const m = css.match(/^\.hint \{([^}]*)\}/m);
    expect(m).not.toBeNull();
    const margin = m[1].match(/margin:\s*([^;]+);/)[1].trim().split(/\s+/);
    const [top, , bottom] = margin;
    expect(parseFloat(top)).toBeLessThanOrEqual(6);
    expect(parseFloat(bottom)).toBeGreaterThanOrEqual(10);
  });

  it('panels the population limitations instead of collapsing them', () => {
    expect(css).toMatch(/^\.notes\s*\{/m);
    expect(css).toMatch(/\.notes__close\s*\{[^}]*border-top/);
  });
});

describe('text contrast, from the tokens', () => {
  const css = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8');

  const tokensOf = (selector) => {
    const block = css.slice(css.indexOf(selector + ' {'));
    const body = block.slice(0, block.indexOf('\n}'));
    const out = {};
    for (const [, name, value] of body.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
      out[name] = value;
    }
    return out;
  };

  const channel = (v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const luminance = (hex) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const contrast = (a, b) => {
    const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };

  const USED_ON = {
    '--ink': ['--bg', '--header', '--panel'],
    '--ink-2': ['--panel'],
    '--body': ['--bg', '--header', '--panel'],
    '--muted': ['--bg', '--panel'],
    '--mono': ['--bg', '--header', '--panel'],
    '--brand': ['--header', '--panel'],
    '--green-text': ['--panel', '--bg'],
    '--amber-text': ['--panel', '--bg'],
    '--rust': ['--panel', '--bg'],
  };
  const AA = 4.5;

  for (const [theme, selector] of [['light', ':root'], ['dark', '[data-theme="dark"]']]) {
    it(`keeps every text token at AA on every ground it is used on (${theme})`, () => {
      const t = tokensOf(selector);
      const failures = [];
      for (const [token, grounds] of Object.entries(USED_ON)) {
        expect(t[token], `${token} missing from ${selector}`).toBeTruthy();
        for (const ground of grounds) {
          expect(t[ground], `${ground} missing from ${selector}`).toBeTruthy();
          const ratio = contrast(t[token], t[ground]);
          if (ratio < AA) {
            failures.push(`${token} on ${ground}: ${ratio.toFixed(2)}:1`);
          }
        }
      }
      expect(failures).toEqual([]);
    });
  }

  it('points every text-carrying ALIAS at a text-safe value', () => {
    const aliases = {
      '--low': '--green-text',
      '--medium': '--amber-text',
      '--high': '--rust',
      '--absent': '--mono',
      '--danger': '--rust',
    };
    for (const [alias, target] of Object.entries(aliases)) {
      const m = css.match(new RegExp(`${alias}:\\s*var\\((--[\\w-]+)\\)`));
      expect(m, `${alias} is not declared as an alias`).not.toBeNull();
      expect(m[1], `${alias} must resolve to ${target}`).toBe(target);
    }
  });

  it('keeps the three risk colours separable from each other as text', () => {
    const t = tokensOf(':root');
    const f = (v) => (v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116);
    const lab = (hex) => {
      const [r, g, b] = [1, 3, 5]
        .map((i) => parseInt(hex.slice(i, i + 2), 16))
        .map(channel);
      const X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
      const Y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      const Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
      return [116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))];
    };
    const dE = (a, b) => {
      const [A, B] = [lab(a), lab(b)];
      return Math.hypot(A[0] - B[0], A[1] - B[1], A[2] - B[2]);
    };
    const pairs = [
      ['--amber-text', '--rust'],
      ['--amber-text', '--green-text'],
      ['--rust', '--green-text'],
    ];
    for (const [a, b] of pairs) {
      expect(dE(t[a], t[b]), `${a} vs ${b}`).toBeGreaterThan(20);
    }
  });

  it('gives the 11px micro-label MORE contrast than 13-14px prose', () => {
    const t = tokensOf(':root');
    expect(luminance(t['--mono'])).toBeLessThan(luminance(t['--muted']));
  });

  it('does not let an absence label reach full body ink', () => {
    const t = tokensOf(':root');
    expect(luminance(t['--mono'])).toBeGreaterThan(luminance(t['--ink']));
    expect(luminance(t['--mono'])).toBeGreaterThan(luminance(t['--body']));
  });
});

describe('the percentile bar', () => {
  const between = {
    position: 'between_published_percentiles',
    lowerPercentile: 50,
    upperPercentile: 75,
    label: 'between the 50th and the 75th percentile',
  };

  it('draws the band between its two published cut-points', () => {
    const { container } = render(<PercentileBar {...between} />);
    const band = container.querySelector('.pctbar__band');
    expect(Number(band.getAttribute('x'))).toBeCloseTo(130, 0);
    expect(Number(band.getAttribute('width'))).toBeCloseTo(60, 0);
  });

  it('spends no risk colour on the band', () => {
    const { container } = render(<PercentileBar {...between} />);
    const fill = container.querySelector('.pctbar__band').getAttribute('fill');
    expect(fill).toBe('var(--brand)');
    expect(fill).not.toMatch(/--green|--amber|--rust|--low|--medium|--high/);
  });

  it('says the band in words for a screen reader', () => {
    render(<PercentileBar {...between} />);
    expect(
      screen.getByRole('img', { name: /between the 50th and the 75th percentile/i })
    ).toBeInTheDocument();
  });

  it('leaves a BELOW-LOWEST band open at the bottom', () => {
    const { container } = render(
      <PercentileBar
        position="below_lowest_published_percentile"
        lowerPercentile={null}
        upperPercentile={5}
        label="below the 5th percentile"
      />
    );
    const band = container.querySelector('.pctbar__band');
    expect(Number(band.getAttribute('x'))).toBe(10);
    expect(container.querySelectorAll('.pctbar__cap')).toHaveLength(1);
  });

  it('leaves an AT-OR-ABOVE-HIGHEST band open at the top', () => {
    const { container } = render(
      <PercentileBar
        position="at_or_above_highest_published_percentile"
        lowerPercentile={95}
        upperPercentile={null}
        label="at or above the 95th percentile"
      />
    );
    const band = container.querySelector('.pctbar__band');
    const right = Number(band.getAttribute('x')) + Number(band.getAttribute('width'));
    expect(right).toBeCloseTo(250, 0);
    expect(container.querySelectorAll('.pctbar__cap')).toHaveLength(1);
  });

  it('draws nothing for a position it does not recognise', () => {
    const { container } = render(
      <PercentileBar position="interpolated_estimate" lowerPercentile={10} upperPercentile={20} label="x" />
    );
    expect(container.querySelector('.pctbar')).toBeNull();
  });

  it('draws nothing when a band is missing an end it claims to have', () => {
    const { container } = render(
      <PercentileBar
        position="between_published_percentiles"
        lowerPercentile={50}
        upperPercentile={null}
        label="between the 50th and the ?"
      />
    );
    expect(container.querySelector('.pctbar')).toBeNull();
  });
});
