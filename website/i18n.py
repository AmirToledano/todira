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
        "he": "טודירה — חיפוש דירות בזמן אמת",
        "en": "Todira — real-time apartment search",
        "ru": "Todira — поиск квартир в реальном времени",
        "fr": "Todira — recherche d'appartements en temps réel",
        "ar": "توديرا — بحث عن شقق في الوقت الفعلي",
    },
    "meta.description": {
        "he": "בוט חיפוש דירות אישי שסורק את שוק הדירות ומתריע לך ברגע שמופיעה דירה שמתאימה בדיוק לסינון שלך.",
        "en": "A personal apartment-search bot that scans the market non-stop and alerts you the moment a listing matches your exact filter.",
        "ru": "Персональный бот для поиска квартир, который непрерывно сканирует рынок и уведомляет вас, как только появляется подходящее объявление.",
        "fr": "Un bot de recherche d'appartements personnel qui scanne le marché en continu et vous alerte dès qu'une annonce correspond exactement à vos critères.",
        "ar": "بوت بحث شقق شخصي يفحص السوق باستمرار وينبهك فور ظهور إعلان يطابق بالضبط الفلتر الخاص بك.",
    },
    "meta.title_apartments": {
        "he": "דירות תואמות — טודירה",
        "en": "Matching apartments — Todira",
        "ru": "Подходящие квартиры — Todira",
        "fr": "Appartements correspondants — Todira",
        "ar": "شقق مطابقة — توديرا",
    },
    "meta.title_liked": {
        "he": "דירות שמורות — טודירה",
        "en": "Saved apartments — Todira",
        "ru": "Сохранённые квартиры — Todira",
        "fr": "Appartements enregistrés — Todira",
        "ar": "شقق محفوظة — توديرا",
    },
    "meta.title_hidden": {
        "he": "דירות מוסתרות — טודירה",
        "en": "Hidden apartments — Todira",
        "ru": "Скрытые квартиры — Todira",
        "fr": "Appartements masqués — Todira",
        "ar": "شقق مخفية — توديرا",
    },
    "meta.title_filter": {
        "he": "הסינון שלי — טודירה",
        "en": "My filter — Todira",
        "ru": "Мой фильтр — Todira",
        "fr": "Mon filtre — Todira",
        "ar": "الفلتر الخاص بي — توديرا",
    },
    "meta.title_404": {
        "he": "הדף לא נמצא — טודירה",
        "en": "Page not found — Todira",
        "ru": "Страница не найдена — Todira",
        "fr": "Page introuvable — Todira",
        "ar": "الصفحة غير موجودة — توديرا",
    },
    "meta.title_generic": {
        "he": "טודירה",
        "en": "Todira",
        "ru": "Todira",
        "fr": "Todira",
        "ar": "توديرا",
    },
    "meta.title_terms": {
        "he": "תנאי שימוש — טודירה",
        "en": "Terms of Use — Todira",
        "ru": "Условия использования — Todira",
        "fr": "Conditions d'utilisation — Todira",
        "ar": "شروط الاستخدام — توديرا",
    },
    "meta.title_privacy": {
        "he": "מדיניות פרטיות — טודירה",
        "en": "Privacy Policy — Todira",
        "ru": "Политика конфиденциальности — Todira",
        "fr": "Politique de confidentialité — Todira",
        "ar": "سياسة الخصوصية — توديرا",
    },
    "meta.title_accessibility": {
        "he": "הצהרת נגישות — טודירה",
        "en": "Accessibility Statement — Todira",
        "ru": "Заявление о доступности — Todira",
        "fr": "Déclaration d'accessibilité — Todira",
        "ar": "بيان إمكانية الوصول — توديرا",
    },
    "meta.title_contact": {
        "he": "צור קשר — טודירה",
        "en": "Contact us — Todira",
        "ru": "Связаться с нами — Todira",
        "fr": "Nous contacter — Todira",
        "ar": "تواصل معنا — توديرا",
    },
    "meta.title_account": {
        "he": "החשבון שלי — טודירה",
        "en": "My Account — Todira",
        "ru": "Мой аккаунт — Todira",
        "fr": "Mon compte — Todira",
        "ar": "حسابي — توديرا",
    },
    "meta.title_login": {
        "he": "התחברות — טודירה", "en": "Login — Todira", "ru": "Вход — Todira",
        "fr": "Connexion — Todira", "ar": "تسجيل الدخول — توديرا",
    },
    "meta.title_google_pending": {
        "he": "כמעט שם — טודירה", "en": "Almost there — Todira", "ru": "Почти готово — Todira",
        "fr": "Presque terminé — Todira", "ar": "أوشكنا على الانتهاء — توديرا",
    },
    "meta.title_upgrade": {
        "he": "שדרוג המנוי — טודירה", "en": "Upgrade subscription — Todira",
        "ru": "Улучшение подписки — Todira", "fr": "Mise à niveau de l'abonnement — Todira",
        "ar": "ترقية الاشتراك — توديرا",
    },
    "meta.title_upgrade_pay": {
        "he": "תשלום — טודירה", "en": "Payment — Todira", "ru": "Оплата — Todira",
        "fr": "Paiement — Todira", "ar": "الدفع — توديرا",
    },
    "meta.title_upgrade_success": {
        "he": "תודה — טודירה", "en": "Thank you — Todira", "ru": "Спасибо — Todira",
        "fr": "Merci — Todira", "ar": "شكرًا — توديرا",
    },
    # ---------- header / nav ----------
    "nav.apartments": {
        "he": "דירות", "en": "Apartments", "ru": "Квартиры", "fr": "Appartements", "ar": "الشقق",
    },
    "nav.brand_home_hint": {
        "he": "(לעמוד הבית)", "en": "(home page)", "ru": "(на главную)",
        "fr": "(page d'accueil)", "ar": "(الصفحة الرئيسية)",
    },
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
    "nav.whatsapp": {
        "he": "הבוט בוואטסאפ", "en": "The WhatsApp bot", "ru": "Бот в WhatsApp",
        "fr": "Le bot WhatsApp", "ar": "بوت واتساب",
    },
    # The opening message pre-filled into a wa.me deep link's own text= param — found live
    # 2026-09-07: this was hardcoded in Hebrew in 3 separate templates (home.html x2, login.html)
    # instead of going through t(), so an English/Russian/French/Arabic visitor's WhatsApp CTA
    # button opened a chat pre-filled with Hebrew text they may not have written themselves.
    "whatsapp.greeting": {
        "he": "היי! אני רוצה להתחיל לחפש דירה 🏠",
        "en": "Hi! I'd like to start looking for an apartment 🏠",
        "ru": "Привет! Я хочу начать искать квартиру 🏠",
        "fr": "Salut ! Je voudrais commencer à chercher un appartement 🏠",
        "ar": "مرحبًا! أريد أن أبدأ البحث عن شقة 🏠",
    },
    "nav.contact": {
        "he": "צור קשר", "en": "Contact us", "ru": "Связаться с нами",
        "fr": "Nous contacter", "ar": "تواصل معنا",
    },
    "nav.account": {
        "he": "החשבון שלי 👤", "en": "My account 👤", "ru": "Мой аккаунт 👤",
        "fr": "Mon compte 👤", "ar": "حسابي 👤",
    },
    "auth.you": {
        "he": "מחובר/ת", "en": "Logged in", "ru": "Вы вошли", "fr": "Connecté(e)", "ar": "تم تسجيل الدخول",
    },
    "auth.logout": {
        "he": "התנתקות", "en": "Log out", "ru": "Выйти", "fr": "Se déconnecter", "ar": "تسجيل الخروج",
    },
    "auth.login": {
        "he": "הרשמה / התחברות", "en": "Sign up / Log in", "ru": "Регистрация / Вход",
        "fr": "Inscription / Connexion", "ar": "التسجيل / تسجيل الدخول",
    },
    "auth.link_google": {
        "he": "קשר את Google לחשבון 🔗", "en": "Link your Google account 🔗", "ru": "Привязать аккаунт Google 🔗",
        "fr": "Lier votre compte Google 🔗", "ar": "ربط حساب Google 🔗",
    },
    "auth.error_body": {
        "he": "לא הצלחנו לאמת את ההתחברות. אפשר לנסות שוב.",
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
    "footer.copyright": {
        "he": "© 2026 טודירה. כל הזכויות שמורות.",
        "en": "© 2026 Todira. All rights reserved.",
        "ru": "© 2026 Todira. Все права защищены.",
        "fr": "© 2026 Todira. Tous droits réservés.",
        "ar": "© 2026 توديرا. جميع الحقوق محفوظة.",
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
        # 2026-09-08 fix (owner's own report): used to say "via Telegram" specifically, which
        # became inaccurate once WhatsApp shipped as an equal channel (see the WhatsApp CTA
        # button right below this) — channel-neutral now instead of naming just one.
        "he": "דירות בזמן אמת · טלגרם + ווטסאפ 👑",
        "en": "Real-time apartments · Telegram + WhatsApp 👑",
        "ru": "Квартиры в реальном времени · Telegram + WhatsApp 👑",
        "fr": "Appartements en temps réel · Telegram + WhatsApp 👑",
        "ar": "شقق في الوقت الفعلي · تيليجرام + واتساب 👑",
    },
    "home.h1": {
        "he": "הדירה שלך מוצאת אותך",
        "en": "Your apartment finds you",
        "ru": "Ваша квартира сама вас найдёт",
        "fr": "Votre appartement vous trouve",
        "ar": "شقتك تجدك",
    },
    "home.lead": {
        "he": "טודירה סורק את שוק הדירות בלי הפסקה, ומתריע לך תוך דקות ברגע שעולה דירה שמתאימה בדיוק למה שחיפשת — לפני שמישהו אחר יתפוס אותה.",
        "en": "Todira scans the apartment market non-stop, and alerts you within minutes the moment a listing matches exactly what you're looking for — before someone else grabs it.",
        "ru": "Todira непрерывно сканирует рынок квартир и уведомляет вас в течение нескольких минут, как только появляется объявление, точно соответствующее вашему запросу — прежде чем его займёт кто-то другой.",
        "fr": "Todira scanne le marché des appartements sans interruption et vous alerte en quelques minutes dès qu'une annonce correspond exactement à ce que vous cherchez — avant que quelqu'un d'autre ne la prenne.",
        "ar": "توديرا يفحص سوق الشقق بلا توقف، وينبهك خلال دقائق فور ظهور شقة تطابق تمامًا ما تبحث عنه — قبل أن يسبقك إليها شخص آخر.",
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
        "fr": "Comment ça marche ?", "ar": "كيف يعمل؟",
    },
    "home.cta_open_whatsapp": {
        "he": "המשך בווטסאפ", "en": "Continue on WhatsApp",
        "ru": "Продолжить в WhatsApp", "fr": "Continuer sur WhatsApp",
        "ar": "تابع عبر واتساب",
    },
    "home.hero_img_alt": {
        "he": "טודי המלך — בוט חיפוש דירות טודירה",
        "en": "King Todi — the Todira apartment-search bot",
        "ru": "Король Тоди — бот поиска квартир Todira",
        "fr": "Le roi Todi — le bot de recherche d'appartements Todira",
        "ar": "الملك تودي — بوت البحث عن شقق توديرا",
    },
    "home.stat_scan_freq_value": {"he": "כל שעתיים", "en": "Every 2h", "ru": "Каждые 2 ч", "fr": "Toutes les 2h", "ar": "كل ساعتين"},
    "home.stat_scan_freq_label": {
        "he": "תדירות סריקה", "en": "Scan frequency", "ru": "Частота сканирования",
        "fr": "Fréquence de scan", "ar": "تكرار الفحص",
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
    "home.stat_free_value": {"he": "3 ימים", "en": "3 days", "ru": "3 дня", "fr": "3 jours", "ar": "3 أيام"},
    "home.stat_free_label": {
        "he": "תקופת ניסיון", "en": "Trial period", "ru": "Пробный период",
        "fr": "Période d'essai", "ar": "فترة تجريبية",
    },
    "home.momentum_1_value": {
        "he": "הקהילה שלנו", "en": "Our community", "ru": "Наше сообщество",
        "fr": "Notre communauté", "ar": "مجتمعنا",
    },
    "home.momentum_1_label": {
        "he": "גדלה כל יום", "en": "Growing every day", "ru": "Растёт каждый день",
        "fr": "En croissance chaque jour", "ar": "ينمو كل يوم",
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
        "he": "כל אזורי יד2 במקום אחד", "en": "Every Yad2 region, in one place", "ru": "Все регионы Yad2 в одном месте",
        "fr": "Toutes les régions Yad2 réunies", "ar": "جميع مناطق يد2 في مكان واحد",
    },
    "home.live_badge": {
        "he": "התראות בזמן אמת 🔔", "en": "Real-time alerts 🔔", "ru": "Уведомления в реальном времени 🔔",
        "fr": "Alertes en temps réel 🔔", "ar": "تنبيهات فورية 🔔",
    },
    "home.example_badge_label": {
        "he": "לדוגמה", "en": "Example", "ru": "Пример", "fr": "Exemple", "ar": "مثال",
    },
    "home.example_card_title": {
        "he": "דירה חדשה!", "en": "New listing!", "ru": "Новое объявление!",
        "fr": "Nouvelle annonce !", "ar": "شقة جديدة!",
    },
    "home.example_card_sub": {
        "he": "תל אביב · 3 חדרים · 6,200 ₪",
        "en": "Tel Aviv · 3 rooms · ₪6,200",
        "ru": "Тель-Авив · 3 комнаты · 6,200 ₪",
        "fr": "Tel-Aviv · 3 pièces · 6 200 ₪",
        "ar": "تل أبيب · 3 غرف · 6,200 ₪",
    },
    "home.feature1_title": {
        "he": "מבין אותך בשפה חופשית",
        "en": "Understands you in plain language",
        "ru": "Понимает вас на естественном языке",
        "fr": "Vous comprend en langage naturel",
        "ar": "يفهمك بلغة طبيعية",
    },
    "home.feature1_body": {
        "he": "פשוט תכתוב מה אתה מחפש — \"2-3 חדרים בתל אביב עד 6000 שקל\" — ובינה מלאכותית מבינה ומגדירה את הסינון בשבילך, בלי טפסים מסובכים.",
        "en": "Just write what you're looking for in Hebrew — e.g. \"2-3 rooms in Tel Aviv, up to 6,000 ILS\" — and AI understands it and sets up the filter for you, no complicated forms.",
        "ru": "Просто напишите на иврите, что вы ищете — например, «2-3 комнаты в Тель-Авиве до 6000 шекелей» — и ИИ поймёт вас и настроит фильтр без сложных форм.",
        "fr": "Décrivez simplement ce que vous cherchez en hébreu — par ex. « 2-3 pièces à Tel-Aviv, jusqu'à 6 000 ILS » — et l'IA comprend et configure le filtre pour vous, sans formulaires compliqués.",
        "ar": "فقط اكتب ما تبحث عنه بالعبرية — مثلاً \"2-3 غرف في تل أبيب حتى 6000 شيكل\" — ويفهم الذكاء الاصطناعي طلبك ويضبط الفلتر نيابة عنك، بدون نماذج معقدة.",
    },
    # 2026-09-10 addition: a concrete before/after visual under feature1 — the same example
    # already quoted in feature1_body's own text, shown as an actual mini-demo (typed query ->
    # parsed chips) instead of only described in a sentence. Only the parsed-chip labels below are
    # real translation keys — the query text itself is a fixed Hebrew example (a real visitor
    # writes to the bot in Hebrew regardless of the UI language they're browsing in, matching
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
    "home.feature2_title": {
        "he": "התראות בזמן אמת", "en": "Real-time alerts", "ru": "Уведомления в реальном времени",
        "fr": "Alertes en temps réel", "ar": "تنبيهات فورية",
    },
    "home.feature2_body": {
        "he": "הסריקה רצה כל הזמן ברקע. ברגע שדירה חדשה תואמת עולה לרשת — אתה מקבל הודעה בטלגרם, לא צריך לרענן אתרים כל היום.",
        "en": "Scanning runs continuously in the background. The moment a new matching listing goes online, you get a Telegram message — no need to refresh sites all day.",
        "ru": "Сканирование работает непрерывно в фоне. Как только появляется новое подходящее объявление, вы получаете сообщение в Telegram — не нужно весь день обновлять сайты.",
        "fr": "Le scan tourne en continu en arrière-plan. Dès qu'une nouvelle annonce correspondante est publiée, vous recevez un message Telegram — plus besoin de rafraîchir des sites toute la journée.",
        "ar": "الفحص يعمل باستمرار في الخلفية. فور ظهور إعلان جديد مطابق على الشبكة، تصلك رسالة على تيليجرام — لا حاجة لتحديث المواقع طوال اليوم.",
    },
    "home.feature3_title": {
        "he": "שומר לך את הדירות שאהבת",
        "en": "Keeps the apartments you liked",
        "ru": "Сохраняет квартиры, которые вам понравились",
        "fr": "Enregistre les appartements que vous avez aimés",
        "ar": "يحفظ الشقق التي أعجبتك",
    },
    "home.feature3_body": {
        "he": "סמן דירות שמעניינות אותך ותחזור אליהן בקלות בכל שלב — כאן באתר או ישירות מתוך הבוט.",
        "en": "Mark apartments you're interested in and come back to them easily at any point — here on the site or straight from the bot.",
        "ru": "Отмечайте интересные квартиры и легко возвращайтесь к ним в любой момент — здесь на сайте или прямо в боте.",
        "fr": "Marquez les appartements qui vous intéressent et retrouvez-les facilement à tout moment — ici sur le site ou directement depuis le bot.",
        "ar": "علّم الشقق التي تهمك وارجع إليها بسهولة في أي وقت — هنا على الموقع أو مباشرة من داخل البوت.",
    },
    "home.compare_title": {
        "he": "למה לא פשוט לגלול לבד?",
        "en": "Why not just scroll on your own?",
        "ru": "Почему бы просто не искать самому?",
        "fr": "Pourquoi ne pas simplement chercher soi-même ?",
        "ar": "لماذا لا تكتفي بالتصفح بنفسك؟",
    },
    "home.compare_sub": {
        "he": "כי אתה עסוק, ודירות טובות נעלמות תוך שעות.",
        "en": "Because you're busy, and good apartments disappear within hours.",
        "ru": "Потому что вы заняты, а хорошие квартиры исчезают за считанные часы.",
        "fr": "Parce que vous êtes occupé, et les bons appartements disparaissent en quelques heures.",
        "ar": "لأنك مشغول، والشقق الجيدة تختفي خلال ساعات.",
    },
    "home.compare_without_title": {
        "he": "בלי טודירה 😩", "en": "Without Todira 😩", "ru": "Без Todira 😩",
        "fr": "Sans Todira 😩", "ar": "بدون توديرا 😩",
    },
    "home.compare_without_1": {
        "he": "מרעננים כמה אתרים כל כמה שעות",
        "en": "Refreshing several sites every few hours",
        "ru": "Обновляете несколько сайтов каждые несколько часов",
        "fr": "Rafraîchir plusieurs sites toutes les quelques heures",
        "ar": "تحديث عدة مواقع كل بضع ساعات",
    },
    "home.compare_without_2": {
        "he": "מפספסים דירות טובות שנתפסות עוד לפני שראיתם אותן",
        "en": "Missing good apartments that get taken before you even see them",
        "ru": "Упускаете хорошие квартиры, которые сдают ещё до того, как вы их увидели",
        "fr": "Rater de bons appartements pris avant même que vous les voyiez",
        "ar": "تفويت شقق جيدة تُحجز قبل أن تراها أصلًا",
    },
    "home.compare_without_3": {
        "he": "עוברים ידנית על עשרות מודעות לא רלוונטיות",
        "en": "Manually sifting through dozens of irrelevant listings",
        "ru": "Вручную просматриваете десятки нерелевантных объявлений",
        "fr": "Parcourir manuellement des dizaines d'annonces non pertinentes",
        "ar": "تصفح عشرات الإعلانات غير ذات الصلة يدويًا",
    },
    "home.compare_without_4": {
        "he": "שוכחים דירה ששמרתם בלשונית שנסגרה",
        "en": "Forgetting an apartment you saved in a tab you closed",
        "ru": "Забываете квартиру, сохранённую во вкладке, которую закрыли",
        "fr": "Oublier un appartement enregistré dans un onglet fermé",
        "ar": "نسيان شقة حفظتها في تبويب أغلقته",
    },
    "home.compare_with_title": {
        "he": "עם טודירה 👑", "en": "With Todira 👑", "ru": "С Todira 👑",
        "fr": "Avec Todira 👑", "ar": "مع توديرا 👑",
    },
    # 2026-09-10 fix: said "every 10 minutes" — stale copy from before the 2026-09-03 schedule
    # change (charts/todira/values.yaml's scraper.schedule is actually every 2 hours, 8:00-22:00
    # Israel time) and directly contradicted home.stat_scan_freq_value below it on the same page,
    # which already said the correct "כל שעתיים"/"Every 2h". Found by cross-checking the page's
    # own claims against each other, then against the real CronJob schedule.
    "home.compare_with_1": {
        "he": "סריקה אוטומטית כל שעתיים, ברקע",
        "en": "Automatic scanning every 2 hours, in the background",
        "ru": "Автоматическое сканирование каждые 2 часа в фоне",
        "fr": "Scan automatique toutes les 2 heures, en arrière-plan",
        "ar": "فحص تلقائي كل ساعتين في الخلفية",
    },
    "home.compare_with_2": {
        "he": "התראה מיידית בטלגרם ברגע שיש התאמה",
        "en": "Instant Telegram alert the moment there's a match",
        "ru": "Мгновенное уведомление в Telegram при совпадении",
        "fr": "Alerte Telegram instantanée dès qu'il y a une correspondance",
        "ar": "تنبيه فوري على تيليجرام فور وجود تطابق",
    },
    "home.compare_with_3": {
        "he": "רואים רק דירות שבאמת עומדות בסינון שלכם",
        "en": "You only see apartments that truly meet your filter",
        "ru": "Вы видите только квартиры, действительно соответствующие фильтру",
        "fr": "Vous ne voyez que les appartements qui correspondent vraiment à votre filtre",
        "ar": "لا ترى إلا الشقق التي تطابق فعلًا فلترك",
    },
    "home.compare_with_4": {
        "he": "כל דירה ששמרתם מחכה לכם כאן וגם בבוט",
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
        "he": "שלוש דקות התחלה, ואז טודירה עובד בשבילך ברקע.",
        "en": "Three minutes to get started, then Todira works for you in the background.",
        "ru": "Три минуты на старт — и дальше Todira работает за вас в фоне.",
        "fr": "Trois minutes pour démarrer, puis Todira travaille pour vous en arrière-plan.",
        "ar": "ثلاث دقائق للبدء، ثم يعمل توديرا من أجلك في الخلفية.",
    },
    "home.step1_title": {
        "he": "מדברים עם הבוט", "en": "Talk to the bot", "ru": "Общайтесь с ботом",
        "fr": "Discutez avec le bot", "ar": "تحدث مع البوت",
    },
    "home.step1_body": {
        "he": "פותחים שיחה בטלגרם ומתארים במילים שלכם את הדירה שאתם מחפשים.",
        "en": "Open a chat on Telegram and describe, in Hebrew and in your own words, the apartment you're looking for.",
        "ru": "Откройте чат в Telegram и опишите на иврите своими словами квартиру, которую вы ищете.",
        "fr": "Ouvrez une conversation sur Telegram et décrivez, en hébreu et avec vos propres mots, l'appartement que vous cherchez.",
        "ar": "افتح محادثة على تيليجرام وصف بالعبرية وبكلماتك الشقة التي تبحث عنها.",
    },
    "home.step2_title": {
        "he": "הסינון נבנה אוטומטית", "en": "The filter builds itself", "ru": "Фильтр строится автоматически",
        "fr": "Le filtre se construit automatiquement", "ar": "يُبنى الفلتر تلقائيًا",
    },
    "home.step2_body": {
        "he": "עיר, טווח מחיר, מספר חדרים ועוד — הכל נחלץ מהשיחה שלכם ונשמר כפרופיל חיפוש.",
        "en": "City, price range, number of rooms and more — it's all extracted from your conversation and saved as a search profile.",
        "ru": "Город, диапазон цен, количество комнат и многое другое — всё извлекается из вашего разговора и сохраняется как профиль поиска.",
        "fr": "Ville, fourchette de prix, nombre de pièces et plus — tout est extrait de votre conversation et enregistré comme profil de recherche.",
        "ar": "المدينة ونطاق السعر وعدد الغرف وأكثر — كل ذلك يُستخرج من محادثتك ويُحفظ كملف بحث.",
    },
    "home.step3_title": {
        "he": "מקבלים התראות", "en": "Get alerts", "ru": "Получайте уведомления",
        "fr": "Recevez des alertes", "ar": "احصل على تنبيهات",
    },
    "home.step3_body": {
        "he": "מרגע זה, כל דירה חדשה שמתאימה תשלח אליכם ישירות — וגם תופיע כאן באתר.",
        "en": "From this moment on, every new matching apartment is sent straight to you — and also shows up here on the site.",
        "ru": "С этого момента каждая новая подходящая квартира отправляется прямо вам — а также появляется здесь на сайте.",
        "fr": "Dès cet instant, chaque nouvel appartement correspondant vous est envoyé directement — et apparaît aussi ici sur le site.",
        "ar": "من هذه اللحظة، تُرسل إليك مباشرة كل شقة جديدة مطابقة — وتظهر أيضًا هنا على الموقع.",
    },
    "home.faq_title": {
        "he": "שאלות נפוצות", "en": "Frequently asked questions", "ru": "Часто задаваемые вопросы",
        "fr": "Questions fréquentes", "ar": "الأسئلة الشائعة",
    },
    "home.faq1_q": {
        "he": "איך הבינה המלאכותית מבינה מה אני מחפש?",
        "en": "How does the AI understand what I'm looking for?",
        "ru": "Как ИИ понимает, что я ищу?",
        "fr": "Comment l'IA comprend-elle ce que je cherche ?",
        "ar": "كيف يفهم الذكاء الاصطناعي ما أبحث عنه؟",
    },
    "home.faq1_a": {
        "he": "אתם כותבים לבוט בשפה חופשית, בדיוק כמו שהייתם מתארים לחבר מה אתם מחפשים. מודל שפה מזהה מתוך המשפט עיר, טווח מחיר, מספר חדרים ופרטים נוספים, ובונה מזה פרופיל חיפוש — בלי טפסים ובלי תפריטים מסובכים.",
        "en": "You write to the bot in plain Hebrew, just like you'd describe it to a friend. A language model picks out the city, price range, number of rooms and more from your sentence, and builds a search profile from it — no forms, no complicated menus.",
        "ru": "Вы пишете боту на иврите свободным текстом, как будто рассказываете другу. Языковая модель распознаёт город, диапазон цен, количество комнат и другие детали из вашего сообщения и строит на их основе профиль поиска — без форм и сложных меню.",
        "fr": "Vous écrivez au bot en hébreu, en langage libre, exactement comme vous le décririez à un ami. Un modèle de langage identifie dans votre phrase la ville, la fourchette de prix, le nombre de pièces et d'autres détails, puis construit un profil de recherche — sans formulaires ni menus compliqués.",
        "ar": "تكتب للبوت بالعبرية بلغة حرة، تمامًا كما لو كنت تصف الأمر لصديق. يحدد نموذج اللغة من جملتك المدينة ونطاق السعر وعدد الغرف وتفاصيل أخرى، ويبني منها ملف بحث — بدون نماذج أو قوائم معقدة.",
    },
    "home.faq2_q": {
        "he": "מאיפה מגיעות הדירות?", "en": "Where do the listings come from?",
        "ru": "Откуда берутся объявления?", "fr": "D'où viennent les annonces ?",
        "ar": "من أين تأتي الإعلانات؟",
    },
    "home.faq2_a": {
        "he": "טודירה סורק את שוק הדירות ברשת באופן אוטומטי כל שעתיים ומשווה כל מודעה חדשה מול הסינון שלכם. עוד מקורות מתווספים בהדרגה.",
        "en": "Todira automatically scans the apartment market online every 2 hours and compares every new listing against your filter. More sources are being added gradually.",
        "ru": "Todira автоматически сканирует рынок квартир в сети каждые 2 часа и сравнивает каждое новое объявление с вашим фильтром. Постепенно добавляются новые источники.",
        "fr": "Todira scanne automatiquement le marché des appartements en ligne toutes les 2 heures et compare chaque nouvelle annonce à votre filtre. D'autres sources sont ajoutées progressivement.",
        "ar": "يفحص توديرا سوق الشقق على الإنترنت تلقائيًا كل ساعتين ويقارن كل إعلان جديد بفلترك. تُضاف مصادر إضافية تدريجيًا.",
    },
    "home.faq3_q": {
        "he": "כמה זה עולה?", "en": "How much does it cost?", "ru": "Сколько это стоит?",
        "fr": "Combien ça coûte ?", "ar": "كم تكلفته؟",
    },
    "home.faq3_a": {
        "he": "יש תקופת ניסיון של 3 ימים, ואז מנוי החל מ-15 ₪ לשבוע (יש גם אפשרות לשבועיים או לחודש).",
        "en": "There's a 3-day trial period, then a subscription starting from ₪15/week (biweekly and monthly options are also available).",
        "ru": "Есть 3-дневный пробный период, затем подписка от 15 ₪ в неделю (доступны также варианты на две недели и на месяц).",
        "fr": "Il y a une période d'essai de 3 jours, puis un abonnement à partir de 15 ₪/semaine (options bihebdomadaire et mensuelle également disponibles).",
        "ar": "هناك فترة تجريبية مدتها 3 أيام، ثم اشتراك يبدأ من 15 ₪ أسبوعيًا (تتوفر أيضًا خيارات لأسبوعين أو لشهر).",
    },
    "home.faq4_q": {
        "he": "אפשר לשנות את הסינון אחרי שהגדרתי אותו?",
        "en": "Can I change my filter after setting it up?",
        "ru": "Можно ли изменить фильтр после его настройки?",
        "fr": "Puis-je modifier mon filtre après l'avoir configuré ?",
        "ar": "هل يمكنني تغيير الفلتر بعد إعداده؟",
    },
    "home.faq4_a": {
        "he": "בהחלט — גם דרך הבוט בטלגרם וגם כאן באתר, בעמוד \"הסינון שלי\", בכל שלב שתרצו.",
        "en": "Absolutely — through the Telegram bot or right here on the site, on the \"My filter\" page, whenever you like.",
        "ru": "Конечно — через бота в Telegram или прямо здесь на сайте, на странице «Мой фильтр», в любой момент.",
        "fr": "Bien sûr — via le bot Telegram ou ici même sur le site, sur la page « Mon filtre », à tout moment.",
        "ar": "بالتأكيد — عبر البوت على تيليجرام أو هنا على الموقع، في صفحة \"فلتري\"، في أي وقت تشاء.",
    },
    "home.footer_cta_title": {
        "he": "מוכנים למצוא את הדירה?", "en": "Ready to find your apartment?",
        "ru": "Готовы найти свою квартиру?", "fr": "Prêt à trouver votre appartement ?",
        "ar": "مستعد لإيجاد شقتك؟",
    },
    "home.footer_cta_body": {
        "he": "זה לוקח פחות משתי דקות להתחיל, וההתראות הראשונות יכולות להגיע עוד היום.",
        "en": "It takes less than two minutes to get started, and your first alerts can arrive today.",
        "ru": "Начать можно меньше чем за две минуты, а первые уведомления могут прийти уже сегодня.",
        "fr": "Il faut moins de deux minutes pour commencer, et vos premières alertes peuvent arriver dès aujourd'hui.",
        "ar": "يستغرق البدء أقل من دقيقتين، وقد تصلك أول التنبيهات اليوم نفسه.",
    },
    "home.footer_cta_btn": {
        "he": "פתח את הבוט בטלגרם ←", "en": "Open the Telegram bot →",
        "ru": "Открыть бота в Telegram →", "fr": "Ouvrir le bot Telegram →",
        "ar": "افتح البوت على تيليجرام ←",
    },
    "home.footer_cta_whatsapp_btn": {
        "he": "המשך בווטסאפ ←", "en": "Continue on WhatsApp →",
        "ru": "Продолжить в WhatsApp →", "fr": "Continuer sur WhatsApp →",
        "ar": "تابع عبر واتساب ←",
    },
    # ---------- apartments page ----------
    "apartments.title": {
        "he": "דירות תואמות 🏠", "en": "Matching apartments 🏠", "ru": "Подходящие квартиры 🏠",
        "fr": "Appartements correspondants 🏠", "ar": "شقق مطابقة 🏠",
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
        "he": "גישה זמנית לפי מזהה טלגרם — קישור אישי זה עדיין לא מאובטח לגמרי, שלב ביניים בלבד עד להשקה.",
        "en": "Temporary access via Telegram ID — this personal link isn't fully secure yet, just an interim step until launch.",
        "ru": "Временный доступ по Telegram ID — эта персональная ссылка пока не полностью защищена, это лишь промежуточный этап до запуска.",
        "fr": "Accès temporaire via l'identifiant Telegram — ce lien personnel n'est pas encore totalement sécurisé, c'est juste une étape intermédiaire avant le lancement.",
        "ar": "وصول مؤقت عبر معرف تيليجرام — هذا الرابط الشخصي ليس آمنًا بالكامل بعد، وهو مجرد مرحلة انتقالية حتى الإطلاق.",
    },
    "apartments.filter_label": {
        "he": "הסינון שלך:", "en": "Your filter:", "ru": "Ваш фильтр:", "fr": "Votre filtre :", "ar": "فلترك:",
    },
    "apartments.rooms_suffix": {
        "he": "חדרים", "en": "rooms", "ru": "комнат", "fr": "pièces", "ar": "غرف",
    },
    "apartments.edit_filter_btn": {
        "he": "ערוך סינון", "en": "Edit filter", "ru": "Изменить фильтр",
        "fr": "Modifier le filtre", "ar": "تعديل الفلتر",
    },
    "apartments.no_brokers_on": {
        "he": "בלי תיווך 🚫", "en": "No brokers 🚫", "ru": "Без посредников 🚫",
        "fr": "Sans agences 🚫", "ar": "بدون سماسرة 🚫",
    },
    "apartments.no_brokers_off": {
        "he": "כולל תיווך 🏢", "en": "Including brokers 🏢", "ru": "С посредниками 🏢",
        "fr": "Avec agences 🏢", "ar": "يشمل السماسرة 🏢",
    },
    "apartments.empty_title": {
        "he": "אין עדיין דירות תואמות להצגה.",
        "en": "No matching apartments to show yet.",
        "ru": "Пока нет подходящих квартир для показа.",
        "fr": "Aucun appartement correspondant à afficher pour le moment.",
        "ar": "لا توجد بعد شقق مطابقة لعرضها.",
    },
    "apartments.empty_hint": {
        "he": "אם זה נראה משונה — סביר שזה כי שאיבת המודעות עדיין בבנייה, לא בעיה בסינון שלך. נסה שוב בקרוב.",
        "en": "If this seems odd — it's most likely because listing collection is still being built out, not an issue with your filter. Try again soon.",
        "ru": "Если это кажется странным — скорее всего, сбор объявлений ещё дорабатывается, а не проблема в вашем фильтре. Попробуйте снова позже.",
        "fr": "Si cela semble étrange — c'est très probablement parce que la collecte des annonces est encore en construction, pas un problème avec votre filtre. Réessayez bientôt.",
        "ar": "إذا بدا هذا غريبًا — فالسبب على الأرجح أن جمع الإعلانات ما زال قيد الإنشاء، وليس مشكلة في فلترك. حاول مجددًا قريبًا.",
    },
    # Announced via an aria-live region when infinite scroll loads another batch (2026-09-07 audit
    # fix) — without this, a screen-reader user got zero indication that new listings had appeared
    # below the ones they'd already heard, since the new cards are inserted silently by JS with no
    # page navigation to re-announce anything.
    "apartments.more_loaded_announcement": {
        "he": "{count} דירות נוספות נטענו",
        "en": "{count} more apartments loaded",
        "ru": "Загружено ещё {count} квартир",
        "fr": "{count} appartements supplémentaires chargés",
        "ar": "تم تحميل {count} شقق إضافية",
    },
    # ---------- liked page ----------
    "liked.title": {
        "he": "דירות שמורות ❤️", "en": "Saved apartments ❤️", "ru": "Сохранённые квартиры ❤️",
        "fr": "Appartements enregistrés ❤️", "ar": "شقق محفوظة ❤️",
    },
    "liked.subtitle": {
        "he": "דירות שסימנת כמעניינות — כאן ובבוט בטלגרם",
        "en": "Apartments you marked as interesting — here and in the Telegram bot",
        "ru": "Квартиры, которые вы отметили как интересные — здесь и в боте Telegram",
        "fr": "Appartements que vous avez marqués comme intéressants — ici et dans le bot Telegram",
        "ar": "شقق علّمتها كمهمة — هنا وفي بوت تيليجرام",
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
        "he": "דירות מוסתרות 🙈", "en": "Hidden apartments 🙈", "ru": "Скрытые квартиры 🙈",
        "fr": "Appartements masqués 🙈", "ar": "الشقق المخفية 🙈",
    },
    # ---------- hidden page ----------
    "hidden.title": {
        "he": "דירות מוסתרות 🙈", "en": "Hidden apartments 🙈", "ru": "Скрытые квартиры 🙈",
        "fr": "Appartements masqués 🙈", "ar": "شقق مخفية 🙈",
    },
    "hidden.subtitle": {
        "he": "דירות שהסתרת מרשימת ההתאמות — לחיצה נוספת על 👀 מחזירה אותן",
        "en": "Apartments you hid from your matches — tap 👀 again to bring them back",
        "ru": "Квартиры, которые вы скрыли из совпадений — нажмите 👀 ещё раз, чтобы вернуть их",
        "fr": "Appartements que vous avez masqués de vos correspondances — appuyez à nouveau sur 👀 pour les récupérer",
        "ar": "شقق أخفيتها من نتائجك — اضغط 👀 مجددًا لإعادتها",
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
        "he": "דירות שמורות ❤️", "en": "Saved apartments ❤️", "ru": "Сохранённые квартиры ❤️",
        "fr": "Appartements enregistrés ❤️", "ar": "الشقق المحفوظة ❤️",
    },
    # ---------- listing card ----------
    "card.like_btn": {
        "he": "שמור/י דירה", "en": "Save apartment", "ru": "Сохранить квартиру",
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
        "he": "מחיר לא צוין", "en": "Price not listed", "ru": "Цена не указана",
        "fr": "Prix non indiqué", "ar": "السعر غير محدد",
    },
    "card.no_city": {
        "he": "עיר לא צוינה", "en": "City not listed", "ru": "Город не указан",
        "fr": "Ville non indiquée", "ar": "المدينة غير محددة",
    },
    "card.rooms": {"he": "חדרים", "en": "rooms", "ru": "комнат", "fr": "pièces", "ar": "غرف"},
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
        "he": "לצפייה במודעה ←", "en": "View listing →", "ru": "Смотреть объявление →",
        "fr": "Voir l'annonce →", "ar": "عرض الإعلان ←",
    },
    # 2026-09-12: reworded from "Upgrade to view" — the description/photos are now shown to every
    # viewer regardless of subscription (see _listing_card.html); this button now gates only the
    # outbound link to the listing's original source (Yad2/etc), so the copy says that instead.
    "card.locked_btn": {
        "he": "שדרג/י לקישור למקור", "en": "Upgrade for original link",
        "ru": "Обновите для перехода к источнику", "fr": "Mettre à niveau pour le lien d'origine",
        "ar": "الترقية للرابط الأصلي",
    },
    # Badge shown on the cover photo (top-left, see .broker-badge in style.css) for a broker-listed
    # property — independent of deal_type (rent or sale, doesn't matter), 2026-09-03 request.
    "card.broker_badge": {
        "he": "תיווך", "en": "Broker", "ru": "Посредник", "fr": "Agence", "ar": "وسيط",
    },
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
        "he": "דירה זו עלתה ללא תמונות, אך שווה לפנות למפרסם ולבקש כמה! 🕵️",
        "en": "This listing has no photos yet — it's worth contacting the lister to ask for some! 🕵️",
        "ru": "У этого объявления пока нет фото — стоит написать автору и попросить! 🕵️",
        "fr": "Cette annonce n'a pas encore de photos — ça vaut le coup de demander au contact ! 🕵️",
        "ar": "لا توجد صور لهذا العرض بعد — يستحق التواصل مع المعلن لطلبها! 🕵️",
    },
    # ---------- filter page ----------
    "filter.title": {
        "he": "הסינון שלי ⚙️", "en": "My filter ⚙️", "ru": "Мой фильтр ⚙️",
        "fr": "Mon filtre ⚙️", "ar": "فلتري ⚙️",
    },
    "filter.welcome_banner": {
        "he": "ברוך הבא לטודירה! בוא נגדיר את הסינון שלך כדי שנראה לך בדיוק את הדירות שמתאימות",
        "en": "Welcome to Todira! Let's set up your filter so we can show you exactly the apartments that fit",
        "ru": "Добро пожаловать в Todira! Давайте настроим ваш фильтр, чтобы показывать именно те квартиры, которые подходят",
        "fr": "Bienvenue sur Todira ! Configurons votre filtre pour vous montrer exactement les appartements qui correspondent",
        "ar": "مرحبًا بك في طوديرة! لنقم بإعداد الفلتر الخاص بك لنعرض لك بالضبط الشقق المناسبة",
    },
    "filter.subtitle": {
        "he": "עריכה מלאה כאן. לעריכה של שכונות/רחובות ספציפיים ותאריכי כניסה — ב-/filter בטלגרם",
        "en": "Full editing here. For specific neighborhoods/streets and move-in dates, use /filter on Telegram.",
        "ru": "Полное редактирование здесь. Для конкретных районов/улиц и дат заселения используйте /filter в Telegram.",
        "fr": "Édition complète ici. Pour des quartiers/rues spécifiques et des dates d'emménagement, utilisez /filter sur Telegram.",
        "ar": "التعديل الكامل هنا. للأحياء/الشوارع المحددة وتواريخ الانتقال، استخدم /filter في تيليجرام.",
    },
    # 2026-09-06: shown instead of filter.subtitle for a visitor with no telegram_user_id at all
    # (a WhatsApp-only or Google-only account) — pointing them at "/filter on Telegram" is a dead
    # end when they have no Telegram account to run that command from. Just the first sentence of
    # the full subtitle in each language, since that sentence alone is still fully true and
    # actionable regardless of which channel got them here.
    "filter.subtitle_short": {
        "he": "עריכה מלאה כאן.",
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
        "he": "חפש/י עיר...", "en": "Search for a city...", "ru": "Поиск города...",
        "fr": "Rechercher une ville...", "ar": "ابحث عن مدينة...",
    },
    "filter.cities_hint": {
        "he": "לא מסומן כלום = כל הערים",
        "en": "Nothing checked = all cities",
        "ru": "Ничего не выбрано = все города",
        "fr": "Rien de coché = toutes les villes",
        "ar": "لا شيء محدد = كل المدن",
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
        "he": "חניה 🚗", "en": "Parking 🚗", "ru": "Парковка 🚗", "fr": "Parking 🚗", "ar": "موقف سيارات 🚗",
    },
    "filter.amenity_elevator": {
        "he": "מעלית 🛗", "en": "Elevator 🛗", "ru": "Лифт 🛗", "fr": "Ascenseur 🛗", "ar": "مصعد 🛗",
    },
    "filter.amenity_balcony": {
        "he": "מרפסת 🌇", "en": "Balcony 🌇", "ru": "Балкон 🌇", "fr": "Balcon 🌇", "ar": "شرفة 🌇",
    },
    "filter.amenity_pets": {
        "he": "חיות מחמד מותרות 🐾", "en": "Pets allowed 🐾", "ru": "Можно с животными 🐾",
        "fr": "Animaux autorisés 🐾", "ar": "يسمح بالحيوانات الأليفة 🐾",
    },
    "filter.amenity_renovated": {
        "he": "משופצת ✨", "en": "Renovated ✨", "ru": "Отремонтирована ✨",
        "fr": "Rénové ✨", "ar": "مجدّدة ✨",
    },
    "filter.amenity_roommates": {
        "he": "מתאימה לשותפים 🧑‍🤝‍🧑", "en": "Roommate friendly 🧑‍🤝‍🧑", "ru": "Подходит для соседей 🧑‍🤝‍🧑",
        "fr": "Adapté à la colocation 🧑‍🤝‍🧑", "ar": "مناسبة للسكن المشترك 🧑‍🤝‍🧑",
    },
    "filter.amenity_photos": {
        "he": "עם תמונות בלבד 🖼️", "en": "With photos only 🖼️", "ru": "Только с фото 🖼️",
        "fr": "Avec photos uniquement 🖼️", "ar": "بصور فقط 🖼️",
    },
    "filter.amenity_no_brokers": {
        "he": "בלי תיווך 🚫", "en": "No brokers 🚫", "ru": "Без посредников 🚫",
        "fr": "Sans agence 🚫", "ar": "بدون وسطاء 🚫",
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
        "he": "מופרדות בפסיקים — דירה תואמת אם התיאור שלה מכיל לפחות אחת מהן",
        "en": "Comma-separated — an apartment matches if its description contains at least one of them",
        "ru": "Через запятую — квартира подходит, если в описании есть хотя бы одно из слов",
        "fr": "Séparés par des virgules — un appartement correspond si sa description contient au moins un des mots",
        "ar": "مفصولة بفواصل — تُطابق الشقة إذا احتوى وصفها على كلمة واحدة منها على الأقل",
    },
    "filter.flexible_match_label": {
        "he": "התאמה גמישה — הצג גם דירות שמפספסות מאפיין אחד בלבד",
        "en": "Flexible match — also show apartments that miss just one feature",
        "ru": "Гибкое совпадение — показывать также квартиры, которым не хватает лишь одной характеристики",
        "fr": "Correspondance flexible — afficher aussi les appartements qui ne remplissent pas qu'un seul critère",
        "ar": "تطابق مرن — عرض أيضًا الشقق التي تفتقد ميزة واحدة فقط",
    },
    "filter.save_btn": {
        "he": "שמור שינויים 💾", "en": "Save changes 💾", "ru": "Сохранить изменения 💾",
        "fr": "Enregistrer les modifications 💾", "ar": "حفظ التغييرات 💾",
    },
    # ---------- empty states / small pages ----------
    "no_filter.body": {
        "he": "לא מצאנו חשבון או סינון פעיל. צריך להגדיר סינון קודם דרך הבוט בטלגרם.",
        "en": "We couldn't find an account or an active filter. You need to set up a filter first, through the Telegram bot.",
        "ru": "Мы не нашли аккаунт или активный фильтр. Сначала настройте фильтр через бота в Telegram.",
        "fr": "Nous n'avons trouvé aucun compte ni filtre actif. Vous devez d'abord configurer un filtre via le bot Telegram.",
        "ar": "لم نعثر على حساب أو فلتر نشط. يجب إعداد فلتر أولاً عبر البوت على تيليجرام.",
    },
    "no_filter.cta": {
        "he": "פתח את הבוט", "en": "Open the bot", "ru": "Открыть бота", "fr": "Ouvrir le bot", "ar": "افتح البوت",
    },
    "need_uid.body": {
        "he": "כדי לראות את ה{target} שלך, צריך להיכנס עם קישור אישי מהבוט בטלגרם.",
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
    "contact.title": {
        "he": "צור קשר 📬", "en": "Contact us 📬", "ru": "Связаться с нами 📬",
        "fr": "Nous contacter 📬", "ar": "تواصل معنا 📬",
    },
    "contact.subtitle": {
        "he": "יש לך שאלה, בעיה או רעיון? נשמח לשמוע — נחזור אליך בהקדם.",
        "en": "Have a question, a problem, or an idea? We'd love to hear from you — we'll get back to you soon.",
        "ru": "Есть вопрос, проблема или идея? Будем рады услышать вас — скоро ответим.",
        "fr": "Une question, un problème ou une idée ? N'hésitez pas à nous écrire — nous vous répondrons rapidement.",
        "ar": "هل لديك سؤال أو مشكلة أو فكرة؟ يسعدنا أن نسمع منك — سنرد عليك قريبًا.",
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
        "he": "כתוב/י כאן את מה שתרצה/י להעביר לנו...",
        "en": "Write what you'd like to tell us here...",
        "ru": "Напишите здесь то, что хотите нам сообщить...",
        "fr": "Écrivez ici ce que vous souhaitez nous dire...",
        "ar": "اكتب هنا ما تود إخبارنا به...",
    },
    "contact.submit_btn": {
        "he": "שלח הודעה 📨", "en": "Send message 📨", "ru": "Отправить сообщение 📨",
        "fr": "Envoyer le message 📨", "ar": "إرسال الرسالة 📨",
    },
    "contact.error_empty": {
        "he": "ההודעה לא יכולה להיות ריקה. ⚠️",
        "en": "The message can't be empty. ⚠️",
        "ru": "Сообщение не может быть пустым. ⚠️",
        "fr": "Le message ne peut pas être vide. ⚠️",
        "ar": "لا يمكن أن تكون الرسالة فارغة. ⚠️",
    },
    "contact.success_title": {
        "he": "ההודעה נשלחה! ✅",
        "en": "Message sent! ✅",
        "ru": "Сообщение отправлено! ✅",
        "fr": "Message envoyé ! ✅",
        "ar": "تم إرسال الرسالة! ✅",
    },
    "contact.success_body": {
        "he": "תודה שפנית אלינו — נחזור אליך בהקדם האפשרי.",
        "en": "Thanks for reaching out — we'll get back to you as soon as possible.",
        "ru": "Спасибо, что обратились к нам — мы ответим вам как можно скорее.",
        "fr": "Merci de nous avoir contactés — nous vous répondrons dès que possible.",
        "ar": "شكرًا لتواصلك معنا — سنرد عليك في أقرب وقت ممكن.",
    },
    "contact.other_ways_title": {
        "he": "דרכים נוספות ליצור קשר", "en": "Other ways to reach us",
        "ru": "Другие способы связи", "fr": "Autres moyens de nous contacter",
        "ar": "طرق أخرى للتواصل",
    },
    "contact.telegram_way": {
        "he": "טלגרם — כתוב/י ישירות לבוט", "en": "Telegram — message the bot directly",
        "ru": "Telegram — напишите боту напрямую", "fr": "Telegram — écrivez directement au bot",
        "ar": "تيليجرام — راسل البوت مباشرة",
    },
    # Added 2026-09-07 — /contact only offered a Telegram link under "other ways to reach us"
    # despite the product having a WhatsApp bot since 2026-09-06 (same gap the footer/home hero
    # CTA already got fixed for).
    "contact.whatsapp_way": {
        "he": "וואטסאפ — כתוב/י ישירות לבוט", "en": "WhatsApp — message the bot directly",
        "ru": "WhatsApp — напишите боту напрямую", "fr": "WhatsApp — écrivez directement au bot",
        "ar": "واتساب — راسل البوت مباشرة",
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
    # ---------- account page ----------
    # 2026-09-08 fix: this whole page was hardcoded Hebrew-only (unlike every other customer-
    # facing page), so a non-Hebrew visitor saw a fully-Hebrew /account regardless of their own
    # language setting — found while auditing the WhatsApp-notifications toggle added tonight,
    # which just followed the page's own (pre-existing, unrelated to that feature) pattern.
    "account.h1": {
        "he": "החשבון שלי 👤", "en": "My Account 👤", "ru": "Мой аккаунт 👤",
        "fr": "Mon compte 👤", "ar": "حسابي 👤",
    },
    "account.subtitle": {
        "he": "המנוי, ההתראות, היסטוריית התשלומים, וחיבור הערוצים — טלגרם, ווטסאפ וגוגל, כולם אותו חשבון אחד.",
        "en": "Your subscription, notifications, payment history, and connected channels — Telegram, WhatsApp and Google, all one account.",
        "ru": "Подписка, уведомления, история платежей и подключённые каналы — Telegram, WhatsApp и Google, всё в одном аккаунте.",
        "fr": "Votre abonnement, vos notifications, votre historique de paiements et vos canaux connectés — Telegram, WhatsApp et Google, tout dans un seul compte.",
        "ar": "اشتراكك، إشعاراتك، سجل مدفوعاتك، والقنوات المرتبطة — تيليجرام وواتساب وجوجل، كلها في حساب واحد.",
    },
    "account.subscription_title": {
        "he": "המנוי שלי 👑", "en": "My Subscription 👑", "ru": "Моя подписка 👑",
        "fr": "Mon abonnement 👑", "ar": "اشتراكي 👑",
    },
    "account.subscription_active": {
        "he": "✅ פעיל, בתוקף עד {date}", "en": "✅ Active, valid until {date}",
        "ru": "✅ Активна, действует до {date}", "fr": "✅ Actif, valable jusqu'au {date}",
        "ar": "✅ نشط، ساري حتى {date}",
    },
    "account.subscription_trial": {
        "he": "⏳ תקופת ניסיון, עד {date}", "en": "⏳ Trial period, until {date}",
        "ru": "⏳ Пробный период, до {date}", "fr": "⏳ Période d'essai, jusqu'au {date}",
        "ar": "⏳ فترة تجريبية، حتى {date}",
    },
    "account.subscription_expired": {
        "he": "תקופת הניסיון הסתיימה ⚠️", "en": "Trial period ended ⚠️",
        "ru": "Пробный период закончился ⚠️", "fr": "Période d'essai terminée ⚠️",
        "ar": "انتهت الفترة التجريبية ⚠️",
    },
    "account.upgrade_cta_renew": {
        "he": "שדרג/י מנוי", "en": "Upgrade subscription", "ru": "Улучшить подписку",
        "fr": "Améliorer l'abonnement", "ar": "ترقية الاشتراك",
    },
    "account.upgrade_cta_start": {
        "he": "לשדרוג המנוי", "en": "Upgrade now", "ru": "Оформить подписку",
        "fr": "Passer à l'abonnement", "ar": "الترقية الآن",
    },
    "account.notifications_title": {
        "he": "התראות 🔔", "en": "Notifications 🔔", "ru": "Уведомления 🔔",
        "fr": "Notifications 🔔", "ar": "الإشعارات 🔔",
    },
    "account.status_on": {
        "he": "🔔 מופעלות", "en": "🔔 On", "ru": "🔔 Включены", "fr": "🔔 Activées", "ar": "🔔 مفعّلة",
    },
    "account.status_off": {
        "he": "🔕 כבויות", "en": "🔕 Off", "ru": "🔕 Выключены", "fr": "🔕 Désactivées", "ar": "🔕 معطّلة",
    },
    "account.notifications_toggle_off": {
        "he": "כבה התראות", "en": "Turn off notifications", "ru": "Выключить уведомления",
        "fr": "Désactiver les notifications", "ar": "إيقاف الإشعارات",
    },
    "account.notifications_toggle_on": {
        "he": "הפעל התראות", "en": "Turn on notifications", "ru": "Включить уведомления",
        "fr": "Activer les notifications", "ar": "تفعيل الإشعارات",
    },
    "account.whatsapp_notifications_title": {
        "he": "התראות בווטסאפ 💬", "en": "WhatsApp Notifications 💬", "ru": "Уведомления в WhatsApp 💬",
        "fr": "Notifications WhatsApp 💬", "ar": "إشعارات واتساب 💬",
    },
    "account.whatsapp_notifications_toggle_off": {
        "he": "כבה התראות בווטסאפ", "en": "Turn off WhatsApp notifications",
        "ru": "Выключить уведомления WhatsApp", "fr": "Désactiver les notifications WhatsApp",
        "ar": "إيقاف إشعارات واتساب",
    },
    "account.whatsapp_notifications_toggle_on": {
        "he": "הפעל התראות בווטסאפ", "en": "Turn on WhatsApp notifications",
        "ru": "Включить уведомления WhatsApp", "fr": "Activer les notifications WhatsApp",
        "ar": "تفعيل إشعارات واتساب",
    },
    "account.whatsapp_notifications_hint": {
        "he": "הודעת ווטסאפ ברגע שעולה דירה חדשה שמתאימה לך, בנוסף לאתר/טלגרם.",
        "en": "A WhatsApp message the moment a new listing matches you, in addition to the website/Telegram.",
        "ru": "Сообщение в WhatsApp, как только появится подходящее объявление — в дополнение к сайту/Telegram.",
        "fr": "Un message WhatsApp dès qu'une nouvelle annonce vous correspond, en plus du site/Telegram.",
        "ar": "رسالة واتساب فور ظهور شقة جديدة تناسبك، بالإضافة إلى الموقع/تيليجرام.",
    },
    "account.channels_title": {
        "he": "חיבור ערוצים 🔗", "en": "Connected Channels 🔗", "ru": "Подключённые каналы 🔗",
        "fr": "Canaux connectés 🔗", "ar": "القنوات المرتبطة 🔗",
    },
    "account.channel_connected": {
        "he": "מחובר ✅", "en": "Connected ✅", "ru": "Подключено ✅", "fr": "Connecté ✅", "ar": "متصل ✅",
    },
    "account.telegram_connect_cta": {
        "he": "פתח/י את הבוט לחיבור", "en": "Open the bot to connect",
        "ru": "Открыть бота для подключения", "fr": "Ouvrir le bot pour vous connecter",
        "ar": "افتح البوت للربط",
    },
    "account.telegram_connect_hint": {
        "he": "לוחצים על הכפתור והחיבור קורה אוטומטית 🎉",
        "en": "Tap the button and the connection happens automatically 🎉",
        "ru": "Нажмите на кнопку — подключение произойдёт автоматически 🎉",
        "fr": "Appuyez sur le bouton, la connexion se fait automatiquement 🎉",
        "ar": "اضغط على الزر وسيتم الربط تلقائيًا 🎉",
    },
    "account.no_active_code": {
        "he": "אין קוד חיבור פעיל כרגע", "en": "No active connection code right now",
        "ru": "Сейчас нет активного кода подключения", "fr": "Aucun code de connexion actif pour le moment",
        "ar": "لا يوجد رمز ربط نشط حاليًا",
    },
    "account.whatsapp_connect_cta": {
        "he": "שלח/י הודעה לחיבור", "en": "Send a message to connect",
        "ru": "Отправьте сообщение для подключения", "fr": "Envoyez un message pour vous connecter",
        "ar": "أرسل رسالة للربط",
    },
    "account.whatsapp_connect_hint": {
        "he": "ההודעה עם הקוד תישלח אוטומטית — רק צריך ללחוץ שליחה 🎉",
        "en": "The message with the code will be sent automatically — just tap send 🎉",
        "ru": "Сообщение с кодом отправится автоматически — просто нажмите «отправить» 🎉",
        "fr": "Le message avec le code sera envoyé automatiquement — il suffit d'appuyer sur envoyer 🎉",
        "ar": "ستُرسل الرسالة مع الرمز تلقائيًا — فقط اضغط إرسال 🎉",
    },
    "account.whatsapp_connect_unavailable": {
        "he": "חיבור ווטסאפ עוד לא זמין כרגע", "en": "WhatsApp connection isn't available yet",
        "ru": "Подключение WhatsApp пока недоступно", "fr": "La connexion WhatsApp n'est pas encore disponible",
        "ar": "الربط عبر واتساب غير متاح بعد",
    },
    "account.google_connect_cta": {
        "he": "קשר את Google לחשבון", "en": "Link Google to your account",
        "ru": "Привязать Google к аккаунту", "fr": "Lier Google à votre compte",
        "ar": "اربط Google بحسابك",
    },
    "account.code_hint_prefix": {
        "he": "הקוד שלך:", "en": "Your code:", "ru": "Ваш код:", "fr": "Votre code :", "ar": "رمزك:",
    },
    "account.code_hint_suffix": {
        "he": "— בתוקף ל-15 דקות. אפשר גם לשלוח אותו ידנית מהערוץ שרוצים לחבר, במקום ללחוץ על הכפתור.",
        "en": "— valid for 15 minutes. You can also send it manually from the channel you want to connect, instead of tapping the button.",
        "ru": "— действителен 15 минут. Можно также отправить его вручную из канала, который хотите подключить, вместо нажатия кнопки.",
        "fr": "— valable 15 minutes. Vous pouvez aussi l'envoyer manuellement depuis le canal que vous souhaitez connecter, au lieu d'appuyer sur le bouton.",
        "ar": "— صالح لمدة 15 دقيقة. يمكنك أيضًا إرساله يدويًا من القناة التي تريد ربطها، بدلاً من الضغط على الزر.",
    },
    "account.payment_history_title": {
        "he": "היסטוריית תשלומים 📄", "en": "Payment History 📄", "ru": "История платежей 📄",
        "fr": "Historique des paiements 📄", "ar": "سجل المدفوعات 📄",
    },
    "account.payment_status_paid": {
        "he": "✅ שולם", "en": "✅ Paid", "ru": "✅ Оплачено", "fr": "✅ Payé", "ar": "✅ مدفوع",
    },
    "account.payment_status_pending": {
        "he": "⏳ ממתין", "en": "⏳ Pending", "ru": "⏳ В ожидании", "fr": "⏳ En attente", "ar": "⏳ قيد الانتظار",
    },
    "account.payment_status_failed": {
        "he": "❌ נכשל", "en": "❌ Failed", "ru": "❌ Не удалось", "fr": "❌ Échoué", "ar": "❌ فشل",
    },
    "account.payment_status_cancelled": {
        "he": "✋ בוטל", "en": "✋ Cancelled", "ru": "✋ Отменено", "fr": "✋ Annulé", "ar": "✋ ألغي",
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
        "he": "בחר/י איך להתחבר — כל האפשרויות מובילות לאותו חשבון.",
        "en": "Choose how to log in — every option leads to the same account.",
        "ru": "Выберите способ входа — все варианты ведут к одному и тому же аккаунту.",
        "fr": "Choisissez comment vous connecter — toutes les options mènent au même compte.",
        "ar": "اختر طريقة تسجيل الدخول — كل الخيارات تؤدي إلى نفس الحساب.",
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
        "he": "כבר רשום/ה דרך טלגרם או ווטסאפ, אבל עדיין לא קישרת Google? לחיצה על \"{telegram_cta}\" למעלה תפתח את הבוט — שם תמצא/י קישור לחשבון שלך (🔗) שמחזיר אותך לכאן, לאותו דפדפן, מזוהה. משם, החיבור עם Google יעבוד ישר על החשבון הקיים שלך.",
        "en": "Already registered via Telegram or WhatsApp, but haven't linked Google yet? Tapping \"{telegram_cta}\" above opens the bot — you'll find your account link there (🔗) that brings you back here, in the same browser, recognized. From there, connecting with Google will work straight on your existing account.",
        "ru": "Уже зарегистрированы через Telegram или WhatsApp, но ещё не привязали Google? Нажатие на «{telegram_cta}» выше откроет бота — там вы найдёте ссылку на свой аккаунт (🔗), которая вернёт вас сюда, в тот же браузер, уже узнанным. Оттуда подключение через Google сработает прямо на вашем существующем аккаунте.",
        "fr": "Déjà inscrit via Telegram ou WhatsApp, mais pas encore lié à Google ? Appuyer sur « {telegram_cta} » ci-dessus ouvre le bot — vous y trouverez le lien de votre compte (🔗) qui vous ramène ici, dans le même navigateur, reconnu. À partir de là, la connexion avec Google fonctionnera directement sur votre compte existant.",
        "ar": "مسجّل بالفعل عبر تيليجرام أو واتساب، لكن لم تربط Google بعد؟ الضغط على \"{telegram_cta}\" أعلاه يفتح البوت — ستجد هناك رابط حسابك (🔗) الذي يعيدك إلى هنا، في نفس المتصفح، معروفًا. من هناك، سيعمل الربط مع Google مباشرة على حسابك الحالي.",
    },
    "google_pending.h1": {
        "he": "ההתחברות עם Google הצליחה", "en": "Google login successful",
        "ru": "Вход через Google выполнен успешно", "fr": "Connexion Google réussie",
        "ar": "تم تسجيل الدخول عبر Google بنجاح",
    },
    "google_pending.subtitle": {
        "he": "זו הפעם הראשונה שאנחנו רואים את החשבון הזה — איך תרצה/י להמשיך?",
        "en": "This is the first time we've seen this account — how would you like to continue?",
        "ru": "Мы впервые видим этот аккаунт — как вы хотите продолжить?",
        "fr": "C'est la première fois que nous voyons ce compte — comment souhaitez-vous continuer ?",
        "ar": "هذه أول مرة نرى فيها هذا الحساب — كيف تريد المتابعة؟",
    },
    "google_pending.new_account_cta": {
        "he": "זה חשבון חדש — תתחיל/י ישר כאן באתר ✨",
        "en": "This is a new account — start right here on the site ✨",
        "ru": "Это новый аккаунт — начните прямо здесь, на сайте ✨",
        "fr": "C'est un nouveau compte — commencez directement ici sur le site ✨",
        "ar": "هذا حساب جديد — ابدأ مباشرة هنا في الموقع ✨",
    },
    "google_pending.new_account_hint": {
        "he": "ניצור לך חשבון וסינון פתוח שמתאים לכל הדירות — תוכל/י לצמצם אותו בכל רגע ב\"סינון\". טלגרם וווטסאפ יישארו זמינים תמיד כאופציה נוספת לקבלת התראות, בלי חובה להשתמש בהם.",
        "en": "We'll create an account for you with an open filter that matches every listing — you can narrow it down anytime in \"Filter\". Telegram and WhatsApp will always stay available as an extra way to get notified, with no obligation to use them.",
        "ru": "Мы создадим для вас аккаунт с открытым фильтром, который подходит под все объявления — вы можете сузить его в любой момент в разделе «Фильтр». Telegram и WhatsApp всегда будут доступны как дополнительный способ получать уведомления, без обязательства ими пользоваться.",
        "fr": "Nous créerons pour vous un compte avec un filtre ouvert qui correspond à toutes les annonces — vous pourrez le restreindre à tout moment dans « Filtre ». Telegram et WhatsApp resteront toujours disponibles comme moyen supplémentaire de recevoir des notifications, sans obligation de les utiliser.",
        "ar": "سننشئ لك حسابًا مع فلتر مفتوح يطابق كل الشقق — يمكنك تضييقه في أي وقت من \"الفلتر\". سيبقى تيليجرام وواتساب متاحين دائمًا كوسيلة إضافية لتلقي الإشعارات، دون إلزام باستخدامهما.",
    },
    "google_pending.divider": {
        "he": "או", "en": "Or", "ru": "Или", "fr": "Ou", "ar": "أو",
    },
    "google_pending.existing_account_prompt": {
        "he": "כבר יש לך חשבון דרך טלגרם או ווטסאפ?",
        "en": "Already have an account via Telegram or WhatsApp?",
        "ru": "У вас уже есть аккаунт через Telegram или WhatsApp?",
        "fr": "Vous avez déjà un compte via Telegram ou WhatsApp ?",
        "ar": "هل لديك حساب بالفعل عبر تيليجرام أو واتساب؟",
    },
    "google_pending.link_existing_cta": {
        "he": "🔗 קשר לחשבון הקיים שלי", "en": "🔗 Link to my existing account",
        "ru": "🔗 Привязать к существующему аккаунту", "fr": "🔗 Lier à mon compte existant",
        "ar": "🔗 اربط بحسابي الحالي",
    },
    "google_pending.link_hint_with_token": {
        "he": "שלח/י /start בבוט — החיבור יושלם מיד שם, בלי קשר לאיזה דפדפן תשתמש/י בהמשך.",
        "en": "Send /start to the bot — the connection completes right there, regardless of which browser you use afterward.",
        "ru": "Отправьте /start боту — подключение завершится сразу там, независимо от того, каким браузером вы будете пользоваться дальше.",
        "fr": "Envoyez /start au bot — la connexion se termine immédiatement là-bas, quel que soit le navigateur que vous utiliserez ensuite.",
        "ar": "أرسل /start للبوت — سيكتمل الربط هناك فورًا، بغض النظر عن المتصفح الذي ستستخدمه لاحقًا.",
    },
    "google_pending.link_hint_no_token": {
        "he": "פתח/י את הבוט פעם אחת — כשתחזור/י לאתר מאותו דפדפן, נשלים את החיבור אוטומטית.",
        "en": "Open the bot once — when you return to the site from the same browser, we'll complete the connection automatically.",
        "ru": "Откройте бота один раз — когда вы вернётесь на сайт из того же браузера, мы автоматически завершим подключение.",
        "fr": "Ouvrez le bot une fois — lorsque vous reviendrez sur le site depuis le même navigateur, nous terminerons la connexion automatiquement.",
        "ar": "افتح البوت مرة واحدة — عند عودتك إلى الموقع من نفس المتصفح، سنكمل الربط تلقائيًا.",
    },
    "upgrade.h1": {
        "he": "שדרוג המנוי 👑", "en": "Upgrade subscription 👑", "ru": "Улучшение подписки 👑",
        "fr": "Mise à niveau de l'abonnement 👑", "ar": "ترقية الاشتراك 👑",
    },
    "upgrade.owner_notice": {
        "he": "אתה הבעלים של השירות — יש לך גישה מלאה תמיד, בלי קשר לתשלום.",
        "en": "You're the service owner — you always have full access, regardless of payment.",
        "ru": "Вы владелец сервиса — у вас всегда есть полный доступ, независимо от оплаты.",
        "fr": "Vous êtes le propriétaire du service — vous avez toujours un accès complet, indépendamment du paiement.",
        "ar": "أنت مالك الخدمة — لديك دائمًا وصول كامل، بغض النظر عن الدفع.",
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
        "he": "תקופת הניסיון הסתיימה. כדי להמשיך לקבל את המודעה המלאה + קישור ישיר, בחר תוכנית למטה.",
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
    "upgrade.choose_plan_cta": {
        "he": "בחר {plan}", "en": "Choose {plan}", "ru": "Выбрать {plan}", "fr": "Choisir {plan}",
        "ar": "اختر {plan}",
    },
    "upgrade.payment_hint_takbull": {
        "he": "התשלום מאובטח דרך תקבול — ביט, Apple Pay, Google Pay או כרטיס אשראי. בעמוד התשלום תראה/י את 3 התוכניות יחד — פשוט תוסיף/י לעגלה את זו שבחרת כאן (לפי המחיר) ותשלים/י תשלום. 🐾",
        "en": "Payment is secured through Takbull — Bit, Apple Pay, Google Pay or credit card. On the payment page you'll see all 3 plans together — just add the one you chose here (by price) to the cart and complete payment. 🐾",
        "ru": "Оплата защищена через Takbull — Bit, Apple Pay, Google Pay или банковская карта. На странице оплаты вы увидите все 3 плана вместе — просто добавьте выбранный здесь план (по цене) в корзину и завершите оплату. 🐾",
        "fr": "Le paiement est sécurisé via Takbull — Bit, Apple Pay, Google Pay ou carte de crédit. Sur la page de paiement, vous verrez les 3 forfaits ensemble — ajoutez simplement celui choisi ici (selon le prix) au panier et finalisez le paiement. 🐾",
        "ar": "الدفع مؤمّن عبر تكبول — Bit أو Apple Pay أو Google Pay أو بطاقة ائتمان. في صفحة الدفع سترى الخطط الثلاث معًا — فقط أضف الخطة التي اخترتها هنا (حسب السعر) إلى السلة وأكمل الدفع. 🐾",
    },
    "upgrade.payment_hint_grow": {
        "he": "התשלום מאובטח דרך Grow — ביט, פייבוקס, Apple Pay, Google Pay או כרטיס אשראי. 🐾",
        "en": "Payment is secured through Grow — Bit, PayBox, Apple Pay, Google Pay or credit card. 🐾",
        "ru": "Оплата защищена через Grow — Bit, PayBox, Apple Pay, Google Pay или банковская карта. 🐾",
        "fr": "Le paiement est sécurisé via Grow — Bit, PayBox, Apple Pay, Google Pay ou carte de crédit. 🐾",
        "ar": "الدفع مؤمّن عبر Grow — Bit أو PayBox أو Apple Pay أو Google Pay أو بطاقة ائتمان. 🐾",
    },
    "upgrade.payment_hint_manual": {
        "he": "התשלום מתבצע ידנית בביט/PayBox — אחרי הלחיצה תועבר/י לעמוד עם כל פרטי התשלום. 🐾",
        "en": "Payment is done manually via Bit/PayBox — after clicking you'll be taken to a page with all the payment details. 🐾",
        "ru": "Оплата производится вручную через Bit/PayBox — после нажатия вы перейдёте на страницу со всеми деталями оплаты. 🐾",
        "fr": "Le paiement se fait manuellement via Bit/PayBox — après avoir cliqué, vous serez redirigé vers une page avec tous les détails de paiement. 🐾",
        "ar": "يتم الدفع يدويًا عبر Bit/PayBox — بعد الضغط ستنتقل إلى صفحة تحتوي على كل تفاصيل الدفع. 🐾",
    },
    # 2026-09-10 addition: a small value-anchor box under the plan cards, right where price
    # sensitivity is highest — reframes the price against what people already know a broker
    # costs, instead of leaving ₪15-40 sitting there with no context. Deliberately does NOT claim
    # "cancel anytime" (a phrase that implies an auto-renewing subscription) — each plan is a
    # one-time purchase for a fixed period (PLAN_DURATIONS), nothing auto-renews, so the honest
    # framing is "no commitment to keep paying," not "cancel."
    "upgrade.value_anchor_title": {
        "he": "40 ₪ לחודש? פחות מכוס קפה ביום.",
        "en": "₪40 a month? Less than a daily coffee.",
        "ru": "40 ₪ в месяц? Меньше чашки кофе в день.",
        "fr": "40 ₪ par mois ? Moins qu'un café par jour.",
        "ar": "40 ₪ شهريًا؟ أقل من فنجان قهوة يوميًا.",
    },
    "upgrade.value_anchor_body": {
        "he": "עמלת תיווך בדרך כלל עולה אלפי שקלים בפעם אחת. אצלנו זה סכום סמלי, ואין התחייבות להמשך אחרי שהתקופה נגמרת.",
        "en": "A broker's fee usually costs thousands of shekels, once. With us it's a token amount, with no commitment to keep paying after the period ends.",
        "ru": "Комиссия риелтора обычно составляет тысячи шекелей, один раз. У нас это символическая сумма, без обязательства продолжать платить после окончания периода.",
        "fr": "Les frais d'agence coûtent généralement des milliers de shekels, une seule fois. Chez nous, c'est une somme symbolique, sans engagement à continuer de payer une fois la période terminée.",
        "ar": "عمولة الوسيط عادة ما تكلف آلاف الشواقل، مرة واحدة. عندنا هو مبلغ رمزي، دون التزام بالاستمرار في الدفع بعد انتهاء الفترة.",
    },
    "upgrade_pay.h1": {
        "he": "השלמת התשלום 💳", "en": "Complete payment 💳", "ru": "Завершение оплаты 💳",
        "fr": "Finaliser le paiement 💳", "ar": "إتمام الدفع 💳",
    },
    "upgrade_pay.plan_prefix": {
        "he": "תוכנית {plan} — לתשלום:", "en": "Plan: {plan} — to pay:", "ru": "План: {plan} — к оплате:",
        "fr": "Forfait : {plan} — à payer :", "ar": "الخطة: {plan} — للدفع:",
    },
    "upgrade_pay.bit_instruction": {
        "he": "פתח/י את אפליקציית Bit, חפש/י את המספר הבא ושלח/י ₪{amount}:",
        "en": "Open the Bit app, search for the following number and send ₪{amount}:",
        "ru": "Откройте приложение Bit, найдите следующий номер и отправьте ₪{amount}:",
        "fr": "Ouvrez l'application Bit, recherchez le numéro suivant et envoyez ₪{amount} :",
        "ar": "افتح تطبيق Bit، ابحث عن الرقم التالي وأرسل ₪{amount}:",
    },
    "upgrade_pay.paybox_cta": {
        "he": "פתח/י את דף התשלום ב-PayBox", "en": "Open the PayBox payment page",
        "ru": "Открыть страницу оплаты PayBox", "fr": "Ouvrir la page de paiement PayBox",
        "ar": "افتح صفحة الدفع في PayBox",
    },
    "upgrade_pay.manual_bit_hint": {
        "he": "שלח/י ₪{amount} בביט — פרטים יישלחו אליך בנפרד. 🐾",
        "en": "Send ₪{amount} via Bit — details will be sent to you separately. 🐾",
        "ru": "Отправьте ₪{amount} через Bit — детали будут отправлены вам отдельно. 🐾",
        "fr": "Envoyez ₪{amount} via Bit — les détails vous seront envoyés séparément. 🐾",
        "ar": "أرسل ₪{amount} عبر Bit — سيتم إرسال التفاصيل إليك بشكل منفصل. 🐾",
    },
    "upgrade_pay.already_paid": {
        "he": "התשלום כבר אושר. ✅", "en": "Payment already confirmed. ✅",
        "ru": "Оплата уже подтверждена. ✅", "fr": "Paiement déjà confirmé. ✅",
        "ar": "تم تأكيد الدفع بالفعل. ✅",
    },
    "upgrade_pay.continue_cta": {
        "he": "המשך", "en": "Continue", "ru": "Продолжить", "fr": "Continuer", "ar": "متابعة",
    },
    "upgrade_pay.confirm_paid_cta": {
        "he": "שילמתי, אשר/י את הגישה ✅", "en": "I've paid, confirm access ✅",
        "ru": "Я оплатил(а), подтвердите доступ ✅", "fr": "J'ai payé, confirmez l'accès ✅",
        "ar": "لقد دفعت، أكّد الوصول ✅",
    },
    "upgrade_pay.confirm_hint": {
        "he": "לוחצים רק אחרי ששלחתם את התשלום בפועל.",
        "en": "Only click after you've actually sent the payment.",
        "ru": "Нажимайте только после того, как действительно отправили платёж.",
        "fr": "Cliquez uniquement après avoir réellement envoyé le paiement.",
        "ar": "اضغط فقط بعد إرسال الدفعة فعليًا.",
    },
    "upgrade_success.paid_message": {
        "he": "התשלום התקבל, הגישה שלך פעילה! 🎉", "en": "Payment received, your access is active! 🎉",
        "ru": "Оплата получена, ваш доступ активен! 🎉", "fr": "Paiement reçu, votre accès est actif ! 🎉",
        "ar": "تم استلام الدفع، وصولك نشط! 🎉",
    },
    "upgrade_success.view_apartments_cta": {
        "he": "לצפייה בדירות", "en": "View apartments", "ru": "Просмотр квартир",
        "fr": "Voir les appartements", "ar": "لعرض الشقق",
    },
    "upgrade_success.processing_message": {
        "he": "מעבדים את התשלום... הדף יתעדכן אוטומטית בעוד כמה שניות.",
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


def get_lang(request: Request) -> str:
    """?lang= wins for this request (and main.py persists it to a cookie on the response);
    otherwise fall back to a previously-set cookie; otherwise Hebrew."""
    candidate = request.query_params.get("lang") or request.cookies.get("lang")
    return candidate if candidate in SUPPORTED_LANGS else DEFAULT_LANG


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
