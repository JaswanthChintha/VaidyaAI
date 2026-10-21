import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import Icon from './Icon';


function ChangePassword() {
  const { changePassword } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  async function onSubmit(event) {
    event.preventDefault();
    setError(null);
    setDone(false);
    if (next !== confirm) {
      setError('The new passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      await changePassword(current, next);
      setCurrent('');
      setNext('');
      setConfirm('');
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="card account__section" aria-labelledby="change-password-title">
      <h2 id="change-password-title" className="form-title">
        <span className="form-title__icon" aria-hidden="true">
          <Icon name="check" size={18} />
        </span>
        Change password
      </h2>
      <p className="hint">
        You will stay signed in here. Any other device signed in to your account
        will be signed out.
      </p>
      <label>
        Current password
        <input
          type="password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          required
          autoComplete="current-password"
        />
      </label>
      <div className="account__pair">
        <label>
          New password
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            autoComplete="new-password"
          />
        </label>
        <label>
          Confirm new password
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            autoComplete="new-password"
          />
        </label>
      </div>
      <p className="hint">
        Use 8 to 72 characters, with at least one uppercase letter, one
        lowercase letter, one number and one symbol (such as ! @ # or ?).
      </p>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {done ? (
        <p className="ok" role="status">
          Your password has been changed.
        </p>
      ) : null}
      <button type="submit" disabled={busy}>
        {busy ? 'Changing…' : 'Change password'}
      </button>
    </form>
  );
}

function DeleteAccount() {
  const { deleteAccount } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function onSubmit(event) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await deleteAccount(password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <section className="card account__section account__danger" aria-labelledby="delete-account-title">
      <h2 id="delete-account-title" className="form-title">
        <span className="form-title__icon form-title__icon--danger" aria-hidden="true">
          <Icon name="signout" size={18} />
        </span>
        Delete account
      </h2>
      <p>
        This permanently deletes your account, your details, every report you
        have uploaded and every analysis of them. It cannot be undone and
        nothing can be recovered afterwards.
      </p>
      {!open ? (
        <button type="button" className="danger" onClick={() => setOpen(true)}>
          Delete my account…
        </button>
      ) : (
        <form onSubmit={onSubmit}>
          <label>
            Enter your password to confirm
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          <label className="account__check">
            <input
              type="checkbox"
              checked={understood}
              onChange={(e) => setUnderstood(e.target.checked)}
            />
            I understand that my account and all my reports will be deleted
            permanently.
          </label>
          {error ? (
            <p className="error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="account__actions">
            <button type="submit" className="danger" disabled={busy || !understood || !password}>
              {busy ? 'Deleting…' : 'Delete my account permanently'}
            </button>
            <button
              type="button"
              className="link"
              disabled={busy}
              onClick={() => {
                setOpen(false);
                setPassword('');
                setUnderstood(false);
                setError(null);
              }}
            >
              Keep my account
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export default function AccountSettings() {
  return (
    <section className="account" aria-label="Account">
      <h2 className="account__title">Account</h2>
      <ChangePassword />
      <DeleteAccount />
    </section>
  );
}
