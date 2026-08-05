#!/usr/bin/env python3
"""ccshift click handler — turns a click on the statusline shift bar into a
session-scoped model/effort switch.

Invoked by the tmux MouseDown1Pane binding (via bin/hud-click.sh) with the
clicked pane and in-pane coordinates. Flow:

1. Capture the pane, take the clicked line, and locate which token was hit
   by display column (CJK wide chars count as 2).
2. Snapshot model/effortLevel in ~/.claude/settings.json (the pre-click
   values = the user's defaults).
3. Inject the /model or /effort command into the pane (Ctrl-U to clear the
   line, type, verify the composer, press Enter; retried a few times).
4. Restore the two settings keys from the snapshot — the switch affects the
   current session only, defaults stay untouched.

Concurrent clicks are serialized with a file lock so a previous click's
leaked values are never mistaken for defaults.
"""
import argparse
import datetime
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata

SETTINGS = os.path.expanduser("~/.claude/settings.json")
LOCK = os.path.expanduser("~/.cache/ccshift.lock")

# Longer tokens first, so OPUS doesn't shadow OPUS4.8, nor HIGH shadow XHIGH
TOKENS = [
    ("OPUS4.8", ("model", "anthropic/claude-opus-4-8[1m]")),
    ("XHIGH", ("effort", "xhigh")),
    ("GROK", ("model", "xai/grok-4.5")),
    ("GEMINI", ("model", "google-antigravity/gemini-3.6-flash[1m]")),
    ("GPT", ("model", "sub2api/gpt-5.6-sol")),
    ("OPUS", ("model", "opus")),
    ("FABLE", ("model", "fable")),
    ("LOW", ("effort", "low")),
    ("MED", ("effort", "medium")),
    ("HIGH", ("effort", "high")),
]
TOKEN_RE = re.compile("|".join(re.escape(t) for t, _ in TOKENS))
ACTIONS = dict(TOKENS)


def cw(ch):
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def token_at(line, col):
    """Which token the click landed on (col is a 0-based display column)."""
    starts = []
    c = 0
    for ch in line:
        starts.append(c)
        c += cw(ch)
    for m in TOKEN_RE.finditer(line):
        s, e = m.span()
        c1 = starts[s]
        c2 = starts[e - 1] + cw(line[e - 1]) - 1
        if c1 <= col <= c2:
            return ACTIONS[m.group(0)]
    return None


TMUX_SOCKET = None


def tmux(*args):
    base = ["tmux"] + (["-S", TMUX_SOCKET] if TMUX_SOCKET else [])
    return subprocess.run([*base, *args], capture_output=True, text=True)


def read_settings():
    try:
        with open(SETTINGS) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def restore_defaults(snap_model, snap_effort):
    data = read_settings()
    if data is None:
        return
    changed = False
    if snap_model is not None and data.get("model") != snap_model:
        data["model"] = snap_model
        changed = True
    if snap_effort is not None and data.get("effortLevel") != snap_effort:
        data["effortLevel"] = snap_effort
        changed = True
    if not changed:
        return
    mode = stat.S_IMODE(os.stat(SETTINGS).st_mode)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(SETTINGS), prefix=".shift-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, SETTINGS)
    except BaseException:
        os.unlink(tmp)
        raise


def composer_line(pane):
    """Current composer line in the target pane (last line starting with ❯;
    the char after ❯ is U+00A0 and must be normalized before comparing)."""
    r = tmux("capture-pane", "-t", pane, "-p")
    if r.returncode != 0:
        return None
    lines = [l.strip().replace("\xa0", " ") for l in r.stdout.splitlines()
             if l.strip().startswith("❯")]
    return lines[-1] if lines else ""


def send_command(pane, text):
    """Inject one command: clear line -> type -> verify composer -> Enter.
    Claude Code re-renders can swallow keystrokes, hence verify + retry."""
    seen = []
    for _ in range(4):
        if tmux("send-keys", "-t", pane, "C-u").returncode != 0:
            return False
        time.sleep(0.2)
        tmux("send-keys", "-t", pane, "-l", "--", text)
        time.sleep(0.6)
        line = composer_line(pane)
        if line is None:
            return False
        if line == f"❯ {text}":
            tmux("send-keys", "-t", pane, "Enter")
            time.sleep(1.5)
            return True
        seen.append(line)
        time.sleep(0.6)
    log(f"send_command failed text={text!r} composer_seen={seen!r}")
    return False


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} {msg}", flush=True)


def main():
    global TMUX_SOCKET
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", default=None, help="socket_path of the tmux server that saw the click")
    ap.add_argument("--pane", required=True)
    ap.add_argument("--x", type=int, required=True)
    ap.add_argument("--y", type=int, required=True)
    args = ap.parse_args()
    TMUX_SOCKET = args.socket

    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    lock_fd = os.open(LOCK, os.O_CREAT | os.O_RDWR)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)  # serialize concurrent clicks

    r = tmux("capture-pane", "-t", args.pane, "-p")
    if r.returncode != 0:
        return
    lines = r.stdout.splitlines()
    if args.y >= len(lines):
        return
    action = token_at(lines[args.y], args.x)
    if action is None:
        return
    kind, value = action

    snap = read_settings() or {}
    snap_model, snap_effort = snap.get("model"), snap.get("effortLevel")

    cmds = [f"/model {value}"] if kind == "model" else [f"/effort {value}"]

    ok = all(send_command(args.pane, c) for c in cmds)
    restore_defaults(snap_model, snap_effort)
    log(f"pane={args.pane} click=({args.x},{args.y}) {kind}={value} "
        f"cmds={cmds} ok={ok} defaults_restored=true")


if __name__ == "__main__":
    main()
