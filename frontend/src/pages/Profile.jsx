import { useEffect, useState } from 'react';
import { api, ApiError } from '../lib/api';

/**
 * Module 2's patient profile.
 *
 * ==========================================================================
 * THE TWO THINGS THIS FORM MUST NOT DO
 * ==========================================================================
 *
 * 1. IT MUST NOT SEND `false` FOR AN UNANSWERED QUESTION. `hypertension` and
 *    `heartDisease` are TRI-STATE server-side: true, false, or absent meaning
 *    nobody asked. Module 12's kidney predictor reads that distinction to
 *    decide whether to skip rather than guess, and collapsing absent to
 *    `false` fabricates a negative clinical finding -- MEMORY.md section 6a
 *    names this explicitly. An HTML checkbox cannot express three states, so
 *    these are radio groups with an explicit "Prefer not to say / not sure",
 *    which is sent by OMITTING the key. Not by sending `null`: the validator
 *    rejects that as a type error, so the honest answer would have produced a
 *    422 the patient could not act on. See `payload()`.
 *
 * 2. IT MUST NOT SEND A DERIVED BMI. BMI is excluded from the writable
 *    allow-list AND recomputed by a model hook, so a client-supplied value is
 *    ignored twice over. It is displayed read-only here, from the server's
 *    own computation, so the number on screen is the number the models use.
 *
 * Gender offers all four stored values including `prefer_not_to_say`. Module
 * 31 answers `SEX_COHORT_NOT_AVAILABLE` for the two non-binary options rather
 * than coercing a stated gender into a binary cohort, and that refusal is the
 * correct behaviour -- so the option is offered honestly here rather than
 * hidden to make a percentile available.
 */

const GENDERS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' },
];

const SMOKING = [
  { value: '', label: 'Not answered' },
  { value: 'never', label: 'Never smoked' },
  { value: 'former', label: 'Former smoker' },
  { value: 'current', label: 'Current smoker' },
  { value: 'ever', label: 'Ever smoked' },
  { value: 'not_current', label: 'Not currently smoking' },
  { value: 'no_info', label: 'Prefer not to say' },
];

/** true / false / null -- never a bare checkbox. See the header. */
function TriState({ label, value, onChange, help }) {
  const name = label.replace(/\s+/g, '-').toLowerCase();
  const options = [
    { v: true, label: 'Yes' },
    { v: false, label: 'No' },
    { v: null, label: 'Not sure / prefer not to say' },
  ];
  return (
    <fieldset className="tristate">
      <legend>{label}</legend>
      {help ? <p className="hint">{help}</p> : null}
      {options.map((option) => (
        <label key={String(option.v)} className="tristate__option">
          <input
            type="radio"
            name={name}
            checked={value === option.v}
            onChange={() => onChange(option.v)}
          />
          {option.label}
        </label>
      ))}
    </fieldset>
  );
}

const EMPTY = {
  age: '',
  gender: '',
  heightCm: '',
  weightKg: '',
  smokingHistory: '',
  hypertension: null,
  heartDisease: null,
};

export default function Profile() {
  const [form, setForm] = useState(EMPTY);
  const [server, setServer] = useState(null);
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.getProfile();
        const profile = data.profile || data;
        setServer(profile);
        setExists(true);
        setForm({
          age: profile.age ?? '',
          gender: profile.gender ?? '',
          heightCm: profile.heightCm ?? '',
          weightKg: profile.weightKg ?? '',
          smokingHistory: profile.smokingHistory ?? '',
          // `?? null` NOT `|| false`: a stored `false` is a real answer and
          // must round-trip as one.
          hypertension: profile.hypertension ?? null,
          heartDisease: profile.heartDisease ?? null,
        });
      } catch (err) {
        // 404 is the documented "no profile yet" answer, not an error -- the
        // backend deliberately 404s rather than returning an empty 200.
        if (err instanceof ApiError && err.status === 404) {
          setExists(false);
        } else {
          setError(err.message);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function set(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  /**
   * Build the payload.
   *
   * An empty text field is OMITTED, not sent as `""` or `0`. The numeric
   * fields accept JSON numbers only -- `"70kg"` and `"170"` are both 422 --
   * so a blank must not become a zero on the way out, and a unit must never
   * be smuggled through as a string.
   */
  function payload() {
    const out = {};
    if (form.age !== '') out.age = Number(form.age);
    if (form.gender !== '') out.gender = form.gender;
    if (form.heightCm !== '') out.heightCm = Number(form.heightCm);
    if (form.weightKg !== '') out.weightKg = Number(form.weightKg);
    if (form.smokingHistory !== '') out.smokingHistory = form.smokingHistory;

    // "NOT SURE" IS SENT BY OMITTING THE KEY, NOT BY SENDING null.
    //
    // The validator rejects an explicit null outright -- "Heart disease status
    // must be true or false" -- so a patient choosing "Not sure" would have
    // got a 422 they could not act on. This comment previously claimed the
    // opposite, and a contract check against the running backend caught it.
    //
    // Clearing works because this form saves with PUT, whose replace
    // semantics drop any field the body omits. That is also why every save
    // sends the WHOLE form: a partial PATCH could never move an answer back
    // to unknown, and "I told you I have hypertension and now I am not sure"
    // has to be expressible. `false` is a real answer and is still sent.
    if (form.hypertension !== null) out.hypertension = form.hypertension;
    if (form.heartDisease !== null) out.heartDisease = form.heartDisease;
    return out;
  }

  async function onSubmit(event) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    try {
      const body = payload();
      // Always PUT. It upserts, so there is no create/update branch to get
      // wrong, and its replace semantics are what make "Not sure" reachable.
      const data = await api.saveProfile(body);
      const profile = data.profile || data;
      setServer(profile);
      setExists(true);
      setSaved(true);
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) return <p className="loading">Loading your profile…</p>;

  const completeness = server?.completeness;

  return (
    <main className="profile">
      <h2>Your details</h2>
      <p className="hint">
        These are used by the analysis. Anything you leave blank stays blank
        &mdash; nothing here is guessed, and a question you do not answer is
        recorded as unanswered rather than as &ldquo;no&rdquo;.
      </p>

      <form onSubmit={onSubmit} className="card">
        <label>
          Age (whole years)
          <input
            type="number"
            min="0"
            max="130"
            value={form.age}
            onChange={(e) => set('age', e.target.value)}
          />
        </label>

        <label>
          Gender
          <select value={form.gender} onChange={(e) => set('gender', e.target.value)}>
            <option value="">Not answered</option>
            {GENDERS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Height (cm)
          <input
            type="number"
            min="30"
            max="275"
            value={form.heightCm}
            onChange={(e) => set('heightCm', e.target.value)}
          />
        </label>

        <label>
          Weight (kg)
          <input
            type="number"
            min="1"
            max="650"
            value={form.weightKg}
            onChange={(e) => set('weightKg', e.target.value)}
          />
        </label>

        <label>
          Smoking history
          <select
            value={form.smokingHistory}
            onChange={(e) => set('smokingHistory', e.target.value)}
          >
            {SMOKING.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <TriState
          label="Diagnosed high blood pressure"
          value={form.hypertension}
          onChange={(v) => set('hypertension', v)}
          help="If you are not sure, say so. An unanswered question is treated as unknown, not as 'no'."
        />

        <TriState
          label="Diagnosed heart disease"
          value={form.heartDisease}
          onChange={(v) => set('heartDisease', v)}
        />

        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
        {saved ? <p className="ok">Saved.</p> : null}

        <button type="submit">{exists ? 'Save changes' : 'Create profile'}</button>
      </form>

      <aside className="card">
        <h3>Derived by the server</h3>
        <p>
          BMI:{' '}
          {server?.bmi != null ? (
            <strong>{server.bmi} kg/m²</strong>
          ) : (
            <em>Not calculated &mdash; height and weight are both needed.</em>
          )}
        </p>
        <p className="hint">
          BMI is always computed from your height and weight, never accepted
          from this form, so the number here is the one the analysis uses.
        </p>
        {completeness ? (
          <p>
            Profile completeness: <strong>{completeness.percent}%</strong> (
            {completeness.filled} of {completeness.fields} fields the analysis
            can use).
            {completeness.missing?.length ? (
              <> Still blank: {completeness.missing.join(', ')}.</>
            ) : null}
          </p>
        ) : null}
      </aside>
    </main>
  );
}
