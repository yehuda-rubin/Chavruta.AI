"use client";
import { useState } from "react";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { Icon } from "./Icon";

// Full-screen sign-in gate, shown only when Supabase is configured AND no user is signed in. Headless
// (our own markup) precisely so the form is native Hebrew RTL — the reason we chose Supabase over a
// prebuilt component library. Email + password, with a sign-up toggle.
export function SignIn({ lang }: { lang: Lang }) {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      if (mode === "up") {
        const { needsConfirm } = await signUp(email.trim(), password);
        if (needsConfirm) setNotice(tr(lang, "authCheckEmail"));
      } else {
        await signIn(email.trim(), password);
      }
    } catch (err) {
      // Supabase returns a readable message (e.g. "Invalid login credentials"); fall back to generic.
      setError(err instanceof Error && err.message ? err.message : tr(lang, "authGenericError"));
    } finally {
      setBusy(false);
    }
  };

  const field =
    "w-full glass rounded-2xl px-4 py-3 font-serif text-[15px] outline-none focus:ring-2 focus:ring-indigo/30";

  return (
    <div className="min-h-screen grid place-items-center p-4">
      <div className="glass rounded-[28px] p-8 w-full max-w-sm flex flex-col gap-5">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="h-14 w-14 rounded-2xl grad grid place-items-center text-white">
            <Icon name="menu_book" className="text-[26px]" />
          </div>
          <h1 className="font-serif text-2xl font-bold text-tekhelet">{tr(lang, "signInTitle")}</h1>
          <p className="text-xs text-ink/55 leading-relaxed">{tr(lang, "signInSubtitle")}</p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3">
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={field}
            placeholder={tr(lang, "signInEmail")}
          />
          <input
            type="password"
            required
            autoComplete={mode === "up" ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={field}
            placeholder={tr(lang, "signInPassword")}
          />

          {error && <p className="text-xs text-red-600 leading-relaxed">{error}</p>}
          {notice && <p className="text-xs text-green-700 leading-relaxed">{notice}</p>}

          <button
            type="submit"
            disabled={busy}
            className="py-3 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition disabled:opacity-60"
          >
            {busy ? tr(lang, "authWorking") : tr(lang, mode === "up" ? "signUpBtn" : "signInBtn")}
          </button>
        </form>

        <button
          onClick={() => {
            setMode(mode === "in" ? "up" : "in");
            setError("");
            setNotice("");
          }}
          className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold"
        >
          {tr(lang, mode === "in" ? "signInToSignUp" : "signInToSignIn")}
        </button>

        <p className="text-[11px] text-ink/40 text-center">{tr(lang, "footer")}</p>
      </div>
    </div>
  );
}
