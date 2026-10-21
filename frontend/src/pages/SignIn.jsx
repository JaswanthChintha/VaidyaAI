import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import ThemeToggle from '../components/ThemeToggle';
import Icon from '../components/Icon';

export default function SignIn() {
  const { signIn, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [mode, setMode] = useState(location.state?.mode === 'register' ? 'register' : 'signIn');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
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
        navigate('/profile', { state: { welcome: true } });
        return;
      }
      await signIn(email, password);
      navigate('/reports');
    } catch (err) {
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
