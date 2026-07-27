// Terms of Use — the in-app rendering of docs/legal/terms-{he,en}.md. Keep this in sync with those
// files (they are the canonical reference for legal review). DRAFT: the operator name and jurisdiction
// are placeholders to fill before going live.
import type { Lang } from "./types";

export const TERMS_VERSION = "1.1";
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
  { heading: "גיל וחשבונות מוסדיים",
    body: "עליך להיות בן 18 לפחות כדי לרכוש מנוי בתשלום, או שתהיה הסכמת הורה/אפוטרופוס. לחשבונות מוסדיים (בתי ספר, ישיבות, מוסדות חינוך) — המנוי נרכש על ידי המוסד עצמו, ולא על ידי תלמידים בודדים." },
  { heading: "תוכן שאתה מעלה",
    body: "בעת צירוף מקורות (טקסט, PDF או Word) אתה מצהיר שיש לך את הזכות להשתמש בהם, ומתיר לנו לעבד אותם לצורך הפקת התשובה. אין להעלות תוכן בלתי חוקי, פוגעני, או המפר זכויות יוצרים או פרטיות של אחר. שים לב: שיחות נמחקות אחרי 3 חודשים — שיחה ללא פעילות במשך 90 יום נמחקת אוטומטית עם הודעותיה, וכל פנייה חדשה מאפסת את הספירה. שיעורים שיצרת אינם נמחקים אוטומטית. אם תוכן חשוב לך לטווח ארוך — הורד ושמור אותו אצלך." },
  { heading: "שימוש הוגן",
    body: "אין לעשות שימוש לרעה בשירות: לרבות עקיפת מגבלות קצב או מכסה, גישה אוטומטית מעבר למותר, עומס מכוון, הנדסה לאחור, או פגיעה בזמינות או באבטחת השירות ומשתמשיו." },
  { heading: "קניין רוחני ומקורות",
    body: "מקורות המאגר כפופים לרישיונות שלהם (לרבות Creative Commons ודרישות ייחוס של Sefaria והמהדירים); הייחוס מוצג לצד המקור. הקוד, העיצוב והממשק שייכים למפעיל." },
  { heading: "פרטיות",
    body: "אנו שומרים את כתובת האימייל שלך (דרך ספק ההרשמה), את היסטוריית השיחות והשיעורים, ומוני שימוש. איננו מוכרים את המידע שלך. הוא משמש להפעלת השירות ולשיוך הנתונים אליך בלבד." },
  { heading: "מכסות, תוכניות בתשלום וביטול מנוי",
    body: "השירות עשוי לכלול תוכנית חינמית עם מכסה יומית, ותוכניות בתשלום. אנו רשאים לשנות מכסות, מחירים ותכונות מעת לעת, בהודעה סבירה. המחירים המפורסמים כוללים מע\"מ. ניתן לבטל מנוי בתשלום בכל עת; החיוב העתידי נפסק מיד (לא ייגבו חיובים נוספים), והגישה לתוכנית בתשלום נמשכת עד תום התקופה ששולמה — כך שאינך משלם עבור תקופה שלא נוצלה. ביטול מנוי (הפסקת חיוב) אינו זהה למחיקת חשבון." },
  { heading: "קופונים",
    body: "עשויים להיות מוצעים קופונים מעת לעת. קופון מקנה הטבה מסוימת (דרג תוכנית לתקופה מוגבלת או זיכויים). לקופון יש תאריך תפוגה והוא אינו ניתן להעברה. לקופון אין ערך כספי ואין אפשרות לפדות אותו במזומן. אם עסקה שנעשתה בקופון מבוטלת — ההטבה שניתנה בקופון נשללת." },
  { heading: "שינויים בתנאים",
    body: "אנו רשאים לעדכן תנאים אלה. המשך השימוש לאחר עדכון מהווה הסכמה לתנאים המעודכנים; הגרסה העדכנית תוצג תמיד בשירות." },
  { heading: "דין וסמכות שיפוט",
    body: "על תנאים אלה יחול דין מדינת ישראל, וסמכות השיפוט הבלעדית תהיה של בתי המשפט המוסמכים במדינת ישראל." },
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
  { heading: "Age and Institutional Accounts",
    body: "You must be at least 18 years old to purchase a paid plan, or have the consent of a parent or guardian. For institutional accounts (schools, yeshivot, educational institutions), the subscription is contracted by the institution itself, not by individual pupils." },
  { heading: "Content You Upload",
    body: "When attaching sources (text, PDF or Word) you represent that you have the right to use them, and you permit us to process them to generate your answer. Do not upload unlawful or offensive content, or content that infringes another's copyright or privacy. Note — conversations are deleted after 3 months: a conversation with no activity for 90 days is deleted automatically with its messages, and any new message in that conversation resets the clock. Lessons you create are not deleted automatically. If content is important to you for the long term — download and save it yourself. See also the Privacy Policy, section 5." },
  { heading: "Acceptable Use",
    body: "Do not misuse the Service, including bypassing rate or quota limits, automated access beyond what is permitted, deliberate overload, reverse engineering, or harming the availability or security of the Service or its users." },
  { heading: "Intellectual Property and Sources",
    body: "Corpus sources are subject to their own licenses (including Creative Commons and the attribution requirements of Sefaria and the editions); the attribution is shown beside each source. The Service's code, design and interface belong to the operator." },
  { heading: "Privacy",
    body: "We store your email address (via the registration provider), your conversation and lesson history, and usage counters. We do not sell your data. It is used only to run the Service and to associate your content with you." },
  { heading: "Quotas, Paid Plans and Cancellation",
    body: "The Service may include a free plan with a daily quota, and paid plans. We may change quotas, prices and features from time to time, with reasonable notice. Prices listed include VAT. You may cancel a paid subscription at any time; on cancellation future billing stops immediately (no further charges) and paid access continues until the end of the period you already paid for — so you are not charged for an unused period. Cancelling a subscription (stopping billing) is not the same as deleting your account." },
  { heading: "Coupons",
    body: "Coupons may be offered from time to time. A coupon grants a specific benefit (a time-limited plan tier or credits). Coupons have an expiration date and are not transferable. A coupon has no cash value and cannot be redeemed for money. If a transaction that used a coupon is cancelled, the coupon-granted benefit is revoked." },
  { heading: "Changes to These Terms",
    body: "We may update these terms. Continued use after an update constitutes acceptance; the current version is always shown in the Service." },
  { heading: "Governing Law and Jurisdiction",
    body: "These terms are governed by the law of the State of Israel, and the exclusive jurisdiction shall be the competent courts of the State of Israel." },
  { heading: "Contact",
    body: "The Service is operated by Yehuda Rubin. Questions about these terms: rubinyehuda8@gmail.com" },
];

export function termsSections(lang: Lang): Section[] {
  return lang === "en" ? EN : HE;
}

// ── Privacy Policy (mirrors docs/legal/privacy-{he,en}.md) ────────────────────
export const PRIVACY_VERSION = "1.1";
export const PRIVACY_EFFECTIVE = "2026-07-27";

const PRIVACY_HE: Section[] = [
  { heading: "איזה מידע אנו אוספים",
    body: "פרטי חשבון (כתובת אימייל, המנוהלת דרך ספק ההרשמה Supabase — איננו רואים או שומרים את סיסמתך); תוכן שאתה יוצר (שאלות, היסטוריית שיחות, שיעורים שמורים, ומקורות שתצרף); נתוני שימוש ומדידה — עבור כל בקשה אנו רושמים מדדים בלבד: מועד (כולל שעה ויום בשבוע), סוג הפעולה, שפה, כמות טוקנים, מספר קריאות למודל, משך העיבוד, האם נמצאו מקורות וכמה, מספר קבצים שצורפו, ולשיעור גם קהל היעד, שכבת הגיל והאורך — כדי להבין מה לשפר, מה עולה יותר ומתי השירות עמוס; איננו שומרים ברשומות אלו את תוכן השאלה, התשובה, המקורות או הקבצים, אלא מדידות בלבד. כן נשמרות רשומות טכניות בסיסיות (מזהה בקשה, כתובת IP) לאבטחה והגבלת קצב; נתוני מנוי וחיוב אם תרכוש מנוי (סטטוס, תקופה, ואסמכתא לאמצעי התשלום אצל ספק הסליקה — לא מספר הכרטיס המלא); והעדפות מקומיות (שפה וערכת נושא) הנשמרות בדפדפן שלך." },
  { heading: "כיצד אנו משתמשים במידע",
    body: "להפעלת השירות והפקת התשובות; לשיוך השיחות והשיעורים לחשבונך; לאכיפת מכסות; ולאבטחת השירות ומניעת שימוש לרעה. איננו משתמשים בתוכן שלך לפרסום." },
  { heading: "עיבוד ואימון על ידי ספק המודל",
    body: "כדי לייצר תשובה, שאלתך (וכל מקור שצירפת) נשלחת לספק מודל הבינה המלאכותית שלנו. ייתכן שספק המודל ישתמש בנתונים שנשלחו אליו — שאלותיך והמקורות שצירפת — גם לצורך שיפור ואימון מודלי הבינה המלאכותית שלו, בכפוף לתנאיו. לפיכך אין להזין מידע רגיש, סודי או אישי שאינך מעוניין שיעובד או שישמש לאימון." },
  { heading: "שיתוף מידע",
    body: "איננו מוכרים את המידע שלך. אנו נעזרים בספקי משנה להפעלת השירות בלבד: ספק ההרשמה (Supabase), ספק מודל הבינה המלאכותית, וספק האירוח; ולמנויים בתשלום — ספק הסליקה (PayPlus) וספק החשבוניות (חשבונית ירוקה). מקורות הלימוד נשלפים ממאגר מבוסס Sefaria. נחשוף מידע אם נידרש על פי דין." },
  { heading: "שמירת מידע",
    body: "שיחות נשמרות עד 3 חודשים: שיחה שלא הייתה בה פעילות במשך 90 יום נמחקת אוטומטית על הודעותיה, וכל פנייה חדשה בשיחה מאפסת את הספירה — כדאי להוריד ולשמור אצלך תוכן שחשוב לך לטווח ארוך. שיעורים שיצרת אינם נמחקים אוטומטית ונשמרים עד שתמחק אותם או עד סגירת החשבון. נתוני המדידה נשמרים לניתוח מגמות, ובעת מחיקת חשבון הם מנותקים מזהותך ונשארים כנתון מצטבר אנונימי. רשומות חיוב — אנו נדרשים בדין לשמור תיעוד חשבונאי (כ-7 שנים) ללא שיוך לזהותך: סכום, מועד ומספר חשבונית בלבד, גם לאחר מחיקת החשבון. רשומות טכניות נשמרות לפרק זמן מוגבל לצורך אבטחה." },
  { heading: "הזכויות שלך",
    body: "באפשרותך לצפות ולמחוק את השיחות והשיעורים שלך בכל עת מתוך האפליקציה. באפשרותך לבקש מחיקת חשבון מתוך ההגדרות — המחיקה מתבצעת לאחר תקופת חסד (כ-30 יום) שבה ניתן לבטלה, ובתומה כל הנתונים נמחקים לצמיתות. באפשרותך לעדכן פרטים בהגדרות. נשיב לבקשת עיון תוך 30 יום (ניתן להאריך ב-15 יום לפי דין); לאחר מחיקה/תיקון נודיע גם לצדדים שקיבלו את המידע ב-3 השנים שקדמו, ככל שנדרש." },
  { heading: "קטינים ובתי ספר",
    body: "השירות מיועד גם ללימוד בבתי ספר; שימוש על ידי קטינים ייעשה באחריות ובפיקוח הורה, מורה או מוסד חינוכי. כאשר הגישה נעשית דרך מוסד חינוכי — המוסד הוא הגורם המסכים והאחראי לנתוני התלמידים ואנחנו מעבד עבורו. חשוב: כמפורט בסעיף העיבוד, שאלות ומקורות שמוזנים נשלחים לספק המודל ועשויים לשמש גם לאימון מודליו — לפיכך אין להזין פרטים מזהים או מידע אישי של קטינים (שם, פרטי קשר, מיקום וכד'). איננו עושים שימוש בנתוני קטינים לשיווק; הסכמת הורה ניתנת לביטול בכל עת. איננו אוספים ביודעין מידע אישי מקטינים מעבר לאימייל לצורך התחברות." },
  { heading: "עוגיות ואחסון מקומי",
    body: "אנו משתמשים באחסון מקומי בדפדפן לשמירת העדפות ולניהול ההתחברות (טוקן הפעלה). איננו משתמשים בעוגיות מעקב פרסומיות של צד שלישי." },
  { heading: "העברת מידע אל מחוץ לישראל",
    body: "חלק מספקי המשנה (למשל Supabase וספק המודל) מעבדים מידע מחוץ לישראל. ההעברה נעשית על בסיס הסכמתך ובכפוף להתחייבות חוזית של הספקים לשמור על רמת הגנה מקבילה לנדרש בדין הישראלי ולא להעביר את המידע הלאה ללא הרשאה, לפי תקנות הגנת הפרטיות (העברת מידע אל מאגרים מחוץ לגבולות המדינה)." },
  { heading: "אבטחה",
    body: "אנו נוקטים אמצעים סבירים — אימות, הגבלת קצב, והצפנה בתעבורה — בהתאם לתקנות הגנת הפרטיות (אבטחת מידע), התשע\"ז-2017. במקרה של אירוע אבטחה חמור נפעל ליידע את הרשות להגנת הפרטיות ואת המשתמשים כנדרש בדין. עם זאת אף שיטה אינה מאובטחת ב-100% ואיננו יכולים להבטיח אבטחה מוחלטת." },
  { heading: "שינויים ויצירת קשר",
    body: "אנו רשאים לעדכן מדיניות זו; הגרסה העדכנית תוצג תמיד בשירות. לשאלות בנושא פרטיות: rubinyehuda8@gmail.com" },
];

const PRIVACY_EN: Section[] = [
  { heading: "What We Collect",
    body: "Account details (your email, managed via the registration provider Supabase — we do not see or store your password); content you create (questions, conversation history, saved lessons, and sources you attach); usage and measurement data (for each request we record measurements only: timestamp including local hour and weekday, action type — question / explanation / comparison / halacha / chavruta / lesson building — language of request, tokens consumed, number of model calls, processing duration, whether sources were found and how many, number of files attached, and for a lesson its target audience, grade band and length; we do NOT record the content of the question, answer, sources or attached files); basic technical records (request id, IP address) for security and rate limiting; subscription & billing data if you purchase a plan (status, period, and a reference to the payment method at the payment provider — not the full card number); and local preferences (language and theme) stored in your browser. The measurements tell us what needs improvement, what costs more, and at which hours the Service is busy." },
  { heading: "How We Use It",
    body: "To operate the Service and generate answers; to associate your conversations and lessons with your account; to enforce quotas; and to secure the Service and prevent abuse. We do not use your content for advertising." },
  { heading: "Processing and Training by the Model Provider",
    body: "To generate an answer, your question (and any source you attach) is sent to our AI model provider. The model provider may use the data sent to it — your questions and attached sources — also to improve and train its AI models, subject to its terms. Therefore do not enter sensitive, confidential or personal information you would not want processed, or used for model training, this way." },
  { heading: "Sharing",
    body: "We do not sell your data. We use sub-processors only to run the Service: the registration provider (Supabase), the AI model provider, and the hosting provider; and for paid subscribers, the payment provider (PayPlus) and the invoicing provider (Green Invoice). Study sources are retrieved from a Sefaria-based corpus. We will disclose information if required by law." },
  { heading: "Retention",
    body: "Conversations are kept for up to 3 months: a conversation with no activity for 90 days is deleted automatically with its messages, and any new message in the conversation resets the count — a conversation you keep returning to will not be deleted. We recommend downloading and saving content that is important to you for the long term. Lessons you create are not deleted automatically and are kept until you delete them or until the account is closed. Measurement data (section 1) is kept for trend analysis, and on account deletion it is detached from your identity and remains as anonymous aggregate data only. Billing records — we are required by law to keep accounting documentation (about 7 years) without association to your identity: amount, date and invoice number only, even after account deletion. Technical records are retained for a limited period for security." },
  { heading: "Your Rights",
    body: "You can view and delete your conversations and lessons at any time in the app. You can request account deletion from Settings — it is carried out after a grace period (about 30 days) during which you can cancel, after which all data is permanently erased. You can update details in settings. We will answer an access request within 30 days (extendable by 15 days as permitted by law); after a deletion/correction we will also notify parties who received the data in the preceding 3 years, where required." },
  { heading: "Minors and Schools",
    body: "The Service is also intended for study in schools; use by minors should be under the responsibility and supervision of a parent, teacher or educational institution. When access is via an educational institution, the institution is the consenting party and controller of student data and we act as its processor. Important: as noted in the processing section, questions and sources entered are sent to the model provider and may also be used to train its models — so do not enter identifying or personal information about minors (name, contact details, location, etc.). We do not use minors' data for marketing; parental consent can be withdrawn at any time. We do not knowingly collect personal information from minors beyond an email used for sign-in." },
  { heading: "Cookies and Local Storage",
    body: "We use browser local storage to keep your preferences and maintain your active session (session token). We do not use third-party advertising or tracking cookies." },
  { heading: "Transfer of Data Outside Israel",
    body: "Some sub-processors (e.g. Supabase and the model provider) process data outside Israel. The transfer is made on the basis of your consent and subject to a contractual undertaking by the providers to maintain protection equivalent to that required under Israeli law and not to transfer the data onward without authorization, under the Protection of Privacy Regulations (Transfer of Data to Databases Abroad), 2001." },
  { heading: "Security",
    body: "We take reasonable measures — authentication, rate limiting, and encryption in transit — in accordance with the Protection of Privacy (Data Security) Regulations, 2017. In the event of a serious security incident we will act to notify the Privacy Protection Authority and affected users as required by law. However, no method is 100% secure and we cannot guarantee absolute security." },
  { heading: "Changes and Contact",
    body: "We may update this policy; the current version is always shown in the Service. For privacy questions: rubinyehuda8@gmail.com" },
];

export function privacySections(lang: Lang): Section[] {
  return lang === "en" ? PRIVACY_EN : PRIVACY_HE;
}
