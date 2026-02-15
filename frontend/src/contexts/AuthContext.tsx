import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { User as FirebaseUser } from 'firebase/auth';
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut,
} from 'firebase/auth';

import { auth } from '../config/firebase';
import { getMe, setAuthToken } from '../api/client';
import type { UserProfile } from '../types';

interface AuthContextValue {
  firebaseUser: FirebaseUser | null;
  user: UserProfile | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshProfile = async () => {
    const profile = await getMe();
    setUser(profile);
  };

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (nextUser) => {
      setFirebaseUser(nextUser);
      if (!nextUser) {
        setAuthToken(null);
        setUser(null);
        setLoading(false);
        return;
      }

      const idToken = await nextUser.getIdToken();
      setAuthToken(idToken);
      await refreshProfile();
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      firebaseUser,
      user,
      loading,
      async login(email, password) {
        await signInWithEmailAndPassword(auth, email, password);
      },
      async register(email, password) {
        await createUserWithEmailAndPassword(auth, email, password);
      },
      async logout() {
        await signOut(auth);
        setAuthToken(null);
        setUser(null);
      },
      refreshProfile,
    }),
    [firebaseUser, user, loading]
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
