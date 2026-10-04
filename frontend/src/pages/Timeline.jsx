import { useEffect, useRef, useState } from 'react';
import Icon from '../components/Icon';
import { api } from '../lib/api';
import { Absent, Value, WarningList } from '../components/Absent';
import TrendChart from '../components/TrendChart';
import { PATIENT_LABEL } from '../lib/labels';
import { isPresent } from '../lib/absence';
import { reportDateInfo } from '../lib/reportDates';
import { PairIdentityNotice } from '../components/IdentityNotice';
import { readableName } from '../lib/displayName';

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
  // SOMEONE ELSE's REPORTS ARE SAID APART (2026-10-03). They were left out on
  // purpose -- another person's values are not changes in the reader -- which
  // is a different fact from "could not contribute".
  const someoneElse = (history.excluded || []).filter((r) => r?.reasonCode === 'SOMEONE_ELSE').length;
  const otherExcluded = isPresent(history.excludedCount)
    ? Math.max(0, history.excludedCount - someoneElse)
    : null;

  return (
    <p className="history">
      Built from <strong>{history.included}</strong> of{' '}
      <strong>{history.considered}</strong> report(s).
      {someoneElse > 0 ? (
        <>
          {' '}
          {someoneElse} report{someoneElse === 1 ? ' is' : 's are'} marked as someone
          else&rsquo;s and {someoneElse === 1 ? 'is' : 'are'} not included.
        </>
      ) : null}
      {otherExcluded ? <> {otherExcluded} could not contribute.</> : null}
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
 * THE SHORT REASON ON A SHUT ROW THAT HAS NO DIRECTION (2026-10-02).
 *
 * Every such row said "no direction", whether the test was on one report
 * only, or on both but taken fasting once and random once. Those are
 * different facts, and the shut list is where a reader scans; the full
 * sentence is still inside the row. Branches on `outcome`, never on `trend`.
 */
function noDirectionWord(trend) {
  if (trend.outcome === 'NOT_COMPARABLE_SAMPLE_TIMING') {
    const timings = [
      ...new Set((trend.points || []).map((p) => p.sample_timing).filter(isPresent)),
    ];
    return timings.length === 2 ? `${timings[0]} vs ${timings[1]}` : 'not comparable';
  }
  if (trend.outcome === 'INSUFFICIENT_DATA' && (trend.points || []).length === 1) {
    return 'one report only';
  }
  return 'no direction';
}

/**
 * THE PERSON, NOT THE BLOOD (2026-10-02). Age, sex and smoking describe who a
 * report is about, and the trends card already leaves them out. In the
 * comparison table they read as measurements: "Age 34 -> 20" between two
 * reports that may not be the same person, and "Not measured -- not on the
 * earlier report" for a sex the earlier report PRINTS (the service carries no
 * value for a word, only for a number). Whether the two reports are the same
 * person is said once, above the table, by `PairIdentityNotice`.
 */
const PERSON_DETAILS = new Set(['age', 'gender', 'smoking_history']);

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
 *   2. WHERE THE LATEST READING SAT against the interval printed on its report
 *      -- `High`, `Low`, `In range`. Not this platform's verdict; but not
 *      necessarily the laboratory's either, since a flag may have been read
 *      from the printed interval rather than a marking. Same three words and
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

/*
 * A PANEL WITH NO LINE GETS THE SAME KIND OF CHIP AS THE ROWS ABOVE IT
 * (owner, 2026-10-03). It used to show the latest reading's flag -- "High",
 * "In range" -- so the shut list mixed two kinds of fact: how a value moved
 * between reports, and where one value sat against one printed range. The
 * chip now says why there is no movement, in the words the assessed rows use;
 * the flag moved inside the panel (`PRINTED_RANGE_SENTENCE`).
 */
function noLineWord(panel) {
  if (panel.blocked) return 'units differ';
  if ((panel.rows || []).length === 1) return 'one report only';
  return 'not a number';
}

/* Where the reading sat against the range printed beside it. NO AGENT: the
   flag is set when the report marks it OR when the printed interval makes it
   plain, and the stored row cannot tell which (MEMORY.md section 0, item 5). */
const PRINTED_RANGE_SENTENCE = {
  high: 'Above the range printed on the report.',
  critical: 'Above the range printed on the report.',
  low: 'Below the range printed on the report.',
  normal: 'Within the range printed on the report.',
};

function LabStatus({ movement, latestFlag, trend, classified }) {
  // BOTH HALVES, and THE SAME FUNCTION THE CARD'S TALLY USES. A payload
  // carrying a direction without a classification is a contradiction, and if
  // one ever arrives the unclassified reading wins -- §6z rendered the string
  // "null" as a direction once on exactly this mistake.
  //
  // It was a second copy of that predicate until the tally needed it too, and
  // a count that decided "declared" differently from the chip beside it would
  // be the summary line's own defect all over again.
  const declared = panelTrendWord({ classified, trend }) !== null;

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
        // SAID IN THE MARKUP WHAT THE CHIP IS COMPARED WITH -- and, since
        // 2026-10-03, NOT WHO COMPARED IT. It read "Your laboratory's own
        // marking", but the flag is set when the report marks it OR when the
        // printed interval makes it plain, and the row cannot tell which
        // (MEMORY.md section 0, item 5); the clinician page and the shut-row
        // sentences already stopped naming an agent.
        <span
          className={`lab-status__flag lab-status__flag--${latestFlag}`}
          title="The latest reading against the range printed on that laboratory report"
        >
          {flag}
        </span>
      ) : null}
    </span>
  );
}

/**
 * The laboratory panels this card will render, as ONE list.
 *
 * SPLIT OUT OF `LabPanels` SO THE COUNT AND THE RENDER CANNOT DISAGREE.
 * The card's summary line has to say how many parameters are improving,
 * worsening and stable, and it was reading Module 28's own tally -- which
 * counts twelve assessed features and knows nothing about these. The only way
 * a count can be trusted is if it is taken from the same array that becomes
 * the panels, so this returns the array and both callers use it.
 */
function labPanelsOf(data) {
  const series = data?.series || [];
  const readings = data?.readings || [];

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
            blocked: true,
            latestFlag: entry.latestFlag,
            joinedFrom: entry.joinedFrom,
          }
        : {
            key: entry.key,
            name: entry.name,
            chart: entry,
            movement: entry.movement,
            latestFlag: entry.latestFlag,
            trend: entry.trend,
            classified: entry.classified,
            joinedFrom: entry.joinedFrom,
            unitEquivalence: entry.unitEquivalence,
            unitAssumed: entry.unitAssumed,
            significantChangePct: entry.significantChangePct,
            trendSource: entry.trendSource,
            trendVerified: entry.trendVerified,
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
      joinedFrom: entry.joinedFrom,
      // The assessed feature this row restates, when it does. See
      // `labRestatements.js` -- it is why the row carries no direction.
      restates: entry.restates,
    })),
  ];

  return panels;
}

/** The word a panel actually shows, or null when it shows none. */
function panelTrendWord(panel) {
  return panel && panel.classified === true && TREND_WORDS.includes(panel.trend)
    ? panel.trend
    : null;
}

/** The word an ASSESSED chart actually shows, or null. Module 28's predicate. */
function featureTrendWord(trend) {
  return trend &&
    trend.outcome === 'TREND_CLASSIFIED' &&
    isPresent(trend.trend) &&
    TREND_WORDS.includes(trend.trend)
    ? trend.trend
    : null;
}

/**
 * The card's own tally, over EVERY panel the card renders.
 *
 * ==========================================================================
 * IT REPLACES MODULE 28's SUMMARY, WHICH HAD STOPPED DESCRIBING THIS CARD
 * ==========================================================================
 *
 * The line read `3 improving · 1 worsening · 3 stable · 5 not determinable`
 * over a card showing twenty-six panels. Both halves were wrong:
 *
 *   - it counted Module 28's twelve ASSESSED features and none of the
 *     fourteen laboratory panels beside them, which now carry verdicts of
 *     their own from Module 35; and
 *   - three of the twelve it did count -- `age`, `sex`, `smoking_history` --
 *     are no longer rendered anywhere on the card, so `not determinable`
 *     included rows the reader cannot see.
 *
 * A COUNT THAT DOES NOT ADD UP TO WHAT IS ON THE SCREEN IS WORSE THAN NO
 * COUNT: a reader who tries to check it finds numbers that cannot be
 * reconciled with the rows in front of them, and stops trusting the ones that
 * are right. So the total is stated too, and it is the panel count -- the
 * four parts sum to it by construction.
 *
 * Module 28's `summary` is still the right answer to a different question
 * (how did the ASSESSED features do) and is untouched; it simply is not the
 * answer to "what is on this card".
 */
function cardTally(charted, labPanels) {
  const counts = { improving: 0, worsening: 0, stable: 0, undirected: 0 };
  const add = (word) => {
    if (word && counts[word] !== undefined) counts[word] += 1;
    else counts.undirected += 1;
  };
  for (const trend of charted) add(featureTrendWord(trend));
  for (const panel of labPanels) add(panelTrendWord(panel));
  return { ...counts, total: charted.length + labPanels.length };
}

/**
 * The one provenance sentence for the whole card, or null.
 *
 * WHY IT IS HERE AND NOT ON EACH PANEL. It used to be a second sentence
 * beside every threshold and every unit equivalence -- three possible
 * wordings, one of them two lines long, on as many as 26 panels. The reader
 * circled it and asked for it gone. A caveat repeated 26 times does not read
 * as 26 caveats; it reads as boilerplate, and it buries the number beside it.
 *
 * WHAT IS NOT DONE HERE: dropping the caveat. Not one row of the variation
 * table has been verified, so a page showing `62%` with nothing said would be
 * presenting a literature-typical figure as an established clinical
 * threshold. The distinction the panels used to draw is kept intact --
 * reviewed, unreviewed, or invented by a model from the test name.
 *
 * COMPUTED FROM THE PANELS THAT ACTUALLY RENDER, and gated on the same
 * `panelTrendWord(panel) && isPresent(...)` the threshold line uses, so it
 * cannot describe a figure no reader can see. A blanket sentence would go
 * stale the moment every row was verified; this one disappears by itself.
 */
function provenanceNote(labPanels) {
  let uncheckedTable = false;
  let fromModel = false;
  let uncheckedEquivalence = false;

  for (const panel of labPanels) {
    if (panelTrendWord(panel) && isPresent(panel.significantChangePct)) {
      // ABSENT PROVENANCE COUNTS AS THE MODEL, exactly as the panel sentence
      // treated it: an unknown source is not a checked one.
      if (panel.trendSource === 'table') {
        if (panel.trendVerified !== true) uncheckedTable = true;
      } else {
        fromModel = true;
      }
    }
    if (panel.unitEquivalence && !panel.unitEquivalence.verified) {
      uncheckedEquivalence = true;
    }
  }

  const unchecked = [];
  if (uncheckedTable || fromModel) unchecked.push('change thresholds');
  if (uncheckedEquivalence) unchecked.push('unit equivalences');
  if (!unchecked.length) return null;

  return (
    <>
      The {unchecked.join(' and ')} used here have not been checked against a
      published source.
      {fromModel
        ? ' Some were produced by a language model from the test name alone.'
        : ''}
    </>
  );
}

function LabPanels({ panels }) {
  if (!panels.length) return null;

  return (
    <>
      {panels.map((panel) => (
        <details className="trend-chart__block disclosure" key={`lab-${panel.key}`}>
          <summary className="disclosure__summary">
            <h3 className="trend-chart__title">{readableName(panel.name)}</h3>
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
            {panel.chart ? (
              <LabStatus
                movement={panel.movement}
                latestFlag={panel.latestFlag}
                trend={panel.trend}
                classified={panel.classified}
              />
            ) : (
              <span className="trend-chart__nodirection">{noLineWord(panel)}</span>
            )}
            <span className="disclosure__chevron" aria-hidden="true" />
          </summary>
          {/* WHICH NAMES WERE TREATED AS ONE TEST.
              A reader whose report says `Polymorphs` is looking at a panel
              headed `NEUTROPHILS`, and without this line that reads as a
              parameter they never had. It is also the only place the join is
              visible at all, and a join nobody can see is a page rewriting
              someone's report rather than regrouping it.
              INSIDE the panel, not on the shut row: the row already carries a
              name, a pair and two chips, and this is the answer to a question
              only a reader who noticed will ask. */}
          {/* WHERE THE "STABLE" THRESHOLD CAME FROM.
              A reader asked why a rise from 35 to 45 reads `stable`, and the
              answer is a threshold -- so the threshold is visible here.

              THE PROVENANCE SENTENCE THAT USED TO FOLLOW IT IS NOW SAID ONCE
              ON THE CARD, by `provenanceNote`, and the reason is the reader's
              own objection: three states meant three sentences, and one of
              them ran to two lines on EVERY ONE OF 26 PANELS. Repeating a
              caveat 26 times does not make it 26 times as true -- it makes
              the useful half (the number) harder to find, which is the
              opposite of what a disclosure is for.

              WHAT DID NOT CHANGE: the caveat is still on the page, still
              distinguishes a reviewed figure from an unreviewed one from a
              model-invented one, and still renders absent provenance as the
              most cautious of them. It is stated where it applies to
              everything below it instead of beside each number. */}
          {panelTrendWord(panel) && isPresent(panel.significantChangePct) ? (
            <p className="trend-chart__threshold">
              Counted as a change only past {panel.significantChangePct}%.
            </p>
          ) : null}
          {/* TWO UNIT LABELS TREATED AS ONE SCALE, AND ON WHOSE AUTHORITY.
              SGPT is printed U/L on one report and IU/L on the other; MCHC is
              g/dL and %. Those are the same scale and the readings are the
              same numbers -- but the reader is looking at two different
              labels on their own documents, and a line drawn between them
              without a word would be this page deciding something it has not
              said. `verified` is false on every declaration today, so the
              sentence says which it is rather than implying a review that
              has not happened. */}
          {/* THE SAME MEASUREMENT, ASSESSED UNDER ANOTHER NAME.
              This row is on the reader's report and stays on the page, but it
              is not trended: it restates a feature Module 28 assesses with a
              reviewed polarity and its own stability band. Trending it a
              second time gave one change two opposite verdicts -- HbA1c
              `worsening` beside AVERAGE BLOOD GLUCOSE `improving`. Naming
              where the real verdict is, is what stops this reading as a
              parameter that was ignored. */}
          {panel.restates ? (
            <p className="trend-chart__joined">
              This is the same measurement as{' '}
              {PATIENT_LABEL[panel.restates] || panel.restates}, which is
              assessed in its own right on this page — so it is shown here but
              not given a second direction of its own.
            </p>
          ) : null}
          {/* A UNIT THE READER'S OWN DOCUMENT DOES NOT CARRY.
              One of these reports printed no unit for this test -- checked in
              the stored extraction, not guessed -- and the reading is shown on
              the scale the other report names. The reader has to be told
              that, or the panel is putting a unit on their document that is
              not on it. */}
          {panel.unitAssumed ? (
            <p className="trend-chart__joined">
              One of your reports did not print a unit for this test. That
              reading is shown in {panel.unitAssumed.unit}, the unit your other
              report gives for it.
            </p>
          ) : null}
          {/* The "has this been checked" half of this sentence moved to the
              card for the same reason as the threshold above it. WHICH two
              labels were treated as one scale is specific to this panel and
              stays; whether anybody reviewed that convention is one fact
              about the whole card. */}
          {panel.unitEquivalence ? (
            <p className="trend-chart__joined">
              Your reports label this test two ways, both meaning{' '}
              {panel.unitEquivalence.label}, so the readings are shown on one
              scale.
            </p>
          ) : null}
          {Array.isArray(panel.joinedFrom) && panel.joinedFrom.length > 1 ? (
            <p className="trend-chart__joined">
              Your reports print this test under{' '}
              {panel.joinedFrom.length} names: {panel.joinedFrom.join(' · ')}. They
              are shown here as one test.
            </p>
          ) : null}
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
              // MODULE 35'S VERDICT, SO THE CHART AND ITS OWN ROW AGREE.
              //
              // FOUND BY READING THE SCREEN, not by a test. These were left
              // off because until Module 35 there was genuinely no direction
              // for an unassessed test, and the chart's spoken summary ended
              // "No direction was classified for them" -- correctly. With a
              // verdict on the row above it, the same panel then said `stable`
              // in one place and "no direction was classified" in the other.
              // A chart contradicting the words beside it is the exact fault
              // these components exist to prevent, and it was on screen.
              //
              // It also earns the line its colour: a classified `worsening`
              // takes rust here for the same reason it does on an assessed
              // chart, and `stable` takes no hue at all.
              classified={panel.classified === true}
              trend={panel.trend}
            />
          ) : (
            <>
              <p className="trend-chart__readings">
                {panel.rows
                  .map(
                    (r) =>
                      `${r.valueRaw ?? ''}${r.unit ? ` ${r.unit}` : ''} (${readingDate(r.date)})`
                  )
                  .join(' · ')}
              </p>
              {/* The flag that used to be the shut row's chip. Nothing is said
                  when there is none: unmarked is "not checked", not in range. */}
              {PRINTED_RANGE_SENTENCE[panel.latestFlag] ? (
                <p className="trend-chart__joined">
                  {PRINTED_RANGE_SENTENCE[panel.latestFlag]}
                </p>
              ) : null}
            </>
          )}
        </details>
      ))}
    </>
  );
}

function Trends({ data, history, labSeries }) {
  const features = data?.features ? Object.values(data.features) : [];
  // THE PANELS, BUILT ONCE AND USED TWICE -- rendered below and counted in the
  // line above them. `hasLab` is now derived from the same array rather than
  // from the payload, so "is there anything here" and "what is here" cannot
  // give different answers.
  const labPanels = labPanelsOf(labSeries);
  const hasLab = labPanels.length > 0;

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

  // Both halves of the card, counted from the arrays that become the panels.
  const tally = cardTally(charted, labPanels);
  // One sentence for the whole card, from those same panels. Computed once.
  const provenance = provenanceNote(labPanels);

  return (
    <section className="card tl-section">
      <h2>
        <span className="tl-section__icon tl-section__icon--trends" aria-hidden="true" />
        Trends over time
      </h2>
      <HistorySummary history={history} />

      {/* THE TALLY, OVER THE PANELS BELOW IT. See `cardTally` for what this
          replaced and why. The total is stated so the four parts can be
          checked against it -- the old line could not be reconciled with the
          rows underneath it at all. */}
      {tally.total ? (
        <p className="hint">
          {tally.total} parameter{tally.total === 1 ? '' : 's'} · {tally.improving}{' '}
          improving · {tally.worsening} worsening · {tally.stable} stable ·{' '}
          {tally.undirected} with no direction stated
        </p>
      ) : null}

      {/* SAID ONCE, FOR EVERYTHING BELOW IT. See `provenanceNote`. */}
      {provenance ? <p className="hint">{provenance}</p> : null}

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
                <span className="trend-chart__nodirection">{noDirectionWord(trend)}</span>
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
      <LabPanels panels={labPanels} />

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


/** A report, named the way the person who uploaded it would recognise it.
 *
 * THE LABEL SAYS WHICH DATE IT IS. `chronoDate` is `reportDate ?? uploadedAt`,
 * so printing it bare showed the upload clock as the date on the document: a
 * report printed 13 September, uploaded on the 19th with the optional field
 * blank, read `9/19/2026 — Test 3.pdf` in this very picker.
 *
 * A reader choosing two reports to compare is choosing two MOMENTS IN THEIR
 * OWN HISTORY, and "the day I sent it in" is not one of them unless it is
 * labelled as such. The ordering is unchanged -- `chronoDate` is still the
 * sort key, and still the right one.
 *
 * AND A TYPED DATE THE DOCUMENT CONTRADICTS IS LABELLED AS SUCH (2026-09-24):
 * `9/9/2026 (report prints 9/5/2026) — 03-renal...pdf`. Two reports printing
 * the same day had been typed two days apart, and this picker offered them as
 * two moments with nothing to say otherwise. `lib/reportDates` decides, for
 * this label and the reports list alike.
 */
function reportLabel(entry, namesById) {
  const info = reportDateInfo(entry);
  const when =
    info.source === 'typed'
      ? info.printedDisagrees
        ? `${info.shown} (report prints ${info.printedDisagrees})`
        : info.shown
      : info.source === 'printed'
        ? info.shown
        : info.source === 'uploaded'
          ? `uploaded ${info.shown}`
          : 'undated';

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

/**
 * THE WORDS A COMPARISON CATEGORY IS SHOWN IN.
 *
 * ==========================================================================
 * `unchanged` BECAME "no real change", AND THE ROW WAS CONTRADICTING ITSELF
 * ==========================================================================
 *
 * The category was printed by replacing its underscores, so `unchanged`
 * reached the reader as "unchanged" -- next to an arrow and two different
 * numbers:
 *
 *     EOSINOPHILS   5 %       ->  2 %        ↓ unchanged
 *     ESR           35 mm/hr  ->  45 mm/hr   ↑ unchanged
 *
 * The arrow says it moved, the numbers say it moved, and the word says it did
 * not. What the category actually means is "it moved less than this test's own
 * variation", which is a different and much weaker claim -- the same
 * distinction the reader had already had to ask about on the timeline.
 *
 * APPLIED TO MODULE 29's OWN ROWS AS WELL, not only the laboratory ones. One
 * table must not use one word for the assessed half and another for the rest,
 * and the assessed rows read exactly the same way -- `BMI 25.25 -> 25.25` is
 * genuinely unchanged, but an assessed feature that moved inside its band was
 * making the same false statement.
 *
 * THE CATEGORY ITSELF IS UNTOUCHED. `category--unchanged` still carries the
 * styling and the payload still says `unchanged`; this is the display word
 * only, so nothing downstream has to learn a new vocabulary.
 *
 * ==========================================================================
 * `changed_direction_only` READ AS "ONLY THE DIRECTION CHANGED"
 * ==========================================================================
 *
 * Printed by replacing its underscores, it reached the reader as:
 *
 *     Haemoglobin   9.2 g/dL  ->  13.6 g/dL   ↑ changed direction only
 *
 * which says nearly the opposite of what the category means. Module 29 found
 * a REAL change -- +47.8 %, far past haemoglobin's 9 % stability band -- and
 * declines only to call it better or worse, because haemoglobin's polarity is
 * deliberately undeclared (harmful low and high; the range turns on sex, age
 * and pregnancy). So it is said as the counterpart of "no real change": the
 * change is real, and no verdict is given on it.
 */
const COMPARISON_WORD = {
  unchanged: 'no real change',
  changed_direction_only: 'real change, not rated better or worse',
};

function comparisonWord(category) {
  return (
    COMPARISON_WORD[category] || String(category || '').replace(/_/g, ' ')
  );
}

/**
 * ONE ROW OF THE COMPARISON, FOR A TEST THIS PLATFORM DOES NOT ASSESS.
 *
 * ==========================================================================
 * THE SAME FOUR COLUMNS, AND NOTHING NEW CLAIMED IN THEM
 * ==========================================================================
 *
 * Module 29's rows and these sit in one table because they answer one
 * question, and a reader should not have to learn which service produced a
 * row to read it. So the `category` vocabulary is MODULE 29's OWN -- improved,
 * worsened, unchanged, changed_direction_only, newly_abnormal, newly_normal,
 * not_classifiable -- chosen in `buildLabComparison` by that module's own
 * documented precedence rather than translated into different words here.
 *
 * WHERE THESE ROWS DIFFER, THEY DIFFER HONESTLY:
 *
 *   - A BLOCKED ROW SHOWS BOTH UNITS. `101.9 U/L` against `13 IU/L` is the
 *     whole reason it cannot be classified, so hiding one unit would hide the
 *     reason. No symbol and no direction either.
 *   - A NON-NUMERIC RESULT IS SHOWN AS ITS TEXT. "Negative" and "Pale Yellow"
 *     are results; rendering them blank loses the laboratory's answer.
 *   - A PARAMETER ON ONE OF THE TWO REPORTS uses the table's existing
 *     "Not measured" shape rather than being dropped, which is what made this
 *     card look short in the first place.
 */
function LabComparisonRow({ row }) {
  const blocked = Boolean(row.blocked);
  // Each side with ITS OWN unit when they disagree, otherwise the shared one.
  const side = (value, raw, unit) => {
    if (isPresent(value)) {
      return <Value value={value} unit={blocked ? unit : row.unit} />;
    }
    // A result that is not a number, as printed.
    if (isPresent(raw)) {
      return (
        <span className="value">
          {raw}
          {unit ? ` ${unit}` : ''}
        </span>
      );
    }
    return (
      <Absent
        label="Not measured"
        reason="This parameter was not on that report."
      />
    );
  };

  return (
    <tr>
      <th scope="row">
        {readableName(row.name)}
        {Array.isArray(row.joinedFrom) && row.joinedFrom.length > 1 ? (
          // The join, named where the name is. `title` rather than a second
          // line, because this table is already four columns wide and the
          // timeline panel states it in full.
          <span className="hint" title={`Also printed as: ${row.joinedFrom.join(', ')}`}>
            {' '}
            ·{' '}
            {row.joinedFrom.length} names
          </span>
        ) : null}
      </th>
      <td>{side(row.previous, row.previousRaw, row.previousUnit)}</td>
      <td>{side(row.current, row.currentRaw, row.currentUnit)}</td>
      <td>
        {isPresent(row.category) && row.category !== 'not_classifiable' ? (
          <span className={`category category--${row.category}`}>
            {isPresent(row.symbol) ? `${row.symbol} ` : ''}
            {comparisonWord(row.category)}
          </span>
        ) : (
          <Absent
            label="Not classifiable"
            reason={
              // A `unit_missing` BRANCH STOOD HERE AND IS GONE WITH THE
              // REASON CODE. A reading that prints no unit is now taken to be
              // in the one unit the series does print, so it is not blocked at
              // all -- and a blocked series always means the printed units
              // genuinely disagree. Keeping a sentence for a state the
              // backend cannot produce would be the `basis.limitations` trap
              // from the other direction: a consumer ready for a payload that
              // no longer exists.
              blocked
                ? 'The two reports give this parameter in different units, so the readings were not compared.'
                : 'This parameter is not on both of these reports.'
            }
          />
        )}
      </td>
    </tr>
  );
}

/** The spec's Parameter / Previous / Current / Trend table. */
function Comparison({ data, lab, identity, reports, namesById, pair, onPairChange, busy }) {
  const rows = (data?.table || []).filter((row) => !PERSON_DETAILS.has(row.feature));
  const labRows = lab?.rows || [];

  return (
    <section className="card tl-section">
      <h2>
        <span className="tl-section__icon tl-section__icon--compare" aria-hidden="true" />
        Comparing two reports
      </h2>

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
          {Number.isFinite(data.pair.days_between)
            ? `, ${Math.abs(data.pair.days_between)} day${Math.abs(data.pair.days_between) === 1 ? '' : 's'} apart`
            : ''}
          {/* The full stop belongs to whichever ending is used. Both were
              printed before, giving "…is reversed.." -- invisible until the
              picker made an out-of-order comparison reachable at all. */}
          {data.pair.chronological === false
            ? ' — these were given out of date order, so the direction of every change is reversed.'
            : '.'}
        </p>
      ) : null}

      {/* BEFORE THE TABLE, because it decides what the table means: two
          people's reports compared as one history turn differences between
          people into "changes". See `components/IdentityNotice`. */}
      <PairIdentityNotice identity={identity} />

      {/* THE COUNT, OVER BOTH HALVES OF THE TABLE. The timeline's summary line
          was counting twelve assessed features over a card of twenty-six
          panels and the reader caught it; this card had the same shape of
          error waiting, so the number is taken from what is rendered. */}
      {rows.length + labRows.length ? (
        <p className="hint">
          {rows.length + labRows.length} parameter
          {rows.length + labRows.length === 1 ? '' : 's'} across these two reports.
        </p>
      ) : null}

      {rows.length + labRows.length ? (
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
                      {/* MODULE 29's ROWS GET THE SAME WORDS. One table, one
                          vocabulary -- see `COMPARISON_WORD`. */}
                      {comparisonWord(row.category)}
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
            {/* THE REST OF THE REPORT, IN THE SAME TABLE. Not a second
                section: the reader asked for these to sit with the rest on
                the timeline and the same answer applies here. */}
            {labRows.map((row) => (
              <LabComparisonRow key={`lab-${row.key}`} row={row} />
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">Nothing could be compared between these reports.</p>
      )}

      {/* THE SERVICE'S HEADLINE IS NOT PRINTED (2026-10-02). It repeated the
          two dates from the top of this card and added "24 parameter(s) were
          examined" under a table counting a different set (it includes age,
          sex and smoking and none of the unassessed tests). One count per
          page, taken from what is shown. The field stays on the API. */}
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
    <section className="card tl-section">
      <h2>
        <span className="tl-section__icon tl-section__icon--progress" aria-hidden="true" />
        Progress score
      </h2>

      {computed && isPresent(data.score) ? (
        <>
          {/* ONE PANEL: the number, its scale and its band, read together. */}
          <div className="progress__panel">
            <div className="progress__figure">
              <p className="progress__score">
                <strong>{data.score}</strong>
                <span className="hint"> / 100</span>
              </p>
              {data.band ? (
                <p className="progress__band">
                  <strong>{data.band.label}</strong>
                </p>
              ) : null}
            </div>
            <div className="progress__scale">
              <ScoreScale score={data.score} />
              {/* The scale's own end points and middle -- not readings. */}
              <div className="progress__ticks" aria-hidden="true">
                <span>0</span>
                <span>50</span>
                <span>100</span>
              </div>
            </div>
          </div>
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
          {/* NO "OF YOUR N" (2026-10-02). The service's total counts age, sex
              and smoking and none of the unassessed tests, so it disagreed
              with the parameter count on the two cards above. The
              contributing count is the one this number is made of. */}
          Worked out from {data.coverage.contributing_count}{' '}
          {data.coverage.contributing_count === 1 ? 'result' : 'results'}: the
          ones whose change between the two reports could be judged.
          {data.coverage.excluded_count > 0
            ? ' Everything else above is not in the number.'
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
  // Which pair choice is the latest. See `choosePair`.
  const requestSeq = useRef(0);

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
    // ONLY THE LATEST CHOICE MAY WRITE (2026-09-25). Two quick changes send
    // two pairs of requests, and nothing orders their answers: if the FIRST
    // choice's answer lands last, the table shows the pair the reader moved
    // away from while the picker names the one they chose -- this page's own
    // rule ("the selects show the comparison actually on screen") broken by
    // timing. Every answer checks it still belongs to the latest choice.
    requestSeq.current += 1;
    const mine = requestSeq.current;
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
    // A later choice has been made since this one was sent. Its own answer
    // will write -- and it alone clears `busy`, so "Comparing…" stays up until
    // the table matches the picker.
    if (mine !== requestSeq.current) return;
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
      <header className="page-hero">
        <span className="page-hero__icon" aria-hidden="true">
          <Icon name="timeline" size={26} />
        </span>
        <div>
          <h1>Your timeline</h1>
          <p className="hint">
            These views describe how measured values changed between your reports.
            They report arithmetic and a declared direction of change &mdash; they
            do not interpret those changes or identify any condition.
          </p>
        </div>
      </header>

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
          // A SEPARATE PROP, because `data` is Module 29's payload verbatim
          // and these rows are this backend's. Merging them before they reach
          // the page would hide which service is answerable for a row.
          lab={state.comparison?.labComparison}
          // This backend's same-person check for the pair on screen.
          identity={state.comparison?.identity}
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
