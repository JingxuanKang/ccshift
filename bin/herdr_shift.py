#!/usr/bin/env python3
"""ccshift link handler for Herdr — turns a Ctrl+click on the statusline shift
bar into a session-scoped model/effort switch.

Herdr invokes this through the `shift-bar` link handler in herdr-plugin.toml
whenever a click lands on a https://ccshift.local/shift/<TOKEN> hyperlink, which
bin/hud-shift-line.sh wraps around every token. Flow:

1. Read the token straight out of HERDR_PLUGIN_CLICKED_URL. No coordinate math:
   the URL already says which token was hit, so the tmux version's column
   walking and CJK width handling are not needed here.
2. Fork immediately and let the parent exit. Herdr observes a plugin action
   until its command exits, so anything the parent waits on — the click lock, a
   settings write — is UI latency. The parent's only job is to validate the
   click and hand it off.
3. The child takes the click lock, snapshots the keys a click can move, submits
   the command with `herdr agent prompt` (text and Enter atomically, honoring
   the pane's bracketed-paste mode), waits for Claude Code to write, and
   restores the snapshot so the switch affects this session only.

The token table and the settings snapshot/restore logic are imported from
hud_click (the tmux handler) so there is exactly one copy of each.

Concurrent clicks are serialized with the same file lock as the tmux path. The
lock is taken *inside* the child, so a slow or stuck restore delays the next
switch but never the terminal.
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
from hud_click import (  # noqa: E402
    ACTIONS, LOCK, restore_snapshot, settings_diverged, snapshot_settings,
)

LOG = os.path.join(os.path.dirname(HERE), "logs", "herdr-shift.log")

# Claude Code writes the settings file within a few hundred ms of consuming the
# slash command. The old 30s ceiling existed to cover an effort write that was
# in fact being watched under the wrong key and so never arrived; with
# settings_diverged watching modelSettings too, a wait this long only ever means
# the command did not land, and every extra second is a queued click.
RESTORE_WAIT_SECONDS = 6.0
RESTORE_POLL_SECONDS = 0.05
# A click that cannot get the lock this fast is queued behind a stuck sibling.
LOCK_WAIT_SECONDS = 10.0


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a") as f:
        f.write(f"{ts} {msg}\n")


def acquire_lock():
    """Take the shared click lock, giving up rather than hanging forever.

    Returns (fd, waited_seconds) or (None, waited_seconds) on timeout.
    """
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR)
    start = time.monotonic()
    deadline = start + LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd, time.monotonic() - start
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                return None, time.monotonic() - start
            time.sleep(RESTORE_POLL_SECONDS)


def wait_for_write(snap):
    """Block until Claude Code moves a watched key, or the ceiling is reached."""
    deadline = time.monotonic() + RESTORE_WAIT_SECONDS
    while time.monotonic() < deadline:
        if settings_diverged(snap):
            # Let the settings rename settle before replacing the file again.
            time.sleep(RESTORE_POLL_SECONDS)
            return True
        time.sleep(RESTORE_POLL_SECONDS)
    return False


def do_switch(pane, kind, value, detail):
    """Snapshot, inject, wait, restore. Runs in the detached child under lock."""
    lock_fd, waited = acquire_lock()
    if lock_fd is None:
        log(f"{detail} ok=false reason=lock_timeout waited={waited:.2f}s")
        return
    queued = f" queued={waited:.2f}s" if waited > 0.2 else ""

    try:
        snap = snapshot_settings()
        cmd = f"/model {value}" if kind == "model" else f"/effort {value}"
        herdr = os.environ.get("HERDR_BIN_PATH", "herdr")
        # No --wait: a slash command often settles without a visible lifecycle
        # change, which would return agent_prompt_stalled after 5s.
        t0 = time.monotonic()
        r = subprocess.run(
            [herdr, "agent", "prompt", pane, cmd],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            restore_snapshot(snap)
            log(f"{detail} ok=false{queued} err={r.stderr.strip()!r}")
            return

        observed = wait_for_write(snap)
        wrote = restore_snapshot(snap)
        log(f"{detail} ok=true{queued} observed={observed} "
            f"restored={wrote} took={time.monotonic() - t0:.2f}s")
    finally:
        os.close(lock_fd)


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
    detail = f"pane={pane} status={status} token={token} {kind}={value}"

    # Detach before touching the lock: Herdr watches this process until it
    # exits, so every millisecond past here would be felt as click latency.
    try:
        pid = os.fork()
    except OSError as exc:
        log(f"{detail} fork_error={exc!r} running_inline=true")
        do_switch(pane, kind, value, detail)
        return

    if pid:
        return

    try:
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        if devnull > 2:
            os.close(devnull)
        do_switch(pane, kind, value, detail)
    except BaseException as exc:
        log(f"{detail} ok=false error={exc!r}")
    finally:
        os._exit(0)


if __name__ == "__main__":
    main()
