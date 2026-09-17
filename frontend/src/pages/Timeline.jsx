import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { Absent, Value, WarningList } from '../components/Absent';
import TrendChart from '../components/TrendChart';
import { PATIENT_LABEL } from '../lib/labels';
import { isPresent } from '../lib/absence';

/**
 * Modules 28, 29 and 30 -- trends, comparison and the progress score.
 *
 * ==========================================================================
 * THE WORD THIS SCREEN MUST NEVER PRINT WITHOUT EARNING
 * ==========================================================================
 *
 * "Stable". Module 28 reserves it for a change measured against a declared
 * stability band -- a reference change value, not a round percentage. Fewer
 * than two usable readings is `INSUFFICIENT_DATA` with `trend: null`, and
 * rendering that as "stable", "no change" or a flat line states something
 * nobody measured. It is the single most repeated hazard on this project and
 * it would be trivially easy to commit here, because a timeline with nothing
 * on it looks like a timeline that did not move.
 *
 * So `outcome` is what this screen branches on, never `trend`. Every refusal
 * outcome carries its own sentence from the service, and those sentences are
 * shown rather than replaced with a friendlier summary -- they are the
 * product, not an error path.
 *
 * ==========================================================================
 * THE HISTORY BLOCK IS SHOWN, NOT HIDDEN
 * ==========================================================================
 *
 * A timeline built from two of a patient's nine reports and a timeline built
 * from a patient's only two reports look identical unless the accounting is
 * on screen. `considered`, `included`, `excludedCount` and `droppedByCap` are
 * rendered for exactly that reason -- the backend added `droppedByCap`
 * because an audit found five reports falling into neither bucket when the
 * cap engaged.
 */

function HistorySummary({ history }) {
  if (!history) return null;
  const dropped = history.droppedByCap;

  return (
    <p className="history">
      Built from <strong>{history.included}</strong> of{' '}
      <strong>{history.considered}</strong> report(s).
      {isPresent(history.excludedCount) && history.excludedCount > 0 ? (
        <> {history.excludedCount} could not contribute.</>
      ) : null}
      {isPresent(dropped) && dropped > 0 ? (
        <>
          {' '}
          {dropped} older report(s) fell outside the most recent{' '}
          {history.cap} and were not included.
        </>
      ) : null}
    </p>
  );
}

/*
 * `rowHeading` and `TrendRow` STOOD HERE AND ARE DELETED.
 *
 * They built the `Parameter / Direction / First -> latest / Readings` table
 * that sat under the charts on this card. Every one of the nine features that
 * has a chart was already showing the same direction word and the same
 * refusal sentence in the chart above its row, so the table was a second copy
 * of the page. The reader asked for it to go.
 *
 * `rowHeading` existed only because that table once printed `trend.feature`
 * raw and leaked `hba1c` and `smoking_history` onto a patient's screen. The
 * chart headings use `PATIENT_LABEL` directly and always did, so the fix is
 * not lost with the function -- there is simply no raw key left to print.
 *
 * ONE COLUMN OF IT CAME BACK, AND ONLY ONE: `First -> latest`. Losing the
 * table took the numbers off the shut row with it, so a reader scanning the
 * closed list saw "worsening" and had to open a panel to learn from what to
 * what. `ChangePair` below puts that back where it was asked for.
 */

/**
 * THE TWO READINGS A MOVEMENT OR DIRECTION WORD IS ABOUT.
 *
 * ==========================================================================
 * IT SELECTS NOTHING AND COMPUTES NOTHING
 * ==========================================================================
 *
 * Both callers hand over values the SERVICE paired: Module 28's own
 * `change.first_value` / `change.last_value` for an assessed feature, and
 * `labSeriesService`'s `movementFrom` / `movementTo` for a laboratory one --
 * the latter added for this. Reading `points[0]` and the last point would
 * give the same two numbers today, and would be a second copy of the rule
 * deciding WHICH readings the word beside them describes. One copy means the
 * word and the pair cannot come to disagree.
 *
 * ABSENT MEANS NOTHING IS DRAWN, not a dash and not a zero. A pair is shown
 * only where a change was established: a blocked series gets none, because
 * two units have not been shown to have moved, and a single reading gets none
 * because there is no pair to show. Both of those already render their
 * numbers in full when opened.
 */
function ChangePair({ from, to, unit }) {
  if (!isPresent(from) || !isPresent(to)) return null;
  return (
    <span className="disclosure__pair">
      {/* THE UNIT ONCE, AT THE END. `2.6 -> 3.03 Lakhs/cumm`, not the unit
          twice -- printing it on both ends made the longest rows wrap.
          PRINTING IT ONCE ASSERTS THAT BOTH READINGS ARE IN IT, and that
          holds wherever this renders: for a laboratory series `blocked` is
          exactly the test that the units agree, and a blocked series is given
          no pair at all, so the one case where the assertion would be false
          renders nothing. For an assessed feature the values are Module 28's
          own, already converted to the `canonical_unit` named here. */}
      <Value value={from} />
      {' → '}
      <Value value={to} unit={unit} />
    </span>
  );
}

/**
 * Outcomes that mean "this is not a quantity with a trajectory" at all.
 *
 * FOUND BY LOOKING AT A REAL PAYLOAD, not by reading the schema. `age` comes
 * back NOT_TRENDABLE with two perfectly good points, and a chart drawn from
 * those points is a line -- on the live data, age descending from 58 to 34,
 * because the two synthetic reports carry different patients. A picture of a
 * trend beside a sentence refusing to describe one is the chart disagreeing
 * with the words next to it, which is the thing these components exist to
 * prevent. `gender` is the same shape from the other end: NOT_NUMERIC, no
 * readings at all, and an axis with nothing on it is not a chart.
 */
const NOT_A_TRAJECTORY = new Set(['NOT_TRENDABLE', 'NOT_NUMERIC']);

/**
 * Module 28's payload, turned into the chart's already-derived props.
 *
 * EVERY DECISION HERE IS THE SERVICE'S, REPEATED. `classified` is its
 * `outcome`, the band is its own declared optimal range, and each gap keeps
 * the availability code Module 7 gave it. Nothing is inferred, and in
 * particular nothing absent acquires a number on the way through.
 */
function chartPropsFor(trend) {
  const polarity = trend.polarity || {};
  // The service's own declared optimal range, handed over as it stands.
  //
  // THE "BOTH ENDS OR NO BAND" RULE LIVES IN THE CHART, NOT HERE. A one-sided
  // optimum (cholesterol declares a floor and no ceiling) drawn as a band
  // would run to the edge of the frame and assert a ceiling nobody declared --
  // and that rule belongs at the layer that cannot be bypassed, in one place,
  // where one mutation can kill it. A second copy here changes nothing
  // observable, which is exactly what makes it a comment pretending to be a
  // guarantee.
  const band = { low: polarity.optimal_low, high: polarity.optimal_high };

  return {
    // The reader's name for it, never the canonical key. `blood_glucose` and
    // `vitamin_b12` are how this platform stores a feature, not how a patient
    // says it, and nine chart headings is nine places to say it wrong.
    label: PATIENT_LABEL[trend.feature] || trend.feature,
    unit: trend.canonical_unit,
    points: (trend.points || []).map((point) => ({
      date: point.date,
      value: point.value,
      unit: point.unit,
      questionable: point.questionable === true,
    })),
    // A gap has no `value` field in the payload and is given none here.
    gaps: (trend.gaps || []).map((gap) => ({
      date: gap.date,
      kind: gap.availability,
      reason: gap.reason,
    })),
    band,
    classified: trend.outcome === 'TREND_CLASSIFIED',
    trend: trend.trend,
    // WHAT WOULD HAVE COUNTED AS A CHANGE, so the chart can be drawn at a
    // scale where "stable" looks stable. The numbers are the service's own
    // (`significant_change_pct`, `min_absolute_change`); nothing is derived
    // here beyond passing them along with the value they are measured from.
    stability: trend.stability || null,
    baseline: trend.change ? trend.change.first_value : null,
  };
}

/** A reading's date, or an honest word when there is not one. */
function readingDate(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString() : 'undated';
}

/**
 * The laboratory's own repeated parameters, AS PANELS IN THE SAME LIST.
 *
 * ==========================================================================
 * WHY THESE ARE NOT A SEPARATE SECTION ANY MORE
 * ==========================================================================
 *
 * They were, under a heading naming them as tests this tool does not assess,
 * above three paragraphs explaining that nothing here is interpreted, that the
 * scale includes the printed reference range, and that no range is drawn. The
 * reader asked for all of it to go and for these to sit with the rest.
 *
 * THE CONTROLS SURVIVE; THE PROSE DOES NOT. That is 6at's lesson, third time:
 * every objection to this page's commentary was right, and every control it
 * described belonged somewhere other than in a paragraph. So --
 *
 *   - NO DIRECTION IS EMITTED FOR THESE, and that is enforced where it cannot
 *     be bypassed: `labSeriesService` never produces one, because there is no
 *     polarity and no stability band for these parameters. It was never the
 *     removed sentence that made it true.
 *   - NO REFERENCE RANGE IS DRAWN. `scaleOnly` enters the chart's domain and
 *     no band rectangle, which is a property of `TrendChart` and a test, not
 *     of the paragraph that used to describe it.
 *   - TWO UNITS ARE STILL NEVER JOINED. `TrendChart` refuses to plot mixed
 *     units and says so on the chart itself, where the question is asked.
 *
 * A panel with no direction badge asserts nothing. That is the difference
 * between removing a claim and removing an explanation of one.
 */
/**
 * THE STATUS ON A PANEL THIS PLATFORM DOES NOT ASSESS.
 *
 * ==========================================================================
 * WHY IT IS NOT improving / worsening / stable
 * ==========================================================================
 *
 * A reader asked why these panels carry no status when the assessed ones do.
 * The answer is that all three of those words need something no part of this
 * pipeline has for an unassessed test:
 *
 *   - `improving` / `worsening` need POLARITY. Whether a rising ESR is better
 *     or worse for this person is a clinical fact nothing here knows, and
 *     Module 28 itself refuses to say it (CLINICAL_DIRECTION_UNKNOWN) rather
 *     than guess.
 *   - `stable` needs a STABILITY BAND. Without one, a 7 % move called
 *     "stable" states something nobody measured -- the hazard this whole file
 *     header is about.
 *
 * SO TWO TRUE STATUSES ARE SHOWN INSTEAD, and between them they answer what
 * the reader was actually asking:
 *
 *   1. WHICH WAY THE NUMBERS WENT -- `rose`, `fell`, `same`. Arithmetic on
 *      their own two readings, claiming nothing about what it means. It takes
 *      NO COLOUR, because green and rust on this page mean better and worse
 *      and that is exactly the judgement not being made.
 *   2. THE LABORATORY'S OWN MARKING of the latest reading -- `High`, `Low`,
 *      `In range`. Not this platform's verdict; the laboratory compared the
 *      value to its own printed interval and said so. Same three words and
 *      the same wording the dashboard uses for the same fact, so the two
 *      screens cannot disagree.
 *
 * A LABORATORY THAT MARKED NOTHING GETS NO CHIP. `null` is "not checked",
 * which is not "In range" -- and on a page about absences, letting the second
 * stand in for the first is the failure mode this project is named for.
 */
const MOVEMENT_WORD = { rose: 'rose', fell: 'fell', same: 'no change' };
const LAB_FLAG_WORD = { high: 'High', low: 'Low', critical: 'High', normal: 'In range' };

const TREND_WORDS = ['improving', 'worsening', 'stable'];

function LabStatus({ movement, latestFlag, trend, classified }) {
  // BOTH HALVES, the same predicate the assessed panels use. A payload
  // carrying a direction without a classification is a contradiction, and if
  // one ever arrives the unclassified reading wins -- §6z rendered the string
  // "null" as a direction once on exactly this mistake.
  const declared = classified === true && TREND_WORDS.includes(trend);

  // THE CLINICAL WORD REPLACES THE ARITHMETIC ONE, never sits beside it.
  // "rose" and "worsening" in one row are two answers to one question, and a
  // reader would reasonably read them as two findings.
  const moved = declared ? null : movement ? MOVEMENT_WORD[movement] : null;
  const flag = latestFlag ? LAB_FLAG_WORD[latestFlag] : null;
  if (!declared && !moved && !flag) return null;

  return (
    <span className="lab-status">
      {declared ? <span className={`trend trend--${trend}`}>{trend}</span> : null}
      {moved ? <span className="lab-status__move">{moved}</span> : null}
      {flag ? (
        // ATTRIBUTED IN THE MARKUP, not only in a comment. A reader hovering,
        // and a screen reader, are told whose judgement this is; the visible
        // chip stays short enough to sit in a row of them.
        <span
          className={`lab-status__flag lab-status__flag--${latestFlag}`}
          title="Your laboratory's own marking, from the range printed on that report"
        >
          {flag}
        </span>
      ) : null}
    </span>
  );
}

function LabPanels({ data }) {
  const series = data?.series || [];
  const readings = data?.readings || [];
  if (!series.length && !readings.length) return null;

  // ONE LIST, TWO KINDS OF PANEL, and the kind is decided by whether a line
  // can honestly be drawn -- not by which array the parameter arrived in.
  //
  // A BLOCKED SERIES IS LISTED, NOT CHARTED. Its two reports printed different
  // units, so there is no axis that can carry both; but the readings are the
  // laboratory's and withholding them would lose the numbers to a presentation
  // rule. They are shown exactly as a one-report reading is.
  const panels = [
    ...series.map((entry) =>
      entry.blocked
        ? {
            key: entry.key,
            name: entry.name,
            rows: entry.points.map((p) => ({
              date: p.date,
              valueRaw: p.value,
              unit: p.unit,
            })),
            // No movement for a blocked series -- the service withholds it,
            // because two units have not been shown to have moved at all.
            movement: entry.movement,
            latestFlag: entry.latestFlag,
          }
        : {
            key: entry.key,
            name: entry.name,
            chart: entry,
            movement: entry.movement,
            latestFlag: entry.latestFlag,
            trend: entry.trend,
            classified: entry.classified,
          }
    ),
    // A reading that cannot be trended is still a reading: one report, or a
    // result that is not a number. No chart, because one point is not a line.
    // It has no movement either -- but the laboratory may still have marked
    // it, and that marking is the one status it can carry.
    ...readings.map((entry) => ({
      key: entry.key,
      name: entry.name,
      rows: entry.rows,
      movement: null,
      latestFlag: entry.latestFlag,
    })),
  ];

  return (
    <>
      {panels.map((panel) => (
        <details className="trend-chart__block disclosure" key={`lab-${panel.key}`}>
          <summary className="disclosure__summary">
            <h3 className="trend-chart__title">{panel.name}</h3>
            <span className="disclosure__spacer" />
            {/* READ OFF THE SERIES, so the pair exists exactly where a line
                was drawn. A blocked panel and a single reading have no
                `chart` and therefore no pair -- the first because its two
                units were never shown to be comparable, the second because
                one reading is not a change. Both print their numbers in full
                on opening. */}
            <ChangePair
              from={panel.chart?.movementFrom}
              to={panel.chart?.movementTo}
              unit={panel.chart?.unit}
            />
            <LabStatus
              movement={panel.movement}
              latestFlag={panel.latestFlag}
              trend={panel.trend}
              classified={panel.classified}
            />
            <span className="disclosure__chevron" aria-hidden="true" />
          </summary>
          {panel.chart ? (
            <TrendChart
              label={panel.chart.name}
              unit={panel.chart.unit}
              points={panel.chart.points.map((p) => ({
                date: p.date,
                value: p.value,
                unit: p.unit,
              }))}
              // THE SCALE ONLY. Never `band` -- that prop is this platform's
              // own declared optimal range and is drawn as a rectangle, and
              // these numbers belong to the laboratory, not to us.
              scaleOnly={panel.chart.referenceScale}
            />
          ) : (
            <p className="trend-chart__readings">
              {panel.rows
                .map(
                  (r) =>
                    `${r.valueRaw ?? ''}${r.unit ? ` ${r.unit}` : ''} (${readingDate(r.date)})`
                )
                .join(' · ')}
            </p>
          )}
        </details>
      ))}
    </>
  );
}

function Trends({ data, history, labSeries }) {
  const features = data?.features ? Object.values(data.features) : [];
  const summary = data?.summary;
  const hasLab = Boolean(
    (labSeries?.series || []).length || (labSeries?.readings || []).length
  );

  // WHAT THIS CARD CAN ACTUALLY DRAW, DECIDED ONCE.
  //
  // Two kinds of feature produce no chart: one that is not a quantity with a
  // trajectory at all (`age`, `sex`), and one with no reading to place. Both
  // used to keep a row in a table below this list, and that table carried the
  // service's own sentence saying why.
  //
  // THAT TABLE IS GONE. It printed the same direction word and the same
  // refusal sentence already shown on every chart above it, for the nine
  // features that have a chart -- the reader asked for the repetition to go.
  // The three that had no chart (`age`, `sex`, `smoking_history`) are profile
  // answers rather than laboratory results, and they still appear in the
  // comparison table further down this page.
  //
  // THE PREDICATE LIVES HERE AND NOWHERE ELSE. The empty line at the bottom
  // of this card depends on it too, and it used to hang off `features.length`
  // -- which was safe only while a table printed a row per feature. A payload
  // carrying nothing but unchartable features would now leave this card
  // completely blank, saying neither a trend nor why there is none. A second
  // copy of the test is how the two come to disagree.
  const charted = features.filter(
    (trend) =>
      !NOT_A_TRAJECTORY.has(trend.outcome) && (trend.points || []).length > 0
  );

  return (
    <section className="card">
      <h2>Trends over time</h2>
      <HistorySummary history={history} />

      {summary ? (
        <p className="hint">
          {summary.improving} improving · {summary.worsening} worsening ·{' '}
          {summary.stable} stable · {summary.not_determinable} not determinable
        </p>
      ) : null}

      {/* THE CHARTS ARE THE RECORD NOW. Each one carries the direction word,
          the service's own refusal sentence when there is no direction, and
          the thing a table could never show -- where the line STOPS. The
          table that used to repeat the first two is gone; see `charted`. */}
      {charted.map((trend) => {
        const props = chartPropsFor(trend);
        // CLOSED BY DEFAULT, AND THE SUMMARY CARRIES THE FINDING.
        //
        // Nine charts at ~200px each were most of this page. Collapsing them
        // is only safe because the summary states the DIRECTION -- improving,
        // stable, or the service's own refusal -- so a reader scanning the
        // shut list learns the same thing the open list told them, and opens
        // only the one they want to look at.
        //
        // The direction word comes from the same `classified && trend`
        // predicate the table uses, NOT from `trend.trend` alone: a payload
        // carrying a direction without a classification must not be summarised
        // as though it had one (MEMORY 6z -- that contradiction printed the
        // string "null" as a direction once already).
        const declared = trend.outcome === 'TREND_CLASSIFIED' && isPresent(trend.trend);
        return (
          <details
            className="trend-chart__block disclosure"
            key={`chart-${trend.feature}`}
          >
            <summary className="disclosure__summary">
              <h3 className="trend-chart__title">{props.label}</h3>
              {/* Module 28's OWN pair. Absent on a feature with one usable
                  reading, which is the same feature that gets no line. */}
              <ChangePair
                from={trend.change?.first_value}
                to={trend.change?.last_value}
                unit={trend.canonical_unit}
              />
              {declared ? (
                <span className={`trend trend--${trend.trend}`}>{trend.trend}</span>
              ) : (
                <span className="trend-chart__nodirection">no direction</span>
              )}
              <span className="disclosure__chevron" aria-hidden="true" />
            </summary>
            {/* WHY THERE IS NO DIRECTION, ON THE CHART ITSELF.
                The service's own sentence was already in the payload and was
                already shown -- in the TABLE, further down the page. So a
                reader looking at the picture saw a line climbing from 88 to
                168 under the words "no direction" and had nothing to
                reconcile the two with until they scrolled.
                On this account that chart is four glucose readings of which
                the first two are FASTING and the last two RANDOM: the climb
                is mostly the change of test, not a change in the reader. The
                refusal is right and it was the only thing on screen that was
                not explained. */}
            {/* ALSO WHEN THE TREND IS "STABLE", which is the other case
                where the words and the picture can disagree. "Stable" does
                not mean the line is flat -- it means the movement is inside
                the band where this test's own variation lives. Cholesterol
                186 -> 172 is -7.53 % against a 17 % band: a real fall, and
                smaller than the noise. Without the sentence the reader sees a
                steep line labelled "stable" and has nothing to reconcile
                them with. */}
            {(!declared || trend.trend === 'stable') && isPresent(trend.reason) ? (
              <p className="trend-chart__why">{trend.reason}</p>
            ) : null}
            <TrendChart {...props} />
          </details>
        );
      })}

      {/* THE SAME LIST, NOT A SECOND ONE. See LabPanels. */}
      <LabPanels data={labSeries} />

      {charted.length || hasLab ? null : (
        // Only when there is genuinely nothing on this card. The charts and
        // panels above are parameters that WERE followed, so printing this
        // beside them would be the page contradicting itself.
        <p className="empty">
          No parameters could be followed across your reports yet.
        </p>
      )}

      {data?.disclaimer ? <p className="hint">{data.disclaimer}</p> : null}
    </section>
  );
}


/** A report, named the way the person who uploaded it would recognise it. */
function reportLabel(entry, namesById) {
  const date = entry.chronoDate ? new Date(entry.chronoDate) : null;
  const when =
    date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString() : 'undated';
  const name = namesById.get(entry.reportId);
  return name ? `${when} — ${name}` : when;
}

/**
 * Choose which two reports to compare.
 *
 * THE DEFAULT IS THE SERVICE'S OWN CHOICE, not this component's. With nothing
 * selected the endpoints are called with no pair and answer
 * `selection: "first_vs_latest"`; the selects are then filled FROM the pair
 * that came back, so the control always shows the comparison actually on
 * screen rather than a guess that could disagree with it.
 *
 * BOTH SELECTS CHANGE BOTH SECTIONS. The progress score is computed from the
 * same two reports as the table, and a score describing one pair beside a
 * table describing another is two answers to different questions presented as
 * one screen.
 *
 * Out-of-order choices are allowed on purpose: comparing a later report
 * against an earlier one is a real question, Module 29 reports
 * `chronological: false` for it, and the sentence under the table already
 * says every direction is reversed. What is NOT allowed is comparing a report
 * with itself, which is not a comparison; that option is left out of the
 * second list rather than refused after the fact.
 */
function PairPicker({ reports, namesById, pair, onChange, busy }) {
  if (!reports || reports.length < 2) return null;

  const baseline = pair?.baseline || '';
  const comparison = pair?.comparison || '';

  const choose = (which) => (event) => {
    const chosen = event.target.value;

    // PICKING THE OTHER SIDE'S REPORT MEANS SWAP, NOT NOTHING.
    //
    // On an account with two reports, choosing the other one as the baseline
    // necessarily equals the current comparison. Refusing that leaves a
    // control that visibly does nothing when clicked -- which is what the
    // first version did, and it is worse than no control. A reader who names
    // the later report as the baseline is asking for the comparison the other
    // way round, which Module 29 supports and reports as
    // `chronological: false`, and the sentence under the table already
    // explains that every direction is reversed.
    // ONLY THE FIRST SELECT CAN COLLIDE, because the second list excludes the
    // current baseline and therefore cannot offer it. A branch handling the
    // other direction would be unreachable, and an unreachable branch is one
    // nobody can find out is wrong.
    const next =
      which === 'baseline'
        ? chosen === comparison
          // Swap. On an account with two reports this is the only change
          // available, and refusing it left a control that visibly did nothing
          // when clicked. Naming the later report as the baseline asks for the
          // comparison the other way round -- supported, reported by Module 29
          // as `chronological: false`, and already explained under the table.
          ? { baseline: chosen, comparison: baseline }
          : { baseline: chosen, comparison }
        : { baseline, comparison: chosen };

    // A half-made choice is never sent: the backend refuses one of the pair
    // rather than guessing the other, so it would become an error message
    // under a table the reader was in the middle of changing.
    if (next.baseline && next.comparison && next.baseline !== next.comparison) {
      onChange(next);
    }
  };

  return (
    <div className="pair-picker">
      <label>
        <span className="pair-picker__label">Compare</span>
        <select value={baseline} onChange={choose('baseline')} disabled={busy}>
          {reports.map((entry) => (
            <option key={entry.reportId} value={entry.reportId}>
              {reportLabel(entry, namesById)}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="pair-picker__label">with</span>
        <select value={comparison} onChange={choose('comparison')} disabled={busy}>
          {reports
            .filter((entry) => entry.reportId !== baseline)
            .map((entry) => (
              <option key={entry.reportId} value={entry.reportId}>
                {reportLabel(entry, namesById)}
              </option>
            ))}
        </select>
      </label>
      {busy ? <span className="hint">Comparing…</span> : null}
    </div>
  );
}

/** The spec's Parameter / Previous / Current / Trend table. */
function Comparison({ data, reports, namesById, pair, onPairChange, busy }) {
  const rows = data?.table || [];

  return (
    <section className="card">
      <h2>Comparing two reports</h2>

      <PairPicker
        reports={reports}
        namesById={namesById}
        pair={pair}
        onChange={onPairChange}
        busy={busy}
      />

      {data?.pair ? (
        <p className="hint">
          Comparing the report of{' '}
          {new Date(data.pair.baseline_date || data.pair.baseline?.date).toLocaleDateString()}{' '}
          with {new Date(data.pair.comparison_date || data.pair.comparison?.date).toLocaleDateString()}
          {/* The full stop belongs to whichever ending is used. Both were
              printed before, giving "…is reversed.." -- invisible until the
              picker made an out-of-order comparison reachable at all. */}
          {data.pair.chronological === false
            ? ' — these were given out of date order, so the direction of every change is reversed.'
            : '.'}
        </p>
      ) : null}

      {rows.length ? (
        <table className="lab-table">
          <thead>
            <tr>
              <th scope="col">Parameter</th>
              <th scope="col">Previous</th>
              <th scope="col">Current</th>
              <th scope="col">Change</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.feature}>
                <th scope="row">{row.description || row.feature}</th>
                <td>
                  <Value
                    value={row.previous}
                    unit={row.unit}
                    reason="This parameter was not on the earlier report."
                  />
                </td>
                <td>
                  <Value
                    value={row.current}
                    unit={row.unit}
                    reason="This parameter was not on the later report."
                  />
                </td>
                <td>
                  {isPresent(row.category) ? (
                    <span className={`category category--${row.category}`}>
                      {isPresent(row.symbol) ? `${row.symbol} ` : ''}
                      {row.category.replace(/_/g, ' ')}
                    </span>
                  ) : (
                    <Absent
                      label="Not classifiable"
                      reason="This parameter could not be compared across the two reports."
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">Nothing could be compared between these reports.</p>
      )}

      {data?.summary?.headline ? <p>{data.summary.headline}</p> : null}
      {data?.warnings?.length ? (
        <WarningList warnings={data.warnings} />
      ) : null}
    </section>
  );
}

/**
 * The 0-100 progress scale, with the score marked on it.
 *
 * A bare "62.5 / 100" makes a reader do the work of placing it. The scale is
 * the one thing on this card that is genuinely about THIS score and cannot be
 * said in fewer words.
 *
 * NEVER A RISK COLOUR. The card states in its own words that this is "not a
 * health score, not a risk score and not a diagnosis" -- painting the marker
 * green at 80 and rust at 20 would contradict that sentence from two inches
 * away, which is the fault every chart in this app is built to avoid. The
 * marker is `--brand`, the neutral accent, exactly as the percentile bar is.
 *
 * NO BAND BOUNDARIES ARE DRAWN. Module 30 puts them at 20/40/60/80, and four
 * gridlines would invite a reader to treat the nearest one as a threshold --
 * the bands are labels for reading the number, not cut-offs that mean
 * anything clinically. The band's WORDS are printed above; the picture just
 * places the number.
 */
function ScoreScale({ score }) {
  const value = Number(score);
  // Absence is not a guess, and neither is a number off the declared scale.
  if (!Number.isFinite(value) || value < 0 || value > 100) return null;
  const x = 10 + (value / 100) * 240;
  return (
    <svg
      className="scorescale"
      viewBox="0 0 260 22"
      width="260"
      height="22"
      role="img"
      aria-label={`${value} out of 100 on this scale.`}
    >
      <title>{`${value} out of 100 on this scale.`}</title>
      <line
        x1="10"
        y1="11"
        x2="250"
        y2="11"
        stroke="var(--track)"
        strokeWidth="8"
        strokeLinecap="round"
      />
      <circle className="scorescale__mark" cx={x} cy="11" r="6" fill="var(--brand)" />
    </svg>
  );
}

/** Module 30. A refusal here is `score: null`, and it is shown as one. */
function Progress({ data, alreadyWarned }) {
  const computed = data?.outcome === 'SCORE_COMPUTED';
  const seen = new Set(alreadyWarned || []);
  const ownWarnings = (data?.warnings || []).filter((w) => !seen.has(w));

  return (
    <section className="card">
      <h2>Progress score</h2>

      {computed && isPresent(data.score) ? (
        <>
          <p className="progress__score">
            <strong>{data.score}</strong>
            <span className="hint"> / 100</span>
          </p>
          <ScoreScale score={data.score} />
          {/* THE BAND DESCRIPTION IS NOT RENDERED, and that is a rendering
              call rather than an edit to the service.
              It restates its own label in this platform's vocabulary: under
              "More favourable movement than unfavourable" it printed "Across
              the parameters that could be assessed, more of the movement was
              in the direction recorded as favourable than in the direction
              recorded as unfavourable." That is the label again, longer. The
              field is untouched on the API for any other consumer; it is the
              SECOND sentence on this card that was the problem, not the
              existence of the sentence. */}
          {data.band ? (
            <p className="progress__band">
              <strong>{data.band.label}</strong>
            </p>
          ) : null}
          {/* "Higher is better." WAS PRINTED HERE AS A LITERAL, immediately
              in front of `direction_text`, which itself opened "The scale
              runs from 0 to 100 and HIGHER IS BETTER". The card said it
              twice in one breath. The service's sentence now carries it
              once, in plain words, and this line adds nothing to it. */}
          {data.scale?.direction_text ? (
            <p className="progress__meaning">{data.scale.direction_text}</p>
          ) : null}
        </>
      ) : (
        // No score is a real answer, and the reason is the service's own.
        <Absent
          label="No score"
          reason={
            data?.summary?.headline ||
            'There was not enough comparable data to calculate a progress score.'
          }
        />
      )}

      {/* COVERAGE IS AN ABSENCE STATEMENT, so it stays on the card and in
          plain words. "parameter(s)" is a placeholder printed at a reader;
          the counts decide the wording. The floor is only worth mentioning
          when it is the reason there is no score -- quoting "at least 3 are
          needed" under a score built from 8 answers a question nobody asked.
          The counts are the service's, verbatim. */}
      {data?.coverage ? (
        <p className="progress__coverage">
          Worked out from {data.coverage.contributing_count} of your{' '}
          {data.coverage.features_examined} results.
          {data.coverage.excluded_count > 0
            ? ` The other ${data.coverage.excluded_count} could not be
               compared this way, so ${
                 data.coverage.excluded_count === 1 ? 'it is' : 'they are'
               } not in the number.`.replace(/\s+/g, ' ')
            : ''}
          {!computed
            ? ` At least ${data.coverage.minimum_required} are needed before a score is shown.`
            : ''}
        </p>
      ) : null}

      {/* MODULE 30 INHERITS MODULE 29'S WARNINGS, so the intermediate-report
          sentence arrived on BOTH cards and printed twice on one screen --
          measured in the live DOM, not guessed. Only the ones this card adds
          are shown.
          FILTERED BY EXACT TEXT against what the comparison card actually
          rendered, never by index or by position: a warning that exists only
          on the progress payload must still appear, and one the reader has
          already read two inches higher must not. Nothing is dropped from the
          API. */}
      {ownWarnings.length ? <WarningList warnings={ownWarnings} /> : null}

      {data?.what_this_is_not ? (
        <p className="hint">{data.what_this_is_not}</p>
      ) : null}
    </section>
  );
}

export default function Timeline() {
  const [state, setState] = useState({ loading: true });
  // `null` means "whatever the service chooses", which is first vs latest.
  // A pair is only ever set from a reader's explicit choice.
  const [pair, setPair] = useState(null);
  const [busy, setBusy] = useState(false);
  const [names, setNames] = useState(new Map());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Independent calls: one failing must not blank the others. The report
        // list is only for LABELLING the picker, so its failure costs the
        // names and nothing else.
        const [trends, comparison, progress, reports] = await Promise.allSettled([
          api.getTrends(),
          api.getComparison(),
          api.getProgress(),
          api.listReports(),
        ]);
        if (cancelled) return;
        if (reports.status === 'fulfilled') {
          const list = reports.value?.reports || reports.value?.items || [];
          setNames(new Map(list.map((r) => [r.id, r.originalName])));
        }
        setState({
          loading: false,
          trends: trends.status === 'fulfilled' ? trends.value : null,
          trendsError: trends.status === 'rejected' ? trends.reason.message : null,
          comparison: comparison.status === 'fulfilled' ? comparison.value : null,
          comparisonError:
            comparison.status === 'rejected' ? comparison.reason.message : null,
          progress: progress.status === 'fulfilled' ? progress.value : null,
          progressError: progress.status === 'rejected' ? progress.reason.message : null,
        });
      } catch (err) {
        if (!cancelled) setState({ loading: false, error: err.message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Re-ask BOTH questions about the newly chosen pair.
   *
   * The trends section is deliberately not refetched: it describes every
   * report on the account, not the two being compared, and re-running it would
   * redraw an unrelated section under the reader's hands.
   *
   * THE OLD ANSWERS ARE CLEARED BEFORE THE NEW ONES ARRIVE. Leaving the
   * previous table on screen under a changed picker states that those numbers
   * are the comparison the control now names, which they are not.
   */
  const choosePair = async (next) => {
    setPair(next);
    setBusy(true);
    setState((current) => ({
      ...current,
      comparison: null,
      comparisonError: null,
      progress: null,
      progressError: null,
    }));
    const [comparison, progress] = await Promise.allSettled([
      api.getComparison(next),
      api.getProgress(next),
    ]);
    setBusy(false);
    setState((current) => ({
      ...current,
      comparison: comparison.status === 'fulfilled' ? comparison.value : null,
      comparisonError:
        comparison.status === 'rejected' ? comparison.reason.message : null,
      progress: progress.status === 'fulfilled' ? progress.value : null,
      progressError: progress.status === 'rejected' ? progress.reason.message : null,
    }));
  };

  if (state.loading) return <p className="loading">Loading your timeline…</p>;
  if (state.error) return <p className="error" role="alert">{state.error}</p>;

  return (
    <main className="timeline">
      <h1>Your timeline</h1>
      <p className="hint">
        These views describe how measured values changed between your reports.
        They report arithmetic and a declared direction of change &mdash; they
        do not interpret those changes or identify any condition.
      </p>

      {state.trendsError ? (
        <p className="error" role="alert">{state.trendsError}</p>
      ) : (
        <>
          <Trends
            data={state.trends?.trends}
            history={state.trends?.history}
            labSeries={state.trends?.labSeries}
          />
        </>
      )}

      {state.comparisonError ? (
        <p className="error" role="alert">{state.comparisonError}</p>
      ) : (
        <Comparison
          data={state.comparison?.comparison}
          reports={state.comparison?.history?.reports || state.trends?.history?.reports}
          namesById={names}
          /* THE PAIR ON SCREEN, not the one requested. With no explicit choice
             the service picks first-vs-latest, and seeding the selects from
             its answer means the control can never describe a comparison the
             table is not showing. */
          pair={
            pair || {
              baseline: state.comparison?.comparison?.pair?.baseline_report_id,
              comparison: state.comparison?.comparison?.pair?.comparison_report_id,
            }
          }
          onPairChange={choosePair}
          busy={busy}
        />
      )}

      {state.progressError ? (
        <p className="error" role="alert">{state.progressError}</p>
      ) : (
        <Progress
          data={state.progress?.progress}
          alreadyWarned={state.comparison?.comparison?.warnings}
        />
      )}
    </main>
  );
}
