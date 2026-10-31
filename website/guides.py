"""Two help pages for renters (2026-10-31, owner approved the drafts): a moving checklist and what to check in a rental
contract. The contract page was recommended instead of a downloadable contract: a contract is a legal document, and a page
that says what to check, with a link to the official source, gives the same value without that risk.

Every legal number on the contract page was checked against Kol Zchut on 2026-10-31 (the pages linked under it); what
could not be checked (notice periods before a lease ends) is left out on purpose. Each text is in the site's five
languages; a missing one falls back to Hebrew.
"""
from __future__ import annotations

_KOLZCHUT_REPAIRS = (
    "https://www.kolzchut.org.il/he/%D7%AA%D7%99%D7%A7%D7%95%D7%9F_%D7%9C%D7%99%D7%A7%D7%95%D7%99%D7%99%D7%9D_"
    "%D7%91%D7%93%D7%99%D7%A8%D7%94_%D7%9E%D7%95%D7%A9%D7%9B%D7%A8%D7%AA"
)
_KOLZCHUT_GUARANTEE = (
    "https://www.kolzchut.org.il/he/%D7%94%D7%92%D7%91%D7%9C%D7%AA_%D7%A1%D7%9B%D7%95%D7%9D_%D7%94%D7%A2%D7%A8%D7%95"
    "%D7%91%D7%94_%D7%A9%D7%9E%D7%95%D7%AA%D7%A8_%D7%9C%D7%93%D7%A8%D7%95%D7%A9_%D7%9E%D7%A9%D7%95%D7%9B%D7%A8_"
    "%D7%93%D7%99%D7%A8%D7%94"
)


def _t(he, en, ru, fr, ar):
    return {"he": he, "en": en, "ru": ru, "fr": fr, "ar": ar}


GUIDES = {
    "moving": {
        "path": "/moving-checklist",
        "checklist": True,
        "title": _t("רשימה למעבר דירה", "Moving checklist", "Чек-лист переезда", "Check-list du déménagement",
                    "قائمة الانتقال إلى شقة جديدة"),
        "lead": _t(
            "מה לעשות לפני שחותמים, לפני המעבר וביום הכניסה. אפשר לסמן כל שורה, והסימון נשמר אצלכם בדפדפן.",
            "What to do before you sign, before you move and on moving day. Tick each line; your ticks stay in your browser.",
            "Что сделать до подписания, до переезда и в день въезда. Отмечайте пункты, отметки сохраняются в вашем браузере.",
            "Ce qu'il faut faire avant de signer, avant le déménagement et le jour J. Cochez chaque ligne ; vos coches restent "
            "dans votre navigateur.",
            "ما يجب فعله قبل التوقيع وقبل الانتقال ويوم الدخول. يمكنك تحديد كل سطر، ويبقى التحديد محفوظاً في متصفحك.",
        ),
        "sections": [
            {
                "title": _t("לפני שחותמים", "Before you sign", "До подписания договора", "Avant de signer",
                            "قبل التوقيع"),
                "items": [
                    _t("לראות את הדירה באור יום, ולפתוח כל ברז, מזגן ודוד.",
                       "See the flat in daylight, and turn on every tap, the air conditioner and the boiler.",
                       "Осмотреть квартиру при дневном свете и проверить каждый кран, кондиционер и бойлер.",
                       "Visiter l'appartement de jour, et ouvrir chaque robinet, la clim et le chauffe-eau.",
                       "معاينة الشقة في ضوء النهار، وتشغيل كل صنبور والمكيّف والسخّان."),
                    _t("לצלם כל פגם שכבר קיים, ולצרף את התמונות לחוזה.",
                       "Photograph every existing defect, and attach the photos to the contract.",
                       "Сфотографировать все существующие дефекты и приложить фото к договору.",
                       "Photographier chaque défaut existant et joindre les photos au contrat.",
                       "تصوير كل عيب موجود، وإرفاق الصور بالعقد."),
                    _t("לבדוק שמי שמשכיר הוא באמת בעל הדירה (נסח טאבו, או ייפוי כוח).",
                       "Check that the person renting it out really owns it (a land registry extract, or a power of attorney).",
                       "Убедиться, что сдающий действительно владелец (выписка из реестра или доверенность).",
                       "Vérifier que le bailleur est bien le propriétaire (extrait du cadastre ou procuration).",
                       "التأكد من أن المؤجّر هو مالك الشقة فعلاً (مستخرج الطابو أو وكالة)."),
                    _t("לשאול כמה עולים ועד בית וארנונה, ומי משלם על מה.",
                       "Ask what the building fee and the municipal tax come to, and who pays what.",
                       "Узнать, сколько стоят домовой сбор и арнона, и кто за что платит.",
                       "Demander le montant des charges d'immeuble et de la taxe municipale, et qui paie quoi.",
                       "السؤال عن رسوم لجنة البناية والأرنونا، ومن يدفع ماذا."),
                    _t("לסכם בכתב כל דבר שהובטח בעל פה.",
                       "Put in writing everything you were promised out loud.",
                       "Закрепить письменно всё, что обещали устно.",
                       "Mettre par écrit tout ce qui a été promis oralement.",
                       "تدوين كل ما وُعدت به شفهياً كتابةً."),
                ],
            },
            {
                "title": _t("שבועיים לפני", "Two weeks before", "За две недели", "Deux semaines avant",
                            "قبل أسبوعين"),
                "items": [
                    _t("להזמין הובלה, ולבקש מחיר סופי בכתב.",
                       "Book the movers, and ask for a final price in writing.",
                       "Заказать перевозку и попросить окончательную цену письменно.",
                       "Réserver le déménageur et demander un prix final par écrit.",
                       "حجز شركة النقل، وطلب سعر نهائي كتابةً."),
                    _t("להעביר את הארנונה, החשמל, המים והגז לשם שלכם, עם קריאת מונים ביום הכניסה.",
                       "Move the municipal tax, electricity, water and gas into your name, with meter readings on moving day.",
                       "Переоформить арнону, электричество, воду и газ на себя, со снятием показаний счётчиков в день въезда.",
                       "Mettre la taxe municipale, l'électricité, l'eau et le gaz à votre nom, avec un relevé des compteurs le "
                       "jour de l'entrée.",
                       "نقل الأرنونا والكهرباء والماء والغاز إلى اسمك، مع قراءة العدّادات يوم الدخول."),
                    _t("להזמין חיבור אינטרנט, כי לפעמים לוקח כמה ימים.",
                       "Order the internet connection, since it sometimes takes a few days.",
                       "Заказать подключение интернета, иногда это занимает несколько дней.",
                       "Commander la connexion internet, cela prend parfois quelques jours.",
                       "طلب توصيل الإنترنت، لأنه قد يستغرق بضعة أيام."),
                    _t("לעדכן כתובת בדואר, בבנק ובקופת החולים.",
                       "Update your address with the post office, the bank and your health fund.",
                       "Обновить адрес на почте, в банке и в больничной кассе.",
                       "Mettre à jour votre adresse auprès de la poste, de la banque et de la caisse maladie.",
                       "تحديث العنوان في البريد والبنك وصندوق المرضى."),
                ],
            },
            {
                "title": _t("ביום הכניסה", "On moving day", "В день въезда", "Le jour de l'entrée", "يوم الدخول"),
                "items": [
                    _t("לצלם את המונים ואת מצב הדירה, עם תאריך.",
                       "Photograph the meters and the state of the flat, with the date.",
                       "Сфотографировать счётчики и состояние квартиры, с датой.",
                       "Photographier les compteurs et l'état de l'appartement, avec la date.",
                       "تصوير العدّادات وحالة الشقة، مع التاريخ."),
                    _t("לקבל את כל המפתחות, כולל תיבת דואר וחניה.",
                       "Get every key, including the mailbox and the parking.",
                       "Получить все ключи, включая почтовый ящик и парковку.",
                       "Récupérer toutes les clés, y compris la boîte aux lettres et le parking.",
                       "استلام كل المفاتيح، بما فيها صندوق البريد والموقف."),
                    _t("לבדוק איפה הברז הראשי של המים ולוח החשמל.",
                       "Find the main water valve and the electrical panel.",
                       "Найти главный водяной кран и электрощит.",
                       "Repérer le robinet d'arrivée d'eau et le tableau électrique.",
                       "معرفة مكان محبس المياه الرئيسي ولوحة الكهرباء."),
                ],
            },
            {
                "title": _t("אחרי", "After", "После", "Après", "بعد ذلك"),
                "items": [
                    _t("לשמור את החוזה, הקבלות ותמונות הכניסה עד סוף השכירות.",
                       "Keep the contract, the receipts and the moving-in photos until the lease ends.",
                       "Хранить договор, квитанции и фото при въезде до конца аренды.",
                       "Garder le contrat, les reçus et les photos d'entrée jusqu'à la fin du bail.",
                       "الاحتفاظ بالعقد والإيصالات وصور الدخول حتى نهاية الإيجار."),
                ],
            },
        ],
        "sources": [],
    },
    "contract": {
        "path": "/rental-contract-check",
        "checklist": False,
        "title": _t("מה לבדוק בחוזה שכירות", "What to check in a rental contract", "Что проверить в договоре аренды",
                    "Ce qu'il faut vérifier dans un bail", "ما الذي يجب فحصه في عقد الإيجار"),
        "lead": _t(
            "הנקודות שכדאי לבדוק לפני שחותמים. זה לא ייעוץ משפטי: בכל שאלה, כדאי לבדוק במקור או עם עורך דין.",
            "The points worth checking before you sign. This is not legal advice: for any question, check the source or a "
            "lawyer.",
            "Что стоит проверить до подписания. Это не юридическая консультация: при любом вопросе сверьтесь с источником "
            "или юристом.",
            "Les points à vérifier avant de signer. Ce n'est pas un conseil juridique : en cas de doute, consultez la source "
            "ou un avocat.",
            "النقاط التي يجدر فحصها قبل التوقيع. هذه ليست استشارة قانونية: لأي سؤال، راجع المصدر أو محامياً.",
        ),
        "sections": [
            {
                "title": _t("מה החוק קובע", "What the law says", "Что говорит закон", "Ce que dit la loi",
                            "ما ينصّ عليه القانون"),
                "items": [
                    _t("<b>על מה זה חל:</b> שכירות למגורים של יותר משלושה חודשים (או עם אופציה להארכה), בשכר דירה של עד "
                       "20,000 ₪ בחודש.",
                       "<b>When it applies:</b> a residential lease of more than three months (or with an option to extend), "
                       "at a rent of up to ₪20,000 a month.",
                       "<b>Когда действует:</b> аренда жилья больше трёх месяцев (или с опцией продления) при плате до "
                       "20 000 ₪ в месяц.",
                       "<b>Quand cela s'applique :</b> un bail d'habitation de plus de trois mois (ou avec option de "
                       "prolongation), pour un loyer jusqu'à 20 000 ₪ par mois.",
                       "<b>متى ينطبق:</b> إيجار سكني لأكثر من ثلاثة أشهر (أو مع خيار التمديد)، بإيجار حتى 20,000 ₪ شهرياً."),
                    _t("<b>ערבות:</b> החוק מגביל כמה ערבות מותר לבקש: עד שליש מכל דמי השכירות של התקופה, ולא יותר משלושה "
                       "חודשי שכירות (הנמוך מביניהם). פיקדון במזומן חוזר תוך 60 יום מהחזרת הדירה.",
                       "<b>Guarantee:</b> the law caps it at a third of the rent for the whole period, and no more than three "
                       "months' rent (whichever is lower). A cash deposit comes back within 60 days of returning the flat.",
                       "<b>Гарантия:</b> закон ограничивает её третью арендной платы за весь срок и не более чем тремя "
                       "месячными платами (что меньше). Денежный залог возвращается в течение 60 дней после сдачи квартиры.",
                       "<b>Garantie :</b> la loi la limite au tiers du loyer de toute la période, et à trois mois de loyer au "
                       "plus (le plus bas des deux). Un dépôt en espèces est rendu dans les 60 jours après la remise de "
                       "l'appartement.",
                       "<b>الضمانة:</b> يحدّها القانون بثلث إيجار كامل المدة، وبما لا يزيد عن إيجار ثلاثة أشهر (الأقل "
                       "بينهما). يُعاد الإيداع النقدي خلال 60 يوماً من إعادة الشقة."),
                    _t("<b>תיקונים:</b> תקלה רגילה המשכיר צריך לתקן תוך 30 יום מהיום שביקשתם. תקלה שלא מאפשרת לגור בדירה "
                       "צריך לתקן תוך 3 ימים. חוזה יכול לקצר את הזמנים האלה, אבל לא להאריך אותם.",
                       "<b>Repairs:</b> the landlord must fix an ordinary fault within 30 days of your request, and one that "
                       "makes the flat unlivable within 3 days. A contract can shorten these times but not extend them.",
                       "<b>Ремонт:</b> обычную неисправность хозяин должен устранить в течение 30 дней после вашей просьбы, а "
                       "ту, что не даёт жить в квартире, за 3 дня. Договор может сократить эти сроки, но не увеличить.",
                       "<b>Réparations :</b> le bailleur doit réparer une panne ordinaire dans les 30 jours suivant votre "
                       "demande, et une panne qui rend le logement inhabitable dans les 3 jours. Un contrat peut raccourcir "
                       "ces délais, pas les allonger.",
                       "<b>التصليحات:</b> على المؤجّر إصلاح العطل العادي خلال 30 يوماً من طلبك، والعطل الذي يمنع السكن خلال "
                       "3 أيام. يمكن للعقد تقصير هذه المدد لا تمديدها."),
                    _t("<b>מה עליכם:</b> תיקונים קטנים, ונזק שנגרם משימוש לא סביר.",
                       "<b>What is on you:</b> small repairs, and damage caused by unreasonable use.",
                       "<b>Что на вас:</b> мелкий ремонт и ущерб от неразумного использования.",
                       "<b>Ce qui est à votre charge :</b> les petites réparations, et les dégâts dus à un usage "
                       "déraisonnable.",
                       "<b>ما عليك:</b> التصليحات الصغيرة، والضرر الناتج عن استعمال غير معقول."),
                ],
            },
            {
                "title": _t("מה לבדוק בחוזה עצמו", "What to look for in the contract itself", "Что проверить в самом договоре",
                            "Ce qu'il faut regarder dans le contrat", "ما يجب فحصه في العقد نفسه"),
                "items": [
                    _t("<b>אופציה להארכה:</b> לבדוק אם יש, ובאיזה מחיר.",
                       "<b>Option to extend:</b> check whether there is one, and at what price.",
                       "<b>Опция продления:</b> есть ли она и по какой цене.",
                       "<b>Option de prolongation :</b> vérifier s'il y en a une, et à quel prix.",
                       "<b>خيار التمديد:</b> التحقق من وجوده وبأي سعر."),
                    _t("<b>יציאה מוקדמת:</b> לבדוק אם אפשר לצאת לפני הסוף, ובאילו תנאים.",
                       "<b>Leaving early:</b> check whether you can leave before the end, and on what terms.",
                       "<b>Досрочный выезд:</b> можно ли съехать раньше и на каких условиях.",
                       "<b>Départ anticipé :</b> vérifier si vous pouvez partir avant la fin, et à quelles conditions.",
                       "<b>المغادرة المبكرة:</b> التحقق من إمكانية المغادرة قبل النهاية وبأي شروط."),
                    _t("<b>מסמך פגמים:</b> לצרף לחוזה רשימה ותמונות של מה שכבר לא תקין.",
                       "<b>List of defects:</b> attach a list and photos of what is already broken.",
                       "<b>Список дефектов:</b> приложить к договору список и фото того, что уже неисправно.",
                       "<b>Liste des défauts :</b> joindre au contrat une liste et des photos de ce qui ne fonctionne déjà "
                       "pas.",
                       "<b>قائمة العيوب:</b> إرفاق قائمة وصور لما هو معطّل أصلاً بالعقد."),
                ],
            },
        ],
        "sources": [
            (_t("כל זכות: תיקון ליקויים בדירה מושכרת", "Kol Zchut: repairing defects in a rented flat (Hebrew)",
                "Kol Zchut: ремонт неисправностей в съёмной квартире (иврит)",
                "Kol Zchut : réparation des défauts d'un logement loué (hébreu)",
                "كول زخوت: إصلاح العيوب في شقة مستأجرة (بالعبرية)"), _KOLZCHUT_REPAIRS),
            (_t("כל זכות: הגבלת סכום הערובה", "Kol Zchut: the cap on the guarantee (Hebrew)",
                "Kol Zchut: ограничение суммы гарантии (иврит)", "Kol Zchut : plafond de la garantie (hébreu)",
                "كول زخوت: تحديد مبلغ الضمانة (بالعبرية)"), _KOLZCHUT_GUARANTEE),
        ],
    },
}

CTA = _t(
    "לקבל כל דירה חדשה שמתאימה לכם, ברגע שהיא עולה",
    "Get every new flat that fits you, the moment it is posted",
    "Получать каждую подходящую квартиру сразу после публикации",
    "Recevoir chaque nouvel appartement qui vous correspond, dès sa publication",
    "استلم كل شقة جديدة تناسبك لحظة نشرها",
)
SOURCES_TITLE = _t("מקורות", "Sources", "Источники", "Sources", "المصادر")


def text(entry: dict, lang: str) -> str:
    return entry.get(lang) or entry["he"]
