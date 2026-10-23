# -*- coding: utf-8 -*-
import subprocess
import os
import sys

html_content = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<title>תוכנית עסקית ומודל תמחור – חברותא (Chavruta.AI)</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;600;700;800&family=Frank+Ruhl+Libre:wght@700;900&display=swap');

  @page {
    size: A4;
    margin: 13mm 11mm 13mm 11mm;
    @bottom-center {
      content: counter(page);
    }
  }

  body {
    font-family: 'Assistant', 'Segoe UI', Arial, sans-serif;
    color: #1a202c;
    line-height: 1.45;
    font-size: 11.5px;
    background: #fff;
    margin: 0;
    padding: 0;
  }

  .cover {
    border-bottom: 3px solid #2b6cb0;
    padding-bottom: 12px;
    margin-bottom: 16px;
  }
  .badge {
    display: inline-block;
    background: #ebf8ff;
    color: #2b6cb0;
    font-weight: 700;
    font-size: 9.5px;
    padding: 2px 7px;
    border-radius: 20px;
    border: 1px solid #bee3f8;
    margin-bottom: 5px;
  }
  h1 {
    font-family: 'Frank Ruhl Libre', serif;
    font-size: 25px;
    color: #1a365d;
    margin: 0 0 4px 0;
    line-height: 1.2;
    font-weight: 900;
  }
  .subtitle {
    font-size: 13px;
    color: #4a5568;
    margin: 0 0 8px 0;
    font-weight: 400;
  }
  .meta-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 7px;
    background: #f7fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 7px 9px;
    font-size: 10px;
  }
  .meta-item strong {
    color: #2d3748;
    display: block;
    margin-bottom: 1px;
  }

  h2 {
    font-family: 'Frank Ruhl Libre', serif;
    font-size: 16px;
    color: #2b6cb0;
    border-bottom: 1.5px solid #e2e8f0;
    padding-bottom: 3px;
    margin-top: 15px;
    margin-bottom: 6px;
    font-weight: 900;
    page-break-after: avoid;
  }
  h3 {
    font-size: 12.5px;
    color: #2d3748;
    margin-top: 10px;
    margin-bottom: 3px;
    font-weight: 700;
    page-break-after: avoid;
  }

  p {
    margin: 0 0 5px 0;
    text-align: justify;
  }

  .callout {
    background: #ebf8ff;
    border-right: 4px solid #3182ce;
    border-radius: 4px 6px 6px 4px;
    padding: 7px 10px;
    margin: 8px 0;
    font-size: 11px;
  }
  .callout.warning {
    background: #fffaf0;
    border-right-color: #dd6b20;
    color: #744210;
  }
  .callout.success {
    background: #f0fff4;
    border-right-color: #38a169;
    color: #22543d;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    margin: 7px 0 10px 0;
    font-size: 10.5px;
    page-break-inside: avoid;
  }
  th, td {
    padding: 5px 7px;
    text-align: right;
    border-bottom: 1px solid #e2e8f0;
  }
  th {
    background: #edf2f7;
    color: #2d3748;
    font-weight: 700;
    font-size: 10px;
    border-top: 1px solid #cbd5e0;
  }
  tr:nth-child(even) td {
    background: #f8fafc;
  }
  .highlight-row td {
    background: #ebf8ff !important;
    font-weight: 700;
    color: #2b6cb0;
  }

  ul, ol {
    margin: 0 0 6px 0;
    padding-right: 15px;
  }
  li {
    margin-bottom: 2px;
  }

  .grid-3 {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 7px;
    margin: 8px 0;
    page-break-inside: avoid;
  }
  .card {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
  }
  .card-val {
    font-size: 16px;
    font-weight: 800;
    color: #2b6cb0;
    margin-bottom: 1px;
  }
  .card-lbl {
    font-size: 10px;
    font-weight: 600;
    color: #4a5568;
    margin-bottom: 2px;
  }
  .card-desc {
    font-size: 9px;
    color: #718096;
    line-height: 1.25;
  }

  .page-break {
    page-break-before: always;
  }

  .footer-note {
    margin-top: 15px;
    padding-top: 6px;
    border-top: 1px solid #e2e8f0;
    font-size: 9px;
    color: #a0aec0;
    text-align: center;
  }
</style>
</head>
<body>

<div class="cover">
  <div class="badge">מסמך אסטרטגי וניהולי פנימי · אוקטובר 2026 (מהדורה v15)</div>
  <h1>תוכנית עסקית ומודל תמחור – חברותא (Chavruta.AI)</h1>
  <div class="subtitle">הקשר מקורות מלא (ללא Reranker), תקרת 60K טוקנים בשרת להגנה ממדרגות מחיר, וניתוח רגישות מחמיר</div>
  
  <div class="meta-grid">
    <div class="meta-item"><strong>פרויקט:</strong> Chavruta.AI</div>
    <div class="meta-item"><strong>יוצר ומייסד:</strong> יהודה רובין</div>
    <div class="meta-item"><strong>עלות שאלה בסיסית:</strong> ~0.0097 ₪ (< 1 אגורה!)</div>
    <div class="meta-item"><strong>הוצאות קבועות מלאות:</strong> 750 ₪ לחודש (שרת 300 ₪)</div>
  </div>
</div>

<!-- פרק 1 -->
<h2>1. תמצית מנהלים והכרעות ארכיטקטורה</h2>
<p>
מסמך זה מהווה תוכנית עסקית סופית ומבוססת עבור <strong>חברותא (Chavruta.AI)</strong> — מערכת RAG תורנית מהימנה מעל 2.5 מיליון מקורות ארון הספרים היהודי.
התוכנית מיישמת פתרון ארכיטקטוני מדויק לצד ניתוח רגישות מעמיק:
</p>
<ul>
  <li><strong>הסרת ה-Reranker לטובת איכות תורנית ונאמנות למקורות:</strong> בבדיקות איכות התברר כי ה-Reranker חתך מקורות ומפרשים קריטיים ופגע ברציפות התשובות. המערכת חוזרת ל<strong>שליפת מקורות מלאה ועשירה (כ-19,500 טוקנים קלט)</strong> ללא סינון אגרסיבי, תוך עמידה בעקרון יסוד I (אפס מקורות מומצאים בבנצ'מרק של 50 שאלות).</li>
  <li><strong>מודל הייצור: Luna 6, עם תקרת 60K טוקנים בשרת:</strong>
    ב-Luna 6 מדרגת המחיר הגבוהה מתחילה רק ב-272K טוקנים. השרת (<code>app/api.py</code>) מגביל כל בקשה ל-<strong>60K טוקנים</strong> (חלון נע וסיכום היסטוריה),
    כך שהמדרגה לעולם אינה מופעלת, וכל השאילתות רצות בעלות הבסיס של <strong>פחות מאגורה אחת (~0.0097 ₪)</strong>.
  </li>
  <li><strong>ניתוח עמידות בתרחיש קיצון (Stress-Test):</strong>
    גם אם העלות הממוצעת לשאלה תהיה <strong>פי 4 מההערכה</strong> (כ-0.038 ₪ לשאלה), כל המוצרים נותרים רווחיים מאוד: מנוי חודשי מניב ~17.5 ₪ נטו (60.3%), כרטיסיית 19 ₪ מניבה 11.40 ₪ נטו (60%), וישיבה מניבה כ-608 ₪ נטו.
  </li>
  <li><strong>כיסוי הוצאות קבועות מדויק (750 ₪):</strong>
    ישיבה בינונית ב-790 ₪ + מע"מ מניבה <strong>707.60 ₪</strong> רווח נקי בבסיס (כיסוי של <strong>94.3%</strong> מכל הוצאות החברה, פער של 42.40 ₪ בלבד להגעה ל-100%); <strong>27 כרטיסיות לומד</strong> או <strong>37 מנויים אישיים</strong> מכסים 100% מהוצאות החברה.
  </li>
</ul>

<div class="callout">
  <strong>נתוני שימוש בפועל (מהשרת, 2.8.2026–16.10.2026, ללא חשבון המנהל, מספרים מצטברים בלבד):</strong>
  <ul>
    <li><strong>172 משתמשים ייחודיים</strong> ו-<strong>861 בקשות</strong> בכ-10 שבועות, ללא שום שיווק.</li>
    <li><strong>33 משתמשים חזרו</strong> בשני שבועות שונים או יותר; 47 שאלו 5 שאלות ומעלה.</li>
    <li><strong>29% מהבקשות הן בניית שיעור</strong> (247 מתוך 861), השימוש השני בגודלו אחרי שאלות כלליות; 103 שיעורים נשמרו.</li>
    <li><strong>מגמה:</strong> אוגוסט 126 משתמשים, ספטמבר 55, אוקטובר (עד ה-16) 16. אחרי גל ההשקה השימוש ירד, כי אין מי שעושה שיווק. זה בדיוק הפער שהשותף העסקי סוגר.</li>
    <li><strong>עלות מדודה:</strong> בממוצע 16,250 טוקני קלט ו-1,050 טוקני פלט לבקשה (30 הימים האחרונים, כולל כל סבבי השליפה). זה <strong>מתחת</strong> להנחת התוכנית (19,500 / 1,350), כלומר ההערכה שמרנית.</li>
  </ul>
</div>

<!-- פרק 2 -->
<h2>2. כלכלת היחידה: ניתוח תקרת שרת מול תרחיש קיצון</h2>
<p>
השוואת עלויות המחשוב (לפי שער חליפין 3.7 ₪ לדולר):
</p>
<ul>
  <li><strong>מצב תפעולי מבוקר (תקרת 60K בשרת / Luna 6 – מודל הייצור):</strong>
    שאילתה ממוצעת מכילה 19,500 טוקני קלט ($0.00195) + 1,350 טוקני פלט ($0.000675) = <strong>$0.002625</strong> = <strong>~0.0097 ₪ לשאלה</strong> (פחות מאגורה!).
    תקרת השרת חותכת/מסכמת היסטוריה מעבר ל-60K טוקנים, ולכן מדרגת ה-100K לעולם אינה נחצית.
  </li>
  <li><strong>הערת טוקניזציה ומדידה בעברית:</strong>
    19.5k טוקנים חושבו לפי מדידת BPE. בייצור נמדדו בפועל כ-16,250 טוקני קלט לבקשה, פחות מההנחה. גם אם תהיה הרחבה של 10%–20%, במחיר של $0.10 למיליון העלות נשארת שבריר אגורה ואינה משנה את הכדאיות.
  </li>
  <li><strong>תרחיש קיצון (פי 4 מהבסיס):</strong>
    0.0097 ₪ × 4 ≈ <strong>0.038 ₪ לשאלה</strong> (כ-3.8 אגורות). זה מכסה שיעורים ארוכים, סבבי שליפה נוספים, או העלאת מחיר של ספק המודל.
  </li>
  <li><strong>10 שאלות התנסות בחינם:</strong>
    במצב המבוקר עולות <strong>~0.097 ₪ לנרשם</strong> (פחות מ-10 אגורות); בתרחיש הקיצון עולות כ-0.38 ₪ לנרשם.
  </li>
</ul>

<div class="grid-3">
  <div class="card">
    <div class="card-val">~0.0097 ₪</div>
    <div class="card-lbl">עלות שאילתה בסיסית מבוקרת</div>
    <div class="card-desc">תקרת שרת 60K מונעת הגעה ל-100K טוקנים. פחות מאגורה אחת לשאילתת מקורות מלאה.</div>
  </div>
  <div class="card">
    <div class="card-val">~0.038 ₪</div>
    <div class="card-lbl">תרחיש קיצון (פי 4 מהבסיס)</div>
    <div class="card-desc">גם בהנחה מחמירה מאוד, העלות הממוצעת נשארת מתחת ל-4 אגורות לשאלה.</div>
  </div>
  <div class="card">
    <div class="card-val">750 ₪</div>
    <div class="card-lbl">הוצאה קבועה חודשית מלאה</div>
    <div class="card-desc">שרת פיזי 64GB בטווח עליון (300 ₪) + גיבוי + רואה חשבון (350 ₪) + מסוף סליקה (50 ₪).</div>
  </div>
</div>

<!-- פרק 3 -->
<h2>3. מודל התמחור ורווחיות נקייה ליחידה (השוואת בסיס מול תרחיש קיצון)</h2>
<p>
הטבלה להלן משקללת מע"מ (עוסק מורשה, 18%), עמלת סליקה מלאה (0.50$ + 5% על הברוטו), ומציגה את המרווח הנקי במצב הייצור המבוקר (0.0097 ₪) לצד תרחיש הקיצון המחמיר (0.038 ₪):
</p>
<p>
<strong>מדיניות מע"מ:</strong> המחירים לצרכן הם מחירים סופיים שכוללים מע"מ, ואינם משתנים לפי סוג העוסק. כל עוד העסק פועל כעוסק פטור, 18% אלה נשארים רווח נוסף. אם וכאשר נעבור לעוסק מורשה, לא נצטרך להעלות מחירים.
</p>

<table>
  <thead>
    <tr>
      <th>מוצר / מסלול</th>
      <th>מחיר ברוטו</th>
      <th>מחיר נטו (ללא מע"מ)</th>
      <th>סליקה (0.50$ + 5%)</th>
      <th>מחשוב מבוקר (0.0097 ₪)</th>
      <th>רווח נקי מבוקר</th>
      <th>רווח בתרחיש קיצון (0.038 ₪)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>כרטיסיית כניסה</strong> (50 שאלות · ללא הגבלת זמן)</td>
      <td><strong>19 ₪</strong></td>
      <td>16.10 ₪</td>
      <td>2.80 ₪</td>
      <td>0.49 ₪</td>
      <td><strong>12.81 ₪</strong> (67.4%)</td>
      <td><strong>11.40 ₪</strong> (60.0%)</td>
    </tr>
    <tr>
      <td><strong>כרטיסיית לומד</strong> (120 שאלות · ללא הגבלת זמן)</td>
      <td><strong>39 ₪</strong></td>
      <td>33.05 ₪</td>
      <td>3.80 ₪</td>
      <td>1.16 ₪</td>
      <td><strong>28.09 ₪</strong> (72.0%)</td>
      <td><strong>24.69 ₪</strong> (63.3%)</td>
    </tr>
    <tr>
      <td><strong>כרטיסיית חוקר</strong> (280 שאלות · ללא הגבלת זמן)</td>
      <td><strong>79 ₪</strong></td>
      <td>66.95 ₪</td>
      <td>5.80 ₪</td>
      <td>2.72 ₪</td>
      <td><strong>58.43 ₪</strong> (74.0%)</td>
      <td><strong>50.51 ₪</strong> (63.9%)</td>
    </tr>
    <tr>
      <td><strong>מנוי חודשי אישי</strong> (100 שאלות / חודש)</td>
      <td><strong>29 ₪</strong></td>
      <td>24.58 ₪</td>
      <td>3.30 ₪</td>
      <td>0.97 ₪</td>
      <td><strong>20.31 ₪</strong> (70.0%)</td>
      <td><strong>17.48 ₪</strong> (60.3%)</td>
    </tr>
    <tr>
      <td><strong>מנוי שנתי אישי</strong> (12 תשלומים חודשיים של 20 ₪)</td>
      <td><strong>240 ₪</strong></td>
      <td>203.39 ₪</td>
      <td>34.20 ₪ (12 עסקאות)</td>
      <td>~11.64 ₪</td>
      <td><strong>157.55 ₪</strong> (65.6%)</td>
      <td><strong>123.59 ₪</strong> (51.5%)</td>
    </tr>
    <tr>
      <td><strong>כולל / בימ"ד</strong> (1,500 שאלות)</td>
      <td><strong>460 ₪</strong> (390+מע"מ)</td>
      <td>390.00 ₪</td>
      <td>24.85 ₪</td>
      <td>14.55 ₪</td>
      <td><strong>350.60 ₪</strong> (76.2%)</td>
      <td><strong>308.15 ₪</strong> (67.0%)</td>
    </tr>
    <tr>
      <td><strong>ישיבה רגילה</strong> (3,500 שאלות)</td>
      <td><strong>932 ₪</strong> (790+מע"מ)</td>
      <td>790.00 ₪</td>
      <td>48.45 ₪</td>
      <td>33.95 ₪</td>
      <td><strong>707.60 ₪</strong> (75.9%)</td>
      <td><strong>608.55 ₪</strong> (65.3%)</td>
    </tr>
    <tr>
      <td><strong>ישיבה גדולה</strong> (7,000 שאלות)</td>
      <td><strong>1,994 ₪</strong> (1,690+מע"מ)</td>
      <td>1,690.00 ₪</td>
      <td>101.55 ₪</td>
      <td>67.90 ₪</td>
      <td><strong>1,520.55 ₪</strong> (76.3%)</td>
      <td><strong>1,322.45 ₪</strong> (66.3%)</td>
    </tr>
    <tr>
      <td><strong>חבילת הרחבה מוסדית</strong> (1,000 שאלות)</td>
      <td><strong>295 ₪</strong> (250+מע"מ)</td>
      <td>250.00 ₪</td>
      <td>16.60 ₪</td>
      <td>9.70 ₪</td>
      <td><strong>223.70 ₪</strong> (75.8%)</td>
      <td><strong>195.40 ₪</strong> (66.2%)</td>
    </tr>
  </tbody>
</table>

<div class="page-break"></div>

<!-- פרק 4 -->
<h2>4. משפך המרה, תקרת השרת וסדר עדיפויות חיתוך (Hierarchy)</h2>

<h3>א. תקרת 60K טוקנים וסדר עדיפויות חיתוך בבקשות שיעור</h3>
<div class="callout success">
  <strong>הפתרון הארכיטקטוני בשרת (<code>app/api.py</code>):</strong>
  כדי שהעלות לבקשה תישאר צפויה, מוגדרת בשרת <strong>תקרה קשיחה של 60K טוקנים</strong>, הרחק מתחת לסף המדרגה של Luna 6 (272K).
  בקשות ליצירת מערך שיעור שלם (`lesson`) צורכות כ-50K–55K טוקני קלט, כך שנותר מרווח ביטחון של 5K–10K טוקנים עד לתקרה.
  לפיכך מוגדר בקוד <strong>סדר עדיפויות חיתוך קשיח (Pruning Hierarchy)</strong>:
  <ol>
    <li><strong>חיתוך וסיכום היסטוריית השיחה (Dialogue History):</strong> תורי שיחה קודמים נחתכים או מסוכמים ראשונים.</li>
    <li><strong>הגנת מקורות קודש (Retrieved Sources Protection):</strong> ציטוטי המקורות, הפסוקים והמפרשים <strong>נשמרים תמיד במלואם ולעולם אינם נחתכים</strong>.</li>
  </ol>
  בפיילוט נבדוק בקשות שיעור ארוכות במיוחד כדי לוודא שהחיתוך אינו פוגע ברוחב המקורות.
</div>

<h3>ב. מבנה המשפך והחזר ה-CAC</h3>
<ul>
  <li>עלות 10 שאלות התנסות לנרשם חדש: <strong>~0.097 ₪</strong> (מבוקר) עד <strong>~0.38 ₪</strong> (קיצון).</li>
  <li>ביחס המרה שמרני של <strong>3%</strong>, נדרשים כ-33 נרשמים כדי לגייס לקוח משלם חדש.</li>
  <li><strong>עלות ההתנסות החינמית לכל לקוח משלם:</strong>
    33.3 × 0.097 ₪ = <strong>3.23 ₪</strong> (במצב מבוקר) ועד כ-12.70 ₪ (בתרחיש קיצון).
    <em>זו עלות המחשוב בלבד. עלות רכישת הלקוח המלאה (CAC) כוללת גם שיווק וזמן מכירה, והיא תימדד בפיילוט.</em>
  </li>
  <li><strong>תקופת החזר ה-CAC (Payback Period):</strong>
    <ul>
      <li><strong>כרטיסיית 19 ₪:</strong> מרווח נקי 11.40 ₪–12.81 ₪ — <strong>החזר מלא כבר בעסקה הקטנה ביותר</strong>.</li>
      <li><strong>מנוי חודשי (29 ₪):</strong> מרווח נקי 17.48 ₪–20.31 ₪ — <strong>החזר מיידי פי 5–6 בחודש הראשון</strong>.</li>
      <li><strong>מנוי שנתי (240 ₪, 20 ₪ לחודש):</strong> מרווח נקי 124 ₪–158 ₪ לשנה — <strong>החזר כבר בתשלום החודשי הראשון</strong>.</li>
    </ul>
  </li>
</ul>

<!-- פרק 5 -->
<h2>5. מודל B2B לישיבות: מאגר משותף מותאם היקף תלמידים</h2>
<p>
ישיבות פועלות כמלכ"ר ואינן מזדכות על מע"מ. המחירים מוצגים בבירור בשקיפות מלאה:
</p>
<ul>
  <li><strong>ללא הגבלת חשבונות ועמדות:</strong> כל בחור או אברך בישיבה יכול לגשת דרך עמדות בית המדרש או מחשבו האישי באמצעות קוד ארגוני (Org Slug) ללא תלות בכתובת IP. המערכת אושרה על ידי חברות הסינון ואינה נחסמת אצל משתמשי נטפרי/אתרוג.</li>
  <li><strong>התאמת גודל המאגר להיקף התלמידים:</strong>
    <ul>
      <li><strong>כולל / בית מדרש קטן (עד 40 לומדים):</strong> 1,500 שאלות חודשיות ב-<strong>390 ₪ + מע"מ (460 ₪ כולל מע"מ)</strong>. מרווח נקי: <strong>350.60 ₪</strong> (בסיס) / <strong>308.15 ₪</strong> (קיצון).</li>
      <li><strong>ישיבה בינונית (עד 120 לומדים):</strong> 3,500 שאלות חודשיות ב-<strong>790 ₪ + מע"מ (932 ₪ כולל מע"מ)</strong>. מרווח נקי: <strong>707.60 ₪</strong> (בסיס – כיסוי 94.3% מהוצאות החברה) / <strong>608.55 ₪</strong> (קיצון – כיסוי 81.1%).</li>
      <li><strong>ישיבה גדולה (מעל 120 לומדים):</strong> 7,000 שאלות חודשיות ב-<strong>1,690 ₪ + מע"מ (1,994 ₪ כולל מע"מ)</strong>. מרווח נקי: <strong>1,520.55 ₪</strong> (בסיס) / <strong>1,322.45 ₪</strong> (קיצון).</li>
    </ul>
  </li>
  <li><strong>חבילות הרחבה ללא השבתה:</strong> לקראת מבחן כללי או שבוע חזרות, המערכת אינה מושבתת בחסימה גסה, אלא מאפשרת לרכז הישיבה לרכוש חבילת הרחבה (1,000 שאלות ב-250 ₪ + מע"מ = 295 ₪ כולל מע"מ) בקליק אחד.</li>
</ul>

<!-- פרק 6 -->
<h2>6. תשתית Bare-Metal, בידוד זיכרון ומערך גיבוי (Litestream)</h2>
<ul>
  <li><strong>שרת ראשי ייעודי בלעדי (Hetzner Auction):</strong> שרת פיזי בלעדי AMD Ryzen 5/7 עם <strong>64 GB RAM פיזי</strong> ו-2 כונני NVMe RAID 1 (מתוקצב בביטחון של עד 300 ₪ לחודש). הסרת ה-Reranker חוסכת משאבי מעבד וזיכרון בשרת.</li>
  <li><strong>בידוד משאבים ומניעת OOM Killer ב-Docker:</strong>
    Qdrant מוגבל קשיחה ל-<strong>38 GB RAM</strong> (מחזיק את כל 2.5M הווקטורים ב-RAM ב-100%); אפליקציית FastAPI ו-Next.js מוגבלות ל-<strong>8 GB RAM</strong>; יתרת <strong>18 GB RAM</strong> נשמרת פנויה למערכת ההפעלה, ל-Disk Page Cache ולמודל bge-m3.</li>
  <li><strong>מערך גיבוי רציף (Litestream + SQLite WAL):</strong> כל רכישה ועדכון יתרת קרדיטים מוזרמים בתוך <strong>שנייה אחת</strong> לאחסון גיבוי חיצוני נפרד (Storage Box ב-15 ₪ / R2), לצד סנאפשוט יומי מוצפן ב-03:00.</li>
</ul>

<div class="page-break"></div>

<!-- פרק 7 -->
<h2>7. תחזית פיננסית מבוססת משפך ב-3 תרחישים</h2>
<p>
התחזית משקללת הוצאות שרת בטווח עליון (300 ₪), רואה חשבון (350 ₪), גיבוי ומסוף (100 ₪), סליקה מלאה, חידוש כרטיסיות 50%, ועלויות מחשוב במצב הייצור המבוקר (0.0097 ₪).
<strong>התרחיש השמרני</strong> נגזר מנתוני השימוש בפועל: כ-40 משתמשים פעילים בחודש היום, ובערך פי 2 אחרי תחילת שיווק בסיסי, ומתוכם קונים מעטים.
</p>

<table>
  <thead>
    <tr>
      <th>מדד פיננסי ותפעולי</th>
      <th>תרחיש שמרני (לפי נתוני אמת, 0 מוסדות)</th>
      <th>תרחיש מתון (0 מוסדות)</th>
      <th>תרחיש בסיס (2 מוסדות)</th>
      <th>תרחיש צמיחה (5 מוסדות)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>כרטיסיות נמכרות בחודש</strong> (חידוש 50%)</td>
      <td><strong>10 כרטיסיות</strong> (~330 ₪)</td>
      <td><strong>30 כרטיסיות</strong> (~1,000 ₪)<br>(15 חדשים / 15 חוזרים)</td>
      <td><strong>44 כרטיסיות</strong> (~1,400 ₪)<br>(22 חדשים / 22 חוזרים)</td>
      <td><strong>70 כרטיסיות</strong> (~2,250 ₪)<br>(35 חדשים / 35 חוזרים)</td>
    </tr>
    <tr>
      <td><strong>מנויים אישיים פעילים</strong> (שימור 85%)</td>
      <td><strong>8 מנויים</strong> (~232 ₪)</td>
      <td><strong>30 מנויים</strong> (~950 ₪)<br>(4 חדשים / 26 משומרים)</td>
      <td><strong>50 מנויים</strong> (~1,650 ₪)<br>(7 חדשים / 43 משומרים)</td>
      <td><strong>90 מנויים</strong> (~3,100 ₪)<br>(12 חדשים / 78 משומרים)</td>
    </tr>
    <tr>
      <td><strong>מוסדות B2B פעילים</strong> (כולל מע"מ)</td>
      <td>0 מוסדות (0 ₪)</td>
      <td>0 מוסדות (0 ₪)</td>
      <td>2 מוסדות (1,392 ₪)</td>
      <td>5 מוסדות (4,660 ₪)</td>
    </tr>
    <tr class="highlight-row">
      <td><strong>סה"כ הכנסות ברוטו שנגבו בחודש</strong></td>
      <td><strong>562 ₪</strong></td>
      <td><strong>1,950 ₪</strong></td>
      <td><strong>4,442 ₪</strong></td>
      <td><strong>10,010 ₪</strong></td>
    </tr>
    <tr>
      <td>מע"מ לתשלום (B2C + B2B)</td>
      <td>~86 ₪</td>
      <td>~297 ₪</td>
      <td>~677 ₪</td>
      <td>~1,525 ₪</td>
    </tr>
    <tr>
      <td>עמלות סליקה מלאות (0.50$ לעסקה + 5%)</td>
      <td>~61 ₪ (18 עסקאות)</td>
      <td>~209 ₪ (60 עסקאות)</td>
      <td>~400 ₪ (96 עסקאות)</td>
      <td>~806 ₪ (165 עסקאות)</td>
    </tr>
    <tr>
      <td>הוצאות קבועות מלאות (כולל שרת 300 ₪ ורו"ח)</td>
      <td>750 ₪</td>
      <td>750 ₪</td>
      <td>750 ₪</td>
      <td>750 ₪</td>
    </tr>
    <tr>
      <td>עלויות מחשוב LLM משלמים (מבוקר 60K)</td>
      <td>~18 ₪</td>
      <td>~44 ₪</td>
      <td>~112 ₪</td>
      <td>~233 ₪</td>
    </tr>
    <tr>
      <td>עלות סבסוד חינם (10 שאלות לנרשם)</td>
      <td>~6 ₪ (כ-60 נרשמים)</td>
      <td>~61 ₪ (כ-633 נרשמים)</td>
      <td>~94 ₪ (כ-967 נרשמים)</td>
      <td>~152 ₪ (כ-1,567 נרשמים)</td>
    </tr>
    <tr class="highlight-row" style="background:#f0fff4; font-weight:700; color:#22543d;">
      <td><strong>רווח תפעולי לפני מס (EBIT) – מבוקר</strong></td>
      <td><strong style="color:#c53030;">−359 ₪</strong></td>
      <td><strong>+589 ₪</strong></td>
      <td><strong>+2,409 ₪</strong></td>
      <td><strong>+6,544 ₪</strong></td>
    </tr>
    <tr style="color:#744210; background:#fffaf0; font-size:9.5px;">
      <td><em>רווח תפעולי בתרחיש קיצון (0.038 ₪)</em></td>
      <td><em>−427 ₪</em></td>
      <td><em>+283 ₪</em></td>
      <td><em>+1,808 ₪</em></td>
      <td><em>+5,421 ₪</em></td>
    </tr>
    <tr class="highlight-row" style="background:#ebf8ff; font-weight:700; color:#2a4365;">
      <td><strong>נטו לשותף אחרי מס, בחודש</strong> (35% מס הכנסה + 18% ביטוח לאומי ובריאות)</td>
      <td><strong>−233 ₪</strong> (אחרי קיזוז מול השכר)</td>
      <td><strong>+291 ₪</strong></td>
      <td><strong>+1,188 ₪</strong></td>
      <td><strong>+3,229 ₪</strong></td>
    </tr>
    <tr style="color:#2a4365; background:#ebf8ff;">
      <td>נטו לשותף אחרי מס, בשנה</td>
      <td>−2,800 ₪</td>
      <td>+3,487 ₪</td>
      <td>+14,262 ₪</td>
      <td>+38,742 ₪</td>
    </tr>
  </tbody>
</table>

<div class="callout">
  <strong>מס הכנסה וביטוח לאומי לשותף (הערכה, לא ייעוץ מס):</strong>
  <ul>
    <li><strong>מס הכנסה רק על הרווח</strong> (הכנסות פחות הוצאות מוכרות), גם בעוסק פטור. כל ההוצאות בטבלה מוכרות: שרת, רואה חשבון, גיבוי, מסוף, סליקה ומחשוב.</li>
    <li><strong>מדרגה שולית של 35%</strong>, כי הרווח מתווסף למשכורת שלו. ביטוח לאומי ומס בריאות כנראה <strong>18%</strong> על כל הרווח, כי המשכורת כבר ניצלה את המדרגה המופחתת. 52% מדמי הביטוח הלאומי מנוכים מההכנסה החייבת.</li>
    <li><strong>שיעור כולל אפקטיבי: כ-50.7%.</strong> מכל שקל רווח נשארות לשותף כ-49 אגורות.</li>
    <li><strong>הפסד:</strong> לפי סעיף 28(א) אפשר לקזז הפסד מהעסק מול המשכורת באותה שנה, ולכן הפסד של 359 ₪ בחודש עולה לו בפועל כ-233 ₪.</li>
    <li><strong>⚠️ סיכון לא פתור, הכנסה מזערית:</strong> ביטוח לאומי גובה מעצמאי לפי הכנסה מינימלית של 3,442 ₪ בחודש. לא ברור אם שכיר עם עסק צדדי פטור מזה. אם לא, נוספים <strong>כ-265 עד 620 ₪ בחודש</strong>, והתרחיש המתון עלול להפוך להפסד.</li>
  </ul>
  <strong>לבדוק עם רואה החשבון של השותף:</strong> (1) האם הכנסה מזערית חלה עליו; (2) האם הניכוי של 52% כולל מס בריאות; (3) תקרת עוסק פטור ל-2026 (כ-122,833 ₪); (4) קיזוז ההפסד מול השכר בפועל; (5) מע"מ על מחשוב מספק זר, ופטור מול מורשה מול מוסדות; (6) המדרגה השולית שלו בפועל.
</div>

<div class="callout">
  <strong>מה התרחיש השמרני אומר:</strong> בלי אף מוסד, ובקצב השימוש של היום, יש הפסד של כ-360 ₪ בחודש, בעיקר בגלל ההוצאות הקבועות.
  <strong>ישיבה בינונית אחת</strong> (707.60 ₪ נטו) הופכת אותו לרווח של כ-350 ₪ בחודש.
  לכן היעד הראשון של השותפות הוא <strong>מוסד משלם אחד</strong>, לא מאות מנויים.
  (תיקון מהמהדורה הקודמת: עמלת הסליקה הקבועה של 0.50$ חושבה עכשיו על כל עסקה, ולכן רווחי התרחישים ירדו מעט.)
</div>

<div class="callout success">
  <strong>נקודות האיזון המדויקות (Break-Even מבוקר):</strong>
  <ul>
    <li><strong>ישיבה בינונית (790 ₪ + מע"מ):</strong> מניבה <strong>707.60 ₪</strong> רווח נקי — ומכסה לבדה <strong>94.3%</strong> מסך כל ההוצאות הקבועות של החברה (750 ₪). חסרים 42.40 ₪ בלבד להגעה ל-100% (שווה ערך ל-2 כרטיסיות לומד או 2 מנויים). בתרחיש הקיצון היא מניבה 608.55 ₪ (כיסוי 81.1%).</li>
    <li><strong>כרטיסיות לומד (39 ₪):</strong> דרושות בדיוק <strong>27 כרטיסיות</strong> (750 ₪ ÷ 28.09 ₪) במצב מבוקר, או <strong>31 כרטיסיות</strong> בתרחיש קיצון.</li>
    <li><strong>מנויים חודשיים (29 ₪):</strong> דרושים בדיוק <strong>37 מנויים</strong> (750 ₪ ÷ 20.31 ₪) במצב מבוקר, או <strong>43 מנויים</strong> (750 ₪ ÷ 17.48 ₪) בתרחיש קיצון.</li>
  </ul>
</div>

<!-- פרק 8 -->
<h2>8. צעדי פעולה, ניהול סיכונים ואסטרטגיית צמיחה</h2>
<div class="callout">
  <strong>ניהול סיכונים מעשי ומינוף שולי הרווח:</strong>
  במרווחי תרומה של 60%–76% ועלות של פחות מ-4 אגורות לשאלה, <strong>עלויות המחשוב אינן מהוות עוד סיכון פיננסי</strong>.
  מוקדי הסיכון המרכזיים שבהם נדרש מיקוד הם:
  יחסי המרה וחידוש, תהליך המכירה לישיבות, אמון הלכתי וציטוט מהימן (ללא הזיות), עמידה בדיני הגנת הצרכן (הכרטיסיות ללא הגבלת זמן; ביטול עסקה תוך 14 יום), ויכולת תפעול אישית שוטפת.
  את שולי הרווח הגבוהים יש לשמר כעת במחירים הקיימים (אין להוריד מחירים). בהמשך, לאחר איסוף נתוני הפיילוט, נוכל לנצלם לצמיחה: למשל הרחבת חבילת ההיכרות ל-30 שאלות (עלות של כ-0.29 ₪ בלבד לנרשם) והגדלת מכסות חודשיות.
</div>

<ol>
  <li><strong>הטמעת תקרת 60K טוקנים וכללי חיתוך (<code>app/api.py</code>):</strong>
    מגבלה קשיחה של 60K ב-Prompt Context, תוך חיתוך היסטוריה ראשונה והגנה מוחלטת על טקסטי המקורות התורניים.
  </li>
  <li><strong>חיבור למודל המוזל ומדידת טוקנים בעברית:</strong>
    חיבור ה-API למודל Luna 6 (0.10$ / 0.50$), ומדידה מדויקת של יחס הטוקניזציה בעברית מתוך לוגי ה-Benchmark.
  </li>
  <li><strong>ביטול ה-Reranker:</strong>
    הסרת מודל הדירוג מהצינור והחזרת הקשר מקורות מלא (19.5k טוקנים) להבטחת דיוק תורני.
  </li>
  <li><strong>עדכון קטלוג התמחור בקוד (<code>app/plans.py</code>):</strong>
    הטמעת הכרטיסיות (19/39/79 ₪), מנוי אישי (29 ₪ חודשי / 240 ₪ שנתי), וחבילות מוסדיות ללא הגבלת חשבונות (390/790/1,690 ₪ + מע"מ).
  </li>
  <li><strong>פריסת תשתית Bare-Metal וחיבור B2B:</strong>
    הזמנת שרת Ryzen 64GB ב-Hetzner Auction (~150–300 ₪), פריסת Litestream לגיבוי רציף, ופנייה ל-2 ישיבות ראשונות.
  </li>
</ol>

<div class="footer-note">
  Chavruta.AI · תוכנית עסקית ומודל תמחור · כל הזכויות שמורות © 2026 יהודה רובין
</div>

</body>
</html>
"""

temp_html_path = r"C:\Users\rubin\AppData\Local\Temp\chavruta_business_plan_v15.html"
target_pdf_path = r"C:\Users\rubin\Downloads\תוכנית_עסקית_חדשה_חברותא_AI.pdf"

with open(temp_html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
cmd = [
    edge_path,
    "--headless=new",
    "--disable-gpu",
    "--no-pdf-header-footer",
    f"--print-to-pdf={target_pdf_path}",
    temp_html_path
]

print(f"Generating v15 PDF at: {target_pdf_path}")
res = subprocess.run(cmd, capture_output=True, text=True)

if os.path.exists(target_pdf_path):
    size_kb = os.path.getsize(target_pdf_path) / 1024
    print(f"SUCCESS: v15 PDF created at {target_pdf_path} (Size: {size_kb:.1f} KB)")
else:
    print(f"ERROR: PDF not created. Returncode: {res.returncode}")
