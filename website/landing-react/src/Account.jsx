import { motion } from "framer-motion";
import { t, pageConfig } from "./i18n";

const easePremium = [0.16, 1, 0.3, 1];

const PLAN_LABEL_KEYS = {
  weekly: "upgrade.plan_weekly",
  biweekly: "upgrade.plan_biweekly",
  monthly: "upgrade.plan_monthly",
  monthly_subscription: "upgrade.plan_subscription",
};
const PAYMENT_STATUS_LABEL_KEYS = {
  paid: "account.payment_status_paid",
  pending: "account.payment_status_pending",
  failed: "account.payment_status_failed",
  cancelled: "account.payment_status_cancelled",
};
const PAYMENT_STATUS_CLASS = {
  paid: "amc-status-ok",
  pending: "amc-status-warn",
  failed: "amc-status-bad",
  cancelled: "amc-status-bad",
};

// 2026-09-25: /account became a React island — its 4 POST actions (cancel/resume-subscription,
// notifications, whatsapp-notifications) are deliberately still plain <form method="post"> native
// submits, not fetch — see main.py's account() route comment for why. This component only reskins
// presentation around those same native forms/hidden fields.
export default function Account() {
  const {
    uid,
    wid,
    hasTelegram,
    hasWhatsapp,
    hasGoogle,
    telegramUsername,
    whatsappPhoneNumber,
    googleEmail,
    code,
    telegramLink,
    whatsappLink,
    displayIsOwner,
    hasAccess,
    trialEndsAt,
    paidUntil,
    notificationsEnabled,
    whatsappNotificationsOptedIn,
    payments,
    hasActiveSubscription,
    cancelAtPeriodEnd,
  } = pageConfig;

  const identityFields = (
    <>
      {uid != null && <input type="hidden" name="uid" value={uid} />}
      {wid && <input type="hidden" name="wid" value={wid} />}
    </>
  );

  const upgradeHref = uid != null
    ? `/upgrade?uid=${encodeURIComponent(uid)}`
    : wid
      ? `/upgrade?wid=${encodeURIComponent(wid)}`
      : "/upgrade";

  return (
    <>
      <motion.div
        className="page-banner"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: easePremium }}
      >
        <div className="pb-text">
          <h1>{t("account.h1")}</h1>
          <p>{t("account.subtitle")}</p>
        </div>
      </motion.div>

      <motion.div
        className="settings-card"
        style={{ marginBottom: 20 }}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1, ease: easePremium }}
      >
        <div className="field-row">
          {!displayIsOwner && (
            <div className="field" style={{ textAlign: "center" }}>
              <div className="field-section-title" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>
                {t("account.subscription_title")}
              </div>
              {hasAccess ? (
                <p className="channel-status connected">
                  {paidUntil
                    ? t("account.subscription_active", { date: paidUntil })
                    : trialEndsAt
                      ? t("account.subscription_trial", { date: trialEndsAt })
                      : null}
                </p>
              ) : (
                <p className="amc-status amc-status-warn" style={{ fontSize: ".95rem", fontWeight: 600 }}>
                  {t("account.subscription_expired")}
                </p>
              )}
              {hasActiveSubscription ? (
                cancelAtPeriodEnd ? (
                  <>
                    <p className="field-hint" style={{ marginTop: 6 }}>{t("account.subscription_will_not_renew")}</p>
                    <form method="post" action="/account/resume-subscription" style={{ marginTop: 10 }}>
                      {identityFields}
                      <button type="submit" className="btn gold block">{t("account.resume_subscription_cta")}</button>
                    </form>
                  </>
                ) : (
                  <>
                    <p className="field-hint" style={{ marginTop: 6 }}>{t("account.subscription_auto_renews")}</p>
                    <form method="post" action="/account/cancel-subscription" style={{ marginTop: 10 }}>
                      {identityFields}
                      <button type="submit" className="btn outline block">{t("account.cancel_subscription_cta")}</button>
                    </form>
                  </>
                )
              ) : (
                <a className="btn gold block" style={{ marginTop: 10 }} href={upgradeHref}>
                  {hasAccess ? t("account.upgrade_cta_renew") : t("account.upgrade_cta_start")}
                </a>
              )}
            </div>
          )}

          <div className="field" style={{ textAlign: "center" }}>
            <div className="field-section-title" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>
              {t("account.notifications_title")}
            </div>
            <p className={`channel-status${notificationsEnabled ? " connected" : ""}`}>
              {notificationsEnabled ? t("account.status_on") : t("account.status_off")}
            </p>
            <form method="post" action="/account/notifications" style={{ marginTop: 10 }}>
              {identityFields}
              <button type="submit" className="btn outline block">
                {notificationsEnabled ? t("account.notifications_toggle_off") : t("account.notifications_toggle_on")}
              </button>
            </form>
          </div>

          {hasWhatsapp && (
            <div className="field" style={{ textAlign: "center" }}>
              <div className="field-section-title" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>
                {t("account.whatsapp_notifications_title")}
              </div>
              <p className={`channel-status${whatsappNotificationsOptedIn ? " connected" : ""}`}>
                {whatsappNotificationsOptedIn ? t("account.status_on") : t("account.status_off")}
              </p>
              <form method="post" action="/account/whatsapp-notifications" style={{ marginTop: 10 }}>
                {identityFields}
                <button type="submit" className="btn outline block">
                  {whatsappNotificationsOptedIn
                    ? t("account.whatsapp_notifications_toggle_off")
                    : t("account.whatsapp_notifications_toggle_on")}
                </button>
              </form>
              <p className="field-hint" style={{ marginTop: 10 }}>{t("account.whatsapp_notifications_hint")}</p>
            </div>
          )}
        </div>
      </motion.div>

      <motion.div
        className="settings-card"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.18, ease: easePremium }}
      >
        <div className="field-section-title" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>
          {t("account.channels_title")}
        </div>
        <div className="field-row">
          <motion.div
            className="field channel-tile"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.24, ease: easePremium }}
          >
            <span className="channel-icon" aria-hidden="true">
              <svg width="30" height="30" viewBox="0 0 24 24">
                <path
                  fill="#229ED9"
                  d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"
                />
              </svg>
            </span>
            <div className="field-section-title" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>Telegram</div>
            {hasTelegram ? (
              <>
                <p className="channel-status connected">{t("account.channel_connected")}</p>
                {telegramUsername && <p className="field-hint">@{telegramUsername}</p>}
              </>
            ) : telegramLink ? (
              <>
                <a className="btn telegram block" href={telegramLink} target="_blank" rel="noreferrer">
                  {t("account.telegram_connect_cta")}
                </a>
                <p className="field-hint" style={{ marginTop: 10 }}>{t("account.telegram_connect_hint")}</p>
              </>
            ) : (
              <p className="field-hint">{t("account.no_active_code")}</p>
            )}
          </motion.div>

          <motion.div
            className="field channel-tile"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.3, ease: easePremium }}
          >
            <span className="channel-icon" aria-hidden="true">
              <svg width="30" height="30" viewBox="0 0 24 24">
                <path
                  fill="#25D366"
                  d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"
                />
              </svg>
            </span>
            <div className="field-section-title" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>WhatsApp</div>
            {hasWhatsapp ? (
              <>
                <p className="channel-status connected">{t("account.channel_connected")}</p>
                {whatsappPhoneNumber && <p className="field-hint">{whatsappPhoneNumber}</p>}
              </>
            ) : whatsappLink ? (
              <>
                <a className="btn whatsapp block" href={whatsappLink} target="_blank" rel="noreferrer">
                  {t("account.whatsapp_connect_cta")}
                </a>
                <p className="field-hint" style={{ marginTop: 10 }}>{t("account.whatsapp_connect_hint")}</p>
              </>
            ) : code ? (
              <p className="field-hint">{t("account.whatsapp_connect_unavailable")}</p>
            ) : (
              <p className="field-hint">{t("account.no_active_code")}</p>
            )}
          </motion.div>

          <motion.div
            className="field channel-tile"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.36, ease: easePremium }}
          >
            <span className="channel-icon channel-icon-plain" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 18 18">
                <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.71v2.26h2.9c1.7-1.57 2.7-3.87 2.7-6.6z" />
                <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.9-2.26c-.8.54-1.84.86-3.06.86-2.35 0-4.34-1.59-5.05-3.72H.96v2.33A9 9 0 0 0 9 18z" />
                <path fill="#FBBC05" d="M3.95 10.7A5.4 5.4 0 0 1 3.66 9c0-.59.1-1.17.29-1.7V4.97H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.03l2.99-2.33z" />
                <path fill="#EA4335" d="M9 3.58c1.32 0 2.51.46 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.97l2.99 2.33C4.66 5.17 6.65 3.58 9 3.58z" />
              </svg>
            </span>
            <div className="field-section-title" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>Google</div>
            {hasGoogle ? (
              <>
                <p className="channel-status connected">{t("account.channel_connected")}</p>
                {googleEmail && <p className="field-hint">{googleEmail}</p>}
              </>
            ) : (
              <a
                className="btn google block"
                href={`/auth/google/start?next=/account${uid != null ? `&uid=${encodeURIComponent(uid)}` : ""}`}
              >
                {t("account.google_connect_cta")}
              </a>
            )}
          </motion.div>
        </div>
        {code && (
          <p className="field-hint" style={{ textAlign: "center", marginTop: 20 }}>
            {t("account.code_hint_prefix")} <b>{code}</b> {t("account.code_hint_suffix")}
          </p>
        )}
      </motion.div>

      {payments && payments.length > 0 && (
        <motion.div
          className="settings-card"
          style={{ marginTop: 20 }}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.26, ease: easePremium }}
        >
          <div className="field-section-title" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>
            {t("account.payment_history_title")}
          </div>
          <div className="payment-history">
            {payments.map((payment, i) => (
              <motion.div
                className="payment-row"
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: 0.05 * i, ease: easePremium }}
              >
                <span className="payment-plan">
                  {PLAN_LABEL_KEYS[payment.plan] ? t(PLAN_LABEL_KEYS[payment.plan]) : payment.plan}
                </span>
                <span className="payment-amount">₪{payment.amountIls}</span>
                <span className="payment-date">{payment.date}</span>
                <span className={`amc-status ${PAYMENT_STATUS_CLASS[payment.status] || "amc-status-bad"}`}>
                  {PAYMENT_STATUS_LABEL_KEYS[payment.status] ? t(PAYMENT_STATUS_LABEL_KEYS[payment.status]) : payment.status}
                </span>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </>
  );
}
