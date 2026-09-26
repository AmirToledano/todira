"""Translated strings for the bots' conversational flows (Telegram: bot/handlers/*.py; WhatsApp:
website/whatsapp_webhook.py) — 2026-09-26 real owner request, see todira_common/language.py's own
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
the "card.*" prefix). cards.py's RTL bidi embedding (_force_rtl/_force_rtl_block) is now
conditional on todira_common.language.RTL_LANGS (Hebrew/Arabic only) rather than applied
unconditionally — forcing an RTL override on already-correctly-LTR English/Russian/French text
would misalign it, not fix anything.

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
    "start.welcome": {
        "he": (
            "✨ 🏠 היי {name}! אני בוט חיפוש דירות אישי — סורק את שוק הדירות ומודיע לך כשמופיעה "
            "דירה שמתאימה לסינון שלך.\n\nפקודות:\n/filter — הגדרת/עדכון הסינון שלך\n/apartments — "
            "הדירות התואמות האחרונות\n/liked — הדירות ששמרת\n/profile — הפרופיל וההגדרות שלך\n\n"
            "רוצה גם להתחבר באתר (Google/ווטסאפ)? {account_url} 🔗"
        ),
        "en": (
            "✨ 🏠 Hi {name}! I'm a personal apartment-search bot — I scan the rental market and "
            "notify you when a listing matches your filter.\n\nCommands:\n/filter — set/update your "
            "filter\n/apartments — the latest matching listings\n/liked — listings you saved\n"
            "/profile — your profile and settings\n\nWant to also sign in on the website "
            "(Google/WhatsApp)? {account_url} 🔗"
        ),
        "ru": (
            "✨ 🏠 Привет, {name}! Я персональный бот для поиска квартир — слежу за рынком аренды и "
            "сообщаю, когда появляется объявление, подходящее под ваш фильтр.\n\nКоманды:\n/filter — "
            "настроить/изменить фильтр\n/apartments — последние подходящие объявления\n/liked — "
            "сохранённые объявления\n/profile — ваш профиль и настройки\n\nХотите также войти на "
            "сайте (Google/WhatsApp)? {account_url} 🔗"
        ),
        "fr": (
            "✨ 🏠 Salut {name} ! Je suis un bot personnel de recherche d'appartements — je scrute le "
            "marché locatif et te préviens dès qu'une annonce correspond à ton filtre.\n\n"
            "Commandes :\n/filter — définir/modifier ton filtre\n/apartments — les dernières "
            "annonces correspondantes\n/liked — les annonces enregistrées\n/profile — ton profil et "
            "tes réglages\n\nTu veux aussi te connecter sur le site (Google/WhatsApp) ? "
            "{account_url} 🔗"
        ),
        "ar": (
            "✨ 🏠 مرحباً {name}! أنا بوت شخصي للبحث عن شقق — أراقب سوق الإيجار وأخبرك عند ظهور إعلان "
            "يطابق تفضيلاتك.\n\nالأوامر:\n/filter — ضبط/تحديث تفضيلاتك\n/apartments — أحدث الإعلانات "
            "المطابقة\n/liked — الإعلانات المحفوظة\n/profile — ملفك الشخصي وإعداداتك\n\nهل تريد "
            "أيضاً تسجيل الدخول عبر الموقع (Google/WhatsApp)؟ {account_url} 🔗"
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
        "he": "ספר/י לי בכמה מילים מה את/ה מחפש/ת — למשל עיר, שכירות/מכירה/סבלט, תקציב, כמה חדרים, "
        "וכל דבר נוסף שחשוב לך. אפשר לכתוב חופשי, אני אבין 🙂\n"
        "(או שאפשר לדלג ולהגדיר הכל ידנית עם /filter בכל שלב)",
        "en": "Tell me in a few words what you're looking for — e.g. city, rent/sale/sublet, "
        "budget, how many rooms, and anything else that matters to you. Feel free to write "
        "naturally, I'll understand 🙂\n(or you can skip and set everything up manually with "
        "/filter at any point)",
        "ru": "Расскажите в нескольких словах, что вы ищете — например, город, аренда/покупка/"
        "субаренда, бюджет, сколько комнат, и что ещё для вас важно. Можно писать свободно, я "
        "пойму 🙂\n(или можно пропустить и настроить всё вручную через /filter в любой момент)",
        "fr": "Dis-moi en quelques mots ce que tu cherches — par exemple ville, location/vente/"
        "sous-location, budget, nombre de pièces, et tout ce qui compte pour toi. Écris librement, "
        "je comprendrai 🙂\n(ou tu peux passer et tout configurer manuellement avec /filter à tout "
        "moment)",
        "ar": "أخبرني ببضع كلمات عما تبحث عنه — مثل المدينة، إيجار/بيع/تأجير من الباطن، الميزانية، "
        "عدد الغرف، وأي شيء آخر يهمك. اكتب بحرية، سأفهم 🙂\n(أو يمكنك التخطي وضبط كل شيء يدوياً عبر "
        "/filter في أي وقت)",
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
    "onboarding.error": {
        "he": "מצטער, יש לי תקלה טכנית רגעית 😅 נסה/י לשלוח שוב בעוד רגע, או תמיד אפשר להגדיר ידנית "
        "עם /filter.",
        "en": "Sorry, I'm having a brief technical hiccup 😅 try sending it again in a moment, or "
        "you can always set things up manually with /filter.",
        "ru": "Извините, у меня небольшой технический сбой 😅 попробуйте отправить снова через "
        "минуту, либо всегда можно настроить всё вручную через /filter.",
        "fr": "Désolé, j'ai un petit souci technique 😅 réessaie d'envoyer dans un instant, ou tu "
        "peux toujours tout configurer manuellement avec /filter.",
        "ar": "آسف، لدي عطل تقني بسيط 😅 حاول الإرسال مرة أخرى بعد قليل، أو يمكنك دائماً الإعداد "
        "يدوياً عبر /filter.",
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
    "contact_fallback.error": {
        "he": "מצטער, יש לי תקלה טכנית רגעית 😅 נסה/י לשלוח שוב בעוד רגע.",
        "en": "Sorry, I'm having a brief technical hiccup 😅 try sending it again in a moment.",
        "ru": "Извините, у меня небольшой технический сбой 😅 попробуйте отправить снова через "
        "минуту.",
        "fr": "Désolé, j'ai un petit souci technique 😅 réessaie d'envoyer dans un instant.",
        "ar": "آسف، لدي عطل تقني بسيط 😅 حاول الإرسال مرة أخرى بعد قليل.",
    },
    "contact_fallback.default_ack": {
        "he": "בסדר! 🙂",
        "en": "Okay! 🙂",
        "ru": "Хорошо! 🙂",
        "fr": "D'accord ! 🙂",
        "ar": "حسناً! 🙂",
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
    "whatsapp.link_conflict": {
        "he": "למספר הווטסאפ הזה כבר יש חשבון נפרד אצלי, אז אי אפשר לחבר אותו לחשבון אחר. אם זו "
        "טעות, אפשר לפנות אלינו דרך האתר.",
        "en": "This WhatsApp number already has its own separate account with me, so it can't be "
        "linked to another one. If this is a mistake, you can reach us via the website.",
        "ru": "У этого номера WhatsApp уже есть отдельный аккаунт у меня, поэтому привязать его к "
        "другому нельзя. Если это ошибка, вы можете связаться с нами через сайт.",
        "fr": "Ce numéro WhatsApp a déjà son propre compte séparé chez moi, il ne peut donc pas "
        "être lié à un autre. Si c'est une erreur, tu peux nous contacter via le site.",
        "ar": "هذا الرقم على واتساب لديه بالفعل حساب منفصل عندي، لذا لا يمكن ربطه بحساب آخر. إذا "
        "كان هذا خطأ، يمكنك التواصل معنا عبر الموقع.",
    },
    "whatsapp.link_success": {
        "he": "🎉 חיברתי! אתה כבר רשום ומעודכן אצלי במערכת — מעכשיו תקבל עדכונים גם כאן.",
        "en": "🎉 Connected! You're already registered with me — from now on you'll get updates "
        "here too.",
        "ru": "🎉 Подключено! Вы уже зарегистрированы у меня — теперь вы будете получать "
        "обновления и здесь.",
        "fr": "🎉 Connecté ! Tu es déjà enregistré chez moi — tu recevras désormais aussi les mises "
        "à jour ici.",
        "ar": "🎉 تم الربط! أنت مسجل بالفعل لدي — من الآن ستصلك التحديثات هنا أيضاً.",
    },
    "whatsapp.error": {
        "he": "מצטער, יש לי תקלה טכנית רגעית 😅 נסה/י לשלוח שוב בעוד רגע.",
        "en": "Sorry, I'm having a brief technical hiccup 😅 try sending it again in a moment.",
        "ru": "Извините, у меня небольшой технический сбой 😅 попробуйте отправить снова через "
        "минуту.",
        "fr": "Désolé, j'ai un petit souci technique 😅 réessaie d'envoyer dans un instant.",
        "ar": "آسف، لدي عطل تقني بسيط 😅 حاول الإرسال مرة أخرى بعد قليل.",
    },
    "whatsapp.unsupported_message_type": {
        "he": "כרגע אני יודע לקרוא רק הודעות טקסט 🙂 אפשר לתאר במילים מה את/ה מחפש/ת?",
        "en": "Right now I can only read text messages 🙂 Can you describe in words what you're "
        "looking for?",
        "ru": "Пока я умею читать только текстовые сообщения 🙂 Можете описать словами, что вы "
        "ищете?",
        "fr": "Pour l'instant je ne sais lire que les messages texte 🙂 Peux-tu décrire avec des "
        "mots ce que tu cherches ?",
        "ar": "حالياً أستطيع قراءة الرسائل النصية فقط 🙂 هل يمكنك وصف ما تبحث عنه بالكلمات؟",
    },
    "whatsapp.onboarding_default_ack": {
        "he": "רשמתי, תודה!",
        "en": "Got it, thanks!",
        "ru": "Записал, спасибо!",
        "fr": "C'est noté, merci !",
        "ar": "تم التسجيل، شكراً!",
    },
    "whatsapp.chat_default_ack": {
        "he": "בסדר! 🙂",
        "en": "Okay! 🙂",
        "ru": "Хорошо! 🙂",
        "fr": "D'accord ! 🙂",
        "ar": "حسناً! 🙂",
    },
    "whatsapp.onboarding_complete": {
        "he": "מעולה, נרשמת! אני כבר עוקב אחרי דירות חדשות שמתאימות לך 🏠",
        "en": "Great, you're registered! I'm already tracking new apartments that match you 🏠",
        "ru": "Отлично, вы зарегистрированы! Я уже слежу за новыми квартирами, которые вам "
        "подходят 🏠",
        "fr": "Super, tu es inscrit ! Je surveille déjà les nouveaux appartements qui te "
        "correspondent 🏠",
        "ar": "رائع، تم تسجيلك! أنا بالفعل أتابع الشقق الجديدة التي تناسبك 🏠",
    },
    "whatsapp.filter_edit_button": {
        "he": "⚙️ עריכת הסינון", "en": "⚙️ Edit filter", "ru": "⚙️ Изменить фильтр",
        "fr": "⚙️ Modifier le filtre", "ar": "⚙️ تعديل التفضيلات",
    },
    "whatsapp.filter_edit_intro": {
        "he": "כדי לערוך את הסינון, הכי פשוט להיכנס ישירות לדף הסינון שלנו:",
        "en": "To edit your filter, the easiest way is to go straight to our filter page:",
        "ru": "Чтобы изменить фильтр, проще всего перейти прямо на страницу фильтра:",
        "fr": "Pour modifier ton filtre, le plus simple est d'aller directement sur notre page de "
        "filtre :",
        "ar": "لتعديل تفضيلاتك، أسهل طريقة هي الدخول مباشرة إلى صفحة التفضيلات لدينا:",
    },
    "whatsapp.filter_edit_followup1": {
        "he": "שם תוכל לשנות בקלות את המחיר, להוסיף או להסיר ערים ושכונות, ולבחור העדפות כמו "
        "חניה, מעלית, או ממ\"ד. ברגע שתשמור שם את השינויים, אני אעדכן את ההתראות שלך בהתאם! ✨🏠",
        "en": "There you can easily change the price, add or remove cities and neighborhoods, and "
        "pick preferences like parking, elevator, or a safe room. Once you save your changes there, "
        "I'll update your notifications accordingly! ✨🏠",
        "ru": "Там вы можете легко изменить цену, добавить или убрать города и районы, а также "
        "выбрать предпочтения — парковку, лифт или бомбоубежище. Как только сохраните изменения, я "
        "обновлю ваши уведомления! ✨🏠",
        "fr": "Là-bas tu peux facilement changer le prix, ajouter ou retirer des villes et "
        "quartiers, et choisir des préférences comme le parking, l'ascenseur, ou un abri. Dès que "
        "tu enregistres les changements, je mettrai à jour tes notifications en conséquence ! ✨🏠",
        "ar": "هناك يمكنك بسهولة تغيير السعر، إضافة أو إزالة مدن وأحياء، واختيار تفضيلات مثل "
        "موقف السيارات أو المصعد أو الغرفة الآمنة. بمجرد حفظ التغييرات هناك، سأحدّث إشعاراتك وفقاً "
        "لذلك! ✨🏠",
    },
    "whatsapp.filter_edit_followup2": {
        "he": "צריך עזרה עם משהו ספציפי בסינון? 😊",
        "en": "Need help with something specific in the filter? 😊",
        "ru": "Нужна помощь с чем-то конкретным в фильтре? 😊",
        "fr": "Besoin d'aide sur un point précis du filtre ? 😊",
        "ar": "هل تحتاج مساعدة في شيء محدد بخصوص التفضيلات؟ 😊",
    },
    "whatsapp.notifications_optin_body": {
        "he": "רוצה שאני אשלח לך הודעה כאן בווטסאפ (בנוסף לאתר) ברגע שעולה דירה חדשה שמתאימה "
        "לך? אפשר להפעיל את זה בעמוד החשבון שלך:",
        "en": "Want me to send you a message here on WhatsApp (in addition to the website) the "
        "moment a new matching apartment appears? You can turn this on in your account page:",
        "ru": "Хотите, чтобы я присылал сообщение сюда, в WhatsApp (в дополнение к сайту), как "
        "только появится подходящая новая квартира? Это можно включить на странице вашего "
        "аккаунта:",
        "fr": "Tu veux que je t'envoie un message ici sur WhatsApp (en plus du site) dès qu'un "
        "nouvel appartement correspondant apparaît ? Tu peux activer ça sur ta page de compte :",
        "ar": "هل تريد أن أرسل لك رسالة هنا على واتساب (بالإضافة إلى الموقع) بمجرد ظهور شقة "
        "جديدة تناسبك؟ يمكنك تفعيل ذلك في صفحة حسابك:",
    },
    "whatsapp.notifications_optin_button": {
        "he": "🔔 הפעלת התראות", "en": "🔔 Turn on notifications", "ru": "🔔 Включить уведомления",
        "fr": "🔔 Activer les notifications", "ar": "🔔 تفعيل الإشعارات",
    },
    "whatsapp.help_request_body": {
        "he": "תודה שכתבת! ההודעה שלך התקבלה ואנחנו נחזור אליך בהקדם 🙏\nאפשר גם לפנות ישירות דרך "
        "עמוד יצירת הקשר שלנו:",
        "en": "Thanks for writing! Your message was received and we'll get back to you soon 🙏\n"
        "You can also reach out directly through our contact page:",
        "ru": "Спасибо за сообщение! Мы его получили и скоро свяжемся с вами 🙏\nТакже можно "
        "обратиться напрямую через нашу страницу контактов:",
        "fr": "Merci pour ton message ! Il a bien été reçu, on te répond bientôt 🙏\nTu peux aussi "
        "nous contacter directement via notre page de contact :",
        "ar": "شكراً لكتابتك! تم استلام رسالتك وسنعاود التواصل معك قريباً 🙏\nيمكنك أيضاً "
        "التواصل مباشرة عبر صفحة الاتصال لدينا:",
    },
    "whatsapp.help_request_button": {
        "he": "✉️ יצירת קשר", "en": "✉️ Contact us", "ru": "✉️ Связаться с нами",
        "fr": "✉️ Nous contacter", "ar": "✉️ تواصل معنا",
    },
    "whatsapp.language_confirmed": {
        "he": "מעולה! מעכשיו אדבר איתך בעברית. ספר לי מה אתה מחפש 🏠",
        "en": "Great! I'll speak with you in English from now on. Tell me what you're looking "
        "for 🏠",
        "ru": "Отлично! Теперь я буду говорить с вами по-русски. Расскажите, что вы ищете 🏠",
        "fr": "Super ! Je vais te parler en français à partir de maintenant. Dis-moi ce que tu "
        "cherches 🏠",
        "ar": "رائع! سأتحدث معك بالعربية من الآن. أخبرني ماذا تبحث عنه 🏠",
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
    # bot/handlers/liked.py's on-demand cards). Field labels/features/buttons only; the RTL bidi
    # embedding in cards._force_rtl is now conditional on language.RTL_LANGS (Hebrew/Arabic only —
    # forcing RTL on English/Russian/French would misalign text that's already correctly LTR).
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
    "card.features_label": {
        "he": "פיצ'רים:", "en": "Features:", "ru": "Особенности:",
        "fr": "Caractéristiques :", "ar": "المميزات:",
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
    "card.full_details_link_plain": {
        "he": "לפרטי הדירה המלאים >>", "en": "Full listing details >>",
        "ru": "Полная информация о квартире >>", "fr": "Détails complets de l'annonce >>",
        "ar": "التفاصيل الكاملة للشقة >>",
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
