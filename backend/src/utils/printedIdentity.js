'use strict';


const STATUS = Object.freeze({ READ: 'read', ABSENT: 'absent', UNREADABLE: 'unreadable' });

const DAY_MS = 24 * 60 * 60 * 1000;
const YEAR_MS = 365.25 * DAY_MS;

const AGE_TOLERANCE_YEARS = 2;

const SEX_WORDS = {
  m: 'male', male: 'male', man: 'male', boy: 'male',
  f: 'female', female: 'female', woman: 'female', girl: 'female',
};

function parseSex(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return { status: STATUS.ABSENT, value: null };
  const word = raw.trim().toLowerCase().replace(/[.\s]+$/g, '');
  const value = SEX_WORDS[word];
  return value ? { status: STATUS.READ, value } : { status: STATUS.UNREADABLE, value: null };
}

const AGE_UNITS = [
  { re: /(\d+(?:\.\d+)?)\s*(?:years?|yrs?|y)\b/i, per: 1 },
  { re: /(\d+(?:\.\d+)?)\s*(?:months?|mths?|mos?|m)\b/i, per: 1 / 12 },
  { re: /(\d+(?:\.\d+)?)\s*(?:weeks?|wks?|w)\b/i, per: 7 / 365.25 },
  { re: /(\d+(?:\.\d+)?)\s*(?:days?|d)\b/i, per: 1 / 365.25 },
];

function parseAge(raw) {
  if (typeof raw !== 'string' || !raw.trim()) return { status: STATUS.ABSENT, value: null };
  const text = raw.trim();

  let years = null;
  if (/^\d{1,3}$/.test(text)) {
    years = Number(text);
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
    sexRaw: sex.status === STATUS.UNREADABLE ? raw(meta.patient_sex) : undefined,
    ageYears: age.value === null ? undefined : age.value,
    ageStatus: age.status,
    ageRaw: age.status === STATUS.UNREADABLE ? raw(meta.patient_age) : undefined,
  };
  for (const key of Object.keys(identity)) {
    if (identity[key] === undefined) delete identity[key];
  }
  return identity;
}

const isRead = (identity, field) =>
  Boolean(identity) && identity[`${field}Status`] === STATUS.READ;

const time = (d) => (d ? new Date(d).getTime() : NaN);

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

function compareWithProfile({ identity, profile, features, reportDate, asOf = new Date() }) {
  const used = valuesUsed(features);
  const mine = profileValues(profile);
  if (!identity) return { status: 'not_checked', conflicts: [], printed: null, profile: mine, used };

  const conflicts = [];
  let sexCompared = false;
  let ageCompared = false;
  if (isRead(identity, 'sex') && mine.sex) {
    sexCompared = true;
    if (identity.sex !== mine.sex) {
      conflicts.push({ field: 'sex', printed: identity.sex, profile: mine.sex });
    }
  }
  if (isRead(identity, 'age') && typeof mine.ageYears === 'number') {
    const since = (time(asOf) - time(reportDate)) / YEAR_MS;
    if (Number.isFinite(since)) {
      ageCompared = true;
      const expected = identity.ageYears + Math.max(0, since);
      if (Math.abs(mine.ageYears - expected) > AGE_TOLERANCE_YEARS) {
        conflicts.push({ field: 'age', printed: identity.ageYears, profile: mine.ageYears });
      }
    }
  }
  const printed = {
    sex: identity.sex || null,
    sexStatus: identity.sexStatus,
    ageYears: identity.ageYears === undefined ? null : identity.ageYears,
    ageStatus: identity.ageStatus,
  };
  const result = { conflicts, printed, profile: mine, used };
  if (conflicts.length) return { status: 'conflict', ...result };
  return { status: sexCompared && ageCompared ? 'consistent' : 'incomplete', ...result };
}

function profileValues(profile) {
  const sex = profile && typeof profile.gender === 'string' ? profile.gender.toLowerCase() : null;
  const age = profile ? profile.age : null;
  return {
    sex: sex === 'male' || sex === 'female' ? sex : null,
    ageYears: typeof age === 'number' && Number.isFinite(age) ? age : null,
  };
}

function valuesUsed(features) {
  const map = features && features.features;
  const pick = (key) => {
    const entry = map && map[key];
    return entry && typeof entry === 'object' ? entry : null;
  };
  const age = pick('age');
  const sex = pick('gender');
  return {
    sex: sex && typeof sex.value === 'string' ? sex.value.toLowerCase() : null,
    sexSource: sex ? sex.source || null : null,
    ageYears: age && typeof age.value === 'number' && Number.isFinite(age.value) ? age.value : null,
    ageSource: age ? age.source || null : null,
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
  profileValues,
  valuesUsed,
};
