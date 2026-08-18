# ccshift

**English** | [中文](README.zh-CN.md)

A clickable **model / effort shift bar** in the Claude Code statusline. Click a token to switch the **current session's** model or reasoning effort — your defaults never move, and new sessions always start from them.

```
  [Fable 5 ◕ xhigh] │ my-project git:(main)
  Context ░░░░░░░░░░ 0% │ Usage ██████░░░░ 57% (resets in 3h 32m)
  ⇧ GROK  GEMINI  GPT  OPUS  OPUS4.8  FABLE │ LOW  MED  HIGH  XHIGH   ← click this line
```

The current model / effort is highlighted in bold amber. **Single click under tmux, Ctrl+click under Herdr** (why, below).

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
| tmux ≥ 3.1 with `mouse on` | clicking, under tmux | The binding uses the `#{m/r:…}` regex format (tmux 3.1+). The installer sets `mouse on` |
| [Herdr](https://herdr.dev) ≥ 0.8.0 | clicking, under Herdr | Uses a plugin link handler — see "Two hosts" below |
| python3 | clicking only | Handler for both hosts; system python3 is fine, no packages |
| jq | optional | Highlights the current model/effort; without it the bar still renders, just not highlighted |
| claude-hud | **not required** | Just a common neighbor — the bar appends to any statusline, or stands alone |

**The boundary, stated plainly:** the bar *displays* in any terminal and under any multiplexer — it is just one extra line printed by the statusline, independent of the host. *Clicking* needs the host to hand the click out, and each host offers a different hook:

| Host | Displays | Clicks | How |
|---|---|---|---|
| tmux ≥ 3.1 | ✅ | ✅ | **single click** |
| [Herdr](https://herdr.dev) ≥ 0.8.0 | ✅ | ✅ | **Ctrl+click** |
| tmux < 3.1 | ✅ | ❌ | Lacks the `#{m/r:…}` regex format |
| Bare terminal (Ghostty / iTerm / …) | ✅ | ❌ | Mouse events reach claude directly; nothing outside can intercept |

On an unsupported host the bar **degrades to a read-only gauge**: the highlight still tracks the current model/effort, it just is not clickable. Switch with the built-in `/model` (press `s` for session-only) and `/effort`.

> Why no keyboard-binding fallback? **"No keyboard bindings, no separate panel" is a design red line for this project** — ccshift exists to provide exactly one interaction, a click inside the HUD. When that is unavailable it stays read-only rather than growing a second way to operate it. (Ctrl+click is still a click, so it does not break the rule.)

### Two hosts, two click paths

Both can be installed at once; they never interfere:

| | tmux | Herdr |
|---|---|---|
| Interception | `MouseDown1Pane` binding in `~/.tmux.conf` | `[[link_handlers]]` in `herdr-plugin.toml` |
| Locating the token | regex-match the bar's line, then walk display columns (CJK wide chars count as 2) | the URL names it outright: `https://ccshift.local/shift/OPUS4.8` |
| Gesture | single click | **Ctrl+click** |
| Injection | C-u clear → type → verify composer → Enter, up to 4 retries | `herdr agent prompt <pane> "/model …"`, text plus Enter atomically |
| Handler | `bin/hud_click.py` | `bin/herdr_shift.py` (reuses the former's token table and snapshot logic) |

Every token on the bar is wrapped in an **OSC 8 hyperlink** (`bin/hud-shift-line.sh`): the label still reads `OPUS`, the URL stays hidden. Claude Code passes OSC 8 through untouched and Herdr honors it. tmux and bare terminals ignore OSC 8 and render just the label, so **the wrapping costs them nothing**.

**Why Herdr requires Ctrl:** the terminal mouse-reporting protocol (SGR mouse) encodes only three modifier bits — Shift, Meta, Control — and has **no bit for Command/Super**. In the byte stream Herdr receives, Cmd+click is indistinguishable from a plain click; Shift is widely reserved for extending selections. Control is what is left. This is a protocol limitation rather than a Herdr design choice, and no config option changes it. Plain clicks must stay available for cursor placement and text selection.

Install on the Herdr side:

```bash
herdr plugin link /path/to/ccshift    # the repo root holds herdr-plugin.toml
```

## How it works

| Layer | Where | Job |
|---|---|---|
| Display | `bin/hud-shift-line.sh` | Renders the bar as an extra statusline line; highlights the current model/effort from the statusline JSON; wraps each token in an OSC 8 hyperlink |
| Click | tmux: `MouseDown1Pane` binding in `~/.tmux.conf`<br>Herdr: `[[link_handlers]]` in `herdr-plugin.toml` | tmux intercepts only lines matching `⇧.*GROK.*XHIGH`; everything else passes through<br>Herdr claims only Ctrl+clicks on `^https://ccshift\.local/shift/`; other clicks and links behave normally |
| Execute | tmux: `bin/hud-click.sh` → `bin/hud_click.py`<br>Herdr: `bin/herdr_shift.py` | Locate the token → snapshot settings → inject the command → restore the snapshot |

Both executors share one token table and one snapshot/restore implementation — `herdr_shift.py` does `from hud_click import ACTIONS, LOCK, read_settings, restore_defaults`, so a model list change is edited in exactly one place.

Restore safety: `settings.json`'s `model` key is read once at session startup and never hot-reloaded (verified on Claude Code 2.1.200), so restoring it after a click never affects running sessions. Concurrent clicks are serialized with `flock` (both paths share the lock file). The `#{socket_path}` passed by the tmux binding means it works on **any tmux server/socket**; on the Herdr side the target pane comes from `focused_pane_id` in `HERDR_PLUGIN_CONTEXT_JSON`, and injection only proceeds when `focused_pane_agent == "claude"`, so a stray click never types into a different agent.

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

**2a. tmux** — add to `~/.tmux.conf` and `tmux source-file` it:

```tmux
set -g mouse on
bind-key -n MouseDown1Pane if-shell -F '#{m/r:⇧.*GROK.*XHIGH,#{mouse_line}}' \
  'run-shell -b "/path/to/ccshift/bin/hud-click.sh #{socket_path} #{pane_id} #{mouse_x} #{mouse_y}"' \
  'select-pane -t = ; send-keys -M'
```

**2b. Herdr** — the repo root already ships `herdr-plugin.toml`, so linking is all it takes:

```bash
herdr plugin link /path/to/ccshift
```

The manifest is one action plus one link handler:

```toml
[[actions]]
id = "shift"
title = "ccshift: switch model/effort"
command = ["python3", "bin/herdr_shift.py"]

[[link_handlers]]
id = "shift-bar"
title = "ccshift: switch model/effort"
pattern = "^https://ccshift\\.local/shift/"   # Rust regex, matched against the clicked URL
action = "shift"
```

Herdr passes the matched URL to the handler as `HERDR_PLUGIN_CLICKED_URL`, alongside `HERDR_PLUGIN_CONTEXT_JSON` (which carries `focused_pane_id` and `focused_pane_agent`).

## Customization

The token table is coupled in **three places** — change one, change all three, or click targeting breaks:

1. `bin/hud-shift-line.sh` — the bar's labels, plus the `case` that maps `$id` to the current tier for highlighting;
2. the `TOKENS` table in `bin/hud_click.py` — label → `/model` / `/effort` argument mapping (**longer tokens must come first**: `OPUS4.8` before `OPUS`, `XHIGH` before `HIGH`);
3. the regex `⇧.*GROK.*XHIGH` in the tmux binding — the signature that identifies the bar's line.

The Herdr path **adds no fourth coupling point**: the URL carries the label itself (`/shift/OPUS4.8`), the handler looks it up in that same `TOKENS` table, and the manifest pattern matches only the prefix.

When the model lineup changes (new tiers, renames), update those three places.

**Getting model ids right** (easy to trip on behind a gateway): with `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`, Claude Code only accepts ids the gateway advertises on `/v1/models`; anything else comes back as `Model '…' not found`. List what is actually available first:

```bash
curl -s "${ANTHROPIC_BASE_URL%/}/v1/models" -H "anthropic-version: 2023-06-01" \
  | python3 -c "import sys,json;[print(m['id']) for m in json.load(sys.stdin)['data']]"
```

Two traps. **An alias replaces the id** — an upstream entry carrying `alias = "opus"` appears as `<lane>/opus`, not `<lane>/claude-opus-4-8`. And **Anthropic's own models should not go through a lane**: gateways like codexwire deliberately drop lane models whose `owned_by` is `anthropic`, since Claude Code already talks to that same subscription directly and routing it through adds a hop while double-spending the quota. So give claude models their **bare** ids (`claude-opus-5[1m]`) and reserve `<lane>/<id>` for models with no direct route.

## Verify / debug

Open a Claude Code session and click a different model token the way your host expects (tmux: single click, Herdr: Ctrl+click): the composer types `/model <x>` and submits, the highlight jumps, and `~/.claude/settings.json` still holds your default. Logs land in `logs/hud-click.log` (tmux) and `logs/herdr-shift.log` (Herdr).

**Clicks do nothing?** Confirm the host first, then work down the layers:

```bash
echo "$TMUX" "$HERDR_ENV"        # both empty = bare terminal, there is no click layer

# --- tmux path ---
tmux show -g mouse                            # expect: mouse on
grep -c 'MouseDown1Pane' ~/.tmux.conf         # expect ≥ 1; run tmux source-file after editing
tail logs/hud-click.log                       # any lines = the click was intercepted

# --- Herdr path ---
herdr plugin list --json | grep ccshift       # should be present and enabled
tail logs/herdr-shift.log                     # any lines = the link handler fired
herdr plugin log list                         # handler exit code / stderr
```

Common symptoms:

- **The bar renders but does not respond.** The display layer is host-independent, so a host switch leaves everything looking normal. Check that the click layer for your current host is installed.
- **Under Herdr, clicking just copies the word.** That is ordinary text selection — Herdr needs **Ctrl+click**, for the reason given under "Two hosts".
- **Injection works but Claude Code says `Model '…' not found`.** The click path is fine; the token table holds a stale id. `ok=True` in the log means the command was submitted. Re-derive the ids as described under Customization.

## License

MIT
