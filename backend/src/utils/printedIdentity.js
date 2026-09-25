'use strict';

/**
 * THE SEX AND AGE A REPORT PRINTS -- READ, COMPARED, AND NEVER GUESSED.
 *
 * ==========================================================================
 * WHY THIS EXISTS
 * ==========================================================================
 *
 * Found 2026-09-24. Every analysis used the ACCOUNT PROFILE's age and sex and
 * never the report's; nothing from the document said whose it was. So:
 *
 *   - `01-all-normal.pdf` prints "34 Years / Female" and was analysed as the
 *     profile's "20, male" -- a woman's haemoglobin judged against the male
 *     anaemia threshold, with nothing on screen to say so;
 *   - it was compared with `03-renal-anaemia-deficiency.pdf`, which prints
 *     "63 Years / Male", as ONE person's history: haemoglobin 9.2 -> 13.6
 *     "in 2 days".
 *
 * Extraction now copies the printed sex and age (Module 4 still never copies
 * a name -- a deliberate limit: two people of one sex and similar age will
 * NOT be told apart). This file reads them and says where they disagree.
 *
 * ==========================================================================
 * THE STATES, AND WHY "NOT CHECKED" IS ONE OF THEM
 * ==========================================================================
 *
 * A report analysed before the fields existed has NO `printedIdentity` at all:
 * nobody looked. That is never reported as "consistent". Within a checked
 * report each field is `read`, `absent` (not printed) or `unreadable`.
 */

const STATUS = Object.freeze({ READ: 'read', ABSENT: 'absent', UNREADABLE: 'unreadable' });

const DAY_MS = 24 * 60 * 60 * 1000;
const YEAR_MS = 365.25 * DAY_MS;

/**
 * Ages are printed in whole years and truncated, so two honest readings a
 * year apart can differ by up to two; anything further is not one person
 * ageing. Wide on purpose: a false alarm here tells someone their own two
 * reports are not theirs.
 */
const AGE_TOLERANCE_YEARS = 2;

const SEX_WORDS = {
  m: 'male', male: 'male', man: 'male', boy: 'male',
  f: 'female', female: 'female', woman: 'female', girl: 'female',
};

function parseSex(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return { status: STATUS.ABSENT, value: null };
  const word = raw.trim().toLowerCase().replace(/[.\s]+$/g, '');
  const value = SEX_WORDS[word];
  // Anything else -- "Other", "M/F", a stray digit -- is not read as either.
  return value ? { status: STATUS.READ, value } : { status: STATUS.UNREADABLE, value: null };
}

const AGE_UNITS = [
  { re: /(\d+(?:\.\d+)?)\s*(?:years?|yrs?|y)\b/i, per: 1 },
  { re: /(\d+(?:\.\d+)?)\s*(?:months?|mths?|mos?|m)\b/i, per: 1 / 12 },
  { re: /(\d+(?:\.\d+)?)\s*(?:weeks?|wks?|w)\b/i, per: 7 / 365.25 },
  { re: /(\d+(?:\.\d+)?)\s*(?:days?|d)\b/i, per: 1 / 365.25 },
];

/** Years, possibly fractional ("34Y 2M" -> 34.17), or unreadable. */
function parseAge(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return { status: STATUS.ABSENT, value: null };
  const text = raw.trim();

  let years = null;
  if (/^\d{1,3}$/.test(text)) {
    years = Number(text); // a bare number on a report's age line is years
  } else {
    let found = false;
    let total = 0;
    for (const { re, per } of AGE_UNITS) {
      const m = text.match(re);
      if (m) {
        found = true;
        total += Number(m[1]) * per;
      }
    }
    if (found) years = total;
  }
  if (years === null || !Number.isFinite(years) || years < 0 || years > 130) {
    return { status: STATUS.UNREADABLE, value: null };
  }
  return { status: STATUS.READ, value: Math.round(years * 100) / 100 };
}

/**
 * The stored shape, from an extraction's `report_metadata` -- or `null` when
 * the extraction predates the fields (the KEYS are absent), which means
 * nobody looked.
 */
function readPrintedIdentity(extraction) {
  const meta = extraction && extraction.report_metadata;
  if (!meta || typeof meta !== 'object') return null;
  if (!('patient_sex' in meta) && !('patient_age' in meta)) return null;
  const sex = parseSex(meta.patient_sex);
  const age = parseAge(meta.patient_age);
  const raw = (v) => (typeof v === 'string' && v.trim() ? v.trim().slice(0, 32) : undefined);
  const identity = {
    sex: sex.value || undefined,
    sexStatus: sex.status,
    // Kept only when it could not be read, so a page can quote it.
    sexRaw: sex.status === STATUS.UNREADABLE ? raw(meta.patient_sex) : undefined,
    ageYears: age.value === null ? undefined : age.value,
    ageStatus: age.status,
    ageRaw: age.status === STATUS.UNREADABLE ? raw(meta.patient_age) : undefined,
  };
  // NO `undefined` KEYS. Inside a nested `$set` the driver can write one as
  // `null`, and a stored `sex: null` beside `sexStatus: absent` is a value
  // where there should be an absence.
  for (const key of Object.keys(identity)) {
    if (identity[key] === undefined) delete identity[key];
  }
  return identity;
}

const isRead = (identity, field) =>
  Boolean(identity) && identity[`${field}Status`] === STATUS.READ;

const time = (d) => (d ? new Date(d).getTime() : NaN);

/**
 * Could these two reports be the same person?
 *
 * @returns {{status: 'not_checked'|'conflict'|'consistent'|'incomplete',
 *            conflicts: object[], notChecked: string[]}}
 *   `conflict`   a printed sex differs, or the printed ages cannot both be
 *                one person's given the two report dates
 *   `consistent` BOTH sex and age were read on BOTH and agree
 *   `incomplete` nothing disagrees, but something was not printed or not
 *                readable -- which is not the same as agreeing
 *   `not_checked` at least one report was analysed before these fields
 *                existed; `notChecked` lists which ('baseline'/'comparison')
 */
function comparePair(baseline, comparison) {
  const notChecked = [];
  if (!baseline || !baseline.identity) notChecked.push('baseline');
  if (!comparison || !comparison.identity) notChecked.push('comparison');
  if (notChecked.length) return { status: 'not_checked', conflicts: [], notChecked };

  const a = baseline.identity;
  const b = comparison.identity;
  const conflicts = [];

  if (isRead(a, 'sex') && isRead(b, 'sex') && a.sex !== b.sex) {
    conflicts.push({ field: 'sex', baseline: a.sex, comparison: b.sex });
  }
  let agesCompared = false;
  if (isRead(a, 'age') && isRead(b, 'age')) {
    const gap = (time(comparison.date) - time(baseline.date)) / YEAR_MS;
    if (Number.isFinite(gap)) {
      agesCompared = true;
      const expected = a.ageYears + gap;
      if (Math.abs(b.ageYears - expected) > AGE_TOLERANCE_YEARS) {
        conflicts.push({
          field: 'age',
          baseline: a.ageYears,
          comparison: b.ageYears,
          expected: Math.round(expected * 10) / 10,
        });
      }
    }
  }

  if (conflicts.length) return { status: 'conflict', conflicts, notChecked };
  const complete = isRead(a, 'sex') && isRead(b, 'sex') && agesCompared;
  return { status: complete ? 'consistent' : 'incomplete', conflicts, notChecked };
}

/**
 * Does the report agree with the profile values the ANALYSIS USED?
 *
 * `used` is read from the analysis's own engineered features, and only the
 * fields whose `source` is `patient_profile` -- a value that came from the
 * report cannot disagree with the report.
 *
 * @returns {{status: 'not_checked'|'conflict'|'consistent'|'incomplete',
 *            conflicts: object[], printed: object|null, used: object}}
 */
function compareWithProfile({ identity, features, reportDate, analysedAt }) {
  const used = profileValuesUsed(features);
  if (!identity) return { status: 'not_checked', conflicts: [], printed: null, used };

  const conflicts = [];
  let sexCompared = false;
  let ageCompared = false;
  if (isRead(identity, 'sex') && (used.sex === 'male' || used.sex === 'female')) {
    sexCompared = true;
    if (identity.sex !== used.sex) {
      conflicts.push({ field: 'sex', printed: identity.sex, used: used.sex });
    }
  }
  if (isRead(identity, 'age') && typeof used.ageYears === 'number') {
    // The profile's age is the reader's age NOW; the report's is their age
    // THEN. Carry the printed one forward before comparing.
    const since = (time(analysedAt) - time(reportDate)) / YEAR_MS;
    if (Number.isFinite(since)) {
      ageCompared = true;
      const expected = identity.ageYears + Math.max(0, since);
      if (Math.abs(used.ageYears - expected) > AGE_TOLERANCE_YEARS) {
        conflicts.push({ field: 'age', printed: identity.ageYears, used: used.ageYears });
      }
    }
  }
  const printed = {
    sex: identity.sex || null,
    sexStatus: identity.sexStatus,
    ageYears: identity.ageYears === undefined ? null : identity.ageYears,
    ageStatus: identity.ageStatus,
  };
  if (conflicts.length) return { status: 'conflict', conflicts, printed, used };
  return {
    status: sexCompared && ageCompared ? 'consistent' : 'incomplete',
    conflicts,
    printed,
    used,
  };
}

/** The sex and age the analysis took from the PROFILE, or null for each. */
function profileValuesUsed(features) {
  const map = features && features.features;
  const pick = (key) => {
    const entry = map && map[key];
    return entry && typeof entry === 'object' && entry.source === 'patient_profile'
      ? entry.value
      : null;
  };
  const age = pick('age');
  const sex = pick('gender');
  return {
    sex: typeof sex === 'string' ? sex.toLowerCase() : null,
    ageYears: typeof age === 'number' && Number.isFinite(age) ? age : null,
  };
}

module.exports = {
  STATUS,
  AGE_TOLERANCE_YEARS,
  parseSex,
  parseAge,
  readPrintedIdentity,
  comparePair,
  compareWithProfile,
  profileValuesUsed,
};
