# Claude Code mods

Three small mods for Claude Code, kept here so one install covers every session and project.

| Mod | What it does |
| --- | --- |
| `usage-band` | A row above the prompt: 5-hour and 7-day usage (used and left), context fill, session cost. |
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
