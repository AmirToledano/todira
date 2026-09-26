"""Translated strings for the bots' core conversational flows (Telegram: bot/handlers/start.py,
onboarding.py, contact_fallback.py; WhatsApp: website/whatsapp_webhook.py) — 2026-09-26 real owner
request, see todira_common/language.py's own docstring for the full reasoning.

Scope, deliberately bounded: this covers first contact (/start's welcome, reactivation, renewal
nudge), free-text onboarding, and the "already onboarded, chatting" fallback on both channels —
the exact flows Gemini's own generated replies (todira_common/gemini_client.py) now also speak in
the visitor's language. It does NOT cover bot/handlers/filter_conversation.py's much larger
menu-driven /filter conversation, apartments.py, liked.py, profile.py, or support.py — those stay
Hebrew-only for now, a separate, larger follow-up.

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
}


def bot_text(key: str, lang: str | None, **kwargs) -> str:
    entry = BOT_STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    return text.format(**kwargs) if kwargs else text
