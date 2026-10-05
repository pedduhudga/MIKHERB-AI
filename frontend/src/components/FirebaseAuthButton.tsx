import React, { useState, useEffect } from 'react';
import { auth, isFirebaseConfigured } from '../services/firebase';
import {
  signInWithPopup,
  GoogleAuthProvider,
  signOut,
  onAuthStateChanged,
  type User
} from 'firebase/auth';
import { LogIn, LogOut, User as UserIcon, Cloud, CheckCircle, AlertCircle } from 'lucide-react';

export const FirebaseAuthButton: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isFirebaseConfigured) return;
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
    });
    return () => unsubscribe();
  }, []);

  const handleSignIn = async () => {
    if (!isFirebaseConfigured) {
      setError("Firebase credentials not configured in environment (VITE_FIREBASE_API_KEY).");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const provider = new GoogleAuthProvider();
      await signInWithPopup(auth, provider);
    } catch (err: any) {
      console.error("Firebase auth error:", err);
      setError(err?.message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSignOut = async () => {
    setLoading(true);
    try {
      await signOut(auth);
    } catch (err: any) {
      console.error("Sign out error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      {user ? (
        <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs">
          {user.photoURL ? (
            <img src={user.photoURL} alt={user.displayName || "User"} className="w-5 h-5 rounded-full" />
          ) : (
            <UserIcon className="w-4 h-4 text-emerald-400" />
          )}
          <span className="text-slate-200 font-medium truncate max-w-[120px]">{user.displayName || user.email}</span>
          <button
            onClick={handleSignOut}
            disabled={loading}
            title="Sign out from Firebase"
            className="text-slate-400 hover:text-rose-400 transition ml-1"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={handleSignIn}
            disabled={loading}
            className="flex items-center gap-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-3 py-1.5 rounded-lg text-xs font-semibold transition"
          >
            <LogIn className="w-3.5 h-3.5" />
            <span>{loading ? "Connecting..." : "Sign in (Firebase)"}</span>
          </button>
          <div className="flex items-center gap-1 text-[11px] text-slate-400" title={isFirebaseConfigured ? "Firebase Cloud Sync Enabled" : "Firebase running in Local Development Mode"}>
            <Cloud className="w-3 h-3 text-emerald-400" />
            {isFirebaseConfigured ? (
              <CheckCircle className="w-3 h-3 text-emerald-400" />
            ) : (
              <span className="text-slate-500">Local DB</span>
            )}
          </div>
        </div>
      )}
      {error && (
        <div className="absolute top-16 right-6 bg-rose-950/90 border border-rose-800 text-rose-200 px-3 py-2 rounded text-xs flex items-center gap-2 z-50">
          <AlertCircle className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-2 font-bold">&times;</button>
        </div>
      )}
    </div>
  );
};
