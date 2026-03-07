/**
 * Auth Callback Page
 * Handles returning from Firebase redirect (legacy/fallback) or direct visits.
 * Primary sign-in now uses signInWithPopup from Login/Register pages.
 * This page remains for:
 *   1. Processing any pending redirect result (getRedirectResult)
 *   2. Recovering an existing Firebase session (currentUser / onAuthStateChanged)
 *   3. Graceful error display if no session is found
 */

import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { onAuthStateChanged, type User } from 'firebase/auth';

import { useAuth } from '../contexts/AuthContext';
import { auth } from '../config/firebase';
import { APIClientError, setAuthToken } from '../api/client';

type AuthStatus = 'processing' | 'success' | 'error' | 'timeout';

const AUTH_TIMEOUT_MS = 30000;
const HYDRATION_WAIT_MS = 10000;

function summarizeAuthError(error: unknown): string {
  if (error instanceof APIClientError) {
    return `status=${error.status} type=${error.errorType} message=${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export function AuthCallbackPage() {
  const navigate = useNavigate();
  const { getRedirectResultForCallback, refreshProfile } = useAuth();
  const [status, setStatus] = useState<AuthStatus>('processing');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const processedRef = useRef(false);

  const goToLogin = () => navigate('/login', { replace: true });

  useEffect(() => {
    if (processedRef.current) return;
    processedRef.current = true;

    const logStep = (step: string, details?: Record<string, unknown>) => {
      if (details) {
        console.info(`[AuthCallback] ${step}`, details);
        return;
      }
      console.info(`[AuthCallback] ${step}`);
    };

    const setTokenWithLog = (token: string, source: string) => {
      setAuthToken(token);
      logStep('token_set', { source, tokenLength: token.length });
    };

    const waitForFirebaseUser = (): Promise<User | null> => {
      const firebaseAuth = auth;
      if (!firebaseAuth) return Promise.resolve(null);
      if (firebaseAuth.currentUser) return Promise.resolve(firebaseAuth.currentUser);
      return new Promise<User | null>((resolve) => {
        let settled = false;
        let unsubscribe: (() => void) | null = null;
        const settle = (user: User | null) => {
          if (settled) return;
          settled = true;
          window.clearTimeout(tid);
          unsubscribe?.();
          resolve(user);
        };
        const tid = window.setTimeout(() => {
          settle(firebaseAuth.currentUser);
        }, HYDRATION_WAIT_MS);
        unsubscribe = onAuthStateChanged(firebaseAuth, (nextUser) => {
          if (nextUser) settle(nextUser);
        });
      });
    };

    const authenticateWithUser = async (
      fbUser: User,
      source: string,
    ): Promise<boolean> => {
      const timeoutId = setTimeout(() => {
        logStep('authenticate:timeout');
        setStatus('timeout');
        setErrorMessage('Authentication timed out. Please try again.');
      }, AUTH_TIMEOUT_MS);
      try {
        const idToken = await fbUser.getIdToken();
        setTokenWithLog(idToken, source);
        logStep('refresh_profile:start', { source });
        await refreshProfile();
        logStep('refresh_profile:success', { source });
        clearTimeout(timeoutId);
        setStatus('success');
        navigate('/projects', { replace: true });
        return true;
      } catch (firstErr) {
        logStep('refresh_profile:error', {
          source,
          detail: summarizeAuthError(firstErr),
        });
        try {
          const refreshedToken = await fbUser.getIdToken(true);
          setTokenWithLog(refreshedToken, `${source}_forced_refresh`);
          await refreshProfile();
          clearTimeout(timeoutId);
          setStatus('success');
          navigate('/projects', { replace: true });
          return true;
        } catch (retryErr) {
          clearTimeout(timeoutId);
          logStep('authenticate:retry_failed', {
            detail: summarizeAuthError(retryErr),
          });
          return false;
        }
      }
    };

    const processAuthResult = async () => {
      logStep('process_start', {
        hasFirebaseAuth: Boolean(auth),
        href: window.location.href,
      });

      // 1. Try pending redirect result (legacy redirect flow / returning from Google).
      if (auth) {
        try {
          logStep('get_redirect_result:start');
          const result = await getRedirectResultForCallback();
          logStep('get_redirect_result:done', { hasUser: Boolean(result?.user) });
          if (result?.user) {
            if (await authenticateWithUser(result.user, 'redirect_result')) return;
          }
        } catch (err) {
          logStep('get_redirect_result:error', { detail: summarizeAuthError(err) });
          setStatus('error');
          setErrorMessage(`Authentication failed: ${summarizeAuthError(err)}`);
          return;
        }
      }

      // 2. Wait for Firebase to hydrate an existing session (currentUser / onAuthStateChanged).
      logStep('waiting_for_firebase_user', { waitMs: HYDRATION_WAIT_MS });
      const currentUser = await waitForFirebaseUser();
      if (currentUser) {
        logStep('firebase_user_found', { uid: currentUser.uid });
        if (await authenticateWithUser(currentUser, 'existing_firebase_user')) return;
      }

      // 3. Seeded-token fallback (dev / E2E).
      if (!auth) {
        const seededToken = localStorage.getItem('auth_token');
        if (seededToken) {
          setTokenWithLog(seededToken, 'seeded_token_fallback');
          try {
            await refreshProfile();
            setStatus('success');
            navigate('/projects', { replace: true });
            return;
          } catch {
            // fall through
          }
        }
      }

      // 4. Nothing worked — show error.
      logStep('no_recoverable_auth_state');
      setStatus('error');
      setErrorMessage(
        'No authenticated session found. Please go back to login and sign in again.',
      );
    };

    void processAuthResult();
  }, [navigate, getRedirectResultForCallback, refreshProfile]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md bg-white border rounded-lg p-8 space-y-6 text-center">
        {status === 'processing' && (
          <>
            <div className="flex justify-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Processing Authentication</h1>
            <p className="text-sm text-gray-600">
              Please wait while we verify your Google sign-in...
            </p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="flex justify-center">
              <div className="h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                <svg className="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Authentication Successful</h1>
            <p className="text-sm text-gray-600">Redirecting you to the application...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="flex justify-center">
              <div className="h-12 w-12 rounded-full bg-red-100 flex items-center justify-center">
                <svg className="h-6 w-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Authentication Failed</h1>
            <p className="text-sm text-red-600">{errorMessage}</p>
            <button
              type="button"
              onClick={goToLogin}
              className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Back to Login
            </button>
          </>
        )}

        {status === 'timeout' && (
          <>
            <div className="flex justify-center">
              <div className="h-12 w-12 rounded-full bg-yellow-100 flex items-center justify-center">
                <svg className="h-6 w-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Authentication Timed Out</h1>
            <p className="text-sm text-gray-600">{errorMessage}</p>
            <button
              type="button"
              onClick={goToLogin}
              className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Back to Login
            </button>
          </>
        )}
      </div>
    </div>
  );
}
