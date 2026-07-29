// Terms of Use — the in-app rendering of docs/legal/terms-{he,en}.md. Keep this in sync with those
// files (they are the canonical reference for legal review). DRAFT: the operator name and jurisdiction
// are placeholders to fill before going live.
import type { Lang } from "./types";

export const TERMS_VERSION = "1.4";
export const TERMS_EFFECTIVE = "2026-07-27";

interface Section {
  heading: string;
  body: string;
}

const HE: Section[] = [
  { heading: "מהות השירות",
    body: "חברותא AI היא שותפה ללימוד תורה מבוססת בינה מלאכותית, המשיבה ממקורות מצוטטים (תנ\"ך, משנה, גמרא, ראשונים ופוסקים) הנשלפים ממאגר מקורות. השירות נועד ללימוד, עיון והכנת שיעורים." },
  { heading: "אינו פסיקת הלכה",
    body: "התשובות אינן פסיקת הלכה למעשה ואינן תחליף לרב מוסמך. יש לאמת כל מקור במקורו, ולהתייעץ עם רב מוסמך בכל שאלה הלכתית מעשית. אין להסתמך על השירות להכרעה הלכתית, ממונית או אישית." },
  { heading: "דיוק, אחריות והגבלת חבות",
    body: "התוכן נוצר על ידי בינה מלאכותית ועלול להיות שגוי, חלקי או לא מדויק. השירות ניתן \"כמות שהוא\" וללא כל אחריות. במידה המרבית המותרת בדין, המפעיל לא יישא באחריות לכל נזק — ישיר או עקיף — הנובע מהשימוש בשירות או מההסתמכות על התשובות. השימוש על אחריות המשתמש בלבד." },
  { heading: "חשבון והרשמה",
    body: "עליך למסור כתובת אימייל תקינה ולשמור על סודיות פרטי הכניסה. אתה אחראי לכל פעילות בחשבונך, ועליך להודיע לנו על כל שימוש בלתי מורשה." },
  { heading: "גיל — השירות מיועד לבני 18 ומעלה",
    body: "השירות מיועד למשתמשים בני 18 ומעלה בלבד, ואינו מיועד לקטינים. בעת ההרשמה תתבקש לאשר זאת במפורש; האישור הוא תנאי להרשמה ונשמר עם החשבון, וחשבון שיתברר כי נפתח בידי קטין ייסגר. זו הצהרה ולא אימות: ההרשמה נעשית בכתובת אימייל ואין בידינו אמצעי לבדוק גיל, ולכן מה שקיים כאן הוא תיחום ברור של קהל היעד והצהרה מודעת של המשתמש — לא מנגנון טכני. האחריות לעמידה בדרישה היא של המשתמש. חשבונות מוסדיים (בתי ספר, ישיבות, מוסדות חינוך) נרכשים על ידי המוסד ומיועדים לצוות ההוראה הבוגר: השירות בונה חומרי לימוד עבור תלמידים, אך התלמיד אינו משתמש בשירות — המורה הוא שמפעיל אותו." },
  { heading: "תוכן שאתה מעלה",
    body: "בעת צירוף מקורות (טקסט, PDF או Word) אתה מצהיר שיש לך את הזכות להשתמש בהם, ומתיר לנו לעבד אותם לצורך הפקת התשובה. אין להעלות תוכן בלתי חוקי, פוגעני, או המפר זכויות יוצרים או פרטיות של אחר. שים לב: שיחות נמחקות אחרי 3 חודשים — שיחה ללא פעילות במשך 90 יום נמחקת אוטומטית עם הודעותיה, וכל פנייה חדשה מאפסת את הספירה. שיעורים שיצרת אינם נמחקים אוטומטית. אם תוכן חשוב לך לטווח ארוך — הורד ושמור אותו אצלך." },
  { heading: "שימוש הוגן",
    body: "אין לעשות שימוש לרעה בשירות: לרבות עקיפת מגבלות קצב או מכסה, גישה אוטומטית מעבר למותר, עומס מכוון, הנדסה לאחור, או פגיעה בזמינות או באבטחת השירות ומשתמשיו." },
  { heading: "קניין רוחני ומקורות",
    body: "מקורות המאגר כפופים לרישיונות שלהם (לרבות Creative Commons ודרישות ייחוס של Sefaria והמהדירים); הייחוס מוצג לצד המקור. הקוד, העיצוב והממשק שייכים למפעיל." },
  { heading: "פרטיות",
    body: "אנו שומרים את כתובת האימייל שלך (דרך ספק ההרשמה), את היסטוריית השיחות והשיעורים, ומוני שימוש. איננו מוכרים את המידע שלך. הוא משמש להפעלת השירות ולשיוך הנתונים אליך בלבד." },
  { heading: "מכסות, תוכניות בתשלום וביטול מנוי",
    body: "השירות עשוי לכלול תוכנית חינמית עם מכסה יומית, ותוכניות בתשלום. אנו רשאים לשנות מכסות, מחירים ותכונות מעת לעת, בהודעה סבירה. המחירים המפורסמים כוללים מע\"מ. המכסות הנוכחיות של כל תוכנית מפורסמות בעמוד 'המכסות הנוכחיות' באפליקציה; הרעה מהותית במכסות מזכה מנוי משלם לבטל. כל החיובים חודשיים — גם התוכנית השנתית, שהיא תעריף מוזל הנגבה בשנים-עשר תשלומים חודשיים ולא תשלום שנתי מראש; הסכום השנתי המוצג הוא סך שנים-עשר התשלומים. ניתן לבטל מנוי בכל עת ובלחיצה אחת (הגדרות → ביטול מנוי): החיוב הבא נפסק מיד, והגישה נמשכת עד תום החודש ששולם. בנוסף, מכיוון שהעסקה נעשית מרחוק, ניתן לבטלה תוך 14 יום ולקבל החזר בניכוי דמי ביטול כמותר בדין (5% או 100 ₪ — הנמוך מביניהם); ההחזר יבוצע לאמצעי התשלום שבו בוצעה העסקה, בתוך 14 יום ממועד קבלת הודעת הביטול, ויונפק זיכוי בהתאם. ביטול מנוי (הפסקת חיוב) אינו זהה למחיקת חשבון." },
  { heading: "קופונים",
    body: "עשויים להיות מוצעים קופונים מעת לעת. קופון מקנה הטבה מסוימת (דרג תוכנית לתקופה מוגבלת או זיכויים). לקופון יש תאריך תפוגה והוא אינו ניתן להעברה. לקופון אין ערך כספי ואין אפשרות לפדות אותו במזומן. אם עסקה שנעשתה בקופון מבוטלת — ההטבה שניתנה בקופון נשללת." },
  { heading: "שינויים בתנאים",
    body: "אנו רשאים לעדכן תנאים אלה. המשך השימוש לאחר עדכון מהווה הסכמה לתנאים המעודכנים; הגרסה העדכנית תוצג תמיד בשירות." },
  { heading: "קהל היעד, דין וסמכות שיפוט",
    body: "השירות מוצע למשתמשים בישראל. הוא אינו מכוון לתושבי האיחוד האירופי, הממלכה המאוחדת או שטחים אחרים שבהם חלים דיני הגנת מידע נפרדים, ואיננו מציעים אותו שם. איננו חוסמים גישה טכנית לפי מיקום — ואיננו מתיימרים לכך — אך תיחום זה קובע למי השירות מיועד ולפי איזה דין נבנה. על תנאים אלה יחול דין מדינת ישראל, וסמכות השיפוט הבלעדית תהיה של בתי המשפט המוסמכים במדינת ישראל." },
  { heading: "יצירת קשר",
    body: "השירות מופעל על ידי יהודה רובין. לשאלות בנוגע לתנאים אלה: rubinyehuda8@gmail.com" },
];

const EN: Section[] = [
  { heading: "The Service",
    body: "Chavruta AI is an AI-based Torah study partner that answers with cited sources (Tanakh, Mishnah, Gemara, Rishonim and Poskim) retrieved from a source corpus. It is intended for study, review and lesson preparation." },
  { heading: "Not a Halachic Ruling",
    body: "Answers are not a halachic ruling and are no substitute for a qualified rabbi. Verify every source at its origin and consult a qualified rabbi on any practical halachic question. Do not rely on the Service for any halachic, financial or personal decision." },
  { heading: "Accuracy, Warranty and Liability",
    body: "Content is AI-generated and may be wrong, partial or inaccurate. The Service is provided \"AS IS\" without any warranty. To the maximum extent permitted by law, the operator shall not be liable for any damage — direct or indirect — arising from use of the Service or reliance on the answers. Use is at your own risk." },
  { heading: "Account and Registration",
    body: "You must provide a valid email address and keep your login credentials confidential. You are responsible for all activity under your account and must notify us of any unauthorized use." },
  { heading: "Age — the Service is for users aged 18 and over",
    body: "The Service is intended for users aged 18 and over, and is not intended for minors. At registration you are asked to confirm this explicitly; the confirmation is a condition of registration and is recorded with the account, and an account found to have been opened by a minor will be closed. This is a declaration, not verification: registration is by email address and we have no means of checking age, so what exists here is a clear scoping of the intended audience and a deliberate statement by the user — not a technical mechanism. Meeting the requirement is the user's responsibility. Institutional accounts (schools, yeshivot, educational institutions) are contracted by the institution and are intended for adult teaching staff: the Service builds teaching material for pupils, but the pupil is not a user of the Service — the teacher operates it." },
  { heading: "Content You Upload",
    body: "When attaching sources (text, PDF or Word) you represent that you have the right to use them, and you permit us to process them to generate your answer. Do not upload unlawful or offensive content, or content that infringes another's copyright or privacy. Note — conversations are deleted after 3 months: a conversation with no activity for 90 days is deleted automatically with its messages, and any new message in that conversation resets the clock. Lessons you create are not deleted automatically. If content is important to you for the long term — download and save it yourself. See also the Privacy Policy, section 5." },
  { heading: "Acceptable Use",
    body: "Do not misuse the Service, including bypassing rate or quota limits, automated access beyond what is permitted, deliberate overload, reverse engineering, or harming the availability or security of the Service or its users." },
  { heading: "Intellectual Property and Sources",
    body: "Corpus sources are subject to their own licenses (including Creative Commons and the attribution requirements of Sefaria and the editions); the attribution is shown beside each source. The Service's code, design and interface belong to the operator." },
  { heading: "Privacy",
    body: "We store your email address (via the registration provider), your conversation and lesson history, and usage counters. We do not sell your data. It is used only to run the Service and to associate your content with you." },
  { heading: "Quotas, Paid Plans and Cancellation",
    body: "The Service may include a free plan with a daily quota, and paid plans. We may change quotas, prices and features from time to time, with reasonable notice. Prices listed include VAT. The current limits for each plan are published on the 'Current limits' page in the app; a material reduction in limits entitles a paying subscriber to cancel. All billing is monthly — including the annual plan, which is a discounted rate charged in twelve monthly instalments rather than a year taken up front; the annual figure shown is the total of those twelve. You may cancel at any time in one click (Settings → Cancel subscription): the next charge stops immediately and access continues to the end of the month you already paid for. Because the transaction is made at a distance you may also cancel within 14 days for a refund, less the fee permitted by law (5% or ₪100, whichever is lower); the refund is made to the payment method used, within 14 days of our receiving your notice, and a credit note is issued accordingly. Cancelling a subscription (stopping billing) is not the same as deleting your account." },
  { heading: "Coupons",
    body: "Coupons may be offered from time to time. A coupon grants a specific benefit (a time-limited plan tier or credits). Coupons have an expiration date and are not transferable. A coupon has no cash value and cannot be redeemed for money. If a transaction that used a coupon is cancelled, the coupon-granted benefit is revoked." },
  { heading: "Changes to These Terms",
    body: "We may update these terms. Continued use after an update constitutes acceptance; the current version is always shown in the Service." },
  { heading: "Intended Audience, Governing Law and Jurisdiction",
    body: "The Service is offered to users in Israel. It is not directed at residents of the European Union, the United Kingdom, or other territories with separate data-protection regimes, and we do not offer it there. We do not technically block access by location — and we do not claim to — but this scoping states who the Service is intended for and the law it was built against. These terms are governed by the law of the State of Israel, and the exclusive jurisdiction shall be the competent courts of the State of Israel." },
  { heading: "Contact",
    body: "The Service is operated by Yehuda Rubin. Questions about these terms: rubinyehuda8@gmail.com" },
];

export function termsSections(lang: Lang): Section[] {
  return lang === "en" ? EN : HE;
}

// ── Privacy Policy (mirrors docs/legal/privacy-{he,en}.md) ────────────────────
export const PRIVACY_VERSION = "1.3";
export const PRIVACY_EFFECTIVE = "2026-07-27";

const PRIVACY_HE: Section[] = [
  { heading: "איזה מידע אנו אוספים",
    body: "פרטי חשבון (כתובת אימייל, המנוהלת דרך ספק ההרשמה Supabase — איננו רואים או שומרים את סיסמתך); תוכן שאתה יוצר (שאלות, היסטוריית שיחות, שיעורים שמורים, ומקורות שתצרף); נתוני שימוש ומדידה — עבור כל בקשה אנו רושמים מדדים בלבד: מועד (כולל שעה ויום בשבוע), סוג הפעולה, שפה, כמות טוקנים, מספר קריאות למודל, משך העיבוד, האם נמצאו מקורות וכמה, מספר קבצים שצורפו, ולשיעור גם קהל היעד, שכבת הגיל והאורך — כדי להבין מה לשפר, מה עולה יותר ומתי השירות עמוס; איננו שומרים ברשומות אלו את תוכן השאלה, התשובה, המקורות או הקבצים, אלא מדידות בלבד. כן נשמרות רשומות טכניות בסיסיות (מזהה בקשה, כתובת IP) לאבטחה והגבלת קצב; נתוני מנוי וחיוב אם תרכוש מנוי (סטטוס, תקופה, ואסמכתא לאמצעי התשלום אצל ספק הסליקה — לא מספר הכרטיס המלא); והעדפות מקומיות (שפה וערכת נושא) הנשמרות בדפדפן שלך." },
  { heading: "כיצד אנו משתמשים במידע",
    body: "להפעלת השירות והפקת התשובות; לשיוך השיחות והשיעורים לחשבונך; לאכיפת מכסות; ולאבטחת השירות ומניעת שימוש לרעה. איננו משתמשים בתוכן שלך לפרסום." },
  { heading: "עיבוד ואימון על ידי ספק המודל",
    body: "כדי לייצר תשובה, שאלתך (וכל מקור שצירפת) נשלחת לספק מודל הבינה המלאכותית שלנו. ייתכן שספק המודל ישתמש בנתונים שנשלחו אליו — שאלותיך והמקורות שצירפת — גם לצורך שיפור ואימון מודלי הבינה המלאכותית שלו, בכפוף לתנאיו. לפיכך אין להזין מידע רגיש, סודי או אישי שאינך מעוניין שיעובד או שישמש לאימון. אין בשירות מסלול 'ללא אימון', גם לא בתשלום ולא לחשבון מוסדי: אין הגדרה שאפשר לבקש מאיתנו להפעיל ואין דרג שקונה אותה. הכלל הזה — מה שלא הוזן, לא נשלח — הוא ההגנה היחידה הקיימת כאן." },
  { heading: "שיתוף מידע",
    body: "איננו מוכרים את המידע שלך. אנו נעזרים בספקי משנה להפעלת השירות בלבד: ספק ההרשמה (Supabase), ספק מודל הבינה המלאכותית, וספק האירוח; ולמנויים בתשלום — ספק הסליקה (PayPlus) וספק החשבוניות (חשבונית ירוקה). מקורות הלימוד נשלפים ממאגר מבוסס Sefaria. נחשוף מידע אם נידרש על פי דין." },
  { heading: "שמירת מידע",
    body: "שיחות נשמרות עד 3 חודשים: שיחה שלא הייתה בה פעילות במשך 90 יום נמחקת אוטומטית על הודעותיה, וכל פנייה חדשה בשיחה מאפסת את הספירה — כדאי להוריד ולשמור אצלך תוכן שחשוב לך לטווח ארוך. שיעורים שיצרת אינם נמחקים אוטומטית ונשמרים עד שתמחק אותם או עד סגירת החשבון. נתוני המדידה נשמרים לניתוח מגמות, ובעת מחיקת חשבון הם מנותקים מזהותך ונשארים כנתון מצטבר אנונימי. רשומות חיוב — אנו נדרשים בדין לשמור תיעוד חשבונאי (כ-7 שנים) ללא שיוך לזהותך: סכום, מועד ומספר חשבונית בלבד, גם לאחר מחיקת החשבון. רשומות טכניות נשמרות לפרק זמן מוגבל לצורך אבטחה." },
  { heading: "הזכויות שלך",
    body: "באפשרותך לצפות ולמחוק את השיחות והשיעורים שלך בכל עת מתוך האפליקציה. באפשרותך לבקש מחיקת חשבון מתוך ההגדרות — המחיקה מתבצעת לאחר תקופת חסד (כ-30 יום) שבה ניתן לבטלה, ובתומה כל הנתונים נמחקים לצמיתות. באפשרותך לעדכן פרטים בהגדרות. נשיב לבקשת עיון תוך 30 יום (ניתן להאריך ב-15 יום לפי דין); לאחר מחיקה/תיקון נודיע גם לצדדים שקיבלו את המידע ב-3 השנים שקדמו, ככל שנדרש." },
  { heading: "השירות אינו מיועד לקטינים",
    body: "השירות מיועד לבני 18 ומעלה בלבד (תנאי השימוש), ובהרשמה נדרש אישור גיל מפורש הנשמר עם החשבון. איננו אוספים ביודעין מידע אישי מקטינים; אם נגלה שחשבון נפתח בידי קטין נסגור אותו ונמחק את המידע. זו הצהרה ולא אימות — ההרשמה נעשית בכתובת אימייל ואין בידינו אמצעי לבדוק גיל. בבתי ספר ובחשבונות מוסדיים: השירות בונה חומרי לימוד עבור תלמידים, והתלמיד אינו משתמש בשירות — המורה, שהוא בגיר, הוא שמזין את השאלה ומקבל את השיעור. איננו מבקשים ואיננו זקוקים לנתוני תלמידים כלל ואין לנו חשבונות תלמידים. ולכן הכלל שנשאר: מה שמוזן נשלח לספק המודל, ואין להזין פרטים מזהים של אף אדם — תלמידים בכלל זה. הכנת שיעור לכיתה ג' אינה מחייבת את שמו של אף ילד. איננו מכוונים שיווק לקטינים ואיננו עושים שימוש בנתוניהם." },
  { heading: "עוגיות ואחסון מקומי",
    body: "אנו משתמשים באחסון מקומי בדפדפן לשמירת העדפות ולניהול ההתחברות (טוקן הפעלה). איננו משתמשים בעוגיות מעקב פרסומיות של צד שלישי." },
  { heading: "העברת מידע אל מחוץ לישראל",
    body: "חלק מספקי המשנה (למשל Supabase וספק המודל) מעבדים מידע מחוץ לישראל. ההעברה נעשית על בסיס הסכמתך ובכפוף להתחייבות חוזית של הספקים לשמור על רמת הגנה מקבילה לנדרש בדין הישראלי ולא להעביר את המידע הלאה ללא הרשאה, לפי תקנות הגנת הפרטיות (העברת מידע אל מאגרים מחוץ לגבולות המדינה)." },
  { heading: "אבטחה",
    body: "אנו נוקטים אמצעים סבירים — אימות, הגבלת קצב, והצפנה בתעבורה — בהתאם לתקנות הגנת הפרטיות (אבטחת מידע), התשע\"ז-2017. במקרה של אירוע אבטחה חמור נפעל ליידע את הרשות להגנת הפרטיות ואת המשתמשים כנדרש בדין. עם זאת אף שיטה אינה מאובטחת ב-100% ואיננו יכולים להבטיח אבטחה מוחלטת." },
  { heading: "המאגר, מטרותיו והדין החל",
    body: "בעל המאגר ומנהלו: יהודה רובין, מפעיל השירות. מטרות המאגר: הפעלת השירות והפקת התשובות והשיעורים; שיוך השיחות, השיעורים והמנוי לחשבונך; אכיפת מכסות ומניעת שימוש לרעה; חיוב, הוצאת חשבוניות וקיום חובות חשבונאיות; אבטחת השירות; והבנת דפוסי שימוש מצטברים לצורך שיפור. איננו משתמשים במידע למטרה אחרת ואיננו מוכרים אותו; שימוש למטרה חדשה יחייב עדכון של מדיניות זו והודעה מראש. מדיניות זו נערכה לפי חוק הגנת הפרטיות, התשמ\"א-1981, כנוסחו לאחר תיקון 13 (בתוקף מאוגוסט 2025), ולפי התקנות שמכוחו. תיקון 13 מחייב מינוי ממונה על הגנת הפרטיות בנסיבות מסוימות; להערכתנו בהיקף הפעילות הנוכחי החובה אינה חלה — אין כאן מידע רגיש כהגדרתו בחוק, אין ניטור שיטתי, ואנו רושמים מדדים ולא תוכן. ההערכה נבחנת מחדש עם גידול בהיקף." },
  { heading: "שינויים ויצירת קשר",
    body: "אנו רשאים לעדכן מדיניות זו; הגרסה העדכנית תוצג תמיד בשירות. לשאלות בנושא פרטיות: rubinyehuda8@gmail.com" },
];

const PRIVACY_EN: Section[] = [
  { heading: "What We Collect",
    body: "Account details (your email, managed via the registration provider Supabase — we do not see or store your password); content you create (questions, conversation history, saved lessons, and sources you attach); usage and measurement data (for each request we record measurements only: timestamp including local hour and weekday, action type — question / explanation / comparison / halacha / chavruta / lesson building — language of request, tokens consumed, number of model calls, processing duration, whether sources were found and how many, number of files attached, and for a lesson its target audience, grade band and length; we do NOT record the content of the question, answer, sources or attached files); basic technical records (request id, IP address) for security and rate limiting; subscription & billing data if you purchase a plan (status, period, and a reference to the payment method at the payment provider — not the full card number); and local preferences (language and theme) stored in your browser. The measurements tell us what needs improvement, what costs more, and at which hours the Service is busy." },
  { heading: "How We Use It",
    body: "To operate the Service and generate answers; to associate your conversations and lessons with your account; to enforce quotas; and to secure the Service and prevent abuse. We do not use your content for advertising." },
  { heading: "Processing and Training by the Model Provider",
    body: "To generate an answer, your question (and any source you attach) is sent to our AI model provider. The model provider may use the data sent to it — your questions and attached sources — also to improve and train its AI models, subject to its terms. Therefore do not enter sensitive, confidential or personal information you would not want processed, or used for model training, this way. There is no 'no-training' path on this Service — not on a paid plan and not on an institutional account: there is no setting you can ask us to enable and no tier that buys one. This rule — what is not entered is not sent — is the only protection that exists here." },
  { heading: "Sharing",
    body: "We do not sell your data. We use sub-processors only to run the Service: the registration provider (Supabase), the AI model provider, and the hosting provider; and for paid subscribers, the payment provider (PayPlus) and the invoicing provider (Green Invoice). Study sources are retrieved from a Sefaria-based corpus. We will disclose information if required by law." },
  { heading: "Retention",
    body: "Conversations are kept for up to 3 months: a conversation with no activity for 90 days is deleted automatically with its messages, and any new message in the conversation resets the count — a conversation you keep returning to will not be deleted. We recommend downloading and saving content that is important to you for the long term. Lessons you create are not deleted automatically and are kept until you delete them or until the account is closed. Measurement data (section 1) is kept for trend analysis, and on account deletion it is detached from your identity and remains as anonymous aggregate data only. Billing records — we are required by law to keep accounting documentation (about 7 years) without association to your identity: amount, date and invoice number only, even after account deletion. Technical records are retained for a limited period for security." },
  { heading: "Your Rights",
    body: "You can view and delete your conversations and lessons at any time in the app. You can request account deletion from Settings — it is carried out after a grace period (about 30 days) during which you can cancel, after which all data is permanently erased. You can update details in settings. We will answer an access request within 30 days (extendable by 15 days as permitted by law); after a deletion/correction we will also notify parties who received the data in the preceding 3 years, where required." },
  { heading: "The Service Is Not Intended for Minors",
    body: "The Service is for users aged 18 and over only (Terms of Use), and registration requires an explicit age confirmation recorded with the account. We do not knowingly collect personal information from minors; if we learn an account was opened by a minor we will close it and delete the information. This is a declaration, not verification — registration is by email address and we have no means of checking age. In schools and institutional accounts: the Service builds teaching material for pupils, and the pupil is not a user of the Service — the teacher, who is an adult, enters the question and receives the lesson. We neither ask for nor need pupil data of any kind, and there are no pupil accounts. Hence the rule that remains: what is entered is sent to the model provider, and you must not enter identifying details of any person — pupils included. Preparing a lesson for a third-grade class does not require any child's name. We do not direct marketing at minors and do not use their data." },
  { heading: "Cookies and Local Storage",
    body: "We use browser local storage to keep your preferences and maintain your active session (session token). We do not use third-party advertising or tracking cookies." },
  { heading: "Transfer of Data Outside Israel",
    body: "Some sub-processors (e.g. Supabase and the model provider) process data outside Israel. The transfer is made on the basis of your consent and subject to a contractual undertaking by the providers to maintain protection equivalent to that required under Israeli law and not to transfer the data onward without authorization, under the Protection of Privacy Regulations (Transfer of Data to Databases Abroad), 2001." },
  { heading: "Security",
    body: "We take reasonable measures — authentication, rate limiting, and encryption in transit — in accordance with the Protection of Privacy (Data Security) Regulations, 2017. In the event of a serious security incident we will act to notify the Privacy Protection Authority and affected users as required by law. However, no method is 100% secure and we cannot guarantee absolute security." },
  { heading: "The Database, Its Purposes, and the Applicable Law",
    body: "Database owner and manager: Yehuda Rubin, the operator of the Service. Purposes of the database: operating the Service and producing answers and lessons; associating conversations, lessons and the subscription with your account; enforcing quotas and preventing abuse; billing, invoicing and meeting accounting obligations; securing the Service; and understanding aggregate usage patterns in order to improve it. We do not use the information for any other purpose and we do not sell it; use for a new purpose would require an update to this policy and advance notice. This policy is drawn up under the Protection of Privacy Law, 5741-1981, as amended by Amendment 13 (in force August 2025), and the regulations under it. Amendment 13 requires appointing a Privacy Protection Officer in certain circumstances; in our assessment the obligation does not apply at the current scale — there is no sensitive data as defined in the Law, no systematic monitoring, and we record measurements rather than content. The assessment is revisited as the scale grows." },
  { heading: "Changes and Contact",
    body: "We may update this policy; the current version is always shown in the Service. For privacy questions: rubinyehuda8@gmail.com" },
];

export function privacySections(lang: Lang): Section[] {
  return lang === "en" ? PRIVACY_EN : PRIVACY_HE;
}

// ── Accessibility Statement (mirrors docs/legal/accessibility-{he,en}.md) ─────
export const ACCESSIBILITY_VERSION = "1.0";
export const ACCESSIBILITY_EFFECTIVE = "2026-07-30";

const ACCESSIBILITY_HE: Section[] = [
  { heading: "מחויבותנו לנגישות",
    body: "חברותא AI פועלת להנגיש את השירות לאנשים עם מוגבלויות, ולאפשר שימוש נוח ושוויוני ככל הניתן. אנו עובדים לפי עקרונות תקן הנגישות לתכנים באינטרנט (WCAG) ברמה סבירה למוצר בשלב זה, ומשפרים את הנגישות באופן הדרגתי ומתמשך." },
  { heading: "מצב הנגישות הנוכחי",
    body: "השירות תומך, בין היתר, בניווט מקלדת בסיסי, בתמיכה בטכנולוגיות מסייעות נפוצות, ובתצוגה בעברית (RTL) ובאנגלית (LTR). זהו מוצר חדש וקטן, ועדיין ייתכנו חלקים שאינם נגישים באופן מלא. אנו פועלים לאתר ולתקן פערים אלה ככל שהמוצר גדל." },
  { heading: "פנייה בנושאי נגישות",
    body: "נתקלת בבעיית נגישות בשימוש בשירות? נשמח שתפנה אלינו — רכז הנגישות: יהודה רובין, rubinyehuda8@gmail.com — ונשתדל להשיב ולטפל בפנייה בזמן סביר." },
  { heading: "שינויים בהצהרה",
    body: "הצהרה זו עשויה להתעדכן מעת לעת ככל שהנגישות משתפרת; הגרסה העדכנית תוצג תמיד בשירות." },
];

const ACCESSIBILITY_EN: Section[] = [
  { heading: "Our Commitment to Accessibility",
    body: "Chavruta AI works to make the Service accessible to people with disabilities, and to enable comfortable and equal use as far as reasonably possible. We follow the principles of the Web Content Accessibility Guidelines (WCAG) at a reasonable level for a product at this stage, and we improve accessibility gradually and on an ongoing basis." },
  { heading: "Current Accessibility Status",
    body: "The Service supports, among other things, basic keyboard navigation, support for common assistive technologies, and display in both Hebrew (RTL) and English (LTR). This is a new, small product, and some parts may not yet be fully accessible. We work to identify and fix such gaps as the product grows." },
  { heading: "Contact Us About Accessibility",
    body: "Encountered an accessibility issue while using the Service? We'd welcome you contacting us — Accessibility Coordinator: Yehuda Rubin, rubinyehuda8@gmail.com — and we will do our best to respond and address it within a reasonable time." },
  { heading: "Changes to This Statement",
    body: "This statement may be updated from time to time as accessibility improves; the current version is always shown in the Service." },
];

export function accessibilitySections(lang: Lang): Section[] {
  return lang === "en" ? ACCESSIBILITY_EN : ACCESSIBILITY_HE;
}
