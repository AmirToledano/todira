# גיבוי של טודירה מחוץ ל־AWS

העותק הזה קיים למקרה שחשבון ה־AWS נסגר, נמחק או נפרץ. הגיבוי הלילי ל־S3 נמצא באותו חשבון AWS, ולכן הוא לא מספיק לבד.

## מה קורה כל לילה (אוטומטי)

- בערך ב־03:40 בלילה (02:40 בחורף) GitHub מוציא עותק מלא של מסד הנתונים מהשרת.
- העותק נדחס ומוצפן בסיסמה שרק אתה יודע (7‑Zip עם הצפנת AES‑256, גם שמות הקבצים מוצפנים).
- הוא עולה לתיקייה **Todira-backups** בגוגל דרייב שלך.
- נשמרים 30 הלילות האחרונים, והישנים יותר נמחקים מעצמם.
- בימי ראשון נשמר גם עותק מלא של הקוד (`todira-code-…bundle`).
- אם הגיבוי נכשל, הבוט שולח לך הודעה בטלגרם.
- ההרשאה לגוגל דרייב מוגבלת לקבצים שהגיבוי עצמו יצר. הוא לא רואה שום קובץ אחר שלך.

הקובץ הזה עולה לדרייב בכל לילה בשם `HOW-TO-RESTORE.md`, כך שההוראות תמיד נמצאות ליד הגיבויים.

## הגדרה חד־פעמית (בערך 10 דקות, רק אתה יכול לעשות אותה)

### א. בוחרים סיסמת הצפנה

- לפחות 12 תווים. משפט ארוך שקל לזכור עובד טוב.
- **שומרים אותה במנהל סיסמאות** (למשל מנהל הסיסמאות של גוגל). בלי הסיסמה אי אפשר לפתוח את הגיבויים, וגם אנחנו לא נוכל.

### ב. נותנים לגיבוי אישור לכתוב לגוגל דרייב

1. מורידים את rclone ל־Windows מ־https://rclone.org/downloads/ (Windows, Intel/AMD 64 Bit) ופורסים את ה־zip.
2. נכנסים לתיקייה שנפרסה. בשורת הכתובת של סייר הקבצים כותבים `cmd` ולוחצים Enter.
3. בחלון השחור מדביקים את השורה הבאה ולוחצים Enter:

```
rclone authorize "drive" "eyJzY29wZSI6ImRyaXZlLmZpbGUifQ"
```

4. נפתח דפדפן. בוחרים את חשבון הגוגל עם ה־5 טרה ומאשרים (Allow).
5. חוזרים לחלון השחור. בין `--->` ל־`<---` מופיעה שורה ארוכה שמתחילה ב־`{"access_token"`. מעתיקים אותה **כולה**, מ־`{` ועד `}`.

### ג. שני סודות ב־GitHub

נכנסים ל־https://github.com/AmirToledano/todira/settings/secrets/actions ולוחצים **New repository secret** פעמיים:

| Name | Secret |
|---|---|
| `GDRIVE_TOKEN` | השורה מ־`{` עד `}` משלב ב׳ |
| `BACKUP_PASSWORD` | הסיסמה משלב א׳ |

### ד. הרצה ראשונה

נכנסים ל־https://github.com/AmirToledano/todira/actions/workflows/offsite-backup-gdrive.yaml, לוחצים **Run workflow** ואז שוב **Run workflow**. אחרי כמה דקות התיקייה Todira-backups מופיעה בדרייב.

## העתקה לדיסק החיצוני בלחיצה אחת (לא חובה)

צריך את **Google Drive for desktop** מותקן ומחובר באותו חשבון גוגל: https://www.google.com/drive/download/

1. מעתיקים את הקובץ `scripts/backup/copy-to-external-drive.bat` מהפרויקט לתיקייה הראשית של הדיסק החיצוני.
2. בכל פעם שמחברים את הדיסק: לחיצה כפולה על הקובץ.
3. הקובץ מעתיק לדיסק רק את מה שחדש. בדיסק לא נמחק כלום, כך שנשמרת בו גם היסטוריה ישנה מ־30 יום.

הדיסק החיצוני מחזיק את כל מה שצריך כדי להקים הכל מחדש: גיבויי המסד, הקוד וההוראות האלה. בנוסף צריך רק את הסיסמה.

## שחזור (בשביל המפתח שיעשה את זה)

### פתיחת גיבוי

7‑Zip (https://www.7-zip.org) ← קליק ימני על `todira-db-YYYY-MM-DD.7z` ← Extract ← הסיסמה. מקבלים את `todira-db.sql.gz`.

### החזרת המסד לשרת

השרת מוקם כרגיל: k3s, ‏`KUBECONFIG_B64` חדש ב־GitHub, ופריסה דרך ה־CI. כל שאר הסודות כבר שמורים ב־GitHub. אחר כך:

```bash
kubectl scale deploy -n todira todira-website todira-bot --replicas=0
for cj in $(kubectl get cronjob -n todira -o name); do kubectl patch -n todira "$cj" -p '{"spec":{"suspend":true}}'; done
PG=$(kubectl get pods -n todira -l app=todira-postgres -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n todira "$PG" -- psql -U todira -d postgres -c 'DROP DATABASE IF EXISTS todira WITH (FORCE)' -c 'CREATE DATABASE todira OWNER todira'
gunzip -c todira-db.sql.gz | kubectl exec -i -n todira "$PG" -- psql -U todira -d todira -v ON_ERROR_STOP=1 -q
kubectl scale deploy -n todira todira-website todira-bot --replicas=1
for cj in $(kubectl get cronjob -n todira -o name); do kubectl patch -n todira "$cj" -p '{"spec":{"suspend":false}}'; done
```

### החזרת הקוד (רק אם גם GitHub איננו)

```bash
git clone todira-code-YYYY-MM-DD.bundle todira
```

## אם הגיבוי מפסיק לעבוד

- **מגיעה הודעה בטלגרם או מייל מ־GitHub על כישלון:** פותחים את הקישור ובודקים איזה שלב נכשל.
- **השלב "Check the two secrets" נכשל:** אחד הסודות חסר או הודבק לא שלם. חוזרים לשלבים ב׳ וג׳.
- **ההעלאה לדרייב נכשלת עם `invalid_grant`:** גוגל ביטלה את האישור, למשל אחרי שינוי סיסמה בגוגל. חוזרים על שלב ב׳ ומעדכנים את `GDRIVE_TOKEN`.
