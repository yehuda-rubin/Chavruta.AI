# צילומי מסך — Nebius Halacha Job (בלי Docker)

צילומי המסך מהריצה האמיתית (24/6/2026, H100 eu-north1). המדריך
[../NEBIUS_HALACHA_JOB.md](../NEBIUS_HALACHA_JOB.md) מטמיע אותם.

| קובץ | מה מצולם | שלב |
|------|---------|-----|
| `01a-gpu-availability.png`    | בחירת פלטפורמת GPU (chance of launch) | 1 |
| `01-create-job.png`          | ראש טופס היצירה (Image + Entrypoint) | 1 |
| `01b-create-job-resources.png`| משאבים: With GPU · Regular · Timeout | 1 |
| `01c-secret-token.png`       | `HF_TOKEN` כ-Secret env | 1 |
| `02-job-provisioning.png`    | הג'וב נוצר (Provisioning, H100) | 2 |
| `02a-embed-logs.png`         | לוגים: `[merge] ✅` + `bge-m3 on CUDA \| batch=256` | 2 |
| `02b-gpu-metrics.png`        | מטריקות GPU (Frame Buffer) | 2 |
| `02d-vm-metrics.png`         | מטריקות VM (CPU/RAM/Disk) | 2 |

## חסרים (אופציונלי להוסיף בעתיד)

| קובץ | מה לצלם | שלב |
|------|---------|-----|
| `00-raw-url.png`      | ה-URL הגולמי של הסקריפט בדפדפן | 0 |
| `02c-publish-ok.png` | שורת `[publish] ✅` בלוגים | 2 |
| `03-job-succeeded.png`| Job = SUCCEEDED + דף HF עם 3 קבצים | 3 |
| `04-local-loaded.png`| טרמינל מקומי: `✅ ready` + `points_count` | 4 |

> טיפ: **Win+Shift+S** רק מעתיק ל-clipboard. כדי לשמור קובץ — לחץ על ההתראה ואז Ctrl+S,
> או Paint → Ctrl+V → Ctrl+S, ושמור ישירות לכאן בשם מהטבלה.
