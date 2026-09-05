import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';

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

  const [mode, setMode] = useState('signIn');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const registering = mode === 'register';

  async function onSubmit(event) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (registering) {
        await register({ name, email, password });
      } else {
        await signIn(email, password);
      }
      navigate('/reports');
    } catch (err) {
      // The backend's messages are fixed strings written to be shown; they
      // never echo input and never disclose whether an account exists.
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <h1>VaidyaAI</h1>
      <p className="auth__tagline">
        Understand your laboratory reports. This is health education and
        decision support, not a diagnosis.
      </p>

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
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete={registering ? 'new-password' : 'current-password'}
          />
        </label>

        {registering ? (
          <p className="hint">
            At least 8 characters, including an uppercase letter, a lowercase
            letter, a number and a special character. Passwords longer than 72
            bytes are not accepted &mdash; the hashing algorithm ignores
            anything past that, so a longer one would be misleading rather
            than stronger.
          </p>
        ) : null}

        {error ? (
          <p className="error" role="alert">
            {error}
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
          }}
        >
          {registering ? 'I already have an account' : 'Create an account'}
        </button>
      </form>
    </main>
  );
}
