import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { User as FirebaseUser, UserCredential } from 'firebase/auth';
import {
  getRedirectResult,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
} from 'firebase/auth';

import { auth } from '../config/firebase';
import { APIClientError, getMe, getAuthToken, setAuthToken } from '../api/client';
import type { UserProfile } from '../types';

interface AuthContextValue {
  firebaseUser: FirebaseUser | null;
  user: UserProfile | null;
  loading: boolean;
  /** Single redirect result for this page load (survives Strict Mode remount). Call once from callback page. */
  getRedirectResultForCallback: () => Promise<UserCredential | null>;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const AUTH_CONTEXT_LOG_PREFIX = '[AuthContext]';

function summarizeAuthError(error: unknown): string {
  if (error instanceof APIClientError) {
    return `status=${error.status} type=${error.errorType} message=${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function isAuthRejectedError(error: unknown): boolean {
  return error instanceof APIClientError && (error.status === 401 || error.status === 422);
}

function logAuthStep(step: string, details?: Record<string, unknown>) {
  if (details) {
    console.info(`${AUTH_CONTEXT_LOG_PREFIX} ${step}`, details);
    return;
  }
  console.info(`${AUTH_CONTEXT_LOG_PREFIX} ${step}`);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const googleProvider = useMemo(() => {
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: 'select_account' });
    return provider;
  }, []);

  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const redirectResultPromiseRef = useRef<Promise<UserCredential | null> | null>(null);
  const getRedirectResultForCallback = useCallback((): Promise<UserCredential | null> => {
    if (redirectResultPromiseRef.current != null) {
      return redirectResultPromiseRef.current;
    }
    if (!auth) {
      return Promise.resolve(null);
    }
    redirectResultPromiseRef.current = getRedirectResult(auth);
    return redirectResultPromiseRef.current;
  }, []);

  const setTokenWithLog = useCallback((token: string | null, source: string) => {
    setAuthToken(token);
    logAuthStep(token ? 'token_set' : 'token_cleared', {
      source,
      tokenLength: token?.length ?? 0,
    });
  }, []);

  const refreshProfile = useCallback(async () => {
    logAuthStep('refresh_profile:start');
    try {
      const profile = await getMe();
      setUser(profile);
      logAuthStep('refresh_profile:success', {
        hasDisplayName: Boolean(profile.display_name),
        githubTokenSet: profile.github_token_set,
      });
    } catch (error) {
      logAuthStep('refresh_profile:error', { detail: summarizeAuthError(error) });
      throw error;
    }
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
    setTokenWithLog(token, 'signInWithSeededToken');
    try {
      await refreshProfile();
    } catch (error) {
      setTokenWithLog(null, 'signInWithSeededToken_error');
      setUser(null);
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Token sign-in failed: ${message}`);
    } finally {
      setLoading(false);
    }
  }, [refreshProfile, setTokenWithLog]);

  useEffect(() => {
    let active = true;

    const clearSession = (reason: string) => {
      logAuthStep('clear_session', { reason });
      setTokenWithLog(null, `clearSession:${reason}`);
      setUser(null);
      setFirebaseUser(null);
    };

    // E2E/dev fallback: allow pre-seeded token from localStorage.
    const bootstrapFromSeededToken = async () => {
      const seededToken = localStorage.getItem('auth_token');
      logAuthStep('bootstrap_seeded_token:check', {
        hasSeededToken: Boolean(seededToken),
        hasInMemoryToken: Boolean(getAuthToken()),
      });
      if (!seededToken || getAuthToken()) return false;
      setTokenWithLog(seededToken, 'bootstrap_seeded_token');
      try {
        await refreshProfile();
        logAuthStep('bootstrap_seeded_token:success');
        return true;
      } catch (error) {
        if (isAuthRejectedError(error)) {
          setTokenWithLog(null, 'bootstrap_seeded_token_invalid');
          setUser(null);
          logAuthStep('bootstrap_seeded_token:failed_invalid_token');
          return false;
        }
        logAuthStep('bootstrap_seeded_token:non_auth_error', {
          detail: summarizeAuthError(error),
        });
        return true;
      }
    };

    const bootstrapFirebaseSession = async (nextUser: FirebaseUser | null) => {
      logAuthStep('firebase_auth_state_changed', { hasUser: Boolean(nextUser) });
      setFirebaseUser(nextUser);
      if (!nextUser) {
        const inMemoryToken = getAuthToken();
        const persistedSeededToken = localStorage.getItem('auth_token');
        const seededToken = inMemoryToken || persistedSeededToken;
        if (!inMemoryToken && persistedSeededToken) {
          setTokenWithLog(persistedSeededToken, 'firebase_no_user_restore_seeded_token');
        }
        if (seededToken) {
          try {
            if (active) setLoading(true);
            await refreshProfile();
            if (active) setLoading(false);
            return;
          } catch (error) {
            // fall through to clear session
            logAuthStep('firebase_session:no_user_refresh_failed', {
              detail: summarizeAuthError(error),
            });
            if (!isAuthRejectedError(error)) {
              if (active) setLoading(false);
              return;
            }
          }
        }
        clearSession('firebase_no_user');
        if (active) setLoading(false);
        return;
      }

      try {
        if (active) setLoading(true);
        logAuthStep('firebase_session:get_id_token:start');
        const idToken = await nextUser.getIdToken();
        setTokenWithLog(idToken, 'firebase_session_primary');
        await refreshProfile();
      } catch (error) {
        // Retry once with a forced token refresh for first-load 401 races.
        if (isAuthRejectedError(error)) {
          try {
            logAuthStep('firebase_session:get_id_token:force_refresh');
            const refreshedToken = await nextUser.getIdToken(true);
            setTokenWithLog(refreshedToken, 'firebase_session_forced_refresh');
            await refreshProfile();
          } catch {
            clearSession('firebase_forced_refresh_failed');
          }
        } else {
          logAuthStep('firebase_session:failed', { detail: summarizeAuthError(error) });
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
      logAuthStep('on_auth_state_changed:callback', { hasUser: Boolean(nextUser) });
      void bootstrapFirebaseSession(nextUser);
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, [refreshProfile, setTokenWithLog]);

  const value = useMemo<AuthContextValue>(
    () => ({
      firebaseUser,
      user,
      loading,
      getRedirectResultForCallback,
      async loginWithGoogle() {
        if (!auth) {
          // Fallback for dev/testing without Firebase
          await signInWithSeededToken();
          return;
        }
        // Popup-based authentication: avoids cross-domain issues that break
        // signInWithRedirect when third-party cookies are blocked (Chrome default).
        // The result is returned directly; no getRedirectResult needed.
        const result = await signInWithPopup(auth, googleProvider);
        if (result.user) {
          logAuthStep('popup_sign_in:success', { uid: result.user.uid });
          const idToken = await result.user.getIdToken();
          setTokenWithLog(idToken, 'popup_sign_in');
          await refreshProfile();
        }
      },
      async logout() {
        logAuthStep('logout:start', { hasFirebaseAuth: Boolean(auth) });
        if (!auth) {
          setTokenWithLog(null, 'logout_without_firebase');
          setUser(null);
          return;
        }
        await signOut(auth);
        setTokenWithLog(null, 'logout_after_signout');
        setUser(null);
      },
      refreshProfile,
    }),
    [firebaseUser, user, loading, getRedirectResultForCallback, googleProvider, signInWithSeededToken, refreshProfile, setTokenWithLog]
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
