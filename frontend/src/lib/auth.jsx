import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, clearSession, hasSession, refreshSession, setSession } from './api';

const AuthContext = createContext(null);

/**
 * Who is signed in, and the three operations that change that.
 *
 * `status` is a three-state, not a boolean: `checking` exists because on a
 * reload we hold a refresh token but do not yet know whether the server still
 * honours it. Collapsing that into `signedIn: false` would bounce a signed-in
 * patient to the login screen on every refresh; collapsing it into `true`
 * would flash a dashboard that is about to 401. Neither is acceptable, so the
 * unknown is represented rather than guessed -- the same rule the rest of this
 * platform applies to clinical values.
 */
export function AuthProvider({ children }) {
  const [status, setStatus] = useState(hasSession() ? 'checking' : 'signedOut');
  const [user, setUser] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (status !== 'checking') return undefined;

    (async () => {
      // A stored refresh token proves nothing: it may have been rotated,
      // revoked by a password change, or simply expired. Exchange it before
      // claiming a session.
      const ok = await refreshSession();
      if (cancelled) return;
      if (!ok) {
        setStatus('signedOut');
        return;
      }
      try {
        const me = await api.me();
        if (cancelled) return;
        setUser(me.user || me);
        setStatus('signedIn');
      } catch {
        if (cancelled) return;
        clearSession();
        setStatus('signedOut');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [status]);

  const signIn = useCallback(async (email, password) => {
    const data = await api.login({ email, password });
    setSession(data);
    setUser(data.user);
    setStatus('signedIn');
  }, []);

  const register = useCallback(async (payload) => {
    const data = await api.register(payload);
    setSession(data);
    setUser(data.user);
    setStatus('signedIn');
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // Logout is session-scoped server-side and best-effort here: a failed
      // call must still clear this device, or a patient who pressed "sign
      // out" on a shared machine stays signed in.
    }
    clearSession();
    setUser(null);
    setStatus('signedOut');
  }, []);

  const value = useMemo(
    () => ({ status, user, signIn, register, signOut }),
    [status, user, signIn, register, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside an AuthProvider');
  return context;
}
