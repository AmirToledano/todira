"""Website i18n. Small hand-rolled dict-based translator — no need for a full framework
(gettext/babel) at this site's size (9 templates, ~150 strings).

Supported languages: Hebrew (default, also the only language the Telegram bot itself understands
right now — see bot/handlers/onboarding.py's Gemini prompt), English, Russian, French, Arabic.
Hebrew and Arabic are RTL; English/Russian/French are LTR — RTL_LANGS below drives the `dir`
attribute on <html>, and the CSS already uses logical properties (margin-inline-start, etc.) so it
needed no direction-specific rules beyond the Arabic font fallback in style.css.

Translations were produced by this assistant, not reviewed by a native speaker of each language —
good enough for real-world use, but if a native speaker ever flags a phrasing as off, trust them
over this file.
"""
from __future__ import annotations

import datetime as dt

from starlette.requests import Request

SUPPORTED_LANGS = ["he", "en", "ru", "fr", "ar"]
DEFAULT_LANG = "he"
RTL_LANGS = {"he", "ar"}

LANG_LABELS = {
    "he": "עברית",
    "en": "English",
    "ru": "Русский",
    "fr": "Français",
    "ar": "العربية",
}

# key -> {lang: text}. Every key MUST have a "he" entry (the fallback used for any language
# missing a translation, and the source of truth since this product is Israel/Hebrew-first).
TRANSLATIONS: dict[str, dict[str, str]] = {
    # ---------- meta / <title> ----------
    "meta.title_home": {
        "he": "טודירה | חיפוש דירות בזמן אמת",
        "en": "Todira | real-time apartment search",
        "ru": "Todira | поиск квартир в реальном времени",
        "fr": "Todira | recherche d'appartements en temps réel",
        "ar": "توديرا | بحث عن شقق في الوقت الفعلي",
    },
    "meta.description": {
        "he": "בוט חיפוש דירות אישי שסורק את שוק הדירות ומתריע לך ברגע שמופיעה דירה שמתאימה בדיוק לסינון שלך.",
        "en": "A personal apartment-search bot that scans the market non-stop and alerts you the moment a listing matches your exact filter.",
        "ru": "Персональный бот для поиска квартир, который непрерывно сканирует рынок и уведомляет вас, как только появляется подходящее объявление.",
        "fr": "Un bot de recherche d'appartements personnel qui scanne le marché en continu et vous alerte dès qu'une annonce correspond exactement à vos critères.",
        "ar": "بوت بحث شقق شخصي يفحص السوق باستمرار وينبهك فور ظهور إعلان يطابق بالضبط الفلتر الخاص بك.",
    },
    "meta.title_apartments": {
        "he": "דירות תואמות | טודירה",
        "en": "Matching apartments | Todira",
        "ru": "Подходящие квартиры | Todira",
        "fr": "Appartements correspondants | Todira",
        "ar": "شقق مطابقة | توديرا",
    },
    "meta.title_liked": {
        "he": "דירות שמורות | טודירה",
        "en": "Saved apartments | Todira",
        "ru": "Сохранённые квартиры | Todira",
        "fr": "Appartements enregistrés | Todira",
        "ar": "شقق محفوظة | توديرا",
    },
    "meta.title_hidden": {
        "he": "דירות מוסתרות | טודירה",
        "en": "Hidden apartments | Todira",
        "ru": "Скрытые квартиры | Todira",
        "fr": "Appartements masqués | Todira",
        "ar": "شقق مخفية | توديرا",
    },
    "meta.title_filter": {
        "he": "הסינון שלי | טודירה",
        "en": "My filter | Todira",
        "ru": "Мой фильтр | Todira",
        "fr": "Mon filtre | Todira",
        "ar": "الفلتر الخاص بي | توديرا",
    },
    "meta.title_404": {
        "he": "הדף לא נמצא | טודירה",
        "en": "Page not found | Todira",
        "ru": "Страница не найдена | Todira",
        "fr": "Page introuvable | Todira",
        "ar": "الصفحة غير موجودة | توديرا",
    },
    "meta.title_generic": {
        "he": "טודירה",
        "en": "Todira",
        "ru": "Todira",
        "fr": "Todira",
        "ar": "توديرا",
    },
    "meta.title_about": {
        "he": "אודות | טודירה",
        "en": "About | Todira",
        "ru": "О нас | Todira",
        "fr": "À propos | Todira",
        "ar": "من نحن | توديرا",
    },
    "meta.title_terms": {
        "he": "תנאי שימוש | טודירה",
        "en": "Terms of Use | Todira",
        "ru": "Условия использования | Todira",
        "fr": "Conditions d'utilisation | Todira",
        "ar": "شروط الاستخدام | توديرا",
    },
    "meta.title_privacy": {
        "he": "מדיניות פרטיות | טודירה",
        "en": "Privacy Policy | Todira",
        "ru": "Политика конфиденциальности | Todira",
        "fr": "Politique de confidentialité | Todira",
        "ar": "سياسة الخصوصية | توديرا",
    },
    "meta.title_accessibility": {
        "he": "הצהרת נגישות | טודירה",
        "en": "Accessibility Statement | Todira",
        "ru": "Заявление о доступности | Todira",
        "fr": "Déclaration d'accessibilité | Todira",
        "ar": "بيان إمكانية الوصول | توديرا",
    },
    "meta.title_contact": {
        "he": "צור קשר | טודירה",
        "en": "Contact us | Todira",
        "ru": "Связаться с нами | Todira",
        "fr": "Nous contacter | Todira",
        "ar": "تواصل معنا | توديرا",
    },
    "meta.title_account": {
        "he": "החשבון שלי | טודירה",
        "en": "My Account | Todira",
        "ru": "Мой аккаунт | Todira",
        "fr": "Mon compte | Todira",
        "ar": "حسابي | توديرا",
    },
    "meta.title_login": {
        "he": "התחברות | טודירה", "en": "Login | Todira", "ru": "Вход | Todira",
        "fr": "Connexion | Todira", "ar": "تسجيل الدخول | توديرا",
    },
    "meta.title_google_pending": {
        "he": "כמעט שם | טודירה", "en": "Almost there | Todira", "ru": "Почти готово | Todira",
        "fr": "Presque terminé | Todira", "ar": "أوشكنا على الانتهاء | توديرا",
    },
    "meta.title_upgrade": {
        "he": "שדרוג המנוי | טודירה", "en": "Upgrade subscription | Todira",
        "ru": "Улучшение подписки | Todira", "fr": "Mise à niveau de l'abonnement | Todira",
        "ar": "ترقية الاشتراك | توديرا",
    },
    "meta.title_upgrade_pay": {
        "he": "תשלום | טודירה", "en": "Payment | Todira", "ru": "Оплата | Todira",
        "fr": "Paiement | Todira", "ar": "الدفع | توديرا",
    },
    "meta.title_upgrade_success": {
        "he": "תודה | טודירה", "en": "Thank you | Todira", "ru": "Спасибо | Todira",
        "fr": "Merci | Todira", "ar": "شكرًا | توديرا",
    },
    # ---------- header / nav ----------
    "nav.apartments": {
        "he": "דירות", "en": "Apartments", "ru": "Квартиры", "fr": "Appartements", "ar": "الشقق",
    },
    "nav.brand_home_hint": {
        "he": "(לעמוד הבית)", "en": "(home page)", "ru": "(на главную)",
        "fr": "(page d'accueil)", "ar": "(الصفحة الرئيسية)",
    },
    # 2026-10-17: banner for visitors inside a social app's built-in browser (main.py _in_app_browser).
    "inapp.text": {
        "he": "פתחת את טודירה מתוך {app}. בדפדפן הרגיל הכל עובד הכי טוב, ותישאר מחובר.",
        "en": "You opened Todira inside {app}. Everything works best in your regular browser, and you stay signed in.",
        "ru": "Вы открыли Todira внутри {app}. В обычном браузере всё работает лучше всего, и вы останетесь в системе.",
        "fr": "Vous avez ouvert Todira dans {app}. Tout fonctionne mieux dans votre navigateur habituel, et vous restez connecté.",
        "ar": "فتحت Todira داخل {app}. كل شيء يعمل بشكل أفضل في متصفحك العادي، وستبقى متصلاً.",
    },
    "inapp.button": {
        "he": "פתח בדפדפן", "en": "Open in browser", "ru": "Открыть в браузере",
        "fr": "Ouvrir dans le navigateur", "ar": "افتح في المتصفح",
    },
    "inapp.fallback_ios": {
        "he": "לא נפתח? לחץ על ••• למעלה ובחר לפתוח בדפדפן.",
        "en": "Didn't open? Tap ••• at the top and choose to open in your browser.",
        "ru": "Не открылось? Нажмите ••• вверху и выберите открыть в браузере.",
        "fr": "Rien ne s'ouvre? Touchez ••• en haut et choisissez d'ouvrir dans le navigateur.",
        "ar": "لم يُفتح؟ اضغط على ••• في الأعلى واختر الفتح في المتصفح.",
    },
    "inapp.fallback_android": {
        "he": "לא נפתח? לחץ על ⋮ למעלה ובחר לפתוח ב־Chrome.",
        "en": "Didn't open? Tap ⋮ at the top and choose to open in Chrome.",
        "ru": "Не открылось? Нажмите ⋮ вверху и выберите открыть в Chrome.",
        "fr": "Rien ne s'ouvre? Touchez ⋮ en haut et choisissez d'ouvrir dans Chrome.",
        "ar": "لم يُفتح؟ اضغط على ⋮ في الأعلى واختر الفتح في Chrome.",
    },
    "inapp.fallback_other": {
        "he": "לא נפתח? פתח את התפריט של האפליקציה ובחר לפתוח בדפדפן.",
        "en": "Didn't open? Open the app's menu and choose to open in your browser.",
        "ru": "Не открылось? Откройте меню приложения и выберите открыть в браузере.",
        "fr": "Rien ne s'ouvre? Ouvrez le menu de l'application et choisissez d'ouvrir dans le navigateur.",
        "ar": "لم يُفتح؟ افتح قائمة التطبيق واختر الفتح في المتصفح.",
    },
    # 2026-10-18: shown when the button could not leave the app's browser (Instagram on iPhone ignores it).
    "inapp.copied": {
        "he": "הקישור הועתק",
        "en": "Link copied",
        "ru": "Ссылка скопирована",
        "fr": "Lien copié",
        "ar": "تم نسخ الرابط",
    },
    "inapp.steps_ios": {
        "he": "לחץ על ••• למעלה ובחר לפתוח בדפדפן. או פתח את ספארי, לחיצה ארוכה על שורת הכתובת והדבק.",
        "en": "Tap ••• at the top and choose to open in your browser. Or open Safari, long-press the address bar and paste.",
        "ru": "Нажмите ••• вверху и выберите открыть в браузере. Или откройте Safari, удерживайте адресную строку и вставьте.",
        "fr": "Touchez ••• en haut et choisissez d'ouvrir dans le navigateur. Ou ouvrez Safari, appuyez longuement sur la "
        "barre d'adresse et collez.",
        "ar": "اضغط على ••• في الأعلى واختر الفتح في المتصفح. أو افتح Safari، اضغط مطولاً على شريط العنوان والصق.",
    },
    "inapp.steps_android": {
        "he": "לחץ על ⋮ למעלה ובחר לפתוח ב־Chrome. או פתח את Chrome והדבק בשורת הכתובת.",
        "en": "Tap ⋮ at the top and choose to open in Chrome. Or open Chrome and paste into the address bar.",
        "ru": "Нажмите ⋮ вверху и выберите открыть в Chrome. Или откройте Chrome и вставьте в адресную строку.",
        "fr": "Touchez ⋮ en haut et choisissez d'ouvrir dans Chrome. Ou ouvrez Chrome et collez dans la barre d'adresse.",
        "ar": "اضغط على ⋮ في الأعلى واختر الفتح في Chrome. أو افتح Chrome والصق في شريط العنوان.",
    },
    "inapp.steps_other": {
        "he": "פתח את התפריט של האפליקציה ובחר לפתוח בדפדפן, או הדבק את הקישור בדפדפן.",
        "en": "Open the app's menu and choose to open in your browser, or paste the link into your browser.",
        "ru": "Откройте меню приложения и выберите открыть в браузере, или вставьте ссылку в браузер.",
        "fr": "Ouvrez le menu de l'application et choisissez d'ouvrir dans le navigateur, ou collez le lien dans le navigateur.",
        "ar": "افتح قائمة التطبيق واختر الفتح في المتصفح، أو الصق الرابط في المتصفح.",
    },
    "inapp.copy_again": {
        "he": "העתק שוב", "en": "Copy again", "ru": "Скопировать снова", "fr": "Copier à nouveau", "ar": "انسخ مجدداً",
    },
    "trial_gift.text": {
        "he": "מתנה: הארכנו לך את תקופת הניסיון! יש לך גישה מלאה עד {date}.",
        "en": "A gift: we extended your free trial! You have full access until {date}.",
        "ru": "Подарок: мы продлили ваш пробный период! Полный доступ до {date}.",
        "fr": "Cadeau: nous avons prolongé votre essai! Accès complet jusqu'au {date}.",
        "ar": "هدية: مددنا فترتك التجريبية! لديك وصول كامل حتى {date}.",
    },
    "trial_gift.short": {
        "he": "תקופת הניסיון שלך: עד {date}",
        "en": "Your free trial: until {date}",
        "ru": "Ваш пробный период: до {date}",
        "fr": "Votre essai gratuit: jusqu'au {date}",
        "ar": "فترتك التجريبية: حتى {date}",
    },
    "inapp.close": {"he": "סגור", "en": "Close", "ru": "Закрыть", "fr": "Fermer", "ar": "إغلاق"},
    "nav.liked": {
        "he": "שמורות", "en": "Saved", "ru": "Сохранённые", "fr": "Enregistrés", "ar": "المحفوظة",
    },
    "nav.filter": {
        "he": "הסינון שלי", "en": "My filter", "ru": "Мой фильтр", "fr": "Mon filtre", "ar": "فلتري",
    },
    "nav.bot": {
        "he": "הבוט בטלגרם", "en": "The Telegram bot", "ru": "Бот в Telegram",
        "fr": "Le bot Telegram", "ar": "بوت تيليجرام",
    },
    "nav.contact": {
        "he": "צור קשר", "en": "Contact us", "ru": "Связаться с нами",
        "fr": "Nous contacter", "ar": "تواصل معنا",
    },
    "nav.account": {
        "he": "החשבון שלי", "en": "My account", "ru": "Мой аккаунт",
        "fr": "Mon compte", "ar": "حسابي",
    },
    "auth.you": {
        "he": "מחובר", "en": "Logged in", "ru": "Вы вошли", "fr": "Connecté(e)", "ar": "تم تسجيل الدخول",
    },
    "auth.logout": {
        "he": "התנתקות", "en": "Log out", "ru": "Выйти", "fr": "Se déconnecter", "ar": "تسجيل الخروج",
    },
    "auth.login": {
        "he": "הרשמה / התחברות", "en": "Sign up / Log in", "ru": "Регистрация / Вход",
        "fr": "Inscription / Connexion", "ar": "التسجيل / تسجيل الدخول",
    },
    "auth.link_google": {
        "he": "קשר את Google לחשבון", "en": "Link your Google account", "ru": "Привязать аккаунт Google",
        "fr": "Lier votre compte Google", "ar": "ربط حساب Google",
    },
    "auth.error_body": {
        "he": "משהו לא הסתדר בהתחברות. נסה שוב.",
        "en": "We couldn't verify the login. Please try again.",
        "ru": "Не удалось подтвердить вход. Попробуйте снова.",
        "fr": "Impossible de vérifier la connexion. Veuillez réessayer.",
        "ar": "تعذّر التحقق من تسجيل الدخول. يرجى المحاولة مرة أخرى.",
    },
    "auth.error_cta": {
        "he": "חזרה לדף הבית", "en": "Back to home", "ru": "На главную",
        "fr": "Retour à l'accueil", "ar": "العودة للصفحة الرئيسية",
    },
    "a11y.skip_to_content": {
        "he": "דלג לתוכן הראשי",
        "en": "Skip to main content",
        "ru": "Перейти к основному содержанию",
        "fr": "Aller au contenu principal",
        "ar": "تخطَّ إلى المحتوى الرئيسي",
    },
    "a11y.lang_switcher_label": {
        "he": "בחירת שפה", "en": "Choose language", "ru": "Выбор языка",
        "fr": "Choisir la langue", "ar": "اختيار اللغة",
    },
    "a11y.main_nav_label": {
        "he": "ניווט ראשי", "en": "Main navigation", "ru": "Основная навигация",
        "fr": "Navigation principale", "ar": "التنقل الرئيسي",
    },
    "a11y.theme_toggle_label": {
        "he": "החלף מצב כהה/בהיר", "en": "Toggle dark/light mode", "ru": "Переключить тёмный/светлый режим",
        "fr": "Basculer le mode sombre/clair", "ar": "تبديل الوضع الداكن/الفاتح",
    },
    # ---------- footer ----------
    "footer.built_by": {
        "he": "נבנה באהבה על ידי אמיר טולדנו",
        "en": "Built with love by Amir Toledano",
        "ru": "Создано с любовью Амиром Толедано",
        "fr": "Conçu avec amour par Amir Toledano",
        "ar": "بُني بحب من قبل أمير توليدانو",
    },
    "footer.gender_note": {
        "he": "הטקסט באתר כתוב בלשון זכר מטעמי נוחות בלבד, ופונה לכל המגדרים.",
        "en": "This site's text defaults to generic phrasing for simplicity and is meant for everyone, regardless of gender.",
        "ru": "Текст на сайте написан в общей форме для простоты и адресован всем, независимо от пола.",
        "fr": "Le texte de ce site est rédigé au masculin par souci de simplicité et s'adresse à toutes les personnes, quel que soit leur genre.",
        "ar": "نص هذا الموقع مكتوب بصيغة عامة لتسهيل القراءة، وهو موجّه للجميع بغض النظر عن الجنس.",
    },
    # {year} substituted by t()'s own .format(**kwargs) support (base.html passes
    # current_year, resolved fresh per request in main.py's _render) — was a hardcoded "© 2026"
    # that would've silently gone stale every January 1st.
    "footer.copyright": {
        "he": "© {year} טודירה. כל הזכויות שמורות.",
        "en": "© {year} Todira. All rights reserved.",
        "ru": "© {year} Todira. Все права защищены.",
        "fr": "© {year} Todira. Tous droits réservés.",
        "ar": "© {year} توديرا. جميع الحقوق محفوظة.",
    },
    # 2026-09-26: split into pre + a real mailto: link (see base.html) so the email address is
    # actually clickable — it used to sit as plain, unlinked text at the end of this sentence on
    # every page's footer (base.html renders this sitewide). Same no-`| safe`-anywhere,
    # split-around-the-markup convention this file already uses for privacy.s5_pre/_post etc.
    "footer.business_info_pre": {
        "he": "טודירה מופעל על ידי אמיר טולדנו, עוסק פטור מס׳ 211530563. ליצירת קשר: ",
        "en": "Todira is operated by Amir Toledano, exempt dealer (עוסק פטור) no. 211530563. Contact: ",
        "ru": "Todira управляется Амиром Толедано, освобождённый предприниматель (עוסק פטור) № 211530563. Контакт: ",
        "fr": "Todira est exploité par Amir Toledano, entrepreneur exonéré (עוסק פטור) n° 211530563. Contact: ",
        "ar": "توديرا يُدار من قبل أمير توليدانو، تاجر معفى رقم 211530563. للتواصل: ",
    },
    "footer.about": {
        "he": "אודות", "en": "About", "ru": "О нас", "fr": "À propos", "ar": "من نحن",
    },
    "footer.terms": {
        "he": "תנאי שימוש", "en": "Terms of Use", "ru": "Условия использования",
        "fr": "Conditions d'utilisation", "ar": "شروط الاستخدام",
    },
    "footer.privacy": {
        "he": "מדיניות פרטיות", "en": "Privacy Policy", "ru": "Политика конфиденциальности",
        "fr": "Politique de confidentialité", "ar": "سياسة الخصوصية",
    },
    "footer.accessibility": {
        "he": "הצהרת נגישות", "en": "Accessibility", "ru": "Доступность",
        "fr": "Accessibilité", "ar": "إمكانية الوصول",
    },
    # ---------- cookie notice banner (2026-09-25) ----------
    "cookies.notice_text": {
        "he": "האתר משתמש רק בשתי עוגיות: אחת זוכרת שהתחברת ואחת זוכרת את השפה. בלי פרסומות ובלי מעקב.",
        "en": "This site uses exactly two functional cookies (login and display language), no advertising or tracking cookies.",
        "ru": "Сайт использует только два функциональных файла cookie (вход и язык отображения), без рекламных или отслеживающих файлов cookie.",
        "fr": "Ce site utilise exactement deux cookies fonctionnels (connexion et langue d'affichage), aucun cookie publicitaire ou de suivi.",
        "ar": "يستخدم هذا الموقع ملفي تعريف ارتباط وظيفيين فقط (تسجيل الدخول ولغة العرض), بدون ملفات تعريف ارتباط إعلانية أو تعقب.",
    },
    "cookies.notice_link": {
        "he": "מדיניות פרטיות", "en": "Privacy policy", "ru": "Политика конфиденциальности",
        "fr": "Politique de confidentialité", "ar": "سياسة الخصوصية",
    },
    "cookies.notice_dismiss": {
        "he": "הבנתי", "en": "Got it", "ru": "Понятно", "fr": "Compris", "ar": "فهمت",
    },
    # ---------- accessibility widget (site-wide floating button + panel) ----------
    "a11y.widget_toggle_label": {
        "he": "כלי נגישות", "en": "Accessibility tools", "ru": "Инструменты доступности",
        "fr": "Outils d'accessibilité", "ar": "أدوات إمكانية الوصول",
    },
    "a11y.panel_title": {
        "he": "נגישות", "en": "Accessibility", "ru": "Доступность",
        "fr": "Accessibilité", "ar": "إمكانية الوصول",
    },
    "a11y.close": {
        "he": "סגור", "en": "Close", "ru": "Закрыть", "fr": "Fermer", "ar": "إغلاق",
    },
    "a11y.font_size": {
        "he": "גודל טקסט", "en": "Text size", "ru": "Размер текста",
        "fr": "Taille du texte", "ar": "حجم النص",
    },
    "a11y.font_decrease": {
        "he": "הקטן", "en": "Decrease", "ru": "Уменьшить", "fr": "Réduire", "ar": "تصغير",
    },
    "a11y.font_reset": {
        "he": "איפוס", "en": "Reset", "ru": "Сброс", "fr": "Réinitialiser", "ar": "إعادة تعيين",
    },
    "a11y.font_increase": {
        "he": "הגדל", "en": "Increase", "ru": "Увеличить", "fr": "Agrandir", "ar": "تكبير",
    },
    "a11y.contrast": {
        "he": "ניגודיות גבוהה", "en": "High contrast", "ru": "Высокая контрастность",
        "fr": "Contraste élevé", "ar": "تباين عالٍ",
    },
    "a11y.grayscale": {
        "he": "גווני אפור", "en": "Grayscale", "ru": "Оттенки серого",
        "fr": "Niveaux de gris", "ar": "تدرج الرمادي",
    },
    "a11y.underline_links": {
        "he": "הדגשת קישורים", "en": "Highlight links", "ru": "Выделить ссылки",
        "fr": "Souligner les liens", "ar": "تمييز الروابط",
    },
    "a11y.big_targets": {
        "he": "הגדלת כפתורים", "en": "Bigger buttons", "ru": "Крупные кнопки",
        "fr": "Boutons agrandis", "ar": "أزرار أكبر",
    },
    "a11y.reading_guide": {
        "he": "פס קריאה", "en": "Reading guide", "ru": "Линия чтения",
        "fr": "Guide de lecture", "ar": "دليل القراءة",
    },
    "a11y.no_motion": {
        "he": "עצירת אנימציות", "en": "Stop animations", "ru": "Остановить анимацию",
        "fr": "Arrêter les animations", "ar": "إيقاف الحركة",
    },
    "a11y.read_aloud": {
        "he": "הקראת העמוד", "en": "Read page aloud", "ru": "Озвучить страницу",
        "fr": "Lire la page à voix haute", "ar": "قراءة الصفحة بصوت عالٍ",
    },
    "a11y.stop_reading": {
        "he": "עצור הקראה", "en": "Stop reading", "ru": "Остановить озвучивание",
        "fr": "Arrêter la lecture", "ar": "إيقاف القراءة",
    },
    "a11y.reset_all": {
        "he": "איפוס כל ההגדרות", "en": "Reset all settings", "ru": "Сбросить все настройки",
        "fr": "Réinitialiser tous les réglages", "ar": "إعادة تعيين كل الإعدادات",
    },
    "a11y.statement_link": {
        "he": "הצהרת הנגישות שלנו", "en": "Our accessibility statement", "ru": "Наше заявление о доступности",
        "fr": "Notre déclaration d'accessibilité", "ar": "بيان إمكانية الوصول لدينا",
    },
    # 2026-09-06: matched against a competitor's (Takbull) own accessibility toolbar, screenshot by
    # the owner — these 9 fill the real gaps between what we had and what theirs offers.
    "a11y.line_height": {
        "he": "מרווח שורות", "en": "Line spacing", "ru": "Межстрочный интервал",
        "fr": "Interligne", "ar": "تباعد الأسطر",
    },
    "a11y.letter_spacing": {
        "he": "מרווח אותיות", "en": "Letter spacing", "ru": "Межбуквенный интервал",
        "fr": "Espacement des lettres", "ar": "تباعد الأحرف",
    },
    "a11y.readable_font": {
        "he": "גופן קריא", "en": "Readable font", "ru": "Читаемый шрифт",
        "fr": "Police lisible", "ar": "خط سهل القراءة",
    },
    "a11y.emphasize_headings": {
        "he": "הדגשת כותרות", "en": "Emphasize headings", "ru": "Выделить заголовки",
        "fr": "Souligner les titres", "ar": "تمييز العناوين",
    },
    "a11y.invert_colors": {
        "he": "היפוך צבעים", "en": "Invert colors", "ru": "Инвертировать цвета",
        "fr": "Inverser les couleurs", "ar": "عكس الألوان",
    },
    "a11y.big_cursor": {
        "he": "סמן גדול", "en": "Big cursor", "ru": "Крупный курсор",
        "fr": "Grand curseur", "ar": "مؤشر كبير",
    },
    "a11y.reading_mask": {
        "he": "מסכת קריאה", "en": "Reading mask", "ru": "Маска для чтения",
        "fr": "Masque de lecture", "ar": "قناع القراءة",
    },
    "a11y.justify_text": {
        "he": "יישור טקסט", "en": "Justify text", "ru": "Выровнять текст по ширине",
        "fr": "Justifier le texte", "ar": "محاذاة النص",
    },
    "a11y.keyboard_nav": {
        "he": "ניווט מקלדת", "en": "Keyboard navigation", "ru": "Навигация с клавиатуры",
        "fr": "Navigation au clavier", "ar": "التنقل بلوحة المفاتيح",
    },
    # ---------- home page ----------
    "home.eyebrow": {
        "he": "דירות בזמן אמת בטלגרם",
        "en": "Real-time apartments, on Telegram",
        "ru": "Квартиры в реальном времени, в Telegram",
        "fr": "Appartements en temps réel, sur Telegram",
        "ar": "شقق في الوقت الفعلي, على تيليجرام",
    },
    "home.h1": {
        "he": "הדירה שלך מוצאת אותך",
        "en": "Your apartment finds you",
        "ru": "Ваша квартира сама вас найдёт",
        "fr": "Votre appartement vous trouve",
        "ar": "شقتك تجدك",
    },
    "home.lead": {
        "he": "אנחנו מחפשים לך דירה, ושולחים לך לטלגרם רק את הדירות שבאמת מתאימות לך. בלי לרענן אתרים כל היום.",
        "en": "We look for an apartment for you, and send you on Telegram only the ones that really fit you. No refreshing websites all day.",
        "ru": "Мы ищем квартиру за вас и присылаем в Telegram только те, что действительно подходят. Больше не нужно весь день обновлять сайты.",
        "fr": "Nous cherchons un appartement pour vous, et vous envoyons sur Telegram uniquement ceux qui vous correspondent vraiment. Fini de rafraîchir les sites toute la journée.",
        "ar": "نبحث لك عن شقة، ونرسل لك على تيليجرام فقط الشقق التي تناسبك فعلًا. بلا تحديث للمواقع طوال اليوم.",
    },
    "home.cta_open_bot": {
        "he": "פתח את הבוט בטלגרם",
        "en": "Open the Telegram bot",
        "ru": "Открыть бота в Telegram",
        "fr": "Ouvrir le bot Telegram",
        "ar": "افتح البوت على تيليجرام",
    },
    "home.cta_how": {
        "he": "איך זה עובד?", "en": "How does it work?", "ru": "Как это работает?",
        "fr": "Comment ça marche?", "ar": "كيف يعمل؟",
    },
    "home.hero_img_alt": {
        "he": "טודי המלך, הכלב של טודירה",
        "en": "King Todi, the Todira apartment-search bot",
        "ru": "Король Тоди, бот поиска квартир Todira",
        "fr": "Le roi Todi, le bot de recherche d'appartements Todira",
        "ar": "الملك تودي, بوت البحث عن شقق توديرا",
    },
    "home.stat_scan_freq_value": {"he": "כל שעה", "en": "Every hour", "ru": "Каждый час", "fr": "Toutes les heures", "ar": "كل ساعة"},
    "home.stat_scan_freq_label": {
        "he": "תדירות סריקה", "en": "Scan frequency", "ru": "Частота сканирования",
        "fr": "Fréquence de scan", "ar": "تكرار الفحص",
    },
    # 2026-10-15 (owner): live numbers on the home page (main.py's _home_live_stats, Stats.jsx / CinematicStat.jsx).
    "home.live_new_24h_label": {
        "he": "מודעות חדשות ב־24 השעות האחרונות",
        "en": "New listings in the last 24 hours",
        "ru": "Новых объявлений за 24 часа",
        "fr": "Nouvelles annonces ces dernières 24 h",
        "ar": "إعلانات جديدة خلال آخر 24 ساعة",
    },
    "home.live_active_label": {
        "he": "מודעות פעילות עכשיו",
        "en": "Live listings right now",
        "ru": "Активных объявлений сейчас",
        "fr": "Annonces actives en ce moment",
        "ar": "إعلانات نشطة الآن",
    },
    "home.live_cities_label": {
        "he": "ערים ויישובים עם מודעות",
        "en": "Cities and towns with listings",
        "ru": "Городов и посёлков с объявлениями",
        "fr": "Villes et localités avec des annonces",
        "ar": "مدن وبلدات فيها إعلانات",
    },
    "home.live_last_scan_label": {
        "he": "בדיקה אחרונה",
        "en": "Last check",
        "ru": "Последняя проверка",
        "fr": "Dernière vérification",
        "ar": "آخر فحص",
    },
    "home.live_last_scan_value": {
        "he": "לפני {n} דק׳",
        "en": "{n} min ago",
        "ru": "{n} мин назад",
        "fr": "il y a {n} min",
        "ar": "قبل {n} دقيقة",
    },
    "home.live_last_scan_now": {
        "he": "ממש עכשיו",
        "en": "Just now",
        "ru": "Только что",
        "fr": "À l'instant",
        "ar": "الآن",
    },
    "home.live_scan_hours_label": {
        "he": "תדירות סריקה",
        "en": "Scan frequency",
        "ru": "Частота сканирования",
        "fr": "Fréquence de scan",
        "ar": "تكرار الفحص",
    },
    "home.live_cinematic_caption": {
        "he": "מודעות חדשות מצאנו ב־24 השעות האחרונות",
        "en": "new listings found in the last 24 hours",
        "ru": "новых объявлений найдено за последние 24 часа",
        "fr": "nouvelles annonces trouvées ces dernières 24 heures",
        "ar": "إعلانًا جديدًا وجدناها خلال آخر 24 ساعة",
    },
    "home.stat_ai_value": {"he": "AI", "en": "AI", "ru": "ИИ", "fr": "IA", "ar": "ذكاء اصطناعي"},
    "home.stat_ai_label": {
        "he": "מבין שפה חופשית",
        "en": "Understands free-form text",
        "ru": "Понимает свободный текст",
        "fr": "Comprend le langage libre",
        "ar": "يفهم النص الحر",
    },
    "home.stat_uptime_value": {"he": "24/7", "en": "24/7", "ru": "24/7", "fr": "24/7", "ar": "24/7"},
    "home.stat_uptime_label": {
        "he": "הבוט תמיד ער", "en": "The bot never sleeps", "ru": "Бот всегда на связи",
        "fr": "Le bot ne dort jamais", "ar": "البوت مستيقظ دائمًا",
    },
    "home.stat_free_value": {"he": "10 ימים", "en": "10 days", "ru": "10 дней", "fr": "10 jours", "ar": "10 أيام"},
    "home.stat_free_label": {
        "he": "תקופת ניסיון", "en": "Trial period", "ru": "Пробный период",
        "fr": "Période d'essai", "ar": "فترة تجريبية",
    },
    "home.momentum_1_value": {
        "he": "הכל במקום אחד", "en": "All in one place", "ru": "Всё в одном месте",
        "fr": "Tout au même endroit", "ar": "كل شيء في مكان واحد",
    },
    "home.momentum_1_label": {
        "he": "בלי לקפוץ בין אתרים ולוחות", "en": "No more jumping between sites and boards", "ru": "Не нужно прыгать между сайтами и досками объявлений",
        "fr": "Fini de passer d'un site à l'autre", "ar": "بلا تنقّل بين المواقع ولوحات الإعلانات",
    },
    "home.momentum_2_value": {
        "he": "ההתראה שלך", "en": "Your alert", "ru": "Ваше уведомление",
        "fr": "Votre alerte", "ar": "تنبيهك",
    },
    "home.momentum_2_label": {
        "he": "ישר לטלגרם, ברגע שיש התאמה", "en": "Straight to Telegram, the moment there's a match",
        "ru": "Прямо в Telegram, как только есть совпадение",
        "fr": "Directement sur Telegram, dès qu'il y a une correspondance",
        "ar": "مباشرة إلى تيليجرام، بمجرد وجود تطابق",
    },
    "home.momentum_3_value": {
        "he": "כל הארץ", "en": "Nationwide", "ru": "По всей стране",
        "fr": "Tout le pays", "ar": "في جميع أنحاء البلاد",
    },
    "home.momentum_3_label": {
        "he": "מאילת ועד קריית שמונה", "en": "From Eilat to Kiryat Shmona",
        "ru": "От Эйлата до Кирьят-Шмоны", "fr": "D'Eilat à Kiryat Shmona",
        "ar": "من إيلات حتى كريات شمونة",
    },
    "home.live_badge": {
        "he": "התראות בזמן אמת", "en": "Real-time alerts", "ru": "Уведомления в реальном времени",
        "fr": "Alertes en temps réel", "ar": "تنبيهات فورية",
    },
    "home.example_badge_label": {
        "he": "לדוגמה", "en": "Example", "ru": "Пример", "fr": "Exemple", "ar": "مثال",
    },
    "home.example_card_title": {
        "he": "דירה חדשה!", "en": "New listing!", "ru": "Новое объявление!",
        "fr": "Nouvelle annonce!", "ar": "شقة جديدة!",
    },
    # 2026-09-25: deliberately a DIFFERENT city/price/room-count than feature1's own demo example
    # (Tel Aviv, 2-3 rooms, ~6,000 ₪) below — this proof card and that demo used to show near-
    # identical numbers, reading as the same example copy-pasted three times on one page. Owner
    # feedback, live screenshot review.
    "home.example_card_sub": {
        "he": "רמת גן, 2 חדרים, 4,900 ₪",
        "en": "Ramat Gan, 2 rooms, ₪4,900",
        "ru": "Рамат-Ган, 2 комнаты, 4,900 ₪",
        "fr": "Ramat Gan, 2 pièces, 4 900 ₪",
        "ar": "رمات غان, غرفتان, 4,900 ₪",
    },
    "home.feature1_title": {
        "he": "תכתוב לו כמו לחבר",
        "en": "Write to it like a friend",
        "ru": "Пишите ему как другу",
        "fr": "Écrivez-lui comme à un ami",
        "ar": "اكتب له كما تكتب لصديق",
    },
    # 2026-09-25: no longer quotes the literal example ("2-3 rooms in Tel Aviv, up to 6,000 ILS")
    # inline — the demo box right below (feature1_example_city/rooms/price + the fixed query text
    # in Features.jsx) already shows that exact example concretely, so repeating it in prose too
    # just duplicated the same numbers twice back-to-back. The "in Hebrew" clarification stays —
    # that's a real functional instruction for non-Hebrew readers, not part of the redundant quote.
    "home.feature1_body": {
        "he": "תכתוב לבוט במילים שלך מה אתה מחפש. הוא מבין לבד ובונה לך את הסינון. בלי טפסים ובלי תפריטים.",
        "en": "Just write what you're looking for in Hebrew, like you'd describe it to a friend, and AI understands it and sets up the filter for you, no complicated forms.",
        "ru": "Просто напишите боту на иврите, что вы ищете, как будто рассказываете другу, и ИИ поймёт вас и настроит фильтр без сложных форм.",
        "fr": "Décrivez simplement au bot ce que vous cherchez en hébreu, comme vous le feriez auprès d'un ami, et l'IA comprend et configure le filtre pour vous, sans formulaires compliqués.",
        "ar": "فقط اكتب للبوت ما تبحث عنه بالعبرية، تمامًا كما لو كنت تصفه لصديق, ويفهم الذكاء الاصطناعي طلبك ويضبط الفلتر نيابة عنك، بدون نماذج معقدة.",
    },
    # 2026-09-10 addition: a concrete before/after visual under feature1, shown as an actual
    # mini-demo (typed query -> parsed chips) instead of only described in a sentence. Only the
    # parsed-chip labels below are real translation keys — the query text itself is a fixed Hebrew
    # example (a real visitor writes to the bot in Hebrew regardless of the UI language they're
    # browsing in, matching
    # feature1_body's own "in Hebrew" framing above), hardcoded directly in home.html rather than
    # given its own key here: an identical-Hebrew-in-every-language entry would trip
    # test_no_hebrew_characters_leak_into_arabic_translations, a guard that exists specifically to
    # catch real accidental leaks — better to not fight it than to special-case around it.
    "home.feature1_example_city": {
        "he": "תל אביב", "en": "Tel Aviv", "ru": "Тель-Авив", "fr": "Tel-Aviv", "ar": "تل أبيب",
    },
    "home.feature1_example_rooms": {
        "he": "2-3 חדרים", "en": "2-3 rooms", "ru": "2-3 комнаты", "fr": "2-3 pièces", "ar": "2-3 غرف",
    },
    "home.feature1_example_price": {
        "he": "עד 6,000 ₪", "en": "Up to ₪6,000", "ru": "До 6 000 ₪", "fr": "Jusqu'à 6 000 ₪",
        "ar": "حتى 6,000 ₪",
    },
    # 2026-09-26: the query→chips demo used to just show the same 3 facts twice back-to-back with a
    # bare "↓" between them — a real visitor screenshot flagged this as reading like an accidental
    # duplication, not a parsing demo. This label (shown between the highlighted query and the
    # chips, see Features.jsx) plus highlighting the matching phrases directly inside the query
    # bubble now makes the "AI extracted these 3 things from your sentence" point explicit instead
    # of implied by a lone arrow.
    "home.feature1_understood_label": {
        "he": "הבוט הבין:", "en": "The bot understood:", "ru": "Бот понял:",
        "fr": "Le bot a compris:", "ar": "فهم البوت:",
    },
    "home.feature2_title": {
        "he": "התראות בזמן אמת", "en": "Real-time alerts", "ru": "Уведомления в реальном времени",
        "fr": "Alertes en temps réel", "ar": "تنبيهات فورية",
    },
    "home.feature2_body": {
        "he": "הבוט מחפש בשבילך שוב ושוב לאורך היום. עלתה דירה שמתאימה לך? ברגע שהוא מוצא אותה, היא אצלך בטלגרם. אתה לא צריך לרענן כלום.",
        "en": "The bot searches for you again and again throughout the day. A new apartment that fits you? The moment it finds it, it's on your Telegram. You don't need to refresh anything.",
        "ru": "Бот снова и снова ищет за вас в течение дня. Появилась подходящая квартира? Как только бот её найдёт, она у вас в Telegram. Ничего не нужно обновлять.",
        "fr": "Le bot cherche pour vous, encore et encore, tout au long de la journée. Un appartement qui vous correspond? Dès qu'il le trouve, il arrive sur votre Telegram. Vous n'avez rien à rafraîchir.",
        "ar": "يبحث البوت من أجلك مرة بعد مرة طوال اليوم. نُشرت شقة تناسبك؟ لحظة أن يجدها تصلك على تيليجرام. لا حاجة لتحديث أي شيء.",
    },
    "home.feature3_title": {
        "he": "שומר לך את הדירות שאהבת",
        "en": "Keeps the apartments you liked",
        "ru": "Сохраняет квартиры, которые вам понравились",
        "fr": "Enregistre les appartements que vous avez aimés",
        "ar": "يحفظ الشقق التي أعجبتك",
    },
    "home.feature3_body": {
        "he": "תסמן דירות שמעניינות אותך ותחזור אליהן מתי שבא לך, פה באתר או בבוט.",
        "en": "Mark apartments you're interested in and come back to them easily at any point, here on the site or straight from the bot.",
        "ru": "Отмечайте интересные квартиры и легко возвращайтесь к ним в любой момент, здесь на сайте или прямо в боте.",
        "fr": "Marquez les appartements qui vous intéressent et retrouvez-les facilement à tout moment, ici sur le site ou directement depuis le bot.",
        "ar": "علّم الشقق التي تهمك وارجع إليها بسهولة في أي وقت, هنا على الموقع أو مباشرة من داخل البوت.",
    },
    "home.compare_title": {
        "he": "למה לא פשוט לגלול לבד?",
        "en": "Why not just scroll on your own?",
        "ru": "Почему бы просто не искать самому?",
        "fr": "Pourquoi ne pas simplement chercher soi-même?",
        "ar": "لماذا لا تكتفي بالتصفح بنفسك؟",
    },
    "home.compare_sub": {
        "he": "כי דירה טובה נחטפת תוך כמה שעות, ואין לך זמן לשבת על זה כל היום.",
        "en": "Because you're busy, and good apartments disappear within hours.",
        "ru": "Потому что вы заняты, а хорошие квартиры исчезают за считанные часы.",
        "fr": "Parce que vous êtes occupé, et les bons appartements disparaissent en quelques heures.",
        "ar": "لأنك مشغول، والشقق الجيدة تختفي خلال ساعات.",
    },
    "home.compare_without_title": {
        "he": "בלי טודירה", "en": "Without Todira", "ru": "Без Todira",
        "fr": "Sans Todira", "ar": "بدون توديرا",
    },
    "home.compare_without_1": {
        "he": "אתה מרענן כמה אתרים כל כמה שעות",
        "en": "Refreshing several sites every few hours",
        "ru": "Обновляете несколько сайтов каждые несколько часов",
        "fr": "Rafraîchir plusieurs sites toutes les quelques heures",
        "ar": "تحديث عدة مواقع كل بضع ساعات",
    },
    "home.compare_without_2": {
        "he": "מפספס דירות טובות שנחטפות עוד לפני שראית אותן",
        "en": "Missing good apartments that get taken before you even see them",
        "ru": "Упускаете хорошие квартиры, которые сдают ещё до того, как вы их увидели",
        "fr": "Rater de bons appartements pris avant même que vous les voyiez",
        "ar": "تفويت شقق جيدة تُحجز قبل أن تراها أصلًا",
    },
    "home.compare_without_3": {
        "he": "עובר ידנית על עשרות מודעות שלא קשורות אליך",
        "en": "Manually sifting through dozens of irrelevant listings",
        "ru": "Вручную просматриваете десятки нерелевантных объявлений",
        "fr": "Parcourir manuellement des dizaines d'annonces non pertinentes",
        "ar": "تصفح عشرات الإعلانات غير ذات الصلة يدويًا",
    },
    "home.compare_without_4": {
        "he": "שוכח דירה ששמרת בלשונית שנסגרה",
        "en": "Forgetting an apartment you saved in a tab you closed",
        "ru": "Забываете квартиру, сохранённую во вкладке, которую закрыли",
        "fr": "Oublier un appartement enregistré dans un onglet fermé",
        "ar": "نسيان شقة حفظتها في تبويب أغلقته",
    },
    "home.compare_with_title": {
        "he": "עם טודירה", "en": "With Todira", "ru": "С Todira",
        "fr": "Avec Todira", "ar": "مع توديرا",
    },
    # 2026-09-10 fix: said "every 10 minutes" — stale copy from before the 2026-09-03 schedule
    # change (charts/todira/values.yaml's scraper.schedule is actually every 2 hours, 8:00-22:00
    # Israel time) and directly contradicted home.stat_scan_freq_value below it on the same page,
    # which already said the correct "כל שעתיים"/"Every 2h". Found by cross-checking the page's
    # own claims against each other, then against the real CronJob schedule.
    "home.compare_with_1": {
        "he": "הבוט סורק בשבילך כל שעה, ברקע",
        "en": "Automatic scanning every hour, in the background",
        "ru": "Автоматическое сканирование каждый час в фоне",
        "fr": "Scan automatique toutes les heures, en arrière-plan",
        "ar": "فحص تلقائي كل ساعة في الخلفية",
    },
    "home.compare_with_2": {
        "he": "הודעה בטלגרם ברגע שיש דירה שמתאימה לך",
        "en": "Instant Telegram alert the moment there's a match",
        "ru": "Мгновенное уведомление в Telegram при совпадении",
        "fr": "Alerte Telegram instantanée dès qu'il y a une correspondance",
        "ar": "تنبيه فوري على تيليجرام فور وجود تطابق",
    },
    "home.compare_with_3": {
        "he": "רואה רק דירות שבאמת מתאימות לסינון שלך",
        "en": "You only see apartments that truly meet your filter",
        "ru": "Вы видите только квартиры, действительно соответствующие фильтру",
        "fr": "Vous ne voyez que les appartements qui correspondent vraiment à votre filtre",
        "ar": "لا ترى إلا الشقق التي تطابق فعلًا فلترك",
    },
    "home.compare_with_4": {
        "he": "כל דירה ששמרת מחכה לך פה וגם בבוט",
        "en": "Every apartment you saved is waiting for you here and in the bot",
        "ru": "Каждая сохранённая квартира ждёт вас здесь и в боте",
        "fr": "Chaque appartement enregistré vous attend ici et dans le bot",
        "ar": "كل شقة حفظتها تنتظرك هنا وفي البوت أيضًا",
    },
    "home.how_title": {
        "he": "איך זה עובד", "en": "How it works", "ru": "Как это работает",
        "fr": "Comment ça marche", "ar": "كيف يعمل",
    },
    "home.how_sub": {
        "he": "שתי דקות להתחיל, ומשם טודירה עובד בשבילך.",
        "en": "Two minutes to start, and from there Todira works for you.",
        "ru": "Две минуты на старт, а дальше Todira работает за вас.",
        "fr": "Deux minutes pour démarrer, ensuite Todira travaille pour vous.",
        "ar": "دقيقتان للبدء، ومن هناك توديرا يعمل من أجلك.",
    },
    "home.step1_title": {
        "he": "מדבר עם הבוט", "en": "Talk to the bot", "ru": "Общайтесь с ботом",
        "fr": "Discutez avec le bot", "ar": "تحدث مع البوت",
    },
    "home.step1_body": {
        "he": "פותח שיחה בטלגרם ומספר במילים שלך איזו דירה אתה מחפש.",
        "en": "Open a chat on Telegram and describe, in Hebrew and in your own words, the apartment you're looking for.",
        "ru": "Откройте чат в Telegram и опишите на иврите своими словами квартиру, которую вы ищете.",
        "fr": "Ouvrez une conversation sur Telegram et décrivez, en hébreu et avec vos propres mots, l'appartement que vous cherchez.",
        "ar": "افتح محادثة على تيليجرام وصف بالعبرية وبكلماتك الشقة التي تبحث عنها.",
    },
    "home.step2_title": {
        "he": "הסינון נבנה לבד", "en": "The filter builds itself", "ru": "Фильтр строится автоматически",
        "fr": "Le filtre se construit automatiquement", "ar": "يُبنى الفلتر تلقائيًا",
    },
    "home.step2_body": {
        "he": "עיר, מחיר, חדרים ועוד. הבוט מוציא הכל מהשיחה ושומר לך את החיפוש.",
        "en": "City, price range, number of rooms and more, it's all extracted from your conversation and saved as a search profile.",
        "ru": "Город, диапазон цен, количество комнат и многое другое, всё извлекается из вашего разговора и сохраняется как профиль поиска.",
        "fr": "Ville, fourchette de prix, nombre de pièces et plus, tout est extrait de votre conversation et enregistré comme profil de recherche.",
        "ar": "المدينة ونطاق السعر وعدد الغرف وأكثر, كل ذلك يُستخرج من محادثتك ويُحفظ كملف بحث.",
    },
    "home.step3_title": {
        "he": "מקבל התראות", "en": "Get alerts", "ru": "Получайте уведомления",
        "fr": "Recevez des alertes", "ar": "احصل على تنبيهات",
    },
    "home.step3_body": {
        "he": "מעכשיו, כל דירה חדשה שמתאימה לך מגיעה אליך ישר, וגם מופיעה פה באתר.",
        "en": "From this moment on, every new matching apartment is sent straight to you, and also shows up here on the site.",
        "ru": "С этого момента каждая новая подходящая квартира отправляется прямо вам, а также появляется здесь на сайте.",
        "fr": "Dès cet instant, chaque nouvel appartement correspondant vous est envoyé directement, et apparaît aussi ici sur le site.",
        "ar": "من هذه اللحظة، تُرسل إليك مباشرة كل شقة جديدة مطابقة, وتظهر أيضًا هنا على الموقع.",
    },
    "home.faq_title": {
        "he": "שאלות נפוצות", "en": "Frequently asked questions", "ru": "Часто задаваемые вопросы",
        "fr": "Questions fréquentes", "ar": "الأسئلة الشائعة",
    },
    "home.faq1_q": {
        "he": "איך הבוט מבין מה אני מחפש?",
        "en": "How does the bot understand what I'm looking for?",
        "ru": "Как бот понимает, что я ищу?",
        "fr": "Comment le bot comprend-il ce que je cherche?",
        "ar": "كيف يفهم البوت ما أبحث عنه؟",
    },
    "home.faq1_a": {
        "he": "אתה כותב לו בשפה חופשית, כמו שהיית מספר לחבר. הבוט מוציא מהמשפט עיר, מחיר, חדרים ועוד, ובונה מזה חיפוש. בלי טפסים ובלי תפריטים.",
        "en": "You write to the bot in plain Hebrew, just like you'd describe it to a friend. A language model picks out the city, price range, number of rooms and more from your sentence, and builds a search profile from it, no forms, no complicated menus.",
        "ru": "Вы пишете боту на иврите свободным текстом, как будто рассказываете другу. Языковая модель распознаёт город, диапазон цен, количество комнат и другие детали из вашего сообщения и строит на их основе профиль поиска, без форм и сложных меню.",
        "fr": "Vous écrivez au bot en hébreu, en langage libre, exactement comme vous le décririez à un ami. Un modèle de langage identifie dans votre phrase la ville, la fourchette de prix, le nombre de pièces et d'autres détails, puis construit un profil de recherche, sans formulaires ni menus compliqués.",
        "ar": "تكتب للبوت بالعبرية بلغة حرة، تمامًا كما لو كنت تصف الأمر لصديق. يحدد نموذج اللغة من جملتك المدينة ونطاق السعر وعدد الغرف وتفاصيل أخرى، ويبني منها ملف بحث, بدون نماذج أو قوائم معقدة.",
    },
    "home.faq2_q": {
        "he": "כל כמה זמן הבוט בודק?", "en": "How often does the bot check?",
        "ru": "Как часто бот проверяет?", "fr": "À quelle fréquence le bot vérifie-t-il?",
        "ar": "كم مرة يفحص البوت؟",
    },
    "home.faq2_a": {
        "he": "שוב ושוב לאורך כל היום. כל מודעה חדשה נבדקת מול הסינון שלך, ומה שמתאים מגיע אליך לטלגרם וגם מחכה לך פה באתר.",
        "en": "Again and again throughout the day. Every new listing is checked against your filter, and whatever fits reaches you on Telegram and also waits for you here on the site.",
        "ru": "Снова и снова в течение всего дня. Каждое новое объявление сравнивается с вашим фильтром, и всё подходящее приходит вам в Telegram и ждёт вас здесь на сайте.",
        "fr": "Encore et encore, tout au long de la journée. Chaque nouvelle annonce est comparée à votre filtre, et ce qui correspond arrive sur votre Telegram et vous attend aussi ici sur le site.",
        "ar": "مرة بعد مرة طوال اليوم. كل إعلان جديد يُقارن بفلترك، وما يناسبك يصلك على تيليجرام وينتظرك أيضًا هنا في الموقع.",
    },
    "home.faq3_q": {
        "he": "כמה זה עולה?", "en": "How much does it cost?", "ru": "Сколько это стоит?",
        "fr": "Combien ça coûte?", "ar": "كم تكلفته؟",
    },
    "home.faq3_a": {
        "he": "יש 10 ימי ניסיון בחינם, ואחרי זה תשלום חד־פעמי: 19.90 ₪ לשבוע, 29.90 ₪ לשבועיים או 49.90 ₪ לחודש. בלי חידוש אוטומטי.",
        "en": "There's a 10-day trial period, then a one-time payment: ₪19.90 for a week, ₪29.90 for two weeks or ₪49.90 for a month, no automatic renewal.",
        "ru": "Есть 10-дневный пробный период, затем разовый платёж: 19.90 ₪ за неделю, 29.90 ₪ за две недели или 49.90 ₪ за месяц, без автопродления.",
        "fr": "Il y a une période d'essai de 10 jours, puis un paiement unique: 19,90 ₪ pour une semaine, 29,90 ₪ pour deux semaines ou 49,90 ₪ pour un mois, sans renouvellement automatique.",
        "ar": "هناك فترة تجريبية مدتها 10 أيام، ثم دفعة واحدة: 19.90 ₪ للأسبوع، أو 29.90 ₪ لأسبوعين، أو 49.90 ₪ للشهر, بدون تجديد تلقائي.",
    },
    "home.faq4_q": {
        "he": "אפשר לשנות את הסינון אחרי שהגדרתי אותו?",
        "en": "Can I change my filter after setting it up?",
        "ru": "Можно ли изменить фильтр после его настройки?",
        "fr": "Puis-je modifier mon filtre après l'avoir configuré?",
        "ar": "هل يمكنني تغيير الفلتر بعد إعداده؟",
    },
    "home.faq4_a": {
        "he": "בטח. בבוט בטלגרם או פה באתר, בעמוד ״הסינון שלי״, מתי שבא לך.",
        "en": "Absolutely, through the Telegram bot or right here on the site, on the \"My filter\" page, whenever you like.",
        "ru": "Конечно, через бота в Telegram или прямо здесь на сайте, на странице «Мой фильтр», в любой момент.",
        "fr": "Bien sûr, via le bot Telegram ou ici même sur le site, sur la page « Mon filtre », à tout moment.",
        "ar": "بالتأكيد, عبر البوت على تيليجرام أو هنا على الموقع، في صفحة \"فلتري\"، في أي وقت تشاء.",
    },
    "home.footer_cta_title": {
        "he": "יאללה, בוא נמצא לך דירה", "en": "Come on, let's find you an apartment",
        "ru": "Давайте найдём вам квартиру", "fr": "Allez, trouvons-vous un appartement",
        "ar": "يلّا، لنجد لك شقة",
    },
    "home.footer_cta_body": {
        "he": "לוקח פחות משתי דקות להתחיל, וההתראות הראשונות יכולות להגיע כבר היום.",
        "en": "It takes less than two minutes to get started, and your first alerts can arrive today.",
        "ru": "Начать можно меньше чем за две минуты, а первые уведомления могут прийти уже сегодня.",
        "fr": "Il faut moins de deux minutes pour commencer, et vos premières alertes peuvent arriver dès aujourd'hui.",
        "ar": "يستغرق البدء أقل من دقيقتين، وقد تصلك أول التنبيهات اليوم نفسه.",
    },
    "home.footer_cta_btn": {
        "he": "פתח את הבוט בטלגרם", "en": "Open the Telegram bot",
        "ru": "Открыть бота в Telegram", "fr": "Ouvrir le bot Telegram",
        "ar": "افتح البوت على تيليجرام",
    },
    # ---------- apartments page ----------
    "apartments.title": {
        "he": "דירות תואמות", "en": "Matching apartments", "ru": "Подходящие квартиры",
        "fr": "Appartements correspondants", "ar": "شقق مطابقة",
    },
    "apartments.subtitle": {
        "he": "כל דירה שעברה את הסינון שלך, ממוינת מהחדשה ביותר",
        "en": "Every apartment that passed your filter, sorted newest first",
        "ru": "Все квартиры, прошедшие ваш фильтр, отсортированы от новых к старым",
        "fr": "Tous les appartements ayant passé votre filtre, triés du plus récent au plus ancien",
        "ar": "كل شقة اجتازت فلترك، مرتبة من الأحدث إلى الأقدم",
    },
    "apartments.results_label": {
        "he": "תוצאות", "en": "results", "ru": "результатов", "fr": "résultats", "ar": "نتائج",
    },
    "apartments.notice": {
        "he": "גישה זמנית לפי מזהה טלגרם. הקישור האישי הזה עדיין לא מאובטח לגמרי, שלב ביניים עד להשקה.",
        "en": "Temporary access via Telegram ID, this personal link isn't fully secure yet, just an interim step until launch.",
        "ru": "Временный доступ по Telegram ID, эта персональная ссылка пока не полностью защищена, это лишь промежуточный этап до запуска.",
        "fr": "Accès temporaire via l'identifiant Telegram, ce lien personnel n'est pas encore totalement sécurisé, c'est juste une étape intermédiaire avant le lancement.",
        "ar": "وصول مؤقت عبر معرف تيليجرام, هذا الرابط الشخصي ليس آمنًا بالكامل بعد، وهو مجرد مرحلة انتقالية حتى الإطلاق.",
    },
    "apartments.filter_label": {
        "he": "הסינון שלך:", "en": "Your filter:", "ru": "Ваш фильтр:", "fr": "Votre filtre:", "ar": "فلترك:",
    },
    "apartments.rooms_suffix": {
        "he": "חדרים", "en": "rooms", "ru": "комнат", "fr": "pièces", "ar": "غرف",
    },
    "apartments.edit_filter_btn": {
        "he": "ערוך סינון", "en": "Edit filter", "ru": "Изменить фильтр",
        "fr": "Modifier le filtre", "ar": "تعديل الفلتر",
    },
    "apartments.no_brokers_on": {
        "he": "בלי תיווך", "en": "No brokers", "ru": "Без посредников",
        "fr": "Sans agences", "ar": "بدون سماسرة",
    },
    "apartments.no_brokers_off": {
        "he": "כולל תיווך", "en": "Including brokers", "ru": "С посредниками",
        "fr": "Avec agences", "ar": "يشمل السماسرة",
    },
    "apartments.empty_title": {
        "he": "עוד אין דירות שמתאימות לך.",
        "en": "No matching apartments to show yet.",
        "ru": "Пока нет подходящих квартир для показа.",
        "fr": "Aucun appartement correspondant à afficher pour le moment.",
        "ar": "لا توجد بعد شقق مطابقة لعرضها.",
    },
    "apartments.empty_hint": {
        "he": "אולי הסינון קצת צר. נסה להרחיב אותו, או תחזור עוד מעט אחרי הסריקה הבאה.",
        "en": "Your filter may be a little narrow. Try widening it, or come back after the next scan.",
        "ru": "Возможно, фильтр слишком узкий. Попробуйте расширить его или загляните после следующего сканирования.",
        "fr": "Votre filtre est peut-être un peu étroit. Élargissez-le, ou revenez après le prochain scan.",
        "ar": "ربما الفلتر ضيق قليلًا. جرّب توسيعه، أو عد بعد الفحص القادم.",
    },
    # Announced via an aria-live region when infinite scroll loads another batch (2026-09-07 audit
    # fix) — without this, a screen-reader user got zero indication that new listings had appeared
    # below the ones they'd already heard, since the new cards are inserted silently by JS with no
    # page navigation to re-announce anything.
    "apartments.loading_more": {
        "he": "רגע, טוען עוד דירות...",
        "en": "One moment, loading more apartments...",
        "ru": "Секунду, загружаем ещё квартиры...",
        "fr": "Un instant, chargement d'autres appartements...",
        "ar": "لحظة واحدة، جارٍ تحميل المزيد من الشقق...",
    },
    "apartments.more_loaded_announcement": {
        "he": "{count} דירות נוספות נטענו",
        "en": "{count} more apartments loaded",
        "ru": "Загружено ещё {count} квартир",
        "fr": "{count} appartements supplémentaires chargés",
        "ar": "تم تحميل {count} شقق إضافية",
    },
    # ---------- apartments map/filter workspace (2026-09-24, dorin.app-style layout) ----------
    "apartments.map_aria_label": {
        "he": "מפת הדירות התואמות", "en": "Map of matching apartments",
        "ru": "Карта подходящих квартир", "fr": "Carte des appartements correspondants",
        "ar": "خريطة الشقق المطابقة",
    },
    "apartments.map_pins_count": {
        "he": "{shown} דירות על המפה (מתוך {total})",
        "en": "{shown} apartments on the map (out of {total})",
        "ru": "{shown} квартир на карте (из {total})",
        "fr": "{shown} appartements sur la carte (sur {total})",
        "ar": "{shown} شقق على الخريطة (من {total})",
    },
    "apartments.map_load_failed": {
        "he": "המפה לא נטענה כרגע (אולי חוסם פרסומות בדפדפן). הדירות עצמן מופיעות ברשימה.",
        "en": "The map couldn't load right now (an ad/privacy blocker may be blocking it), the apartments themselves are still shown in the list.",
        "ru": "Не удалось загрузить карту (возможно, её блокирует блокировщик рекламы/приватности), сами квартиры всё ещё показаны в списке.",
        "fr": "La carte n'a pas pu se charger (un bloqueur de publicités/confidentialité la bloque peut-être), les appartements restent affichés dans la liste.",
        "ar": "تعذّر تحميل الخريطة الآن (ربما يحظرها مانع إعلانات/خصوصية), الشقق نفسها لا تزال معروضة في القائمة.",
    },
    "apartments.map_no_pins": {
        "he": "לאף אחת מהדירות המוצגות כרגע אין מיקום מדויק על המפה.",
        "en": "None of the currently shown apartments have an exact map location.",
        "ru": "Ни одна из показанных сейчас квартир не имеет точного местоположения на карте.",
        "fr": "Aucun des appartements actuellement affichés n'a d'emplacement exact sur la carte.",
        "ar": "لا تحتوي أي من الشقق المعروضة حاليًا على موقع دقيق على الخريطة.",
    },
    "apartments.resize_map_label": {
        "he": "שנה את רוחב המפה", "en": "Resize the map panel",
        "ru": "Изменить ширину карты", "fr": "Redimensionner le panneau de la carte",
        "ar": "تغيير حجم لوحة الخريطة",
    },
    "apartments.resize_filter_label": {
        "he": "שנה את רוחב הסינון", "en": "Resize the filter panel",
        "ru": "Изменить ширину фильтра", "fr": "Redimensionner le panneau de filtre",
        "ar": "تغيير حجم لوحة الفلتر",
    },
    "apartments.filter_panel_title": {
        "he": "סינון", "en": "Filter", "ru": "Фильтр", "fr": "Filtre", "ar": "فلتر",
    },
    # Map collapse/expand toggle (2026-09-24, real owner request) — a small arrow at the map's own
    # top-left corner collapses it; once collapsed, a pill button at the workspace's left edge
    # reopens it, so the map doesn't have to stay permanently open for users who'd rather not have it.
    "apartments.map_collapse_label": {
        "he": "סגור את תצוגת המפה", "en": "Close the map view",
        "ru": "Закрыть карту", "fr": "Fermer la vue carte",
        "ar": "إغلاق عرض الخريطة",
    },
    "apartments.map_reopen_label": {
        "he": "תצוגת מפה", "en": "Map view", "ru": "Показать карту", "fr": "Vue carte",
        "ar": "عرض الخريطة",
    },
    # 2026-09-24: the toolbar toggle's own label swaps between this (map hidden) and
    # map_reopen_label above (map hidden -> shown) depending on current state.
    "apartments.map_hide_label": {
        "he": "הסתר מפה", "en": "Hide map", "ru": "Скрыть карту", "fr": "Masquer la carte",
        "ar": "إخفاء الخريطة",
    },
    # Listing-detail drawer inside the filter pane (2026-09-24, real owner request comparing
    # directly against dorin.app: clicking a card used to only be reachable through the outbound
    # "view" link, jumping straight off-site — now clicking the card opens a real floating modal
    # with the listing's own details, closed via the bar spanning its own top (2026-09-24: this key
    # originally read "back to filter" for an earlier sidebar-swap version of this feature, replaced
    # with a real modal — see the modal markup's own comment).
    "apartments.detail_close_label": {
        "he": "סגור וחזור", "en": "Close",
        "ru": "Закрыть", "fr": "Fermer",
        "ar": "إغلاق",
    },
    # 2026-09-26: real owner request — on desktop specifically, opening a listing now swaps the
    # filter sidebar's own content for the listing's details in place (dorin.app's own pattern,
    # confirmed against a live reference), rather than the floating modal mobile keeps using. This
    # is that swap's own "go back" control label — separate from detail_close_label above (the
    # modal's close button, unchanged, still used on mobile) since the two are different controls
    # now, not the same one reused across breakpoints like the pre-modal version of this feature.
    "apartments.detail_back_to_filter_label": {
        "he": "חזרה לסינון", "en": "Back to filters",
        "ru": "Назад к фильтрам", "fr": "Retour aux filtres",
        "ar": "العودة إلى الفلتر",
    },
    "apartments.detail_view_title": {
        "he": "פרטי הדירה", "en": "Apartment details",
        "ru": "Информация о квартире", "fr": "Détails de l'appartement",
        "ar": "تفاصيل الشقة",
    },
    # 2026-09-25: real owner request, comparing directly against dorin.app's own bottom-sheet
    # detail view — the modal's description used to be a plain paragraph with no heading at all,
    # and the only date shown was the card's own relative "posted X ago" tucked in the footer next
    # to the CTA button. dorin shows a real "תיאור הנכס" section heading and an exact posted date
    # as its own line near the bottom — both added to apartments.html's own openListingDetail()
    # using data already on the card (data-posted-at), no new backend data needed.
    "apartments.detail_description_heading": {
        "he": "תיאור הנכס", "en": "Property description",
        "ru": "Описание объекта", "fr": "Description du bien",
        "ar": "وصف العقار",
    },
    "apartments.detail_also_on": {
        "he": "המודעה פורסמה גם ב:", "en": "Also posted on:",
        "ru": "Также опубликовано на:", "fr": "Aussi publiée sur:",
        "ar": "نُشر أيضًا على:",
    },
    "apartments.detail_posted_on": {
        "he": "פורסם ב-{date}", "en": "Posted on {date}",
        "ru": "Опубликовано {date}", "fr": "Publié le {date}",
        "ar": "نُشر في {date}",
    },
    # 2026-10-14 owner request: the rich listing detail view (templates/_listing_details.html, main.py's listing_details).
    "details.loading": {
        "he": "טוען עוד פרטים…",
        "en": "Loading more details…",
        "ru": "Загружаем подробности…",
        "fr": "Chargement des détails…",
        "ar": "جارٍ تحميل المزيد من التفاصيل…",
    },
    "details.facts_title": {
        "he": "פרטי הנכס",
        "en": "Property details",
        "ru": "Характеристики",
        "fr": "Caractéristiques",
        "ar": "تفاصيل العقار",
    },
    "details.property_type": {
        "he": "סוג נכס",
        "en": "Type",
        "ru": "Тип",
        "fr": "Type",
        "ar": "النوع",
    },
    "details.rooms": {
        "he": "חדרים",
        "en": "Rooms",
        "ru": "Комнаты",
        "fr": "Pièces",
        "ar": "الغرف",
    },
    "details.size": {
        "he": "גודל",
        "en": "Size",
        "ru": "Площадь",
        "fr": "Surface",
        "ar": "المساحة",
    },
    "details.size_value": {
        "he": "{n} מ״ר",
        "en": "{n} m²",
        "ru": "{n} м²",
        "fr": "{n} m²",
        "ar": "{n} م²",
    },
    "details.floor": {
        "he": "קומה",
        "en": "Floor",
        "ru": "Этаж",
        "fr": "Étage",
        "ar": "الطابق",
    },
    "details.floor_of": {
        "he": "{floor} מתוך {total}",
        "en": "{floor} of {total}",
        "ru": "{floor} из {total}",
        "fr": "{floor} sur {total}",
        "ar": "{floor} من {total}",
    },
    "details.floor_ground": {
        "he": "קרקע",
        "en": "Ground",
        "ru": "Нулевой (партер)",
        "fr": "Rez-de-chaussée",
        "ar": "الأرضي",
    },
    "details.price_per_sqm": {
        "he": "מחיר למ״ר",
        "en": "Price per m²",
        "ru": "Цена за м²",
        "fr": "Prix au m²",
        "ar": "السعر للمتر المربع",
    },
    "details.move_in": {
        "he": "כניסה",
        "en": "Move-in",
        "ru": "Въезд",
        "fr": "Emménagement",
        "ar": "الدخول",
    },
    "details.listed_by": {
        "he": "מפרסם",
        "en": "Listed by",
        "ru": "Кто размещает",
        "fr": "Annonceur",
        "ar": "المُعلِن",
    },
    "details.listed_by_broker": {
        "he": "תיווך",
        "en": "Broker",
        "ru": "Посредник",
        "fr": "Agence",
        "ar": "وسيط",
    },
    "details.listed_by_private": {
        "he": "פרטי, בלי תיווך",
        "en": "Private, no broker",
        "ru": "Частное, без посредника",
        "fr": "Particulier, sans agence",
        "ar": "خاص، بدون وسيط",
    },
    "details.furniture": {
        "he": "ריהוט",
        "en": "Furniture",
        "ru": "Мебель",
        "fr": "Mobilier",
        "ar": "الأثاث",
    },
    "details.furnished": {
        "he": "מרוהטת",
        "en": "Furnished",
        "ru": "С мебелью",
        "fr": "Meublé",
        "ar": "مفروشة",
    },
    "details.unfurnished": {
        "he": "לא מרוהטת",
        "en": "Unfurnished",
        "ru": "Без мебели",
        "fr": "Non meublé",
        "ar": "غير مفروشة",
    },
    "details.safe_room": {
        "he": "מרחב מוגן",
        "en": "Shelter",
        "ru": "Защищённое помещение",
        "fr": "Abri",
        "ar": "مكان محمي",
    },
    "details.safe_room_in_flat": {
        "he": "ממ״ד בדירה",
        "en": "Safe room in the flat",
        "ru": "Мамад в квартире",
        "fr": "Pièce sécurisée dans l'appartement",
        "ar": "غرفة آمنة في الشقة",
    },
    "details.building_shelter": {
        "he": "מקלט בבניין",
        "en": "Shelter in the building",
        "ru": "Убежище в здании",
        "fr": "Abri dans l'immeuble",
        "ar": "ملجأ في المبنى",
    },
    "details.no_shelter": {
        "he": "אין",
        "en": "None",
        "ru": "Нет",
        "fr": "Aucun",
        "ar": "لا يوجد",
    },
    "details.amenities_title": {
        "he": "פיצ׳רים בדירה",
        "en": "Features",
        "ru": "Удобства в квартире",
        "fr": "Équipements",
        "ar": "مزايا الشقة",
    },
    "details.amenity_roommates": {
        "he": "מתאימה לשותפים",
        "en": "suits roommates",
        "ru": "подходит для соседей",
        "fr": "colocation possible",
        "ar": "مناسبة للسكن المشترك",
    },
    "details.amenity_yes": {
        "he": "יש",
        "en": "Yes",
        "ru": "Есть",
        "fr": "Oui",
        "ar": "يوجد",
    },
    "details.amenity_no": {
        "he": "אין",
        "en": "No",
        "ru": "Нет",
        "fr": "Non",
        "ar": "لا يوجد",
    },
    "details.area_title": {
        "he": "המחיר ביחס לאזור",
        "en": "Price vs. the area",
        "ru": "Цена относительно района",
        "fr": "Prix par rapport au quartier",
        "ar": "السعر مقارنة بالمنطقة",
    },
    "details.area_cheaper": {
        "he": "זולה ב-{pct}% מהמחיר הרגיל באזור",
        "en": "{pct}% below the usual price here",
        "ru": "На {pct}% дешевле обычного для района",
        "fr": "{pct} % sous le prix habituel du quartier",
        "ar": "أرخص بنسبة {pct}% من السعر المعتاد في المنطقة",
    },
    "details.area_pricier": {
        "he": "יקרה ב-{pct}% מהמחיר הרגיל באזור",
        "en": "{pct}% above the usual price here",
        "ru": "На {pct}% дороже обычного для района",
        "fr": "{pct} % au-dessus du prix habituel du quartier",
        "ar": "أغلى بنسبة {pct}% من السعر المعتاد في المنطقة",
    },
    "details.area_typical": {
        "he": "בדיוק במחיר הרגיל באזור",
        "en": "Right at the usual price here",
        "ru": "Обычная цена для района",
        "fr": "Dans la moyenne du quartier",
        "ar": "بالسعر المعتاد في المنطقة",
    },
    "details.area_median_rooms": {
        "he": "המחיר האמצעי לדירות {rooms} חדרים ב{area}: {price} ₪",
        "en": "Median for {rooms} rooms in {area}: {price} ₪",
        "ru": "Медиана для {rooms} комн. в {area}: {price} ₪",
        "fr": "Médiane pour {rooms} pièces à {area}: {price} ₪",
        "ar": "الوسيط لشقق {rooms} غرف في {area}: {price} ₪",
    },
    "details.area_median": {
        "he": "המחיר האמצעי ב{area}: {price} ₪",
        "en": "Median in {area}: {price} ₪",
        "ru": "Медиана в {area}: {price} ₪",
        "fr": "Médiane à {area}: {price} ₪",
        "ar": "الوسيط في {area}: {price} ₪",
    },
    "details.area_based_on": {
        "he": "לפי {n} מודעות מהחודש האחרון",
        "en": "based on {n} listings from the last month",
        "ru": "по {n} объявлениям за последний месяц",
        "fr": "d'après {n} annonces du dernier mois",
        "ar": "استنادًا إلى {n} إعلانًا من الشهر الأخير",
    },
    "details.area_sqm": {
        "he": "למ״ר: {mine} ₪ כאן, לעומת {usual} ₪ בדרך כלל",
        "en": "Per m²: {mine} ₪ here vs. {usual} ₪ usually",
        "ru": "За м²: {mine} ₪ здесь, обычно {usual} ₪",
        "fr": "Au m²: {mine} ₪ ici, contre {usual} ₪ d'habitude",
        "ar": "للمتر المربع: {mine} ₪ هنا، مقابل {usual} ₪ عادةً",
    },
    "details.area_few": {
        "he": "מבוסס על מעט מודעות ({n}), כדאי להתייחס בזהירות",
        "en": "Based on only {n} listings, so take it with caution",
        "ru": "Всего {n} объявлений, относитесь с осторожностью",
        "fr": "Seulement {n} annonces, à prendre avec prudence",
        "ar": "يستند إلى {n} إعلانات فقط، لذا تعامل معه بحذر",
    },
    "details.area_how_title": {
        "he": "איך חישבנו את זה?",
        "en": "How we worked this out",
        "ru": "Как мы это посчитали",
        "fr": "Comment nous l'avons calculé",
        "ar": "كيف حسبنا ذلك",
    },
    "details.area_how_body": {
        "he": "חישבנו את זה בעצמנו, רק מהמודעות שאספנו: המחיר האמצעי מתוך {n} מודעות של {kind} ב{area} שראינו ב־30 הימים האחרונים (כולל כאלה שכבר ירדו), בלי כפילויות של אותה דירה ובלי הדירה הזאת עצמה. אלה המחירים המבוקשים במודעות, לא המחירים שנסגרו בפועל. אין כאן הערכה ואין מידע מבחוץ.",
        "en": "We worked this out ourselves, only from the listings we collected: the median of {n} listings of {kind} in {area} that we saw in the last 30 days (including ones already taken down), without duplicates of the same flat and without this one. These are the asking prices in the ads, not the prices finally agreed. No estimates and no outside data.",
        "ru": "Мы посчитали это сами, только по собранным нами объявлениям: медиана {n} объявлений ({kind}, {area}) за последние 30 дней (включая уже снятые), без дублей одной квартиры и без этой. Это цены из объявлений, а не цены реальных сделок. Никаких оценок и внешних данных.",
        "fr": "Calculé par nous, uniquement à partir des annonces que nous avons collectées: la médiane de {n} annonces ({kind}, {area}) vues ces 30 derniers jours (y compris celles déjà retirées), sans doublons du même logement et sans celle-ci. Ce sont les prix demandés dans les annonces, pas les prix réellement conclus. Aucune estimation ni donnée extérieure.",
        "ar": "حسبنا ذلك بأنفسنا، فقط من الإعلانات التي جمعناها: الوسيط من {n} إعلانًا ({kind}، {area}) رأيناها خلال آخر 30 يومًا (بما فيها التي أُزيلت)، دون تكرارات للشقة نفسها ودون هذه الشقة. هذه أسعار مطلوبة في الإعلانات، لا أسعار صفقات فعلية. لا تقديرات ولا بيانات خارجية.",
    },
    "details.kind_rooms": {
        "he": "דירות {rooms} חדרים",
        "en": "{rooms}-room flats",
        "ru": "{rooms} комн.",
        "fr": "{rooms} pièces",
        "ar": "{rooms} غرف",
    },
    "details.kind_any": {
        "he": "דירות",
        "en": "flats",
        "ru": "квартиры",
        "fr": "logements",
        "ar": "شقق",
    },
    "details.deal_rent": {
        "he": "להשכרה",
        "en": "for rent",
        "ru": "аренда",
        "fr": "location",
        "ar": "إيجار",
    },
    "details.deal_sale": {
        "he": "למכירה",
        "en": "for sale",
        "ru": "продажа",
        "fr": "vente",
        "ar": "بيع",
    },
    "details.deal_sublet": {
        "he": "בסאבלט",
        "en": "as a sublet",
        "ru": "субаренда",
        "fr": "sous-location",
        "ar": "إيجار من الباطن",
    },
    "details.area_scale_low": {
        "he": "זול יותר",
        "en": "Cheaper",
        "ru": "Дешевле",
        "fr": "Moins cher",
        "ar": "أرخص",
    },
    "details.area_scale_mid": {
        "he": "רגיל",
        "en": "Usual",
        "ru": "Обычно",
        "fr": "Habituel",
        "ar": "معتاد",
    },
    "details.area_scale_high": {
        "he": "יקר יותר",
        "en": "Pricier",
        "ru": "Дороже",
        "fr": "Plus cher",
        "ar": "أغلى",
    },
    "details.sources_title": {
        "he": "איפה המודעה פורסמה",
        "en": "Where it was posted",
        "ru": "Где опубликовано",
        "fr": "Où elle est publiée",
        "ar": "أين نُشر الإعلان",
    },
    "details.source_line": {
        "he": "המודעה הזאת מ{source}",
        "en": "This listing is from {source}",
        "ru": "Это объявление с {source}",
        "fr": "Cette annonce vient de {source}",
        "ar": "هذا الإعلان من {source}",
    },
    "details.also_on_line": {
        "he": "המודעה הזאת הועלתה גם ב:",
        "en": "This listing was also posted on:",
        "ru": "Это объявление также размещено на:",
        "fr": "Cette annonce est aussi publiée sur:",
        "ar": "نُشر هذا الإعلان أيضًا على:",
    },
    "details.only_on": {
        "he": "לא מצאנו אותה באתרים אחרים, רק ב{source}",
        "en": "Not found on other sites, only on {source}",
        "ru": "На других сайтах не найдено, только на {source}",
        "fr": "Introuvable ailleurs, seulement sur {source}",
        "ar": "لم نجده في مواقع أخرى، فقط على {source}",
    },
    "details.timeline_title": {
        "he": "ציר זמן",
        "en": "Timeline",
        "ru": "Хронология",
        "fr": "Chronologie",
        "ar": "الجدول الزمني",
    },
    "details.timeline_posted": {
        "he": "פורסמה באתר המקור",
        "en": "Posted on the source site",
        "ru": "Опубликовано на сайте",
        "fr": "Publiée sur le site d'origine",
        "ar": "نُشر في الموقع الأصلي",
    },
    "details.timeline_found": {
        "he": "טודירה מצאה אותה",
        "en": "Todira found it",
        "ru": "Todira нашла его",
        "fr": "Todira l'a trouvée",
        "ar": "عثرت عليه توديرا",
    },
    "details.timeline_price_drop": {
        "he": "המחיר ירד מ-{old} ₪ ל-{new} ₪",
        "en": "Price dropped from {old} ₪ to {new} ₪",
        "ru": "Цена снизилась с {old} ₪ до {new} ₪",
        "fr": "Le prix est passé de {old} ₪ à {new} ₪",
        "ar": "انخفض السعر من {old} ₪ إلى {new} ₪",
    },
    "details.timeline_price_rise": {
        "he": "המחיר עלה מ-{old} ₪ ל-{new} ₪",
        "en": "Price rose from {old} ₪ to {new} ₪",
        "ru": "Цена выросла с {old} ₪ до {new} ₪",
        "fr": "Le prix est passé de {old} ₪ à {new} ₪",
        "ar": "ارتفع السعر من {old} ₪ إلى {new} ₪",
    },
    "details.timeline_last_seen": {
        "he": "עדיין באוויר, נבדקה לאחרונה",
        "en": "Still live, last checked",
        "ru": "Ещё активно, последняя проверка",
        "fr": "Toujours en ligne, vérifiée le",
        "ar": "لا يزال نشطًا، آخر فحص",
    },
    "details.timeline_delisted": {
        "he": "ירדה מהאתר",
        "en": "Taken down",
        "ru": "Снято с сайта",
        "fr": "Retirée du site",
        "ar": "أُزيل من الموقع",
    },
    "details.location_title": {
        "he": "מיקום",
        "en": "Location",
        "ru": "Расположение",
        "fr": "Emplacement",
        "ar": "الموقع",
    },
    "details.map_approx": {
        "he": "המיקום על המפה משוער",
        "en": "The map position is approximate",
        "ru": "Положение на карте приблизительное",
        "fr": "Position approximative",
        "ar": "الموقع على الخريطة تقريبي",
    },
    "details.open_in_maps": {
        "he": "פתיחה בגוגל מפות",
        "en": "Open in Google Maps",
        "ru": "Открыть в Google Maps",
        "fr": "Ouvrir dans Google Maps",
        "ar": "افتح في خرائط Google",
    },
    "details.similar_title": {
        "he": "דירות דומות באזור",
        "en": "Similar apartments nearby",
        "ru": "Похожие квартиры рядом",
        "fr": "Appartements similaires à proximité",
        "ar": "شقق مشابهة في المنطقة",
    },
    "details.similar_rooms": {
        "he": "{rooms} חד׳",
        "en": "{rooms} rooms",
        "ru": "{rooms} комн.",
        "fr": "{rooms} p.",
        "ar": "{rooms} غرف",
    },
    # Map settings popover — filters which PINS show by listing age, without touching the listing
    # list itself (real owner request, lower detail/priority than the rest of this batch, referencing
    # a dorin.app screenshot of an equivalent control).
    "apartments.map_settings_label": {
        "he": "הגדרות מפה", "en": "Map settings",
        "ru": "Настройки карты", "fr": "Paramètres de la carte",
        "ar": "إعدادات الخريطة",
    },
    "apartments.map_age_filter_label": {
        "he": "הסתר מודעות ישנות מ-", "en": "Hide listings older than",
        "ru": "Скрыть объявления старше", "fr": "Masquer les annonces de plus de",
        "ar": "إخفاء الإعلانات الأقدم من",
    },
    "apartments.map_age_all": {
        "he": "הצג הכל", "en": "Show all", "ru": "Показать все", "fr": "Tout afficher",
        "ar": "عرض الكل",
    },
    "apartments.map_age_7": {
        "he": "7 ימים", "en": "7 days", "ru": "7 дней", "fr": "7 jours", "ar": "7 أيام",
    },
    "apartments.map_age_14": {
        "he": "14 ימים", "en": "14 days", "ru": "14 дней", "fr": "14 jours", "ar": "14 يومًا",
    },
    "apartments.map_age_30": {
        "he": "30 יום", "en": "30 days", "ru": "30 дней", "fr": "30 jours", "ar": "30 يومًا",
    },
    "apartments.map_draw_rect_label": {
        "he": "סימון אזור מלבני", "en": "Draw a rectangle area",
        "ru": "Нарисовать прямоугольную область", "fr": "Dessiner une zone rectangulaire",
        "ar": "رسم منطقة مستطيلة",
    },
    "apartments.map_draw_circle_label": {
        "he": "סימון אזור עגול", "en": "Draw a circle area",
        "ru": "Нарисовать круглую область", "fr": "Dessiner une zone circulaire",
        "ar": "رسم منطقة دائرية",
    },
    "apartments.map_region_clear_label": {
        "he": "נקה אזור מסומן", "en": "Clear drawn area",
        "ru": "Очистить область", "fr": "Effacer la zone",
        "ar": "مسح المنطقة",
    },
    "apartments.map_region_drawing_hint": {
        "he": "גרור על המפה כדי לצייר את האזור", "en": "Drag on the map to draw the area",
        "ru": "Перетащите на карте, чтобы нарисовать область",
        "fr": "Faites glisser sur la carte pour dessiner la zone",
        "ar": "اسحب على الخريطة لرسم المنطقة",
    },
    "apartments.map_region_active_label": {
        "he": "מסונן לפי אזור מסומן על המפה", "en": "Filtered by a drawn map area",
        "ru": "Фильтр по области на карте", "fr": "Filtré par une zone dessinée sur la carte",
        "ar": "تمت التصفية حسب منطقة مرسومة على الخريطة",
    },
    # ---------- liked page ----------
    "liked.title": {
        "he": "דירות שמורות", "en": "Saved apartments", "ru": "Сохранённые квартиры",
        "fr": "Appartements enregistrés", "ar": "شقق محفوظة",
    },
    "liked.subtitle": {
        "he": "דירות שסימנת כמעניינות, כאן ובבוט בטלגרם",
        "en": "Apartments you marked as interesting, here and in the Telegram bot",
        "ru": "Квартиры, которые вы отметили как интересные, здесь и в боте Telegram",
        "fr": "Appartements que vous avez marqués comme intéressants, ici et dans le bot Telegram",
        "ar": "شقق علّمتها كمهمة, هنا وفي بوت تيليجرام",
    },
    "liked.empty_title": {
        "he": "עדיין לא שמרת דירות.", "en": "You haven't saved any apartments yet.",
        "ru": "Вы ещё не сохранили ни одной квартиры.", "fr": "Vous n'avez encore enregistré aucun appartement.",
        "ar": "لم تحفظ أي شقة بعد.",
    },
    "liked.empty_hint": {
        "he": "כשתסמן דירה כ\"אהבתי\" בטלגרם, היא תופיע כאן.",
        "en": "Once you mark an apartment as \"liked\" on Telegram, it'll show up here.",
        "ru": "Как только вы отметите квартиру как «понравилось» в Telegram, она появится здесь.",
        "fr": "Dès que vous marquez un appartement comme « aimé » sur Telegram, il apparaîtra ici.",
        "ar": "بمجرد أن تعلّم شقة بـ\"أعجبتني\" في تيليجرام، ستظهر هنا.",
    },
    "liked.hidden_link": {
        "he": "דירות מוסתרות", "en": "Hidden apartments", "ru": "Скрытые квартиры",
        "fr": "Appartements masqués", "ar": "الشقق المخفية",
    },
    # ---------- hidden page ----------
    "hidden.title": {
        "he": "דירות מוסתרות", "en": "Hidden apartments", "ru": "Скрытые квартиры",
        "fr": "Appartements masqués", "ar": "شقق مخفية",
    },
    "hidden.subtitle": {
        "he": "דירות שהסתרת מרשימת ההתאמות. לחיצה נוספת על 👀 מחזירה אותן",
        "en": "Apartments you hid from your matches, tap 👀 again to bring them back",
        "ru": "Квартиры, которые вы скрыли из совпадений, нажмите 👀 ещё раз, чтобы вернуть их",
        "fr": "Appartements que vous avez masqués de vos correspondances, appuyez à nouveau sur 👀 pour les récupérer",
        "ar": "شقق أخفيتها من نتائجك, اضغط 👀 مجددًا لإعادتها",
    },
    "hidden.empty_title": {
        "he": "אין לך כרגע דירות מוסתרות.", "en": "You don't have any hidden apartments right now.",
        "ru": "У вас сейчас нет скрытых квартир.", "fr": "Vous n'avez actuellement aucun appartement masqué.",
        "ar": "ليس لديك حاليًا شقق مخفية.",
    },
    "hidden.empty_hint": {
        "he": "כשתסתיר דירה (🙈) כאן או בטלגרם, היא תופיע כאן.",
        "en": "Once you hide an apartment (🙈) here or on Telegram, it'll show up here.",
        "ru": "Как только вы скроете квартиру (🙈) здесь или в Telegram, она появится здесь.",
        "fr": "Dès que vous masquez un appartement (🙈) ici ou sur Telegram, il apparaîtra ici.",
        "ar": "بمجرد أن تخفي شقة (🙈) هنا أو في تيليجرام، ستظهر هنا.",
    },
    "hidden.liked_link": {
        "he": "דירות שמורות", "en": "Saved apartments", "ru": "Сохранённые квартиры",
        "fr": "Appartements enregistrés", "ar": "الشقق المحفوظة",
    },
    # ---------- listing card ----------
    "card.like_btn": {
        "he": "שמור דירה", "en": "Save apartment", "ru": "Сохранить квартиру",
        "fr": "Enregistrer l'appartement", "ar": "احفظ الشقة",
    },
    "card.hide_btn": {
        "he": "הסתר דירה", "en": "Hide apartment", "ru": "Скрыть квартиру",
        "fr": "Masquer l'appartement", "ar": "إخفاء الشقة",
    },
    "card.unhide_btn": {
        "he": "החזר לרשימה", "en": "Unhide", "ru": "Вернуть в список",
        "fr": "Réafficher", "ar": "إظهار مجددًا",
    },
    "card.no_price": {
        "he": "מחיר: לא צוין", "en": "Price: not listed", "ru": "Цена: не указана",
        "fr": "Prix: non indiqué", "ar": "السعر: غير محدد",
    },
    "card.no_city": {
        "he": "עיר לא צוינה", "en": "City not listed", "ru": "Город не указан",
        "fr": "Ville non indiquée", "ar": "المدينة غير محددة",
    },
    "card.rooms": {"he": "חדרים", "en": "rooms", "ru": "комнат", "fr": "pièces", "ar": "غرف"},
    "card.room_in_shared": {
        "he": "חדר בדירת שותפים", "en": "Room in a shared flat", "ru": "Комната в квартире с соседями",
        "fr": "Chambre en colocation", "ar": "غرفة في شقة مشتركة",
    },
    "card.floor": {"he": "קומה", "en": "floor", "ru": "этаж", "fr": "étage", "ar": "طابق"},
    "card.sqm": {"he": "מ\"ר", "en": "sqm", "ru": "кв.м", "fr": "m²", "ar": "م²"},
    "card.amenity_parking": {"he": "חניה", "en": "parking", "ru": "парковка", "fr": "parking", "ar": "موقف سيارات"},
    "card.amenity_elevator": {"he": "מעלית", "en": "elevator", "ru": "лифт", "fr": "ascenseur", "ar": "مصعد"},
    "card.amenity_balcony": {"he": "מרפסת", "en": "balcony", "ru": "балкон", "fr": "balcon", "ar": "شرفة"},
    "card.amenity_pets": {
        "he": "חיות מחמד", "en": "pets ok", "ru": "можно с животными",
        "fr": "animaux acceptés", "ar": "يسمح بالحيوانات",
    },
    "card.amenity_renovated": {
        "he": "משופצת", "en": "renovated", "ru": "отремонтирована", "fr": "rénové", "ar": "مجدّدة",
    },
    "card.amenity_safe_room": {
        "he": 'ממ"ד', "en": "safe room", "ru": "защищённая комната",
        "fr": "pièce sécurisée", "ar": "غرفة محصّنة",
    },
    "card.amenity_furnished": {
        "he": "מרוהטת", "en": "furnished", "ru": "меблирована", "fr": "meublé", "ar": "مفروشة",
    },
    # ---------- listing card: relative "posted X ago" (replaces the old fixed dd/mm date,
    # 2026-09-02 request — see relative_time_label below) ----------
    "card.posted_ago_seconds": {
        "he": "עלתה לפני {n} שניות", "en": "Posted {n} seconds ago",
        "ru": "Опубликовано {n} секунд назад", "fr": "Publié il y a {n} secondes",
        "ar": "نُشر قبل {n} ثوانٍ",
    },
    "card.posted_ago_minutes": {
        "he": "עלתה לפני {n} דקות", "en": "Posted {n} minutes ago",
        "ru": "Опубликовано {n} минут назад", "fr": "Publié il y a {n} minutes",
        "ar": "نُشر قبل {n} دقائق",
    },
    "card.posted_ago_hours": {
        "he": "עלתה לפני {n} שעות", "en": "Posted {n} hours ago",
        "ru": "Опубликовано {n} часов назад", "fr": "Publié il y a {n} heures",
        "ar": "نُشر قبل {n} ساعات",
    },
    "card.posted_ago_days": {
        "he": "עלתה לפני {n} ימים", "en": "Posted {n} days ago",
        "ru": "Опубликовано {n} дней назад", "fr": "Publié il y a {n} jours",
        "ar": "نُشر قبل {n} أيام",
    },
    "card.view_btn": {
        "he": "לצפייה במודעה", "en": "View listing", "ru": "Смотреть объявление",
        "fr": "Voir l'annonce", "ar": "عرض الإعلان",
    },
    # 2026-09-12: reworded from "Upgrade to view" — the description/photos are now shown to every
    # viewer regardless of subscription (see _listing_card.html); this button now gates only the
    # outbound link to the listing's original source (Yad2/etc), so the copy says that instead.
    "card.locked_btn_renew": {
        "he": "חדש מנוי וקבל קישור למודעה", "en": "Renew for the original link", "ru": "Продлите для перехода к источнику",
        "fr": "Renouveler pour le lien d'origine", "ar": "جدّد للرابط الأصلي",
    },
    "apartments.notice_trial_ended": {
        "he": "תקופת הניסיון הסתיימה! לצפייה במודעות המלאות ובמקור, עם גישה מלאה לשירות, אפשר לשדרג כאן",
        "en": "Your free trial has ended! To see full listings and their source, with full access, upgrade here",
        "ru": "Пробный период закончился! Чтобы видеть объявления полностью и их источник, оформите доступ здесь",
        "fr": "Ta période d'essai est terminée! Pour voir les annonces complètes et leur source, passe à l'accès complet ici",
        "ar": "انتهت الفترة التجريبية! لرؤية الإعلانات كاملة ومصدرها، مع وصول كامل للخدمة، يمكنك الترقية هنا",
    },
    "apartments.notice_subscription_expired": {
        "he": "תקופת המנוי הסתיימה! על מנת לצפות שוב במודעות עם גישה מלאה לשירות, אפשר לחדש מנוי כאן",
        "en": "Your subscription has ended! To see listings again with full access, renew here",
        "ru": "Срок подписки закончился! Чтобы снова видеть объявления с полным доступом, продлите её здесь",
        "fr": "Ton abonnement est terminé! Pour revoir les annonces avec un accès complet, renouvelle-le ici",
        "ar": "انتهى اشتراكك! لرؤية الإعلانات مجدداً مع وصول كامل للخدمة، يمكنك التجديد هنا",
    },
    "apartments.notice_upgrade_btn": {
        "he": "לשדרוג המנוי", "en": "Upgrade", "ru": "Оформить доступ", "fr": "Passer à l'accès complet", "ar": "الترقية",
    },
    "apartments.notice_renew_btn": {
        "he": "לחידוש המנוי", "en": "Renew", "ru": "Продлить", "fr": "Renouveler", "ar": "التجديد",
    },
    "card.locked_btn": {
        "he": "שדרג וקבל קישור למודעה", "en": "Upgrade for original link",
        "ru": "Обновите для перехода к источнику", "fr": "Mettre à niveau pour le lien d'origine",
        "ar": "الترقية للرابط الأصلي",
    },
    # Badge shown on the cover photo (top-left, see .broker-badge in style.css) for a broker-listed
    # property — independent of deal_type (rent or sale, doesn't matter), 2026-09-03 request.
    "card.broker_badge": {
        "he": "תיווך", "en": "Broker", "ru": "Посредник", "fr": "Agence", "ar": "وسيط",
    },
    # 2026-09-26: dorin.app-style contact-action buttons on the listing detail view (real owner
    # request, comparing directly against dorin.app's own "פרטי איש קשר" section). Same has_access
    # gate as card.view_btn/card.locked_btn above — this project never stores the poster's own
    # phone number (see _listing_card.html's own comment on that), so a has_access viewer's click
    # here goes to the listing's own original source page (same target as "view listing"), not a
    # fabricated in-app reveal; a non-access viewer's click opens the contact-paywall modal instead
    # (card.contact_modal_*) rather than navigating at all.
    "card.contact_btn": {
        "he": "פתיחת המודעה המקורית", "en": "Contact, open the original listing",
        "ru": "Связаться, открыть оригинальное объявление",
        "fr": "Contacter, ouvrir l'annonce d'origine", "ar": "التواصل, فتح الإعلان الأصلي",
    },
    "card.contact_modal_title": {
        "he": "רוצה את פרטי הקשר?", "en": "Want the contact details?",
        "ru": "Хотите получить контактные данные?", "fr": "Vous voulez les coordonnées?",
        "ar": "هل تريد بيانات التواصل؟",
    },
    "card.contact_modal_body": {
        "he": "פרטי הקשר של המפרסם פתוחים למנויים. שדרג ותקבל גישה.",
        "en": "Contact details for the poster are open to Premium subscribers. Upgrade your "
        "subscription to access them.",
        "ru": "Контактные данные автора объявления доступны подписчикам Premium. Обновите "
        "подписку, чтобы получить к ним доступ.",
        "fr": "Les coordonnées de l'annonceur sont réservées aux abonnés Premium. Passe à "
        "l'abonnement premium pour y accéder.",
        "ar": "بيانات التواصل مع المعلن متاحة لمشتركي Premium. قم بترقية اشتراكك للوصول إليها.",
    },
    "card.contact_modal_upgrade_btn": {
        "he": "לשדרוג", "en": "Go Premium", "ru": "Перейти на Premium",
        "fr": "Passer à Premium", "ar": "الترقية إلى Premium",
    },
    # 2026-09-26 follow-up: explicit owner decision, matching dorin.app's own popup exactly — a
    # secondary escape hatch that works even for a non-access viewer (unlike the footer's own
    # locked link), straight to the listing's real original source.
    # alt text for a listing's own real photos (2026-09-07 audit: every cover photo had alt="",
    # the same treatment as a genuinely decorative image — a screen-reader user got zero
    # information about what a card's actual photos showed). {city}/{rooms} are filled in from the
    # listing itself; not the illustrated Todi fallback, which stays alt="" on purpose (that one
    # really is decorative — the caption right below it already states there are no real photos).
    "card.photo_alt": {
        "he": "תמונה מהדירה ב{city}, {rooms} חדרים",
        "en": "Photo of the apartment in {city}, {rooms} rooms",
        "ru": "Фото квартиры в {city}, {rooms} комнат",
        "fr": "Photo de l'appartement à {city}, {rooms} pièces",
        "ar": "صورة الشقة في {city}، {rooms} غرف",
    },
    "card.no_image_caption": {
        "he": "הדירה עלתה בלי תמונות, אבל שווה לבקש מהמפרסם כמה!",
        "en": "This listing has no photos yet, it's worth contacting the lister to ask for some!",
        "ru": "У этого объявления пока нет фото, стоит написать автору и попросить!",
        "fr": "Cette annonce n'a pas encore de photos, ça vaut le coup de demander au contact!",
        "ar": "لا توجد صور لهذا العرض بعد, يستحق التواصل مع المعلن لطلبها!",
    },
    # 2026-09-24: property-type badge on the card, real owner request comparing against dorin.app's
    # own card (a "דירה"/"סטודיו"/etc. badge alongside rooms/floor/sqm). A self-contained mirror of
    # PROPERTY_TYPE_LABELS' own text (website/i18n.py) under the card.* namespace rather than
    # passing that dict through every listing_card() caller — hidden.html/liked.html/apartments.html
    # don't all build the same context, and t() (unlike a passed variable) is already a Jinja
    # global available in every one of them without extra wiring.
    "card.type_apartment": {"he": "דירה", "en": "Apartment", "ru": "Квартира", "fr": "Appartement", "ar": "شقة"},
    "card.type_garden_apartment": {
        "he": "דירת גן", "en": "Garden apartment", "ru": "Квартира с садом",
        "fr": "Appartement avec jardin", "ar": "شقة حديقة",
    },
    "card.type_penthouse": {"he": "פנטהאוז", "en": "Penthouse", "ru": "Пентхаус", "fr": "Penthouse", "ar": "بنتهاوس"},
    "card.type_studio": {"he": "סטודיו", "en": "Studio", "ru": "Студия", "fr": "Studio", "ar": "استوديو"},
    "card.type_housing_unit": {
        "he": "יחידת דיור", "en": "Housing unit", "ru": "Жилая единица",
        "fr": "Unité de logement", "ar": "وحدة سكنية",
    },
    "card.type_private_house": {
        "he": "בית פרטי", "en": "Private house", "ru": "Частный дом", "fr": "Maison privée", "ar": "بيت خاص",
    },
    "card.type_shared_room": {
        "he": "חדר בדירת שותפים", "en": "Room in a shared apartment", "ru": "Комната в общей квартире",
        "fr": "Chambre en colocation", "ar": "غرفة في شقة مشتركة",
    },
    "card.move_in_date": {
        "he": "כניסה: {date}", "en": "Move in: {date}", "ru": "Заезд: {date}",
        "fr": "Entrée: {date}", "ar": "الدخول: {date}",
    },
    "card.move_in_immediate": {
        "he": "מיידית", "en": "immediate", "ru": "сразу", "fr": "immédiate", "ar": "فوري",
    },
    "card.move_in_flexible": {
        "he": "גמיש", "en": "flexible", "ru": "гибко", "fr": "flexible", "ar": "مرن",
    },
    # Price-change badge (2026-09-24, real owner request comparing against dorin.app's own card —
    # a struck-through previous price + a colored percentage badge next to the current one). Only
    # the sign-free number goes here; the +/- and color are decided in the template/CSS from
    # whether the price went down or up (see _listing_card.html's own comment).
    "card.price_change_badge": {"he": "{sign}{percent}%", "en": "{sign}{percent}%", "ru": "{sign}{percent}%",
                                 "fr": "{sign}{percent}%", "ar": "{sign}{percent}%"},
    # ---------- filter page ----------
    "filter.title": {
        "he": "הסינון שלי", "en": "My filter", "ru": "Мой фильтр",
        "fr": "Mon filtre", "ar": "فلتري",
    },
    "filter.welcome_banner": {
        "he": "ברוך הבא לטודירה! בוא נגדיר את הסינון, ונראה לך רק דירות שמתאימות לך.",
        "en": "Welcome to Todira! Let's set up your filter so we can show you exactly the apartments that fit",
        "ru": "Добро пожаловать в Todira! Давайте настроим ваш фильтр, чтобы показывать именно те квартиры, которые подходят",
        "fr": "Bienvenue sur Todira! Configurons votre filtre pour vous montrer exactement les appartements qui correspondent",
        "ar": "مرحبًا بك في طوديرة! لنقم بإعداد الفلتر الخاص بك لنعرض لك بالضبط الشقق المناسبة",
    },
    "filter.subtitle": {
        "he": "פה אפשר לערוך הכל. שכונות, רחובות ותאריכי כניסה עורכים ב־/filter בבוט.",
        "en": "Full editing here. For specific neighborhoods/streets and move-in dates, use /filter on Telegram.",
        "ru": "Полное редактирование здесь. Для конкретных районов/улиц и дат заселения используйте /filter в Telegram.",
        "fr": "Édition complète ici. Pour des quartiers/rues spécifiques et des dates d'emménagement, utilisez /filter sur Telegram.",
        "ar": "التعديل الكامل هنا. للأحياء/الشوارع المحددة وتواريخ الانتقال، استخدم /filter في تيليجرام.",
    },
    # 2026-09-06: shown instead of filter.subtitle for a visitor with no telegram_user_id at all
    # (a Google-only account) — pointing them at "/filter on Telegram" is a dead
    # end when they have no Telegram account to run that command from. Just the first sentence of
    # the full subtitle in each language, since that sentence alone is still fully true and
    # actionable regardless of which channel got them here.
    "filter.subtitle_short": {
        "he": "פה אפשר לערוך הכל.",
        "en": "Full editing here.",
        "ru": "Полное редактирование здесь.",
        "fr": "Édition complète ici.",
        "ar": "التعديل الكامل هنا.",
    },
    "filter.cities_count_label": {
        "he": "ערים בסינון", "en": "cities in filter", "ru": "городов в фильтре",
        "fr": "villes dans le filtre", "ar": "مدن في الفلتر",
    },
    "filter.cities_label": {
        "he": "ערים", "en": "Cities", "ru": "Города", "fr": "Villes", "ar": "المدن",
    },
    "filter.cities_placeholder": {
        "he": "חפש עיר, יישוב או אזור...", "en": "Search a city, town or area...",
        "ru": "Поиск города, посёлка или района...", "fr": "Rechercher une ville, une localité ou une région...",
        "ar": "ابحث عن مدينة أو بلدة أو منطقة...",
    },
    # 2026-09-27: rewritten — checking every individual city box is NOT the same as "all cities"
    # (an exact match against this curated ~42-city whitelist vs. no city filter at all; see
    # filter_form_fields.html's own comment on the "all cities" toggle this now explains, and
    # filter_update's comment on the live-confirmed 29% of active listings this used to silently
    # exclude). The old copy ("nothing checked = all cities") described an undiscoverable
    # unchecked-grid convention that the mandatory-city onboarding rule (task #80) also made
    # unreachable during welcome; the explicit toggle replaces both problems at once.
    # 2026-10-13: every locality in Israel and every area can now be searched (see _filter_form_fields.html).
    "filter.cities_hint": {
        "he": "אפשר לחפש כל עיר, מושב, קיבוץ או יישוב, וגם אזור שלם כמו השרון או גוש עציון",
        "en": "Search any city, moshav, kibbutz or town, or a whole area such as the Sharon or Gush Etzion",
        "ru": "Можно найти любой город, мошав, кибуц или посёлок, а также целый район, например Шарон или Гуш-Эцион",
        "fr": "Cherche n'importe quelle ville, moshav, kibboutz ou localité, ou toute une région comme le Sharon ou "
        "le Goush Etzion",
        "ar": "يمكنك البحث عن أي مدينة أو موشاف أو كيبوتس أو بلدة، أو منطقة كاملة مثل الشارون أو غوش عتصيون",
    },
    "filter.cities_all_label": {
        "he": "כל הערים",
        "en": "All cities",
        "ru": "Все города",
        "fr": "Toutes les villes",
        "ar": "كل المدن",
    },
    "filter.price_min_label": {
        "he": "מחיר מינימלי", "en": "Minimum price", "ru": "Минимальная цена",
        "fr": "Prix minimum", "ar": "الحد الأدنى للسعر",
    },
    "filter.price_max_label": {
        "he": "מחיר מקסימלי", "en": "Maximum price", "ru": "Максимальная цена",
        "fr": "Prix maximum", "ar": "الحد الأقصى للسعر",
    },
    "filter.price_max_placeholder": {
        "he": "ללא הגבלה", "en": "No limit", "ru": "Без ограничений", "fr": "Sans limite", "ar": "بلا حد",
    },
    "filter.rooms_min_label": {
        "he": "חדרים מינימום", "en": "Minimum rooms", "ru": "Минимум комнат",
        "fr": "Pièces minimum", "ar": "الحد الأدنى للغرف",
    },
    "filter.rooms_max_label": {
        "he": "חדרים מקסימום", "en": "Maximum rooms", "ru": "Максимум комнат",
        "fr": "Pièces maximum", "ar": "الحد الأقصى للغرف",
    },
    "filter.location_section": {
        "he": "מיקום", "en": "Location", "ru": "Местоположение", "fr": "Emplacement", "ar": "الموقع",
    },
    "filter.price_section": {
        "he": "טווח מחירים", "en": "Price range", "ru": "Диапазон цен",
        "fr": "Fourchette de prix", "ar": "نطاق السعر",
    },
    "filter.rooms_section": {
        "he": "חדרים", "en": "Rooms", "ru": "Комнаты", "fr": "Pièces", "ar": "الغرف",
    },
    "filter.advanced_section": {
        "he": "אפשרויות מתקדמות", "en": "Advanced options", "ru": "Дополнительные параметры",
        "fr": "Options avancées", "ar": "خيارات متقدمة",
    },
    "filter.property_type_section": {
        "he": "סוג נכס", "en": "Property type", "ru": "Тип недвижимости",
        "fr": "Type de bien", "ar": "نوع العقار",
    },
    "filter.property_type_hint": {
        "he": "לא מסומן כלום = כל סוגי הנכס",
        "en": "Nothing checked = all property types",
        "ru": "Ничего не выбрано = все типы недвижимости",
        "fr": "Rien de coché = tous les types de bien",
        "ar": "لا شيء محدد = كل أنواع العقارات",
    },
    "filter.floor_section": {
        "he": "קומה", "en": "Floor", "ru": "Этаж", "fr": "Étage", "ar": "الطابق",
    },
    "filter.floor_min_label": {
        "he": "קומה מינימום", "en": "Minimum floor", "ru": "Минимальный этаж",
        "fr": "Étage minimum", "ar": "الحد الأدنى للطابق",
    },
    "filter.floor_max_label": {
        "he": "קומה מקסימום", "en": "Maximum floor", "ru": "Максимальный этаж",
        "fr": "Étage maximum", "ar": "الحد الأقصى للطابق",
    },
    "filter.ground_floor_only": {
        "he": "קומת קרקע בלבד", "en": "Ground floor only", "ru": "Только первый этаж",
        "fr": "Rez-de-chaussée uniquement", "ar": "الطابق الأرضي فقط",
    },
    "filter.amenities_section": {
        "he": "מאפיינים", "en": "Features", "ru": "Особенности", "fr": "Caractéristiques", "ar": "الميزات",
    },
    "filter.amenity_parking": {
        "he": "חניה", "en": "Parking", "ru": "Парковка", "fr": "Parking", "ar": "موقف سيارات",
    },
    "filter.amenity_elevator": {
        "he": "מעלית", "en": "Elevator", "ru": "Лифт", "fr": "Ascenseur", "ar": "مصعد",
    },
    "filter.amenity_balcony": {
        "he": "מרפסת", "en": "Balcony", "ru": "Балкон", "fr": "Balcon", "ar": "شرفة",
    },
    "filter.amenity_pets": {
        "he": "חיות מחמד מותרות", "en": "Pets allowed", "ru": "Можно с животными",
        "fr": "Animaux autorisés", "ar": "يسمح بالحيوانات الأليفة",
    },
    "filter.amenity_renovated": {
        "he": "משופצת", "en": "Renovated", "ru": "Отремонтирована",
        "fr": "Rénové", "ar": "مجدّدة",
    },
    "filter.amenity_roommates": {
        "he": "מתאימה לשותפים", "en": "Roommate friendly", "ru": "Подходит для соседей",
        "fr": "Adapté à la colocation", "ar": "مناسبة للسكن المشترك",
    },
    "filter.amenity_photos": {
        "he": "עם תמונות בלבד", "en": "With photos only", "ru": "Только с фото",
        "fr": "Avec photos uniquement", "ar": "بصور فقط",
    },
    "filter.amenity_no_brokers": {
        "he": "בלי תיווך", "en": "No brokers", "ru": "Без посредников",
        "fr": "Sans agence", "ar": "بدون وسطاء",
    },
    "filter.safe_room_label": {
        "he": "ממ״ד", "en": "Safe room", "ru": "Бомбоубежище", "fr": "Abri (mamad)", "ar": "غرفة آمنة",
    },
    "filter.furniture_label": {
        "he": "ריהוט", "en": "Furniture", "ru": "Мебель", "fr": "Ameublement", "ar": "الأثاث",
    },
    "filter.min_area_label": {
        "he": "שטח מינימלי (מ״ר)", "en": "Minimum area (sqm)", "ru": "Минимальная площадь (кв.м)",
        "fr": "Surface minimale (m²)", "ar": "المساحة الدنيا (م²)",
    },
    "filter.keywords_label": {
        "he": "מילות מפתח", "en": "Keywords", "ru": "Ключевые слова", "fr": "Mots-clés", "ar": "كلمات مفتاحية",
    },
    "filter.keywords_placeholder": {
        "he": "משופצת, נוף לים", "en": "renovated, sea view", "ru": "ремонт, вид на море",
        "fr": "rénové, vue mer", "ar": "مجددة، إطلالة بحر",
    },
    "filter.keywords_hint": {
        "he": "מופרדות בפסיקים. דירה תואמת אם התיאור שלה מכיל לפחות אחת מהן",
        "en": "Comma-separated, an apartment matches if its description contains at least one of them",
        "ru": "Через запятую, квартира подходит, если в описании есть хотя бы одно из слов",
        "fr": "Séparés par des virgules, un appartement correspond si sa description contient au moins un des mots",
        "ar": "مفصولة بفواصل, تُطابق الشقة إذا احتوى وصفها على كلمة واحدة منها على الأقل",
    },
    "filter.flexible_match_label": {
        "he": "התאמה גמישה: תראה לי גם דירות שחסר להן מאפיין אחד",
        "en": "Flexible match, also show apartments that miss just one feature",
        "ru": "Гибкое совпадение, показывать также квартиры, которым не хватает лишь одной характеристики",
        "fr": "Correspondance flexible, afficher aussi les appartements qui ne remplissent pas qu'un seul critère",
        "ar": "تطابق مرن, عرض أيضًا الشقق التي تفتقد ميزة واحدة فقط",
    },
    "filter.save_btn": {
        "he": "שמור שינויים", "en": "Save changes", "ru": "Сохранить изменения",
        "fr": "Enregistrer les modifications", "ar": "حفظ التغييرات",
    },
    # 2026-09-26: dorin.app-style onboarding, real owner request from the 33-page PDF — during the
    # first-time welcome flow ONLY (filter.html's own `welcome` context, see main.py's filter_update),
    # saving with zero cities selected is blocked with this error instead of advancing to step 2.
    # This does NOT change the general /filter or apartments-sidebar behavior at all — outside
    # onboarding, an empty cities list still means "all cities" exactly as filter.cities_hint above
    # already says; a returning user can still clear it back to that any time.
    "filter.save_btn_continue": {
        "he": "שמור והמשך", "en": "Save and continue", "ru": "Сохранить и продолжить",
        "fr": "Enregistrer et continuer", "ar": "احفظ وتابع",
    },
    "filter.cities_required_error": {
        "he": "צריך לבחור לפחות עיר אחת כדי להתחיל לקבל דירות.",
        "en": "You must choose at least one city. Pick at least one to start getting matches",
        "ru": "Нужно выбрать хотя бы один город. Выберите хотя бы один, чтобы начать получать варианты",
        "fr": "Vous devez choisir au moins une ville. Choisissez-en au moins une pour commencer à recevoir des offres",
        "ar": "يجب اختيار مدينة واحدة على الأقل. اختر مدينة واحدة على الأقل للبدء بتلقي العروض",
    },
    "onboarding.step_label": {
        "he": "שלב {n} מתוך 3", "en": "Step {n} of 3", "ru": "Шаг {n} из 3",
        "fr": "Étape {n} sur 3", "ar": "الخطوة {n} من 3",
    },
    "onboarding.step1_title": {
        "he": "הגדרת סינון", "en": "Filter setup", "ru": "Настройка фильтра",
        "fr": "Configuration du filtre", "ar": "إعداد الفلتر",
    },
    "onboarding.step2_title": {
        "he": "חיבור להתראות", "en": "Connect notifications", "ru": "Подключение уведомлений",
        "fr": "Connexion aux notifications", "ar": "ربط الإشعارات",
    },
    "onboarding.step3_title": {
        "he": "הפעלת פרימיום", "en": "Activating Premium", "ru": "Активация Premium",
        "fr": "Activation Premium", "ar": "تفعيل بريميوم",
    },
    "onboarding.notifications_title": {
        "he": "מומלץ לחבר את הבוט", "en": "We recommend connecting the bot",
        "ru": "Рекомендуем подключить бота", "fr": "Nous recommandons de connecter le bot",
        "ar": "ننصح بربط البوت",
    },
    "onboarding.notifications_body": {
        "he": "תחבר את הבוט בטלגרם ותקבל דירות חדשות בשנייה שהן עולות, לפני כולם.",
        "en": "We recommend connecting the Telegram bot so you get new apartments the second they go up, before everyone else.",
        "ru": "Рекомендуем подключить бота в Telegram, чтобы получать новые квартиры в ту же секунду, как они появляются, раньше всех.",
        "fr": "Nous recommandons de connecter le bot Telegram pour recevoir les nouveaux appartements dès leur publication, avant tout le monde.",
        "ar": "ننصح بربط بوت تيليجرام لتصلك الشقق الجديدة في نفس ثانية نشرها, قبل الجميع.",
    },
    "onboarding.notifications_cta": {
        "he": "התראות ב-Telegram", "en": "Telegram notifications", "ru": "Уведомления в Telegram",
        "fr": "Notifications Telegram", "ar": "إشعارات تيليجرام",
    },
    "onboarding.notifications_skip": {
        "he": "המשך בלי התראות לנייד", "en": "Continue without mobile notifications",
        "ru": "Продолжить без уведомлений на телефон", "fr": "Continuer sans notifications mobiles",
        "ar": "المتابعة بدون إشعارات على الجوال",
    },
    "onboarding.trial_title": {
        "he": "קיבלת 10 ימי פרימיום במתנה!", "en": "You got 10 days of Premium as a gift!",
        "ru": "Вы получили 10 дней Premium в подарок!", "fr": "Vous avez reçu 10 jours de Premium en cadeau!",
        "ar": "حصلت على 10 أيام بريميوم كهدية!",
    },
    "onboarding.trial_body": {
        "he": "גישה מלאה להכל, כולל יצירת קשר עם המפרסמים, עד {date}. בלי כרטיס אשראי ובלי חיוב אוטומטי.",
        "en": "Full access to every feature, including direct contact with posters, valid until {date}. No credit card, no auto-billing.",
        "ru": "Полный доступ ко всем функциям, включая прямую связь с авторами объявлений, действует до {date}. Без карты, без автосписания.",
        "fr": "Accès complet à toutes les fonctionnalités, y compris le contact direct avec les annonceurs, valable jusqu'au {date}. Sans carte bancaire, sans prélèvement automatique.",
        "ar": "وصول كامل لجميع الميزات، بما في ذلك التواصل المباشر مع المعلنين، صالح حتى {date}. بدون بطاقة ائتمان، بدون خصم تلقائي.",
    },
    "onboarding.trial_cta": {
        "he": "המשך לאתר", "en": "Continue to the site", "ru": "Перейти на сайт",
        "fr": "Continuer vers le site", "ar": "المتابعة إلى الموقع",
    },
    # ---------- empty states / small pages ----------
    "no_filter.body": {
        "he": "לא מצאנו חשבון או סינון. קודם צריך להגדיר סינון בבוט בטלגרם.",
        "en": "We couldn't find an account or an active filter. You need to set up a filter first, through the Telegram bot.",
        "ru": "Мы не нашли аккаунт или активный фильтр. Сначала настройте фильтр через бота в Telegram.",
        "fr": "Nous n'avons trouvé aucun compte ni filtre actif. Vous devez d'abord configurer un filtre via le bot Telegram.",
        "ar": "لم نعثر على حساب أو فلتر نشط. يجب إعداد فلتر أولاً عبر البوت على تيليجرام.",
    },
    "no_filter.cta": {
        "he": "פתח את הבוט", "en": "Open the bot", "ru": "Открыть бота", "fr": "Ouvrir le bot", "ar": "افتح البوت",
    },
    "need_uid.body": {
        "he": "כדי לראות את ה{target} שלך, צריך להיכנס עם הקישור האישי מהבוט בטלגרם.",
        "en": "To see your {target}, you need to open a personal link from the Telegram bot.",
        "ru": "Чтобы увидеть {target}, откройте персональную ссылку из бота в Telegram.",
        "fr": "Pour voir {target}, vous devez ouvrir un lien personnel depuis le bot Telegram.",
        "ar": "لرؤية {target} الخاصة بك، عليك الدخول برابط شخصي من البوت على تيليجرام.",
    },
    "need_uid.target_apartments": {
        "he": "דירות", "en": "apartments", "ru": "квартиры", "fr": "appartements", "ar": "الشقق",
    },
    "need_uid.target_liked": {
        "he": "דירות השמורות", "en": "saved apartments", "ru": "сохранённые квартиры",
        "fr": "appartements enregistrés", "ar": "الشقق المحفوظة",
    },
    "need_uid.target_filter": {
        "he": "סינון", "en": "filter", "ru": "фильтр", "fr": "filtre", "ar": "الفلتر",
    },
    "need_uid.target_upgrade": {
        "he": "שדרוג המנוי", "en": "subscription upgrade", "ru": "обновление подписки",
        "fr": "mise à niveau de l'abonnement", "ar": "ترقية الاشتراك",
    },
    "need_uid.target_account": {
        "he": "חיבור הערוצים", "en": "channel linking", "ru": "связывание каналов",
        "fr": "liaison des canaux", "ar": "ربط القنوات",
    },
    "need_uid.cta": {
        "he": "התחברות", "en": "Log in", "ru": "Войти", "fr": "Se connecter", "ar": "تسجيل الدخول",
    },
    "404.body": {
        "he": "הדף שחיפשת לא קיים, או שהקישור אליו שגוי.",
        "en": "The page you're looking for doesn't exist, or the link to it is wrong.",
        "ru": "Страница, которую вы искали, не существует, или ссылка на неё неверна.",
        "fr": "La page que vous cherchez n'existe pas, ou le lien est incorrect.",
        "ar": "الصفحة التي تبحث عنها غير موجودة، أو الرابط إليها خاطئ.",
    },
    "404.hint": {
        "he": "אולי הדירה כבר עברה דירה משלה. אפשר לחזור לדף הבית ולהמשיך משם.",
        "en": "Maybe the apartment already moved on to an apartment of its own. You can head back to the homepage and continue from there.",
        "ru": "Возможно, квартира уже переехала в свою собственную квартиру. Вернитесь на главную страницу и продолжите оттуда.",
        "fr": "Peut-être que l'appartement a déjà déménagé dans son propre appartement. Vous pouvez revenir à la page d'accueil et continuer à partir de là.",
        "ar": "ربما انتقلت الشقة إلى شقة خاصة بها. يمكنك العودة إلى الصفحة الرئيسية والمتابعة من هناك.",
    },
    "404.cta": {
        "he": "חזרה לדף הבית", "en": "Back to homepage", "ru": "На главную",
        "fr": "Retour à l'accueil", "ar": "العودة إلى الصفحة الرئيسية",
    },
    # ---------- contact page ----------
    "contact.feedback_title": {
        "he": "משוב על האתר", "en": "Feedback on the site", "ru": "Отзыв о сайте",
        "fr": "Votre avis sur le site", "ar": "رأيك في الموقع",
    },
    "contact.feedback_subtitle": {
        "he": "מה עובד טוב ומה כדאי לשפר? כל הערה עוזרת לנו.",
        "en": "What works well and what should we improve? Every note helps.",
        "ru": "Что работает хорошо, а что стоит улучшить? Нам поможет любое замечание.",
        "fr": "Qu'est-ce qui marche bien, et que faut-il améliorer? Chaque remarque nous aide.",
        "ar": "ما الذي يعمل جيدًا وما الذي يستحق التحسين؟ كل ملاحظة تساعدنا.",
    },
    "contact.feedback_placeholder": {
        "he": "מה אהבת? מה חסר או לא עבד?",
        "en": "What did you like? What was missing or didn't work?",
        "ru": "Что понравилось? Чего не хватило или что не сработало?",
        "fr": "Qu'avez-vous aimé? Qu'est-ce qui manquait ou n'a pas marché?",
        "ar": "ما الذي أعجبك؟ ما الذي كان ناقصًا أو لم يعمل؟",
    },
    "feedback.bubble": {
        "he": "משוב על האתר", "en": "Feedback", "ru": "Отзыв о сайте", "fr": "Votre avis", "ar": "رأيك في الموقع",
    },
    "contact.title": {
        "he": "צור קשר", "en": "Contact us", "ru": "Связаться с нами",
        "fr": "Nous contacter", "ar": "تواصل معنا",
    },
    "contact.subtitle": {
        "he": "יש לך שאלה, בעיה או רעיון? תכתוב, נחזור אליך מהר.",
        "en": "Have a question, a problem, or an idea? We'd love to hear from you, we'll get back to you soon.",
        "ru": "Есть вопрос, проблема или идея? Будем рады услышать вас, скоро ответим.",
        "fr": "Une question, un problème ou une idée? N'hésitez pas à nous écrire, nous vous répondrons rapidement.",
        "ar": "هل لديك سؤال أو مشكلة أو فكرة؟ يسعدنا أن نسمع منك, سنرد عليك قريبًا.",
    },
    "contact.name_label": {
        "he": "שם (לא חובה)", "en": "Name (optional)", "ru": "Имя (необязательно)",
        "fr": "Nom (facultatif)", "ar": "الاسم (اختياري)",
    },
    "contact.email_label": {
        "he": "אימייל (לא חובה)", "en": "Email (optional)", "ru": "Эл. почта (необязательно)",
        "fr": "E-mail (facultatif)", "ar": "البريد الإلكتروني (اختياري)",
    },
    "contact.message_label": {
        "he": "ההודעה שלך", "en": "Your message", "ru": "Ваше сообщение",
        "fr": "Votre message", "ar": "رسالتك",
    },
    "contact.message_placeholder": {
        "he": "תכתוב פה מה שבא לך...",
        "en": "Write what you'd like to tell us here...",
        "ru": "Напишите здесь то, что хотите нам сообщить...",
        "fr": "Écrivez ici ce que vous souhaitez nous dire...",
        "ar": "اكتب هنا ما تود إخبارنا به...",
    },
    "contact.submit_btn": {
        "he": "שלח הודעה", "en": "Send message", "ru": "Отправить сообщение",
        "fr": "Envoyer le message", "ar": "إرسال الرسالة",
    },
    "contact.error_empty": {
        "he": "ההודעה לא יכולה להיות ריקה.",
        "en": "The message can't be empty.",
        "ru": "Сообщение не может быть пустым.",
        "fr": "Le message ne peut pas être vide.",
        "ar": "لا يمكن أن تكون الرسالة فارغة.",
    },
    "contact.error_consent": {
        "he": "יש לאשר את מדיניות הפרטיות כדי לשלוח את הפנייה.",
        "en": "Please agree to the privacy policy to send your message.",
        "ru": "Чтобы отправить сообщение, необходимо согласиться с политикой конфиденциальности.",
        "fr": "Veuillez accepter la politique de confidentialité pour envoyer votre message.",
        "ar": "يرجى الموافقة على سياسة الخصوصية لإرسال رسالتك.",
    },
    # 2026-09-25: added when /contact became a React island submitting via fetch (POST
    # /api/contact) instead of a native form POST — a network failure or unexpected server error
    # is now a real, distinct client-side state the old full-page-reload form never had to render
    # its own message for (the browser's own error page handled it before).
    "contact.error_generic": {
        "he": "משהו השתבש. נסה שוב עוד רגע.",
        "en": "Something went wrong. Please try again in a moment.",
        "ru": "Что-то пошло не так. Попробуйте ещё раз через минуту.",
        "fr": "Une erreur s'est produite. Veuillez réessayer dans un instant.",
        "ar": "حدث خطأ ما. يرجى المحاولة مرة أخرى بعد قليل.",
    },
    "contact.consent_prefix": {
        "he": "קראתי ואני מסכים ל", "en": "I have read and agree to the",
        "ru": "Я прочитал(а) и согласен(на) с", "fr": "J'ai lu et j'accepte la",
        "ar": "لقد قرأت وأوافق على",
    },
    "contact.success_title": {
        "he": "ההודעה נשלחה!",
        "en": "Message sent!",
        "ru": "Сообщение отправлено!",
        "fr": "Message envoyé!",
        "ar": "تم إرسال الرسالة!",
    },
    "contact.success_body": {
        "he": "תודה שכתבת! נחזור אליך הכי מהר שאפשר.",
        "en": "Thanks for reaching out, we'll get back to you as soon as possible.",
        "ru": "Спасибо, что обратились к нам, мы ответим вам как можно скорее.",
        "fr": "Merci de nous avoir contactés, nous vous répondrons dès que possible.",
        "ar": "شكرًا لتواصلك معنا, سنرد عليك في أقرب وقت ممكن.",
    },
    "contact.other_ways_title": {
        "he": "דרכים נוספות ליצור קשר", "en": "Other ways to reach us",
        "ru": "Другие способы связи", "fr": "Autres moyens de nous contacter",
        "ar": "طرق أخرى للتواصل",
    },
    "contact.telegram_way": {
        "he": "טלגרם: תכתוב ישר לבוט", "en": "Telegram, message the bot directly",
        "ru": "Telegram, напишите боту напрямую", "fr": "Telegram, écrivez directement au bot",
        "ar": "تيليجرام, راسل البوت مباشرة",
    },
    # ---------- legal pages ----------
    # Terms/Privacy only have full He+En copy (see terms.html/privacy.html) — legal text is exactly
    # the kind of content where a rushed, unreviewed machine translation is riskier than admitting
    # a gap. This banner tells a ru/fr/ar viewer honestly that they're seeing the English version.
    "legal.non_native_notice": {
        "he": "",
        "en": "",
        "ru": "Этот документ пока доступен только на иврите и английском. Ниже показана английская версия.",
        "fr": "Ce document n'est pour l'instant disponible qu'en hébreu et en anglais. La version anglaise est affichée ci-dessous.",
        "ar": "هذا المستند متاح حاليًا بالعبرية والإنجليزية فقط. تُعرض أدناه النسخة الإنجليزية.",
    },
    # ---------- about page (2026-09-25 React island) ----------
    # he/en only, matching the page's own pre-existing (pre-React) behavior — the plain Jinja2
    # template this content moved out of never had ru/fr/ar translations either, showing English +
    # legal.non_native_notice above for those readers instead. The React component keeps that same
    # real-content-only behavior rather than fabricating three new translations here.
    "about.h1": {"he": "אודות טודירה", "en": "About Todira"},
    "about.body_intro": {
        "he": "טודירה זה בוט בטלגרם ואתר שמחפשים לך דירה. הבוט מחפש בשבילך שוב ושוב לאורך היום, ושולח לך רק מודעות שמתאימות לסינון שלך: עיר, מחיר, חדרים, סוג נכס ועוד.",
        "en": "Todira is a Telegram bot and website that look for an apartment for you. The bot searches for you again and again throughout the day and sends you only the listings that match your filter: city, price, rooms, property type and more.",
    },
    "about.body_disclaimer": {
        "he": "חשוב לדעת: אנחנו לא משרד תיווך, אין לנו נכסים ואנחנו לא צד לעסקה. אנחנו כלי שחוסך לך לרענן אתרים כל היום.",
        "en": "The service is not a real-estate brokerage, does not own any properties, and is not a party to any rental transaction, it is a technology tool built to save apartment seekers the need to repeatedly refresh listing sites themselves.",
    },
    "about.links_p1": {"he": "לפרטים נוספים ניתן לעיין ב", "en": "For more details, see the "},
    "about.links_p2": {"he": " וב", "en": " and the "},
    "about.links_p3": {"he": ", או לפנות אלינו דרך ", "en": ", or reach out via the "},
    "about.links_p4": {"he": ".", "en": "."},
    # Deliberately separate from footer.terms/footer.privacy: those carry different Hebrew
    # wording (no definite article) and real ru/fr/ar translations, neither of which matches
    # this page's own original text — its non-Hebrew branch always showed literal English here,
    # never localized to ru/fr/ar.
    "about.link_terms": {"he": "תנאי השימוש", "en": "Terms of Use"},
    "about.link_privacy": {"he": "מדיניות הפרטיות", "en": "Privacy Policy"},
    "about.link_contact_page": {"he": "עמוד יצירת הקשר", "en": "contact page"},
    # ---------- accessibility page (2026-09-25 React island) ----------
    # he/en only, matching the page's own pre-existing (pre-React) behavior — same reasoning as
    # about.* above (see that section's own comment).
    "accessibility.h1": {"he": "הצהרת נגישות", "en": "Accessibility Statement"},
    "accessibility.updated": {"he": "עודכן לאחרונה: ספטמבר 2026", "en": "Last updated: September 2026"},
    "accessibility.s1_title": {"he": "1. המחויבות שלנו", "en": "1. Our commitment"},
    "accessibility.s1_body": {
        "he": "טודירה פועל להנגיש את האתר לאנשים עם מוגבלות, ברוח תקנות שוויון זכויות לאנשים עם מוגבלות (התאמות נגישות לשירות), התשע\"ג-2013, ובהתאם לתקן הישראלי (ת\"י 5568) המבוסס על הנחיות WCAG 2.0 ברמה AA. זהו תהליך מתמשך. האתר עדיין לא עבר בדיקת התאמה מלאה על ידי גורם מוסמך חיצוני.",
        "en": "Todira works to make this website accessible to people with disabilities, in the spirit of Israel's Equal Rights for Persons with Disabilities (Service Accessibility Adjustments) Regulations, 2013, and the Israeli standard (IS 5568) based on WCAG 2.0 Level AA guidelines. This is an ongoing effort, the site has not yet undergone a full conformance audit by an external accredited party.",
    },
    "accessibility.s2_title": {"he": "2. מה קיים באתר כיום", "en": "2. What's available today"},
    "accessibility.s2_item1": {
        "he": "כפתור נגישות צף (בפינת המסך) עם כלים להתאמה אישית: הגדלת/הקטנת טקסט, ניגודיות גבוהה, גווני אפור, הדגשת קישורים, הגדלת אזורי לחיצה, פס קריאה, עצירת אנימציות, והקראת תוכן העמוד בקול.",
        "en": "A floating accessibility button (in the corner of the screen) with tools for: increasing/decreasing text size, high contrast, grayscale, link highlighting, larger click targets, a reading guide, stopping animations, and reading the page's content aloud.",
    },
    "accessibility.s2_item2": {
        "he": 'ניווט מלא במקלדת, כולל קישור "דלג לתוכן" בתחילת כל עמוד.',
        "en": 'Full keyboard navigation, including a "skip to content" link at the top of every page.',
    },
    "accessibility.s2_item3": {
        "he": "תיאורי טקסט (aria-label) לרכיבי ניווט עיקריים, ומצב פוקוס גלוי לכל רכיב אינטראקטיבי.",
        "en": "Text descriptions (aria-label) for key navigation elements, and a visible focus state on every interactive element.",
    },
    "accessibility.s2_item4": {
        "he": 'תמיכה בהעדפת "הפחתת תנועה" של מערכת ההפעלה/הדפדפן.',
        "en": 'Support for the operating system/browser\'s "reduce motion" preference.',
    },
    "accessibility.s3_title": {"he": "3. מגבלות ידועות", "en": "3. Known limitations"},
    "accessibility.s3_body": {
        "he": "תוכן המודעות עצמו (תמונות, טקסט תיאור) מגיע ממקורות חיצוניים (אתרי נדל\"ן ולוחות מודעות שונים) שאינם בשליטת טודירה, וייתכן שאינו נגיש במלואו. אנו פועלים לשפר את הנגישות של שאר האתר באופן שוטף.",
        "en": "Listing content itself (photos, description text) comes from external sources (various real-estate sites and listing boards) not controlled by Todira, and may not be fully accessible. We continue to work on improving the accessibility of the rest of the site.",
    },
    "accessibility.s4_title": {
        "he": "4. רכז נגישות ופנייה בנושא נגישות",
        "en": "4. Accessibility coordinator and reporting an issue",
    },
    # split into pre/post around a real mailto: link (Accessibility.jsx) — same clickable-email
    # fix as footer.business_info_pre above.
    "accessibility.s4_body_pre": {
        "he": "נתקלתם בבעיית נגישות באתר? נשמח שתדווחו לנו כדי שנוכל לטפל בכך. רכז הנגישות של טודירה הוא אמיר טולדנו. ניתן לפנות ישירות באימייל ",
        "en": "Found an accessibility problem on the site? We'd appreciate a report so we can address it. Todira's accessibility coordinator is Amir Toledano, you can reach out directly by email at ",
    },
    "accessibility.s4_body_post": {
        "he": " או דרך הבוט בטלגרם.",
        "en": " or via the Telegram bot.",
    },
    # ---------- privacy page (2026-09-25 React island) ----------
    # he/en only, matching the page's own pre-existing (pre-React) behavior — same reasoning as
    # about.*/accessibility.* above. Text that was inline-marked-up (<strong>, <a>) in the original
    # template is split into separate keys around the markup (pre/strong/post, or label/body) —
    # matching this file's own no-`| safe`-anywhere convention (see upgrade.terms_agree_prefix's
    # own comment) — so the React component supplies the actual <strong>/<a> element, not a raw
    # HTML string. Items with no inline markup stay as one key, same as accessibility.* above.
    "privacy.h1": {"he": "מדיניות פרטיות", "en": "Privacy Policy"},
    "privacy.updated": {
        "he": "עודכן לאחרונה: אוקטובר 2026",
        "en": "Last updated: October 2026",
    },
    "privacy.s1_title": {"he": "1. אילו נתונים נאספים", "en": "1. What data is collected"},
    "privacy.s1_item1": {
        "he": "מזהה המשתמש בטלגרם (Telegram user ID) ושם המשתמש כפי שמופיע בטלגרם, אם נרשמת דרך הבוט.",
        "en": "Your Telegram user ID and the username shown by Telegram, if you registered via the bot.",
    },
    "privacy.s1_item3": {
        "he": "כתובת האימייל ושם התצוגה שלך מחשבון Google, אם התחברת עם Google.",
        "en": "Your email address and display name from your Google account, if you signed in with Google.",
    },
    "privacy.s1_item4": {
        "he": "הסינון שהגדרת: עיר, טווח מחיר, מספר חדרים, סוג נכס ושאר העדפות חיפוש.",
        "en": "The filter you set up, city, price range, number of rooms, property type, and other search preferences.",
    },
    "privacy.s1_item5": {
        "he": "הודעות טקסט חופשי ששלחת לבוט (לצורך בניית פרופיל חיפוש בעזרת בינה מלאכותית).",
        "en": "Free-text messages you send the bot (used to build a search profile via AI).",
    },
    "privacy.s1_item6": {
        "he": 'דירות שסימנת כ"אהבתי"/"הסתרתי", וסטטיסטיקת התראות שנשלחו אליך.',
        "en": 'Apartments you marked "liked"/"hidden," and statistics on alerts sent to you.',
    },
    "privacy.s1_item7_pre": {
        "he": "פרטי מנוי ותשלום: תוכנית שנרכשה, סכום, מועד תשלום, סטטוס העסקה, ומזהה עסקה אצל ספק הסליקה. ",
        "en": "Subscription and payment details: plan purchased, amount, payment date, transaction status, and a transaction ID from our payment processor. ",
    },
    "privacy.s1_item7_strong": {
        "he": "אנו לא רואים ולא שומרים את פרטי כרטיס האשראי שלך",
        "en": "We never see or store your credit card details",
    },
    "privacy.s1_item7_post": {
        "he": ": התשלום עצמו מתבצע ישירות מול ספק סליקה חיצוני (ר' סעיף 3).",
        "en": ": payment itself is made directly with an external payment processor (see section 3).",
    },
    "privacy.s1_item8": {
        "he": "אם פנית אלינו דרך טופס יצירת הקשר באתר: שם, אימייל ותוכן הפנייה שהזנת.",
        "en": "If you contacted us via the site's contact form, the name, email, and message content you entered.",
    },
    "privacy.s2_title": {"he": "2. איך המידע משמש", "en": "2. How the data is used"},
    "privacy.s2_body": {
        "he": "המידע משמש להפעלת השירות עצמו: התאמת דירות לסינון שלך, שליחת התראות והודעות שירות (כגון תזכורת לפני סיום תקופת הגישה), עיבוד תשלומים, שמירת ההעדפות שלך בין ביקורים, ואבטחה ומניעת שימוש לרעה. מסירת המידע נעשית מרצונך, אך בלי חלקו (למשל מזהה הערוץ שדרכו נשלחות ההתראות) לא נוכל לספק את השירות. המידע אינו נמכר ואינו מועבר לצדדים שלישיים לצורכי שיווק. המודעות עצמן נאספות ממקורות פומביים ברשת, ואיננו שומרים את מספר הטלפון של המפרסם.",
        "en": "Data is used to operate the service itself: matching apartments to your filter, sending alerts and service messages (such as a reminder before your access period ends), processing payments, remembering your preferences between visits, and security and abuse prevention. Providing the data is voluntary, but without part of it (for example the channel identifier through which alerts are sent) we cannot provide the service. Data is not sold and is not shared with third parties for marketing purposes. The listings themselves are collected from public sources on the web, and we do not store the advertiser's phone number.",
    },
    "privacy.s3_title": {"he": "3. ספקים חיצוניים", "en": "3. Third-party providers"},
    "privacy.s3_intro": {
        "he": "לצורך הפעלת השירות נעשה שימוש בספקים חיצוניים הבאים, שכל אחד מהם מעבד את הנתונים הרלוונטיים לפעולתו בלבד, בכפוף למדיניות הפרטיות שלו. חלק מהספקים ממוקמים מחוץ לישראל, ולכן מידע עשוי להיות מעובד ומאוחסן מחוץ לישראל:",
        "en": "To operate the service we use the following external providers, each of which processes only the data relevant to its function, subject to its own privacy policy. Some providers are located outside Israel, so data may be processed and stored outside Israel:",
    },
    "privacy.s3_item1_label": {"he": "Telegram", "en": "Telegram"},
    "privacy.s3_item1_body": {
        "he": ": שליחת וקבלת הודעות הבוט.",
        "en": ": sending/receiving bot messages.",
    },
    "privacy.s3_item3_label": {"he": "Google", "en": "Google"},
    "privacy.s3_item3_body": {
        "he": ": התחברות עם חשבון Google (Sign in with Google), ו-Gemini API לפענוח הודעות טקסט חופשי ולחילוץ פרטים ממודעות. הודעות הטקסט החופשי שאתה שולח לבוט מועברות ל-Gemini לצורך כך.",
        "en": ": signing in with a Google account (Sign in with Google), and the Gemini API to interpret free-text messages and extract details from listings. The free-text messages you send to the bot are passed to Gemini for this purpose.",
    },
    "privacy.s3_item4_label": {"he": "Takbull (דרך UPAY)", "en": "Takbull (via UPAY)"},
    "privacy.s3_item4_body": {
        "he": ": עיבוד תשלומים עבור מנוי בתשלום. פרטי האשראי עצמם מוזנים ישירות בדף הסליקה המאובטח של הספק ולעולם אינם עוברים דרך שרתי טודירה.",
        "en": ": payment processing for paid subscriptions. Your card details are entered directly on the processor's own secure checkout page and never pass through Todira's servers.",
    },
    "privacy.s3_item5_label": {
        "he": "ZenRows, Bright Data ו-Amazon Web Services (AWS)",
        "en": "ZenRows, Bright Data and Amazon Web Services (AWS)",
    },
    "privacy.s3_item5_body": {
        "he": ": תשתית טכנית: איסוף מודעות דירות ממקורות חיצוניים ברשת (ZenRows ו-Bright Data, שאינם מקבלים מידע אישי עליך), ואחסון ענן שבו רצים השירות ומסד הנתונים (AWS).",
        "en": ": technical infrastructure: collecting apartment listings from external sources on the web (ZenRows and Bright Data, which receive no personal information about you), and the cloud hosting on which the service and its database run (AWS).",
    },
    "privacy.s4_title": {"he": "4. עוגיות (Cookies)", "en": "4. Cookies"},
    "privacy.s4_body": {
        "he": "האתר משתמש בעוגיות פונקציונליות בלבד: עוגיית התחברות (session) הנחוצה כדי לזהות אותך כמחובר בין דפים, ועוגיית שמירת שפת התצוגה שבחרת. בנוסף נשמרות בדפדפן העדפות התצוגה שבחרת (כגון מצב כהה והגדרות נגישות). כל אלה טכניות בלבד. אין עוגיות פרסום, מעקב אחר גלישה או פרסונליזציה שיווקית. שרתי האתר רושמים נתונים טכניים של הגלישה (כגון כתובת IP וסוג הדפדפן) לצורכי אבטחה ותפעול.",
        "en": "The website uses functional cookies only: a login (session) cookie needed to recognize you as signed in between pages, and a cookie that remembers the display language you chose. Display preferences you choose (such as dark mode and accessibility settings) are also kept in your browser. All of these are technical only, not advertising cookies, browsing tracking or marketing personalization. The website's servers record technical browsing data (such as IP address and browser type) for security and operational purposes.",
    },
    "privacy.s5_title": {"he": "5. שמירת מידע ומחיקתו", "en": "5. Data retention and deletion"},
    "privacy.s5_pre": {
        "he": "ניתן לבקש בכל עת מחיקה מלאה של המידע השמור עליך על ידי פנייה דרך הבוט בטלגרם או דרך ",
        "en": "You can request full deletion of your stored data at any time by contacting us through the Telegram bot or the ",
    },
    "privacy.s5_post": {
        "he": ". נטפל בבקשה בתוך זמן סביר ולכל היותר 30 ימים. המידע נשמר כל עוד החשבון פעיל ולצורך מתן השירות. שים לב: רשומות תשלום נשמרות לתקופה נוספת (בדרך כלל עד 7 שנים) בהתאם לדרישות חשבונאיות/מיסוי כדין, גם לאחר בקשת מחיקה.",
        "en": ". We will handle the request within a reasonable time and in any case within 30 days. Data is kept as long as the account is active and as needed to provide the service. Note: payment records are retained for an additional period (usually up to 7 years) as required by applicable accounting/tax law, even after a deletion request.",
    },
    "privacy.s6_title": {"he": "6. זכויותיך", "en": "6. Your rights"},
    "privacy.s6_body": {
        "he": "בהתאם לחוק הגנת הפרטיות, התשמ\"א-1981, זכותך לעיין במידע שנאסף עליך, לבקש את תיקונו או מחיקתו ולהתנגד לעיבודו. לשם מימוש הזכויות ניתן לפנות אלינו בדרכים המפורטות בסעיף 10. אם אינך מרוצה מהטיפול בפנייתך, ניתן לפנות גם לרשות להגנת הפרטיות.",
        "en": "Under Israel's Protection of Privacy Law, 5741-1981, you have the right to review the data collected about you, to request its correction or deletion, and to object to its processing. To exercise these rights, contact us as set out in section 10. If you are not satisfied with how your request was handled, you may also contact the Privacy Protection Authority.",
    },
    "privacy.s7_title": {"he": "7. אבטחת מידע", "en": "7. Data security"},
    "privacy.s7_body": {
        "he": "אנו נוקטים אמצעים סבירים להגנה על המידע, ובהם חיבור מוצפן (HTTPS), קישורי התחברות חתומים והגבלת הגישה למידע לגורמים מורשים בלבד, אך אין באפשרותנו להבטיח הגנה מוחלטת מפני כל גישה בלתי מורשית. אם יתגלה אירוע אבטחה מהותי הפוגע במידע האישי שלך, נפעל בהתאם לדין.",
        "en": "We take reasonable measures to protect the data, including an encrypted connection (HTTPS), signed login links and restricting access to the data to authorized parties only, but we cannot guarantee absolute protection against any unauthorized access. If a material security incident affecting your personal data is discovered, we will act as the law requires.",
    },
    "privacy.s8_title": {"he": "8. קטינים", "en": "8. Minors"},
    "privacy.s8_body": {
        "he": "השירות אינו מיועד לשימוש על ידי קטינים ללא הסכמת הורה או אפוטרופוס.",
        "en": "The service is not intended for use by minors without the consent of a parent or guardian.",
    },
    "privacy.s9_title": {"he": "9. שינויים במדיניות", "en": "9. Changes to this policy"},
    "privacy.s9_body": {
        "he": "מדיניות זו עשויה להתעדכן מעת לעת. שינוי מהותי יפורסם בעמוד זה, והמשך השימוש בשירות לאחר עדכון מהווה הסכמה למדיניות המעודכנת.",
        "en": "This policy may be updated from time to time. A material change will be published on this page, and continued use of the service after an update constitutes agreement to the updated policy.",
    },
    "privacy.s10_title": {"he": "10. יצירת קשר", "en": "10. Contact"},
    # split into pre/post around a real mailto: link (Privacy.jsx) — same clickable-email fix as
    # footer.business_info_pre above.
    "privacy.s10_body_pre": {
        "he": "טודירה מופעל על ידי אמיר טולדנו, עוסק פטור מס׳ 211530563. לשאלות בנוגע לפרטיות, או לבקשת מחיקת מידע, ניתן לפנות באימייל ",
        "en": "Todira is operated by Amir Toledano, exempt dealer (עוסק פטור) no. 211530563. For questions about privacy, or to request data deletion, please email ",
    },
    "privacy.s10_body_post": {
        "he": " או דרך הבוט בטלגרם.",
        "en": " or reach out via the Telegram bot.",
    },
    # ---------- terms page (2026-09-25, fifth page moved into a React island — he/en only, same
    # reasoning as about.*/accessibility.*/privacy.* above) ----------
    "terms.h1": {"he": "תנאי שימוש", "en": "Terms of Use"},
    "terms.updated": {
        "he": "עודכן לאחרונה: אוקטובר 2026",
        "en": "Last updated: October 2026",
    },
    "terms.s1_title": {"he": "1. מה זה טודירה", "en": "1. What Todira is"},
    "terms.s1_body": {
        "he": "טודירה הוא שירות אישי (בוט טלגרם ואתר נלווה) שסורק אוטומטית מודעות דירות ממקורות חיצוניים ברשת (אתרי נדל\"ן ולוחות מודעות שונים), ומתריע למשתמש בטלגרם כאשר מתפרסמת מודעה שתואמת לסינון שהגדיר. האתר מאפשר לצפות במודעות, לערוך את הסינון ולנהל את החשבון. לכל משתמש חדש ניתנת תקופת ניסיון חינמית בת 10 ימים. לאחריה, המשך השימוש כרוך בתשלום חד-פעמי לתקופת גישה לבחירתך: ₪19.90 לשבוע (7 ימים), ₪29.90 לשבועיים (14 ימים) או ₪49.90 לחודש (30 ימים), כמפורט בעמוד השדרוג באתר. אין חידוש אוטומטי ולא יבוצעו חיובים נוספים; נשלח תזכורת לפני סיום תקופת הגישה.",
        "en": "Todira is a personal service (a Telegram bot and a companion website) that automatically scans apartment listings from external sources on the web (real-estate sites and listing boards) and alerts the user on Telegram when a listing matching their filter is published. The website lets you view listings, edit your filter and manage your account. Every new user gets a free 10-day trial. After it, continued use requires a one-time payment for an access period of your choice: NIS 19.90 for a week (7 days), NIS 29.90 for two weeks (14 days) or NIS 49.90 for a month (30 days), as detailed on the website's upgrade page. There is no automatic renewal and no further charges will be made; we will send a reminder before your access period ends.",
    },
    "terms.s2_title": {"he": "2. אין אחריות על תוכן המודעות", "en": "2. No warranty on listing content"},
    "terms.s2_body": {
        "he": "כל המודעות המוצגות בטודירה נאספות ממקורות חיצוניים שאינם בשליטת טודירה. טודירה אינו מפרסם, יוצר, מאמת או ערב לדיוק, לעדכניות או לזמינות של אף מודעה. מחיר, תמונות, זמינות, תיאור הנכס וכל פרט אחר עשויים להיות שגויים, מיושנים או שהנכס כבר הושכר/נמכר. יש לבדוק כל מודעה מול המקור המקורי ומול המפרסם לפני כל החלטה. המודעות מוצגות לנוחות המשתמש תוך הפניה למקור; פרטי הקשר של המפרסם (לרבות מספר טלפון) נמצאים באתר המקור בלבד, ואינם נשמרים אצלנו. מפרסם המבקש להסיר מודעה מהשירות מוזמן לפנות אלינו (סעיף 12) ונטפל בבקשה בהקדם.",
        "en": "All listings shown in Todira are collected from external sources outside Todira's control. Todira does not publish, create, verify or vouch for the accuracy, freshness or availability of any listing, price, photos, availability, the property description and any other detail may be wrong, outdated, or the property may already be rented/sold. Check every listing with the original source and the advertiser before any decision. Listings are shown for the user's convenience with a reference to the source; the advertiser's contact details (including a phone number) are found on the source site only and are not stored by us. An advertiser who wants a listing removed from the service is welcome to contact us (section 12) and we will handle the request promptly.",
    },
    "terms.s3_title": {"he": "3. טודירה אינו צד לעסקה", "en": "3. Todira is not a party to any transaction"},
    "terms.s3_body": {
        "he": "טודירה אינו מתווך, משכיר, בעל נכס או צד לכל עסקת שכירות/מכירה. כל תקשורת, משא ומתן והתקשרות מול מפרסם, בעל נכס או מתווך נעשית באחריותו הבלעדית של המשתמש, וטודירה אינו אחראי לתוצאותיה.",
        "en": "Todira is not a broker, landlord, property owner, or a party to any rental or sale transaction. All communication, negotiation, and dealings with an advertiser, property owner, or broker are the user's sole responsibility, and Todira bears no responsibility for their outcome.",
    },
    "terms.s4_title": {"he": "4. שימוש בבינה מלאכותית", "en": "4. Use of AI"},
    "terms.s4_body": {
        "he": "השירות משתמש במודל שפה (Gemini מבית Google) כדי לפרש הודעות טקסט חופשי ולבנות מהן פרופיל חיפוש, וכדי לעזור לחלץ פרטים ממודעות. הפירוש והחילוץ עלולים לפעמים להיות שגויים. ניתן תמיד לתקן את הסינון ידנית דרך הבוט (/filter) או דרך האתר, ויש לאמת כל פרט מול המודעה המקורית.",
        "en": "The service uses a language model (Google's Gemini) to interpret free-text messages and build a search profile from them, and to help extract details from listings. The interpretation and extraction may sometimes be wrong, you can always correct the filter manually through the bot (/filter) or the website, and every detail should be verified against the original listing.",
    },
    "terms.s5_title": {"he": "5. הגבלת אחריות", "en": "5. Limitation of liability"},
    "terms.s5_body": {
        "he": "השירות ניתן \"כמות שהוא\" (AS IS), ללא כל התחייבות לזמינות רציפה, נכונות המידע או התאמה למטרה מסוימת. ככל שמותר על פי דין, טודירה ומפעיליו לא יישאו באחריות לכל נזק, ישיר או עקיף, שייגרם משימוש בשירות, מהסתמכות על מידע בו, מתקלה טכנית או מהפסקת השירות.",
        "en": "The service is provided \"AS IS,\" with no commitment to continuous availability, accuracy of information, or fitness for a particular purpose. To the extent permitted by law, Todira and its operator shall not be liable for any damage, direct or indirect, arising from use of the service, reliance on information in it, technical failure, or discontinuation of the service.",
    },
    "terms.s6_title": {"he": "6. שינויים בשירות", "en": "6. Changes to the service"},
    "terms.s6_body": {
        "he": "טודירה רשאי לשנות, להשעות או להפסיק את השירות (כולו או חלקו), בכל עת וללא הודעה מוקדמת. שינויים מהותיים בתנאים אלה יפורסמו בעמוד זה. ייתכנו גם הפסקות או שינויים בשירות עקב שינויים אצל מקורות המודעות או אצל ספקים חיצוניים, שאינם בשליטתנו. ככל שהופסק השירות מצדנו לפני תום תקופת גישה ששולמה, נבחן בתום לב החזר יחסי.",
        "en": "Todira may change, suspend or discontinue the service (in whole or in part) at any time without prior notice. Material changes to these terms will be published on this page. The service may also be interrupted or changed because of changes at the listing sources or at external providers, which are outside our control. If we discontinue the service before a paid access period ends, we will consider a pro-rata refund in good faith.",
    },
    "terms.s7_title": {"he": "7. קניין רוחני", "en": "7. Intellectual property"},
    "terms.s7_body": {
        "he": "עיצוב האתר, המיתוג והקוד של טודירה הם קניינו של מפעיל השירות. תוכן המודעות עצמו שייך למקורות המקוריים שממנו נאסף. אין להעתיק, לסרוק (scraping), לאסוף באופן אוטומטי, למכור מחדש או להפיץ את תוכן השירות או את הנתונים בו, ואין לנסות לעקוף את מנגנוני הגישה או האבטחה שלו. הגישה לשירות אישית ואינה ניתנת להעברה לאחר. מפעיל השירות רשאי לחסום גישה למשתמש שהפר הוראות אלה.",
        "en": "The website's design, branding, and code belong to the service's operator. Listing content itself belongs to the original sources it was collected from. You may not copy, scrape, automatically harvest, resell or distribute the service's content or data, or try to bypass its access or security mechanisms. Access to the service is personal and not transferable. The operator may block access for a user who violates these provisions.",
    },
    "terms.s8_title": {"he": "8. דין וסמכות שיפוט", "en": "8. Governing law and jurisdiction"},
    "terms.s8_body": {
        "he": "תנאים אלה כפופים לדיני מדינת ישראל, וכל מחלוקת תידון בבתי המשפט המוסמכים בישראל בלבד.",
        "en": "These terms are governed by the laws of the State of Israel, and any dispute shall be resolved exclusively in the competent courts of Israel.",
    },
    "terms.s9_title": {"he": "9. אספקת השירות", "en": "9. Service delivery"},
    "terms.s9_body": {
        "he": "השירות ניתן במלואו באופן דיגיטלי, ואינו כרוך במשלוח פיזי של מוצר כלשהו. עם אישור התשלום עבור תקופת גישה, הגישה מופעלת באופן אוטומטי ומיידי (בדרך כלל תוך דקות ספורות ממועד אישור העסקה), דרך הבוט בטלגרם והאתר, ללא צורך בפעולה נוספת מצד המשתמש. אם הגישה לא נפתחה תוך זמן סביר, יש לפנות אלינו (סעיף 12).",
        "en": "The service is provided entirely digitally and does not involve physical shipping of any product. Once payment for an access period is confirmed, access is activated automatically and immediately (typically within a few minutes of the transaction confirmation) through the Telegram bot and the website, with no further action required from the user. If access has not opened within a reasonable time, please contact us (section 12).",
    },
    "terms.s10_title": {"he": "10. ביטול עסקה והחזרים", "en": "10. Cancellation and refunds"},
    # 2026-10-13 (owner decision): a cancellation within the legal 14 days charges the days elapsed since the purchase
    # (used or not) at the price of the shortest pass that covers them (not a pro-rata share of the longer pass), plus the legal 5% / NIS 100 fee.
    "terms.s10_body": {
        "he": "מדובר בשירות דיגיטלי הניתן באופן מיידי ואוטומטי מרגע אישור התשלום. לכל משתמש ניתנת תקופת ניסיון חינמית בת 10 ימים לפני כל תשלום (ר' סעיף 1). הגישה נמכרת בתשלום חד-פעמי לתקופה שנבחרה (7, 14 או 30 ימים), ללא חידוש אוטומטי, ולכן אין מנוי שצריך לבטל. בהתאם לחוק הגנת הצרכן, התשמ\"א-1981, ניתן לבטל עסקה שנעשתה מרחוק בתוך 14 ימים ממועד ביצוע העסקה (או ממועד קבלת האישור בכתב, לפי המאוחר), בכפתור הביטול באזור האישי באתר, או בהודעה אלינו דרך עמוד יצירת הקשר או הבוט בטלגרם. הגישה לשירות מסתיימת במועד הודעת הביטול. מאחר שהגישה לשירות זמינה במלואה מרגע התשלום, בין אם נעשה בה שימוש ובין אם לא, מהסכום ששולם יקוזזו מחיר החבילה הקצרה ביותר שמכסה את הימים שחלפו ממועד הרכישה (יום שהחל נחשב יום מלא), ודמי ביטול בשיעור של 5% ממחיר העסקה או 100 ש\"ח, לפי הנמוך מביניהם. היתרה, אם נותרה, תוחזר לאמצעי התשלום המקורי בתוך 14 ימים ממועד הודעת הביטול. לדוגמה: מי שרכש גישה לחודש (49.90 ש\"ח) וביטל לאחר 10 ימים, יקוזזו מחיר גישה לשבועיים (29.90 ש\"ח) ודמי ביטול (2.50 ש\"ח), והוא יקבל החזר של 17.50 ש\"ח; מי שרכש גישה לשבוע וביטל לפני תום השבוע לא יקבל החזר, כי מחיר החבילה הקצרה ביותר כבר מכסה את הימים שחלפו. ההחזר מבוצע באמצעות ספק הסליקה, ומועד הופעתו בחשבונך תלוי בנהלי חברת האשראי. לאחר 14 ימים ממועד העסקה לא ניתן לבטלה, ולא יינתן החזר בגין יתרת התקופה. בנוסף, נבחן בתום לב כל פנייה להחזר במקרה של תקלה טכנית מהותית שמנעה שימוש בשירות, חיוב כפול או טעות בתשלום.",
        "en": "This is a digital service delivered immediately and automatically upon payment confirmation. Every user gets a free 10-day trial before any payment (see section 1). Access is sold as a one-time payment for the period chosen (7, 14 or 30 days), with no automatic renewal, so there is no subscription to cancel. In accordance with Israel's Consumer Protection Law, 5741-1981, a distance transaction may be cancelled within 14 days of the transaction (or of receiving the written confirmation, whichever is later) with the cancel button on your account page, or by notifying us through the contact page or the Telegram bot. Access to the service ends when the cancellation notice is given. Because full access is available from the moment of payment, whether or not it is used, the amount paid is reduced by the price of the shortest pass that covers the days that have passed since the purchase (a day that has started counts as a full day) and by a cancellation fee of 5% of the transaction price or NIS 100, whichever is lower. Any remaining balance is refunded to the original payment method within 14 days of the cancellation notice. For example: someone who bought 1 month (NIS 49.90) and cancelled after 10 days is charged the 2-week price (NIS 29.90) and the cancellation fee (NIS 2.50), and gets a refund of NIS 17.50; someone who bought 1 week and cancelled before the week ended gets no refund, since the price of the shortest pass already covers the days that have passed. The refund is processed through the payment provider, and when it appears in your account depends on the card company's procedures. After 14 days from the transaction it can no longer be cancelled, and no refund is given for the rest of the period. In addition, we will review in good faith any refund request in case of a material technical fault that prevented use of the service, a duplicate charge, or a payment error.",
    },
    "terms.s11_title": {"he": "11. פרטי מפעיל השירות", "en": "11. Service operator details"},
    "terms.s11_body": {
        "he": "טודירה מופעל על ידי אמיר טולדנו, עוסק פטור מס׳ 211530563. המחירים באתר הם המחירים הסופיים: מפעיל השירות עוסק פטור ואינו גובה מע\"מ.",
        "en": "Todira is operated by Amir Toledano, exempt dealer (עוסק פטור) no. 211530563. The prices on the website are final: the operator is an exempt dealer and does not charge VAT.",
    },
    "terms.s12_title": {"he": "12. יצירת קשר", "en": "12. Contact"},
    # split further around a real mailto: link (Terms.jsx) — same clickable-email fix as
    # footer.business_info_pre above; terms.s12_mid is the text between the email and the
    # existing /contact page link, terms.s12_post stays the trailing "." after that link.
    "terms.s12_pre": {
        "he": "לשאלות בנוגע לתנאים אלה, ניתן לפנות באימייל ",
        "en": "For questions about these terms, please reach out via email at ",
    },
    "terms.s12_mid": {
        "he": ", דרך הבוט בטלגרם, או דרך ",
        "en": ", the Telegram bot, or the ",
    },
    "terms.s12_post": {"he": ".", "en": "."},
    # ---------- account page ----------
    # 2026-09-08 fix: this whole page was hardcoded Hebrew-only (unlike every other customer-
    # facing page), so a non-Hebrew visitor saw a fully-Hebrew /account regardless of their own
    # language setting.
    "account.h1": {
        "he": "החשבון שלי", "en": "My Account", "ru": "Мой аккаунт",
        "fr": "Mon compte", "ar": "حسابي",
    },
    "account.subtitle": {
        "he": "המנוי, ההתראות, היסטוריית התשלומים וחיבור הערוצים, טלגרם וגוגל, הכל באותו חשבון.",
        "en": "Your subscription, notifications, payment history, and connected channels, Telegram and Google, all one account.",
        "ru": "Подписка, уведомления, история платежей и подключённые каналы, Telegram и Google, всё в одном аккаунте.",
        "fr": "Votre abonnement, vos notifications, votre historique de paiements et vos canaux connectés, Telegram et Google, tout dans un seul compte.",
        "ar": "اشتراكك، إشعاراتك، سجل مدفوعاتك، والقنوات المرتبطة, تيليجرام وجوجل، كلها في حساب واحد.",
    },
    "account.subscription_title": {
        "he": "המנוי שלי", "en": "My Subscription", "ru": "Моя подписка",
        "fr": "Mon abonnement", "ar": "اشتراكي",
    },
    "account.subscription_active": {
        "he": "פעיל, בתוקף עד {date}", "en": "Active, valid until {date}",
        "ru": "Активна, действует до {date}", "fr": "Actif, valable jusqu'au {date}",
        "ar": "نشط، ساري حتى {date}",
    },
    # 2026-10-13 (owner): a live "days left" under the access status on /account ({days} >= 2; the last day has its own text).
    "account.days_left": {
        "he": "נשארו {days} ימים", "en": "{days} days left", "ru": "Осталось дней: {days}",
        "fr": "Encore {days} jours", "ar": "متبقٍ {days} أيام",
    },
    "account.last_day": {
        "he": "זה היום האחרון", "en": "This is the last day", "ru": "Сегодня последний день",
        "fr": "C'est le dernier jour", "ar": "هذا هو اليوم الأخير",
    },
    "account.subscription_trial": {
        "he": "תקופת ניסיון, עד {date}", "en": "Trial period, until {date}",
        "ru": "Пробный период, до {date}", "fr": "Période d'essai, jusqu'au {date}",
        "ar": "فترة تجريبية، حتى {date}",
    },
    "account.subscription_expired": {
        "he": "תקופת הניסיון הסתיימה", "en": "Trial period ended",
        "ru": "Пробный период закончился", "fr": "Période d'essai terminée",
        "ar": "انتهت الفترة التجريبية",
    },
    "account.upgrade_cta_renew": {
        "he": "שדרג מנוי", "en": "Upgrade subscription", "ru": "Улучшить подписку",
        "fr": "Améliorer l'abonnement", "ar": "ترقية الاشتراك",
    },
    "account.upgrade_cta_start": {
        "he": "לשדרוג המנוי", "en": "Upgrade now", "ru": "Оформить подписку",
        "fr": "Passer à l'abonnement", "ar": "الترقية الآن",
    },
    "account.subscription_auto_renews": {
        "he": "המנוי מתחדש אוטומטית כל חודש.",
        "en": "Your subscription auto-renews every month.",
        "ru": "Ваша подписка автоматически продлевается каждый месяц.",
        "fr": "Votre abonnement se renouvelle automatiquement chaque mois.",
        "ar": "يتجدد اشتراكك تلقائيًا كل شهر.",
    },
    "account.subscription_will_not_renew": {
        "he": "ביטלת את החידוש האוטומטי. הגישה נשארת עד סוף התקופה ששילמת, ולא תחויב שוב.",
        "en": "You cancelled auto-renewal, access stays until the end of the period you already paid for, and you won't be charged again.",
        "ru": "Вы отменили автопродление, доступ сохранится до конца уже оплаченного периода, повторного списания не будет.",
        "fr": "Vous avez annulé le renouvellement automatique, l'accès reste actif jusqu'à la fin de la période déjà payée, sans nouveau prélèvement.",
        "ar": "لقد ألغيت التجديد التلقائي, يبقى الوصول حتى نهاية الفترة المدفوعة بالفعل، ولن يتم خصم أي مبلغ مرة أخرى.",
    },
    "account.cancel_subscription_cta": {
        "he": "בטל חידוש אוטומטי", "en": "Cancel auto-renewal", "ru": "Отменить автопродление",
        "fr": "Annuler le renouvellement automatique", "ar": "إلغاء التجديد التلقائي",
    },
    # 2026-10-13 (owner request): the small "cancel purchase" link on /account for a one-time pass inside the 14-day
    # window of terms section 10. {refund}/{paid}/{covering}/{fee} are shekel amounts, {days} the days since purchase.
    "account.cancel_pass_link": {
        "he": "ביטול הרכישה", "en": "Cancel purchase", "ru": "Отменить покупку", "fr": "Annuler l'achat",
        "ar": "إلغاء الشراء",
    },
    "account.cancel_pass_refund": {
        "he": "ביטול עכשיו סוגר את הגישה מיד, ותקבל החזר של ₪{refund} לאמצעי התשלום תוך 14 ימים.",
        "en": "Cancelling now ends your access right away, and ₪{refund} will be refunded to your payment method within 14 days.",
        "ru": "Отмена сейчас сразу закроет доступ, а ₪{refund} вернутся на ваш способ оплаты в течение 14 дней.",
        "fr": "Annuler maintenant met fin à ton accès immédiatement, et ₪{refund} seront remboursés sur ton moyen de paiement sous 14 jours.",
        "ar": "الإلغاء الآن يُنهي وصولك فورًا، وسيُعاد إليك ₪{refund} إلى وسيلة الدفع خلال 14 يومًا.",
    },
    "account.cancel_pass_no_refund": {
        "he": "ביטול עכשיו סוגר את הגישה מיד. לפי מדיניות הביטול, על הרכישה הזו אין החזר.",
        "en": "Cancelling now ends your access right away. Under the cancellation policy, no refund is due for this purchase.",
        "ru": "Отмена сейчас сразу закроет доступ. По правилам отмены за эту покупку возврат не положен.",
        "fr": "Annuler maintenant met fin à ton accès immédiatement. Selon la politique d'annulation, aucun remboursement n'est dû pour cet achat.",
        "ar": "الإلغاء الآن يُنهي وصولك فورًا. وفق سياسة الإلغاء لا يُستحق استرداد عن هذا الشراء.",
    },
    "account.cancel_pass_breakdown": {
        "he": "שולם ₪{paid}. מקוזזים ₪{covering} עבור {days} ימים מאז הרכישה ו־₪{fee} דמי ביטול.",
        "en": "Paid ₪{paid}. Deducted: ₪{covering} for {days} days since the purchase and a ₪{fee} cancellation fee.",
        "ru": "Оплачено ₪{paid}. Удерживается ₪{covering} за {days} дн. с момента покупки и ₪{fee} за отмену.",
        "fr": "Payé ₪{paid}. Retenus: ₪{covering} pour {days} jours depuis l'achat et ₪{fee} de frais d'annulation.",
        "ar": "تم دفع ₪{paid}. يُخصم ₪{covering} مقابل {days} أيام منذ الشراء و₪{fee} رسوم إلغاء.",
    },
    "account.cancel_pass_policy": {
        "he": "מדיניות הביטול", "en": "Cancellation policy", "ru": "Правила отмены",
        "fr": "Politique d'annulation", "ar": "سياسة الإلغاء",
    },
    "account.cancel_pass_confirm": {
        "he": "אישור הביטול", "en": "Confirm cancellation", "ru": "Подтвердить отмену",
        "fr": "Confirmer l'annulation", "ar": "تأكيد الإلغاء",
    },
    "account.cancel_pass_keep": {
        "he": "השארת הגישה", "en": "Keep my access", "ru": "Оставить доступ", "fr": "Garder mon accès",
        "ar": "الإبقاء على الوصول",
    },
    "account.cancel_pass_done": {
        "he": "הביטול התקבל והגישה נסגרה. החזר של ₪{refund} יגיע לאמצעי התשלום תוך 14 ימים.",
        "en": "Your cancellation was received and access has ended. A refund of ₪{refund} will reach your payment method within 14 days.",
        "ru": "Отмена принята, доступ закрыт. Возврат ₪{refund} поступит на ваш способ оплаты в течение 14 дней.",
        "fr": "Annulation reçue, l'accès est terminé. Un remboursement de ₪{refund} arrivera sur ton moyen de paiement sous 14 jours.",
        "ar": "تم استلام الإلغاء وانتهى الوصول. سيصل استرداد بقيمة ₪{refund} إلى وسيلة الدفع خلال 14 يومًا.",
    },
    "account.cancel_pass_done_no_refund": {
        "he": "הביטול התקבל והגישה נסגרה.", "en": "Your cancellation was received and access has ended.",
        "ru": "Отмена принята, доступ закрыт.", "fr": "Annulation reçue, l'accès est terminé.",
        "ar": "تم استلام الإلغاء وانتهى الوصول.",
    },
    "account.resume_subscription_cta": {
        "he": "חדש חידוש אוטומטי", "en": "Resume auto-renewal", "ru": "Возобновить автопродление",
        "fr": "Reprendre le renouvellement automatique", "ar": "استئناف التجديد التلقائي",
    },
    "account.notifications_title": {
        "he": "התראות", "en": "Notifications", "ru": "Уведомления",
        "fr": "Notifications", "ar": "الإشعارات",
    },
    "account.status_on": {
        "he": "מופעלות", "en": "On", "ru": "Включены", "fr": "Activées", "ar": "مفعّلة",
    },
    "account.status_off": {
        "he": "כבויות", "en": "Off", "ru": "Выключены", "fr": "Désactivées", "ar": "معطّلة",
    },
    "account.notifications_toggle_off": {
        "he": "כבה התראות", "en": "Turn off notifications", "ru": "Выключить уведомления",
        "fr": "Désactiver les notifications", "ar": "إيقاف الإشعارات",
    },
    "account.notifications_toggle_on": {
        "he": "הפעל התראות", "en": "Turn on notifications", "ru": "Включить уведомления",
        "fr": "Activer les notifications", "ar": "تفعيل الإشعارات",
    },
    "account.channels_title": {
        "he": "חיבור ערוצים", "en": "Connected Channels", "ru": "Подключённые каналы",
        "fr": "Canaux connectés", "ar": "القنوات المرتبطة",
    },
    "account.channel_connected": {
        "he": "מחובר", "en": "Connected", "ru": "Подключено", "fr": "Connecté", "ar": "متصل",
    },
    "account.telegram_connect_cta": {
        "he": "פתח את הבוט לחיבור", "en": "Open the bot to connect",
        "ru": "Открыть бота для подключения", "fr": "Ouvrir le bot pour vous connecter",
        "ar": "افتح البوت للربط",
    },
    "account.telegram_connect_hint": {
        "he": "לוחץ על הכפתור והחיבור קורה לבד",
        "en": "Tap the button and the connection happens automatically",
        "ru": "Нажмите на кнопку, подключение произойдёт автоматически",
        "fr": "Appuyez sur le bouton, la connexion se fait automatiquement",
        "ar": "اضغط على الزر وسيتم الربط تلقائيًا",
    },
    "account.no_active_code": {
        "he": "אין קוד חיבור פעיל כרגע", "en": "No active connection code right now",
        "ru": "Сейчас нет активного кода подключения", "fr": "Aucun code de connexion actif pour le moment",
        "ar": "لا يوجد رمز ربط نشط حاليًا",
    },
    "account.google_connect_cta": {
        "he": "קשר את Google לחשבון", "en": "Link Google to your account",
        "ru": "Привязать Google к аккаунту", "fr": "Lier Google à votre compte",
        "ar": "اربط Google بحسابك",
    },
    "account.code_hint_prefix": {
        "he": "הקוד שלך:", "en": "Your code:", "ru": "Ваш код:", "fr": "Votre code:", "ar": "رمزك:",
    },
    "account.code_hint_suffix": {
        "he": "(בתוקף ל־15 דקות). אפשר גם לשלוח אותו ידנית מהערוץ שאתה רוצה לחבר, במקום ללחוץ על הכפתור.",
        "en": ": valid for 15 minutes. You can also send it manually from the channel you want to connect, instead of tapping the button.",
        "ru": ": действителен 15 минут. Можно также отправить его вручную из канала, который хотите подключить, вместо нажатия кнопки.",
        "fr": ": valable 15 minutes. Vous pouvez aussi l'envoyer manuellement depuis le canal que vous souhaitez connecter, au lieu d'appuyer sur le bouton.",
        "ar": ": صالح لمدة 15 دقيقة. يمكنك أيضًا إرساله يدويًا من القناة التي تريد ربطها، بدلاً من الضغط على الزر.",
    },
    "account.payment_history_title": {
        "he": "היסטוריית תשלומים", "en": "Payment History", "ru": "История платежей",
        "fr": "Historique des paiements", "ar": "سجل المدفوعات",
    },
    "account.payment_status_paid": {
        "he": "שולם", "en": "Paid", "ru": "Оплачено", "fr": "Payé", "ar": "مدفوع",
    },
    "account.payment_status_pending": {
        "he": "ממתין", "en": "Pending", "ru": "В ожидании", "fr": "En attente", "ar": "قيد الانتظار",
    },
    "account.payment_status_failed": {
        "he": "נכשל", "en": "Failed", "ru": "Не удалось", "fr": "Échoué", "ar": "فشل",
    },
    "account.payment_status_cancelled": {
        "he": "בוטל", "en": "Cancelled", "ru": "Отменено", "fr": "Annulé", "ar": "ألغي",
    },
    # ---------- login / google-pending / upgrade / upgrade_pay / upgrade_success pages ----------
    # 2026-09-08, same audit as the account-page section above: the whole auth+payment funnel was
    # hardcoded Hebrew-only too. Not fixed here: PLAN_LABELS_HE (website/main.py) — the plan name
    # shown on /upgrade/pay still comes from a Hebrew-only dict server-side, a deeper gap than a
    # template string; left as a known follow-up rather than silently declaring this fully done.
    "login.h1": {
        "he": "התחברות לטודירה", "en": "Log in to Todira", "ru": "Войти в Todira",
        "fr": "Connexion à Todira", "ar": "تسجيل الدخول إلى توديرا",
    },
    "login.subtitle": {
        "he": "בחר איך להתחבר. כל האפשרויות מובילות לאותו חשבון.",
        "en": "Choose how to log in, every option leads to the same account.",
        "ru": "Выберите способ входа, все варианты ведут к одному и тому же аккаунту.",
        "fr": "Choisissez comment vous connecter, toutes les options mènent au même compte.",
        "ar": "اختر طريقة تسجيل الدخول, كل الخيارات تؤدي إلى نفس الحساب.",
    },
    "login.google_cta": {
        "he": "התחברות מהירה עם Google", "en": "Quick login with Google",
        "ru": "Быстрый вход через Google", "fr": "Connexion rapide avec Google",
        "ar": "تسجيل دخول سريع عبر Google",
    },
    "login.divider": {
        "he": "או המשך ישירות דרך האפליקציה", "en": "Or continue directly through the app",
        "ru": "Или продолжите прямо через приложение", "fr": "Ou continuez directement via l'application",
        "ar": "أو تابع مباشرة عبر التطبيق",
    },
    "login.telegram_cta": {
        "he": "המשך בטלגרם", "en": "Continue on Telegram", "ru": "Продолжить в Telegram",
        "fr": "Continuer sur Telegram", "ar": "تابع عبر تيليجرام",
    },
    "login.hint": {
        "he": "כבר נרשמת בטלגרם ועוד לא חיברת Google? לחיצה על ״{telegram_cta}״ פותחת את הבוט. שם יש קישור לחשבון שלך שמחזיר אותך לפה, לאותו דפדפן, מחובר. משם החיבור ל־Google יעבוד ישר על החשבון שלך.",
        "en": "Already registered via Telegram, but haven't linked Google yet? Tapping \"{telegram_cta}\" above opens the bot, you'll find your account link there that brings you back here, in the same browser, recognized. From there, connecting with Google will work straight on your existing account.",
        "ru": "Уже зарегистрированы через Telegram, но ещё не привязали Google? Нажатие на «{telegram_cta}» выше откроет бота, там вы найдёте ссылку на свой аккаунт, которая вернёт вас сюда, в тот же браузер, уже узнанным. Оттуда подключение через Google сработает прямо на вашем существующем аккаунте.",
        "fr": "Déjà inscrit via Telegram, mais pas encore lié à Google? Appuyer sur « {telegram_cta} » ci-dessus ouvre le bot, vous y trouverez le lien de votre compte qui vous ramène ici, dans le même navigateur, reconnu. À partir de là, la connexion avec Google fonctionnera directement sur votre compte existant.",
        "ar": "مسجّل بالفعل عبر تيليجرام، لكن لم تربط Google بعد؟ الضغط على \"{telegram_cta}\" أعلاه يفتح البوت, ستجد هناك رابط حسابك الذي يعيدك إلى هنا، في نفس المتصفح، معروفًا. من هناك، سيعمل الربط مع Google مباشرة على حسابك الحالي.",
    },
    "google_pending.h1": {
        "he": "ההתחברות עם Google הצליחה", "en": "Google login successful",
        "ru": "Вход через Google выполнен успешно", "fr": "Connexion Google réussie",
        "ar": "تم تسجيل الدخول عبر Google بنجاح",
    },
    "google_pending.subtitle": {
        "he": "זו הפעם הראשונה שאנחנו רואים את החשבון הזה. איך תרצה להמשיך?",
        "en": "This is the first time we've seen this account, how would you like to continue?",
        "ru": "Мы впервые видим этот аккаунт, как вы хотите продолжить?",
        "fr": "C'est la première fois que nous voyons ce compte, comment souhaitez-vous continuer?",
        "ar": "هذه أول مرة نرى فيها هذا الحساب, كيف تريد المتابعة؟",
    },
    "google_pending.new_account_cta": {
        "he": "זה חשבון חדש, מתחיל ישר פה באתר",
        "en": "This is a new account, start right here on the site",
        "ru": "Это новый аккаунт, начните прямо здесь, на сайте",
        "fr": "C'est un nouveau compte, commencez directement ici sur le site",
        "ar": "هذا حساب جديد, ابدأ مباشرة هنا في الموقع",
    },
    "google_pending.new_account_hint": {
        "he": "ניצור לך חשבון עם סינון פתוח לכל הדירות, ותוכל לצמצם אותו מתי שבא לך ב״סינון״. טלגרם תמיד יישאר אפשרות נוספת להתראות, לא חובה.",
        "en": "We'll create an account for you with an open filter that matches every listing, you can narrow it down anytime in \"Filter\". Telegram will always stay available as an extra way to get notified, with no obligation to use it.",
        "ru": "Мы создадим для вас аккаунт с открытым фильтром, который подходит под все объявления, вы можете сузить его в любой момент в разделе «Фильтр». Telegram всегда будет доступен как дополнительный способ получать уведомления, без обязательства им пользоваться.",
        "fr": "Nous créerons pour vous un compte avec un filtre ouvert qui correspond à toutes les annonces, vous pourrez le restreindre à tout moment dans « Filtre ». Telegram restera toujours disponible comme moyen supplémentaire de recevoir des notifications, sans obligation de l'utiliser.",
        "ar": "سننشئ لك حسابًا مع فلتر مفتوح يطابق كل الشقق, يمكنك تضييقه في أي وقت من \"الفلتر\". سيبقى تيليجرام متاحًا دائمًا كوسيلة إضافية لتلقي الإشعارات، دون إلزام باستخدامه.",
    },
    "google_pending.divider": {
        "he": "או", "en": "Or", "ru": "Или", "fr": "Ou", "ar": "أو",
    },
    "google_pending.existing_account_prompt": {
        "he": "כבר יש לך חשבון דרך טלגרם?",
        "en": "Already have an account via Telegram?",
        "ru": "У вас уже есть аккаунт через Telegram?",
        "fr": "Vous avez déjà un compte via Telegram?",
        "ar": "هل لديك حساب بالفعل عبر تيليجرام؟",
    },
    "google_pending.link_existing_cta": {
        "he": "קשר לחשבון הקיים שלי", "en": "Link to my existing account",
        "ru": "Привязать к существующему аккаунту", "fr": "Lier à mon compte existant",
        "ar": "اربط بحسابي الحالي",
    },
    "google_pending.link_hint_with_token": {
        "he": "שלח /start בבוט, והחיבור יושלם שם מיד, לא משנה באיזה דפדפן תמשיך.",
        "en": "Send /start to the bot, the connection completes right there, regardless of which browser you use afterward.",
        "ru": "Отправьте /start боту, подключение завершится сразу там, независимо от того, каким браузером вы будете пользоваться дальше.",
        "fr": "Envoyez /start au bot, la connexion se termine immédiatement là-bas, quel que soit le navigateur que vous utiliserez ensuite.",
        "ar": "أرسل /start للبوت, سيكتمل الربط هناك فورًا، بغض النظر عن المتصفح الذي ستستخدمه لاحقًا.",
    },
    "google_pending.link_hint_no_token": {
        "he": "פתח את הבוט פעם אחת. כשתחזור לאתר מאותו דפדפן, נשלים את החיבור לבד.",
        "en": "Open the bot once, when you return to the site from the same browser, we'll complete the connection automatically.",
        "ru": "Откройте бота один раз, когда вы вернётесь на сайт из того же браузера, мы автоматически завершим подключение.",
        "fr": "Ouvrez le bot une fois, lorsque vous reviendrez sur le site depuis le même navigateur, nous terminerons la connexion automatiquement.",
        "ar": "افتح البوت مرة واحدة, عند عودتك إلى الموقع من نفس المتصفح، سنكمل الربط تلقائيًا.",
    },
    "upgrade.h1": {
        "he": "שדרוג המנוי", "en": "Upgrade subscription", "ru": "Улучшение подписки",
        "fr": "Mise à niveau de l'abonnement", "ar": "ترقية الاشتراك",
    },
    "upgrade.owner_notice": {
        "he": "אתה הבעלים של השירות, ולכן יש לך גישה מלאה תמיד, בלי קשר לתשלום.",
        "en": "You're the service owner, you always have full access, regardless of payment.",
        "ru": "Вы владелец сервиса, у вас всегда есть полный доступ, независимо от оплаты.",
        "fr": "Vous êtes le propriétaire du service, vous avez toujours un accès complet, indépendamment du paiement.",
        "ar": "أنت مالك الخدمة, لديك دائمًا وصول كامل، بغض النظر عن الدفع.",
    },
    "upgrade.access_active": {
        "he": "יש לך גישה מלאה, בתוקף עד {date}.", "en": "You have full access, valid until {date}.",
        "ru": "У вас есть полный доступ, действует до {date}.",
        "fr": "Vous avez un accès complet, valable jusqu'au {date}.",
        "ar": "لديك وصول كامل، ساري حتى {date}.",
    },
    "upgrade.access_trial": {
        "he": "אתה בתקופת הניסיון, עד {date}.", "en": "You're in the trial period, until {date}.",
        "ru": "Вы находитесь в пробном периоде, до {date}.",
        "fr": "Vous êtes en période d'essai, jusqu'au {date}.",
        "ar": "أنت في الفترة التجريبية، حتى {date}.",
    },
    "upgrade.access_expired": {
        "he": "תקופת הניסיון נגמרה. כדי להמשיך לקבל את המודעה המלאה וקישור ישיר, בחר חבילה למטה.",
        "en": "Your trial period has ended. To keep getting the full listing + direct link, choose a plan below.",
        "ru": "Ваш пробный период закончился. Чтобы продолжать получать полное объявление + прямую ссылку, выберите план ниже.",
        "fr": "Votre période d'essai est terminée. Pour continuer à recevoir l'annonce complète + le lien direct, choisissez un forfait ci-dessous.",
        "ar": "انتهت فترتك التجريبية. لمواصلة الحصول على الإعلان الكامل + الرابط المباشر، اختر خطة أدناه.",
    },
    "upgrade.plan_weekly": {
        "he": "שבועי", "en": "Weekly", "ru": "Недельный", "fr": "Hebdomadaire", "ar": "أسبوعي",
    },
    "upgrade.plan_biweekly": {
        "he": "שבועיים", "en": "Bi-weekly", "ru": "Двухнедельный", "fr": "Bihebdomadaire", "ar": "كل أسبوعين",
    },
    "upgrade.plan_monthly": {
        "he": "חודשי", "en": "Monthly", "ru": "Ежемесячный", "fr": "Mensuel", "ar": "شهري",
    },
    "upgrade.plan_subscription": {
        "he": "מנוי חודשי", "en": "Monthly subscription", "ru": "Ежемесячная подписка",
        "fr": "Abonnement mensuel", "ar": "اشتراك شهري",
    },
    # Same string, different key — upgrade_pay.html looks this one up via string concatenation
    # ("upgrade.plan_" ~ plan, plan being the raw SUBSCRIPTION_PLAN="monthly_subscription" key),
    # while upgrade.html/account.html reference upgrade.plan_subscription directly above.
    "upgrade.plan_monthly_subscription": {
        "he": "מנוי חודשי", "en": "Monthly subscription", "ru": "Ежемесячная подписка",
        "fr": "Abonnement mensuel", "ar": "اشتراك شهري",
    },
    "upgrade.per_month_suffix": {
        "he": " / חודש", "en": " / month", "ru": " / месяц", "fr": " / mois", "ar": " / شهر",
    },
    "upgrade.cancel_anytime_hint": {
        "he": "מתחדש אוטומטית כל חודש. אפשר לבטל בכל רגע מ־/account, וממשיכים לקבל גישה עד סוף התקופה ששולמה.",
        "en": "Auto-renews every month. Cancel anytime from /account, you keep access until the end of the period you already paid for.",
        "ru": "Автоматически продлевается каждый месяц. Отменить можно в любой момент в /account, доступ сохраняется до конца уже оплаченного периода.",
        "fr": "Se renouvelle automatiquement chaque mois. Annulez à tout moment depuis /account, vous gardez l'accès jusqu'à la fin de la période déjà payée.",
        "ar": "يتجدد تلقائيًا كل شهر. يمكن الإلغاء في أي وقت من /account, يبقى الوصول حتى نهاية الفترة المدفوعة بالفعل.",
    },
    "upgrade.already_subscribed": {
        "he": "יש לך כבר מנוי פעיל.", "en": "You already have an active subscription.",
        "ru": "У вас уже есть активная подписка.", "fr": "Vous avez déjà un abonnement actif.",
        "ar": "لديك بالفعل اشتراك نشط.",
    },
    # 2026-09-24: split off from upgrade.already_subscribed's own text so this renders as a real
    # <a href="/account"> link (real bug fix — see that route's own comment: a user whose
    # subscription is cancelled-but-not-yet-lapsed used to be able to land back on THIS page and
    # open a second Takbull order, orphaning the still-billing original) rather than a plain-text
    # mention of the path.
    "upgrade.manage_subscription_link": {
        "he": "לניהול המנוי", "en": "Manage subscription", "ru": "Управление подпиской",
        "fr": "Gérer l'abonnement", "ar": "إدارة الاشتراك",
    },
    "upgrade.choose_plan_cta": {
        "he": "בחר {plan}", "en": "Choose {plan}", "ru": "Выбрать {plan}", "fr": "Choisir {plan}",
        "ar": "اختر {plan}",
    },
    "upgrade.payment_hint_takbull": {
        "he": "התשלום מאובטח דרך תקבול: ביט או כרטיס אשראי. בעמוד התשלום תראה את 3 החבילות. תוסיף לעגלה את זו שבחרת ותשלם.",
        "en": "Payment is secured through Takbull, Bit or credit card. On the payment page you'll see all 3 plans together, just add the one you chose here (by price) to the cart and complete payment.",
        "ru": "Оплата защищена через Takbull, Bit или банковская карта. На странице оплаты вы увидите все 3 плана вместе, просто добавьте выбранный здесь план (по цене) в корзину и завершите оплату.",
        "fr": "Le paiement est sécurisé via Takbull, Bit ou carte de crédit. Sur la page de paiement, vous verrez les 3 forfaits ensemble, ajoutez simplement celui choisi ici (selon le prix) au panier et finalisez le paiement.",
        "ar": "الدفع مؤمّن عبر تكبول, Bit أو بطاقة ائتمان. في صفحة الدفع سترى الخطط الثلاث معًا, فقط أضف الخطة التي اخترتها هنا (حسب السعر) إلى السلة وأكمل الدفع.",
    },
    "upgrade.payment_hint_takbull_recurring": {
        "he": "התשלום מאובטח דרך תקבול: ביט או כרטיס אשראי. החיוב מתחדש כל חודש עד שתבטל.",
        "en": "Payment is secured through Takbull, Bit or credit card. The charge auto-renews every month until you cancel.",
        "ru": "Оплата защищена через Takbull, Bit или банковская карта. Списание автоматически продлевается каждый месяц, пока вы не отмените подписку.",
        "fr": "Le paiement est sécurisé via Takbull, Bit ou carte de crédit. Le prélèvement se renouvelle automatiquement chaque mois jusqu'à l'annulation.",
        "ar": "الدفع مؤمّن عبر تكبول, Bit أو بطاقة ائتمان. يتجدد الخصم تلقائيًا كل شهر حتى تقوم بالإلغاء.",
    },
    "upgrade.payment_hint_manual": {
        "he": "התשלום ידני בביט/PayBox. אחרי הלחיצה תעבור לעמוד עם כל הפרטים.",
        "en": "Payment is done manually via Bit/PayBox, after clicking you'll be taken to a page with all the payment details.",
        "ru": "Оплата производится вручную через Bit/PayBox, после нажатия вы перейдёте на страницу со всеми деталями оплаты.",
        "fr": "Le paiement se fait manuellement via Bit/PayBox, après avoir cliqué, vous serez redirigé vers une page avec tous les détails de paiement.",
        "ar": "يتم الدفع يدويًا عبر Bit/PayBox, بعد الضغط ستنتقل إلى صفحة تحتوي على كل تفاصيل الدفع.",
    },
    # 2026-09-10 addition: a small value-anchor box under the plan card, right where price
    # sensitivity is highest — reframes the price against what people already know a broker
    # costs. 2026-09-21: the plan itself became a real auto-renewing subscription (see
    # todira_common/access.py's SUBSCRIPTION_PLAN), so the body copy below now DOES say "cancel
    # anytime" — cancel_anytime_hint above (right on the plan card itself) already sets that
    # expectation, this box just reinforces it next to the price comparison.
    # 2026-09-25 fix (owner's own report): "less than a daily coffee" wasn't actually accurate —
    # a single coffee in practice costs less than the MONTHLY price this is comparing it to, so
    # the comparison read as backwards/misleading rather than reassuring. Reframed as roughly
    # EQUAL to one coffee-and-pastry outing (owner's own suggested framing) — a comparison that's
    # actually true at this price point, not just a nice-sounding line.
    # 2026-10-13 (owner): no "a month?" - access is a one-time pass (week / two weeks / month), not a monthly charge.
    "upgrade.value_anchor_title": {
        "he": "חודש שלם ב־49.90 ₪? בערך המחיר של קפה ומאפה.",
        "en": "A whole month for ₪49.90? About the price of a coffee and a pastry.",
        "ru": "Целый месяц за 49.90 ₪? Примерно цена кофе с выпечкой.",
        "fr": "Un mois entier pour 49,90 ₪? À peu près le prix d'un café et d'une pâtisserie.",
        "ar": "شهر كامل مقابل 49.90 ₪؟ تقريبًا سعر قهوة ومعجنات.",
    },
    "upgrade.value_anchor_body": {
        "he": "עמלת תיווך עולה בדרך כלל אלפי שקלים. אצלנו זה סכום סמלי, בלי חידוש אוטומטי ובלי התחייבות.",
        "en": "A broker's fee usually costs thousands of shekels, once. With us it's a token amount, with no automatic renewal and no commitment.",
        "ru": "Комиссия брокера обычно стоит тысячи шекелей. У нас, символическая сумма, без автопродления и обязательств.",
        "fr": "Les frais d'un agent coûtent souvent des milliers de shekels. Chez nous, c'est un montant symbolique, sans renouvellement automatique ni engagement.",
        "ar": 'عمولة الوسيط تكلّف عادةً آلاف الشواقل. عندنا مبلغ رمزي، بدون تجديد تلقائي وبدون التزام.',
    },
    # Required terms-agreement checkbox on each plan's own form (2026-09-17, added per the
    # payment processor's own compliance requirement — active, explicit consent to the terms,
    # not just a passive link, before proceeding to checkout). Split into prefix/suffix around
    # the terms link (reusing footer.terms for the link text itself) rather than one embedded-
    # HTML string, matching this file's own no-`| safe`-anywhere convention.
    "upgrade.terms_agree_prefix": {
        "he": "קראתי ואני מסכים ל", "en": "I have read and agree to the ",
        "ru": "Я прочитал(а) и согласен(на) с ", "fr": "J'ai lu et j'accepte les ",
        "ar": "لقد قرأت وأوافق على ",
    },
    "upgrade.terms_agree_suffix": {
        "he": ", כולל מדיניות ביטול העסקה", "en": ", including the cancellation policy",
        "ru": ", включая политику отмены", "fr": ", y compris la politique d'annulation",
        "ar": "، بما في ذلك سياسة الإلغاء",
    },
    # 2026-09-28 (backlog #81): dorin.app-style single-card redesign — real owner-supplied
    # screenshots of dorin's own plan cards (icon badge, subtitle, price, checkmark list, CTA,
    # disclaimer) and FAQ accordion below the card. Owner's explicit call: match the VISUAL
    # structure only — Todira stays a recurring monthly subscription (unlike dorin's one-time
    # week/2-week/month passes), so copy below describes OUR real plan and mechanics, not dorin's.
    "upgrade.pass_name_7": {
        "he": 'שבוע',
        "en": '1 week',
        "ru": '1 неделя',
        "fr": '1 semaine',
        "ar": 'أسبوع',
    },
    "upgrade.pass_name_14": {
        "he": 'שבועיים',
        "en": '2 weeks',
        "ru": '2 недели',
        "fr": '2 semaines',
        "ar": 'أسبوعان',
    },
    "upgrade.pass_name_30": {
        "he": 'חודש',
        "en": '1 month',
        "ru": '1 месяц',
        "fr": '1 mois',
        "ar": 'شهر',
    },
    "upgrade.pass_days": {
        "he": '{days} ימי גישה',
        "en": '{days} days of access',
        "ru": '{days} дн. доступа',
        "fr": "{days} jours d'accès",
        "ar": '{days} يومًا من الوصول',
    },
    "upgrade.pass_per_day": {
        "he": '≈ ₪{price} ליום',
        "en": '≈ ₪{price} per day',
        "ru": '≈ {price} ₪ в день',
        "fr": '≈ {price} ₪ par jour',
        "ar": '≈ {price} ₪ يوميًا',
    },
    "upgrade.pass_best_value": {
        "he": 'הכי משתלם',
        "en": 'Best value',
        "ru": 'Самый выгодный',
        "fr": 'Meilleur rapport',
        "ar": 'الأوفر',
    },
    # 2026-10-13 (owner decision): one button to Takbull's page, where the pass is picked once (replaces the old
    # "pick the same pass again on the next page" notice).
    "upgrade.pass_choose_cta": {
        "he": 'לבחירת חבילה ותשלום מאובטח',
        "en": 'Choose your pass and pay securely',
        "ru": 'Выбрать тариф и оплатить',
        "fr": 'Choisir mon pass et payer',
        "ar": 'اختيار الباقة والدفع بأمان',
    },
    "upgrade.pass_choose_hint": {
        "he": 'בעמוד הבא בוחרים שבוע, שבועיים או חודש ומשלמים.',
        "en": 'On the next page you pick 1 week, 2 weeks or 1 month and pay.',
        "ru": 'На следующей странице вы выбираете 1 неделю, 2 недели или 1 месяц и оплачиваете.',
        "fr": 'Sur la page suivante, vous choisissez 1 semaine, 2 semaines ou 1 mois et payez.',
        "ar": 'في الصفحة التالية تختارون أسبوعًا أو أسبوعين أو شهرًا وتدفعون.',
    },
    # 2026-10-13 (owner request): the three facts under the pass cards, each said once (they replace
    # upgrade.pass_onetime_hint and upgrade.payment_hint_takbull_onetime, which repeated each other). "No automatic
    # renewal and no commitment" is left to upgrade.value_anchor_body right below, so it is said once on the page.
    "upgrade.pass_fact_secure": {
        "he": 'תשלום מאובטח דרך תקבול: ביט או כרטיס אשראי',
        "en": 'Secure payment through Takbull: Bit or credit card',
        "ru": 'Защищённая оплата через Takbull: Bit или банковская карта',
        "fr": "Paiement sécurisé via Takbull: Bit ou carte bancaire",
        "ar": 'دفع آمن عبر Takbull: Bit أو بطاقة ائتمان',
    },
    "upgrade.pass_fact_instant": {
        "he": 'הגישה נפתחת אוטומטית תוך דקה',
        "en": 'Access opens automatically within a minute',
        "ru": 'Доступ открывается автоматически в течение минуты',
        "fr": "L'accès s'ouvre automatiquement en une minute",
        "ar": 'يُفتح الوصول تلقائيًا خلال دقيقة',
    },
    "upgrade.pass_fact_onetime": {
        "he": 'תשלום חד-פעמי. נזכיר לך לפני שהגישה מסתיימת',
        "en": "One-time payment. We'll remind you before your access ends",
        "ru": 'Разовый платёж. Мы напомним вам до окончания доступа',
        "fr": "Paiement unique. Nous vous rappellerons avant la fin de votre accès",
        "ar": 'دفعة واحدة. سنذكّرك قبل انتهاء الوصول',
    },
    "upgrade.faq_q1_onetime": {
        "he": 'האם זה מתחדש אוטומטית?',
        "en": 'Does it renew automatically?',
        "ru": 'Продлевается ли доступ автоматически?',
        "fr": "Est-ce que ça se renouvelle automatiquement?",
        "ar": 'هل يتجدد تلقائيًا؟',
    },
    "upgrade.faq_a1_onetime": {
        "he": "לא. זה תשלום חד־פעמי לתקופה שבחרת (7, 14 או 30 ימים). לפני שהגישה נגמרת נשלח לך תזכורת, ואם תרצה להמשיך, פשוט תבחר שוב.",
        "en": "No. It's a one-time payment for the period you choose (7, 14 or 30 days). We'll send you a reminder before your access ends, and if you want to continue you can choose again.",
        "ru": 'Нет. Это разовый платёж за выбранный период (7, 14 или 30 дней). Перед окончанием доступа мы пришлём напоминание, и вы сможете выбрать снова.',
        "fr": "Non. C'est un paiement unique pour la période choisie (7, 14 ou 30 jours). Nous vous enverrons un rappel avant la fin de votre accès, et vous pourrez choisir à nouveau.",
        "ar": 'لا. هذه دفعة واحدة للفترة التي تختارها (7 أو 14 أو 30 يومًا). سنرسل لك تذكيرًا قبل انتهاء الوصول، ويمكنك الاختيار من جديد إن أردت المتابعة.',
    },
    "upgrade.faq_q3_onetime": {
        "he": 'מה קורה כשהתקופה נגמרת?',
        "en": 'What happens when the period ends?',
        "ru": 'Что происходит, когда период заканчивается?',
        "fr": "Que se passe-t-il à la fin de la période?",
        "ar": 'ماذا يحدث عند انتهاء الفترة؟',
    },
    "upgrade.faq_a3_onetime": {
        "he": "הגישה המלאה נגמרת ולא תחויב שוב. אפשר לחדש מתי שבא לך מהעמוד הזה.",
        "en": 'Full access ends and you are not charged again. You can renew at any time from this page.',
        "ru": 'Полный доступ заканчивается, повторных списаний нет. Продлить можно в любой момент на этой странице.',
        "fr": "L'accès complet se termine et vous n'êtes plus débité. Vous pouvez renouveler à tout moment depuis cette page.",
        "ar": 'ينتهي الوصول الكامل ولن يتم خصم أي مبلغ مرة أخرى. يمكنك التجديد في أي وقت من هذه الصفحة.',
    },
    "upgrade.plan_badge_label": {
        "he": "הבחירה המומלצת", "en": "Recommended choice", "ru": "Рекомендуемый выбор",
        "fr": "Choix recommandé", "ar": "الخيار الموصى به",
    },
    "upgrade.plan_subtitle": {
        "he": "גישה מלאה לכל דירה שמתאימה לך, בלי הגבלה",
        "en": "Full access to every apartment that matches you, unlimited",
        "ru": "Полный доступ к каждой подходящей вам квартире, без ограничений",
        "fr": "Accès complet à chaque appartement qui vous correspond, sans limite",
        "ar": "وصول كامل لكل شقة تناسبك، بلا حدود",
    },
    "upgrade.checklist_scan": {
        "he": "חיפוש אוטומטי לאורך כל היום",
        "en": "Automatic searching all day long",
        "ru": "Автоматический поиск весь день",
        "fr": "Recherche automatique toute la journée",
        "ar": "بحث تلقائي طوال اليوم",
    },
    "upgrade.checklist_alert": {
        "he": "התראה מיידית בטלגרם ברגע שיש התאמה",
        "en": "Instant Telegram alert the moment there's a match",
        "ru": "Мгновенное уведомление в Telegram при совпадении",
        "fr": "Alerte Telegram instantanée dès qu'il y a une correspondance",
        "ar": "تنبيه فوري على تيليجرام فور وجود تطابق",
    },
    "upgrade.checklist_filtered": {
        "he": "רק דירות שבאמת עומדות בסינון שלך",
        "en": "Only apartments that truly meet your filter",
        "ru": "Только квартиры, действительно соответствующие вашему фильтру",
        "fr": "Uniquement les appartements qui correspondent vraiment à votre filtre",
        "ar": "فقط الشقق التي تطابق فعلًا فلترك",
    },
    "upgrade.checklist_contact": {
        "he": "גישה מלאה לפרטי הקשר וקישור ישיר למודעה המקורית",
        "en": "Full access to contact details, a direct link to the original listing",
        "ru": "Полный доступ к контактным данным, прямая ссылка на оригинальное объявление",
        "fr": "Accès complet aux coordonnées, lien direct vers l'annonce d'origine",
        "ar": "وصول كامل لبيانات التواصل, رابط مباشر للإعلان الأصلي",
    },
    "upgrade.checklist_cancel": {
        "he": "ביטול בכל רגע, בלי התחייבות",
        "en": "Cancel anytime, no commitment",
        "ru": "Отмена в любой момент, без обязательств",
        "fr": "Annulation à tout moment, sans engagement",
        "ar": "إلغاء في أي وقت، بلا التزام",
    },
    "upgrade.faq_title": {
        "he": "שאלות נפוצות על התשלום וההפעלה", "en": "Common questions about payment and activation",
        "ru": "Частые вопросы об оплате и активации", "fr": "Questions fréquentes sur le paiement et l'activation",
        "ar": "أسئلة شائعة حول الدفع والتفعيل",
    },
    "upgrade.faq_q1": {
        "he": "האם המנוי מתחדש אוטומטית?", "en": "Does the subscription renew automatically?",
        "ru": "Подписка продлевается автоматически?", "fr": "L'abonnement se renouvelle-t-il automatiquement?",
        "ar": "هل يتجدد الاشتراك تلقائيًا؟",
    },
    "upgrade.faq_a1": {
        "he": "כן, המנוי מתחדש אוטומטית מדי חודש. אפשר לבטל בכל רגע מעמוד /account, וממשיכים לקבל גישה עד סוף התקופה ששולמה.",
        "en": "Yes, the subscription renews automatically every month. You can cancel anytime from the /account page, and you keep access until the end of the period you already paid for.",
        "ru": "Да, подписка автоматически продлевается каждый месяц. Отменить можно в любой момент на странице /account, доступ сохранится до конца уже оплаченного периода.",
        "fr": "Oui, l'abonnement se renouvelle automatiquement chaque mois. Vous pouvez annuler à tout moment depuis la page /account, et vous gardez l'accès jusqu'à la fin de la période déjà payée.",
        "ar": "نعم، يتجدد الاشتراك تلقائيًا كل شهر. يمكنك الإلغاء في أي وقت من صفحة /account، وستحتفظ بالوصول حتى نهاية الفترة المدفوعة بالفعل.",
    },
    "upgrade.faq_q2": {
        "he": "איך משלמים? האם התשלום מאובטח?", "en": "How do I pay? Is the payment secure?",
        "ru": "Как оплатить? Безопасен ли платёж?", "fr": "Comment payer? Le paiement est-il sécurisé?",
        "ar": "كيف أدفع؟ هل الدفع آمن؟",
    },
    "upgrade.faq_a2": {
        "he": "התשלום מאובטח לגמרי, דרך ביט או כרטיס אשראי.",
        "en": "Payment is fully secured, via Bit or credit card.",
        "ru": "Оплата полностью защищена, через Bit или банковскую карту.",
        "fr": "Le paiement est entièrement sécurisé, via Bit ou carte de crédit.",
        "ar": "الدفع مؤمّن بالكامل، عبر Bit أو بطاقة ائتمان.",
    },
    "upgrade.faq_q3": {
        "he": "מה קורה אם אני מבטל את המנוי?", "en": "What happens if I cancel my subscription?",
        "ru": "Что произойдёт, если я отменю подписку?", "fr": "Que se passe-t-il si j'annule mon abonnement?",
        "ar": "ماذا يحدث إذا ألغيت اشتراكي؟",
    },
    "upgrade.faq_a3": {
        "he": "ממשיכים לקבל גישה מלאה עד סוף התקופה ששילמת עליה, ולא תחויב שוב.",
        "en": "You keep full access until the end of the period you already paid for, and you won't be charged again.",
        "ru": "Вы сохраните полный доступ до конца уже оплаченного периода, и повторного списания не будет.",
        "fr": "Vous gardez un accès complet jusqu'à la fin de la période déjà payée, et vous ne serez plus débité.",
        "ar": "ستحتفظ بالوصول الكامل حتى نهاية الفترة المدفوعة بالفعل، ولن يتم خصم مبلغ آخر منك.",
    },
    "upgrade.terms_error": {
        "he": "צריך לאשר את תנאי השימוש לפני שממשיכים לתשלום.",
        "en": "You need to agree to the Terms of Use before continuing to payment.",
        "ru": "Перед переходом к оплате нужно принять условия использования.",
        "fr": "Vous devez accepter les conditions d'utilisation avant de continuer vers le paiement.",
        "ar": "يجب الموافقة على شروط الاستخدام قبل المتابعة إلى الدفع.",
    },
    "upgrade_pay.h1": {
        "he": "השלמת התשלום", "en": "Complete payment", "ru": "Завершение оплаты",
        "fr": "Finaliser le paiement", "ar": "إتمام الدفع",
    },
    "upgrade_pay.plan_prefix": {
        "he": "תוכנית {plan}, לתשלום:", "en": "Plan: {plan}, to pay:", "ru": "План: {plan}, к оплате:",
        "fr": "Forfait: {plan}, à payer:", "ar": "الخطة: {plan}, للدفع:",
    },
    "upgrade_pay.bit_instruction": {
        "he": "פתח את Bit, חפש את המספר הזה ושלח ₪{amount}:",
        "en": "Open the Bit app, search for the following number and send ₪{amount}:",
        "ru": "Откройте приложение Bit, найдите следующий номер и отправьте ₪{amount}:",
        "fr": "Ouvrez l'application Bit, recherchez le numéro suivant et envoyez ₪{amount}:",
        "ar": "افتح تطبيق Bit، ابحث عن الرقم التالي وأرسل ₪{amount}:",
    },
    "upgrade_pay.paybox_cta": {
        "he": "פתח את דף התשלום ב־PayBox", "en": "Open the PayBox payment page",
        "ru": "Открыть страницу оплаты PayBox", "fr": "Ouvrir la page de paiement PayBox",
        "ar": "افتح صفحة الدفع في PayBox",
    },
    "upgrade_pay.manual_bit_hint": {
        "he": "שלח ₪{amount} בביט, והפרטים יישלחו אליך בנפרד.",
        "en": "Send ₪{amount} via Bit, details will be sent to you separately.",
        "ru": "Отправьте ₪{amount} через Bit, детали будут отправлены вам отдельно.",
        "fr": "Envoyez ₪{amount} via Bit, les détails vous seront envoyés séparément.",
        "ar": "أرسل ₪{amount} عبر Bit, سيتم إرسال التفاصيل إليك بشكل منفصل.",
    },
    "upgrade_pay.already_paid": {
        "he": "התשלום כבר אושר.", "en": "Payment already confirmed.",
        "ru": "Оплата уже подтверждена.", "fr": "Paiement déjà confirmé.",
        "ar": "تم تأكيد الدفع بالفعل.",
    },
    "upgrade_pay.continue_cta": {
        "he": "המשך", "en": "Continue", "ru": "Продолжить", "fr": "Continuer", "ar": "متابعة",
    },
    "upgrade_pay.confirm_paid_cta": {
        "he": "שילמתי, תפתחו לי גישה", "en": "I've paid, confirm access",
        "ru": "Я оплатил(а), подтвердите доступ", "fr": "J'ai payé, confirmez l'accès",
        "ar": "لقد دفعت، أكّد الوصول",
    },
    "upgrade_pay.confirm_hint": {
        "he": "תלחץ רק אחרי שבאמת שילמת.",
        "en": "Only click after you've actually sent the payment.",
        "ru": "Нажимайте только после того, как действительно отправили платёж.",
        "fr": "Cliquez uniquement après avoir réellement envoyé le paiement.",
        "ar": "اضغط فقط بعد إرسال الدفعة فعليًا.",
    },
    "upgrade_success.paid_message": {
        "he": "התשלום התקבל, הגישה שלך פעילה!", "en": "Payment received, your access is active!",
        "ru": "Оплата получена, ваш доступ активен!", "fr": "Paiement reçu, votre accès est actif!",
        "ar": "تم استلام الدفع، وصولك نشط!",
    },
    "upgrade_success.view_apartments_cta": {
        "he": "לצפייה בדירות", "en": "View apartments", "ru": "Просмотр квартир",
        "fr": "Voir les appartements", "ar": "لعرض الشقق",
    },
    "upgrade_success.processing_message": {
        "he": "מעבדים את התשלום... הדף יתעדכן לבד בעוד כמה שניות.",
        "en": "Processing payment... the page will update automatically in a few seconds.",
        "ru": "Обрабатываем платёж... страница обновится автоматически через несколько секунд.",
        "fr": "Traitement du paiement... la page se mettra à jour automatiquement dans quelques secondes.",
        "ar": "جارٍ معالجة الدفع... سيتم تحديث الصفحة تلقائيًا خلال ثوانٍ.",
    },
    "upgrade_success.back_to_upgrade_cta": {
        "he": "חזרה לדף השדרוג", "en": "Back to upgrade page", "ru": "Вернуться на страницу улучшения",
        "fr": "Retour à la page de mise à niveau", "ar": "العودة إلى صفحة الترقية",
    },
}

PROPERTY_TYPE_LABELS: dict[str, dict[str, str]] = {
    "he": {
        "apartment": "דירה", "garden_apartment": "דירת גן", "penthouse": "פנטהאוז",
        "studio": "סטודיו", "housing_unit": "יחידת דיור", "private_house": "בית פרטי",
        "shared_room": "חדר בדירת שותפים",
    },
    "en": {
        "apartment": "Apartment", "garden_apartment": "Garden apartment", "penthouse": "Penthouse",
        "studio": "Studio", "housing_unit": "Housing unit", "private_house": "Private house",
        "shared_room": "Room in a shared apartment",
    },
    "ru": {
        "apartment": "Квартира", "garden_apartment": "Квартира с садом", "penthouse": "Пентхаус",
        "studio": "Студия", "housing_unit": "Жилая единица", "private_house": "Частный дом",
        "shared_room": "Комната в общей квартире",
    },
    "fr": {
        "apartment": "Appartement", "garden_apartment": "Appartement avec jardin", "penthouse": "Penthouse",
        "studio": "Studio", "housing_unit": "Unité de logement", "private_house": "Maison privée",
        "shared_room": "Chambre en colocation",
    },
    "ar": {
        "apartment": "شقة", "garden_apartment": "شقة حديقة", "penthouse": "بنتهاوس",
        "studio": "استوديو", "housing_unit": "وحدة سكنية", "private_house": "بيت خاص",
        "shared_room": "غرفة في شقة مشتركة",
    },
}

SAFE_ROOM_LABELS: dict[str, dict[str, str]] = {
    "he": {"any": "לא משנה", "safe_room_only": "רק ממ״ד", "safe_room_or_shelter": "ממ״ד או מקלט בבניין"},
    "en": {"any": "Doesn't matter", "safe_room_only": "Safe room only", "safe_room_or_shelter": "Safe room or building shelter"},
    "ru": {"any": "Неважно", "safe_room_only": "Только бомбоубежище", "safe_room_or_shelter": "Бомбоубежище или укрытие в здании"},
    "fr": {"any": "Peu importe", "safe_room_only": "Abri uniquement", "safe_room_or_shelter": "Abri ou refuge dans l'immeuble"},
    "ar": {"any": "غير مهم", "safe_room_only": "غرفة آمنة فقط", "safe_room_or_shelter": "غرفة آمنة أو ملجأ في المبنى"},
}

FURNITURE_LABELS: dict[str, dict[str, str]] = {
    "he": {"any": "לא משנה", "furnished": "מרוהטת", "unfurnished": "לא מרוהטת"},
    "en": {"any": "Doesn't matter", "furnished": "Furnished", "unfurnished": "Unfurnished"},
    "ru": {"any": "Неважно", "furnished": "С мебелью", "unfurnished": "Без мебели"},
    "fr": {"any": "Peu importe", "furnished": "Meublé", "unfurnished": "Non meublé"},
    "ar": {"any": "غير مهم", "furnished": "مفروشة", "unfurnished": "غير مفروشة"},
}


def get_lang(request: Request, known_lang: str | None = None) -> str:
    """?lang= wins for this request (and main.py persists it to a cookie on the response);
    otherwise a previously-set cookie (an explicit choice made earlier on this same browser);
    otherwise `known_lang` — the viewer's own language on file (User.language), passed in by a
    caller that already resolved a real user via uid — otherwise Hebrew.

    2026-10-17 (owner, launch day): the browser's Accept-Language is no longer used. A visitor from
    Instagram's in-app browser on a phone set to English got the whole site in English; the owner wants
    Hebrew for everyone until they pick another language themselves (the switcher sets the cookie).

    2026-09-29: a Telegram user with the bot set to Hebrew opening their own link from Telegram's in-app
    browser must get Hebrew - `known_lang` carries that on-file preference; an explicit ?lang= or an
    earlier cookie choice on this browser still comes first."""
    candidate = request.query_params.get("lang") or request.cookies.get("lang")
    if candidate in SUPPORTED_LANGS:
        return candidate
    if known_lang in SUPPORTED_LANGS:
        return known_lang
    return DEFAULT_LANG


def make_translator(lang: str):
    def t(key: str, **kwargs) -> str:
        entry = TRANSLATIONS.get(key)
        if entry is None:
            return key
        text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
        return text.format(**kwargs) if kwargs else text

    return t


def relative_time_label(posted_at: dt.datetime | None, lang: str) -> str:
    """"עלתה לפני X שניות/דקות/שעות/ימים" (2026-09-02 request) — replaces the old fixed dd/mm
    date on a listing card with how long ago it was posted, in the largest whole unit that fits
    (seconds under a minute, minutes under an hour, hours under a day, otherwise days)."""
    if posted_at is None:
        return ""
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=dt.timezone.utc)
    seconds = max(0, int((dt.datetime.now(dt.timezone.utc) - posted_at).total_seconds()))

    if seconds < 60:
        key, n = "card.posted_ago_seconds", seconds
    elif seconds < 3600:
        key, n = "card.posted_ago_minutes", seconds // 60
    elif seconds < 86400:
        key, n = "card.posted_ago_hours", seconds // 3600
    else:
        key, n = "card.posted_ago_days", seconds // 86400

    return make_translator(lang)(key, n=n)


# --- 2026-10-19: the redesigned home page (templates/home.html, static/home.js) ---------------------------------------
# Kept apart from "home.*", which the classic React home page (templates/home_classic.html) still reads.
TRANSLATIONS.update({
    "landing.h1": {"he": "הדירות באות אליך", "en": "The flats come to you", "ru": "Квартиры сами приходят к вам",
                   "fr": "Les appartements viennent à vous", "ar": "الشقق تأتي إليك"},
    "landing.lede": {
        "he": "כותבים לבוט מה מחפשים, במילים שלכם. מאותו רגע כל דירה חדשה שמתאימה נשלחת אליכם לטלגרם.",
        "en": "Tell the bot what you're looking for, in your own words. From then on, every new flat that fits is sent to you on Telegram.",
        "ru": "Напишите боту своими словами, что вы ищете. С этого момента каждая новая подходящая квартира приходит вам в Telegram.",
        "fr": "Dites au bot ce que vous cherchez, avec vos mots. Dès lors, chaque nouvel appartement qui vous correspond vous est envoyé sur Telegram.",
        "ar": "اكتبوا للبوت ما تبحثون عنه بكلماتكم. ومن تلك اللحظة تصلكم كل شقة جديدة مناسبة على تيليغرام.",
    },
    "landing.cta": {"he": "פתיחת הבוט בטלגרם", "en": "Open the bot in Telegram", "ru": "Открыть бота в Telegram",
                    "fr": "Ouvrir le bot dans Telegram", "ar": "افتحوا البوت في تيليغرام"},
    "landing.how_link": {"he": "איך זה עובד", "en": "How it works", "ru": "Как это работает", "fr": "Comment ça marche",
                         "ar": "كيف يعمل"},
    "landing.trial_note": {"he": "10 ימים ראשונים בחינם, בלי כרטיס אשראי.", "en": "First 10 days free, no credit card.",
                           "ru": "Первые 10 дней бесплатно, без банковской карты.",
                           "fr": "Les 10 premiers jours sont gratuits, sans carte bancaire.",
                           "ar": "أول 10 أيام مجانًا، بدون بطاقة ائتمان."},
    "landing.hero_img_alt": {"he": "טודי המלך, בוט חיפוש דירות טודירה", "en": "Todi the king, Todira's flat-hunting bot",
                             "ru": "Король Тоди, бот поиска квартир Тодира", "fr": "Todi le roi, le bot de recherche d'appartements Todira",
                             "ar": "الملك تودي، بوت البحث عن الشقق توديرا"},
    "landing.notif_now": {"he": "עכשיו", "en": "now", "ru": "сейчас", "fr": "maintenant", "ar": "الآن"},
    "landing.notif_title": {"he": "דירה חדשה ב{city}", "en": "New flat in {city}", "ru": "Новая квартира: {city}",
                            "fr": "Nouvel appartement à {city}", "ar": "شقة جديدة في {city}"},
    "landing.notif_detail": {"he": "{rooms}, {price} ₪ לחודש", "en": "{rooms}, ₪{price} a month", "ru": "{rooms}, {price} ₪ в месяц",
                             "fr": "{rooms}, {price} ₪ par mois", "ar": "{rooms}، {price} ₪ شهريًا"},
    "landing.rooms_n": {"he": "{n} חדרים", "en": "{n} rooms", "ru": "{n} комн.", "fr": "{n} pièces", "ar": "{n} غرف"},
    "landing.rooms_1": {"he": "חדר אחד", "en": "1 room", "ru": "1 комната", "fr": "1 pièce", "ar": "غرفة واحدة"},
    "landing.live_pre": {"he": "ביממה האחרונה נכנסו", "en": "In the last 24 hours,", "ru": "За последние сутки появилось",
                         "fr": "Ces dernières 24 heures,", "ar": "خلال آخر 24 ساعة دخلت"},
    "landing.live_mid": {"he": "דירות חדשות, ב־", "en": "new flats came in, across", "ru": "новых квартир в",
                         "fr": "nouveaux appartements sont arrivés, dans", "ar": "شقة جديدة، في"},
    "landing.live_post": {"he": "ערים ויישובים", "en": "cities and towns", "ru": "городах и поселках",
                          "fr": "villes et localités", "ar": "مدينة وبلدة"},
    "landing.legend_new": {"he": "דירה חדשה מהיממה האחרונה", "en": "New in the last 24 hours", "ru": "Новые за последние сутки",
                           "fr": "Nouveaux depuis 24 heures", "ar": "جديدة خلال آخر 24 ساعة"},
    "landing.legend_old": {"he": "דירות שכבר במערכת", "en": "Already in the system", "ru": "Уже в системе",
                           "fr": "Déjà dans le système", "ar": "موجودة في النظام"},
    "landing.feed_label": {"he": "דירות שנכנסו עכשיו", "en": "Flats that just came in", "ru": "Только что появившиеся квартиры",
                           "fr": "Appartements qui viennent d'arriver", "ar": "شقق دخلت الآن"},
    "landing.feed_note": {"he": "המפה והמספרים מתעדכנים מהמערכת.", "en": "The map and the numbers update from the system.",
                          "ru": "Карта и цифры обновляются из системы.", "fr": "La carte et les chiffres se mettent à jour depuis le système.",
                          "ar": "الخريطة والأرقام تتحدث من النظام."},
    "landing.map_label": {"he": "מפת ישראל עם הדירות שבמערכת", "en": "Map of Israel with the flats in the system",
                          "ru": "Карта Израиля с квартирами в системе", "fr": "Carte d'Israël avec les appartements du système",
                          "ar": "خريطة إسرائيل مع الشقق في النظام"},
    "landing.city_haifa": {"he": "חיפה", "en": "Haifa", "ru": "Хайфа", "fr": "Haïfa", "ar": "حيفا"},
    "landing.city_tel_aviv": {"he": "תל אביב", "en": "Tel Aviv", "ru": "Тель-Авив", "fr": "Tel Aviv", "ar": "تل أبيب"},
    "landing.city_jerusalem": {"he": "ירושלים", "en": "Jerusalem", "ru": "Иерусалим", "fr": "Jérusalem", "ar": "القدس"},
    "landing.city_beer_sheva": {"he": "באר שבע", "en": "Beersheba", "ru": "Беэр-Шева", "fr": "Beer-Sheva", "ar": "بئر السبع"},
    "landing.city_eilat": {"he": "אילת", "en": "Eilat", "ru": "Эйлат", "fr": "Eilat", "ar": "إيلات"},
    "landing.step1_title": {"he": "כותבים לבוט מה מחפשים", "en": "Tell the bot what you want", "ru": "Напишите боту, что ищете",
                            "fr": "Dites au bot ce que vous voulez", "ar": "اكتبوا للبوت ما تبحثون عنه"},
    "landing.step1_body": {"he": "במילים שלכם, כמו לחבר. בלי טפסים ובלי תפריטים.", "en": "In your own words, like to a friend. No forms, no menus.",
                           "ru": "Своими словами, как другу. Без форм и меню.", "fr": "Avec vos mots, comme à un ami. Sans formulaires ni menus.",
                           "ar": "بكلماتكم، كما لصديق. بلا نماذج وبلا قوائم."},
    "landing.step2_title": {"he": "הבוט בונה לכם סינון", "en": "The bot builds your filter", "ru": "Бот настраивает фильтр",
                            "fr": "Le bot crée votre filtre", "ar": "البوت يبني لكم الفلتر"},
    "landing.step2_body": {"he": "עיר, מחיר, חדרים וכל מה שביקשתם. אפשר לשנות בכל רגע, בבוט או באתר.",
                           "en": "City, price, rooms and whatever else you asked for. Change it any time, in the bot or on the site.",
                           "ru": "Город, цена, комнаты и всё, что вы просили. Можно изменить в любой момент, в боте или на сайте.",
                           "fr": "Ville, prix, pièces et tout ce que vous avez demandé. Modifiable à tout moment, dans le bot ou sur le site.",
                           "ar": "المدينة والسعر والغرف وكل ما طلبتم. يمكن التغيير في أي وقت، في البوت أو في الموقع."},
    "landing.step3_title": {"he": "עולה דירה מתאימה, היא אצלכם", "en": "A matching flat goes up, you have it",
                            "ru": "Появилась подходящая квартира, она уже у вас", "fr": "Un appartement qui vous correspond, il est à vous",
                            "ar": "تُنشر شقة مناسبة، فتصلكم"},
    "landing.step3_body": {"he": "עם תמונות, מחיר, חדרים ומיקום במפה. שומרים, מסתירים, או מסמנים שמצאתם.",
                           "en": "With photos, price, rooms and its place on the map. Save it, hide it, or mark that you found one.",
                           "ru": "С фото, ценой, комнатами и местом на карте. Сохраняйте, скрывайте или отметьте, что нашли.",
                           "fr": "Avec photos, prix, pièces et emplacement sur la carte. Enregistrez, masquez, ou indiquez que vous avez trouvé.",
                           "ar": "مع الصور والسعر والغرف والموقع على الخريطة. احفظوا، أخفوا، أو أشيروا أنكم وجدتم."},
    "landing.demo_bot": {"he": "בוט", "en": "bot", "ru": "бот", "fr": "bot", "ar": "بوت"},
    "landing.demo_got": {"he": "הבנתי, מחפש לך:", "en": "Got it, looking for:", "ru": "Понял, ищу:", "fr": "Compris, je cherche :",
                         "ar": "فهمت، أبحث لك عن:"},
    "landing.demo_label": {"he": "דוגמה לשיחה עם הבוט", "en": "An example chat with the bot", "ru": "Пример переписки с ботом",
                           "fr": "Exemple de conversation avec le bot", "ar": "مثال على محادثة مع البوت"},
    # five example chats the demo walks through; chips are "|"-separated
    "landing.demo1_ask": {"he": "3 חדרים ברמת גן עד 7,500, עם מרפסת", "en": "3 rooms in Ramat Gan up to 7,500, with a balcony",
                          "ru": "3 комнаты в Рамат-Гане до 7 500, с балконом", "fr": "3 pièces à Ramat Gan jusqu'à 7 500, avec balcon",
                          "ar": "3 غرف في رمات غان حتى 7,500، مع شرفة"},
    "landing.demo1_chips": {"he": "רמת גן|3 חדרים|עד 7,500 ₪|מרפסת", "en": "Ramat Gan|3 rooms|up to ₪7,500|balcony",
                            "ru": "Рамат-Ган|3 комнаты|до 7 500 ₪|балкон", "fr": "Ramat Gan|3 pièces|jusqu'à 7 500 ₪|balcon",
                            "ar": "رمات غان|3 غرف|حتى 7,500 ₪|شرفة"},
    "landing.demo1_street": {"he": "רחוב ביאליק, רמת גן", "en": "Bialik St, Ramat Gan", "ru": "ул. Бялик, Рамат-Ган",
                             "fr": "rue Bialik, Ramat Gan", "ar": "شارع بياليك، رمات غان"},
    "landing.demo2_ask": {"he": "2 חדרים בחיפה עד 4,000, אפשר עם כלב", "en": "2 rooms in Haifa up to 4,000, dog allowed",
                          "ru": "2 комнаты в Хайфе до 4 000, можно с собакой", "fr": "2 pièces à Haïfa jusqu'à 4 000, chien accepté",
                          "ar": "غرفتان في حيفا حتى 4,000، مع كلب"},
    "landing.demo2_chips": {"he": "חיפה|2 חדרים|עד 4,000 ₪|חיות מחמד", "en": "Haifa|2 rooms|up to ₪4,000|pets",
                            "ru": "Хайфа|2 комнаты|до 4 000 ₪|животные", "fr": "Haïfa|2 pièces|jusqu'à 4 000 ₪|animaux",
                            "ar": "حيفا|غرفتان|حتى 4,000 ₪|حيوانات أليفة"},
    "landing.demo2_street": {"he": "שדרות מוריה, חיפה", "en": "Moriah Blvd, Haifa", "ru": "бульвар Мория, Хайфа",
                             "fr": "boulevard Moriah, Haïfa", "ar": "جادة موريا، حيفا"},
    "landing.demo3_ask": {"he": "סאבלט בתל אביב לחודש, עד 6,000", "en": "A sublet in Tel Aviv for a month, up to 6,000",
                          "ru": "Субаренда в Тель-Авиве на месяц, до 6 000", "fr": "Une sous-location à Tel Aviv pour un mois, jusqu'à 6 000",
                          "ar": "إيجار من الباطن في تل أبيب لشهر، حتى 6,000"},
    "landing.demo3_chips": {"he": "תל אביב|סאבלט|עד 6,000 ₪", "en": "Tel Aviv|sublet|up to ₪6,000",
                            "ru": "Тель-Авив|субаренда|до 6 000 ₪", "fr": "Tel Aviv|sous-location|jusqu'à 6 000 ₪",
                            "ar": "تل أبيب|من الباطن|حتى 6,000 ₪"},
    "landing.demo3_street": {"he": "רחוב פלורנטין, תל אביב", "en": "Florentin St, Tel Aviv", "ru": "ул. Флорентин, Тель-Авив",
                             "fr": "rue Florentin, Tel Aviv", "ar": "شارع فلورنتين، تل أبيب"},
    "landing.demo4_ask": {"he": "4 חדרים בבאר שבע עד 5,000, עם חניה", "en": "4 rooms in Beersheba up to 5,000, with parking",
                          "ru": "4 комнаты в Беэр-Шеве до 5 000, с парковкой", "fr": "4 pièces à Beer-Sheva jusqu'à 5 000, avec parking",
                          "ar": "4 غرف في بئر السبع حتى 5,000، مع موقف سيارة"},
    "landing.demo4_chips": {"he": "באר שבע|4 חדרים|עד 5,000 ₪|חניה", "en": "Beersheba|4 rooms|up to ₪5,000|parking",
                            "ru": "Беэр-Шева|4 комнаты|до 5 000 ₪|парковка", "fr": "Beer-Sheva|4 pièces|jusqu'à 5 000 ₪|parking",
                            "ar": "بئر السبع|4 غرف|حتى 5,000 ₪|موقف"},
    "landing.demo4_street": {"he": "רחוב רגר, באר שבע", "en": "Rager Blvd, Beersheba", "ru": "ул. Рагер, Беэр-Шева",
                             "fr": "boulevard Rager, Beer-Sheva", "ar": "شارع راغر، بئر السبع"},
    "landing.demo5_ask": {"he": "לקנות 4 חדרים בירושלים עד 3 מיליון", "en": "Buy 4 rooms in Jerusalem up to 3 million",
                          "ru": "Купить 4 комнаты в Иерусалиме до 3 миллионов", "fr": "Acheter un 4 pièces à Jérusalem jusqu'à 3 millions",
                          "ar": "شراء 4 غرف في القدس حتى 3 ملايين"},
    "landing.demo5_chips": {"he": "ירושלים|קנייה|4 חדרים|עד 3,000,000 ₪", "en": "Jerusalem|buy|4 rooms|up to ₪3,000,000",
                            "ru": "Иерусалим|покупка|4 комнаты|до 3 000 000 ₪", "fr": "Jérusalem|achat|4 pièces|jusqu'à 3 000 000 ₪",
                            "ar": "القدس|شراء|4 غرف|حتى 3,000,000 ₪"},
    "landing.demo5_street": {"he": "רחוב עמק רפאים, ירושלים", "en": "Emek Refaim St, Jerusalem", "ru": "ул. Эмек Рефаим, Иерусалим",
                             "fr": "rue Emek Refaim, Jérusalem", "ar": "شارع عيمق رفائيم، القدس"},
    "landing.price_title": {"he": "כמה זה עולה", "en": "What it costs", "ru": "Сколько это стоит", "fr": "Combien ça coûte",
                            "ar": "كم يكلف"},
    "landing.price_p1": {
        "he": "10 הימים הראשונים בחינם. אחר כך בוחרים לכמה זמן צריך, ומשלמים פעם אחת דרך תקבול, בביט או באשראי.",
        "en": "The first 10 days are free. After that you pick how long you need and pay once through Takbull, with Bit or a credit card.",
        "ru": "Первые 10 дней бесплатно. Потом выбираете нужный срок и платите один раз через Takbull, через Bit или картой.",
        "fr": "Les 10 premiers jours sont gratuits. Ensuite vous choisissez la durée et payez une seule fois via Takbull, par Bit ou carte bancaire.",
        "ar": "أول 10 أيام مجانًا. بعدها تختارون المدة وتدفعون مرة واحدة عبر Takbull، ببيت أو ببطاقة ائتمان.",
    },
    "landing.price_p2": {"he": "אין חידוש אוטומטי, ונזכיר לכם לפני שהגישה נגמרת.",
                         "en": "Nothing renews on its own, and we remind you before your access ends.",
                         "ru": "Автопродления нет, и мы напомним до окончания доступа.",
                         "fr": "Pas de renouvellement automatique, et on vous prévient avant la fin de l'accès.",
                         "ar": "لا يوجد تجديد تلقائي، وسنذكّركم قبل انتهاء الوصول."},
    "landing.per_day": {"he": "{price} ₪ ליום", "en": "₪{price} a day", "ru": "{price} ₪ в день", "fr": "{price} ₪ par jour",
                        "ar": "{price} ₪ يوميًا"},
    "landing.faq_title": {"he": "שאלות", "en": "Questions", "ru": "Вопросы", "fr": "Questions", "ar": "أسئلة"},
    "landing.end_title": {"he": "טודי כבר מחפש", "en": "Todi is already looking", "ru": "Тоди уже ищет",
                          "fr": "Todi cherche déjà", "ar": "تودي يبحث بالفعل"},
})
