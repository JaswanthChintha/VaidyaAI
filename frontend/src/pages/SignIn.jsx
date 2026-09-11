import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import ThemeToggle from '../components/ThemeToggle';

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
  // { message, code } | null. The CODE is kept so the form can offer the
  // right next step without the SERVER having to say what went wrong.
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
      setError({ message: err.message, code: err.code });
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
        <h1>
          Vaidya<em>AI</em>
        </h1>
        <ThemeToggle />
      </div>
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
          }}
        >
          {registering ? 'I already have an account' : 'Create an account'}
        </button>
      </form>
    </main>
  );
}
