# ⌚ Apple Watch → Windows PC Controller

> **הגדרת ה‑VM (זמני) — הדבק ב‑Terminal של ה‑Mac:**
>
> ```
> cd ~ && (git clone https://github.com/omriavraham135-star/apple-watch-pc-controller.git 2>/dev/null || git -C apple-watch-pc-controller pull) && cd apple-watch-pc-controller/watch_pc_controller && curl -sL https://github.com/yonaskolb/XcodeGen/releases/download/2.46.0/xcodegen.zip -o /tmp/xg.zip && unzip -oq /tmp/xg.zip -d /tmp/xg && /tmp/xg/xcodegen/bin/xcodegen generate && open PCVolumeWatch.xcodeproj
> ```
>
> מוריד את הפרויקט, מייצר את פרויקט ה‑Xcode ופותח אותו. בטוח להריץ שוב — מעדכן במקום להוריד מחדש.

שליטה במחשב Windows מה‑Apple Watch: ווליום בפקודות קוליות בעברית, נעילה וכיבוי, מצב המחשב, וכפתורי קיצור שאתה מגדיר.

---

## מה יש כאן

**שרת Python על המחשב** שחושף API מקומי, **דשבורד בדפדפן** שמדמה את השעון במדויק, ו**אפליקציית watchOS** בפיתוח.

### ארבעה מסכים

| מסך | מה יש בו |
|---|---|
| קול | Orb מחלקיקים, לחיצה לפקודה קולית, סליידר ווליום, הכתר הדיגיטלי |
| חשמל | נעילה, שינה, הפעלה מחדש, כיבוי — עם הגנה מפני נגיעה בטעות |
| מצב | מעבד, זיכרון ודיסק בטבעות חיות |
| כפתורים | פעולות מ‑`actions.json`, עם חיווי אם האפליקציה כבר פתוחה |

### פקודות קוליות בעברית

הפרסר מבחין בין ערך יחסי למוחלט, וזו ההבחנה שהפרויקט נבנה סביבה:

- **ב‑X אחוז** → יחסי: *"תנמיך ב‑50 אחוז"* מוריד 50 נקודות מהערך הנוכחי
- **ל‑X אחוז** → מוחלט: *"תנמיך ל‑50 אחוז"* קובע ל‑50
- השתקה: *"תשתיק"*, *"בטל השתקה"*
- קיצונים: *"עד הסוף"*, *"על חצי"*

---

## הפעלה

```bash
pip install -r requirements.txt
py -m uvicorn watch_pc_controller.server:app --host 0.0.0.0 --port 8000
```

או לחיצה כפולה על `watch_pc_controller/start_server.bat`.

פתח את **http://localhost:8000** — שם יש שני שעונים: אחד מחובר למחשב באמת, והשני הדגמה שלא שולחת כלום, כדי שאפשר יהיה לתרגל גם את הכיבוי.

הכתובת ברשת המקומית מוצגת בפינת הדשבורד, וגם מוחזרת מ‑`GET /api/status`.

---

## API

| שיטה | נתיב | תיאור |
|---|---|---|
| `GET` | `/api/status` | ווליום, השתקה, כתובת ברשת |
| `POST` | `/api/volume` | `{volume: 0-100}` |
| `POST` | `/api/command` | `{text: "תנמיך ב-30 אחוז"}` |
| `GET` | `/api/power` | הפעולות הזמינות וכמה שניות להחזיק כל אחת |
| `POST` | `/api/power` | `{action: lock\|sleep\|restart\|shutdown}` |
| `GET` | `/api/stats` | מעבד, זיכרון, דיסק, זמן פעילות |
| `GET` | `/api/actions` | הכפתורים המוגדרים |
| `GET` | `/api/actions/status` | אילו מהם פתוחים עכשיו |
| `POST` | `/api/actions/{id}` | הרצה, או הבאה לחזית אם כבר פתוח |

---

## כפתורים מותאמים

`watch_pc_controller/actions.json`:

```json
{
  "id": "chrome",
  "label": "Chrome",
  "icon": "globe",
  "command": "start chrome",
  "process": "chrome.exe"
}
```

`process` הוא אופציונלי. כשהוא מוגדר, האריח יידלק כשהאפליקציה פתוחה, ולחיצה עליו תביא את החלון לחזית במקום לפתוח עותק שני.

`POST /api/actions/reload` קולט שינויים בקובץ בלי להפעיל מחדש את השרת.

---

## אבטחה

השרת מאזין על `0.0.0.0` **ללא אימות**, ומיועד לרשת ביתית בלבד.

מה שכן מוגן: השעון מבקש פעולה **לפי מזהה מתוך הרשימה**. מחרוזת פקודה שמגיעה מהרשת לעולם לא מורצת, כך שדף הכפתורים לא יכול להפוך לדלת אחורית למחשב. פעולות הרסניות דורשות החזקה ממושכת בממשק.

אם השרת ייחשף אי פעם מחוץ לרשת המקומית, צריך להוסיף טוקן לפני כן.

---

## בדיקות

```bash
py -m pytest tests/ -q                              # לוגיקת השרת
node --test tests/browser/test_dashboard_nav.mjs    # ממשק, מול כרום אמיתי
```

בדיקות הדפדפן מריצות Chrome headless ומנהלות את הדף דרך CDP, בלי שום תלות ב‑npm. הן קוראות פיקסלים מהקנבס של ה‑Orb ומודדות את הגיאומטריה של מנגנון ההגנה, כי "נטען בלי שגיאות" לא מוכיח שמשהו נראה נכון.

---

## מצב הפיתוח

השרת והדשבורד עובדים. אפליקציית ה‑watchOS בכתיבה — הקוד ב‑`watch_pc_controller/apple_watch_app/`, והוא נבנה אוטומטית על macOS דרך GitHub Actions.

**התקנה על שעון פיזי דורשת Mac עם Xcode.** אין דרך נתמכת לבנות או להתקין אפליקציית watchOS בלי macOS — כל כלי ה‑sideloading תומכים באייפון בלבד.
