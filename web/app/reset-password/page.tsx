"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { Icon } from "@/components/Icon";

// Landing point for a Supabase password-recovery email link. The Supabase client (detectSessionInUrl:
// true, see lib/supabase.ts) reads the recovery token from the URL and establishes a session before
// this ever renders meaningfully — so by the time the user submits, updatePassword() is just an
// ordinary authenticated call, not a special recovery-flow one.
export default function ResetPassword() {
  const [lang] = useState<Lang>("he");
  const { user, loading, updatePassword } = useAuth();
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (done) {
      const t = setTimeout(() => router.replace("/"), 1500);
      return () => clearTimeout(t);
    }
  }, [done, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await updatePassword(password);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : tr(lang, "authGenericError"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div dir="rtl" className="min-h-screen grid place-items-center p-4">
      <div className="glass rounded-[28px] p-8 w-full max-w-sm flex flex-col gap-5">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="h-14 w-14 rounded-2xl grad grid place-items-center text-white">
            <Icon name="lock_reset" className="text-[26px]" />
          </div>
          <h1 className="font-serif text-2xl font-bold text-tekhelet">{tr(lang, "resetPasswordTitle")}</h1>
          <p className="text-xs text-ink/55 leading-relaxed">{tr(lang, "resetPasswordSubtitle")}</p>
        </div>

        {!loading && !user ? (
          <p className="text-xs text-red-600 text-center leading-relaxed">{tr(lang, "authGenericError")}</p>
        ) : done ? (
          <p className="text-xs text-green-700 text-center leading-relaxed">{tr(lang, "passwordUpdated")}</p>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-3">
            <input
              type="password"
              required
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={tr(lang, "newPassword")}
              className="w-full glass rounded-2xl px-4 py-3 font-serif text-[15px] outline-none focus:ring-2 focus:ring-indigo/30"
            />
            {error && <p className="text-xs text-red-600 leading-relaxed">{error}</p>}
            <button
              type="submit"
              disabled={busy || loading}
              className="py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-60"
            >
              {busy ? tr(lang, "authWorking") : tr(lang, "setNewPasswordBtn")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
