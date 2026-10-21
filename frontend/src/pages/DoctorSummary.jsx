import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { isPresent } from '../lib/absence';
import { isPatientDetail } from '../lib/sources';
import { readableName } from '../lib/displayName';
import { friendlyPageError } from '../lib/friendlyErrors';
import Icon from '../components/Icon';


const nameList = (names) =>
  names.join(names.some((name) => String(name).includes(',')) ? '; ' : ', ');

const andList = (names) =>
  names.length < 2
    ? names.join('')
    : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;

const humanFeature = (key) => String(key).replace(/_/g, ' ');

const sentenceCase = (text) =>
  text.length ? text[0].toUpperCase() + text.slice(1) : text;

function readableDate(value) {
  if (typeof value !== 'string' || value === '') return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function printedParameterName(row) {
  const printed = row.provenance?.original_test_name;
  if (row.provenance?.source === 'lab_report' && isPresent(printed?.text)) {
    return printed.text;
  }
  return row.display_name || row.feature;
}

function parameterName(row) {
  return readableName(printedParameterName(row));
}

function flaggingKinds(assessment) {
  const kinds = new Set();
  for (const basis of assessment.bases || []) {
    if (basis.status === 'Not Indicated' || basis.assessed === false) continue;
    kinds.add(basis.source_kind === 'machine_learning' ? 'model' : 'rule');
  }
  return kinds;
}

const NARRATIVE_CLOSING_LINE =
  'Not a diagnosis and not a clinical conclusion. The original laboratory '
  + 'report remains the primary record.';

function narrativeParagraphs(text) {
  return String(text || '')
    .replace(/\.\s{2,}/g, '.\n\n')
    .split(/\n\s*\n/)
    .map((para) => para.trim())
    .filter(Boolean);
}

function narrativeBody(text) {
  const paragraphs = narrativeParagraphs(text);
  const last = paragraphs[paragraphs.length - 1];
  return last === NARRATIVE_CLOSING_LINE ? paragraphs.slice(0, -1) : paragraphs;
}

function narrativeClosing(text) {
  const paragraphs = narrativeParagraphs(text);
  const last = paragraphs[paragraphs.length - 1];
  return last === NARRATIVE_CLOSING_LINE ? last : null;
}

function narrativeListsAllValues(text, rows) {
  if (!rows.length) return false;
  const body = String(text || '');
  return rows.every((row) => {
    const value = `${row.value}${isPresent(row.unit) ? ` ${row.unit}` : ''}`;
    return body.includes(`${printedParameterName(row)} ${value}`);
  });
}


function referenceText(item) {
  const low = item.labReferenceLow;
  const high = item.labReferenceHigh;
  if (low !== undefined && high !== undefined) return `${low}\u2013${high}`;
  if (high !== undefined) return `\u2264 ${high}`;
  if (low !== undefined) return `\u2265 ${low}`;
  return '';
}


export default function DoctorSummary() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    let summaryRendered = false;
    setData(null);
    setError(null);
    (async () => {
      try {
        const result = await api.getDoctorSummary(id);
        if (cancelled) return;
        setData(result);
        summaryRendered = true;

      } catch (err) {
        if (!cancelled && !summaryRendered) setError(friendlyPageError(err.message));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data) return <p className="loading">Preparing the clinical summary…</p>;

  const summary = data.doctorSummary || {};
  const unassessed = data.unassessed || null;
  const ROW_ABNORMAL_POSITIONS = ['below_reference_interval', 'above_reference_interval'];
  const assessedOutOfRange = (summary.laboratory?.rows || [])
    .filter((row) => {
      if (isPatientDetail(row.provenance?.source)) return false;
      if (row.usable === false || row.value === null || row.value === undefined) return false;
      const flag = String(row.printed_flag ?? '').trim().toLowerCase();
      const flagged = flag !== '' && flag !== 'none' && flag !== 'null' && flag !== 'normal';
      return ROW_ABNORMAL_POSITIONS.includes(String(row.position ?? '')) || flagged;
    })
    .map((row) => ({
      testName: parameterName(row),
      value: row.value,
      unit: row.unit,
      labReferenceLow: row.reference_low ?? undefined,
      labReferenceHigh: row.reference_high ?? undefined,
      labFlag: row.printed_flag ?? '',
    }));

  const unassessedOutOfRange = (unassessed?.items || []).filter(
    (item) => item.labFlaggedAbnormal === true
  );

  const outOfRange = [...assessedOutOfRange, ...unassessedOutOfRange].sort((a, b) =>
    String(a.testName).localeCompare(String(b.testName))
  );

  const outOfRangeLine = outOfRange.length ? (
    <p className="passage__outofrange">
        <strong>Outside the reference interval printed on the report:</strong>{' '}
        {outOfRange.map((item, index) => (
          <span key={`${item.testName}-${index}`}>
            {index > 0 ? '; ' : ''}
            {readableName(item.testName)} {item.value}
            {item.unit ? ` ${item.unit}` : ''}
            {referenceText(item) ? ` (${referenceText(item)}` : ' ('}
            {item.labFlag ? `${referenceText(item) ? ', ' : ''}${item.labFlag}` : ''}
            {')'}
          </span>
        ))}
        .{' '}
        <span className="passage__provenance">
          Either marked on the report or determined from the interval printed
          beside it; this tool does not record which.
        </span>
      </p>
  ) : null;
  const narrative = data.narrative || null;
  const patient = summary.patient || {};
  const laboratory = summary.laboratory || {};
  const quality = summary.data_quality || {};
  const rows = laboratory.rows || [];
  const assessments = summary.assessments || [];

  const context = [];
  if (isPresent(patient.age)) context.push(`${patient.age}-year-old`);
  if (isPresent(patient.gender)) context.push(String(patient.gender));
  const subject = context.join(' ');
  const notSupplied = ['hypertension', 'heart_disease', 'smoking_history'].filter(
    (key) => !isPresent(patient[key])
  );

  const personRow = (feature) =>
    rows.find((row) => row.feature === feature && isPresent(row.value)) || null;
  const ageRow = personRow('age');
  const sexRow = personRow('gender');
  const bmiRow = personRow('bmi');
  const fromReport = (row) => row?.provenance?.source === 'report_details';
  const fromProfile = (row) => row?.provenance?.source === 'patient_profile';
  const subjectParts = [];
  if (sexRow) subjectParts.push(sentenceCase(String(sexRow.value)));
  if (ageRow) subjectParts.push(`${ageRow.value} years`);
  if (bmiRow) subjectParts.push(`BMI ${bmiRow.value} kg/m²`);
  const printed = [];
  const profile = [];
  for (const [row, label] of [[sexRow, 'sex'], [ageRow, 'age'], [bmiRow, 'BMI']]) {
    if (fromReport(row)) printed.push(label);
    else if (fromProfile(row)) profile.push(label);
  }
  const sources = [];
  if (printed.length) sources.push(`${andList(printed)} as printed on the report`);
  const otherPerson = data.report?.subject?.owner === 'other';
  if (profile.length) {
    sources.push(
      `${andList(profile)} ${otherPerson ? 'as entered for this report' : "from the patient's profile"}`
    );
  }
  const unprinted = [sexRow && !fromReport(sexRow) && 'sex', ageRow && !fromReport(ageRow) && 'age']
    .filter(Boolean);
  if (unprinted.length) sources.push(`no ${unprinted.join(' or ')} could be read from the report`);
  const subjectLine = subjectParts.length ? (
    <p className="passage__subject">
      <strong>Analysed as.</strong> {subjectParts.join(', ')}
      {sources.length ? ` — ${sources.join('; ')}` : ''}.
    </p>
  ) : null;

  const measured = rows.filter(
    (row) => !isPatientDetail(row.provenance?.source) && row.usable !== false
  );
  const rejected = rows.filter((row) => row.usable === false);
  const anyInterval = measured.some(
    (row) => isPresent(row.reference_low) || isPresent(row.reference_high)
  );
  const labFlagged = measured.filter((row) => isPresent(row.printed_flag));

  const notAssessed = (unassessed?.items || []).filter(
    (item) => isPresent(item.testName) && isPresent(item.value)
  );
  const notAssessedHasInterval = notAssessed.some(
    (item) => isPresent(item.labReferenceLow) || isPresent(item.labReferenceHigh)
  );
  const notAssessedFlagged = notAssessed.some((item) => item.labFlaggedAbnormal === true);
  const reportedValuesLine = measured.length || notAssessed.length ? (
    <p>
      <strong>Reported values.</strong>{' '}
      {[
        ...measured.map((row) => {
          const value = `${row.value}${isPresent(row.unit) ? ` ${row.unit}` : ''}`;
          const flag = isPresent(row.printed_flag) ? ` (${row.printed_flag})` : '';
          return `${parameterName(row)} ${value}${flag}`;
        }),
        ...notAssessed.map((item) => {
          const value = `${item.value}${isPresent(item.unit) ? ` ${item.unit}` : ''}`;
          const flag = isPresent(item.labFlag) ? ` (${item.labFlag})` : '';
          return `${readableName(item.testName)} ${value}${flag}`;
        }),
      ].join('; ')}
      .
      {!anyInterval && !notAssessedHasInterval
        ? ' The source report printed no reference intervals, so no value here is placed relative to a range.'
        : ''}
      {(anyInterval || notAssessedHasInterval) && !labFlagged.length && !notAssessedFlagged
        ? ' None of these is marked outside the interval printed beside it.'
        : ''}
    </p>
  ) : null;

  const abnormal = new Set(summary.abnormal_findings || []);
  const flagged = assessments.filter(
    (a) => abnormal.has(a.condition) || (a.assessed !== false && a.status !== 'Not Indicated')
  );
  const byBoth = [];
  const byRule = [];
  const byModel = [];
  for (const assessment of flagged) {
    const kinds = flaggingKinds(assessment);
    const entry = `${assessment.condition}${
      isPresent(assessment.status) && assessment.status !== 'Indicated'
        ? ` (${String(assessment.status).toLowerCase()})`
        : ''
    }`;
    if (kinds.has('rule') && kinds.has('model')) byBoth.push(entry);
    else if (kinds.has('model')) byModel.push(entry);
    else byRule.push(entry);
  }
  const assessedNotFlagged = (a) =>
    !flagged.includes(a) && a.assessed !== false && a.status !== 'Insufficient Data';
  const clear = assessments.filter(assessedNotFlagged);


  const unreadable = quality.pages_unreadable || [];
  const reportDate = readableDate(summary.attribution?.report_date);

  return (
    <main className="doctor-summary">
      <header className="page-hero doctor-hero">
        <span className="page-hero__icon" aria-hidden="true">
          <Icon name="doctor" size={26} />
        </span>
        <div className="doctor-hero__text">
          <nav className="crumbs" aria-label="Breadcrumb">
            <Link to={`/reports/${id}`}>Dashboard</Link>
            <span aria-hidden="true">/</span>
            <span className="crumbs__here">Clinical summary</span>
          </nav>
          <h1>Summary for a healthcare professional</h1>
          <p className="hint">A short summary of this report to show your doctor.</p>
          {isPresent(data.report?.originalName) ? (
            <p className="doctor-hero__file">Report: {data.report.originalName}</p>
          ) : null}
        </div>
        <button type="button" className="doctor-hero__print" onClick={() => window.print()}>
          <Icon name="reports" size={18} />
          Print or save as PDF
        </button>
      </header>

      {isPresent(narrative?.text) ? (
        <article className="passage">
          {subjectLine}
          {narrativeListsAllValues(narrative.text, measured) && !notAssessed.length
            ? null
            : reportedValuesLine}
          {narrativeBody(narrative.text).map((para, index) => (
            <p key={index}>{para}</p>
          ))}
          {outOfRangeLine}

          <p className="passage__close">
            The wording above was written by a language model from the findings
            of this analysis and checked before being shown. The findings
            themselves were not produced by a language model.
          </p>

          {narrativeClosing(narrative.text) ? (
            <p>{narrativeClosing(narrative.text)}</p>
          ) : null}

        </article>
      ) : (
      <article className="passage">
        <p>
          {subject ? `${subject}. ` : ''}
          {isPresent(patient.bmi) ? `BMI ${patient.bmi} kg/m². ` : ''}
          Single laboratory report
          {isPresent(quality.page_count)
            ? `, ${quality.page_count} page${quality.page_count === 1 ? '' : 's'}`
            : ''}
          {reportDate ? `, analysed ${reportDate}` : ''}.
          {notSupplied.length
            ? ` ${sentenceCase(nameList(notSupplied.map(humanFeature)))} ${
                notSupplied.length === 1 ? 'was' : 'were'
              } not supplied and unavailable to the analysis.`
            : ''}
        </p>

        {reportedValuesLine}

        {rejected.length ? (
          <p>
            <strong>Not used.</strong> {nameList(rejected.map(parameterName))} did
            not pass validation and {rejected.length === 1 ? 'was' : 'were'}{' '}
            excluded from the analysis below.
          </p>
        ) : null}

        {flagged.length ? (
          <p>
            <strong>Flagged.</strong>{' '}
            {byBoth.length
              ? `${nameList(byBoth)} ${
                  byBoth.length === 1 ? 'was' : 'were'
                } flagged two ways: a measured value crossed one of this tool's cut-offs, and the statistical model agreed. `
              : ''}
            {byRule.length
              ? `${nameList(byRule)} ${
                  byRule.length === 1 ? 'was' : 'were'
                } flagged because a measured value crossed one of this tool's cut-offs. `
              : ''}
            {byModel.length
              ? `${nameList(byModel)} ${
                  byModel.length === 1 ? 'was' : 'were'
                } flagged by the statistical model alone — no measured value crossed a cut-off for ${
                  byModel.length === 1 ? 'it' : 'them'
                }. `
              : ''}
          </p>
        ) : (
          <p>
            <strong>Flagged.</strong> No measured value crossed a cut-off, and
            the statistical model flagged nothing.
          </p>
        )}

        {clear.length ? (
          <p>
            <strong>Assessed, not flagged.</strong>{' '}
            {nameList(clear.map((a) => a.condition))}. Each was compared
            against this tool&rsquo;s cut-offs and none was crossed.
          </p>
        ) : null}

        {unreadable.length ||
        quality.partial_document === true ||
        quality.sources_failed?.length ? (
          <p>
            <strong>Not fully read.</strong>{' '}
            {unreadable.length || quality.partial_document === true
              ? `Part of the document could not be read${
                  unreadable.length
                    ? ` (page${unreadable.length === 1 ? '' : 's'} ${unreadable.join(', ')})`
                    : ''
                }, so a parameter missing above may be missing from the reading rather than from the report. `
              : ''}
            {quality.sources_failed?.length
              ? `${nameList(quality.sources_failed)} did not complete. `
              : ''}
            None of this is a negative finding.
          </p>
        ) : null}

        {outOfRangeLine}

        <p className="passage__close">
          Not a diagnosis and not a clinical conclusion. The original laboratory
          report remains the primary record.
        </p>
      </article>
      )}

    </main>
  );
}
