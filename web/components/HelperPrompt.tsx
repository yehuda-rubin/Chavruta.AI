"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type HelperStatus } from "@/lib/api";
import { Icon } from "./Icon";

// The dev-helper side the PERSON sees: the invitation, and any notices the operator sent them.
//
// The invitation panel carries the full disclosure — what changes, what is stored, and that it is
// voluntary and unpaid. That placement is the point, not decoration: the privacy policy is where
// this is written down, but the moment of asking is where it has to be READ. Consent given without
// seeing what is collected is not informed consent, and a link to a policy page is a poor substitute
// for the two lines that actually matter.
//
// Renders nothing at all for the overwhelming majority of accounts, which is why it is safe to mount
// unconditionally: /helper/status answers {status:"none"} rather than erroring for them.
export function HelperPrompt() {
  const [st, setSt] = useState<HelperStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.helper.status().then(setSt).catch(() => setSt(null));
  }, []);

  if (!st) return null;

  const answer = async (accept: boolean) => {
    setBusy(true);
    try {
      setSt(accept ? await api.helper.accept() : await api.helper.decline());
    } catch {
      /* leave the panel up — an unanswered invitation is better than one that looks answered */
    } finally {
      setBusy(false);
    }
  };

  const dismiss = async (id: number) => {
    // Optimistic: the notice disappears now and the read receipt catches up. A failed write means
    // it reappears on the next load, which is the right way round for something already read.
    setSt({ ...st, unread: st.unread.filter((m) => m.id !== id) });
    try {
      await api.helper.markRead(id);
    } catch {
      /* ignore */
    }
  };

  return (
    <>
      {st.status === "invited" && (
        <div
          role="dialog"
          aria-modal="false"
          aria-labelledby="helper-invite-title"
          className="glass rounded-[24px] p-5 flex flex-col gap-3 ring-1 ring-tekhelet/20"
        >
          <h2 id="helper-invite-title" className="font-serif text-lg font-bold text-tekhelet">
            הוזמנת לעזור בבדיקת המערכת
          </h2>
          {st.note && <p className="text-xs text-ink/50">הערת המזמין: {st.note}</p>}

          <div className="text-sm text-ink/75 leading-relaxed flex flex-col gap-2">
            <p>
              <b>מה תקבל:</b> מכסת שימוש בגובה התוכנית הבסיסית, ויכולות שטרם נפתחו לכולם. אם כבר יש
              לך מנוי בתשלום — הוא לא נפגע, והמכסה הגבוהה מבין השתיים חלה.
            </p>
            <p>
              <b>מה יישמר עליך:</b> שהצטרפת ומתי, אילו יכולות נפתחו, ההערה שלמעלה, והודעות שיישלחו
              אליך כאן — כולל מתי קראת אותן. הכול נמחק אם תמחק את החשבון.
            </p>
            <p>
              <b>מה זה לא:</b> זו אינה עבודה ואין עליה תשלום. אין מטלות, אין שעות, ואפשר להפסיק בכל
              רגע. יכולות שטרם שוחררו עלולות להיות חלקיות או להשתנות.
            </p>
          </div>

          <p className="text-[11px] text-ink/40">
            הפירוט המלא ב
            <Link href="/terms" className="text-tekhelet/70 hover:underline"> תנאי השימוש</Link>
            {" (סעיף 11א) וב"}
            <Link href="/privacy" className="text-tekhelet/70 hover:underline">מדיניות הפרטיות</Link>.
          </p>

          <div className="flex gap-2">
            <button
              disabled={busy}
              onClick={() => answer(true)}
              className="px-4 py-2 rounded-2xl grad text-white font-semibold text-sm disabled:opacity-40"
            >
              מאשר, אני בעניין
            </button>
            <button
              disabled={busy}
              onClick={() => answer(false)}
              className="px-4 py-2 rounded-2xl glass text-ink/60 font-semibold text-sm disabled:opacity-40"
            >
              לא תודה
            </button>
          </div>
        </div>
      )}

      {st.unread.map((m) => (
        <div
          key={m.id}
          role="status"
          className="glass rounded-[24px] p-4 flex items-start gap-3 ring-1 ring-gold/25"
        >
          <Icon name="campaign" className="text-gold text-[20px] mt-0.5 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-ink/80 whitespace-pre-line break-words">{m.body}</p>
            <p className="text-[11px] text-ink/40 mt-1">
              {new Date(m.at).toLocaleString("he-IL")}
            </p>
          </div>
          <button
            onClick={() => dismiss(m.id)}
            aria-label="סמן כנקרא"
            title="סמן כנקרא"
            className="shrink-0 h-8 w-8 rounded-full glass grid place-items-center text-ink/50 hover:text-tekhelet"
          >
            <Icon name="close" className="text-[18px]" />
          </button>
        </div>
      ))}
    </>
  );
}
