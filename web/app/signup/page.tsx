"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Lang } from "@/lib/types";
import { useAuth } from "@/lib/auth";
import { SignIn } from "@/components/SignIn";

// Sign-in / sign-up on its own address, so the landing page can send people here instead of
// dropping them straight into a form. ?mode=up opens sign-up, ?ref=<code> carries a referral
// (SignIn reads both from the URL itself). A signed-in visitor goes on to the app.
export default function SignUpPage() {
  const auth = useAuth();
  const router = useRouter();
  const [lang, setLang] = useState<Lang>("he");

  useEffect(() => {
    try {
      // Same rule as the app: a saved choice wins, otherwise follow the browser (Hebrew or English).
      const saved = localStorage.getItem("chavruta-lang");
      if (saved === "en" || saved === "he") setLang(saved);
      else setLang((navigator.language || "").toLowerCase().startsWith("he") ? "he" : "en");
    } catch {}
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "he" ? "rtl" : "ltr";
  }, [lang]);
  useEffect(() => {
    if (!auth.loading && (!auth.enabled || auth.user)) router.replace("/");
  }, [auth.loading, auth.enabled, auth.user, router]);

  if (auth.loading || !auth.enabled || auth.user) return null;
  return <SignIn lang={lang} />;
}
