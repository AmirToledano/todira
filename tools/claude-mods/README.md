# Claude Code mods

Three small mods for Claude Code, kept here so one install covers every session and project.

| Mod | What it does |
| --- | --- |
| `usage-band` | A row above the prompt: 5-hour and 7-day usage (used and left), context fill, session cost. `/usage` prints the same as one line of text, for sessions where nothing draws (a cloud session). |
| `rtl-messages` | Draws Hebrew and Arabic messages right-to-left, yours and Claude's. `/rtl` toggles it. |
| `hide-replies` | A button in that row that collapses Claude's replies to one dim line each, and shows them again. |

## Install (run in a terminal Claude Code)

```
/plugin marketplace add AmirToledano/todira
/plugin install usage-band@todira-mods
/plugin install rtl-messages@todira-mods
/plugin install hide-replies@todira-mods
```

Choose the **user** scope when asked: the mods then load in every session and every project on that machine.

## Cloud sessions of this repo

`.claude/settings.json` at the repo root enables all three for any Claude Code session opened on this repository, local or
cloud. Other repositories need the same file (or the user-scope install above on the machine that runs the session).

## Where the mods can draw

The row, the button and the right-to-left drawing are rendered by a surface: the terminal, the desktop app or VS Code
running a **local** session. A cloud session has no attached surface (the engine log says `nothing attached draws`), so
those three cannot show there. Two text fallbacks exist: `/usage` prints the figures on demand, and in a session where no screen draws, `usage-band` hands Claude the live figures as hidden context with the instruction to close each reply with one 📊 line (`/usage-footer` toggles it; it adds nothing where a surface draws the row itself). To see the mods in the desktop app, run the session locally.
