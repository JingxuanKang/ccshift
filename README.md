# ccshift

**English** | [中文](README.zh-CN.md)

A clickable **model / effort shift bar** in the Claude Code statusline. Click a token to switch the **current session's** model or reasoning effort — your defaults never move, and new sessions always start from them.

```
  [Fable 5 ◕ xhigh] │ my-project git:(main)
  Context ░░░░░░░░░░ 0% │ Usage ██████░░░░ 57% (resets in 3h 32m)
  ⇧ GROK  GEMINI  GPT  OPUS  OPUS4.8  FABLE │ LOW  MED  HIGH  XHIGH   ← click this line
```

The current model / effort is highlighted in bold amber.

No daemon, no polling, no keybindings — code only runs at the moment you click.

## Why

Claude Code's built-in `/model` and `/effort` have a side effect: **the choice is written to `~/.claude/settings.json`**, so every session you open afterwards inherits it. "Drop this one session to Haiku for grunt work, keep everything else on the big model" isn't a one-click operation (`/model` has a session-only `s` shortcut buried in its menu; `/effort` has no equivalent).

ccshift makes it one click: it injects the `/model` / `/effort` command to switch the current session, then immediately restores `settings.json` from a pre-click snapshot. Net effect: **session-scoped switching, defaults pinned**.

## Install

```bash
git clone https://github.com/JingxuanKang/ccshift.git
cd ccshift && ./install.sh
```

The installer does exactly two things, both reversible:

1. **Statusline** — points `statusLine.command` in `~/.claude/settings.json` at a generated wrapper. **If you already use a statusline (claude-hud, a custom script, anything), it is preserved automatically**: the wrapper runs it first, then appends the shift bar as one extra line.
2. **tmux** — writes one marked block into `~/.tmux.conf` (the click binding) and reloads running servers.

Re-run `./install.sh` any time (after `git pull`, or after moving the repo) — it's idempotent. Remove everything with:

```bash
./install.sh --uninstall
```

> ⚠️ claude-hud users: re-running `/claude-hud:setup` or `/claude-hud:configure` overwrites `statusLine.command` and the shift bar disappears. Just run `./install.sh` again — it re-wraps the new claude-hud command.

### Requirements

| Dependency | Needed for | Notes |
|---|---|---|
| Claude Code | everything | — |
| tmux ≥ 3.1 with `mouse on` | **clicking only** | The binding uses the `#{m/r:…}` regex format (tmux 3.1+). The installer sets `mouse on`. **tmux is currently the only host that can provide the click layer** — see the boundary below |
| python3 | clicking only | Click handler; system python3 is fine, no packages |
| jq | optional | Highlights the current model/effort; without it the bar still renders, just not highlighted |
| claude-hud | **not required** | Just a common neighbor — the bar appends to any statusline, or stands alone |

**The boundary, stated plainly:** the bar *displays* in any terminal and under any multiplexer — it is just one extra line printed by the statusline, independent of the host. But *clicking* requires the host to satisfy a narrow condition: **it must intercept mouse clicks inside the pane and hand the click coordinates to an external shell command.**

Only tmux offers that hook today (`bind-key -n MouseDown1Pane` plus `#{mouse_x} #{mouse_y}`). In a bare terminal, mouse events go straight to the app and nothing outside can intercept them; **other multiplexers generally capture the mouse but do not expose coordinates to external commands**, so they cannot click either.

When the host does not qualify, the bar **degrades to a read-only gauge**: the highlight still tracks the current model/effort, it just is not clickable. Switch with the built-in `/model` (press `s` for session-only) and `/effort`.

> Why no keyboard-binding fallback? **"No keyboard bindings, no separate panel" is a design red line for this project** — ccshift exists to provide exactly one interaction, a click inside the HUD. When that is unavailable it stays read-only rather than growing a second way to operate it.

<details>
<summary>Known host compatibility (verified 2026-08)</summary>

| Host | Displays | Clicks | Notes |
|---|---|---|---|
| tmux ≥ 3.1 | ✅ | ✅ | The only fully supported host |
| tmux < 3.1 | ✅ | ❌ | Lacks the `#{m/r:…}` regex format |
| [Herdr](https://herdr.dev) 0.8.0 | ✅ | ❌ | See below |
| Bare terminal (Ghostty / iTerm / …) | ✅ | ❌ | Mouse events reach claude directly; nothing outside can intercept |

**Herdr specifics** (the most common surprise when switching multiplexers): its custom-command hook `[[keys.command]]` accepts **keyboard** binding syntax only (`prefix+x` / `ctrl+letter` / function keys). There is no mouse-event binding and no way to pass click coordinates to an external script, so the click layer cannot be ported. This is a capability gap, not a misconfiguration.

Herdr does, however, provide both tmux primitives this project's **execution layer** relies on, and more conveniently:

| What ccshift uses tmux for | Herdr equivalent |
|---|---|
| `tmux capture-pane -p` | `herdr pane read <pane-id> --source visible` |
| `send_command()` in `hud_click.py` (C-u clear → type → verify composer → Enter → up to 4 retries) | `herdr agent prompt <pane-id> "/model opus"` — atomically submits text plus Enter, honoring bracketed-paste |

So: **if Herdr ever gains mouse-event bindings with coordinates, the click layer ports directly and the execution layer gets considerably simpler** (the fragile retry loop in `hud_click.py` could be deleted outright). Until then, use the read-only gauge behavior described above under Herdr.
</details>

## How it works

| Layer | Where | Job |
|---|---|---|
| Display | `bin/hud-shift-line.sh` | Renders the bar as an extra statusline line; highlights the current model/effort from the statusline JSON |
| Click | `MouseDown1Pane` binding in `~/.tmux.conf` | Intercepts clicks only on lines matching `⇧.*GROK.*XHIGH`; every other click passes through untouched |
| Execute | `bin/hud-click.sh` → `bin/hud_click.py` | Locates the clicked token by display column → snapshots settings → injects the command (clear line → type → verify composer → Enter, retried) → restores the snapshot |

Restore safety: `settings.json`'s `model` key is read once at session startup and never hot-reloaded (verified on Claude Code 2.1.200), so restoring it after a click never affects running sessions. Concurrent clicks are serialized with `flock`. The `#{socket_path}` passed by the binding means it works on **any tmux server/socket**, not just the default one.

## Costs & caching

**Switching mid-session invalidates the prompt cache.** Anthropic's prompt cache is a prefix match in three tiers (`tools → system → messages`), and invalidation is tiered:

| Change | tools cache | system cache | messages cache |
|---|---|---|---|
| Switch model / change tool list | ❌ | ❌ | ❌ |
| Edit system prompt | kept | ❌ | ❌ |
| Change thinking / effort parameters | kept | kept | ❌ |

In a long session nearly all tokens sit in `messages` (conversation history + tool output), so **both a model switch and an effort switch effectively re-read the whole context at uncached prices** (slower first token; the longer the context, the more it costs). **This is Claude Code / Anthropic API behavior, not something ccshift adds** — the built-in `/model` and `/effort` behave identically. Switching back to the original model within the cache TTL (~5 minutes) may still hit.

Two more things to know:

- **The large-context guardrail dialog**: on sessions past 200k context, Claude Code shows a usage-credits confirmation before switching model/effort (cancel prints "Kept model as … / Kept effort level as …"). ccshift **deliberately does not auto-confirm it** — at that point a switch means cache invalidation plus long-context pricing, and that decision belongs to you. It's a guardrail, not a bug.
- A click clears the input line first (Ctrl-U) — don't leave an unsent draft in the composer when you click.

## Manual install

If you'd rather not run the script: wire the two integration points yourself.

**1. Statusline** — Claude Code pipes a JSON blob to your `statusLine.command` on stdin. Feed that JSON to both your existing statusline and `bin/hud-shift-line.sh` (which prints one extra line). Either point `statusLine.command` straight at the script (bar only):

```json
"statusLine": { "type": "command", "command": "bash /path/to/ccshift/bin/hud-shift-line.sh" }
```

or append to your own wrapper script (read stdin into a variable first — it can only be read once):

```bash
printf '%s' "$input" | bash /path/to/ccshift/bin/hud-shift-line.sh
```

**2. tmux** — add to `~/.tmux.conf` and `tmux source-file` it:

```tmux
set -g mouse on
bind-key -n MouseDown1Pane if-shell -F '#{m/r:⇧.*GROK.*XHIGH,#{mouse_line}}' \
  'run-shell -b "/path/to/ccshift/bin/hud-click.sh #{socket_path} #{pane_id} #{mouse_x} #{mouse_y}"' \
  'select-pane -t = ; send-keys -M'
```

## Customization

The token table is coupled in **three places** — change one, change all three, or click targeting breaks:

1. `bin/hud-shift-line.sh` — the bar's labels;
2. the `TOKENS` table in `bin/hud_click.py` — label → `/model` / `/effort` argument mapping (**longer tokens must come first**: `OPUS4.8` before `OPUS`, `XHIGH` before `HIGH`);
3. the regex `⇧.*GROK.*XHIGH` in the tmux binding — the signature that identifies the bar's line.

When the Claude Code model lineup changes (new tiers, renames), update those three places.

## Verify / debug

Open a Claude Code session inside tmux and click a different model token: the composer types `/model <x>` and submits, the highlight jumps, and `~/.claude/settings.json` still holds your default. Click logs are in `logs/hud-click.log`.

**Clicks do nothing?** Narrow down which layer is broken:

```bash
echo "$TMUX"                                   # empty = not inside tmux → no click layer, see the boundary above
tmux show -g mouse                             # expect: mouse on
grep -c 'MouseDown1Pane' ~/.tmux.conf          # expect ≥ 1; run tmux source-file after editing the conf
tail ~/Build/ccshift/logs/hud-click.log        # any lines = the click was intercepted, so the problem is in the execution layer
```

A bar that **still renders but no longer responds to clicks** usually means the host changed (tmux → Herdr, or tmux → bare terminal). The display layer is host-independent, so everything looks normal. That is the known limitation in the compatibility table above, not a bug.

## License

MIT
