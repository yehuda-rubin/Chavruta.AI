"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { BirthFields, MIN_AGE_MONTHS, monthsSinceBirth } from "@/components/AgeStep";
import { ContentTree } from "@/components/ContentTree";
import { api, type Me } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";

// The parent's page. Served at /family, NOT /parent: /parent is proxied to the API (nginx.conf and
// next.config.mjs), so a page there would never be reached. A parent links a child by account ID, the
// child approves in their own settings, and a linked parent may correct the child's birth month/year and
// switch books off. Nothing here reads the child's conversations, and the API offers no route that could.

type Child = { child_owner_id: string; status: string };

function ChildCard({ lang, child, onChanged }: { lang: Lang; child: Child; onChanged: () => void }) {
  const [month, setMonth] = useState("");
  const [year, setYear] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [showContent, setShowContent] = useState(false);
  const active = child.status === "active";

  const saveAge = async (e: React.FormEvent) => {
    e.preventDefault();
    const m = Number(month), y = Number(year);
    if (!m || !y) { setMsg({ ok: false, text: tr(lang, "ageStepInvalid") }); return; }
    if (monthsSinceBirth(y, m) < MIN_AGE_MONTHS) { setMsg({ ok: false, text: tr(lang, "ageStepTooYoung") }); return; }
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.parent.setAge(child.child_owner_id, y, m);
      setMsg({ ok: true, text: tr(lang, r.is_minor ? "familyAgeSaved" : "familyAgeNowAdult") });
      if (!r.is_minor) onChanged();
    } catch {
      setMsg({ ok: false, text: tr(lang, "ageStepFailed") });
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    if (!window.confirm(tr(lang, "familyRevokeConfirm"))) return;
    setBusy(true);
    try {
      await api.parent.revoke(child.child_owner_id);
      onChanged();
    } catch {
      setMsg({ ok: false, text: tr(lang, "linkReqFailed") });
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="glass rounded-2xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <code className="font-mono text-[11px] text-ink/70 truncate" dir="ltr">{child.child_owner_id}</code>
          <span className={`px-1.5 py-0.5 rounded text-[10px] ${active ? "bg-tekhelet/10 text-tekhelet" : "bg-ink/10 text-ink/60"}`}>
            {tr(lang, active ? "familyStatusActive" : "familyStatusPending")}
          </span>
        </div>
        <button disabled={busy} onClick={revoke}
                className="text-[11px] px-2 py-1 rounded-lg glass text-ink/60 disabled:opacity-40">
          {tr(lang, "familyRevoke")}
        </button>
      </div>

      {active && (
        <>
          <form onSubmit={saveAge} className="flex flex-col gap-2 border-t border-ink/10 pt-3">
            <h3 className="text-sm font-semibold text-tekhelet">{tr(lang, "familyAgeHeading")}</h3>
            <BirthFields lang={lang} month={month} year={year} onMonth={setMonth} onYear={setYear} />
            <div className="flex items-center gap-3 flex-wrap">
              <button disabled={busy || !month || !year}
                      className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold disabled:opacity-40">
                {tr(lang, "familyAgeSave")}
              </button>
              {msg && (
                <span role={msg.ok ? "status" : "alert"} className={`text-xs ${msg.ok ? "text-green-700" : "text-red-600"}`}>
                  {msg.text}
                </span>
              )}
            </div>
          </form>

          <div className="border-t border-ink/10 pt-3 flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-tekhelet">{tr(lang, "familyContentHeading")}</h3>
            {showContent ? (
              <ContentTree
                lang={lang}
                load={() => api.parent.content(child.child_owner_id)}
                save={(d) => api.parent.setContent(child.child_owner_id, d)}
              />
            ) : (
              <button onClick={() => setShowContent(true)}
                      className="self-start text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold">
                {tr(lang, "familyContentOpen")}
              </button>
            )}
          </div>
        </>
      )}
    </li>
  );
}

export default function FamilyPage() {
  const auth = useAuth();
  const [lang, setLang] = useState<Lang>("he");
  const [me, setMe] = useState<Me | null>(null);
  const [children, setChildren] = useState<Child[]>([]);
  const [childId, setChildId] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    let l: Lang = "he";
    try {
      const sp = new URLSearchParams(window.location.search).get("lang");
      const saved = localStorage.getItem("chavruta-lang");
      if (sp === "he" || sp === "en") l = sp;
      else if (saved === "he" || saved === "en") l = saved;
    } catch {}
    setLang(l);
  }, []);

  const toggleLang = () => {
    const next: Lang = lang === "he" ? "en" : "he";
    setLang(next);
    try { localStorage.setItem("chavruta-lang", next); } catch {}
  };

  const loadChildren = useCallback(() => {
    api.parent.children().then((r) => setChildren(r.children)).catch(() => setChildren([]));
  }, []);

  useEffect(() => {
    if (auth.loading || (auth.enabled && !auth.user)) return;
    api.me().then(setMe).catch(() => setMe(null));
    loadChildren();
  }, [auth.loading, auth.enabled, auth.user, loadChildren]);

  const link = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!childId.trim() || busy) return;
    setBusy(true);
    setMsg(null);
    try {
      await api.parent.link(childId.trim());
      setChildId("");
      setMsg({ ok: true, text: tr(lang, "familyLinkSent") });
      loadChildren();
    } catch (err) {
      const status = (err as Error & { status?: number }).status;
      setMsg({ ok: false, text: tr(lang, status === 404 ? "familyLinkNotFound" : "linkReqFailed") });
    } finally {
      setBusy(false);
    }
  };

  const dir = lang === "he" ? "rtl" : "ltr";

  let body: React.ReactNode;
  if (auth.loading) {
    body = <p className="text-sm text-ink/50">{tr(lang, "schoolLoading")}</p>;
  } else if (auth.enabled && !auth.user) {
    body = <p className="text-sm text-ink/60">{tr(lang, "familyDenied")}</p>;
  } else if (me?.is_minor) {
    body = <p className="text-sm text-ink/60">{tr(lang, "familyMinorDenied")}</p>;
  } else {
    body = (
      <>
        <section className="glass rounded-2xl p-4 flex flex-col gap-3">
          <h2 className="font-serif font-bold text-tekhelet">{tr(lang, "familyLinkHeading")}</h2>
          <form onSubmit={link} className="flex gap-2 flex-wrap">
            <input
              value={childId}
              onChange={(e) => setChildId(e.target.value)}
              dir="ltr"
              aria-label={tr(lang, "familyChildIdPlaceholder")}
              placeholder={tr(lang, "familyChildIdPlaceholder")}
              className="flex-1 min-w-48 bg-white border border-line rounded-xl px-3 py-2 text-sm font-mono outline-none focus:border-indigo"
            />
            <button disabled={busy || !childId.trim()}
                    className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold disabled:opacity-40">
              {tr(lang, "familyLinkBtn")}
            </button>
          </form>
          {msg && (
            <p role={msg.ok ? "status" : "alert"} className={`text-xs ${msg.ok ? "text-green-700" : "text-red-600"}`}>
              {msg.text}
            </p>
          )}
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="font-serif font-bold text-tekhelet">{tr(lang, "familyChildrenHeading")}</h2>
          {children.length === 0 ? (
            <p className="text-xs text-ink/40">{tr(lang, "familyChildrenEmpty")}</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {children.map((c) => (
                <ChildCard key={c.child_owner_id} lang={lang} child={c} onChanged={loadChildren} />
              ))}
            </ul>
          )}
        </section>
      </>
    );
  }

  return (
    <div dir={dir} className="min-h-dvh flex flex-col gap-4 p-4 lg:p-8 max-w-3xl mx-auto">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <Icon name="family_restroom" className="text-tekhelet text-[28px]" />
          <h1 className="font-serif text-xl font-bold text-tekhelet">{tr(lang, "familyTitle")}</h1>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={toggleLang} className="px-3 py-1.5 rounded-full glass text-ink/70 text-xs font-semibold">
            עברית · EN
          </button>
          <Link href="/" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
            {tr(lang, "backToApp")}
          </Link>
        </div>
      </header>
      <p className="text-xs text-ink/60 leading-relaxed">{tr(lang, "familyIntro")}</p>
      {body}
    </div>
  );
}
