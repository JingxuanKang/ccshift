#!/usr/bin/env python3
"""ccshift link handler for Herdr — turns a Ctrl+click on the statusline shift
bar into a session-scoped model/effort switch.

Herdr invokes this through the `shift-bar` link handler in herdr-plugin.toml
whenever a click lands on a https://ccshift.local/shift/<TOKEN> hyperlink, which
bin/hud-shift-line.sh wraps around every token. Flow:

1. Read the token straight out of HERDR_PLUGIN_CLICKED_URL. No coordinate math:
   the URL already says which token was hit, so the tmux version's column
   walking and CJK width handling are not needed here.
2. Snapshot model/effortLevel in ~/.claude/settings.json (the pre-click values
   = the user's defaults).
3. Submit the /model or /effort command with `herdr agent prompt`, which sends
   text and Enter atomically while honoring the pane's bracketed-paste mode.
   That replaces the tmux version's clear/type/verify/Enter retry loop.
4. Return to Herdr immediately. A detached child waits until Claude Code has
   written the selected value, then restores the two settings keys so the
   switch affects this session only without blocking the UI.

The token table and the settings snapshot/restore logic are imported from
hud_click (the tmux handler) so there is exactly one copy of each.

Concurrent clicks are serialized with the same file lock as the tmux path.
"""
import datetime
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# hud_click has no import-time side effects (main() is guarded), so this is safe
# and keeps TOKENS/settings handling single-sourced.
from hud_click import ACTIONS, LOCK, read_settings, restore_defaults  # noqa: E402

LOG = os.path.join(os.path.dirname(HERE), "logs", "herdr-shift.log")
RESTORE_WAIT_SECONDS = 30.0
RESTORE_POLL_SECONDS = 0.05


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a") as f:
        f.write(f"{ts} {msg}\n")


def wait_and_restore(kind, value, snap_model, snap_effort):
    """Wait for Claude Code's settings write, then restore the saved defaults.

    The Herdr action itself must not sleep: unlike tmux's run-shell -b, plugin
    actions are observed until their command exits. Polling in a detached child
    keeps the click responsive while still restoring only after Claude has
    consumed the slash command.
    """
    key = "model" if kind == "model" else "effortLevel"
    snap_value = snap_model if kind == "model" else snap_effort

    if snap_value == value:
        return "not_needed"

    deadline = time.monotonic() + RESTORE_WAIT_SECONDS
    while time.monotonic() < deadline:
        data = read_settings()
        if data is not None and data.get(key) == value:
            # Let the settings rename settle before replacing the file again.
            time.sleep(RESTORE_POLL_SECONDS)
            restore_defaults(snap_model, snap_effort)
            return "observed"
        time.sleep(RESTORE_POLL_SECONDS)

    # Usually a cancelled large-context confirmation: put back any defaults
    # that did change, but do not keep the plugin lock forever.
    restore_defaults(snap_model, snap_effort)
    return "timeout"


def schedule_restore(kind, value, snap_model, snap_effort, lock_fd, detail):
    """Fork a detached restorer that retains the shared click lock."""
    try:
        pid = os.fork()
    except OSError as exc:
        outcome = wait_and_restore(kind, value, snap_model, snap_effort)
        os.close(lock_fd)
        log(f"{detail} restore={outcome} background=false fork_error={exc!r}")
        return None

    if pid:
        os.close(lock_fd)
        return pid

    try:
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        if devnull > 2:
            os.close(devnull)

        outcome = wait_and_restore(kind, value, snap_model, snap_effort)
        log(f"{detail} restore={outcome} background=true defaults_restored=true")
    except BaseException as exc:
        log(f"{detail} restore=failed background=true error={exc!r}")
    finally:
        os.close(lock_fd)
        os._exit(0)


def main():
    url = os.environ.get("HERDR_PLUGIN_CLICKED_URL", "")
    ctx = {}
    try:
        ctx = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
    except json.JSONDecodeError:
        pass

    pane = ctx.get("focused_pane_id")
    agent = ctx.get("focused_pane_agent")
    status = ctx.get("focused_pane_status")

    # The token is the last URL path segment: .../shift/OPUS4.8
    token = urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
    action = ACTIONS.get(token)

    if action is None:
        log(f"ignored: url={url!r} token={token!r} not in token table")
        return
    if not pane:
        log(f"ignored: url={url!r} no focused_pane_id in context")
        return
    if agent != "claude":
        # The bar only ever renders inside a Claude Code statusline; a click
        # resolving to some other agent means the focus moved. Do not inject.
        log(f"ignored: token={token} focused pane {pane} hosts agent={agent!r}, not claude")
        return

    kind, value = action
    cmd = f"/model {value}" if kind == "model" else f"/effort {value}"

    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    lock_fd = os.open(LOCK, os.O_CREAT | os.O_RDWR)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)  # serialize concurrent clicks

    snap = read_settings() or {}
    snap_model, snap_effort = snap.get("model"), snap.get("effortLevel")

    herdr = os.environ.get("HERDR_BIN_PATH", "herdr")
    # No --wait: a slash command often settles without a visible lifecycle
    # change, which would return agent_prompt_stalled after 5s.
    r = subprocess.run(
        [herdr, "agent", "prompt", pane, cmd],
        capture_output=True, text=True,
    )
    ok = r.returncode == 0
    detail = f"pane={pane} status={status} token={token} {kind}={value}"
    if ok:
        restore_pid = schedule_restore(
            kind, value, snap_model, snap_effort, lock_fd, detail
        )
        log(f"{detail} ok=true dispatched=true restore_pid={restore_pid}")
        return

    restore_defaults(snap_model, snap_effort)
    os.close(lock_fd)
    log(f"{detail} ok=false defaults_restored=true err={r.stderr.strip()!r}")


if __name__ == "__main__":
    main()
