import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './lib/auth';
import ThemeToggle from './components/ThemeToggle';
import Icon from './components/Icon';
import Logo from './components/Logo';
import ChatBot from './components/ChatBot';
import Landing from './pages/Landing';
import SignIn from './pages/SignIn';
import Profile from './pages/Profile';
import Reports from './pages/Reports';
import Dashboard from './pages/Dashboard';
import Timeline from './pages/Timeline';
import DoctorSummary from './pages/DoctorSummary';
import Population from './pages/Population';

function RequireAuth({ children }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'checking') return <p className="loading">Checking your session…</p>;
  if (status !== 'signedIn') return <Navigate to="/signin" state={{ from: location }} replace />;
  return children;
}

function Nav() {
  const { status, user, signOut } = useAuth();
  const onLanding = useLocation().pathname === '/';
  if (status !== 'signedIn' || onLanding) return null;
  const who = user?.name || user?.email || '';
  return (
    <nav className="nav" aria-label="Main">
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
  const onLanding = useLocation().pathname === '/';

  return (
    <div className={status === 'signedIn' && !onLanding ? 'app app--shell' : 'app'}>
      <Nav />
      <Routes>
        <Route path="/" element={<Landing />} />
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
      {status === 'signedIn' && !onLanding ? <ChatBot /> : null}
    </div>
  );
}
