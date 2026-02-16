/**
 * Firebase Configuration
 * Initialize Firebase with environment variables for Google authentication.
 *
 * Google Sign-In redirect: Set the Authorized redirect URI to the exact callback URL
 * so the user lands on /auth/callback with the OAuth hash intact.
 * - Firebase Console: Authentication → Sign-in method → Google
 * - Google Cloud Console: APIs & Services → Credentials → OAuth 2.0 client
 * Example (local): http://localhost:5173/auth/callback
 * Example (prod): https://your-domain.com/auth/callback
 */

import { initializeApp, getApps, type FirebaseApp } from 'firebase/app';
import { getAuth, type Auth } from 'firebase/auth';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET as string | undefined,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID as string | undefined,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string | undefined,
};

// Only initialize Firebase if config is provided
const isConfigured = Boolean(firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId);

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

if (isConfigured) {
  app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];
  auth = getAuth(app);
}

export { auth, app };
export const isFirebaseConfigured = isConfigured;
