import { useEffect, useState } from 'react';
import { api, ApiError } from '../lib/api';
import { profileFieldLabel } from '../lib/labels';
import AccountSettings from '../components/AccountSettings';
import Icon from '../components/Icon';

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

/* THE VALUES ARE THE DIABETES MODEL'S OWN CATEGORIES and must not change;
   only the words do (owner, 2026-10-02). "Ever smoked" and "Not currently
   smoking" sat beside "Former" and "Current" with nothing to tell them apart.
   They are the two half-answers: smoked at some point but not saying whether
   now, and not smoking now but not saying whether before. */
const SMOKING = [
  { value: '', label: 'Not answered' },
  { value: 'never', label: 'Never smoked' },
  { value: 'current', label: 'I smoke now' },
  { value: 'former', label: 'I used to smoke and have stopped' },
  { value: 'ever', label: 'I have smoked (not saying whether I still do)' },
  { value: 'not_current', label: "I don't smoke now (not saying about the past)" },
  { value: 'no_info', label: 'Prefer not to say' },
];

/** true / false / null -- never a bare checkbox. See the header. */
const TRISTATE_OPTIONS = [
  { v: true, label: 'Yes' },
  { v: false, label: 'No' },
  { v: null, label: 'Not sure / prefer not to say' },
];

/** The stored answer in the words the form uses for it. */
export function answerLabel(value) {
  const match = TRISTATE_OPTIONS.find((option) => option.v === value);
  return match ? match.label : TRISTATE_OPTIONS[2].label;
}

/**
 * One tri-state question, as a disclosure.
 *
 * CLOSED IS THE RESTING STATE, and closing loses nothing: THE ANSWER IS ON
 * THE SUMMARY. A collapsed question that hid its own answer would make the
 * reader open both boxes to find out what is recorded, which is more work
 * than the open version and would put an absence ("Not sure") out of sight --
 * the one thing this form must never do.
 *
 * `<details>` REPLACED `<fieldset>`, and that fixed the layout defect as a
 * side effect. A `<legend>` is positioned OVER its fieldset's top border by
 * the user agent: give the box a background and the heading sits half on the
 * border with the line running through it, which is exactly what it looked
 * like. There is no CSS that makes a legend an ordinary block without a float
 * hack, and the element was buying nothing that `role="radiogroup"` plus an
 * `aria-label` does not -- the grouping a screen reader needs is preserved,
 * and the question is now announced once rather than by both a summary and a
 * legend saying the same words.
 */
function TriState({ label, value, onChange, help, open, onOpenChange }) {
  const name = label.replace(/\s+/g, '-').toLowerCase();
  return (
    <details
      className="tristate"
      open={open}
      onToggle={(event) => onOpenChange(event.currentTarget.open)}
    >
      <summary className="tristate__summary">
        <span className="tristate__q">{label}</span>
        <span className="tristate__answer">{answerLabel(value)}</span>
        <span className="disclosure__chevron" aria-hidden="true" />
      </summary>
      <div className="tristate__body" role="radiogroup" aria-label={label}>
        {help ? <p className="hint">{help}</p> : null}
        {TRISTATE_OPTIONS.map((option) => (
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
      </div>
    </details>
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
  /**
   * Which diagnosis questions are open.
   *
   * CLOSED ON ARRIVAL AND CLOSED AFTER A SAVE. They are two of the eight
   * fields on this form and they take five rows each; left open they are most
   * of the page, and a reader who has already answered them has no reason to
   * be looking at the radio buttons.
   *
   * This state is NOT derived from the answers. Opening "unanswered" ones
   * automatically was the obvious move and is wrong twice over: it would
   * re-open both boxes on every visit for anyone who has deliberately chosen
   * "prefer not to say" -- nagging someone for an answer they have already
   * given -- and it would make the boxes spring open again the moment a save
   * completed, which is the behaviour being removed.
   */
  const [openQuestion, setOpenQuestion] = useState({
    hypertension: false,
    heartDisease: false,
  });
  const openSetter = (key) => (next) =>
    setOpenQuestion((current) => ({ ...current, [key]: next }));
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
      // The answers are in; the controls for changing them are not what the
      // reader needs to see next.
      setOpenQuestion({ hypertension: false, heartDisease: false });
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) return <p className="loading">Loading your profile…</p>;

  const completeness = server?.completeness;

  return (
    <main className="profile">
      <header className="page-hero">
        <span className="page-hero__icon" aria-hidden="true">
          <Icon name="profile" size={26} />
        </span>
        <div>
          <h1>Your details</h1>
          <p className="hint">
            These are used by the analysis. Anything you leave blank stays blank
            &mdash; nothing here is guessed, and a question you do not answer is
            recorded as unanswered rather than as &ldquo;no&rdquo;.
          </p>
        </div>
      </header>

      <div className="profile__grid">
        <form onSubmit={onSubmit} className="card">
          <h2 className="form-title">
            <span className="form-title__icon" aria-hidden="true">
              <Icon name="profile" size={18} />
            </span>
            About you
          </h2>
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
            open={openQuestion.hypertension}
            onOpenChange={openSetter('hypertension')}
          />

          <TriState
            label="Diagnosed heart disease"
            value={form.heartDisease}
            onChange={(v) => set('heartDisease', v)}
            open={openQuestion.heartDisease}
            onOpenChange={openSetter('heartDisease')}
          />

          {error ? (
            <p className="error" role="alert">
              {error}
            </p>
          ) : null}
          {/* WHAT "SAVED." DOES NOT MEAN, and the reason this page looked
              broken. `analysisService.buildProfilePayload()` reads the profile
              AT ANALYSIS TIME and the result is stored on the report, so a
              report that has already been analysed keeps the answers that were
              known when it ran. A reader who answers these two questions
              BECAUSE the dashboard told them "no value was available for your
              history of heart disease and high blood pressure" then sees the
              dashboard say exactly the same thing, and concludes the save did
              nothing.
              It is the same standing property as the explanation cap and the
              clinician narrative (MEMORY 6ad, 6ag): changing an input does not
              rewrite what a past run stored. Said here, where the reader is
              when the expectation forms. */}
          {saved ? (
            <>
              <p className="ok">Saved.</p>
              <p className="hint">
                These answers are used the next time a report is analysed.
                Reports you have already analysed keep what was known when they
                ran, so their results do not change.
              </p>
            </>
          ) : null}

          <button type="submit">{exists ? 'Save changes' : 'Create profile'}</button>
        </form>

        <aside className="card profile__summary">
          <h3>Worked out for you</h3>
          <p className="profile__bmi">
            BMI:{' '}
            {server?.bmi != null ? (
              <strong>{server.bmi} kg/m²</strong>
            ) : (
              <em>Not calculated &mdash; height and weight are both needed.</em>
            )}
          </p>
          <p className="hint">
            BMI is always worked out from your height and weight &mdash; you
            can&rsquo;t type it in &mdash; so the number here is the one the
            analysis uses.
          </p>
          {completeness ? (
            <span className="meter" aria-hidden="true">
              <i style={{ width: `${Math.max(0, Math.min(100, Number(completeness.percent) || 0))}%` }} />
            </span>
          ) : null}
          {completeness ? (
            <p>
              Profile completeness: <strong>{completeness.percent}%</strong> (
              {completeness.filled} of {completeness.fields} fields the analysis
              can use).
              {/* THE FIELD NAMES WERE PRINTED RAW. "Still blank: heartDisease"
                  is a key from the profile document shown to the person whose
                  heart it is -- the same defect as `vitamin_b12` reaching a
                  patient, one layer up. The words now match the question the
                  form asks above, so a reader can find what they are told is
                  missing. */}
              {completeness.missing?.length ? (
                <>
                  {' '}
                  {/* "Not answered yet", not "Still blank" (2026-10-02): the
                      form above shows "Not sure / prefer not to say" for the
                      same unanswered question, and "blank" beside a visible
                      answer read as two different facts. */}
                  Not answered yet:{' '}
                  {completeness.missing.map(profileFieldLabel).join(', ')}.
                </>
              ) : null}
            </p>
          ) : null}
        </aside>
      </div>

      <AccountSettings />
    </main>
  );
}
