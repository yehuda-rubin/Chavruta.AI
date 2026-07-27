"use client";
// Auth context. When Supabase is configured it tracks the signed-in session, keeps api.ts's bearer
// token in sync, and exposes sign-in/up/out. When Supabase is NOT configured it's inert — `enabled`
// is false, `user` is null, and the app renders normally (unauthenticated local mode, unchanged).
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { getSupabase, supabaseEnabled } from "./supabase";
import { setAuthToken } from "./api";

interface AuthState {
  enabled: boolean;
  loading: boolean;
  user: User | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, meta?: Record<string, unknown>) => Promise<{ needsConfirm: boolean }>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // Not-enabled ⇒ nothing to load, render immediately. Enabled ⇒ wait for the initial session check.
  const [loading, setLoading] = useState(supabaseEnabled);

  const apply = useCallback((session: Session | null) => {
    setAuthToken(session?.access_token ?? null);
    setUser(session?.user ?? null);
  }, []);

  useEffect(() => {
    const sb = getSupabase();
    if (!sb) return;
    let alive = true;
    sb.auth.getSession().then(({ data }) => {
      if (!alive) return;
      apply(data.session);
      setLoading(false);
    });
    // Keep the token fresh across refreshes, sign-in, and sign-out, in this and other tabs.
    const { data: sub } = sb.auth.onAuthStateChange((_evt, session) => apply(session));
    return () => {
      alive = false;
      sub.subscription.unsubscribe();
    };
  }, [apply]);

  const signIn = useCallback(async (email: string, password: string) => {
    const sb = getSupabase();
    if (!sb) return;
    const { error } = await sb.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }, []);

  const signUp = useCallback(async (email: string, password: string, meta?: Record<string, unknown>) => {
    const sb = getSupabase();
    if (!sb) return { needsConfirm: false };
    // `meta` is stored as Supabase user_metadata — we use it to record terms-acceptance (version +
    // timestamp) so consent is durable on the account, not just a client-side gate.
    const { data, error } = await sb.auth.signUp({ email, password, options: { data: meta } });
    if (error) throw error;
    // If email confirmation is on, there's a user but no session yet.
    return { needsConfirm: !data.session };
  }, []);

  const signOut = useCallback(async () => {
    const sb = getSupabase();
    if (!sb) return;
    await sb.auth.signOut();
  }, []);

  const value = useMemo<AuthState>(
    () => ({ enabled: supabaseEnabled, loading, user, signIn, signUp, signOut }),
    [loading, user, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
