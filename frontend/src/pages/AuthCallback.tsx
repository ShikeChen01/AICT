/**
 * Auth Callback Page
 * Intermediate page that processes Firebase redirect authentication results.
 * Shows loading state while processing, handles success/failure/timeout.
 */

import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { getRedirectResult } from 'firebase/auth';

import { useAuth } from '../contexts/AuthContext';
import { auth } from '../config/firebase';
import { setAuthToken, getMe } from '../api/client';

type AuthStatus = 'processing' | 'success' | 'error' | 'timeout';

const AUTH_TIMEOUT_MS = 30000; // 30 seconds timeout

export function AuthCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { loginWithGoogle } = useAuth();
  const [status, setStatus] = useState<AuthStatus>('processing');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const processedRef = useRef(false);

  useEffect(() => {
    // Prevent double processing in React strict mode
    if (processedRef.current) return;
    processedRef.current = true;

    const processAuthResult = async () => {
      // Always check for redirect result first. When user returns from Google they land here
      // (sometimes still with ?mode=google). If we see mode=google before checking result,
      // we'd start another redirect and send them back to Google.
      if (auth) {
        let result;
        try {
          result = await getRedirectResult(auth);
        } catch (err) {
          setStatus('error');
          setErrorMessage(err instanceof Error ? err.message : 'Authentication failed');
          setTimeout(() => {
            navigate('/login?error=' + encodeURIComponent('Authentication failed'), { replace: true });
          }, 2000);
          return;
        }
        if (result?.user) {
          // User just returned from Google – process the result (no new redirect).
          const timeoutId = setTimeout(() => {
            setStatus('timeout');
            setErrorMessage('Authentication timed out. Please try again.');
            setTimeout(() => {
              navigate('/login?error=' + encodeURIComponent('Authentication timed out'), { replace: true });
            }, 2000);
          }, AUTH_TIMEOUT_MS);
          try {
            const idToken = await result.user.getIdToken();
            setAuthToken(idToken);
            try {
              await getMe();
              clearTimeout(timeoutId);
              setStatus('success');
              setTimeout(() => navigate('/repositories', { replace: true }), 500);
              return;
            } catch {
              const refreshedToken = await result.user.getIdToken(true);
              setAuthToken(refreshedToken);
              await getMe();
              clearTimeout(timeoutId);
              setStatus('success');
              setTimeout(() => navigate('/repositories', { replace: true }), 500);
              return;
            }
          } catch (backendError) {
            clearTimeout(timeoutId);
            setStatus('error');
            setErrorMessage('Failed to verify authentication with server.');
            setTimeout(() => {
              navigate('/login?error=' + encodeURIComponent('Server verification failed'), { replace: true });
            }, 2000);
            return;
          }
        }
      }

      // No redirect result: either we're here to start the flow (mode=google) or user opened URL directly.
      const mode = searchParams.get('mode');
      if (mode === 'google') {
        try {
          await loginWithGoogle();
          navigate('/repositories', { replace: true });
        } catch (err) {
          setStatus('error');
          setErrorMessage(err instanceof Error ? err.message : 'Failed to start sign-in');
          setTimeout(() => {
            navigate('/login?error=' + encodeURIComponent('Failed to start sign-in'), { replace: true });
          }, 2000);
        }
        return;
      }

      if (!auth) {
        // Firebase not configured, try seeded token fallback
        const seededToken = localStorage.getItem('auth_token');
        if (seededToken) {
          setAuthToken(seededToken);
          try {
            await getMe();
            setStatus('success');
            navigate('/repositories', { replace: true });
            return;
          } catch {
            // Fall through to error
          }
        }
        setStatus('error');
        setErrorMessage('Firebase authentication is not configured.');
        setTimeout(() => {
          navigate('/login?error=' + encodeURIComponent('Authentication not configured'), { replace: true });
        }, 2000);
        return;
      }

      // No redirect result and not mode=google: user opened /auth/callback directly
      const currentUser = auth.currentUser;
      if (currentUser) {
        try {
          const idToken = await currentUser.getIdToken();
          setAuthToken(idToken);
          await getMe();
          setStatus('success');
          navigate('/repositories', { replace: true });
          return;
        } catch {
          // Fall through to redirect login
        }
      }
      navigate('/login', { replace: true });
    };

    void processAuthResult();
  }, [navigate, searchParams, loginWithGoogle]);

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
            <p className="text-sm text-gray-600">
              Redirecting you to the application...
            </p>
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
            <p className="text-sm text-gray-600">Redirecting to login...</p>
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
            <p className="text-sm text-gray-600">Redirecting to login...</p>
          </>
        )}
      </div>
    </div>
  );
}
