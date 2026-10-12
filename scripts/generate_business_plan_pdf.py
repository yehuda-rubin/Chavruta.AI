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
  <div class="badge">מסמך אסטרטגי פנימי מבוקר · גרסה v7</div>
  <h1>תוכנית עסקית ומודל תמחור – חברותא (Chavruta.AI)</h1>
  <div class="subtitle">מודל תמחור היברידי, ניתוח משפך מפוכח (חידוש 50%), שילוב מודל הדירוג והכרחיות הפיילוט המוזל (Large 3)</div>
  
  <div class="meta-grid">
    <div class="meta-item"><strong>פרויקט:</strong> Chavruta.AI</div>
    <div class="meta-item"><strong>יוצר ומייסד:</strong> יהודה רובין</div>
    <div class="meta-item"><strong>עלות שאלה (עם דירוג):</strong> ~0.124 ₪ (12.4 אג')</div>
    <div class="meta-item"><strong>הוצאות קבועות מלאות:</strong> 600 ₪ לחודש</div>
  </div>
</div>

<!-- פרק 1 -->
<h2>1. תמצית מנהלים והכרעות אסטרטגיות</h2>
<p>
מסמך זה מהווה תוכנית עסקית מפוכחת עבור <strong>חברותא (Chavruta.AI)</strong> — מערכת RAG תורנית מהימנה מעל 2.4 מיליון מקורות ארון הספרים היהודי.
התוכנית מציגה ניתוח חשבונאי עמוק ומיישמת שינויים מכריעים להבטחת כדאיות כלכלית:
</p>
<ul>
  <li><strong>מודל הדירוג (Reranker) והשפעתו:</strong> הוספת מודל דירוג מוקדם הפחיתה 3,000 טוקנים קלט לשאלה, הורידה את עלות השאלה ב-14% (ל-<strong>12.4 אגורות</strong>), ואת עלות ה-10 שאלות התנסות ל-<strong>1.24 ₪</strong>. יש לאמת ב-50 מבחני איכות שציטוט המקורות לא נפגע.</li>
  <li><strong>פיכחון במשפך הכרטיסיות (50% חידוש):</strong> הנחת שיעור חידוש ריאלי של כ-50% בכרטיסיות ל-90 יום (ולא 77% אופטימי). התחזית מכוילת ל-35 כרטיסיות חודשיות בשמרני.</li>
  <li><strong>הכרחיות המעבר למודל מוזל (פיילוט Large 3):</strong> הניתוח מוכיח שתחת DeepSeek הנוכחי, התרחיש השמרני גבולי מאוד (-180 ₪ עד +150 ₪). מעבר למודל מוזל (Large 3 / מודל קל ביחס מחשוב ÷3.2) הוא <strong>העוגן המרכזי</strong> שהופך את כל התרחישים לרווחיים באופן מובהק (+750 ₪ עד +6,500 ₪) ומאפשר סבסוד חינם בטוח.</li>
  <li><strong>מודל B2B לישיבות (מלכ"ר):</strong> מאגר מוסדי ללא הגבלת חשבונות, מוצג בשקיפות עם מע"מ (460 ₪ / 932 ₪ / 1,994 ₪ כולל מע"מ), ללא תלות ב-IP (אימות טוקן/סלאג).</li>
</ul>

<!-- פרק 2 -->
<h2>2. כלכלת היחידה המעודכנת (Unit Economics עם מודל הדירוג)</h2>
<p>
החישוב מתבסס על שילוב מודל הדירוג שהקטין את שאילתת הקלט ל-16.5k טוקנים ($1.75 קלט / $3.50 פלט / שער דולר 3.7 ₪):
</p>
<ul>
  <li><strong>שאלת לימוד רגילה (`qa`/`chavruta`):</strong> כ-16,500 קלט + 1,350 פלט + Reranker = <strong>~0.124 ₪ לשאלה</strong>.</li>
  <li><strong>מערך שיעור שלם (`lesson`):</strong> כ-50,000 קלט + 4,000 פלט = <strong>~0.37 ₪ לשיעור</strong>.</li>
  <li><strong>מפתח קרדיטים רשמי:</strong> <strong>שאלה רגילה = 1 קרדיט | שיעור שלם = 3 קרדיטים</strong>.</li>
  <li><strong>עלות נרשם חדש (10 שאלות התנסות):</strong> <strong>1.24 ₪ למשתמש חדש</strong> (ב-Large 3 ירד ל-~0.39 ₪).</li>
</ul>

<div class="grid-3">
  <div class="card">
    <div class="card-val">~0.124 ₪</div>
    <div class="card-lbl">עלות שאלת לימוד (DeepSeek)</div>
    <div class="card-desc">16.5k קלט + 1.35k פלט + Reranker = 0.0336$ (~0.124 ₪) לשאלה.</div>
  </div>
  <div class="card">
    <div class="card-val">1.24 ₪</div>
    <div class="card-lbl">עלות התנסות (10 שאלות)</div>
    <div class="card-desc">10 שאלות היכרות עמוקות. יורד ל-0.39 ₪ במודל Large 3.</div>
  </div>
  <div class="card">
    <div class="card-val">600 ₪</div>
    <div class="card-lbl">הוצאה קבועה חודשית מלאה</div>
    <div class="card-desc">שרת פיזי 64GB + גיבוי + רואה חשבון (350 ₪) + מסוף PayPlus (50 ₪).</div>
  </div>
</div>

<!-- פרק 3 -->
<h2>3. מודל התמחור ורווחיות נקייה ליחידה (כולל מע"מ וסליקה מלאה)</h2>
<p>
הטבלה להלן משקללת מע"מ (עוסק מורשה, 18%), עמלת סליקה מלאה (0.50$ + 5% על הברוטו), ועלות LLM מעודכנת לאחר מודל הדירוג:
</p>

<table>
  <thead>
    <tr>
      <th>מוצר / מסלול</th>
      <th>מחיר לצרכן (כולל מע"מ)</th>
      <th>מחיר נטו (ללא מע"מ)</th>
      <th>עמלת סליקה מלאה (0.50$ + 5%)</th>
      <th>עלות מחשוב מקסימלית</th>
      <th>מרווח תרומה נקי לעסקה</th>
      <th>שיעור רווח נקי מהברוטו</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>כרטיסיית כניסה</strong> (50 קרדיטים / 90 יום)</td>
      <td><strong>19 ₪</strong></td>
      <td>16.10 ₪</td>
      <td>2.80 ₪</td>
      <td>6.20 ₪ (50 שאלות)</td>
      <td><strong>7.10 ₪</strong></td>
      <td><strong>37.4%</strong></td>
    </tr>
    <tr>
      <td><strong>כרטיסיית לומד</strong> (120 קרדיטים / 90 יום)</td>
      <td><strong>39 ₪</strong></td>
      <td>33.05 ₪</td>
      <td>3.80 ₪</td>
      <td>14.88 ₪ (120 שאלות)</td>
      <td><strong>14.37 ₪</strong></td>
      <td><strong>36.8%</strong></td>
    </tr>
    <tr>
      <td><strong>כרטיסיית חוקר</strong> (280 קרדיטים / 90 יום)</td>
      <td><strong>79 ₪</strong></td>
      <td>66.95 ₪</td>
      <td>5.80 ₪</td>
      <td>34.72 ₪ (280 שאלות)</td>
      <td><strong>26.43 ₪</strong></td>
      <td><strong>33.5%</strong></td>
    </tr>
    <tr>
      <td><strong>מנוי חודשי אישי</strong> (100 שאלות / חודש)</td>
      <td><strong>29 ₪ / חודש</strong></td>
      <td>24.58 ₪</td>
      <td>3.30 ₪</td>
      <td>12.40 ₪ (במקסימום)</td>
      <td><strong>8.88 ₪</strong> (בממוצע: ~12.5 ₪)</td>
      <td><strong>30.6%</strong></td>
    </tr>
    <tr>
      <td><strong>מנוי שנתי אישי</strong> (משולם מראש Upfront)</td>
      <td><strong>240 ₪ / שנה</strong></td>
      <td>203.39 ₪</td>
      <td>13.85 ₪</td>
      <td>~120 ₪ (ממוצע שנתי)</td>
      <td><strong>69.54 ₪ לשנה</strong></td>
      <td><strong>29.0%</strong></td>
    </tr>
    <tr>
      <td><strong>כולל / בימ"ד</strong> (עד 1,500 שאלות)</td>
      <td><strong>460 ₪</strong> (390 ₪ + מע"מ)</td>
      <td>390.00 ₪</td>
      <td>24.85 ₪ (על הברוטו)</td>
      <td>186.00 ₪</td>
      <td><strong>179.15 ₪</strong></td>
      <td><strong>38.9%</strong></td>
    </tr>
    <tr>
      <td><strong>ישיבה רגילה</strong> (עד 3,500 שאלות)</td>
      <td><strong>932 ₪</strong> (790 ₪ + מע"מ)</td>
      <td>790.00 ₪</td>
      <td>48.45 ₪ (על הברוטו)</td>
      <td>434.00 ₪</td>
      <td><strong>307.55 ₪</strong></td>
      <td><strong>33.0%</strong></td>
    </tr>
    <tr>
      <td><strong>ישיבה גדולה</strong> (עד 7,000 שאלות)</td>
      <td><strong>1,994 ₪</strong> (1,690 ₪ + מע"מ)</td>
      <td>1,690.00 ₪</td>
      <td>101.55 ₪ (על הברוטו)</td>
      <td>868.00 ₪</td>
      <td><strong>720.45 ₪</strong></td>
      <td><strong>36.1%</strong></td>
    </tr>
    <tr>
      <td><strong>חבילת הרחבה מוסדית</strong> (1,000 שאלות)</td>
      <td><strong>295 ₪</strong> (250 ₪ + מע"מ)</td>
      <td>250.00 ₪</td>
      <td>16.60 ₪ (על הברוטו)</td>
      <td>124.00 ₪</td>
      <td><strong>109.40 ₪</strong></td>
      <td><strong>37.1%</strong></td>
    </tr>
  </tbody>
</table>

<div class="page-break"></div>

<!-- פרק 4 -->
<h2>4. ניתוח משפך מפוכח: החזר CAC, שיעור חידוש ותקציב התנעה</h2>
<div class="callout warning">
  <strong>ההכרה במציאות התפעולית:</strong> כרטיסיית 90 יום אינה מנוי קבוע. משתמש אינו מחדש אותה ב-77% הצלחה בכל רבעון. שיעור חידוש ריאלי עומד על <strong>כ-50%</strong>. מי שמתמיד בשיעור גבוה יותר מומר למנוי שנתי מוזל (240 ₪).
</div>

<h3>א. מבנה המשפך והחזר ה-CAC מול מרווח התרומה הנקי</h3>
<ul>
  <li>עלות 10 שאלות התנסות לנרשם חדש: <strong>1.24 ₪</strong> (ב-Large 3: <strong>0.39 ₪</strong>).</li>
  <li>ביחס המרה שמרני של <strong>3%</strong>, נדרשים כ-33 נרשמים כדי לייצר לקוח משלם חדש.</li>
  <li><strong>עלות רכישת לקוח (CAC של חינם בלבד):</strong> $33 \times 1.24\text{ ₪} = \mathbf{40.90\text{ ₪}}$ (ב-Large 3 יורד ל-<strong>12.90 ₪</strong> בלבד!).</li>
  <li><strong>תקופת החזר ה-CAC (Payback מול מרווח תרומה בלבד):</strong>
    <ul>
      <li><strong>מנוי שנתי (240 ₪):</strong> מרווח נקי 69.54 ₪ (מזומן 203 ₪) — <strong>החזר מלא ומיידי ביום הראשון</strong> (פי 1.7 מעלות ה-CAC).</li>
      <li><strong>כרטיסיית חוקר (79 ₪):</strong> מרווח 26.43 ₪ — החזר מלא בתוך 1.5 רכישות.</li>
      <li><strong>כרטיסיית לומד (39 ₪):</strong> מרווח 14.37 ₪ — החזר מלא בתוך 2.8 רכישות.</li>
      <li><strong>כרטיסיית כניסה (19 ₪):</strong> מרווח 7.10 ₪ — מיועדת להורדת חסם אמון ראשוני (Tripwire), ומובילה לשדרוג למנוי או חבילה גדולה.</li>
    </ul>
  </li>
</ul>

<h3>ב. מנגנון תקציב שיווק חינם: התנעה קבועה + תקציב דינמי מבוקר</h3>
<ol>
  <li><strong>חודש התנעה ראשון (Bootstrap Phase):</strong> תקציב ייעודי קבוע של <strong>300 ₪</strong> לחודש הראשון (מאפשר כ-240 נרשמים חדשים עוד בטרם כניסת תקבולים).</li>
  <li><strong>מחודש 2 ואילך (Dynamic Cap):</strong> תקציב סבסוד החינם החודשי מוגבל קשיחה ל-<strong>15%–20% מהכנסות החודש הקודם נטו</strong> (כ-350–500 ₪ בשמרני).</li>
  <li><strong>אבטחה:</strong> חסימת דומיינים של מיילים זמניים, זיהוי טביעת דפדפן, וחסימת הורדת קובצי Word למשתמשי חינם.</li>
</ol>

<!-- פרק 5 -->
<h2>5. מודל B2B לישיבות: מאגר משותף מותאם היקף תלמידים</h2>
<p>
ישיבות פועלות כמלכ"ר ואינן מזדכות על מע"מ. המחירים מוצגים בבירור בשקיפות מלאה:
</p>
<ul>
  <li><strong>ללא הגבלת חשבונות ועמדות:</strong> כל בחור או אברך בישיבה יכול לגשת דרך עמדות בית המדרש או מחשבו האישי באמצעות קוד ארגוני (Org Slug) ללא תלות בכתובת IP (עוקף לחלוטין את בעיית הסינון של נטפרי/אתרוג).</li>
  <li><strong>התאמת גודל המאגר להיקף התלמידים:</strong>
    <ul>
      <li><strong>כולל / בית מדרש קטן (עד 40 לומדים):</strong> 1,500 שאלות חודשיות ב-<strong>390 ₪ + מע"מ (460 ₪ כולל מע"מ)</strong>.</li>
      <li><strong>ישיבה בינונית (עד 120 לומדים):</strong> 3,500 שאלות חודשיות ב-<strong>790 ₪ + מע"מ (932 ₪ כולל מע"מ)</strong>. מרווח נקי לישיבה: <strong>307.55 ₪</strong>.</li>
      <li><strong>ישיבה גדולה (מעל 120 לומדים):</strong> 7,000 שאלות חודשיות ב-<strong>1,690 ₪ + מע"מ (1,994 ₪ כולל מע"מ)</strong>. מרווח נקי: <strong>720.45 ₪</strong>.</li>
    </ul>
  </li>
  <li><strong>חבילות הרחבה ללא השבתה:</strong> לקראת מבחן כללי או שבוע חזרות, המערכת אינה מושבתת בחסימה גסה, אלא מאפשרת לרכז הישיבה לרכוש חבילת הרחבה (1,000 שאלות ב-250 ₪ + מע"מ = 295 ₪ כולל מע"מ) בקליק אחד.</li>
</ul>

<!-- פרק 6 -->
<h2>6. תשתית Bare-Metal, בידוד זיכרון ומערך גיבוי (Litestream)</h2>
<ul>
  <li><strong>שרת ראשי ייעודי בלעדי (Hetzner Auction):</strong> AMD Ryzen 5/7 עם <strong>64 GB RAM פיזי</strong> ו-2 כונני NVMe RAID 1 ב-<strong>~150 ₪ לחודש</strong> (מחשב פיזי שלם שלך בלבד, ללא שום שכנים ושותפים). ניטור חומרה ודיסקים מוגדר באמצעות התרעות מיידיות.</li>
  <li><strong>בידוד משאבים ומניעת OOM Killer ב-Docker:</strong>
    Qdrant מוגבל קשיחה ל-<strong>38 GB RAM</strong> (מחזיק את כל 2.4M הווקטורים ב-RAM ב-100%); אפליקציית FastAPI ו-Next.js מוגבלות ל-<strong>8 GB RAM</strong>; יתרת <strong>18 GB RAM</strong> נשמרת פנויה למערכת ההפעלה, ל-Disk Page Cache ולמודל bge-m3.</li>
  <li><strong>מערך גיבוי רציף (Litestream + SQLite WAL):</strong> כל רכישה ועדכון יתרת קרדיטים מוזרמים בתוך <strong>שנייה אחת</strong> לאחסון גיבוי חיצוני נפרד (Storage Box ב-15 ₪ / R2), לצד סנאפשוט יומי מוצפן ב-03:00.</li>
</ul>

<div class="page-break"></div>

<!-- פרק 7 -->
<h2>7. תחזית פיננסית מפוכחת: השוואת DeepSeek מול Large 3</h2>
<p>
הטבלה להלן מציגה ניתוח מפוכח: חידוד הנחת חידוש הכרטיסיות ל-50% (35 כרטיסיות בשמרני: 15 חדשים + 20 חוזרים), ו<strong>השוואה ישירה בין מודל DeepSeek הנוכחי לבין מודל Large 3 המוזל</strong>:
</p>

<table>
  <thead>
    <tr>
      <th>מדד פיננסי ותפעולי</th>
      <th>תרחיש שמרני (0 מוסדות)</th>
      <th>תרחיש בסיס (2 מוסדות)</th>
      <th>תרחיש צמיחה (5 מוסדות)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>כרטיסיות נמכרות בחודש</strong> (חידוש 50%)</td>
      <td><strong>35 כרטיסיות</strong> (~1,150 ₪)<br>(15 חדשים / 20 חוזרים)</td>
      <td><strong>55 כרטיסיות</strong> (~1,750 ₪)<br>(22 חדשים / 33 חוזרים)</td>
      <td><strong>95 כרטיסיות</strong> (~3,000 ₪)<br>(35 חדשים / 60 חוזרים)</td>
    </tr>
    <tr>
      <td><strong>מנויים אישיים פעילים</strong> (שימור 85%)</td>
      <td><strong>30 מנויים</strong> (~950 ₪)</td>
      <td><strong>50 מנויים</strong> (~1,650 ₪)</td>
      <td><strong>90 מנויים</strong> (~3,100 ₪)</td>
    </tr>
    <tr>
      <td><strong>מוסדות B2B פעילים</strong> (כולל מע"מ)</td>
      <td>0 מוסדות (0 ₪)</td>
      <td>2 מוסדות (1,392 ₪)</td>
      <td>5 מוסדות (4,660 ₪)</td>
    </tr>
    <tr class="highlight-row">
      <td><strong>סה"כ הכנסות ברוטו שנגבו בחודש</strong></td>
      <td><strong>2,100 ₪</strong></td>
      <td><strong>4,792 ₪</strong></td>
      <td><strong>10,760 ₪</strong></td>
    </tr>
    <tr>
      <td>מע"מ לתשלום (B2C + B2B)</td>
      <td>~320 ₪</td>
      <td>~730 ₪</td>
      <td>~1,640 ₪</td>
    </tr>
    <tr>
      <td>עמלות סליקה מלאות (0.50$ + 5%)</td>
      <td>~185 ₪</td>
      <td>~415 ₪</td>
      <td>~820 ₪</td>
    </tr>
    <tr>
      <td>הוצאות קבועות מלאות (כולל רו"ח וסליקה)</td>
      <td>600 ₪</td>
      <td>600 ₪</td>
      <td>600 ₪</td>
    </tr>
    <tr>
      <td>עלויות מחשוב LLM משלמים (DeepSeek)</td>
      <td>~490 ₪</td>
      <td>~1,250 ₪</td>
      <td>~2,750 ₪</td>
    </tr>
    <tr>
      <td>עלות סבסוד חינם בתקרה דינמית (DeepSeek)</td>
      <td>~390 ₪ (כ-315 נרשמים)</td>
      <td>~520 ₪ (כ-420 נרשמים)</td>
      <td>~850 ₪ (כ-685 נרשמים)</td>
    </tr>
    <tr class="highlight-row">
      <td><strong>רווח תפעולי לפני מס תחת DeepSeek (EBIT)</strong></td>
      <td><strong>+115 ₪</strong> (גבולי)</td>
      <td><strong>+1,277 ₪</strong></td>
      <td><strong>+4,100 ₪</strong></td>
    </tr>
    <tr style="background:#f0fff4; font-weight:700; color:#22543d;">
      <td><strong>רווח תפעולי לפני מס תחת Large 3 (EBIT)</strong><br>(עלות מחשוב וסבסוד מחולקת ב-3.2)</td>
      <td><strong>+710 ₪</strong> (יציב ובטוח!)</td>
      <td><strong>+2,480 ₪</strong></td>
      <td><strong>+6,530 ₪</strong></td>
    </tr>
  </tbody>
</table>
<div class="callout success">
  <strong>המסקנה הכלכלית המרכזית:</strong> תחת DeepSeek הנוכחי המערכת מאוזנת אך חשופה לשינויי המרה בתרחיש השמרני. <strong>מעבר לפיילוט Large 3 מעביר את הרווחיות לפסים יציבים ובטוחים לחלוטין (+710 ₪ ומעלה בכל תרחיש)</strong> ומספק מרווח ביטחון מלא.
</div>

<!-- פרק 8 -->
<h2>8. צעדי פעולה ויישום מיידיים (Roadmap)</h2>
<ol>
  <li><strong>אימות איכות ה-Reranker (50 Benchmark Tests):</strong>
    הרצת סדרת בדיקות אימות על 50 שאילתות תורניות לבדיקה שחיתוך 3,000 הטוקנים לא פגע באיכות הציטוטים או הוריד מקורות מהותיים.
  </li>
  <li><strong>האצת פיילוט Large 3 (או מודל מוזל חלופי):</strong>
    בדיקת ביצועים ודיוק של מודל מוזל להורדת עלויות המחשוב פי 3.2, המבטיחה רווחיות מובהקת גם בתרחיש שמרני קיצוני.
  </li>
  <li><strong>עדכון קטלוג התמחור (<code>app/plans.py</code>):</strong>
    הטמעת הכרטיסיות (19/39/79 ₪), מנוי אישי (29 ₪ חודשי / 240 ₪ שנתי), וחבילות מוסדיות ללא הגבלת חשבונות (390/790/1,690 ₪ + מע"מ). הגדרת 10 שאלות התנסות וחסימת הורדת קובצי Word.
  </li>
  <li><strong>מעבר לשרת Bare-Metal (Hetzner Auction):</strong>
    הזמנת שרת Ryzen 64GB RAM ו-NVMe RAID 1. הגדרת מגבלות Docker (38GB ל-Qdrant, 8GB לאפליקציה).
  </li>
  <li><strong>השקה מוסדית B2B:</strong>
    פנייה ל-2 ישיבות עם מודל המאגר החופשי לכלל הבחורים במחיר של 790 ₪ + מע"מ (932 ₪ כולל מע"מ).
  </li>
</ol>

<div class="footer-note">
  Chavruta.AI · תוכנית עסקית ומודל תמחור · כל הזכויות שמורות © 2026 יהודה רובין
</div>

</body>
</html>
"""

temp_html_path = r"C:\Users\rubin\AppData\Local\Temp\chavruta_business_plan_v7.html"
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

print(f"Generating v7 PDF at: {target_pdf_path}")
res = subprocess.run(cmd, capture_output=True, text=True)

if os.path.exists(target_pdf_path):
    size_kb = os.path.getsize(target_pdf_path) / 1024
    print(f"SUCCESS: v7 PDF created at {target_pdf_path} (Size: {size_kb:.1f} KB)")
else:
    print(f"ERROR: PDF not created. Returncode: {res.returncode}")
