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

/** One feature's trajectory, or the stated reason there isn't one. */
/**
 * A feature name as a table-row heading.
 *
 * `PATIENT_LABEL` was already imported on this page and already used for the
 * chart headings above -- and this table printed `trend.feature` RAW, so one
 * screen showed "HbA1c (average blood sugar)" as a chart title and `hba1c`,
 * `blood_glucose`, `vitamin_b12` and `smoking_history` as row headings in the
 * table beneath it. Found while auditing the comparison table one row down
 * for the same class of leak.
 *
 * The table's entries for the profile answers are lower case because they are
 * written for mid-sentence use ("sex", "age", "smoking history"); a row
 * heading needs the first letter raised. The shared table is NOT edited for
 * that -- it would break every prose caller -- so the casing happens here,
 * where the heading is.
 */
function rowHeading(feature) {
  const label = PATIENT_LABEL[feature] || feature;
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function TrendRow({ trend }) {
  const classified = trend.outcome === 'TREND_CLASSIFIED';

  return (
    <tr>
      <th scope="row">{rowHeading(trend.feature)}</th>
      <td>
        {classified && isPresent(trend.trend) ? (
          <span className={`trend trend--${trend.trend}`}>{trend.trend}</span>
        ) : (
          // NOT "stable". The service's own sentence says why there is no
          // trend, and it is shown verbatim.
          <Absent
            label="No trend"
            reason={trend.reason || 'Not enough usable readings to describe a change.'}
          />
        )}
      </td>
      <td>
        {classified && trend.change ? (
          <>
            <Value value={trend.change.first_value} unit={trend.canonical_unit} />
            {' → '}
            <Value value={trend.change.last_value} unit={trend.canonical_unit} />
          </>
        ) : (
          <span className="absent">—</span>
        )}
      </td>
      <td className="hint">
        {trend.usable_point_count} usable reading(s)
        {trend.gaps?.length ? `, ${trend.gaps.length} gap(s)` : ''}
      </td>
    </tr>
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

/**
 * The laboratory's OWN repeated parameters.
 *
 * Module 28 trends canonical features -- the ones this pipeline can identify
 * across reports and express in one unit -- so everything the platform does
 * not assess was absent from the timeline entirely. A reader with reports
 * full of parameters that never appeared asked why.
 *
 * NO DIRECTION WORD ANYWHERE IN HERE, and no summary badge. There is no
 * polarity for these parameters and no stability band: nothing knows whether
 * a rising ESR is better or worse, or how much movement is noise. The panel
 * carries the readings and the dates and stops.
 */
function LabSeries({ data }) {
  const series = data?.series || [];
  if (!series.length && !data?.consideredCount) return null;

  const plotted = series.filter((s) => !s.blocked);
  const blocked = series.filter((s) => s.blocked);

  // HOW MANY OF THE DRAWN CHARTS GOT A SCALE. Taken from the panels actually
  // on screen, not from the payload's own counter -- a count that does not
  // come from the list it claims to count is a statement waiting to be wrong,
  // and this page has been wrong that way before.
  const scaled = plotted.filter((s) => s.referenceScale).length;
  const unscaled = plotted.length - scaled;

  return (
    <section className="card">
      <h2>Other parameters on your reports</h2>

      <p className="hint">
        Values your laboratory reported that this tool does not assess, shown
        over time. Nothing here is interpreted: no direction is given and no
        condition is derived from any of it.
      </p>

      {/* THE SCALE, AND WHY NO RANGE IS DRAWN.
          The assessed charts above are drawn against the band a change would
          have to cross to count. These parameters have no such band -- no
          polarity and no stability figure exists for them -- but their own
          laboratories printed a reference interval beside each value, and
          that is now carried through to set the scale.
          IT SETS THE SCALE AND IS NOT DRAWN, and the sentence below says so
          rather than leaving a reader to wonder where the shaded band went.
          The reader's reports disagree about the range on most parameters, so
          there is no single interval a band could honestly represent. */}
      {scaled ? (
        <p className="hint">
          The vertical scale on these includes the reference range printed on
          your own reports, so a reading inside the usual range sits inside the
          scale instead of filling it. No range is drawn on the charts: your
          reports do not all print the same range for the same test, so there
          is no one range to show.
        </p>
      ) : null}

      {/* A CHART WITH NO SCALE IS NOT THE SAME CHART, and a reader cannot see
          the difference between the two kinds by looking. Counted, not left
          to be inferred from a picture. */}
      {unscaled ? (
        <p className="hint">
          {scaled
            ? `${unscaled} of these had no reference range printed, so ${
                unscaled === 1 ? 'its scale covers' : 'their scales cover'
              } only the readings shown`
            : 'The vertical scale on these covers only the readings shown'}
          , and even a small change looks large.
        </p>
      ) : null}

      {plotted.map((entry) => (
        <details className="trend-chart__block disclosure" key={entry.key}>
          <summary className="disclosure__summary">
            <h3 className="trend-chart__title">{entry.name}</h3>
            <span className="disclosure__spacer" />
            <span className="disclosure__chevron" aria-hidden="true" />
          </summary>
          <TrendChart
            label={entry.name}
            unit={entry.unit}
            points={entry.points.map((p) => ({
              date: p.date,
              value: p.value,
              unit: p.unit,
            }))}
            // THE SCALE ONLY. Never `band` -- that prop is this platform's own
            // declared optimal range and is drawn as a rectangle, and these
            // numbers belong to the laboratory, not to us.
            scaleOnly={entry.referenceScale}
          />
          {entry.referenceScale ? null : (
            <p className="hint">
              No reference range for this test could be read from your reports,
              so this scale covers only the readings shown.
            </p>
          )}
        </details>
      ))}

      {/* A UNIT DISAGREEMENT IS A RESULT, NOT A REASON TO HIDE THE READINGS.
          Two scales on one axis is the failure 6z caught once already, so no
          line is drawn -- but the values are the laboratory's and the reader
          is entitled to them, with the disagreement named. */}
      {blocked.length ? (
        <div className="lab-series__blocked">
          {blocked.map((entry) => (
            <p key={entry.key}>
              <strong>{entry.name}</strong>{' '}
              {entry.points
                .map((p) => `${p.value} ${p.unit || ''}`.trim())
                .join(' \u2192 ')}
              {' \u2014 '}
              reported in different units ({entry.blocked.units.join(' and ')}),
              so these are not plotted together.
            </p>
          ))}
        </div>
      ) : null}

      {/* WHAT WAS CONSIDERED, so a reader seeing ten panels can tell that
          twenty-two parameters were looked at. An absence that is counted is
          not the same as one that is silent. */}
      <p className="hint">
        {data.consideredCount} parameter
        {data.consideredCount === 1 ? '' : 's'} considered.
        {data.singleReportCount
          ? ` ${data.singleReportCount} appeared on only one report, so there is nothing to compare them against.`
          : ''}
        {data.notNumericCount
          ? ` ${data.notNumericCount} were not reported as numbers.`
          : ''}
      </p>
    </section>
  );
}

function Trends({ data, history }) {
  const features = data?.features ? Object.values(data.features) : [];
  const summary = data?.summary;

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

      {/* THE CHARTS SIT ABOVE THE TABLE AND SAY THE SAME THINGS. The table
          stays the record -- it carries the service's own refusal sentence for
          every feature, including the ones with nothing to plot; the charts
          carry what a table cannot, which is where the line STOPS. */}
      {features.map((trend) => {
        if (NOT_A_TRAJECTORY.has(trend.outcome)) return null;
        const props = chartPropsFor(trend);
        // At least one real reading, or there is nothing to place: the row
        // below still carries the service's own sentence saying why.
        if (!props.points.length) return null;
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

      {features.length ? (
        <table className="lab-table">
          <thead>
            <tr>
              <th scope="col">Parameter</th>
              <th scope="col">Direction</th>
              <th scope="col">First → latest</th>
              <th scope="col">Readings</th>
            </tr>
          </thead>
          <tbody>
            {features.map((trend) => (
              <TrendRow key={trend.feature} trend={trend} />
            ))}
          </tbody>
        </table>
      ) : (
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
          <Trends data={state.trends?.trends} history={state.trends?.history} />
          <LabSeries data={state.trends?.labSeries} />
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
