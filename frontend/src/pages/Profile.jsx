import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import { profileFieldLabel } from '../lib/labels';
import AccountSettings from '../components/AccountSettings';
import Icon from '../components/Icon';


const GENDERS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' },
];

const SMOKING = [
  { value: '', label: 'Not answered' },
  { value: 'never', label: 'Never smoked' },
  { value: 'current', label: 'I smoke now' },
  { value: 'former', label: 'I used to smoke and have stopped' },
  { value: 'ever', label: 'I have smoked (not saying whether I still do)' },
  { value: 'not_current', label: "I don't smoke now (not saying about the past)" },
  { value: 'no_info', label: 'Prefer not to say' },
];

const TRISTATE_OPTIONS = [
  { v: true, label: 'Yes' },
  { v: false, label: 'No' },
  { v: null, label: 'Not sure / prefer not to say' },
];

export function answerLabel(value) {
  const match = TRISTATE_OPTIONS.find((option) => option.v === value);
  return match ? match.label : TRISTATE_OPTIONS[2].label;
}

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
  const welcome = Boolean(useLocation().state?.welcome);
  const [form, setForm] = useState(EMPTY);
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
          hypertension: profile.hypertension ?? null,
          heartDisease: profile.heartDisease ?? null,
        });
      } catch (err) {
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

  function payload() {
    const out = {};
    if (form.age !== '') out.age = Number(form.age);
    if (form.gender !== '') out.gender = form.gender;
    if (form.heightCm !== '') out.heightCm = Number(form.heightCm);
    if (form.weightKg !== '') out.weightKg = Number(form.weightKg);
    if (form.smokingHistory !== '') out.smokingHistory = form.smokingHistory;

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
      const data = await api.saveProfile(body);
      const profile = data.profile || data;
      setServer(profile);
      setExists(true);
      setSaved(true);
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

      {welcome ? (
        <section className="card profile-nudge" aria-labelledby="welcome-title">
          {saved ? (
            <>
              <h2 id="welcome-title">You&rsquo;re all set</h2>
              <p>
                Your details are saved. You can change them here at any time.
              </p>
              <p>
                <Link to="/reports" className="button-link">
                  Upload your first report
                </Link>
              </p>
            </>
          ) : (
            <>
              <h2 id="welcome-title">Welcome to VaidyaAI &mdash; start with your details</h2>
              <p>
                Please fill these in before your first report. The analysis
                uses your <strong>age and sex</strong> (for example to estimate
                kidney function, and for limits that differ for men and women),
                and your <strong>height and weight</strong>. Anything you leave
                blank is shown as &ldquo;not known&rdquo; &mdash; never guessed.
              </p>
              <p>
                <Link to="/reports">Skip for now</Link>
              </p>
            </>
          )}
        </section>
      ) : null}

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
              {completeness.missing?.length ? (
                <>
                  {' '}
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
