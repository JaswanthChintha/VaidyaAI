import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import ThemeToggle from '../components/ThemeToggle';
import Icon from '../components/Icon';

/**
 * Sign in and register, on one screen.
 *
 * REGISTRATION SENDS NO ROLE. The backend hard-codes `patient` in the
 * controller AND rejects any supplied role in the validator (MEMORY.md
 * section 6), so sending one would be refused -- but the field is absent here
 * too, so this client never even implies that the choice exists. Clinician
 * and admin accounts are provisioned out of band by design.
 *
 * The 72-byte password cap is the backend's, enforced at the model layer
 * where it cannot be bypassed. It is surfaced here as guidance so a patient
 * learns about it before submitting, not as a substitute for that check.
 */
export default function SignIn() {
  const { signIn, register } = useAuth();
  const navigate = useNavigate();
  // The landing page's "Create an account" arrives here already in that mode.
  const location = useLocation();

  const [mode, setMode] = useState(location.state?.mode === 'register' ? 'register' : 'signIn');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  // CONFIRM ON REGISTER, AND A WAY TO SEE WHAT WAS TYPED (2026-10-02). There
  // is no "forgot password" on this platform, so a typo in the one password
  // field at registration locked the new account for good.
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  // { message, code } | null. The CODE is kept so the form can offer the
  // right next step without the SERVER having to say what went wrong.
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const registering = mode === 'register';

  async function onSubmit(event) {
    event.preventDefault();
    setError(null);
    if (registering && password !== confirm) {
      setError({
        message: 'The two passwords do not match. Type the same password in both boxes.',
        code: 'PASSWORD_MISMATCH',
      });
      return;
    }
    setBusy(true);
    try {
      if (registering) {
        await register({ name, email, password });
        // A NEW ACCOUNT STARTS ON ITS DETAILS (owner, 2026-10-06): the
        // analysis reads age, sex, height and weight from the profile, and a
        // new user had no way to know. `welcome` shows the note explaining why.
        navigate('/profile', { state: { welcome: true } });
        return;
      }
      await signIn(email, password);
      navigate('/reports');
    } catch (err) {
      // The backend's messages are fixed strings written to be shown; they
      // never echo input and never disclose whether an account exists.
      //
      // EXCEPT THE RATE LIMIT'S, which is shared by every limiter and says
      // only "Too many requests, please try again later" -- not how long.
      // Sign-in and register sit behind the login limiter, whose window is
      // RATE_LIMIT_WINDOW_MS (15 minutes); "up to" because part of it may
      // already have passed.
      const message =
        err.code === 'RATE_LIMIT_EXCEEDED'
          ? `Too many ${registering ? 'attempts' : 'sign-in attempts'}. Please wait up to 15 minutes and try again.`
          : err.message;
      setError({ message, code: err.code });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      {/* THE TOGGLE HAS TO BE HERE TOO. The header is only rendered when
          signed in, so without this the sign-in screen -- the first thing
          anyone ever sees, and the one most likely to be opened at night --
          would be the single page with no way to change the theme. */}
      <div className="auth__head">
        <Link to="/" className="auth__brand">
          <span className="nav__mark" aria-hidden="true">
            <Icon name="leaf" size={18} />
          </span>
          <span>
            Vaidya<em>AI</em>
          </span>
        </Link>
        <ThemeToggle />
      </div>

      <div className="auth__body">
        <section className="auth__intro">
          <h1>{registering ? 'Make sense of your next lab report.' : 'Welcome back.'}</h1>
          <p className="auth__tagline">
            Understand your laboratory reports. This is health education and
            decision support, not a diagnosis.
          </p>
          <ul className="auth__points">
            <li>Every value read straight from your report, PDF or photo</li>
            <li>Plain-language explanations, safety-checked before you see them</li>
            <li>See how your results change from one report to the next</li>
          </ul>
        </section>

        <form onSubmit={onSubmit} className="card">
          <h2>{registering ? 'Create an account' : 'Sign in'}</h2>

          {registering ? (
            <label>
              Name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoComplete="name"
              />
            </label>
          ) : null}

          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </label>

          <label>
            Password
            <span className="auth__password">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete={registering ? 'new-password' : 'current-password'}
              />
              <button
                type="button"
                className="link auth__show"
                aria-pressed={showPassword}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword((v) => !v)}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </span>
          </label>

          {registering ? (
            <label>
              Confirm password
              <input
                type={showPassword ? 'text' : 'password'}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                autoComplete="new-password"
              />
            </label>
          ) : null}

          {/* 72 is the backend's limit (bcrypt reads only the first 72
              BYTES). Said here in characters, which is exact for ordinary
              letters, numbers and symbols; the backend's own message covers
              the emoji case if it ever arises. */}
          {registering ? (
            <p className="hint">
              Use 8 to 72 characters, with at least one uppercase letter, one
              lowercase letter, one number and one symbol (such as ! @ # or ?).
            </p>
          ) : null}

          {error ? (
            <p className="error" role="alert">
              {error.message}
            </p>
          ) : null}

          {/*
            WHY THIS IS A SEPARATE HINT AND NOT A BETTER ERROR MESSAGE.

            "No account exists for this email" would be the clearest possible
            copy, and we deliberately do not say it. Saying it turns the login
            form into an oracle: anyone could type an address and learn whether
            that person holds a VaidyaAI account -- which, for a service that
            exists to interpret someone's medical results, discloses something
            about their health situation to a stranger. The backend refuses to
            leak it (`authController.login` returns one message and takes one
            code path whether the email is unknown or the password is wrong),
            so the client must not reconstruct it either.

            What a user who mistyped and a user who never registered BOTH need
            is the same thing: a way forward. Offering that unconditionally on
            a failed sign-in helps the second user without telling the first
            one anything about the first.
          */}
          {error && error.code === 'INVALID_CREDENTIALS' && !registering ? (
            <p className="hint">
              If you have not signed up yet,{' '}
              <button
                type="button"
                className="link"
                onClick={() => {
                  setMode('register');
                  setError(null);
                }}
              >
                create an account
              </button>
              .
            </p>
          ) : null}

          <button type="submit" disabled={busy}>
            {busy ? 'Working…' : registering ? 'Create account' : 'Sign in'}
          </button>

          <button
            type="button"
            className="link"
            onClick={() => {
              setMode(registering ? 'signIn' : 'register');
              setError(null);
              setConfirm('');
            }}
          >
            {registering ? 'I already have an account' : 'Create an account'}
          </button>
        </form>
      </div>
    </main>
  );
}
