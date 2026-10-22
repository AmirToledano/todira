"""Translated strings for the bot's conversational flows (bot/handlers/*.py) — 2026-09-26 real owner request, see todira_common/language.py's own
docstring for the full reasoning.

2026-09-26 follow-up: the owner explicitly asked for FULL coverage, not the originally-bounded
scope — extended to bot/handlers/profile.py, apartments.py, liked.py, and
filter_conversation.py's own menu-driven /filter conversation too (support.py needs no entries:
escalate_to_owner only ever messages OWNER_TELEGRAM_USER_ID, a fixed Hebrew-speaking recipient,
never the requesting user, so there's nothing user-facing in that module to translate). Same pass
also covers the two deeper layers a /filter conversation actually renders through — bot/keyboards.py
(every inline-keyboard button/category-title/summary label the menu screens show, under the "kb.*"
key prefix) and todira_common/cards.py (the listing-card caption itself — field labels, features,
buttons — shared by scraper/notifier.py's push and bot/handlers/liked.py's on-demand cards, under
the "card.*" prefix). cards.py builds every caption as plain text (no bidi marks at all, see
its own module comment above _normalize_line_breaks) — Telegram handles Hebrew/Arabic's
right-to-left direction natively, no per-language override needed here.

Translations were produced by this assistant, not reviewed by a native speaker of each language —
same caveat website/i18n.py's own header already states for the website's copy; good enough for
real-world use, but trust a native speaker over this file if one ever flags a phrasing as off.

Mirrors website/i18n.py's own dict-of-dicts shape and t(key, **kwargs) pattern (not literally
shared code — that module lives under website/ and pulls in ~250 web-page-specific keys the bots
have no use for — but the same simple approach, deliberately, rather than a second, different
i18n mechanism for no real reason)."""
from __future__ import annotations

from todira_common.language import DEFAULT_LANG

BOT_STRINGS: dict[str, dict[str, str]] = {
    # Telegram HTML (handlers/start.py sends /start replies with parse_mode HTML and escapes {name}/{account_url}).
    # The "⠀" line is a blank line Telegram can't collapse: extra space above the commands (owner request 2026-10-13).
    "start.welcome": {
        "he": (
            "👋 היי {name}!\n"
            "אני <b>טודירה</b> 🏠 הבוט שמחפש לך דירה.\n"
            "אני סורק את שוק הדירות כל הזמן, ושולח לך הודעה <b>ברגע</b> שעולה דירה שמתאימה לחיפוש שלך 🔔\n\n"
            "✍️ <b>אפשר פשוט לכתוב לי מה מחפשים</b>, במילים שלך, ואני אבין לבד.\n"
            "💬 למשל: <i>\"דירת 3 חדרים בתל אביב עד 8,000 ₪ עם מרפסת\"</i>\n\n⠀\n"
            "📋 <b>פקודות:</b>\n/filter — הגדרת/עדכון הסינון שלך\n/apartments — "
            "הדירות התואמות האחרונות\n/liked — הדירות ששמרת\n/profile — הפרופיל וההגדרות שלך\n/language — שינוי שפה · Language\n\n"
            "🔗 רוצה גם להתחבר באתר (Google)? <a href=\"{account_url}\">לכניסה לאזור האישי</a>"
        ),
        "en": (
            "👋 Hi {name}!\n"
            "I'm <b>Todira</b> 🏠, the bot that finds you an apartment.\n"
            "I scan the housing market around the clock and message you <b>the moment</b> a listing matches your "
            "search 🔔\n\n"
            "✍️ <b>Just tell me what you're looking for</b>, in your own words, and I'll understand.\n"
            "💬 For example: <i>\"3 rooms in Tel Aviv up to ₪8,000 with a balcony\"</i>\n\n⠀\n"
            "📋 <b>Commands:</b>\n/filter — set/update your filter\n/apartments — the latest matching listings\n"
            "/liked — listings you saved\n/profile — your profile and settings\n/language — change language · שפה\n\n"
            "🔗 Want to also sign in on the website (Google)? <a href=\"{account_url}\">Open my account</a>"
        ),
        "ru": (
            "👋 Привет, {name}!\n"
            "Я <b>Todira</b> 🏠, бот, который ищет для вас квартиру.\n"
            "Я постоянно слежу за рынком жилья и пишу вам <b>сразу</b>, как появляется объявление под ваш "
            "поиск 🔔\n\n"
            "✍️ <b>Просто напишите, что вы ищете</b>, своими словами, и я пойму.\n"
            "💬 Например: <i>«3 комнаты в Тель-Авиве до 8 000 ₪ с балконом»</i>\n\n⠀\n"
            "📋 <b>Команды:</b>\n/filter — настроить/изменить фильтр\n/apartments — последние подходящие "
            "объявления\n/liked — сохранённые объявления\n/profile — ваш профиль и настройки\n/language — сменить язык · שפה\n\n"
            "🔗 Хотите также входить на сайте (Google)? <a href=\"{account_url}\">Открыть личный кабинет</a>"
        ),
        "fr": (
            "👋 Salut {name} !\n"
            "Je suis <b>Todira</b> 🏠, le bot qui te trouve un appartement.\n"
            "Je scrute le marché immobilier en continu et je te préviens <b>dès qu'une annonce</b> correspond à "
            "ta recherche 🔔\n\n"
            "✍️ <b>Écris-moi simplement ce que tu cherches</b>, avec tes propres mots, et je comprendrai.\n"
            "💬 Par exemple : <i>« 3 pièces à Tel Aviv jusqu'à 8 000 ₪ avec balcon »</i>\n\n⠀\n"
            "📋 <b>Commandes :</b>\n/filter — définir/modifier ton filtre\n/apartments — les dernières "
            "annonces correspondantes\n/liked — les annonces enregistrées\n/profile — ton profil et "
            "tes réglages\n/language — changer de langue · שפה\n\n"
            "🔗 Tu veux aussi te connecter sur le site (Google) ? <a href=\"{account_url}\">Ouvrir mon espace</a>"
        ),
        "ar": (
            "👋 مرحباً {name}!\n"
            "أنا <b>Todira</b> 🏠، البوت الذي يبحث لك عن شقة.\n"
            "أراقب سوق الشقق باستمرار وأرسل لك رسالة <b>فور</b> ظهور شقة تطابق بحثك 🔔\n\n"
            "✍️ <b>اكتب لي ببساطة ما تبحث عنه</b> بكلماتك الخاصة، وسأفهم.\n"
            "💬 مثلاً: <i>\"3 غرف في تل أبيب حتى 8,000 ₪ مع شرفة\"</i>\n\n⠀\n"
            "📋 <b>الأوامر:</b>\n/filter — ضبط/تحديث تفضيلاتك\n/apartments — أحدث الإعلانات "
            "المطابقة\n/liked — الإعلانات المحفوظة\n/profile — ملفك الشخصي وإعداداتك\n/language — تغيير اللغة · שפה\n\n"
            "🔗 هل تريد أيضاً تسجيل الدخول عبر الموقع (Google)؟ <a href=\"{account_url}\">فتح حسابي</a>"
        ),
    },
    "start.linked": {
        "he": "🎉 חיברתי! אתה כבר רשום ומעודכן אצלי במערכת — מעכשיו תקבל עדכונים גם כאן בטלגרם.",
        "en": "🎉 Connected! You're already registered with me — from now on you'll get updates "
        "here on Telegram too.",
        "ru": "🎉 Подключено! Вы уже зарегистрированы у меня — теперь вы будете получать "
        "обновления и здесь, в Telegram.",
        "fr": "🎉 Connecté ! Tu es déjà enregistré chez moi — tu recevras désormais aussi les mises "
        "à jour ici, sur Telegram.",
        "ar": "🎉 تم الربط! أنت مسجل بالفعل لدي — من الآن ستصلك التحديثات هنا في تيليجرام أيضاً.",
    },
    "start.link_conflict": {
        "he": "לחשבון הטלגרם הזה כבר יש חשבון נפרד אצלי, אז אי אפשר לחבר אותו לחשבון אחר. אם זו "
        "טעות, כתוב/י לנו דרך /contact.",
        "en": "This Telegram account already has its own separate account with me, so it can't be "
        "linked to another one. If this is a mistake, message us via /contact.",
        "ru": "У этого аккаунта Telegram уже есть отдельный аккаунт у меня, поэтому привязать его "
        "к другому нельзя. Если это ошибка — напишите нам через /contact.",
        "fr": "Ce compte Telegram a déjà son propre compte séparé chez moi, il ne peut donc pas "
        "être lié à un autre. Si c'est une erreur, écris-nous via /contact.",
        "ar": "هذا الحساب على تيليجرام لديه بالفعل حساب منفصل عندي، لذا لا يمكن ربطه بحساب آخر. "
        "إذا كان هذا خطأ، راسلنا عبر /contact.",
    },
    "start.google_linked_note": {
        "he": "🔗 חשבון ה-Google שלך קושר בהצלחה לחשבון הזה — מעכשיו אפשר להתחבר איתו באתר, מכל "
        "דפדפן.\n\n",
        "en": "🔗 Your Google account was successfully linked to this account — from now on you can "
        "sign in with it on the website, from any browser.\n\n",
        "ru": "🔗 Ваш аккаунт Google успешно привязан к этому аккаунту — теперь вы можете входить "
        "с его помощью на сайте, из любого браузера.\n\n",
        "fr": "🔗 Ton compte Google a bien été lié à ce compte — tu peux désormais te connecter avec "
        "lui sur le site, depuis n'importe quel navigateur.\n\n",
        "ar": "🔗 تم ربط حساب Google الخاص بك بهذا الحساب بنجاح — يمكنك الآن تسجيل الدخول به على "
        "الموقع، من أي متصفح.\n\n",
    },
    "start.renewal_needed": {
        "he": "היי {name}! 👋 שוב אנחנו?\n\nשמתי לב שתקופת הגישה שלך הסתיימה, אז ההתראות מושהות "
        "כרגע. {cities_line}רוצה שנחדש את המנוי ונחזור לחפש לך דירה? אפשר ישר כאן: {upgrade_url} "
        "🔥🏠",
        "en": "Hi {name}! 👋 Us again?\n\nI noticed your access period has ended, so notifications "
        "are paused right now. {cities_line}Want to renew your subscription and get back to "
        "searching? Right here: {upgrade_url} 🔥🏠",
        "ru": "Привет, {name}! 👋 Снова мы?\n\nЗаметил, что срок вашего доступа закончился, поэтому "
        "уведомления сейчас приостановлены. {cities_line}Хотите продлить подписку и снова начать "
        "поиск? Прямо здесь: {upgrade_url} 🔥🏠",
        "fr": "Salut {name} ! 👋 Encore nous ?\n\nJ'ai remarqué que ta période d'accès est terminée, "
        "les notifications sont donc en pause. {cities_line}Tu veux renouveler ton abonnement et "
        "reprendre la recherche ? Juste ici : {upgrade_url} 🔥🏠",
        "ar": "مرحباً {name}! 👋 نحن مجدداً؟\n\nلاحظت أن فترة وصولك انتهت، لذا الإشعارات متوقفة "
        "مؤقتاً. {cities_line}هل تريد تجديد اشتراكك والعودة للبحث؟ مباشرة هنا: {upgrade_url} 🔥🏠",
    },
    "start.renewal_cities_line": {
        "he": "מתגעגע/ת לעדכונים על {cities}? ",
        "en": "Missing updates about {cities}? ",
        "ru": "Скучаете по новостям о {cities}? ",
        "fr": "Les mises à jour sur {cities} te manquent ? ",
        "ar": "تفتقد التحديثات عن {cities}؟ ",
    },
    "onboarding.intro_prompt": {
        "he": "ספר/י לי בכמה מילים מה את/ה מחפש/ת — למשל עיר, שכירות/קנייה/סאבלט, תקציב, כמה חדרים, "
        "וכל דבר נוסף שחשוב לך. אפשר לכתוב חופשי, אני אבין 🙂\n"
        "🎯 לדיוק של 100% אפשר להגדיר הכל בכפתורים עם /filter, בכל שלב.",
        "en": "Tell me in a few words what you're looking for — e.g. city, rent/buy/sublet, budget, how many rooms, "
        "and anything else that matters to you. Feel free to write naturally, I'll understand 🙂\n"
        "🎯 For 100% accuracy, you can set everything with buttons using /filter, at any point.",
        "ru": "Расскажите в нескольких словах, что вы ищете — например, город, аренда/покупка/субаренда, бюджет, "
        "сколько комнат, и что ещё для вас важно. Можно писать свободно, я пойму 🙂\n"
        "🎯 Для 100% точности всё можно настроить кнопками через /filter в любой момент.",
        "fr": "Dis-moi en quelques mots ce que tu cherches — par exemple ville, location/achat/sous-location, budget, "
        "nombre de pièces, et tout ce qui compte pour toi. Écris librement, je comprendrai 🙂\n"
        "🎯 Pour une précision de 100 %, tu peux tout régler avec les boutons via /filter, à tout moment.",
        "ar": "أخبرني ببضع كلمات عما تبحث عنه — مثل المدينة، إيجار/شراء/تأجير من الباطن، الميزانية، عدد الغرف، "
        "وأي شيء آخر يهمك. اكتب بحرية، سأفهم 🙂\n"
        "🎯 لدقة 100٪ يمكنك ضبط كل شيء بالأزرار عبر /filter في أي وقت.",
    },
    "onboarding.cancelled_for_other_command": {
        "he": "ביטלתי את תהליך ההרשמה החופשי — שלח/י שוב את הפקודה כדי להמשיך 👍",
        "en": "I cancelled the free-text registration — send the command again to continue 👍",
        "ru": "Я отменил свободную регистрацию — отправьте команду ещё раз, чтобы продолжить 👍",
        "fr": "J'ai annulé l'inscription en texte libre — renvoie la commande pour continuer 👍",
        "ar": "ألغيت عملية التسجيل بالنص الحر — أرسل الأمر مرة أخرى للمتابعة 👍",
    },
    "onboarding.help_request_precheck": {
        "he": "🙋 קיבלתי, העברתי את הפנייה שלך לצוות ותקבל/י מענה בהקדם.\n\nבינתיים, אם תרצה/י "
        "להמשיך לחפש דירה — ספר/י לי מה מחפשים (עיר, שכירות/מכירה/סבלט וכו').",
        "en": "🙋 Got it, I've passed your message to the team and you'll hear back soon.\n\nIn "
        "the meantime, if you'd like to keep searching for an apartment — tell me what you're "
        "looking for (city, rent/sale/sublet, etc).",
        "ru": "🙋 Понял, передал ваше сообщение команде, скоро с вами свяжутся.\n\nА пока, если "
        "хотите продолжить поиск квартиры — расскажите, что вы ищете (город, аренда/покупка/"
        "субаренда и т.д.).",
        "fr": "🙋 Compris, j'ai transmis ton message à l'équipe, tu auras une réponse bientôt.\n\n"
        "En attendant, si tu veux continuer à chercher un appartement — dis-moi ce que tu cherches "
        "(ville, location/vente/sous-location, etc).",
        "ar": "🙋 فهمت، أحلت رسالتك إلى الفريق وستصلك إجابة قريباً.\n\nفي هذه الأثناء، إذا أردت "
        "متابعة البحث عن شقة — أخبرني ماذا تبحث عنه (المدينة، إيجار/بيع/تأجير من الباطن، إلخ).",
    },
    "onboarding.checking": {
        "he": "🔍 רגע, טודירה בודק את מה שכתבת...",
        "en": "🔍 One sec, Todira's checking what you wrote...",
        "ru": "🔍 Секунду, Тодира проверяет, что вы написали...",
        "fr": "🔍 Une seconde, Todira vérifie ce que tu as écrit...",
        "ar": "🔍 لحظة، تودّيرا يتحقق مما كتبته...",
    },
    # 2026-10-13 (owner report: Gemini out of credit, every new user got errors): onboarding reads the message with free
    # rules first and asks for what's missing with buttons (bot/handlers/onboarding.py, todira_common/search_text.py).
    "onboarding.understood": {
        "he": "🔎 החיפוש שלך פעיל: {summary}",
        "en": "🔎 Your search is on: {summary}",
        "ru": "🔎 Ваш поиск активен: {summary}",
        "fr": "🔎 Ta recherche est active : {summary}",
        "ar": "🔎 بحثك نشط: {summary}",
    },
    "onboarding.known_so_far": {
        "he": "הבנתי: {summary}.\n",
        "en": "Got it: {summary}.\n",
        "ru": "Понял: {summary}.\n",
        "fr": "Compris : {summary}.\n",
        "ar": "فهمت: {summary}.\n",
    },
    "onboarding.ask_deal": {
        "he": "מה מחפשים? 👇",
        "en": "What are you looking for? 👇",
        "ru": "Что вы ищете? 👇",
        "fr": "Tu cherches quoi ? 👇",
        "ar": "ماذا تبحث؟ 👇",
    },
    "onboarding.btn_rent": {"he": "🏠 שכירות", "en": "🏠 Rent", "ru": "🏠 Аренда", "fr": "🏠 Location", "ar": "🏠 إيجار"},
    "onboarding.btn_sale": {"he": "🔑 קנייה", "en": "🔑 Buy", "ru": "🔑 Покупка", "fr": "🔑 Achat", "ar": "🔑 شراء"},
    "onboarding.btn_sublet": {
        "he": "🛏️ סאבלט", "en": "🛏️ Sublet", "ru": "🛏️ Субаренда", "fr": "🛏️ Sous-location", "ar": "🛏️ تأجير من الباطن",
    },
    "onboarding.deal_rent": {"he": "שכירות", "en": "rent", "ru": "аренда", "fr": "location", "ar": "إيجار"},
    "onboarding.deal_sale": {"he": "קנייה", "en": "buy", "ru": "покупка", "fr": "achat", "ar": "شراء"},
    "onboarding.deal_sublet": {"he": "סאבלט", "en": "sublet", "ru": "субаренда", "fr": "sous-location", "ar": "تأجير من الباطن"},
    "onboarding.rooms": {"he": "{rooms} חדרים", "en": "{rooms} rooms", "ru": "комнат: {rooms}", "fr": "{rooms} pièces", "ar": "{rooms} غرف"},
    "onboarding.rooms_up_to": {
        "he": "עד {rooms} חדרים", "en": "up to {rooms} rooms", "ru": "до {rooms} комнат", "fr": "jusqu'à {rooms} pièces",
        "ar": "حتى {rooms} غرف",
    },
    "onboarding.price_up_to": {
        "he": "עד ₪{price}", "en": "up to ₪{price}", "ru": "до ₪{price}", "fr": "jusqu'à ₪{price}", "ar": "حتى ₪{price}",
    },
    "onboarding.price_from": {
        "he": "מ־₪{price}", "en": "from ₪{price}", "ru": "от ₪{price}", "fr": "à partir de ₪{price}", "ar": "من ₪{price}",
    },
    "onboarding.ask_city": {
        "he": "באיזו עיר מחפשים? אפשר לכתוב גם כמה ערים 🙂",
        "en": "Which city? You can write several 🙂",
        "ru": "В каком городе? Можно указать несколько 🙂",
        "fr": "Dans quelle ville ? Tu peux en écrire plusieurs 🙂",
        "ar": "في أي مدينة؟ يمكنك كتابة عدة مدن 🙂",
    },
    "onboarding.city_suggest": {
        "he": "לא מצאתי עיר בשם הזה. התכוונת לאחת מאלה? 👇",
        "en": "I couldn't find that city. Did you mean one of these? 👇",
        "ru": "Не нашёл такой город. Может, один из этих? 👇",
        "fr": "Je n'ai pas trouvé cette ville. Tu voulais dire l'une de celles-ci ? 👇",
        "ar": "لم أجد هذه المدينة. هل تقصد إحدى هذه؟ 👇",
    },
    "onboarding.city_unknown": {
        "he": "לא מצאתי את העיר הזו ברשימה שלנו 🤔 אפשר לכתוב עיר אחרת, או לבחור מהרשימה המלאה ב-/filter",
        "en": "I couldn't find that city in our list 🤔 Try another city, or pick from the full list with /filter",
        "ru": "Не нашёл этот город в нашем списке 🤔 Напишите другой город или выберите из полного списка через /filter",
        "fr": "Je n'ai pas trouvé cette ville dans notre liste 🤔 Écris une autre ville, ou choisis dans la liste complète "
        "avec /filter",
        "ar": "لم أجد هذه المدينة في قائمتنا 🤔 اكتب مدينة أخرى، أو اختر من القائمة الكاملة عبر /filter",
    },
    "onboarding.needs_human_help": {
        "he": "🙋 קיבלתי, זה נשמע כמו משהו שכדאי שבן אדם אמיתי יענה עליו — העברתי את ההודעה שלך "
        "לצוות ותקבל/י מענה בהקדם.\n\nאם תרצה/י להמשיך לחפש דירה בינתיים, אפשר לכתוב לי עוד "
        "פרטים 🙂",
        "en": "🙋 Got it — this sounds like something a real person should answer, so I've passed "
        "your message to the team and you'll hear back soon.\n\nIf you'd like to keep searching for "
        "an apartment meanwhile, feel free to tell me more details 🙂",
        "ru": "🙋 Понял, похоже, на это лучше ответит живой человек — передал ваше сообщение "
        "команде, скоро свяжутся с вами.\n\nЕсли хотите пока продолжить поиск квартиры — можете "
        "написать мне ещё детали 🙂",
        "fr": "🙋 Compris, ça ressemble à quelque chose qu'une vraie personne devrait traiter — j'ai "
        "transmis ton message à l'équipe, tu auras une réponse bientôt.\n\nSi tu veux continuer à "
        "chercher un appartement en attendant, n'hésite pas à me donner plus de détails 🙂",
        "ar": "🙋 فهمت، يبدو أن هذا شيء يجب أن يرد عليه شخص حقيقي — أحلت رسالتك إلى الفريق وستصلك "
        "إجابة قريباً.\n\nإذا أردت متابعة البحث عن شقة في هذه الأثناء، يمكنك إخباري بمزيد من "
        "التفاصيل 🙂",
    },
    "onboarding.default_ack": {
        "he": "רשמתי, תודה!",
        "en": "Got it, thanks!",
        "ru": "Записал, спасибо!",
        "fr": "C'est noté, merci !",
        "ar": "تم التسجيل، شكراً!",
    },
    "onboarding.filter_hint": {
        "he": "אפשר תמיד להרחיב את הסינון (מחיר, קומה, דרישות ועוד) עם /filter ⚙️",
        "en": "You can always broaden your filter (price, floor, requirements, and more) with "
        "/filter ⚙️",
        "ru": "Фильтр всегда можно расширить (цена, этаж, требования и т.д.) через /filter ⚙️",
        "fr": "Tu peux toujours élargir ton filtre (prix, étage, exigences, etc.) avec /filter ⚙️",
        "ar": "يمكنك دائماً توسيع تفضيلاتك (السعر، الطابق، المتطلبات وغيرها) عبر /filter ⚙️",
    },
    "onboarding.matches_found": {
        "he": "👀 יש כרגע {total} דירות שמתאימות — כולן כאן: {apartments_url}",
        "en": "👀 There are currently {total} matching apartments — all of them here: "
        "{apartments_url}",
        "ru": "👀 Сейчас есть {total} подходящих квартир — все они здесь: {apartments_url}",
        "fr": "👀 Il y a actuellement {total} appartements correspondants — tous ici : "
        "{apartments_url}",
        "ar": "👀 يوجد حالياً {total} شقة مطابقة — جميعها هنا: {apartments_url}",
    },
    "onboarding.no_matches_yet": {
        "he": "עדיין אין דירות תואמות כרגע — אני אמשיך לחפש ואודיע לך. אפשר גם לעקוב באתר: "
        "{apartments_url}",
        "en": "No matching apartments yet — I'll keep searching and let you know. You can also "
        "follow along on the website: {apartments_url}",
        "ru": "Пока нет подходящих квартир — я продолжу искать и сообщу вам. Также можно следить "
        "на сайте: {apartments_url}",
        "fr": "Pas encore d'appartement correspondant — je continue de chercher et je te préviens. "
        "Tu peux aussi suivre ça sur le site : {apartments_url}",
        "ar": "لا توجد شقق مطابقة بعد — سأستمر بالبحث وأخبرك. يمكنك أيضاً المتابعة عبر الموقع: "
        "{apartments_url}",
    },
    # 2026-10-18: a message the bot could not turn into a search change, with an example of what works.
    "contact_fallback.not_understood": {
        "he": "לא הבנתי מה לשנות בחיפוש 🤔\nאפשר לכתוב לי למשל: ״3 חדרים בחיפה עד 6,000 ₪״ או ״תוסיף גם רמת גן״.\n"
        "לכל ההגדרות: /filter · לדירות שנמצאו: /apartments",
        "en": "I didn't catch what to change in your search 🤔\nYou can write, for example: \"3 rooms in Haifa up to "
        "₪6,000\" or \"add Ramat Gan too\".\nAll settings: /filter · Listings found: /apartments",
        "ru": "Не понял, что изменить в поиске 🤔\nМожно написать, например: «3 комнаты в Хайфе до 6 000 ₪» или "
        "«добавь Рамат-Ган».\nВсе настройки: /filter · Найденные квартиры: /apartments",
        "fr": "Je n'ai pas compris quoi changer dans ta recherche 🤔\nTu peux écrire par exemple : « 3 pièces à Haïfa "
        "jusqu'à 6 000 ₪ » ou « ajoute aussi Ramat Gan ».\nTous les réglages : /filter · Annonces trouvées : /apartments",
        "ar": "لم أفهم ما الذي يجب تغييره في البحث 🤔\nيمكنك أن تكتب مثلاً: «3 غرف في حيفا حتى 6,000 ₪» أو "
        "«أضف رمات غان أيضاً».\nكل الإعدادات: /filter · الشقق التي وُجدت: /apartments",
    },
    "contact_fallback.updated": {
        "he": "✅ עדכנתי את החיפוש שלך: {summary}",
        "en": "✅ I updated your search: {summary}",
        "ru": "✅ Обновил ваш поиск: {summary}",
        "fr": "✅ J'ai mis à jour ta recherche : {summary}",
        "ar": "✅ حدّثت بحثك: {summary}",
    },
    "contact_fallback.thanks": {
        "he": "בכיף! 🙂 אני ממשיך לחפש ואעדכן אותך ברגע שעולה דירה מתאימה.",
        "en": "Anytime! 🙂 I'll keep searching and let you know the moment a matching apartment comes up.",
        "ru": "Всегда пожалуйста! 🙂 Продолжаю искать и сразу сообщу, когда появится подходящая квартира.",
        "fr": "Avec plaisir ! 🙂 Je continue à chercher et je te préviens dès qu'un appartement correspond.",
        "ar": "على الرحب! 🙂 سأواصل البحث وأخبرك فور ظهور شقة مناسبة.",
    },
    "contact_fallback.default_ack": {
        "he": "בסדר! 🙂",
        "en": "Okay! 🙂",
        "ru": "Хорошо! 🙂",
        "fr": "D'accord ! 🙂",
        "ar": "حسناً! 🙂",
    },
    # 2026-10-18: the one-time message bot/announce_trial_extension.py sends (trial 3 -> 10 days, +7 for everyone).
    "trial_gift.telegram": {
        "he": "🎁 מתנה מטודירה!\nפתחנו לך עוד 7 ימים של גישה מלאה וחינמית, עד {date} 🙌\n"
        "אני ממשיך לחפש ושולח לך כל דירה חדשה שמתאימה לחיפוש שלך.\nלכל הדירות שמתאימות לך: /apartments",
        "en": "🎁 A gift from Todira!\nYou get 7 more days of full, free access, until {date} 🙌\n"
        "I keep searching and send you every new apartment that matches your search.\nAll your matches: /apartments",
        "ru": "🎁 Подарок от Todira!\nВам открыто ещё 7 дней полного бесплатного доступа, до {date} 🙌\n"
        "Я продолжаю искать и присылаю каждую новую подходящую квартиру.\nВсе подходящие квартиры: /apartments",
        "fr": "🎁 Un cadeau de Todira !\nTu as 7 jours de plus d'accès complet et gratuit, jusqu'au {date} 🙌\n"
        "Je continue à chercher et je t'envoie chaque nouvel appartement qui correspond.\nToutes tes annonces : /apartments",
        "ar": "🎁 هدية من Todira!\nلديك 7 أيام إضافية من الوصول الكامل المجاني، حتى {date} 🙌\n"
        "أواصل البحث وأرسل لك كل شقة جديدة تناسب بحثك.\nكل الشقق المناسبة لك: /apartments",
    },
    "contact_fallback.help_escalated": {
        "he": "תודה שכתבת! ההודעה שלך התקבלה ואנחנו נחזור אליך בהקדם 🙏\n\nלחיפוש דירות: /start",
        "en": "Thanks for writing! Your message was received and we'll get back to you soon 🙏\n\n"
        "To search for apartments: /start",
        "ru": "Спасибо за сообщение! Мы его получили и скоро свяжемся с вами 🙏\n\nЧтобы искать "
        "квартиры: /start",
        "fr": "Merci pour ton message ! Il a bien été reçu, on te répond bientôt 🙏\n\nPour "
        "chercher un appartement : /start",
        "ar": "شكراً لكتابتك! تم استلام رسالتك وسنعاود التواصل معك قريباً 🙏\n\nللبحث عن شقق: "
        "/start",
    },
    "contact_fallback.new_user_prompt": {
        "he": "היי! 🐶 אני טודירה, בוט חיפוש הדירות. כדי להתחיל לחפש דירה, שלח/י /start.",
        "en": "Hi! 🐶 I'm Todira, the apartment-search bot. To start searching, send /start.",
        "ru": "Привет! 🐶 Я Тодира, бот для поиска квартир. Чтобы начать поиск, отправьте /start.",
        "fr": "Salut ! 🐶 Je suis Todira, le bot de recherche d'appartements. Pour commencer, "
        "envoie /start.",
        "ar": "مرحباً! 🐶 أنا تودّيرا، بوت البحث عن الشقق. للبدء بالبحث، أرسل /start.",
    },
    "renewal.reminder": {
        "he": "היי! הגישה שלך לטודירה מסתיימת ב-{date} ⏰ כדי להמשיך לקבל דירות ולראות פרטים אפשר לחדש כאן: {url}",
        "en": "Hi! Your Todira access ends on {date} ⏰ To keep getting listings and details, renew here: {url}",
        "ru": "Привет! Ваш доступ к Todira заканчивается {date} ⏰ Чтобы продолжать получать объявления и детали, продлите здесь: {url}",
        "fr": "Salut ! Ton accès à Todira se termine le {date} ⏰ Pour continuer à recevoir les annonces et les détails, renouvelle ici : {url}",
        "ar": "مرحباً! ينتهي وصولك إلى Todira في {date} ⏰ لمتابعة تلقي الإعلانات والتفاصيل جدّد من هنا: {url}",
    },
    # 2026-10-16 (owner): one message before the free trial ends - scraper/renewal_reminder.py.
    "trial.reminder": {
        "he": "היי! הניסיון החינמי שלך בטודירה נגמר {when} ⏳ רוצה להמשיך לקבל דירות עם כל הפרטים והקישור למודעה? אפשר לשדרג פה: {url}",
        "en": "Hi! Your free Todira trial ends {when} ⏳ Want to keep getting listings with all the details and the link to the ad? Upgrade here: {url}",
        "ru": "Привет! Ваш бесплатный пробный период в Todira заканчивается {when} ⏳ Хотите и дальше получать объявления со всеми деталями и ссылкой? Оформите доступ здесь: {url}",
        "fr": "Salut ! Ton essai gratuit de Todira se termine {when} ⏳ Tu veux continuer à recevoir les annonces avec tous les détails et le lien ? Passe à l'offre complète ici : {url}",
        "ar": "مرحباً! تنتهي فترتك التجريبية المجانية في Todira {when} ⏳ تريد الاستمرار في تلقي الإعلانات مع كل التفاصيل والرابط؟ رقِّ اشتراكك من هنا: {url}",
    },
    "trial.when_today": {
        "he": "היום ב־{time}", "en": "today at {time}", "ru": "сегодня в {time}", "fr": "aujourd'hui à {time}", "ar": "اليوم الساعة {time}",
    },
    "trial.when_tomorrow": {
        "he": "מחר ב־{time}", "en": "tomorrow at {time}", "ru": "завтра в {time}", "fr": "demain à {time}", "ar": "غداً الساعة {time}",
    },
    "trial.when_date": {
        "he": "ב־{date}", "en": "on {date}", "ru": "{date}", "fr": "le {date}", "ar": "في {date}",
    },
    "profile.header": {
        "he": "👤 <b>הפרופיל שלך</b>", "en": "👤 <b>Your profile</b>",
        "ru": "👤 <b>Ваш профиль</b>", "fr": "👤 <b>Ton profil</b>", "ar": "👤 <b>ملفك الشخصي</b>",
    },
    "profile.status_line": {
        "he": "סטטוס חיפוש: {status}", "en": "Search status: {status}",
        "ru": "Статус поиска: {status}", "fr": "Statut de recherche : {status}",
        "ar": "حالة البحث: {status}",
    },
    "profile.status_active": {
        "he": "🟢 פעיל", "en": "🟢 Active", "ru": "🟢 Активен", "fr": "🟢 Actif", "ar": "🟢 نشط",
    },
    "profile.status_paused": {
        "he": "⏸️ מושהה", "en": "⏸️ Paused", "ru": "⏸️ Приостановлен", "fr": "⏸️ En pause",
        "ar": "⏸️ متوقف مؤقتاً",
    },
    "profile.notifications_line": {
        "he": "התראות: {status}", "en": "Notifications: {status}",
        "ru": "Уведомления: {status}", "fr": "Notifications : {status}", "ar": "الإشعارات: {status}",
    },
    "profile.notifications_on": {
        "he": "🔔 מופעלות", "en": "🔔 On", "ru": "🔔 Включены", "fr": "🔔 Activées", "ar": "🔔 مفعّلة",
    },
    "profile.notifications_off": {
        "he": "🔕 כבויות", "en": "🔕 Off", "ru": "🔕 Выключены", "fr": "🔕 Désactivées",
        "ar": "🔕 معطّلة",
    },
    "profile.total_sent_line": {
        "he": 'סה"כ התראות שנשלחו: {count}', "en": "Total notifications sent: {count}",
        "ru": "Всего отправлено уведомлений: {count}", "fr": "Total des notifications envoyées : {count}",
        "ar": "إجمالي الإشعارات المرسلة: {count}",
    },
    "profile.no_filter_line": {
        "he": "\nעדיין לא הגדרת סינון. שלח/י /filter כדי להתחיל.",
        "en": "\nYou haven't set a filter yet. Send /filter to get started.",
        "ru": "\nВы ещё не настроили фильтр. Отправьте /filter, чтобы начать.",
        "fr": "\nTu n'as pas encore configuré de filtre. Envoie /filter pour commencer.",
        "ar": "\nلم تقم بضبط تفضيلاتك بعد. أرسل /filter للبدء.",
    },
    "profile.btn_pause": {
        "he": "⏸️ השהה חיפוש", "en": "⏸️ Pause search", "ru": "⏸️ Приостановить поиск",
        "fr": "⏸️ Mettre en pause", "ar": "⏸️ إيقاف البحث مؤقتاً",
    },
    "profile.btn_resume": {
        "he": "▶️ המשך חיפוש", "en": "▶️ Resume search", "ru": "▶️ Продолжить поиск",
        "fr": "▶️ Reprendre la recherche", "ar": "▶️ متابعة البحث",
    },
    "profile.btn_notif_off": {
        "he": "🔕 כבה התראות", "en": "🔕 Turn off notifications", "ru": "🔕 Выключить уведомления",
        "fr": "🔕 Désactiver les notifications", "ar": "🔕 إيقاف الإشعارات",
    },
    "profile.btn_language": {
        "he": "🌐 שפה · Language", "en": "🌐 Language · שפה", "ru": "🌐 Язык · שפה",
        "fr": "🌐 Langue · שפה", "ar": "🌐 اللغة · שפה",
    },
    # 2026-10-18: /language (bot/handlers/language.py). The prompt names the choice in every language, since the
    # person picking may not read the language the bot is in right now.
    "language.prompt": {
        lang: "🌐 בחר/י שפה · Choose a language · Выберите язык · Choisis ta langue · اختر لغتك"
        for lang in ("he", "en", "ru", "fr", "ar")
    },
    "language.changed": {
        "he": "✅ מעכשיו אדבר איתך בעברית.",
        "en": "✅ Done, I'll talk to you in English from now on.",
        "ru": "✅ Готово, теперь я буду писать вам по-русски.",
        "fr": "✅ C'est fait, je te parlerai en français désormais.",
        "ar": "✅ تم، سأتحدث معك بالعربية من الآن.",
    },
    "profile.btn_notif_on": {
        "he": "🔔 הפעל התראות", "en": "🔔 Turn on notifications", "ru": "🔔 Включить уведомления",
        "fr": "🔔 Activer les notifications", "ar": "🔔 تفعيل الإشعارات",
    },
    "apartments.no_filter_yet": {
        "he": "עדיין לא הגדרת סינון. שלח/י /filter כדי להתחיל.",
        "en": "You haven't set a filter yet. Send /filter to get started.",
        "ru": "Вы ещё не настроили фильтр. Отправьте /filter, чтобы начать.",
        "fr": "Tu n'as pas encore configuré de filtre. Envoie /filter pour commencer.",
        "ar": "لم تقم بضبط تفضيلاتك بعد. أرسل /filter للبدء.",
    },
    "apartments.no_matches": {
        "he": "לא נמצאו כרגע דירות תואמות. אני אמשיך לחפש ואודיע לך כשתתפרסם דירה מתאימה. אפשר גם "
        "לעקוב באתר: {apartments_url}",
        "en": "No matching apartments found right now. I'll keep searching and let you know when a "
        "matching one is published. You can also follow along on the website: {apartments_url}",
        "ru": "Сейчас подходящих квартир не найдено. Я продолжу искать и сообщу, когда появится "
        "подходящая. Также можно следить на сайте: {apartments_url}",
        "fr": "Aucun appartement correspondant trouvé pour l'instant. Je continue de chercher et te "
        "préviens dès qu'un appartement correspondant est publié. Tu peux aussi suivre ça sur le "
        "site : {apartments_url}",
        "ar": "لم يتم العثور على شقق مطابقة حالياً. سأستمر بالبحث وأخبرك عند نشر شقة مطابقة. يمكنك "
        "أيضاً المتابعة عبر الموقع: {apartments_url}",
    },
    "liked.no_liked_yet": {
        "he": "עדיין לא שמרת אף דירה. אפשר ללחוץ ❤️ שמור על כרטיס דירה כדי לשמור אותה כאן.",
        "en": "You haven't saved any apartment yet. Tap ❤️ Save on a listing card to save it here.",
        "ru": "Вы ещё не сохранили ни одной квартиры. Нажмите ❤️ Сохранить на карточке объявления, "
        "чтобы сохранить её здесь.",
        "fr": "Tu n'as encore enregistré aucun appartement. Appuie sur ❤️ Enregistrer sur une "
        "annonce pour l'enregistrer ici.",
        "ar": "لم تحفظ أي شقة بعد. اضغط ❤️ حفظ على بطاقة الإعلان لحفظها هنا.",
    },
    "liked.no_hidden": {
        "he": "אין לך כרגע דירות מוסתרות.",
        "en": "You don't have any hidden apartments right now.",
        "ru": "У вас сейчас нет скрытых квартир.",
        "fr": "Tu n'as aucun appartement masqué pour le moment.",
        "ar": "ليس لديك حالياً أي شقق مخفية.",
    },
    "liked.found_paused": {
        "he": "מזל טוב! השהיתי את החיפוש עבורך. שלח/י /start כדי לחזור.",
        "en": "Congrats! I've paused your search. Send /start to come back.",
        "ru": "Поздравляем! Я приостановил ваш поиск. Отправьте /start, чтобы вернуться.",
        "fr": "Félicitations ! J'ai mis ta recherche en pause. Envoie /start pour revenir.",
        "ar": "مبروك! أوقفت بحثك مؤقتاً. أرسل /start للعودة.",
    },
    "liked.removed_from_liked": {
        "he": "הוסר מהשמורים 💔", "en": "Removed from saved 💔", "ru": "Удалено из сохранённых 💔",
        "fr": "Retiré des enregistrés 💔", "ar": "تمت الإزالة من المحفوظات 💔",
    },
    "liked.restored_to_list": {
        "he": "הוחזר לרשימה 👀", "en": "Restored to the list 👀", "ru": "Возвращено в список 👀",
        "fr": "Restauré dans la liste 👀", "ar": "تمت الإعادة إلى القائمة 👀",
    },
    "liked.saved": {
        "he": "נשמר ❤️", "en": "Saved ❤️", "ru": "Сохранено ❤️", "fr": "Enregistré ❤️",
        "ar": "تم الحفظ ❤️",
    },
    "liked.hidden": {
        "he": "הוסתר 🙈", "en": "Hidden 🙈", "ru": "Скрыто 🙈", "fr": "Masqué 🙈", "ar": "تم الإخفاء 🙈",
    },
    "liked.reaction_error": {
        "he": "משהו השתבש, נסה/י שוב 🙏", "en": "Something went wrong, please try again 🙏",
        "ru": "Что-то пошло не так, попробуйте ещё раз 🙏",
        "fr": "Une erreur s'est produite, réessaie 🙏", "ar": "حدث خطأ ما، حاول مرة أخرى 🙏",
    },
    "filter.prompt_city": {
        "he": "הקלד/י שם עיר לחיפוש:", "en": "Type a city name to search:",
        "ru": "Введите название города для поиска:", "fr": "Tape le nom d'une ville à rechercher :",
        "ar": "اكتب اسم مدينة للبحث:",
    },
    "filter.prompt_price_min": {
        "he": "הקלד/י מחיר מינימלי (או '-' לביטול הגבלה):",
        "en": "Type a minimum price (or '-' to remove the limit):",
        "ru": "Введите минимальную цену (или «-», чтобы убрать ограничение):",
        "fr": "Tape un prix minimum (ou « - » pour supprimer la limite) :",
        "ar": "اكتب الحد الأدنى للسعر (أو '-' لإلغاء الحد):",
    },
    "filter.prompt_price_max": {
        "he": "הקלד/י מחיר מקסימלי (או '-' לביטול הגבלה):",
        "en": "Type a maximum price (or '-' to remove the limit):",
        "ru": "Введите максимальную цену (или «-», чтобы убрать ограничение):",
        "fr": "Tape un prix maximum (ou « - » pour supprimer la limite) :",
        "ar": "اكتب الحد الأقصى للسعر (أو '-' لإلغاء الحد):",
    },
    "filter.prompt_rooms_min": {
        "he": "הקלד/י מספר חדרים מינימלי (למשל 2.5), או '-' לביטול:",
        "en": "Type a minimum number of rooms (e.g. 2.5), or '-' to cancel:",
        "ru": "Введите минимальное количество комнат (например, 2.5), или «-», чтобы отменить:",
        "fr": "Tape un nombre minimum de pièces (ex. 2.5), ou « - » pour annuler :",
        "ar": "اكتب الحد الأدنى لعدد الغرف (مثلاً 2.5)، أو '-' للإلغاء:",
    },
    "filter.prompt_rooms_max": {
        "he": "הקלד/י מספר חדרים מקסימלי, או '-' לביטול:",
        "en": "Type a maximum number of rooms, or '-' to cancel:",
        "ru": "Введите максимальное количество комнат, или «-», чтобы отменить:",
        "fr": "Tape un nombre maximum de pièces, ou « - » pour annuler :",
        "ar": "اكتب الحد الأقصى لعدد الغرف، أو '-' للإلغاء:",
    },
    "filter.prompt_floor_min": {
        "he": "הקלד/י קומה מינימלית, או '-' לביטול:",
        "en": "Type a minimum floor, or '-' to cancel:",
        "ru": "Введите минимальный этаж, или «-», чтобы отменить:",
        "fr": "Tape un étage minimum, ou « - » pour annuler :",
        "ar": "اكتب الحد الأدنى للطابق، أو '-' للإلغاء:",
    },
    "filter.prompt_floor_max": {
        "he": "הקלד/י קומה מקסימלית, או '-' לביטול:",
        "en": "Type a maximum floor, or '-' to cancel:",
        "ru": "Введите максимальный этаж, или «-», чтобы отменить:",
        "fr": "Tape un étage maximum, ou « - » pour annuler :",
        "ar": "اكتب الحد الأقصى للطابق، أو '-' للإلغاء:",
    },
    "filter.prompt_min_area_sqm": {
        "he": 'הקלד/י שטח מינימלי במ"ר, או \'-\' לביטול:',
        "en": "Type a minimum area in sqm, or '-' to cancel:",
        "ru": "Введите минимальную площадь в кв.м, или «-», чтобы отменить:",
        "fr": "Tape une superficie minimum en m², ou « - » pour annuler :",
        "ar": "اكتب الحد الأدنى للمساحة بالمتر المربع، أو '-' للإلغاء:",
    },
    "filter.prompt_keywords": {
        "he": "הקלד/י מילות מפתח מופרדות בפסיקים:",
        "en": "Type keywords separated by commas:",
        "ru": "Введите ключевые слова через запятую:",
        "fr": "Tape des mots-clés séparés par des virgules :",
        "ar": "اكتب كلمات مفتاحية مفصولة بفواصل:",
    },
    "filter.prompt_move_in_earliest": {
        "he": "הקלד/י תאריך מוקדם ביותר (YYYY-MM-DD), או '-' לביטול:",
        "en": "Type the earliest date (YYYY-MM-DD), or '-' to cancel:",
        "ru": "Введите самую раннюю дату (ГГГГ-ММ-ДД), или «-», чтобы отменить:",
        "fr": "Tape la date la plus tôt (AAAA-MM-JJ), ou « - » pour annuler :",
        "ar": "اكتب أقرب تاريخ (YYYY-MM-DD)، أو '-' للإلغاء:",
    },
    "filter.prompt_move_in_latest": {
        "he": "הקלד/י תאריך מאוחר ביותר (YYYY-MM-DD), או '-' לביטול:",
        "en": "Type the latest date (YYYY-MM-DD), or '-' to cancel:",
        "ru": "Введите самую позднюю дату (ГГГГ-ММ-ДД), или «-», чтобы отменить:",
        "fr": "Tape la date la plus tardive (AAAA-MM-JJ), ou « - » pour annuler :",
        "ar": "اكتب أبعد تاريخ (YYYY-MM-DD)، أو '-' للإلغاء:",
    },
    "filter.all_cities_note": {
        "he": "\n\n🌍 <i>כרגע: כל הערים (בלי הגבלה) — כולל ערים שלא ברשימה הקבועה.</i>",
        "en": "\n\n🌍 <i>Right now: every city (no restriction) — including cities not on the "
        "curated list.</i>",
        "ru": "\n\n🌍 <i>Сейчас: все города (без ограничений) — включая города не из "
        "составленного списка.</i>",
        "fr": "\n\n🌍 <i>Actuellement : toutes les villes (sans restriction) — y compris les "
        "villes hors de la liste organisée.</i>",
        "ar": "\n\n🌍 <i>حالياً: جميع المدن (بدون قيد) — بما في ذلك المدن غير المدرجة في "
        "القائمة المنسّقة.</i>",
    },
    "filter.validation_price_max": {
        "he": "💰 מחיר מקסימלי חייב להיות גדול או שווה למחיר מינימלי.",
        "en": "💰 Maximum price must be greater than or equal to the minimum price.",
        "ru": "💰 Максимальная цена должна быть больше или равна минимальной.",
        "fr": "💰 Le prix maximum doit être supérieur ou égal au prix minimum.",
        "ar": "💰 يجب أن يكون الحد الأقصى للسعر أكبر من أو يساوي الحد الأدنى.",
    },
    "filter.validation_rooms_max": {
        "he": "🛏️ מספר חדרים מקסימלי חייב להיות גדול או שווה למינימלי.",
        "en": "🛏️ Maximum rooms must be greater than or equal to the minimum.",
        "ru": "🛏️ Максимальное количество комнат должно быть больше или равно минимальному.",
        "fr": "🛏️ Le nombre maximum de pièces doit être supérieur ou égal au minimum.",
        "ar": "🛏️ يجب أن يكون الحد الأقصى لعدد الغرف أكبر من أو يساوي الحد الأدنى.",
    },
    "filter.validation_floor_max": {
        "he": "🏢 קומה מקסימלית חייבת להיות גדולה או שווה למינימלית.",
        "en": "🏢 Maximum floor must be greater than or equal to the minimum.",
        "ru": "🏢 Максимальный этаж должен быть больше или равен минимальному.",
        "fr": "🏢 L'étage maximum doit être supérieur ou égal au minimum.",
        "ar": "🏢 يجب أن يكون الحد الأقصى للطابق أكبر من أو يساوي الحد الأدنى.",
    },
    "filter.validation_move_in_latest": {
        "he": "📅 תאריך הכניסה המאוחר ביותר חייב להיות אחרי המוקדם ביותר.",
        "en": "📅 The latest move-in date must be after the earliest one.",
        "ru": "📅 Самая поздняя дата заселения должна быть позже самой ранней.",
        "fr": "📅 La date d'entrée la plus tardive doit être après la plus tôt.",
        "ar": "📅 يجب أن يكون أبعد تاريخ دخول بعد أقرب تاريخ.",
    },
    "filter.validation_generic_field": {
        "he": "שדה לא תקין: {field}", "en": "Invalid field: {field}",
        "ru": "Недопустимое поле: {field}", "fr": "Champ invalide : {field}",
        "ar": "حقل غير صالح: {field}",
    },
    "filter.fix_before_save": {
        "he": "⚠️ <b>לפני השמירה, תקן/י:</b>\n{warning}\n\n{summary}",
        "en": "⚠️ <b>Before saving, please fix:</b>\n{warning}\n\n{summary}",
        "ru": "⚠️ <b>Перед сохранением исправьте:</b>\n{warning}\n\n{summary}",
        "fr": "⚠️ <b>Avant d'enregistrer, corrige :</b>\n{warning}\n\n{summary}",
        "ar": "⚠️ <b>قبل الحفظ، يرجى تصحيح:</b>\n{warning}\n\n{summary}",
    },
    "filter.saved_confirmation": {
        "he": "✅ הסינון נשמר! תתחיל/י לקבל התראות על דירות מתאימות.",
        "en": "✅ Filter saved! You'll start getting notifications about matching apartments.",
        "ru": "✅ Фильтр сохранён! Вы начнёте получать уведомления о подходящих квартирах.",
        "fr": "✅ Filtre enregistré ! Tu vas commencer à recevoir des notifications pour les "
        "appartements correspondants.",
        "ar": "✅ تم حفظ التفضيلات! ستبدأ بتلقي إشعارات عن الشقق المطابقة.",
    },
    "filter.cancelled": {
        "he": "הסינון בוטל, לא נשמרו שינויים.",
        "en": "Filter editing cancelled, no changes were saved.",
        "ru": "Редактирование фильтра отменено, изменения не сохранены.",
        "fr": "Modification du filtre annulée, aucun changement enregistré.",
        "ar": "تم إلغاء تعديل التفضيلات، لم يتم حفظ أي تغييرات.",
    },
    "filter.cancelled_command": {
        "he": "הסינון בוטל.", "en": "Filter editing cancelled.",
        "ru": "Редактирование фильтра отменено.", "fr": "Modification du filtre annulée.",
        "ar": "تم إلغاء تعديل التفضيلات.",
    },
    "filter.cancelled_for_other_command": {
        "he": "ביטלתי את עריכת הסינון — שלח/י שוב את הפקודה כדי להמשיך 👍",
        "en": "I cancelled filter editing — send the command again to continue 👍",
        "ru": "Я отменил редактирование фильтра — отправьте команду ещё раз, чтобы продолжить 👍",
        "fr": "J'ai annulé la modification du filtre — renvoie la commande pour continuer 👍",
        "ar": "ألغيت تعديل التفضيلات — أرسل الأمر مرة أخرى للمتابعة 👍",
    },
    "filter.not_a_valid_value_escalated": {
        "he": "🙋 זה לא נראה כמו הערך שביקשתי, אז ליתר ביטחון העברתי את מה שכתבת לצוות — אם זו "
        "הייתה שאלה, תקבל/י מענה בהקדם.\n\n{retry_message}",
        "en": "🙋 That doesn't look like the value I asked for, so just in case I've passed what "
        "you wrote to the team — if it was a question, you'll hear back soon.\n\n{retry_message}",
        "ru": "🙋 Это не похоже на значение, которое я просил, поэтому на всякий случай я передал "
        "написанное вами команде — если это был вопрос, вам скоро ответят.\n\n{retry_message}",
        "fr": "🙋 Ça ne ressemble pas à la valeur que j'ai demandée, donc par précaution j'ai "
        "transmis ce que tu as écrit à l'équipe — si c'était une question, tu auras une réponse "
        "bientôt.\n\n{retry_message}",
        "ar": "🙋 هذا لا يبدو كالقيمة التي طلبتها، لذا احتياطاً أحلت ما كتبته إلى الفريق — إذا كان "
        "سؤالاً، ستصلك إجابة قريباً.\n\n{retry_message}",
    },
    "filter.city_not_found": {
        "he": "לא נמצאה עיר תואמת, נסה/י שוב:", "en": "No matching city found, try again:",
        "ru": "Подходящий город не найден, попробуйте ещё раз:",
        "fr": "Aucune ville correspondante trouvée, réessaie :",
        "ar": "لم يتم العثور على مدينة مطابقة، حاول مرة أخرى:",
    },
    "filter.pick_city": {
        "he": "בחר/י את העיר המבוקשת:", "en": "Choose the city you meant:",
        "ru": "Выберите нужный город:", "fr": "Choisis la ville que tu voulais dire :",
        "ar": "اختر المدينة المقصودة:",
    },
    "filter.number_parse_failed": {
        "he": "לא הצלחתי לפרש מספר, נסה/י שוב (או '-'):",
        "en": "I couldn't parse a number, try again (or '-'):",
        "ru": "Не удалось распознать число, попробуйте ещё раз (или «-»):",
        "fr": "Je n'ai pas réussi à interpréter un nombre, réessaie (ou « - ») :",
        "ar": "لم أتمكن من فهم رقم، حاول مرة أخرى (أو '-'):",
    },
    "filter.date_parse_failed": {
        "he": "פורמט תאריך לא תקין, נסה/י YYYY-MM-DD (או '-'):",
        "en": "Invalid date format, try YYYY-MM-DD (or '-'):",
        "ru": "Неверный формат даты, попробуйте ГГГГ-ММ-ДД (или «-»):",
        "fr": "Format de date invalide, essaie AAAA-MM-JJ (ou « - ») :",
        "ar": "تنسيق تاريخ غير صالح، جرّب YYYY-MM-DD (أو '-'):",
    },
    "filter.menu_help_escalated": {
        "he": "🙋 קיבלתי, העברתי את הפנייה שלך לצוות ותקבל/י מענה בהקדם.\n\nכדי להמשיך לערוך את "
        "הסינון, יש להשתמש בכפתורים שלמעלה 👆",
        "en": "🙋 Got it, I've passed your message to the team and you'll hear back soon.\n\nTo "
        "keep editing your filter, please use the buttons above 👆",
        "ru": "🙋 Понял, передал ваше сообщение команде, скоро с вами свяжутся.\n\nЧтобы "
        "продолжить редактировать фильтр, используйте кнопки выше 👆",
        "fr": "🙋 Compris, j'ai transmis ton message à l'équipe, tu auras une réponse bientôt.\n\n"
        "Pour continuer à modifier ton filtre, utilise les boutons ci-dessus 👆",
        "ar": "🙋 فهمت، أحلت رسالتك إلى الفريق وستصلك إجابة قريباً.\n\nلمتابعة تعديل تفضيلاتك، "
        "يرجى استخدام الأزرار أعلاه 👆",
    },
    # 2026-10-13: text typed while the /filter menu is open (bot/handlers/filter_conversation.py menu_text_fallback).
    "filter.typed_applied": {
        "he": "עדכנתי בחיפוש: {summary} ✍️\nכדי לשמור, לחצו על \"💾 שמור וחפש\" למטה 👇",
        "en": "Updated your search: {summary} ✍️\nTo keep it, tap \"💾 Save and search\" below 👇",
        "ru": "Обновил поиск: {summary} ✍️\nЧтобы сохранить, нажмите «💾 Сохранить и искать» ниже 👇",
        "fr": "Recherche mise à jour : {summary} ✍️\nPour la garder, appuie sur « 💾 Enregistrer et rechercher » ci-dessous 👇",
        "ar": "حدّثت بحثك: {summary} ✍️\nللحفظ اضغط «💾 حفظ وبحث» في الأسفل 👇",
    },
    "filter.use_buttons_below": {
        "he": "לעריכת החיפוש אפשר לכתוב למשל \"שכירות בחיפה עד 5000\", או להשתמש בכפתורים 👇",
        "en": "To edit your search, write e.g. \"rent in Haifa up to 5000\", or use the buttons 👇",
        "ru": "Чтобы изменить поиск, напишите например «аренда в Хайфе до 5000» или используйте кнопки 👇",
        "fr": "Pour modifier ta recherche, écris par ex. « location à Haïfa jusqu'à 5000 », ou utilise les boutons 👇",
        "ar": "لتعديل البحث اكتب مثلاً «إيجار في حيفا حتى 5000» أو استخدم الأزرار 👇",
    },
    "filter.use_buttons_hint": {
        "he": "יש להשתמש בכפתורים שלמעלה כדי לערוך את הסינון 👆",
        "en": "Please use the buttons above to edit your filter 👆",
        "ru": "Используйте кнопки выше, чтобы редактировать фильтр 👆",
        "fr": "Utilise les boutons ci-dessus pour modifier ton filtre 👆",
        "ar": "يرجى استخدام الأزرار أعلاه لتعديل تفضيلاتك 👆",
    },
    "filter.not_awaiting_anything": {
        "he": "שלח/י /filter כדי להתחיל לערוך את הסינון.",
        "en": "Send /filter to start editing your filter.",
        "ru": "Отправьте /filter, чтобы начать редактировать фильтр.",
        "fr": "Envoie /filter pour commencer à modifier ton filtre.",
        "ar": "أرسل /filter لبدء تعديل تفضيلاتك.",
    },
    "filter.help_request_continue": {
        "he": "אפשר להמשיך מאיפה שהפסקנו — שלח/י את הערך שהתבקשת להקליד.",
        "en": "We can continue where we left off — send the value you were asked to type.",
        "ru": "Можем продолжить с того места, где остановились — отправьте значение, которое "
        "нужно было ввести.",
        "fr": "On peut reprendre là où on s'est arrêtés — envoie la valeur qu'on t'a demandé de "
        "taper.",
        "ar": "يمكننا المتابعة من حيث توقفنا — أرسل القيمة التي طُلب منك كتابتها.",
    },
    "filter.help_request_continue_escalated": {
        "he": "🙋 קיבלתי, העברתי את הפנייה שלך לצוות ותקבל/י מענה בהקדם.\n\n{continue_msg}",
        "en": "🙋 Got it, I've passed your message to the team and you'll hear back soon.\n\n"
        "{continue_msg}",
        "ru": "🙋 Понял, передал ваше сообщение команде, скоро с вами свяжутся.\n\n{continue_msg}",
        "fr": "🙋 Compris, j'ai transmis ton message à l'équipe, tu auras une réponse bientôt.\n\n"
        "{continue_msg}",
        "ar": "🙋 فهمت، أحلت رسالتك إلى الفريق وستصلك إجابة قريباً.\n\n{continue_msg}",
    },
    "profile.not_registered": {
        "he": "שלח/י /start כדי להתחיל.", "en": "Send /start to get started.",
        "ru": "Отправьте /start, чтобы начать.", "fr": "Envoie /start pour commencer.",
        "ar": "أرسل /start للبدء.",
    },
    # --- bot/keyboards.py — CATEGORY_TITLES + every inline-keyboard button/summary label the
    # /filter menu renders. 2026-09-26 follow-up to the "FULL coverage" note above: the menu
    # screens themselves (not just filter_conversation.py's own prompts/errors) were still
    # Hebrew-only until this pass.
    "kb.title.root": {
        "he": "🔧 <b>הסינון שלך</b>", "en": "🔧 <b>Your filter</b>",
        "ru": "🔧 <b>Ваш фильтр</b>", "fr": "🔧 <b>Ton filtre</b>", "ar": "🔧 <b>تفضيلاتك</b>",
    },
    "kb.title.dt": {
        "he": "🏷️ סוג עסקה", "en": "🏷️ Deal type", "ru": "🏷️ Тип сделки",
        "fr": "🏷️ Type de transaction", "ar": "🏷️ نوع الصفقة",
    },
    "kb.title.pt": {
        "he": "🏠 סוג נכס", "en": "🏠 Property type", "ru": "🏠 Тип недвижимости",
        "fr": "🏠 Type de bien", "ar": "🏠 نوع العقار",
    },
    "kb.title.loc": {
        "he": "📍 מיקום", "en": "📍 Location", "ru": "📍 Местоположение",
        "fr": "📍 Emplacement", "ar": "📍 الموقع",
    },
    "kb.title.locpick": {
        "he": "📍 בחר/י ערים מהרשימה", "en": "📍 Choose cities from the list",
        "ru": "📍 Выберите города из списка", "fr": "📍 Choisis des villes dans la liste",
        "ar": "📍 اختر مدنًا من القائمة",
    },
    "kb.title.price": {
        "he": "💰 מחיר", "en": "💰 Price", "ru": "💰 Цена", "fr": "💰 Prix", "ar": "💰 السعر",
    },
    "kb.title.rooms": {
        "he": "🛏️ חדרים", "en": "🛏️ Rooms", "ru": "🛏️ Комнаты", "fr": "🛏️ Pièces",
        "ar": "🛏️ الغرف",
    },
    "kb.title.floor": {
        "he": "🏢 קומה", "en": "🏢 Floor", "ru": "🏢 Этаж", "fr": "🏢 Étage", "ar": "🏢 الطابق",
    },
    "kb.title.req": {
        "he": "✅ דרישות", "en": "✅ Requirements", "ru": "✅ Требования",
        "fr": "✅ Exigences", "ar": "✅ المتطلبات",
    },
    "kb.title.safe": {
        "he": "🛡️ מיגון", "en": "🛡️ Safe room", "ru": "🛡️ Защищённая комната",
        "fr": "🛡️ Abri", "ar": "🛡️ الغرفة الآمنة",
    },
    "kb.title.furn": {
        "he": "🛋️ ריהוט", "en": "🛋️ Furniture", "ru": "🛋️ Мебель", "fr": "🛋️ Meublé",
        "ar": "🛋️ الأثاث",
    },
    "kb.title.area": {
        "he": "📏 שטח מינימלי", "en": "📏 Minimum area", "ru": "📏 Минимальная площадь",
        "fr": "📏 Surface minimale", "ar": "📏 المساحة الأدنى",
    },
    "kb.title.kw": {
        "he": "🔍 מילות מפתח", "en": "🔍 Keywords", "ru": "🔍 Ключевые слова",
        "fr": "🔍 Mots-clés", "ar": "🔍 الكلمات المفتاحية",
    },
    "kb.title.move": {
        "he": "📅 תאריך כניסה", "en": "📅 Move-in date", "ru": "📅 Дата въезда",
        "fr": "📅 Date d'entrée", "ar": "📅 تاريخ الانتقال",
    },
    "kb.title.adv": {
        "he": "⚙️ מתקדם", "en": "⚙️ Advanced", "ru": "⚙️ Дополнительно", "fr": "⚙️ Avancé",
        "ar": "⚙️ خيارات متقدمة",
    },
    "kb.deal_type.rent": {
        "he": "להשכרה", "en": "For rent", "ru": "Аренда", "fr": "À louer", "ar": "للإيجار",
    },
    "kb.deal_type.sale": {
        "he": "למכירה", "en": "For sale", "ru": "Продажа", "fr": "À vendre", "ar": "للبيع",
    },
    "kb.deal_type.sublet": {
        "he": "סאבלט", "en": "Sublet", "ru": "Субаренда", "fr": "Sous-location",
        "ar": "تأجير من مستأجر",
    },
    "kb.property_type.apartment": {
        "he": "דירה", "en": "Apartment", "ru": "Квартира", "fr": "Appartement", "ar": "شقة",
    },
    "kb.property_type.garden_apartment": {
        "he": "דירת גן", "en": "Garden apartment", "ru": "Квартира с садом",
        "fr": "Appartement avec jardin", "ar": "شقة أرضية بحديقة",
    },
    "kb.property_type.penthouse": {
        "he": "פנטהאוז/גג", "en": "Penthouse/rooftop", "ru": "Пентхаус/крыша",
        "fr": "Penthouse/toit", "ar": "بنتهاوس/سطح",
    },
    "kb.property_type.studio": {
        "he": "סטודיו", "en": "Studio", "ru": "Студия", "fr": "Studio", "ar": "استوديو",
    },
    "kb.property_type.housing_unit": {
        "he": "יחידת דיור", "en": "Housing unit", "ru": "Жилая единица",
        "fr": "Unité de logement", "ar": "وحدة سكنية",
    },
    "kb.property_type.private_house": {
        "he": "בית פרטי", "en": "Private house", "ru": "Частный дом", "fr": "Maison privée",
        "ar": "منزل خاص",
    },
    "kb.property_type.shared_room": {
        "he": "חדר בשותפים", "en": "Room in shared apartment",
        "ru": "Комната в квартире с соседями", "fr": "Chambre en colocation",
        "ar": "غرفة في شقة مشتركة",
    },
    "kb.safe_room.only": {
        "he": 'ממ"ד בלבד', "en": "Safe room only", "ru": "Только защищённая комната",
        "fr": "Abri uniquement", "ar": "غرفة آمنة فقط",
    },
    "kb.safe_room.or_shelter": {
        "he": 'ממ"ד/מקלט', "en": "Safe room/shelter", "ru": "Защищённая комната/укрытие",
        "fr": "Abri/refuge", "ar": "غرفة آمنة/ملجأ",
    },
    "kb.furniture.furnished": {
        "he": "מרוהטת", "en": "Furnished", "ru": "С мебелью", "fr": "Meublé", "ar": "مفروشة",
    },
    "kb.furniture.unfurnished": {
        "he": "לא מרוהטת", "en": "Unfurnished", "ru": "Без мебели", "fr": "Non meublé",
        "ar": "غير مفروشة",
    },
    "kb.requirement.parking": {
        "he": "🅿️ חניה", "en": "🅿️ Parking", "ru": "🅿️ Парковка", "fr": "🅿️ Parking",
        "ar": "🅿️ موقف سيارات",
    },
    "kb.requirement.elevator": {
        "he": "🛗 מעלית", "en": "🛗 Elevator", "ru": "🛗 Лифт", "fr": "🛗 Ascenseur",
        "ar": "🛗 مصعد",
    },
    "kb.requirement.balcony": {
        "he": "🌳 מרפסת", "en": "🌳 Balcony", "ru": "🌳 Балкон", "fr": "🌳 Balcon",
        "ar": "🌳 شرفة",
    },
    "kb.requirement.pets_allowed": {
        "he": "🐾 חיות מחמד", "en": "🐾 Pets allowed", "ru": "🐾 Домашние животные",
        "fr": "🐾 Animaux acceptés", "ar": "🐾 يسمح بالحيوانات",
    },
    "kb.requirement.renovated": {
        "he": "🔨 משופצת", "en": "🔨 Renovated", "ru": "🔨 Отремонтированная",
        "fr": "🔨 Rénové", "ar": "🔨 مجددة",
    },
    "kb.requirement.has_photos": {
        "he": "📷 עם תמונות", "en": "📷 With photos", "ru": "📷 С фотографиями",
        "fr": "📷 Avec photos", "ar": "📷 مع صور",
    },
    "kb.requirement.roommate_friendly": {
        "he": "🤝 לשותפים", "en": "🤝 Roommate-friendly",
        "ru": "🤝 Подходит для соседей по квартире", "fr": "🤝 Pour colocataires",
        "ar": "🤝 مناسب للشركاء بالسكن",
    },
    "kb.all": {
        "he": "הכל", "en": "All", "ru": "Все", "fr": "Tout", "ar": "الكل",
    },
    "kb.back": {
        "he": "⬅️ חזרה", "en": "⬅️ Back", "ru": "⬅️ Назад", "fr": "⬅️ Retour", "ar": "⬅️ رجوع",
    },
    "kb.save_and_search": {
        "he": "💾 שמור וחפש", "en": "💾 Save and search", "ru": "💾 Сохранить и искать",
        "fr": "💾 Enregistrer et rechercher", "ar": "💾 حفظ وبحث",
    },
    "kb.cancel_button": {
        "he": "❌ ביטול", "en": "❌ Cancel", "ru": "❌ Отмена", "fr": "❌ Annuler",
        "ar": "❌ إلغاء",
    },
    "kb.add_city_from_list": {
        "he": "📋 הוסף עיר מרשימה", "en": "📋 Add a city from the list",
        "ru": "📋 Добавить город из списка", "fr": "📋 Ajouter une ville depuis la liste",
        "ar": "📋 أضف مدينة من القائمة",
    },
    "kb.search_city_by_typing": {
        "he": "🔍 חיפוש עיר לפי הקלדה", "en": "🔍 Search for a city by typing",
        "ru": "🔍 Найти город по вводу", "fr": "🔍 Rechercher une ville en tapant",
        "ar": "🔍 البحث عن مدينة بالكتابة",
    },
    "kb.clear_all_cities": {
        "he": "🌍 נקה הכל — כל הערים, בלי הגבלה", "en": "🌍 Clear all — every city, no limit",
        "ru": "🌍 Очистить всё — все города, без ограничений",
        "fr": "🌍 Tout effacer — toutes les villes, sans limite",
        "ar": "🌍 مسح الكل — كل المدن، بلا حدود",
    },
    "kb.remove_city": {
        "he": "❌ הסר: {city}", "en": "❌ Remove: {city}", "ru": "❌ Убрать: {city}",
        "fr": "❌ Retirer : {city}", "ar": "❌ إزالة: {city}",
    },
    "filter.remove_city_hint": {
        "he": "\n\nהערים שבחרת מופיעות למטה. לחיצה על עיר מסירה אותה מהסינון.",
        "en": "\n\nYour cities are listed below. Tap a city to remove it from the filter.",
        "ru": "\n\nВыбранные города ниже. Нажмите на город, чтобы убрать его из фильтра.",
        "fr": "\n\nVos villes sont listées ci-dessous. Touchez une ville pour la retirer du filtre.",
        "ar": "\n\nالمدن التي اخترتها أدناه. اضغط على مدينة لإزالتها من الفلتر.",
    },
    "kb.search_by_typing": {
        "he": "🔍 חיפוש לפי הקלדה", "en": "🔍 Search by typing", "ru": "🔍 Поиск по вводу",
        "fr": "🔍 Rechercher en tapant", "ar": "🔍 البحث بالكتابة",
    },
    "kb.other_value": {
        "he": "✏️ ערך אחר...", "en": "✏️ Other value...", "ru": "✏️ Другое значение...",
        "fr": "✏️ Autre valeur...", "ar": "✏️ قيمة أخرى...",
    },
    "kb.clear_no_limit": {
        "he": "🗑️ נקה (ללא הגבלה)", "en": "🗑️ Clear (no limit)",
        "ru": "🗑️ Очистить (без ограничений)", "fr": "🗑️ Effacer (sans limite)",
        "ar": "🗑️ مسح (بلا حدود)",
    },
    "kb.minimum_value": {
        "he": "מינימום: {value}", "en": "Minimum: {value}", "ru": "Минимум: {value}",
        "fr": "Minimum : {value}", "ar": "الحد الأدنى: {value}",
    },
    "kb.maximum_value": {
        "he": "מקסימום: {value}", "en": "Maximum: {value}", "ru": "Максимум: {value}",
        "fr": "Maximum : {value}", "ar": "الحد الأقصى: {value}",
    },
    "kb.only_with_price": {
        "he": "רק דירות עם מחיר", "en": "Only listings with a price",
        "ru": "Только объявления с ценой", "fr": "Uniquement les annonces avec prix",
        "ar": "فقط الإعلانات التي تحتوي على سعر",
    },
    "kb.ground_floor_only_toggle": {
        "he": "קומת קרקע בלבד", "en": "Ground floor only", "ru": "Только первый этаж",
        "fr": "Rez-de-chaussée uniquement", "ar": "الطابق الأرضي فقط",
    },
    "kb.min_area_value": {
        "he": "שטח מינימלי: {value} מ\"ר", "en": "Minimum area: {value} sqm",
        "ru": "Минимальная площадь: {value} м²", "fr": "Surface minimale : {value} m²",
        "ar": "المساحة الأدنى: {value} م²",
    },
    "kb.edit_keywords": {
        "he": "✏️ ערוך מילות מפתח", "en": "✏️ Edit keywords",
        "ru": "✏️ Изменить ключевые слова", "fr": "✏️ Modifier les mots-clés",
        "ar": "✏️ تعديل الكلمات المفتاحية",
    },
    "kb.clear_button": {
        "he": "🗑️ נקה", "en": "🗑️ Clear", "ru": "🗑️ Очистить", "fr": "🗑️ Effacer",
        "ar": "🗑️ مسح",
    },
    "kb.earliest_value": {
        "he": "מוקדם ביותר: {value}", "en": "Earliest: {value}", "ru": "Не ранее: {value}",
        "fr": "Au plus tôt : {value}", "ar": "الأقرب: {value}",
    },
    "kb.latest_value": {
        "he": "מאוחר ביותר: {value}", "en": "Latest: {value}", "ru": "Не позднее: {value}",
        "fr": "Au plus tard : {value}", "ar": "الأبعد: {value}",
    },
    "kb.no_brokers_toggle": {
        "he": "ללא תיווך", "en": "No brokers", "ru": "Без посредников", "fr": "Sans agences",
        "ar": "بدون وسطاء",
    },
    "kb.flexible_match_toggle": {
        "he": "סינון גמיש (מותר לפספס דרישה אחת)",
        "en": "Flexible match (may miss one requirement)",
        "ru": "Гибкий подбор (может не соответствовать одному требованию)",
        "fr": "Correspondance flexible (peut manquer une exigence)",
        "ar": "مطابقة مرنة (يمكن تفويت متطلب واحد)",
    },
    "kb.label.deal_type": {
        "he": "סוג עסקה", "en": "Deal type", "ru": "Тип сделки",
        "fr": "Type de transaction", "ar": "نوع الصفقة",
    },
    "kb.label.property_type": {
        "he": "סוג נכס", "en": "Property type", "ru": "Тип недвижимости",
        "fr": "Type de bien", "ar": "نوع العقار",
    },
    "kb.label.cities": {
        "he": "ערים", "en": "Cities", "ru": "Города", "fr": "Villes", "ar": "المدن",
    },
    "kb.label.price": {
        "he": "מחיר", "en": "Price", "ru": "Цена", "fr": "Prix", "ar": "السعر",
    },
    "kb.label.rooms": {
        "he": "חדרים", "en": "Rooms", "ru": "Комнаты", "fr": "Pièces", "ar": "الغرف",
    },
    "kb.label.floor": {
        "he": "קומה", "en": "Floor", "ru": "Этаж", "fr": "Étage", "ar": "الطابق",
    },
    "kb.label.requirements": {
        "he": "דרישות", "en": "Requirements", "ru": "Требования", "fr": "Exigences",
        "ar": "المتطلبات",
    },
    "kb.label.safe_room": {
        "he": "מיגון", "en": "Safe room", "ru": "Защищённая комната", "fr": "Abri",
        "ar": "الغرفة الآمنة",
    },
    "kb.label.furniture": {
        "he": "ריהוט", "en": "Furniture", "ru": "Мебель", "fr": "Meublé", "ar": "الأثاث",
    },
    "kb.label.min_area": {
        "he": "שטח מינימלי", "en": "Minimum area", "ru": "Минимальная площадь",
        "fr": "Surface minimale", "ar": "المساحة الأدنى",
    },
    "kb.label.keywords": {
        "he": "מילות מפתח", "en": "Keywords", "ru": "Ключевые слова", "fr": "Mots-clés",
        "ar": "الكلمات المفتاحية",
    },
    "kb.label.move_in": {
        "he": "כניסה", "en": "Move-in", "ru": "Въезд", "fr": "Entrée", "ar": "الانتقال",
    },
    "kb.label.no_brokers": {
        "he": "ללא תיווך", "en": "No brokers", "ru": "Без посредников", "fr": "Sans agences",
        "ar": "بدون وسطاء",
    },
    "kb.label.flexible_match": {
        "he": "סינון גמיש", "en": "Flexible match", "ru": "Гибкий подбор",
        "fr": "Correspondance flexible", "ar": "مطابقة مرنة",
    },
    "kb.ground_floor_only_label": {
        "he": "קרקע בלבד", "en": "Ground floor only", "ru": "Только первый этаж",
        "fr": "Rez-de-chaussée uniquement", "ar": "الطابق الأرضي فقط",
    },
    "kb.no_limit": {
        "he": "ללא הגבלה", "en": "No limit", "ru": "Без ограничений", "fr": "Sans limite",
        "ar": "بلا حدود",
    },
    "kb.range_from": {
        "he": "מ-{lo}{unit}", "en": "From {lo}{unit}", "ru": "От {lo}{unit}",
        "fr": "À partir de {lo}{unit}", "ar": "من {lo}{unit}",
    },
    "kb.range_until": {
        "he": "עד {hi}{unit}", "en": "Up to {hi}{unit}", "ru": "До {hi}{unit}",
        "fr": "Jusqu'à {hi}{unit}", "ar": "حتى {hi}{unit}",
    },
    "kb.sqm_value": {
        "he": "{value} מ\"ר", "en": "{value} sqm", "ru": "{value} м²", "fr": "{value} m²",
        "ar": "{value} م²",
    },
    "filter.numeric_picker_price_min": {
        "he": "מחיר מינימלי", "en": "Minimum price", "ru": "Минимальная цена",
        "fr": "Prix minimum", "ar": "الحد الأدنى للسعر",
    },
    "filter.numeric_picker_price_max": {
        "he": "מחיר מקסימלי", "en": "Maximum price", "ru": "Максимальная цена",
        "fr": "Prix maximum", "ar": "الحد الأقصى للسعر",
    },
    "filter.numeric_picker_rooms_min": {
        "he": "חדרים מינימלי", "en": "Minimum rooms", "ru": "Минимум комнат",
        "fr": "Pièces minimum", "ar": "الحد الأدنى للغرف",
    },
    "filter.numeric_picker_rooms_max": {
        "he": "חדרים מקסימלי", "en": "Maximum rooms", "ru": "Максимум комнат",
        "fr": "Pièces maximum", "ar": "الحد الأقصى للغرف",
    },
    "filter.numeric_picker_floor_min": {
        "he": "קומה מינימלית", "en": "Minimum floor", "ru": "Минимальный этаж",
        "fr": "Étage minimum", "ar": "الحد الأدنى للطابق",
    },
    "filter.numeric_picker_floor_max": {
        "he": "קומה מקסימלית", "en": "Maximum floor", "ru": "Максимальный этаж",
        "fr": "Étage maximum", "ar": "الحد الأقصى للطابق",
    },
    # --- todira_common/cards.py — the listing-card caption itself (scraper/notifier.py's push,
    # bot/handlers/liked.py's on-demand cards). Field labels/features/buttons only; every caption
    # is plain text (no bidi marks) regardless of language — see cards.py's own module comment.
    "card.broker": {
        "he": "תיווך", "en": "Broker", "ru": "Агент", "fr": "Agence", "ar": "وسيط",
    },
    "card.sublet": {
        "he": "סאבלט", "en": "Sublet", "ru": "Субаренда", "fr": "Sous-location",
        "ar": "تأجير من مستأجر",
    },
    "card.price_label": {
        "he": "מחיר:", "en": "Price:", "ru": "Цена:", "fr": "Prix :", "ar": "السعر:",
    },
    "card.rooms_label": {
        "he": "חדרים:", "en": "Rooms:", "ru": "Комнаты:", "fr": "Pièces :", "ar": "الغرف:",
    },
    "card.area_label": {
        "he": "שטח:", "en": "Area:", "ru": "Площадь:", "fr": "Surface :", "ar": "المساحة:",
    },
    "card.floor_label": {
        "he": "קומה:", "en": "Floor:", "ru": "Этаж:", "fr": "Étage :", "ar": "الطابق:",
    },
    "card.floor_of": {
        "he": "מתוך", "en": "of", "ru": "из", "fr": "sur", "ar": "من",
    },
    "card.move_in_label": {
        "he": "כניסה:", "en": "Move-in:", "ru": "Въезд:", "fr": "Entrée :", "ar": "الانتقال:",
    },
    "card.move_in_immediate": {
        "he": "מיידית", "en": "Immediate", "ru": "Сразу", "fr": "Immédiate", "ar": "فوري",
    },
    "card.move_in_flexible": {
        "he": "גמיש", "en": "Flexible", "ru": "Гибко", "fr": "Flexible", "ar": "مرن",
    },
    "card.features_label": {
        "he": "פיצ'רים:", "en": "Features:", "ru": "Особенности:",
        "fr": "Caractéristiques :", "ar": "المميزات:",
    },
    # 2026-10-09: the property type line (shown for anything that is not a plain apartment), read from the source or from the ad text.
    "card.type_label": {
        "he": "סוג:", "en": "Type:", "ru": "Тип:", "fr": "Type :", "ar": "النوع:",
    },
    "card.type_garden_apartment": {
        "he": "דירת גן", "en": "Garden apartment", "ru": "Квартира с садом", "fr": "Appartement avec jardin", "ar": "شقة حديقة",
    },
    "card.type_penthouse": {
        "he": "פנטהאוז / דירת גג", "en": "Penthouse", "ru": "Пентхаус", "fr": "Penthouse", "ar": "بنتهاوس",
    },
    "card.type_private_house": {
        "he": "בית פרטי", "en": "Private house", "ru": "Частный дом", "fr": "Maison individuelle", "ar": "بيت خاص",
    },
    "card.type_studio": {
        "he": "סטודיו", "en": "Studio", "ru": "Студия", "fr": "Studio", "ar": "ستوديو",
    },
    "card.type_housing_unit": {
        "he": "יחידת דיור", "en": "Housing unit", "ru": "Жилая единица", "fr": "Unité de logement", "ar": "وحدة سكنية",
    },
    "card.type_shared_room": {
        "he": "חדר בדירת שותפים", "en": "Room in a shared flat", "ru": "Комната в общей квартире",
        "fr": "Chambre en colocation", "ar": "غرفة في شقة مشتركة",
    },
    "card.price_dropped": {
        "he": "ירידת מחיר!", "en": "Price drop!", "ru": "Снижение цены!",
        "fr": "Baisse de prix !", "ar": "انخفاض السعر!",
    },
    "card.price_increased": {
        "he": "עליית מחיר!", "en": "Price increase!", "ru": "Повышение цены!",
        "fr": "Augmentation de prix !", "ar": "ارتفاع السعر!",
    },
    "card.was_price": {
        "he": "(היה {price}₪)", "en": "(was {price}₪)", "ru": "(было {price}₪)",
        "fr": "(était {price}₪)", "ar": "(كان {price}₪)",
    },
    "card.full_details_link_html": {
        "he": "לפרטי הדירה המלאים &gt;&gt;", "en": "Full listing details &gt;&gt;",
        "ru": "Полная информация о квартире &gt;&gt;",
        "fr": "Détails complets de l'annonce &gt;&gt;",
        "ar": "التفاصيل الكاملة للشقة &gt;&gt;",
    },
    "card.upgrade_to_see_link": {
        "he": "לקישור למודעה המקורית — שדרג/י את המנוי",
        "en": "To see the original listing link — upgrade your subscription",
        "ru": "Чтобы увидеть ссылку на оригинальное объявление — обновите подписку",
        "fr": "Pour voir le lien de l'annonce originale — passe à l'abonnement premium",
        "ar": "لرؤية رابط الإعلان الأصلي — قم بترقية اشتراكك",
    },
    "card.upgrade_required_plain": {
        "he": "לקישור למודעה המקורית יש לשדרג את המנוי",
        "en": "Upgrade your subscription to see the original listing link",
        "ru": "Обновите подписку, чтобы увидеть ссылку на оригинальное объявление",
        "fr": "Passe à l'abonnement premium pour voir le lien de l'annonce originale",
        "ar": "قم بترقية اشتراكك لرؤية رابط الإعلان الأصلي",
    },
    # 2026-10-09: what a card says instead of the generic lock line to a user whose access has ended, so the person knows
    # WHY the original-listing link is missing. Two situations, two texts (owner request): the free trial ran out vs. a
    # paid subscription/pass that ended. `_link` goes inside the upgrade hyperlink, `_plain` is used when there is no URL.
    # 2026-10-19 (owner, matching the competitor's card): the notice on its own line, then the link on the next.
    "card.trial_ended_notice": {
        "he": "✨ תקופת הניסיון הסתיימה! לצפייה במודעה המלאה ובמקור, עם גישה מלאה לשירות, אפשר לשדרג בקישור למטה 👇",
        "en": "✨ Your free trial has ended! To see the full listing and its source, with full access, upgrade via the link below 👇",
        "ru": "✨ Пробный период закончился! Чтобы видеть объявление полностью и его источник, оформите доступ по ссылке ниже 👇",
        "fr": "✨ Ta période d'essai est terminée ! Pour voir l'annonce complète et sa source, passe à l'accès complet via le lien ci-dessous 👇",
        "ar": "✨ انتهت الفترة التجريبية! لرؤية الإعلان كاملاً ومصدره، مع وصول كامل للخدمة، يمكنك الترقية عبر الرابط أدناه 👇",
    },
    "card.trial_ended_link": {
        "he": "לשדרוג וצפייה במודעה המלאה >>", "en": "Upgrade and see the full listing >>",
        "ru": "Оформить доступ и открыть объявление >>", "fr": "Passer à l'accès complet >>",
        "ar": "الترقية ورؤية الإعلان كاملاً >>",
    },
    "card.subscription_expired_notice": {
        "he": "✨ תקופת המנוי הסתיימה! על מנת לצפות שוב במודעות עם גישה מלאה לשירות, אפשר לחדש מנוי בקישור למטה 👇",
        "en": "✨ Your subscription has ended! To see listings again with full access, renew via the link below 👇",
        "ru": "✨ Срок подписки закончился! Чтобы снова видеть объявления с полным доступом, продлите её по ссылке ниже 👇",
        "fr": "✨ Ton abonnement est terminé ! Pour revoir les annonces avec un accès complet, renouvelle-le via le lien ci-dessous 👇",
        "ar": "✨ انتهى اشتراكك! لرؤية الإعلانات مجدداً مع وصول كامل للخدمة، يمكنك التجديد عبر الرابط أدناه 👇",
    },
    "card.subscription_expired_link": {
        "he": "לחידוש המנוי >>", "en": "Renew my access >>", "ru": "Продлить доступ >>",
        "fr": "Renouveler mon accès >>", "ar": "تجديد الاشتراك >>",
    },
    "card.room_in_shared": {
        "he": "חדר בדירת שותפים", "en": "a room in a shared flat", "ru": "комната в квартире с соседями",
        "fr": "chambre en colocation", "ar": "غرفة في شقة مشتركة",
    },
    "card.price_unknown": {
        "he": "לא צוין", "en": "not listed", "ru": "не указана", "fr": "non indiqué", "ar": "غير محدد",
    },
    "card.no_photos_banner": {
        "he": "🕵️ <b>דירה זו עלתה ללא תמונות, אך שווה לפנות למפרסם ולבקש כמה!</b>\n\n",
        "en": "🕵️ <b>This listing has no photos, but it may still be worth asking the poster for "
        "some!</b>\n\n",
        "ru": "🕵️ <b>В этом объявлении нет фотографий, но стоит попросить их у "
        "автора!</b>\n\n",
        "fr": "🕵️ <b>Cette annonce n'a pas de photos, mais ça vaut peut-être le coup d'en "
        "demander à l'annonceur !</b>\n\n",
        "ar": "🕵️ <b>لا تحتوي هذه الشقة على صور، لكن يستحق التواصل مع المعلن وطلب بعضها!</b>\n\n",
    },
    "card.feature_parking": {
        "he": "חניה", "en": "Parking", "ru": "Парковка", "fr": "Parking", "ar": "موقف سيارات",
    },
    "card.feature_elevator": {
        "he": "מעלית", "en": "Elevator", "ru": "Лифт", "fr": "Ascenseur", "ar": "مصعد",
    },
    "card.feature_balcony": {
        "he": "מרפסת", "en": "Balcony", "ru": "Балкон", "fr": "Balcon", "ar": "شرفة",
    },
    "card.feature_pets_allowed": {
        "he": "חיות מחמד", "en": "Pets allowed", "ru": "Домашние животные",
        "fr": "Animaux acceptés", "ar": "يسمح بالحيوانات",
    },
    "card.feature_renovated": {
        "he": "משופצת", "en": "Renovated", "ru": "Отремонтированная", "fr": "Rénové",
        "ar": "مجددة",
    },
    "card.feature_roommate_friendly": {
        "he": "מתאימה לשותפים", "en": "Roommate-friendly",
        "ru": "Подходит для соседей по квартире", "fr": "Convient aux colocataires",
        "ar": "مناسبة للشركاء بالسكن",
    },
    "card.feature_safe_room": {
        "he": 'ממ"ד', "en": "Safe room", "ru": "Защищённая комната", "fr": "Abri",
        "ar": "غرفة آمنة",
    },
    "card.feature_furnished": {
        "he": "מרוהטת", "en": "Furnished", "ru": "С мебелью", "fr": "Meublé", "ar": "مفروشة",
    },
    "card.like_button": {
        "he": "❤️ שמור", "en": "❤️ Save", "ru": "❤️ Сохранить", "fr": "❤️ Enregistrer",
        "ar": "❤️ حفظ",
    },
    "card.hide_button": {
        "he": "🙈 הסתר", "en": "🙈 Hide", "ru": "🙈 Скрыть", "fr": "🙈 Masquer",
        "ar": "🙈 إخفاء",
    },
    # 2026-10-22 (owner approved): "did you find a flat?" - asked on pause and after a pass/trial ends
    # (todira_common/testimonials.py), and the testimonial request after a "yes".
    "found_ask.question": {
        "he": "היי, רק שאלה קטנה: מצאתם דירה?",
        "en": "Hi, just a quick question: did you find a flat?",
        "ru": "Привет, небольшой вопрос: вы нашли квартиру?",
        "fr": "Salut, petite question : vous avez trouvé un appartement ?",
        "ar": "مرحبًا، سؤال صغير: هل وجدتم شقة؟",
    },
    "found_ask.yes_btn": {"he": "כן! 🎉", "en": "Yes! 🎉", "ru": "Да! 🎉", "fr": "Oui ! 🎉", "ar": "نعم! 🎉"},
    "found_ask.no_btn": {"he": "עדיין מחפש", "en": "Still looking", "ru": "Ещё ищу", "fr": "Je cherche encore",
                         "ar": "ما زلت أبحث"},
    "found_ask.yes_reply": {
        "he": "איזה כיף! תכתבו לנו משפט אחד על איך היה, ואם מותר לנו להציג אותו באתר עם השם הפרטי שלכם.",
        "en": "That's great! Write us one sentence about how it went, and whether we may show it on the site with your first name.",
        "ru": "Как здорово! Напишите нам одно предложение о том, как всё прошло, и можно ли показать его на сайте с вашим именем.",
        "fr": "Super ! Écrivez-nous une phrase sur votre expérience, et dites-nous si on peut l'afficher sur le site avec votre prénom.",
        "ar": "رائع! اكتبوا لنا جملة واحدة عن تجربتكم، وهل يمكننا عرضها في الموقع مع اسمكم الأول.",
    },
    "found_ask.no_reply": {
        "he": "בהצלחה בחיפוש! 🍀", "en": "Good luck with the search! 🍀", "ru": "Удачи в поисках! 🍀",
        "fr": "Bonne chance pour la recherche ! 🍀", "ar": "بالتوفيق في البحث! 🍀",
    },
    "found_ask.thanks": {"he": "תודה רבה! 🙏", "en": "Thank you so much! 🙏", "ru": "Большое спасибо! 🙏",
                         "fr": "Merci beaucoup ! 🙏", "ar": "شكرًا جزيلًا! 🙏"},
    # 2026-10-22: the card's share button (off until the owner approves - cards.py's _bot_share_enabled).
    "card.share_button": {
        "he": "📤 שיתוף הדירה", "en": "📤 Share this flat", "ru": "📤 Поделиться", "fr": "📤 Partager",
        "ar": "📤 مشاركة الشقة",
    },
    "card.share_text": {
        "he": "מצאתי דירה בטודירה ששווה לראות",
        "en": "Found a flat on Todira worth a look",
        "ru": "Нашёл квартиру в Todira, стоит посмотреть",
        "fr": "J'ai trouvé un appartement sur Todira qui vaut le coup d'œil",
        "ar": "وجدت شقة في توديرا تستحق النظر",
    },
    "card.found_button": {
        "he": "🎉 מצאתי דירה!", "en": "🎉 Found an apartment!", "ru": "🎉 Нашёл квартиру!",
        "fr": "🎉 J'ai trouvé un appartement !", "ar": "🎉 وجدت شقة!",
    },
}


def bot_text(key: str, lang: str | None, **kwargs) -> str:
    entry = BOT_STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    return text.format(**kwargs) if kwargs else text
