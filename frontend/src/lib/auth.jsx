import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  api,
  clearSession,
  hasSession,
  isSessionRejected,
  refreshSession,
  setSession,
} from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(hasSession() ? 'checking' : 'signedOut');
  const [user, setUser] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (status !== 'checking') return undefined;

    (async () => {
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
      } catch (error) {
        if (cancelled) return;
        if (isSessionRejected(error)) clearSession();
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
    }
    clearSession();
    setUser(null);
    setStatus('signedOut');
  }, []);

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    const data = await api.changePassword(currentPassword, newPassword);
    setSession(data);
    if (data.user) setUser(data.user);
  }, []);

  const deleteAccount = useCallback(async (password) => {
    await api.deleteAccount(password);
    clearSession();
    setUser(null);
    setStatus('signedOut');
  }, []);

  const value = useMemo(
    () => ({ status, user, signIn, register, signOut, changePassword, deleteAccount }),
    [status, user, signIn, register, signOut, changePassword, deleteAccount]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside an AuthProvider');
  return context;
}
