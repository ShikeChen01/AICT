import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { signInWithCustomToken } from 'firebase/auth';

import { auth } from '../config/firebase';
import { oauthCallback, setAuthToken } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

type CallbackStatus = 'processing' | 'success' | 'error';

export function OpenAICallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { refreshProfile } = useAuth();
  const [status, setStatus] = useState<CallbackStatus>('processing');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;
    processedRef.current = true;

    const processCallback = async () => {
      const code = searchParams.get('code');
      const state = searchParams.get('state');

      if (!code || !state) {
        setStatus('error');
        setErrorMessage('Missing authorization code. Please try again.');
        return;
      }

      try {
        const result = await oauthCallback(code, state);

        if (result.error) {
          setStatus('error');
          setErrorMessage(result.message || result.error);
          return;
        }

        if (result.firebase_custom_token) {
          if (auth) {
            const cred = await signInWithCustomToken(auth, result.firebase_custom_token);
            const idToken = await cred.user.getIdToken();
            setAuthToken(idToken);
          } else {
            setAuthToken(result.firebase_custom_token);
          }
          await refreshProfile();
          setStatus('success');
          navigate('/projects', { replace: true });
          return;
        }

        if (result.connected) {
          setStatus('success');
          navigate('/settings', { replace: true });
          return;
        }

        setStatus('error');
        setErrorMessage('Unexpected response from server.');
      } catch (err) {
        setStatus('error');
        setErrorMessage(err instanceof Error ? err.message : 'Authentication failed');
      }
    };

    void processCallback();
  }, [searchParams, navigate, refreshProfile]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md bg-white border rounded-lg p-8 space-y-6 text-center">
        {status === 'processing' && (
          <>
            <div className="flex justify-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600"></div>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Signing in with OpenAI</h1>
            <p className="text-sm text-gray-600">Please wait...</p>
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
            <h1 className="text-xl font-semibold text-gray-900">Success</h1>
            <p className="text-sm text-gray-600">Redirecting...</p>
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
              onClick={() => navigate('/login', { replace: true })}
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
