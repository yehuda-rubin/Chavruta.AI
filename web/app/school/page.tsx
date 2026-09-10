"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { api, type OrgInvite, type OrgPanel } from "@/lib/api";
import type { Lang } from "@/lib/types";
import { tr } from "@/lib/i18n";

// The school panel. Same Client-Component reasoning as /admin: it needs state for the fetch and the
// actions, and there is no SEO upside to a page nobody should find.
//
// The gate below is UX only. Every /orgs/* route resolves the caller's own membership server-side
// and 404s — never 403 — whatever this page decides to render.
//
// WHAT THIS PAGE DOES NOT SHOW, and must never be extended to show: the text of anything a member
// wrote. Not a question, not an answer, not a saved lesson. Everything here comes from usage
// counters and usage_events, whose columns are a fixed list of measurements. The tempting shortcut
// — joining `sessions` to list "recent chats" — would surface `first_q`, the verbatim opening
// question of every conversation. See specs/004-school-accounts/plan.md decision 1.

// Tokens mean nothing to a reader, so everything here is shown as questions — the unit people think
// in. 23,512 normalized tokens is the measured mean of a real turn (166 production turns, 2026-08-12).
const TURN = 23512;

const ROLE_HE: Record<string, string> = { admin: "מנהל", teacher: "מורה", student: "תלמיד" };
const ROLE_EN: Record<string, string> = { admin: "Administrator", teacher: "Teacher", student: "Student" };

export default function SchoolPanel() {
  const [lang, setLang] = useState<Lang>("he");
  const [loading, setLoading] = useState(true);
  const [panel, setPanel] = useState<OrgPanel | null>(null);
  const [denied, setDenied] = useState(false);
  const [demo, setDemo] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [invites, setInvites] = useState<OrgInvite[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let initialLang: Lang = "he";
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const paramLang = urlParams.get("lang");
      if (paramLang === "he" || paramLang === "en") {
        initialLang = paramLang;
      } else {
        const saved = localStorage.getItem("chavruta-lang");
        if (saved === "he" || saved === "en") {
          initialLang = saved;
        }
      }
    } catch {}
    setLang(initialLang);
  }, []);

  const toggleLang = () => {
    const next: Lang = lang === "he" ? "en" : "he";
    setLang(next);
    try {
      localStorage.setItem("chavruta-lang", next);
    } catch {}
  };

  const loadInvites = useCallback(() => {
    api.orgs.invites().then((r) => setInvites(r.invites)).catch(() => setInvites([]));
  }, []);

  const load = useCallback((asDemo: boolean) => {
    setLoading(true);
    setDenied(false);
    api.orgs
      .panel(asDemo)
      .then(setPanel)
      .catch(() => setDenied(true))
      .finally(() => setLoading(false));
    loadInvites();
  }, [loadInvites]);

  useEffect(() => {
    // Try the caller's own school first; the operator, who belongs to none, falls back to the
    // synthetic one so the panel can be inspected without opening a real school's records.
    api.orgs
      .panel(false)
      .then((p) => {
        setPanel(p);
        setLoading(false);
      })
      .catch(() =>
        api.orgs
          .panel(true)
          .then((p) => {
            setPanel(p);
            setDemo(true);
          })
          .catch(() => setDenied(true))
          .finally(() => setLoading(false)),
      );
  }, []);

  async function mintCode(role: string) {
    setBusy(true);
    try {
      const res = await api.orgs.invite(role, role === "student" ? 30 : 1);
      setCode(res.code);
      loadInvites();
    } finally {
      setBusy(false);
    }
  }

  async function revoke(c: string) {
    if (!window.confirm(tr(lang, "schoolConfirmRevokeCode"))) return;
    setBusy(true);
    try {
      await api.orgs.revokeInvite(c);
      if (code === c) setCode(null);
      loadInvites();
    } finally {
      setBusy(false);
    }
  }

  async function closeSchool() {
    if (!window.confirm(tr(lang, "schoolConfirmClose"))) return;
    setBusy(true);
    try {
      await api.orgs.close();
      window.location.href = "/";
    } finally {
      setBusy(false);
    }
  }

  async function removeMember(ownerId: string) {
    if (!window.confirm(tr(lang, "schoolConfirmRemoveMember")))
      return;
    setBusy(true);
    try {
      await api.orgs.removeMember(ownerId);
      load(demo);
    } finally {
      setBusy(false);
    }
  }

  async function readmit(ownerId: string) {
    setBusy(true);
    try {
      await api.orgs.readmitMember(ownerId);
      load(demo);
    } finally {
      setBusy(false);
    }
  }

  async function setCap(ownerId: string, current: number) {
    // Stated in questions, because that is the unit an administrator thinks in — and the two special
    // values are spelled out. Until recently 0 meant "tier default" here and "no ceiling at all" one
    // layer down, so an admin who typed 0 to stop a disruptive student silently gave them the
    // largest allowance in the system.
    const raw = window.prompt(
      tr(lang, "schoolPromptSetCap"),
      String(current > 0 ? Math.round(current / TURN) : current),
    );
    if (raw === null) return;
    const asked = Number(raw);
    if (!Number.isFinite(asked) || asked < -1) return;
    setBusy(true);
    try {
      await api.orgs.setCap(ownerId, asked > 0 ? Math.round(asked * TURN) : asked);
      load(demo);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="h-dvh grid place-items-center text-ink/50 text-sm">{tr(lang, "schoolLoading")}</div>;
  }

  if (denied || !panel) {
    return (
      <div dir={lang === "he" ? "rtl" : "ltr"} className="h-dvh grid place-items-center p-4">
        <div className="glass rounded-[28px] p-8 max-w-sm text-center flex flex-col gap-3">
          <h1 className="font-serif text-xl font-bold text-tekhelet">{tr(lang, "schoolDeniedTitle")}</h1>
          <p className="text-sm text-ink/60">{tr(lang, "schoolDeniedBody")}</p>
          <Link href="/" className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold">
            {tr(lang, "backToApp")}
          </Link>
        </div>
      </div>
    );
  }

  const isAdminRole = panel.role === "admin";
  // The sample school is for LOOKING at. Every mutating /orgs/* route resolves the organisation from
  // the caller's own membership, and the operator is a member of nothing — so minting a code or
  // setting a cap here would 404. The controls stay visible, because seeing the real screen is the
  // whole point of the demo, but they are inert and say so.
  const demoReadOnly = !!panel.is_demo;
  const demoNote = demoReadOnly ? tr(lang, "schoolDemoNote") : undefined;
  const num = (n: number) => n.toLocaleString(lang === "he" ? "he-IL" : "en-US");
  const asTurns = (tokens: number) => Math.round(tokens / TURN);
  const roleName = (role: string) => (lang === "he" ? ROLE_HE[role] : ROLE_EN[role]) ?? role;

  return (
    <div dir={lang === "he" ? "rtl" : "ltr"} className="min-h-dvh flex flex-col gap-4 p-4 lg:p-8">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <Icon name="school" className="text-tekhelet text-[28px]" />
          <div>
            <h1 className="font-serif text-xl font-bold text-tekhelet">{panel.name}</h1>
            <p className="text-xs text-ink/50">
              {roleName(panel.role)} · {tr(lang, "schoolSeatsSubtitle").replace("{used}", num(panel.seats_used)).replace("{total}", num(panel.seats))}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={toggleLang}
            className="px-3 py-1.5 rounded-full glass text-ink/70 text-xs font-semibold"
          >
            עברית · EN
          </button>
          <Link
            href={demoReadOnly ? "/admin" : "/"}
            className="text-xs text-tekhelet/80 hover:text-tekhelet font-semibold"
          >
            {demoReadOnly ? tr(lang, "schoolBackToAdmin") : tr(lang, "backToApp")}
          </Link>
        </div>
      </header>

      {panel.is_demo && (
        <div className="glass rounded-2xl p-3 text-xs text-ink/70 border border-gold/40">
          <b>{tr(lang, "schoolDemoTitle")}</b> {tr(lang, "schoolDemoNotice")}
        </div>
      )}

      {panel.warn_80 && (
        <div className="glass rounded-2xl p-3 text-xs text-gold-soft border border-gold/50">
          {tr(lang, "schoolWarn80")}
        </div>
      )}

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          {
            label: tr(lang, "schoolQuestionsToday"),
            value: num(asTurns(panel.pool_used_today)),
            sub: tr(lang, "schoolSubOfApprox").replace("{n}", num(asTurns(panel.pool_daily))),
          },
          {
            label: tr(lang, "schoolQuestionsWeek"),
            value: num(asTurns(panel.pool_used_week)),
            sub: tr(lang, "schoolSubOfApprox").replace("{n}", num(asTurns(panel.pool_weekly))),
          },
          {
            label: tr(lang, "schoolLessonsWeek"),
            value: num(panel.lessons_used_week),
            sub: tr(lang, "schoolSubOf").replace("{n}", num(panel.weekly_lessons)),
          },
          {
            label: tr(lang, "schoolUsageToday"),
            value: `${Math.round(panel.pool_pct_today * 100)}%`,
            sub: tr(lang, "schoolSubDailyQuota"),
          },
        ].map((c) => (
          <div key={c.label} className="glass rounded-2xl p-4">
            <div className="text-[11px] text-ink/50">{c.label}</div>
            <div className="text-2xl font-bold text-tekhelet">{c.value}</div>
            <div className="text-[11px] text-ink/40">{c.sub}</div>
          </div>
        ))}
      </section>

      <section className="glass rounded-2xl p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-serif font-bold text-tekhelet">{tr(lang, "schoolAddMembers")}</h2>
          <div className="flex gap-2">
            <button
              disabled={busy || demoReadOnly}
              title={demoNote}
              onClick={() => mintCode("student")}
              className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold disabled:opacity-40"
            >
              {tr(lang, "schoolStudentCodeBtn")}
            </button>
            {isAdminRole && (
              <button
                disabled={busy || demoReadOnly}
                title={demoNote}
                onClick={() => mintCode("teacher")}
                className="text-xs px-3 py-2 rounded-xl glass text-tekhelet font-semibold disabled:opacity-40"
              >
                {tr(lang, "schoolTeacherCodeBtn")}
              </button>
            )}
          </div>
        </div>
        {code ? (
          <div className="flex items-center gap-2 flex-wrap">
            <code className="text-lg font-bold tracking-[0.2em] text-tekhelet bg-ink/5 px-3 py-2 rounded-xl">
              {code}
            </code>
            <button
              onClick={() => {
                navigator.clipboard?.writeText(code);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              className="text-xs px-3 py-2 rounded-xl glass text-tekhelet"
            >
              {copied ? tr(lang, "copied") : tr(lang, "copy")}
            </button>
          </div>
        ) : null}
        <p className="text-[11px] text-ink/50 leading-relaxed">
          {tr(lang, "schoolInviteExplainer")}
        </p>

        {invites.length > 0 && (
          <div className="flex flex-col gap-1 border-t border-ink/10 pt-3">
            <div className="text-[11px] text-ink/50">{tr(lang, "schoolActiveCodes")}</div>
            {invites.map((inv) => (
              <div key={inv.code} className="flex items-center gap-2 flex-wrap text-xs">
                <code className="font-mono tracking-widest text-tekhelet">{inv.code}</code>
                <span className="text-ink/50">
                  {roleName(inv.role)} · {tr(lang, "schoolUses").replace("{used}", num(inv.used_count)).replace("{max}", num(inv.max_uses))}
                  {inv.expires_at ? tr(lang, "schoolExpiresPrefix").replace("{date}", inv.expires_at.slice(0, 10)) : ""}
                </span>
                <button
                  disabled={busy || demoReadOnly}
                  title={demoNote}
                  onClick={() => revoke(inv.code)}
                  className="text-[11px] px-2 py-1 rounded-lg glass text-ink/60 disabled:opacity-40"
                >
                  {tr(lang, "schoolRevokeCode")}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="glass rounded-2xl p-4 overflow-x-auto">
        <h2 className="font-serif font-bold text-tekhelet mb-3">{tr(lang, "schoolMembersHeading")}</h2>
        <table className="w-full text-sm min-w-[560px]">
          <thead className="text-[11px] text-ink/50">
            <tr>
              <th className="text-start font-normal pb-2">{tr(lang, "schoolColMember")}</th>
              <th className="text-start font-normal pb-2">{tr(lang, "schoolColRole")}</th>
              <th className="text-start font-normal pb-2">{tr(lang, "schoolColQuestionsToday")}</th>
              <th className="text-start font-normal pb-2">{tr(lang, "schoolColQuestionsWeek")}</th>
              <th className="text-start font-normal pb-2">{tr(lang, "schoolColDailyCap")}</th>
              {isAdminRole && <th className="text-start font-normal pb-2">{tr(lang, "schoolColActions")}</th>}
            </tr>
          </thead>
          <tbody>
            {panel.members.map((m) => (
              <tr key={m.owner_id} className="border-t border-ink/10">
                <td className="py-2 font-mono text-[11px] text-ink/70">{m.owner_id}</td>
                <td className="py-2">
                  <span className="inline-flex items-center gap-1.5">
                    {roleName(m.role)}
                    {!m.accepted ? (
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-ink/10 text-ink/50">
                        {tr(lang, "schoolStatusRemoved")}
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-tekhelet/10 text-tekhelet">
                        {tr(lang, "schoolStatusActive")}
                      </span>
                    )}
                  </span>
                </td>
                <td className="py-2">{num(asTurns(m.tokens_today))}</td>
                <td className="py-2">{num(asTurns(m.tokens_week))}</td>
                <td className="py-2 text-ink/60">
                  {m.daily_cap < 0 ? (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-gold/15 text-gold-soft">
                      {tr(lang, "schoolStatusBlocked")}
                    </span>
                  ) : m.daily_cap > 0 ? (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-ink/10 text-ink/70">
                        {tr(lang, "schoolStatusCustomCap")}
                      </span>
                      <span>{num(asTurns(m.daily_cap))}</span>
                    </span>
                  ) : (
                    <span className="text-xs text-ink/50">{tr(lang, "schoolStatusDefaultCap")}</span>
                  )}
                </td>
                {isAdminRole && (
                  <td className="py-2 flex gap-2">
                    {m.accepted ? (
                      <>
                        <button
                          disabled={busy || demoReadOnly}
                          title={demoNote}
                          onClick={() => setCap(m.owner_id, m.daily_cap)}
                          className="text-[11px] px-2 py-1 rounded-lg glass text-tekhelet disabled:opacity-40"
                        >
                          {tr(lang, "schoolActionSetCap")}
                        </button>
                        <button
                          disabled={busy || demoReadOnly || m.role === "admin"}
                          title={demoNote}
                          onClick={() => removeMember(m.owner_id)}
                          className="text-[11px] px-2 py-1 rounded-lg glass text-ink/60 disabled:opacity-30"
                        >
                          {tr(lang, "schoolActionRemove")}
                        </button>
                      </>
                    ) : (
                      <button
                        disabled={busy || demoReadOnly}
                        title={demoNote}
                        onClick={() => readmit(m.owner_id)}
                        className="text-[11px] px-2 py-1 rounded-lg glass text-tekhelet disabled:opacity-40"
                      >
                        {tr(lang, "schoolActionReadmit")}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {isAdminRole && (
        <section className="glass rounded-2xl p-4">
          <h2 className="font-serif font-bold text-tekhelet mb-1">{tr(lang, "schoolTopicsHeading")}</h2>
          <p className="text-[11px] text-ink/50 mb-3">
            {tr(lang, "schoolTopicsExplainer")}
          </p>
          {panel.topics.length ? (
            <ul className="flex flex-wrap gap-2">
              {panel.topics.map((t) => (
                <li key={t.intent} className="text-xs glass rounded-xl px-3 py-2">
                  <b className="text-tekhelet">{t.intent}</b>
                  <span className="text-ink/50"> · {num(t.requests)} {tr(lang, "schoolTopicsRequests")}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-ink/40">{tr(lang, "schoolTopicsEmpty")}</p>
          )}
        </section>
      )}

      {/* Only the owner, and only on a real school. The way out of an otherwise closed loop: an
          owner cannot leave their own org and cannot delete their account while it exists. */}
      {isAdminRole && !panel.is_demo && (
        <section className="glass rounded-2xl p-4 border border-gold/30">
          <h2 className="font-serif font-bold text-tekhelet mb-1">{tr(lang, "schoolCloseHeading")}</h2>
          <p className="text-[11px] text-ink/50 mb-3 leading-relaxed">
            {tr(lang, "schoolCloseExplainer")}
          </p>
          <button
            disabled={busy}
            onClick={closeSchool}
            className="text-xs px-3 py-2 rounded-xl glass text-gold-soft font-semibold disabled:opacity-40"
          >
            {tr(lang, "schoolCloseBtn")}
          </button>
        </section>
      )}
    </div>
  );
}
