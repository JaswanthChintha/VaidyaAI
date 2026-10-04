import { Link } from 'react-router-dom';
import ThemeToggle from '../components/ThemeToggle';
import Icon from '../components/Icon';
import Splash from '../components/Splash';

/**
 * The public front page, shown only to someone who is not signed in.
 *
 * EVERY CLAIM ON THIS PAGE IS ONE THE CODE MAKES TRUE. No user counts, no
 * accuracy figures, no testimonials: a medical tool that opens with numbers
 * nobody measured has told the reader how much to trust the rest of it.
 *
 * The example cards are labelled as examples and use the same categorical
 * colours the dashboard uses, meaning exactly what they mean there.
 */

const STEPS = [
  {
    icon: 'upload',
    title: 'Upload your report',
    text: 'A PDF or a photo of a blood test report. Add the date it was printed so your reports line up in order.',
  },
  {
    icon: 'read',
    title: 'Every value is read',
    text: 'Each page is read for the test name, value and unit. Units are converted, and readings that make no sense are set aside.',
  },
  {
    icon: 'check',
    title: 'Checked two ways',
    text: 'Clinical rules with their published sources, and trained models for diabetes, heart disease and kidney disease. Each says so when the report has too little to go on.',
  },
  {
    icon: 'explain',
    title: 'Explained in plain words',
    text: 'Short explanations drawn from a curated knowledge base. Every explanation passes a safety check before you see it, and is withheld if it does not.',
  },
];

const FEATURES = [
  {
    icon: 'reports',
    title: 'A dashboard for every report',
    text: 'What is worth a closer look, what was checked and found nothing, and every value set against the limit it was compared with.',
  },
  {
    icon: 'timeline',
    title: 'A timeline across reports',
    // Not "a real change told apart from variation": the per-test variation
    // figures are published values none of which has yet been verified by a
    // person (MEMORY.md section 0, item 1). Reworded 2026-10-02.
    text: 'How each value moved between your reports, compared against published figures for how much each test normally varies.',
  },
  {
    icon: 'doctor',
    title: 'A summary for your doctor',
    text: 'A short clinical summary of the values and the findings, written to be read by a healthcare professional.',
  },
  {
    icon: 'people',
    title: 'How your values compare',
    text: 'Where a value sits among people of the same age and sex in a US national health survey (NHANES).',
  },
];

const PROMISES = [
  {
    title: 'It does not diagnose',
    text: 'It points out what may be worth discussing with a doctor. It never tells you that you have a condition.',
  },
  {
    title: 'It does not fill gaps',
    text: 'A test missing from your report is shown as missing. “Not checked” is never presented as “fine”.',
  },
  {
    title: 'It does not guess whose report it is',
    text: 'If the sex or age printed on a report differs from your profile, it says so and tells you which one it used.',
  },
  {
    title: 'It shows its working',
    text: 'Each finding lists the values behind it and the threshold it was compared with, so you or your doctor can check it.',
  },
];

const PIPELINE = ['Reading', 'Validation', 'Clinical rules', 'Trained models', 'Explanations', 'Safety check'];

const EXAMPLE = [
  { name: 'HbA1c', value: '7.0 %', verdict: 'Above the usual limit', kind: 'high' },
  { name: 'Fasting glucose', value: '168 mg/dL', verdict: 'Above the usual limit', kind: 'high' },
  { name: 'Haemoglobin', value: '13.6 g/dL', verdict: 'Within the usual limit', kind: 'normal' },
];

function Brand() {
  return (
    <Link to="/" className="landing__brand">
      <span className="nav__mark" aria-hidden="true">
        <Icon name="leaf" size={18} />
      </span>
      <span>
        Vaidya<em>AI</em>
      </span>
    </Link>
  );
}

function ExampleSheet() {
  return (
    <figure className="specimen" aria-label="Example of a results table, with illustrative values">
      <div className="specimen__head">
        <span className="micro">Example · illustrative values</span>
        <span className="micro">Blood test</span>
      </div>
      <table className="specimen__table">
        <thead>
          <tr>
            <th scope="col">Test</th>
            <th scope="col">Result</th>
            <th scope="col">
              <span className="visually-hidden">Reading</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {EXAMPLE.map((row) => (
            <tr key={row.name}>
              <td>{row.name}</td>
              <td className="specimen__num">{row.value}</td>
              <td>
                <span className={`specimen__tag specimen__tag--${row.kind}`}>{row.verdict}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export default function Landing() {
  return (
    <div className="landing">
      <Splash />
      <header className="landing__bar">
        <Brand />
        <nav className="landing__links" aria-label="On this page">
          <a href="#how">How it works</a>
          <a href="#features">What you get</a>
          <a href="#safety">Safety</a>
        </nav>
        <span className="landing__spacer" />
        <ThemeToggle />
        <Link to="/signin" className="landing__signin">
          Sign in
        </Link>
        <Link to="/signin" state={{ mode: 'register' }} className="button-link landing__cta">
          Get started
        </Link>
      </header>

      <main className="landing__main">
        <section className="hero">
          <div className="hero__text">
            <p className="pill">
              <Icon name="leaf" size={15} />
              Laboratory reports, explained
            </p>
            <h1 className="hero__title">
              Your lab report, read <em>carefully</em>.
            </h1>
            <p className="hero__lead">
              Upload a blood test report. VaidyaAI reads each value, compares
              it with published clinical thresholds, and explains what it found
              in plain words.
            </p>
            <div className="hero__actions">
              <Link to="/signin" state={{ mode: 'register' }} className="button-link">
                Create an account
                <Icon name="arrow" size={18} />
              </Link>
              <Link to="/signin" className="button-link button-link--quiet">
                Sign in
              </Link>
            </div>
            <ul className="hero__ticks">
              <li>Not a diagnosis</li>
              <li>Safety-checked wording</li>
              <li>Missing values stay missing</li>
            </ul>
          </div>

          <div className="hero__visual">
            <ExampleSheet />
            <div className="float-card float-card--verdict" aria-hidden="true">
              <span className="micro">Example · overall</span>
              <strong>Worth a closer look</strong>
              <span>2 conditions · discuss with a doctor</span>
            </div>
            <div className="float-card float-card--safety" aria-hidden="true">
              <span className="icon-disc icon-disc--sm">
                <Icon name="check" size={18} />
              </span>
              <span>Every written explanation is safety-checked before you read it</span>
            </div>
          </div>
        </section>

        <section className="pipeline" aria-label="What happens to a report">
          {PIPELINE.map((stage, i) => (
            <span key={stage} className="pipeline__stage">
              {stage}
              {i < PIPELINE.length - 1 ? <Icon name="arrow" size={14} /> : null}
            </span>
          ))}
        </section>

        <section id="how" className="band">
          <div className="band__head">
            <p className="eyebrow">How it works</p>
            <h2 className="band__title">From a printed report to an explanation you can read</h2>
          </div>
          <ol className="steps">
            {STEPS.map((step, i) => (
              <li key={step.title} className="step">
                <div className="step__top">
                  <span className="icon-disc">
                    <Icon name={step.icon} />
                  </span>
                  <span className="step__num">{String(i + 1).padStart(2, '0')}</span>
                </div>
                <h3 className="step__title">{step.title}</h3>
                <p className="step__text">{step.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="features" className="band">
          <div className="band__head">
            <p className="eyebrow">What you get</p>
            <h2 className="band__title">One report, four ways to understand it</h2>
          </div>
          <div className="features">
            {FEATURES.map((f) => (
              <div key={f.title} className="feature">
                <span className="icon-disc">
                  <Icon name={f.icon} />
                </span>
                <h3 className="feature__title">{f.title}</h3>
                <p className="feature__text">{f.text}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="safety" className="safety">
          <div className="band__head">
            <p className="eyebrow">Safety</p>
            <h2 className="band__title">What it will not do</h2>
          </div>
          <div className="promises">
            {PROMISES.map((p) => (
              <div key={p.title} className="promise">
                <span className="promise__mark" aria-hidden="true">
                  <Icon name="check" size={18} />
                </span>
                <div>
                  <h3 className="promise__title">{p.title}</h3>
                  <p className="promise__text">{p.text}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      <section className="closing">
        <div className="closing__inner">
          <div>
            <h2 className="closing__title">Have a report to hand?</h2>
            <p className="closing__text">Reading one usually takes a few minutes.</p>
          </div>
          <Link to="/signin" state={{ mode: 'register' }} className="button-link closing__button">
            Create an account
            <Icon name="arrow" size={18} />
          </Link>
        </div>
      </section>

      <footer className="landing__foot">
        <div className="foot__brand">
          <Brand />
          <p>
            VaidyaAI explains laboratory results for education and discussion.
            It does not diagnose, and it is not a substitute for advice from a
            qualified healthcare professional.
          </p>
        </div>
        <div className="foot__col">
          <h3>Product</h3>
          <a href="#how">How it works</a>
          <a href="#features">What you get</a>
          <a href="#safety">Safety</a>
        </div>
        <div className="foot__col">
          <h3>Account</h3>
          <Link to="/signin">Sign in</Link>
          <Link to="/signin" state={{ mode: 'register' }}>
            Create an account
          </Link>
        </div>
      </footer>
    </div>
  );
}
