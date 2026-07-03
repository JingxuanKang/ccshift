#!/usr/bin/env python3
"""model-switch 点击处理器——把 HUD 换挡条上的点击变成会话级换挡。

由 ~/.tmux.conf 的 MouseDown1Pane 绑定调用（经 bin/hud-click.sh），参数是
点击的 pane 与 pane 内坐标。流程：

1. capture 该 pane，取点击行文字，按显示列（CJK 宽字符=2）定位点到了哪个 token；
2. 快照 ~/.claude/settings.json 的 model/effortLevel（点击前的值 = 用户默认）；
3. 向 pane 注入 /model 或 /effort 命令（C-u 清行 → 输入 → 验证 composer → 回车，重试 3 次）；
4. 把 settings.json 两键还原成快照 → 切换只影响当前会话，默认不动。

并发点击用文件锁串行化，避免把上一次点击的泄漏值误当默认快照。
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
LOCK = os.path.expanduser("~/.cache/model-switch.lock")

# 长 token 在前，避免 SONNET 抢了 SONNET·1M、HIGH 抢了 XHIGH
TOKENS = [
    ("SONNET·1M", ("model", "sonnet[1m]")),
    ("XHIGH", ("effort", "xhigh")),
    ("HAIKU", ("model", "haiku")),
    ("SONNET", ("model", "sonnet")),
    ("OPUS", ("model", "opus")),
    ("FABLE", ("model", "fable")),
    ("DEFAULT", ("reset", None)),
    ("LOW", ("effort", "low")),
    ("MED", ("effort", "medium")),
    ("HIGH", ("effort", "high")),
]
TOKEN_RE = re.compile("|".join(re.escape(t) for t, _ in TOKENS))
ACTIONS = dict(TOKENS)


def cw(ch):
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def token_at(line, col):
    """点击列落在哪个 token 上（col 为显示列，0-based）。"""
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
    """目标 pane 里当前 composer 行（最后一个 ❯ 开头的行；❯ 后是 U+00A0 需归一化）。"""
    r = tmux("capture-pane", "-t", pane, "-p")
    if r.returncode != 0:
        return None
    lines = [l.strip().replace("\xa0", " ") for l in r.stdout.splitlines()
             if l.strip().startswith("❯")]
    return lines[-1] if lines else ""


def send_command(pane, text):
    """注入一条命令：清行 → 输入 → 验证 composer → 回车（claude 重渲染会吞字，必须验证重试）。"""
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
    log(f"send_command 失败 text={text!r} 每次验证看到的 composer={seen!r}")
    return False


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} {msg}", flush=True)


def main():
    global TMUX_SOCKET
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", default=None, help="触发点击的 tmux server 的 socket_path")
    ap.add_argument("--pane", required=True)
    ap.add_argument("--x", type=int, required=True)
    ap.add_argument("--y", type=int, required=True)
    args = ap.parse_args()
    TMUX_SOCKET = args.socket

    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    lock_fd = os.open(LOCK, os.O_CREAT | os.O_RDWR)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)  # 串行化并发点击

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

    if kind == "model":
        cmds = [f"/model {value}"]
    elif kind == "effort":
        cmds = [f"/effort {value}"]
    else:  # reset → 回默认档
        cmds = []
        if snap_model:
            cmds.append(f"/model {snap_model}")
        if snap_effort:
            cmds.append(f"/effort {snap_effort}")

    ok = all(send_command(args.pane, c) for c in cmds)
    restore_defaults(snap_model, snap_effort)
    log(f"pane={args.pane} click=({args.x},{args.y}) {kind}={value} "
        f"cmds={cmds} ok={ok} 默认已还原")


if __name__ == "__main__":
    main()
