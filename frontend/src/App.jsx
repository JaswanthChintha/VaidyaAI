import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './lib/auth';
import ThemeToggle from './components/ThemeToggle';
import Icon from './components/Icon';
import Logo from './components/Logo';
import Landing from './pages/Landing';
import SignIn from './pages/SignIn';
import Profile from './pages/Profile';
import Reports from './pages/Reports';
import Dashboard from './pages/Dashboard';
import Timeline from './pages/Timeline';
import DoctorSummary from './pages/DoctorSummary';
import Population from './pages/Population';

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
  const who = user?.name || user?.email || '';
  return (
    // A sidebar from 900px up, a wrapping top bar below it -- one element,
    // laid out by the stylesheet, so the two cannot drift apart.
    <nav className="nav" aria-label="Main">
      {/* The wordmark carries the one italic serif flourish in the app. */}
      <Link to="/reports" className="nav__brand">
        <Logo size={32} className="nav__mark" />
        <span>
          Vaidya<em>AI</em>
        </span>
      </Link>
      <NavLink to="/reports">
        <Icon name="reports" />
        <span>Reports</span>
      </NavLink>
      <NavLink to="/timeline">
        <Icon name="timeline" />
        <span>Timeline</span>
      </NavLink>
      <NavLink to="/profile">
        <Icon name="profile" />
        <span>Your details</span>
      </NavLink>
      <span className="nav__spacer" />
      <span className="nav__user" title={who}>
        <span className="nav__avatar" aria-hidden="true">
          {who.trim().charAt(0).toUpperCase() || '?'}
        </span>
        <span className="nav__who">{who}</span>
      </span>
      <ThemeToggle />
      <button type="button" className="link nav__signout" onClick={signOut} aria-label="Sign out">
        <Icon name="signout" size={18} />
        <span>Sign out</span>
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
  // The landing page carries its own footer with the same statement.
  const onLanding = useLocation().pathname === '/';

  return (
    <div className={status === 'signedIn' ? 'app app--shell' : 'app'}>
      <Nav />
      <Routes>
        <Route
          path="/"
          element={
            status === 'signedIn' ? (
              <Navigate to="/reports" replace />
            ) : status === 'checking' ? (
              // A returning reader holds a session; do not flash the
              // marketing page at them while it is confirmed.
              <p className="loading">Checking your session…</p>
            ) : (
              <Landing />
            )
          }
        />
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
          path="/reports/:id"
          element={
            <RequireAuth>
              <Dashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/reports/:id/doctor-summary"
          element={
            <RequireAuth>
              <DoctorSummary />
            </RequireAuth>
          }
        />
        <Route
          path="/reports/:id/population"
          element={
            <RequireAuth>
              <Population />
            </RequireAuth>
          }
        />
        <Route
          path="/timeline"
          element={
            <RequireAuth>
              <Timeline />
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
        <Route path="*" element={<Navigate to={status === 'signedIn' ? '/reports' : '/'} replace />} />
      </Routes>
      {onLanding ? null : <Disclaimer />}
    </div>
  );
}
