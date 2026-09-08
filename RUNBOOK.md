# טודירה — Disaster Recovery Runbook

Read this when the site/bot is down and you need to actually fix it, not investigate slowly. For
day-to-day project history and decisions, see `PROJECT_STATE.md` instead — this file is only
"something is broken, what do I do right now."

## ⚠️ The one fact that matters most: where the data actually lives

This is a **single EC2 node** running k3s. Everything — website, bot, Postgres — runs on that one
box. Postgres's data directory is a PersistentVolumeClaim with no `storageClassName` set, which
means it uses the cluster's only available StorageClass: **`local-path-provisioner`** — i.e. a
plain directory on that same node's own root EBS volume, not a separate/networked disk.

**What this means in practice:**
- **Stop → Start the same EC2 instance**: the EBS volume survives, Postgres data survives. This
  already happened once (see `PROJECT_STATE.md`'s 2026-08-30 entry) — the only real issue was a
  changed public IP breaking `KUBECONFIG_B64` (fix: below).
- **Terminate the instance, lose the EBS volume, or a hardware/AZ failure**: **the database is
  gone. Permanently.** Every user, every saved filter, every payment record — gone, with no way
  to get it back, **unless a backup exists somewhere else.**
- As of 2026-09-08, **there is no automated backup of any kind.** This is the single biggest
  operational risk in the whole project — worth fixing before real paying customers rely on this.

## Step 1 — confirm what's actually broken

1. Try `https://todira.app/healthz` in a browser or `curl -i https://todira.app/healthz`.
   - `200 ok` → the website + DB are both fine. If the BOT specifically seems dead (no replies on
     Telegram), skip to "Bot-only issue" below — the site being healthy means the node itself is up.
   - Connection refused / times out entirely → the whole node is likely down. Go to Step 2.
   - `503 db unreachable` → the website process is up but Postgres isn't. Go to Step 3.
2. If you have Telegram alerts configured (the `{{ .Release.Name }}-healthcheck` CronJob, added
   2026-09-08 — see `charts/todira/templates/healthcheck-cronjob.yaml`), a 🚨 message from the bot
   itself is usually the first sign, ~15 minutes after something breaks. **Remember its real
   limit**: it runs INSIDE this same node, so if the node itself is dead, this alert never fires —
   don't wait for it to confirm a total outage. See "Set up real external monitoring" at the
   bottom for the piece that actually covers that case.

## Step 2 — the whole node is down

1. AWS Console → EC2 → Instances → find the instance (check its state: running / stopped /
   impaired / terminated).
2. **If it's just stopped or impaired**: Start it. Same EBS volume, same instance ID → Postgres
   data is intact.
   - **Its public IP will very likely change** on Start (unless it has an Elastic IP attached —
     check first). If it does change, `KUBECONFIG_B64` (the GitHub Actions repo secret CI/CD uses
     to `helm upgrade`) now points at the OLD IP and every deploy will fail with a timeout — this
     exact thing happened once already (`PROJECT_STATE.md`, 2026-08-30 entry). Fix: get the new
     kubeconfig off the box (SSH or AWS Instance Connect/CloudShell `aws ssm start-session`, then
     `cat ~/.kube/config` or wherever k3s wrote it, usually `/etc/rancher/k3s/k3s.yaml` — swap
     `127.0.0.1` for the new public IP), base64 it (`base64 -w0 config.yaml`), update the
     `KUBECONFIG_B64` GitHub secret. Also update DNS (`todira.app`'s A record) to the new IP if it
     changed — check your DNS provider (Porkbun, per this project's own domain purchase).
   - SSH in (`diramir-key.pem`, per earlier project history) and sanity-check: `sudo systemctl
     status k3s`, `free -h` (was it an OOM kill?), `dmesg | tail`.
3. **If it's genuinely gone (terminated, corrupted, AMI issue)**: you're rebuilding from scratch.
   - Launch a new EC2 instance (t3.small or larger — the original t2/t3.micro was already flagged
     as flaky under load).
   - Install k3s (`curl -sfL https://get.k3s.io | sh -`).
   - Update `KUBECONFIG_B64` (same steps as above) and the DNS A record to the new instance's IP.
   - Re-run the GitHub Actions deploy (or push any commit to `main` — CI/CD runs `helm upgrade`
     automatically) — this rebuilds every Deployment/Service/CronJob from the chart in
     `charts/todira/` exactly as it's checked into git. Code and infra config come back instantly.
   - **The database does not.** A fresh Postgres pod starts with an EMPTY database. This is the
     scenario a backup is for — if one exists, restore it now (see whatever backup mechanism is in
     place at the time you're reading this — check `charts/todira/templates/` for a
     `*backup*` CronJob and `PROJECT_STATE.md`'s most recent entries for how it's configured).
     **If no backup exists, this data is unrecoverable — every user has to sign up again from
     zero.**

## Step 3 — website is up, Postgres specifically isn't

1. `kubectl get pods` (from wherever your kubeconfig points, or SSH'd into the node itself with
   local access to the cluster) — look for the `*-postgres-*` pod. `CrashLoopBackOff` /
   `Pending` / `0/1 Running` all point here.
2. `kubectl logs <postgres-pod-name>` — common causes: the PVC's underlying disk filled up
   (`df -h` on the node itself), a bad `POSTGRES_PASSWORD` secret change without a matching
   checksum-triggered restart (should self-heal now, see the 2026-09-07 fix in
   `postgres-deployment.yaml`), or actual disk corruption on the node.
3. `kubectl describe pod <postgres-pod-name>` for scheduling issues (e.g. the PVC's node affinity
   pointing at a node that no longer exists — only relevant if the cluster ever grows past one
   node, not the case today).

## Bot-only issue (website is fine, but Telegram doesn't reply)

The bot has its own liveness probe (added 2026-09-08 — `bot-deployment.yaml`, checks a heartbeat
file `main.py` touches on every JobQueue tick). A genuinely hung bot process should now
self-restart within ~45-60 seconds without any manual action. If it's STILL not responding after
a few minutes:
1. `kubectl get pods -l app=todira-bot` (the Helm release is named `todira` — see `ci-cd.yaml`'s
   `helm upgrade --install todira`) — is it actually restarting
   repeatedly (`RESTARTS` column climbing)? That means it's crash-looping, not just hung — check
   `kubectl logs --previous <pod>` for the actual exception.
2. Check the bot's own Telegram-side status: is `TELEGRAM_BOT_TOKEN` still valid (the owner didn't
   revoke it via @BotFather)? A revoked/wrong token makes the bot silently unable to poll at all.

## After any recovery — verify, don't assume

1. Load `https://todira.app` in an actual browser, not just `/healthz` (confirms Caddy's cert +
   proxying, not just the backend).
2. Send `/start` to the Telegram bot from a real account.
3. If DNS or the domain changed at all, re-verify `https://todira.app/healthz` resolves and
   returns 200 from an external network (your phone on cellular data, not the same WiFi as
   whatever you're debugging from — rules out a purely local DNS-cache issue looking like a real
   outage).

## The two things this runbook can't fix by itself — set these up

1. **Automated off-node database backups.** Nothing in this repo does this as of 2026-09-08 — see
   the warning at the top. Needs a decision on where backups go (S3, or something simpler) before
   it can be built; once it exists, this section should be updated with exactly how to restore
   from one.
2. **External uptime monitoring.** The in-cluster `healthcheck` CronJob (see Step 1) cannot detect
   the node itself going down — only a monitor running OUTSIDE this infrastructure entirely can.
   A free tier of UptimeRobot / Better Uptime / similar, pointed at `https://todira.app/healthz`
   on a 1-5 minute interval with a Telegram or email alert, closes this gap. This needs an account
   signup — not something deployable from a coding session.
