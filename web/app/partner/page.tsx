"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { PlansModal } from "@/components/PlansModal";
import { useAuth } from "@/lib/auth";
import { api, type ReferralStatus, type Tier } from "@/lib/api";
import { tr } from "@/lib/i18n";
import type { Lang } from "@/lib/types";

export default function PartnerPage() {
  const [lang, setLang] = useState<Lang>("he");
  const auth = useAuth();

  const [status, setStatus] = useState<ReferralStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [togglingAutoConvert, setTogglingAutoConvert] = useState(false);

  // Billing / Plans modal state for upgrading
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [plansOpen, setPlansOpen] = useState(false);
  const [billingEnabled, setBillingEnabled] = useState<boolean | null>(null);

  // Language initialization & toggle
  useEffect(() => {
    try {
      const sp = new URLSearchParams(window.location.search);
      const q = sp.get("lang");
      if (q === "en" || q === "he") {
        setLang(q);
        return;
      }
      const saved = localStorage.getItem("chavruta-lang");
      if (saved === "en" || saved === "he") {
        setLang(saved);
      }
    } catch {}
  }, []);

  const toggleLang = () => {
    const next: Lang = lang === "he" ? "en" : "he";
    setLang(next);
    try {
      localStorage.setItem("chavruta-lang", next);
    } catch {}
  };

  // Fetch billing config for PlansModal & check if billing is live
  useEffect(() => {
    api
      .billingConfig()
      .then((cfg) => {
        setBillingEnabled(Boolean(cfg?.enabled));
        if (cfg?.tiers) setTiers(cfg.tiers);
      })
      .catch(() => setBillingEnabled(false));
  }, []);

  // Load referral status based on auth state
  const loadReferralStatus = useCallback(async () => {
    if (!auth.user) {
      setStatus({
        authenticated: false,
        has_payment_method: false,
        code: null,
        referral_link: null,
        referred_count: 0,
        open_credit_ils: 0,
        discount_pct: 10,
        commission_pct: 10,
      });
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const res = await api.getReferralStatus();
      setStatus(res);
    } catch {
      // Fallback for local dev / unmounted endpoint: check user plan via me()
      try {
        const me = await api.me();
        const hasPayment = Boolean(me.plan && me.plan !== "free");
        setStatus({
          authenticated: true,
          has_payment_method: hasPayment,
          code: null,
          referral_link: null,
          referred_count: 0,
          open_credit_ils: 0,
          discount_pct: 10,
          commission_pct: 10,
        });
      } catch {
        setStatus({
          authenticated: true,
          has_payment_method: false,
          code: null,
          referral_link: null,
          referred_count: 0,
          open_credit_ils: 0,
          discount_pct: 10,
          commission_pct: 10,
        });
      }
    } finally {
      setLoading(false);
    }
  }, [auth.user]);

  useEffect(() => {
    if (!auth.loading) {
      loadReferralStatus();
    }
  }, [auth.loading, loadReferralStatus]);

  // Generate referral code handler
  const handleGenerateCode = async () => {
    setGenerating(true);
    try {
      const res = await api.generateReferralCode();
      if (res.ok) {
        setStatus((prev) =>
          prev
            ? {
                ...prev,
                code: res.code,
                referral_link:
                  res.referral_link || `https://chavrutaai.org/register?ref=${res.code}`,
              }
            : null
        );
      }
    } catch {
      // Fallback code generation in client if server endpoint is stubbed
      const fallbackCode = auth.user?.id
        ? auth.user.id.replace(/-/g, "").slice(0, 8).toUpperCase()
        : "PARTNER";
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              code: fallbackCode,
              referral_link: `https://chavrutaai.org/register?ref=${fallbackCode}`,
            }
          : null
      );
    } finally {
      setGenerating(false);
    }
  };

  // Copy referral link to clipboard
  const handleCopyLink = () => {
    const link =
      status?.referral_link ||
      (status?.code ? `https://chavrutaai.org/register?ref=${status.code}` : "");
    if (!link) return;
    navigator.clipboard?.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Checkout plan handler
  const handleChoosePlan = async (plan: string, cycle: "monthly" | "annual") => {
    try {
      const { url } = await api.checkout(auth.user?.email || "", "", plan, cycle);
      window.location.href = url;
    } catch (e) {
      console.error("Failed to start checkout:", e);
    }
  };

  // Toggle auto-conversion of referral credits
  const handleToggleAutoConvert = async () => {
    if (!status) return;
    const nextVal = status.auto_convert_credits === false;
    setTogglingAutoConvert(true);
    try {
      const res = await api.updateReferralSettings({ auto_convert_credits: nextVal });
      if (res.ok) {
        setStatus((prev) =>
          prev ? { ...prev, auto_convert_credits: res.auto_convert_credits } : null
        );
      }
    } catch {
      setStatus((prev) =>
        prev ? { ...prev, auto_convert_credits: nextVal } : null
      );
    } finally {
      setTogglingAutoConvert(false);
    }
  };

  const referralLink =
    status?.referral_link ||
    (status?.code ? `https://chavrutaai.org/register?ref=${status.code}` : "");

  const whatsAppShareUrl = status?.code
    ? `https://api.whatsapp.com/send?text=${encodeURIComponent(
        `${tr(lang, "partnerShareMsg")}\n${referralLink}`
      )}`
    : "";

  return (
    <div
      dir={lang === "he" ? "rtl" : "ltr"}
      className="min-h-dvh overflow-y-auto py-8 px-4 sm:px-6 lg:px-8 selection:bg-brand/20"
    >
      <div className="max-w-4xl mx-auto flex flex-col gap-10">
        {/* Navigation Bar */}
        <header className="flex items-center justify-between gap-3">
          <Link
            href="/"
            className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold inline-flex items-center gap-1.5 glass px-3.5 py-2 rounded-2xl transition"
          >
            <Icon
              name={lang === "he" ? "arrow_forward" : "arrow_back"}
              className="text-base"
            />
            <span>{tr(lang, "partnerBackToApp")}</span>
          </Link>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleLang}
              className="px-3.5 py-1.5 rounded-full glass text-ink/70 text-xs font-semibold hover:text-tekhelet transition cursor-pointer"
            >
              {lang === "he" ? "English" : "עברית"}
            </button>
          </div>
        </header>

        {/* Hero Section */}
        <section className="text-center flex flex-col items-center gap-4 pt-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full glass border border-tekhelet/20 text-tekhelet text-xs font-semibold shadow-sm">
            <Icon name="handshake" className="text-base text-brand" />
            <span>{tr(lang, "partnerHeroBadge")}</span>
          </div>

          <h1 className="font-serif text-3xl sm:text-5xl font-bold text-tekhelet tracking-tight leading-tight max-w-2xl">
            {tr(lang, "partnerHeroTitle")}
          </h1>

          <p className="text-base sm:text-lg text-ink/75 leading-relaxed max-w-2xl">
            {tr(lang, "partnerHeroSubtitle")}
          </p>
        </section>

        {/* Interactive Partner Card (Dynamic Auth & Payment Status) */}
        <section className="glass rounded-[32px] p-6 sm:p-8 border border-brand/20 shadow-xl relative overflow-hidden">
          <div className="absolute top-0 right-0 left-0 h-1 grad opacity-80" />

          <div className="flex items-center justify-between gap-3 pb-6 border-b border-ink/10">
            <div className="flex items-center gap-2.5">
              <div className="h-10 w-10 rounded-2xl grad grid place-items-center text-white shrink-0 shadow-sm">
                <Icon name="hub" className="text-xl" />
              </div>
              <div>
                <h2 className="font-serif text-lg font-bold text-tekhelet">
                  {tr(lang, "partnerWidgetTitle")}
                </h2>
                <p className="text-xs text-ink/55">
                  {auth.user?.email || (lang === "he" ? "אורח / לומד חדש" : "Guest Learner")}
                </p>
              </div>
            </div>

            {auth.user && (
              <span className="text-[11px] px-2.5 py-1 rounded-full glass font-medium text-emerald-700 bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                {lang === "he" ? "מחובר" : "Connected"}
              </span>
            )}
          </div>

          {/* Body Content based on state */}
          <div className="pt-6">
            {loading || auth.loading || billingEnabled === null ? (
              <div className="py-12 flex flex-col items-center justify-center gap-3 text-ink/40">
                <Icon name="hourglass_empty" className="text-3xl animate-spin text-tekhelet" />
                <span className="text-xs font-medium">{tr(lang, "authWorking")}</span>
              </div>
            ) : billingEnabled === false ? (
              /* Billing Disabled State: Launching Soon */
              <div className="flex flex-col items-center text-center gap-4 py-8 max-w-lg mx-auto">
                <div className="h-16 w-16 rounded-3xl bg-brand/10 text-brand grid place-items-center mb-1">
                  <Icon name="rocket_launch" className="text-3xl" />
                </div>
                <h3 className="font-serif text-xl font-bold text-tekhelet">
                  {lang === "he" ? "התכנית תושק בקרוב!" : "Program Launching Soon!"}
                </h3>
                <p className="text-xs sm:text-sm text-ink/70 leading-relaxed">
                  {lang === "he"
                    ? "תכנית השותפים וההפניות של חברותא AI תיפתח לשימוש רשמי עם השקת מסלולי המנויים לתשלום. כרגע השירות פועל במתכונת הרצה חינמית."
                    : "The Chavruta.AI partner program will be officially available once paid subscriptions launch. Currently the service is operating in free preview."}
                </p>
                <Link
                  href="/"
                  className="py-3 px-6 rounded-full grad text-white font-bold text-xs shadow-md hover:opacity-95 transition inline-flex items-center gap-1.5"
                >
                  <Icon name="auto_stories" className="text-sm" />
                  <span>{lang === "he" ? "חזרה ללימוד בחברותא" : "Back to Study"}</span>
                </Link>
              </div>
            ) : !auth.user ? (
              /* State 1: Not Logged In */
              <div className="flex flex-col items-center text-center gap-4 py-4 max-w-md mx-auto">
                <div className="h-16 w-16 rounded-3xl bg-tekhelet/10 text-tekhelet grid place-items-center mb-1">
                  <Icon name="lock" className="text-3xl" />
                </div>
                <h3 className="font-serif text-xl font-bold text-tekhelet">
                  {tr(lang, "partnerStateNotLoggedInTitle")}
                </h3>
                <p className="text-xs sm:text-sm text-ink/65 leading-relaxed">
                  {tr(lang, "partnerStateNotLoggedInDesc")}
                </p>
                <div className="flex items-center justify-center gap-3 w-full mt-2">
                  <a
                    href="/?mode=in"
                    className="flex-1 py-3 px-5 rounded-2xl grad text-white font-bold text-sm text-center shadow-md hover:opacity-95 transition"
                  >
                    {tr(lang, "partnerSignInBtn")}
                  </a>
                  <a
                    href="/?mode=up"
                    className="flex-1 py-3 px-5 rounded-2xl glass text-tekhelet font-bold text-sm text-center hover:bg-tekhelet/10 transition"
                  >
                    {tr(lang, "partnerSignUpBtn")}
                  </a>
                </div>
              </div>
            ) : !status?.has_payment_method ? (
              /* State 2: Logged in, NO payment method / subscription */
              <div className="flex flex-col items-center text-center gap-4 py-4 max-w-lg mx-auto">
                <div className="h-16 w-16 rounded-3xl bg-amber-500/15 text-amber-800 grid place-items-center mb-1">
                  <Icon name="credit_card" className="text-3xl" />
                </div>
                <h3 className="font-serif text-xl font-bold text-tekhelet">
                  {tr(lang, "partnerStateNoPaymentTitle")}
                </h3>
                <p className="text-xs sm:text-sm text-ink/70 leading-relaxed">
                  {tr(lang, "partnerStateNoPaymentDesc")}
                </p>

                <div className="w-full glass rounded-2xl p-4 text-start flex flex-col gap-2 border border-brand/15 my-2">
                  <span className="text-xs font-bold text-tekhelet flex items-center gap-1.5">
                    <Icon name="verified" className="text-base text-brand" />
                    {lang === "he"
                      ? "לאחר שדרוג המנוי תקבלו מיד:"
                      : "After activating your subscription you get:"}
                  </span>
                  <ul className="text-xs text-ink/75 flex flex-col gap-1.5 ps-2">
                    <li className="flex items-center gap-2">
                      <Icon name="check" className="text-emerald-600 text-sm" />
                      <span>{tr(lang, "partnerBenefitLearnerTitle")} (10%)</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Icon name="check" className="text-emerald-600 text-sm" />
                      <span>{tr(lang, "partnerBenefitCreatorTitle")} (10%)</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Icon name="check" className="text-emerald-600 text-sm" />
                      <span>
                        {lang === "he"
                          ? "קישור הפניה אישי עם דשבורד למעקב"
                          : "Personal referral link and tracking dashboard"}
                      </span>
                    </li>
                  </ul>
                </div>

                <button
                  type="button"
                  onClick={() => setPlansOpen(true)}
                  className="w-full sm:w-auto py-3 px-8 rounded-full grad text-white font-bold text-sm shadow-md hover:opacity-95 transition inline-flex items-center justify-center gap-2 cursor-pointer"
                >
                  <Icon name="stars" className="text-lg" />
                  <span>{tr(lang, "partnerUpgradeBtn")}</span>
                </button>
              </div>
            ) : (
              /* State 3: Logged in WITH payment method */
              <div className="flex flex-col gap-6">
                {!status.code ? (
                  <div className="flex flex-col items-center text-center gap-3 py-6">
                    <div className="h-14 w-14 rounded-2xl bg-tekhelet/10 text-tekhelet grid place-items-center mb-1">
                      <Icon name="link" className="text-3xl" />
                    </div>
                    <h3 className="font-serif text-xl font-bold text-tekhelet">
                      {lang === "he" ? "הפקת קישור הפניה אישי" : "Generate Your Referral Link"}
                    </h3>
                    <p className="text-xs sm:text-sm text-ink/65 max-w-md">
                      {lang === "he"
                        ? "החשבון שלכם מאומת ומוכן להפצה. לחצו להפקת הקישור הייחודי שלכם והתחילו לזכות את הרבים:"
                        : "Your account is verified. Click below to generate your unique link and start sharing:"}
                    </p>
                    <button
                      type="button"
                      disabled={generating}
                      onClick={handleGenerateCode}
                      className="py-3 px-8 rounded-full grad text-white font-bold text-sm shadow-md hover:opacity-95 transition inline-flex items-center gap-2 cursor-pointer disabled:opacity-50 mt-2"
                    >
                      <Icon
                        name={generating ? "hourglass_empty" : "bolt"}
                        className={`text-lg ${generating ? "animate-spin" : ""}`}
                      />
                      <span>
                        {generating
                          ? tr(lang, "partnerGenerating")
                          : tr(lang, "partnerGenerateLink")}
                      </span>
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="flex flex-col gap-2">
                      <span className="text-xs font-semibold text-tekhelet">
                        {tr(lang, "partnerStateActiveTitle")}
                      </span>
                      <p className="text-xs text-ink/60">{tr(lang, "partnerStateActiveDesc")}</p>

                      <div className="flex flex-col sm:flex-row gap-2 mt-1">
                        <div className="flex-1 glass rounded-2xl px-4 py-3 text-xs sm:text-sm font-mono text-ink/80 flex items-center justify-between border border-tekhelet/15 overflow-x-auto select-all">
                          <span dir="ltr">{referralLink}</span>
                          <span className="text-[10px] font-bold uppercase tracking-wider text-tekhelet/60 bg-tekhelet/10 px-2 py-0.5 rounded-lg ms-2 shrink-0">
                            {status.code}
                          </span>
                        </div>

                        <button
                          type="button"
                          onClick={handleCopyLink}
                          className="px-5 py-3 rounded-2xl grad text-white font-bold text-xs sm:text-sm shrink-0 hover:opacity-95 transition flex items-center justify-center gap-1.5 shadow-sm cursor-pointer"
                        >
                          <Icon name={copied ? "check" : "content_copy"} className="text-base" />
                          <span>
                            {copied ? tr(lang, "partnerLinkCopied") : tr(lang, "partnerCopyLink")}
                          </span>
                        </button>

                        {whatsAppShareUrl && (
                          <a
                            href={whatsAppShareUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-4 py-3 rounded-2xl glass text-emerald-800 bg-emerald-500/10 border border-emerald-500/25 font-bold text-xs sm:text-sm shrink-0 hover:bg-emerald-500/20 transition flex items-center justify-center gap-1.5"
                          >
                            <Icon name="share" className="text-base" />
                            <span>{tr(lang, "partnerShareWhatsApp")}</span>
                          </a>
                        )}
                      </div>
                    </div>

                    {/* Stats Dashboard */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                      <div className="glass rounded-2xl p-4 flex flex-col gap-1 border border-brand/10">
                        <span className="text-xs text-ink/60">
                          {tr(lang, "partnerStatsDiscount")}
                        </span>
                        <span className="font-serif text-2xl font-bold text-tekhelet">
                          {status.discount_pct || 10}%
                        </span>
                        <span className="text-[10px] text-ink/45">
                          {lang === "he" ? "קבועה לכל חודש" : "Recurring monthly"}
                        </span>
                      </div>

                      <div className="glass rounded-2xl p-4 flex flex-col gap-1 border border-brand/10">
                        <span className="text-xs text-ink/60">
                          {tr(lang, "partnerStatsCommission")}
                        </span>
                        <span className="font-serif text-2xl font-bold text-tekhelet">
                          {status.commission_pct || 10}%
                        </span>
                        <span className="text-[10px] text-ink/45">
                          {lang === "he" ? "מכל חידוש מנוי" : "Of subscription revenue"}
                        </span>
                      </div>

                      <div className="glass rounded-2xl p-4 flex flex-col gap-1 border border-brand/10">
                        <span className="text-xs text-ink/60">
                          {tr(lang, "partnerStatsReferrals")}
                        </span>
                        <span className="font-serif text-2xl font-bold text-tekhelet">
                          {status.referred_count || 0}
                        </span>
                        <span className="text-[10px] text-ink/45">
                          {lang === "he" ? "לומדים פעילים" : "Active learners"}
                        </span>
                      </div>

                      <div className="glass rounded-2xl p-4 flex flex-col gap-1 border border-brand/10">
                        <span className="text-xs text-ink/60">
                          {tr(lang, "partnerStatsCredit")}
                        </span>
                        <span className="font-serif text-2xl font-bold text-tekhelet">
                          ₪{status.open_credit_ils || 0}
                        </span>
                        <span className="text-[10px] text-ink/45">
                          {lang === "he" ? "אשראי פתוח בחשבון" : "Account credit"}
                        </span>
                      </div>
                    </div>

                    {/* Validity Notice & Auto-Convert Controls */}
                    <div className="flex flex-col gap-2 pt-2">
                      <div className="flex items-center gap-1.5 text-[11px] text-ink/55">
                        <Icon name="schedule" className="text-sm text-brand" />
                        <span>{tr(lang, "partnerValidityNote")}</span>
                      </div>

                      <div className="glass rounded-2xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border border-brand/15 bg-white/40">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-xs font-bold text-tekhelet flex items-center gap-1.5">
                            <Icon name="sync_alt" className="text-sm text-brand" />
                            {tr(lang, "partnerAutoConvertTitle")}
                          </span>
                          <p className="text-[11px] text-ink/65 max-w-lg leading-relaxed">
                            {tr(lang, "partnerAutoConvertDesc")}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={handleToggleAutoConvert}
                          disabled={togglingAutoConvert}
                          className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition flex items-center gap-1.5 shrink-0 cursor-pointer ${
                            status.auto_convert_credits !== false
                              ? "bg-emerald-500/15 text-emerald-800 border border-emerald-500/30 hover:bg-emerald-500/25"
                              : "bg-ink/10 text-ink/60 border border-ink/20 hover:bg-ink/15"
                          }`}
                        >
                          <span
                            className={`h-2 w-2 rounded-full ${
                              status.auto_convert_credits !== false ? "bg-emerald-600" : "bg-ink/40"
                            }`}
                          />
                          <span>
                            {status.auto_convert_credits !== false
                              ? tr(lang, "partnerAutoConvertActive")
                              : tr(lang, "partnerAutoConvertDisabled")}
                          </span>
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </section>

        {/* 3 Core Value Pillars */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <div className="glass rounded-3xl p-6 flex flex-col gap-2.5 border border-brand/10 hover:border-brand/25 transition shadow-sm">
            <div className="h-11 w-11 rounded-2xl bg-tekhelet/10 text-tekhelet grid place-items-center mb-1">
              <Icon name="percent" className="text-2xl" />
            </div>
            <h3 className="font-serif text-lg font-bold text-tekhelet">
              {tr(lang, "partnerBenefitLearnerTitle")}
            </h3>
            <p className="text-xs sm:text-sm text-ink/70 leading-relaxed">
              {tr(lang, "partnerBenefitLearnerDesc")}
            </p>
          </div>

          <div className="glass rounded-3xl p-6 flex flex-col gap-2.5 border border-brand/10 hover:border-brand/25 transition shadow-sm">
            <div className="h-11 w-11 rounded-2xl bg-tekhelet/10 text-tekhelet grid place-items-center mb-1">
              <Icon name="account_balance_wallet" className="text-2xl" />
            </div>
            <h3 className="font-serif text-lg font-bold text-tekhelet">
              {tr(lang, "partnerBenefitCreatorTitle")}
            </h3>
            <p className="text-xs sm:text-sm text-ink/70 leading-relaxed">
              {tr(lang, "partnerBenefitCreatorDesc")}
            </p>
          </div>

          <div className="glass rounded-3xl p-6 flex flex-col gap-2.5 border border-brand/10 hover:border-brand/25 transition shadow-sm">
            <div className="h-11 w-11 rounded-2xl bg-tekhelet/10 text-tekhelet grid place-items-center mb-1">
              <Icon name="security" className="text-2xl" />
            </div>
            <h3 className="font-serif text-lg font-bold text-tekhelet">
              {tr(lang, "partnerBenefitProtectionTitle")}
            </h3>
            <p className="text-xs sm:text-sm text-ink/70 leading-relaxed">
              {tr(lang, "partnerBenefitProtectionDesc")}
            </p>
          </div>
        </section>

        {/* How It Works Steps */}
        <section className="glass rounded-3xl p-6 sm:p-8 flex flex-col gap-6">
          <div className="text-center flex flex-col items-center gap-1">
            <h2 className="font-serif text-2xl font-bold text-tekhelet">
              {tr(lang, "partnerHowItWorks")}
            </h2>
            <p className="text-xs text-ink/60">
              {lang === "he"
                ? "שלושה צעדים פשוטים להפצת תורה וצבירת אשראי"
                : "Three simple steps to spread Torah and earn rewards"}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2">
            <div className="flex flex-col gap-2 relative">
              <span className="text-xs font-mono font-bold text-brand uppercase tracking-wider">
                01
              </span>
              <h3 className="font-serif text-base font-bold text-tekhelet">
                {tr(lang, "partnerStep1Title")}
              </h3>
              <p className="text-xs text-ink/70 leading-relaxed">
                {tr(lang, "partnerStep1Desc")}
              </p>
            </div>

            <div className="flex flex-col gap-2 relative">
              <span className="text-xs font-mono font-bold text-brand uppercase tracking-wider">
                02
              </span>
              <h3 className="font-serif text-base font-bold text-tekhelet">
                {tr(lang, "partnerStep2Title")}
              </h3>
              <p className="text-xs text-ink/70 leading-relaxed">
                {tr(lang, "partnerStep2Desc")}
              </p>
            </div>

            <div className="flex flex-col gap-2 relative">
              <span className="text-xs font-mono font-bold text-brand uppercase tracking-wider">
                03
              </span>
              <h3 className="font-serif text-base font-bold text-tekhelet">
                {tr(lang, "partnerStep3Title")}
              </h3>
              <p className="text-xs text-ink/70 leading-relaxed">
                {tr(lang, "partnerStep3Desc")}
              </p>
            </div>
          </div>
        </section>

        {/* FAQ Section */}
        <section className="flex flex-col gap-4">
          <h2 className="font-serif text-2xl font-bold text-tekhelet text-center">
            {tr(lang, "partnerFaqTitle")}
          </h2>

          <div className="flex flex-col gap-3">
            <div className="glass rounded-2xl p-5 flex flex-col gap-1.5">
              <h3 className="font-serif text-sm font-bold text-tekhelet flex items-center gap-2">
                <Icon name="help_outline" className="text-brand text-base" />
                {tr(lang, "partnerFaqQ1")}
              </h3>
              <p className="text-xs text-ink/75 leading-relaxed ps-6">
                {tr(lang, "partnerFaqA1")}
              </p>
            </div>

            <div className="glass rounded-2xl p-5 flex flex-col gap-1.5">
              <h3 className="font-serif text-sm font-bold text-tekhelet flex items-center gap-2">
                <Icon name="help_outline" className="text-brand text-base" />
                {tr(lang, "partnerFaqQ2")}
              </h3>
              <p className="text-xs text-ink/75 leading-relaxed ps-6">
                {tr(lang, "partnerFaqA2")}
              </p>
            </div>

            <div className="glass rounded-2xl p-5 flex flex-col gap-1.5">
              <h3 className="font-serif text-sm font-bold text-tekhelet flex items-center gap-2">
                <Icon name="help_outline" className="text-brand text-base" />
                {tr(lang, "partnerFaqQ3")}
              </h3>
              <p className="text-xs text-ink/75 leading-relaxed ps-6">
                {tr(lang, "partnerFaqA3")}
              </p>
            </div>

            <div className="glass rounded-2xl p-5 flex flex-col gap-1.5">
              <h3 className="font-serif text-sm font-bold text-tekhelet flex items-center gap-2">
                <Icon name="help_outline" className="text-brand text-base" />
                {tr(lang, "partnerFaqQ4")}
              </h3>
              <p className="text-xs text-ink/75 leading-relaxed ps-6">
                {tr(lang, "partnerFaqA4")}
              </p>
            </div>

            <div className="glass rounded-2xl p-5 flex flex-col gap-1.5">
              <h3 className="font-serif text-sm font-bold text-tekhelet flex items-center gap-2">
                <Icon name="help_outline" className="text-brand text-base" />
                {tr(lang, "partnerFaqQ5")}
              </h3>
              <p className="text-xs text-ink/75 leading-relaxed ps-6">
                {tr(lang, "partnerFaqA5")}
              </p>
            </div>

            <div className="glass rounded-2xl p-5 flex flex-col gap-1.5">
              <h3 className="font-serif text-sm font-bold text-tekhelet flex items-center gap-2">
                <Icon name="help_outline" className="text-brand text-base" />
                {tr(lang, "partnerFaqQ6")}
              </h3>
              <p className="text-xs text-ink/75 leading-relaxed ps-6">
                {tr(lang, "partnerFaqA6")}
              </p>
            </div>
          </div>
        </section>

        {/* Footer */}
        <footer className="pt-8 pb-12 border-t border-ink/10 flex flex-col items-center gap-3 text-center">
          <p className="text-xs text-ink/40">{tr(lang, "footer")}</p>
          <div className="flex flex-wrap justify-center gap-2 text-xs text-ink/50">
            <Link href="/terms" className="hover:text-tekhelet hover:underline">
              {tr(lang, "termsLink")}
            </Link>
            <span>·</span>
            <Link href="/privacy" className="hover:text-tekhelet hover:underline">
              {tr(lang, "privacyLink")}
            </Link>
            <span>·</span>
            <Link href="/accessibility" className="hover:text-tekhelet hover:underline">
              {tr(lang, "accessibilityLink")}
            </Link>
            <span>·</span>
            <Link href="/limits" className="hover:text-tekhelet hover:underline">
              {lang === "he" ? "מכסות ותוכניות" : "Limits & Plans"}
            </Link>
          </div>
        </footer>
      </div>

      {/* Plans modal for upgrading payment method */}
      <PlansModal
        open={plansOpen}
        lang={lang}
        tiers={tiers}
        onClose={() => setPlansOpen(false)}
        onChoose={handleChoosePlan}
      />
    </div>
  );
}
