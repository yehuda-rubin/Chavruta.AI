"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import type { Lang } from "@/lib/types";
import { api, type Tier } from "@/lib/api";
import "./landing.css";

const CONTACT_EMAIL = "rubinyehuda8@gmail.com";

// The landing is its own surface (visitors who are not signed in), so its copy lives here rather than
// in lib/i18n.ts, which is the app's string table. Both languages carry the same claims — and only
// claims the product can back: every answer cites its source, and "no source" is a valid answer.
const COPY = {
  he: {
    navWhy: "למה חברותא", navHow: "איך זה עובד", navPrice: "מחירים", navFaq: "שאלות",
    signIn: "כניסה", start: "התחילו חינם", langBtn: "English",
    h1: "החברותא שתמיד מוכנה ללמוד איתך",
    lead: "שואלים בחופשיות על כל ספר ביהדות. מקבלים תשובה ברורה, וכל משפט בה מפנה למקור שאפשר לפתוח.",
    ctaPrimary: "להתחיל ללמוד", ctaSecondary: "איך זה עובד",
    demoQ: "למה התורה מתחילה ב״בראשית״ ולא במצווה הראשונה?",
    demoA: "רש״י פותח בדיוק בשאלה הזו. לפי רבי יצחק, היה ראוי להתחיל את התורה מ״החדש הזה לכם״, שהיא המצווה הראשונה שנצטוו בה ישראל.",
    demoRefs: ["רש״י על בראשית א׳:א׳", "בראשית א׳:א׳"],
    whyTitle: "לא עוד תשובה בלי כתובת", whySub: "שלושה דברים שמבדילים את חברותא מכל צ׳אט אחר.",
    t1h: "2.4 מיליון קטעי מקור במאגר", t1p: "תנ״ך, משנה, תלמוד, הלכה, שו״ת ומפרשים, ב־15 קטגוריות.",
    t2h: "״לא מצאתי״ זו תשובה", t2p: "כשאין מקור, חברותא אומרת את זה. בלי המצאות, בלי ניחושים.",
    t3h: "רישיון נקי", t3p: "כל המקורות מותרים לשימוש מסחרי.",
    t4h: "דרכים ללמוד", t4p: "בוחרים מצב ושואלים.",
    modes: ["שיעור", "הסבר", "שאלה ותשובה", "הלכה ושו״ת", "חברותא"],
    betaModes: ["פרשת השבוע", "דף יומי", "דף מקורות"], beta: "בטא",
    stepsTitle: "שלושה צעדים",
    steps: [["שואלים", "בעברית או באנגלית, בניסוח חופשי."], ["חברותא מחפשת", "במאגר המקורות, כולל המפרשים."], ["מקבלים ובודקים", "תשובה עם הפניות שאפשר ללחוץ עליהן."]],
    priceTitle: "מתחילים בחינם", priceSub: "משדרגים רק כשצריך עוד.",
    free: "חינם", perMonth: "חודש", pickFree: "להתחיל", pickPaid: "לבחור",
    freeBullets: ["כל המקורות והציטוטים", "היסטוריית שיחות", "מכסה יומית"],
    paidBullet: (m: number) => `פי ${m} מהמכסה החינמית`,
    paidBullets2: ["כל המקורות והציטוטים"],
    inst: "מוסד לימוד או ישיבה?", instLink: "דברו איתנו",
    faqTitle: "שאלות נפוצות",
    faq: [
      ["האם חברותא מחליפה רב?", "לא. היא כלי לימוד שמראה מקורות. לשאלות הלכה למעשה, פונים לרב."],
      ["מאיפה המקורות?", "ממאגר ברישיון שמאפשר שימוש מסחרי, בהם ספריא ופרויקטים פתוחים אחרים."],
      ["מה קורה כשאין תשובה במקורות?", "חברותא אומרת שלא נמצא מקור, ולא מנסה לנחש."],
    ],
    finalH: "בואו נלמד ביחד", finalBtn: "הרשמה חינם",
    terms: "תנאי שימוש", privacy: "פרטיות", access: "נגישות", limits: "מכסות ותוכניות", brand: "חברותא",
  },
  en: {
    navWhy: "Why Chavruta", navHow: "How it works", navPrice: "Pricing", navFaq: "FAQ",
    signIn: "Sign in", start: "Start free", langBtn: "עברית",
    h1: "The study partner who is always ready to learn with you",
    lead: "Ask freely about any Jewish text. Get a clear answer where every sentence points to a source you can open.",
    ctaPrimary: "Start learning", ctaSecondary: "How it works",
    demoQ: "Why does the Torah begin with “Bereshit” and not with the first commandment?",
    demoA: "Rashi opens with exactly this question. According to Rabbi Yitzchak, the Torah should have begun with “This month shall be for you”, the first commandment given to Israel.",
    demoRefs: ["Rashi on Genesis 1:1", "Genesis 1:1"],
    whyTitle: "No more answers without an address", whySub: "Three things that set Chavruta apart from any other chat.",
    t1h: "2.4 million source passages", t1p: "Tanakh, Mishnah, Talmud, Halakha, Responsa and commentaries, in 15 categories.",
    t2h: "“I couldn’t find it” is an answer", t2p: "When there is no source, Chavruta says so. No inventing, no guessing.",
    t3h: "Clean licensing", t3p: "Every source is cleared for commercial use.",
    t4h: "Ways to learn", t4p: "Pick a mode and ask.",
    modes: ["Lesson", "Explain", "Q&A", "Halakha & Responsa", "Chavruta"],
    betaModes: ["Weekly Parsha", "Daf Yomi", "Source sheet"], beta: "beta",
    stepsTitle: "Three steps",
    steps: [["Ask", "In Hebrew or English, in your own words."], ["Chavruta searches", "Across the source library, commentaries included."], ["Read and check", "An answer with references you can click."]],
    priceTitle: "Start free", priceSub: "Upgrade only when you need more.",
    free: "Free", perMonth: "month", pickFree: "Get started", pickPaid: "Choose",
    freeBullets: ["All sources and citations", "Chat history", "Daily allowance"],
    paidBullet: (m: number) => `${m}× the free allowance`,
    paidBullets2: ["All sources and citations"],
    inst: "A school or yeshiva?", instLink: "Talk to us",
    faqTitle: "Frequently asked",
    faq: [
      ["Does Chavruta replace a rabbi?", "No. It is a study tool that shows sources. For practical halakhic questions, ask a rabbi."],
      ["Where do the sources come from?", "From a library licensed for commercial use, including Sefaria and other open projects."],
      ["What if the sources have no answer?", "Chavruta says no source was found, and does not guess."],
    ],
    finalH: "Let’s learn together", finalBtn: "Sign up free",
    terms: "Terms", privacy: "Privacy", access: "Accessibility", limits: "Plans & limits", brand: "Chavruta",
  },
} as const;

export function Landing() {
  const [lang, setLang] = useState<Lang>("he");
  const [tiers, setTiers] = useState<Tier[]>([]);
  const c = COPY[lang];

  // Same persisted key the app uses, so choosing English here carries into the app after sign-in.
  useEffect(() => {
    try {
      // Same rule as the app: a saved choice wins, otherwise follow the browser (Hebrew or English).
      const saved = localStorage.getItem("chavruta-lang");
      if (saved === "en" || saved === "he") setLang(saved);
      else setLang((navigator.language || "").toLowerCase().startsWith("he") ? "he" : "en");
    } catch {}
    api.billingConfig().then((cfg) => setTiers(cfg?.tiers ?? [])).catch(() => setTiers([]));
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "he" ? "rtl" : "ltr";
    try { localStorage.setItem("chavruta-lang", lang); } catch {}
  }, [lang]);

  const free = tiers.find((t) => t.seats === 1 && t.price_ils === 0);
  const paid = tiers.filter((t) => t.seats === 1 && (t.price_ils ?? 0) > 0);
  const hasInstitutions = tiers.some((t) => t.seats > 1);
  const signup = "/signup?mode=up";

  return (
    <div className="lp">
      <nav className="top">
        <div className="in">
          <Link className="logo" href="/welcome">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="" />
            {c.brand}
          </Link>
          <ul>
            <li><a href="#why">{c.navWhy}</a></li>
            <li><a href="#how">{c.navHow}</a></li>
            {free && <li><a href="#pricing">{c.navPrice}</a></li>}
            <li><a href="#faq">{c.navFaq}</a></li>
          </ul>
          <div className="actions">
            <button className="langbtn" onClick={() => setLang(lang === "he" ? "en" : "he")}>{c.langBtn}</button>
            <Link className="btn w" href="/signup">{c.signIn}</Link>
            <Link className="btn v" href={signup}>{c.start}</Link>
          </div>
        </div>
      </nav>

      <header className="hero">
        <div className="wrap">
          <h1>{c.h1}</h1>
          <p className="lead">{c.lead}</p>
          <div className="cta">
            <Link className="btn v big" href={signup}>{c.ctaPrimary}</Link>
            <a className="btn w big" href="#how">{c.ctaSecondary}</a>
          </div>
          <div className="chatdemo" aria-label={c.demoQ}>
            <div className="b me">{c.demoQ}</div>
            <div className="b ai">
              {c.demoA}
              <div className="srcrow">
                {c.demoRefs.map((r) => <span className="ref" key={r}>{r}</span>)}
              </div>
            </div>
          </div>
        </div>
      </header>

      <section id="why">
        <div className="wrap">
          <h2>{c.whyTitle}</h2>
          <p className="sub">{c.whySub}</p>
          <div className="bento">
            <div className="tile t1"><h3>{c.t1h}</h3><p>{c.t1p}</p></div>
            <div className="tile t2"><h3>{c.t2h}</h3><p>{c.t2p}</p></div>
            <div className="tile t3"><h3>{c.t3h}</h3><p>{c.t3p}</p></div>
            <div className="tile t4">
              <h3>{c.t4h}</h3><p>{c.t4p}</p>
              <div className="chips">
                {c.modes.map((m) => <span key={m}>{m}</span>)}
                {c.betaModes.map((m) => <span className="beta" key={m}>{m} · {c.beta}</span>)}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="how" style={{ paddingTop: 20 }}>
        <div className="wrap">
          <h2>{c.stepsTitle}</h2>
          <div className="steps">
            {c.steps.map(([h, p], i) => (
              <div className="step" key={h}>
                <div className="dot">{i + 1}</div>
                <h3>{h}</h3><p>{p}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing is rendered from the live catalogue (/billing/config), never hard-coded, so the
          landing can't drift from what checkout charges. No catalogue (billing off / API down) =
          no pricing section at all, rather than a stale number. */}
      {free && (
        <section id="pricing">
          <div className="wrap">
            <h2>{c.priceTitle}</h2>
            <p className="sub">{c.priceSub}</p>
            <div className="price">
              <div className="plan">
                <h3>{free.name || c.free}</h3>
                <div className="p">₪0</div>
                <ul>{c.freeBullets.map((b) => <li key={b}>{b}</li>)}</ul>
                <Link className="btn w" href={signup}>{c.pickFree}</Link>
              </div>
              {paid.map((t, i) => (
                <div className={"plan" + (i === 0 ? " hot" : "")} key={t.id}>
                  <h3>{t.name}</h3>
                  <div className="p">₪{t.price_ils}<small> / {c.perMonth}</small></div>
                  <ul>
                    <li>{c.paidBullet(t.multiple)}</li>
                    {c.paidBullets2.map((b) => <li key={b}>{b}</li>)}
                  </ul>
                  <Link className={"btn " + (i === 0 ? "v" : "w")} href={signup}>{c.pickPaid} {t.name}</Link>
                </div>
              ))}
            </div>
            {hasInstitutions && (
              <p className="inst">{c.inst} <a href={`mailto:${CONTACT_EMAIL}`}>{c.instLink}</a></p>
            )}
          </div>
        </section>
      )}

      <section id="faq" style={{ paddingTop: 0 }}>
        <div className="wrap" style={{ maxWidth: 780 }}>
          <h2 style={{ marginBottom: 40 }}>{c.faqTitle}</h2>
          {c.faq.map(([q, a]) => (
            <details key={q}><summary>{q}</summary><p>{a}</p></details>
          ))}
        </div>
      </section>

      <div className="final">
        <h2>{c.finalH}</h2>
        <Link className="btn big" href={signup}>{c.finalBtn}</Link>
      </div>

      <footer>
        <div className="wrap">
          <Link className="logo" style={{ fontSize: 20 }} href="/welcome">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="" style={{ width: 30, height: 30 }} />
            {c.brand}
          </Link>
          <nav aria-label="footer">
            <Link href="/terms">{c.terms}</Link>
            <Link href="/privacy">{c.privacy}</Link>
            <Link href="/accessibility">{c.access}</Link>
            <Link href="/limits">{c.limits}</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
