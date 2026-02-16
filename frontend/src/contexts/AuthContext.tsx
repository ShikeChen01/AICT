import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { User as FirebaseUser } from 'firebase/auth';
import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithRedirect,
  signOut,
} from 'firebase/auth';

import { auth } from '../config/firebase';
import { APIClientError, getMe, getAuthToken, setAuthToken } from '../api/client';
import type { UserProfile } from '../types';

interface AuthContextValue {
  firebaseUser: FirebaseUser | null;
  user: UserProfile | null;
  loading: boolean;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const googleProvider = useMemo(() => {
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: 'select_account' });
    return provider;
  }, []);

  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshProfile = useCallback(async () => {
    const profile = await getMe();
    setUser(profile);
  }, []);

  const signInWithSeededToken = useCallback(async () => {
    const tokenFromStorage = localStorage.getItem('auth_token');
    const tokenFromEnv = import.meta.env.VITE_API_TOKEN as string | undefined;
    const token = tokenFromStorage || tokenFromEnv || null;
    if (!token) {
      throw new Error(
        'Google sign-in is not configured. Set VITE_FIREBASE_* or seed localStorage.auth_token.'
      );
    }

    setLoading(true);
    setAuthToken(token);
    try {
      await refreshProfile();
    } catch (error) {
      setAuthToken(null);
      setUser(null);
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Token sign-in failed: ${message}`);
    } finally {
      setLoading(false);
    }
  }, [refreshProfile]);

  useEffect(() => {
    let active = true;

    const clearSession = () => {
      setAuthToken(null);
      setUser(null);
      setFirebaseUser(null);
    };

    // E2E/dev fallback: allow pre-seeded token from localStorage.
    const bootstrapFromSeededToken = async () => {
      const seededToken = localStorage.getItem('auth_token');
      if (!seededToken || getAuthToken()) return false;
      setAuthToken(seededToken);
      try {
        await refreshProfile();
        return true;
      } catch {
        setAuthToken(null);
        setUser(null);
        return false;
      }
    };

    const bootstrapFirebaseSession = async (nextUser: FirebaseUser | null) => {
      setFirebaseUser(nextUser);
      if (!nextUser) {
        const seededToken = getAuthToken();
        if (seededToken) {
          try {
            if (active) setLoading(true);
            await refreshProfile();
            if (active) setLoading(false);
            return;
          } catch {
            // fall through to clear session
          }
        }
        clearSession();
        if (active) setLoading(false);
        return;
      }

      try {
        if (active) setLoading(true);
        const idToken = await nextUser.getIdToken();
        setAuthToken(idToken);
        await refreshProfile();
      } catch (error) {
        // Retry once with a forced token refresh for first-load 401 races.
        if (error instanceof APIClientError && (error.status === 401 || error.status === 422)) {
          try {
            const refreshedToken = await nextUser.getIdToken(true);
            setAuthToken(refreshedToken);
            await refreshProfile();
          } catch {
            clearSession();
          }
        } else {
          clearSession();
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    void (async () => {
      // If we can restore a seeded token, avoid the auth-loading deadlock in tests/dev.
      if (await bootstrapFromSeededToken()) {
        if (active) setLoading(false);
        return;
      }
      if (!auth && active) {
        setLoading(false);
      }
    })();

    if (!auth) {
      return () => {
        active = false;
      };
    }

    const unsubscribe = onAuthStateChanged(auth, (nextUser) => {
      void bootstrapFirebaseSession(nextUser);
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, [refreshProfile]);

  const value = useMemo<AuthContextValue>(
    () => ({
      firebaseUser,
      user,
      loading,
      async loginWithGoogle() {
        if (!auth) {
          // Fallback for dev/testing without Firebase
          await signInWithSeededToken();
          return;
        }
        // Use redirect-based authentication
        // This will redirect the user to Google, then back to the app
        // The AuthCallback page will handle getRedirectResult
        await signInWithRedirect(auth, googleProvider);
      },
      async logout() {
        if (!auth) {
          setAuthToken(null);
          setUser(null);
          return;
        }
        await signOut(auth);
        setAuthToken(null);
        setUser(null);
      },
      refreshProfile,
    }),
    [firebaseUser, user, loading, googleProvider, signInWithSeededToken, refreshProfile]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
