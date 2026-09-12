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
    { name: 'Diabetes', assessed: true, coverage: 0.625, available: 5, cited: 8 },
    { name: 'Anemia', assessed: true, coverage: 1, available: 1, cited: 1 },
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
    // AND THE FILLED SHAPE PASSES THROUGH IT. The polygon and the vertices
    // once derived this separately, so the shape could reach out to a topic
    // whose own point was drawn at the centre as an absence.
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
    // A radius is not readable by a screen reader and is not precise to
    // anyone else either. "5 of 8" is both.
    render(<CoverageRadar topics={TOPICS} />);
    const label = screen.getByRole('img').getAttribute('aria-label');
    expect(label).toMatch(/Diabetes 5 of 8/);
    expect(label).toMatch(/Anemia 1 of 1/);
  });

  it('places the vertex at the coverage, not at the verdict', () => {
    // THE GEOMETRY, not just the words. Asserting only the spoken fractions
    // let the radius quietly go back to being the verdict and still pass.
    // The top spoke runs from the centre (139,106) to (139,22), so half
    // coverage is cy 64 and full coverage is cy 22.
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
    // A flagged topic examined on half its inputs sits INSIDE a clear topic
    // examined on all of them -- the opposite of the old behaviour.
    expect(Number(vertices[0].getAttribute('cy'))).toBeGreaterThan(22);
  });

  it('shows the dotted-point caption ONLY when a dotted point is drawn', () => {
    // On a report where every topic was assessed, the caption described a mark
    // that is not on the chart -- the same fault as a "shaded band = usual
    // range" legend above a chart with no band.
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
    // "Triglycerides" is right-anchored at x=9.1 and runs ~83 units wide, so
    // at the old -56 gutter it began at -74 and rendered as ".glycerides" on a
    // live report -- §6x's "olesterol" defect, on the other side of the chart.
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
    // The left-hand label's anchor, with room for the longest name this chart
    // can be given (~18 characters of 10.5px mono).
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

  /* The chart draws nothing at all unless at least one row carries a real
     reference interval (see `hasComparableRange`), so the per-row behaviours
     below are exercised NEXT TO a banded row rather than alone -- which is
     also the only arrangement in which a reader ever sees them. */
  const BANDED = { name: 'Vitamin B12', state: 'measured', value: 420, unit: 'pg/ml', low: 200, high: 900 };

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
      <RangeChart rows={[BANDED, { name: 'Vitamin D', state: 'not_on_report' }]} />
    );
    // One marker, for the banded row -- none for the absent one.
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
    // THREE STATES, NOT TWO. A dashed empty band means "the value is missing".
    // A real value with no printed interval is the opposite: the value is
    // there, the comparison is not -- and on a report that prints no ranges
    // (which is most of the fixtures) the two-state version marked EVERY row
    // as absent while showing its number beside it.
    const { container } = render(
      <RangeChart rows={[BANDED, { name: 'HbA1c', state: 'measured', value: 8.4, unit: '%' }]} />
    );
    const rows = container.querySelectorAll('.range__row');
    const bandless = rows[1];
    expect(bandless.querySelector('.range__band')).toBeNull();
    expect(bandless.querySelector('.range__band--absent')).toBeNull();
    // The value itself is still plotted and still printed.
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
    // READ OFF A REAL SCREEN. Every row's domain is derived from its own value
    // alone, so with no interval anywhere every marker lands at the same
    // fraction of its own track: eight rows, eight dots in an identical
    // position, separated only by colour. A picture that looks like a
    // measurement and encodes nothing is worse than no picture, and the panel
    // title promises a comparison that does not exist.
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
    // And the legend for a band that is not there goes with it.
    expect(screen.queryByText(/Shaded band/i)).not.toBeInTheDocument();
  });

  it('needs BOTH ends of an interval before it calls a row comparable', () => {
    // A floor with no ceiling draws no band (see the band state table), so a
    // chart admitted on the strength of one is a chart with no bands in it --
    // exactly the state this guard exists to refuse, reached sideways.
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

/**
 * THE STYLESHEET, READ AS SOURCE.
 *
 * jsdom applies no stylesheet and evaluates no media query, so every guarantee
 * that lives in CSS is invisible to every other test in this suite. That is
 * not a small gap: the round-up's "no fill" and "dashed" absence treatment,
 * and the header's behaviour on a phone, are all CSS and all unkillable from
 * a render test.
 *
 * These read `styles.css` as text and assert the one class of fault that has
 * actually bitten: A RULE THAT LOSES TO A LATER ONE AND SILENTLY DOES NOTHING.
 * The design system's own `.nav` block was dead for exactly this reason -- a
 * pre-existing `.nav` further down the file overrode its background, padding,
 * border and `.nav__user` type, and the in-page palette sweep passed it
 * because both rules use legitimate tokens. A palette sweep proves no colour
 * is foreign; it cannot prove a rule won.
 */
describe('the stylesheet, as source', () => {
  // `import.meta.url` is rewritten to an http URL by the Vite transform, so
  // the file is resolved from the project root instead (vitest's cwd).
  const css = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8');

  /** Every index at which a plain (non-media) `.nav {` rule opens. */
  const plainNavRuleOffsets = () => {
    const out = [];
    const re = /^\.nav\s*\{/gm;
    let m;
    while ((m = re.exec(css)) !== null) out.push(m.index);
    return out;
  };

  const mobileNavBlockOffset = () => css.indexOf('@media (max-width: 560px)', css.indexOf('THE HEADER ON A PHONE'));

  it('declares .nav exactly ONCE', () => {
    // THE DEFECT THIS PINS SHUT. The design system's header rule was added
    // ABOVE a pre-existing `.nav` block and lost every property they shared,
    // so the band, its padding, its border and the identity's type were dead
    // from the day they were written -- and the in-page palette sweep passed
    // the whole time, because the rule that won also used real tokens.
    // Two rules for one element is the shape of that fault, so the count is
    // the guarantee: a second `.nav {` is how it comes back.
    expect(plainNavRuleOffsets()).toHaveLength(1);
  });

  it('keeps the header on the --header band, not the panel colour', () => {
    // The specific thing that was silently lost (design.md section 4).
    const m = css.match(/^\.nav\s*\{([^}]*)\}/m);
    expect(m).not.toBeNull();
    expect(m[1]).toMatch(/background:\s*var\(--header\)/);
    expect(m[1]).toMatch(/border-bottom:\s*1px solid var\(--header-line\)/);
    // Folded in from the deleted block. Without these the header is not a row
    // at all -- the merge that removed that block had to carry them.
    expect(m[1]).toMatch(/display:\s*flex/);
    expect(m[1]).toMatch(/align-items:\s*center/);
  });

  it('keeps the header links out of the browser default underline', () => {
    // `text-decoration: none` existed ONLY in the deleted block. It is the
    // single easiest declaration to lose in a merge and the loss is visible on
    // every page: section 6x already had to fix browser-default anchors once.
    const m = css.match(/^\.nav a\s*\{([^}]*)\}/m);
    expect(m).not.toBeNull();
    expect(m[1]).toMatch(/text-decoration:\s*none/);
  });

  it('keeps the spacer that pushes the controls right', () => {
    // Also only in the deleted block. Without it the header collapses to the
    // left and the identity sits against the nav links.
    expect(css).toMatch(/\.nav__spacer\s*\{[^}]*flex:\s*1/);
  });

  it('puts the phone header rules AFTER every plain .nav rule', () => {
    // THE TRAP, PINNED. A media query adds no specificity, so
    // `@media (...) { .nav { ... } }` placed earlier in the file loses to a
    // later plain `.nav` on every shared property -- flex-wrap included, which
    // would restore the 558px horizontal scroll with the rule still present
    // and looking correct. Moving the block up is a silent revert, and this is
    // the only thing that would say so.
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
    // The wrap POINT is declared, not left to whatever fits. Without this the
    // `flex: 1` spacer absorbs row one's free space and the break lands
    // wherever the signed-in email's length happens to put it.
    const mobile = mobileNavBlockOffset();
    const block = css.slice(mobile, mobile + 1400);
    expect(block).toMatch(/\.nav__spacer\s*\{[^}]*flex-basis:\s*100%/);
  });

  it('truncates the signed-in identity at EVERY width, not just on a phone', () => {
    // SCOPING THIS TO THE PHONE QUERY WAS THE FIRST FIX, AND IT WAS WRONG.
    // Measured with the project's own test-account email (37 characters): the
    // header still overflowed from 561px to ~890px, with `Sign out` at x=811
    // on an 800px window. The identity is the only variable-length item in a
    // fixed row, so the rule belongs outside any breakpoint -- and this test
    // has to look outside the phone block or it would pass on the broken
    // version, which it did.
    const mobile = mobileNavBlockOffset();
    const base = css.slice(0, mobile);
    const m = base.match(/\.nav__user\s*\{([^}]*text-overflow[^}]*)\}/);
    expect(m).not.toBeNull();
    expect(m[1]).toMatch(/text-overflow:\s*ellipsis/);
    expect(m[1]).toMatch(/white-space:\s*nowrap/);
    // The load-bearing half: a flex item defaults to `min-width: auto` and
    // refuses to shrink below its content, so `overflow: hidden` alone does
    // nothing and the row grows instead.
    expect(m[1]).toMatch(/min-width:\s*0/);
  });

  it('draws an unchecked chip with NO FILL and a dashed border', () => {
    // design.md section 6, and the guarantee jsdom cannot see. An unchecked
    // topic acquiring a background is "we could not look" rendered as a quiet
    // pass -- the failure this whole screen exists to prevent.
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
    // MUTATION-FOUND GAP: dimming this to `--mono` survived everything. The
    // unchecked chip's colour is pinned and this one was not, so the two could
    // drift into the same ink while the fill and border still differed --
    // quietly spending one of the three signals that keep them apart.
    expect(m[1]).toMatch(/color:\s*var\(--ink\)/);
  });

  it('keeps the unchecked topic NAME readable rather than dimming it', () => {
    // A first version used `--mono` here: 3.37:1 on `--bg`, below AA and
    // DIMMER than the comma-run it replaced. The outline carries the absence
    // precisely so the text does not have to be degraded to carry it.
    const m = css.match(/\.chip--unassessed\s*\{([^}]*)\}/);
    expect(m[1]).toMatch(/color:\s*var\(--body\)/);
    expect(m[1]).not.toMatch(/color:\s*var\(--mono\)/);
  });

  it('spends no risk colour on the shared list rows', () => {
    // `--green`, `--amber` and `--rust` are categorical. A fourth decorative
    // use teaches the eye that colour here is decoration.
    //
    // This asserted `.guidance > li` and its `--panel-line` left rule until
    // the population page's limitations wanted the identical treatment. The
    // rule moved to a shared `.bullets` rather than being copied -- this file
    // has had to reverse a duplicated rule twice -- so the assertion follows
    // it. The INVARIANT is unchanged: no risk colour on a decorative mark.
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
    // The duplication guard. Two copies of this rule is how the dashboard and
    // the population page drift apart, and it is the same fault shape as the
    // two `.nav` blocks -- which cost a month of the header being dead.
    const defs = [...css.matchAll(/^\.bullets\s*\{/gm)];
    expect(defs).toHaveLength(1);
    // ...and no page-specific override reintroducing a second one.
    expect(css).not.toMatch(/\.\w[\w-]*\s+\.bullets\s*>\s*li\s*\{/);
  });

  it('gives a hint room below it, so it cannot touch what follows', () => {
    // MEASURED DEFECT, not a taste. `.hint` had `margin: 4px 0 0` -- no bottom
    // at all -- so anything after it without a top margin of its own sat at a
    // literal 0px gap. Four of those across two routes: the profile intro
    // against its form, the timeline intro against its first panel, a trend
    // summary against its chart, and a comparison lead against its table.
    // The areas read as "clumsy" because two blocks were in contact.
    //
    // The top margin must STAY small -- a hint belongs to the thing above it,
    // and pushing it away would attach it to the wrong subject.
    const m = css.match(/^\.hint \{([^}]*)\}/m);
    expect(m).not.toBeNull();
    const margin = m[1].match(/margin:\s*([^;]+);/)[1].trim().split(/\s+/);
    const [top, , bottom] = margin;
    expect(parseFloat(top)).toBeLessThanOrEqual(6);
    expect(parseFloat(bottom)).toBeGreaterThanOrEqual(10);
  });

  it('panels the population limitations instead of collapsing them', () => {
    // Section 6ag: what may never go is the CAVEAT. The dashboard's guidance
    // topics are behind a disclosure; these are not, and the difference is
    // deliberate -- a caveat behind a toggle is a caveat most readers never
    // open. If `.notes` ever becomes a `<details>`, this is the test that
    // should have to be deleted first.
    expect(css).toMatch(/^\.notes\s*\{/m);
    expect(css).toMatch(/\.notes__close\s*\{[^}]*border-top/);
  });
});

/**
 * TEXT CONTRAST, COMPUTED FROM THE TOKENS THEMSELVES.
 *
 * `--muted` and `--mono` both failed WCAG AA in the light theme for the whole
 * life of the design system -- `--mono` at 3.04:1 -- and the text they carry
 * is "Not measured", "not checked" and the reasons underneath them. **The
 * absence labels were the least readable text in the app**, on a screen whose
 * entire purpose is that an absence must not be mistaken for a result.
 *
 * Nothing could have caught it: jsdom has no colours, the in-page palette
 * sweep only asks whether a colour is IN the palette, and a token that is in
 * the palette and too light passes that check every time. So the ratio is
 * computed here, from the hex values as written, against the grounds these
 * tokens are actually rendered on (measured in the live DOM: `--bg`,
 * `--header`, `--panel` -- never `--track`, which backs chart geometry and no
 * text).
 */
describe('text contrast, from the tokens', () => {
  const css = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8');

  /** Read one custom property out of a given rule block. */
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

  // WHICH TOKEN LANDS ON WHICH GROUND -- MEASURED, NOT ASSUMED.
  //
  // Collected by walking the rendered DOM of six routes in both themes and
  // recording the effective background behind every text node. The first
  // version of this test used the cartesian product instead and failed on
  // `--green-text` over `--header` at 4.11:1 -- a pairing that does not exist
  // and never will, because the header holds a wordmark, links, an identity
  // and two controls, and no verdict word. Tuning a colour to satisfy a
  // combination nothing renders is the same error as tuning `--mono` to
  // `--track`, which backs chart geometry and no text at all.
  //
  // A NEW PAIRING MEANS A NEW ROW HERE. That is the point: adding one is a
  // deliberate act with a contrast number attached, rather than something
  // that slips in behind a green suite.
  const USED_ON = {
    '--ink': ['--bg', '--header', '--panel'],
    '--ink-2': ['--panel'],
    '--body': ['--bg', '--header', '--panel'],
    '--muted': ['--bg', '--panel'],
    '--mono': ['--bg', '--header', '--panel'],
    '--brand': ['--header', '--panel'],
    // Risk words. A verdict is text before it is a colour, so all three are
    // held to the text floor on the grounds a results table actually uses.
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
    // MUTATION-FOUND GAP, and the most useful finding of the three tokens.
    // The stylesheet's rules do not name `--amber-text`; they name `--medium`.
    // Repointing that alias back to `var(--amber)` restores the 2.28:1 defect
    // in full and SURVIVED every test above, because those check the token
    // VALUES and nothing checked what the aliases resolve to. A guard over a
    // list cannot see what never entered the list -- section 6ad's lesson, in
    // a stylesheet.
    //
    // `--low`, `--medium` and `--high` are the risk aliases and all three are
    // used as text. Each must resolve to a value held by the AA test above,
    // never to the raw band colour beside it.
    const aliases = {
      '--low': '--green-text',
      '--medium': '--amber-text',
      '--high': '--rust',
      '--absent': '--mono',
      // `.error` on the sign-in card, `.status--failed`, `.report__confirm-text`.
      // Added after auditing /signin, which is the one route the signed-in
      // session cannot reach and so had never been measured at all.
      '--danger': '--rust',
    };
    for (const [alias, target] of Object.entries(aliases)) {
      const m = css.match(new RegExp(`${alias}:\\s*var\\((--[\\w-]+)\\)`));
      expect(m, `${alias} is not declared as an alias`).not.toBeNull();
      expect(m[1], `${alias} must resolve to ${target}`).toBe(target);
    }
  });

  it('keeps the three risk colours separable from each other as text', () => {
    // Darkening any hue far enough to pass AA on sand drags it toward the
    // others' luminance -- `--amber-text` and `--rust` differ by only 1.05:1 --
    // so luminance cannot be what tells them apart, and the stylesheet's
    // header requires that it can be told apart. CIE Lab dE is the measure
    // that survives that darkening; ~2 is just noticeable, and these sit
    // near 30.
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
    // `--mono` carries tracked uppercase at 11px -- `NOT CHECKED`,
    // `NOT ON REPORT`, the header identity. It is harder to read than
    // `--muted`'s prose at the same ratio, so it is set darker rather than
    // both being pushed to the same floor. Reversing that is a regression the
    // AA test alone would not notice, because both would still pass.
    const t = tokensOf(':root');
    expect(luminance(t['--mono'])).toBeLessThan(luminance(t['--muted']));
  });

  it('does not let an absence label reach full body ink', () => {
    // The other direction. These labels must stay legible AND stay recessive:
    // an absence rendered at the same weight as a result is the failure this
    // whole design system exists to prevent. Readable, not loud.
    const t = tokensOf(':root');
    expect(luminance(t['--mono'])).toBeGreaterThan(luminance(t['--ink']));
    expect(luminance(t['--mono'])).toBeGreaterThan(luminance(t['--body']));
  });
});

/**
 * THE PERCENTILE BAR.
 *
 * It replaced two sentences per card that differed only by the parameter name
 * interpolated into one template. The thing it must never do is become a
 * verdict: the page states in as many words that a percentile "does not say
 * whether a result is normal, high, or low", and a green or rust segment two
 * inches below that sentence contradicts it.
 */
describe('the percentile bar', () => {
  const between = {
    position: 'between_published_percentiles',
    lowerPercentile: 50,
    upperPercentile: 75,
    label: 'between the 50th and the 75th percentile',
  };

  it('draws the band between its two published cut-points', () => {
    // Track runs x=10..250, so 50th is x=130 and 75th is x=190.
    const { container } = render(<PercentileBar {...between} />);
    const band = container.querySelector('.pctbar__band');
    expect(Number(band.getAttribute('x'))).toBeCloseTo(130, 0);
    expect(Number(band.getAttribute('width'))).toBeCloseTo(60, 0);
  });

  it('spends no risk colour on the band', () => {
    // The whole reason this is a bar and not a verdict.
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
    // NOT LIVE-VERIFIED: both stored reports produce only
    // `between_published_percentiles`, so this path and the one below have
    // never been rendered from real data. They are reachable the moment a
    // value falls outside the published grid.
    //
    // "Below the 5th percentile" has no floor in the survey. A closed segment
    // starting at 0 would assert a lower bound nobody published -- the
    // one-sided-interval fault of 6ab and 6z. The segment runs to the frame
    // and the cap that would close it is not drawn.
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
    // Absence is not a guess. A vocabulary the service grows later must not
    // be rendered as a shape whose meaning this component invented.
    const { container } = render(
      <PercentileBar position="interpolated_estimate" lowerPercentile={10} upperPercentile={20} label="x" />
    );
    expect(container.querySelector('.pctbar')).toBeNull();
  });

  it('draws nothing when a band is missing an end it claims to have', () => {
    // A contradictory payload: `between` with only one cut-point. Absence
    // wins the contradiction, the same rule as the gauge and the radar.
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
