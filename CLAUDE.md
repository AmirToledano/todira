# Todira: notes for Claude

- **Product.** An Israeli apartment-alert Telegram bot plus the site todira.app.
- **Code layout:**
  - FastAPI + Jinja site in `website/`
  - bot in `bot/`
  - scrapers and scheduled steps in `scraper/`
  - shared code in `common/todira_common/`
- **State.** Read `HANDOFF.md` first (where the last conversation stopped), then `PROJECT_STATE.md` for where things stand.
- **Handoff.** At the end of every task, update `HANDOFF.md` (the owner's last request, what is in progress, waiting
  for the owner, waiting for approval) in the same commit as the task, so the next conversation, on the computer or
  in the cloud, continues exactly from there. In Hebrew, short.

## Before you design or change anything visual
Read `DESIGN.md` (the design language) and follow it.
- One gold button per screen.
- Heebo for text, Rubik for headings, Karantina only for the home page's big headlines.
- Colours come from the tokens in `website/static/style.css`.
- Real content only.
- Check the page at 390px wide, in light and dark.

## Text rules (site, bot, channel, Instagram)
- No "—" or "–" in anything a user reads.
- Never name the sites ads come from.
- Never write the bot's @name. Put the link on words: `t.me/AmirDirotBot?start=<source>`.
- Messages to users go out only between 09:00 and 12:00 Israel time.
- Never put the owner's phone, Telegram id, email, address, card or ID number in code, workflows, commits or logs.

## Checks
- `ruff check .`
- `python -m pytest tests -q`
