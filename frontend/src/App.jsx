import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './lib/auth';
import SignIn from './pages/SignIn';
import Profile from './pages/Profile';
import Reports from './pages/Reports';

/**
 * `checking` is a real state and is rendered as one.
 *
 * On a reload we hold a refresh token but do not yet know whether the server
 * still honours it. Guessing either way is wrong: guess signed-out and a
 * signed-in patient is bounced to the login screen on every refresh; guess
 * signed-in and a dashboard flashes up before 401ing. So the unknown waits.
 */
function RequireAuth({ children }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'checking') return <p className="loading">Checking your session…</p>;
  if (status !== 'signedIn') return <Navigate to="/signin" state={{ from: location }} replace />;
  return children;
}

function Nav() {
  const { status, user, signOut } = useAuth();
  if (status !== 'signedIn') return null;
  return (
    <nav className="nav">
      <span className="nav__brand">VaidyaAI</span>
      <Link to="/reports">Reports</Link>
      <Link to="/profile">Your details</Link>
      <span className="nav__spacer" />
      <span className="nav__user">{user?.name || user?.email}</span>
      <button type="button" className="link" onClick={signOut}>
        Sign out
      </button>
    </nav>
  );
}

/**
 * The standing disclaimer.
 *
 * Spec section 1 is explicit that this is an AI-assisted education and
 * decision-support platform and NOT an autonomous diagnostic system. Every
 * layer beneath carries that statement in its payloads; it belongs on the
 * screen too, on every page rather than once at sign-up where it would be
 * read once and forgotten.
 */
function Disclaimer() {
  return (
    <footer className="disclaimer">
      VaidyaAI explains laboratory results for education and discussion. It
      does not diagnose, and it is not a substitute for advice from a
      qualified healthcare professional.
    </footer>
  );
}

export default function App() {
  const { status } = useAuth();

  return (
    <div className="app">
      <Nav />
      <Routes>
        <Route
          path="/signin"
          element={status === 'signedIn' ? <Navigate to="/reports" replace /> : <SignIn />}
        />
        <Route
          path="/reports"
          element={
            <RequireAuth>
              <Reports />
            </RequireAuth>
          }
        />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <Profile />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to={status === 'signedIn' ? '/reports' : '/signin'} replace />} />
      </Routes>
      <Disclaimer />
    </div>
  );
}
