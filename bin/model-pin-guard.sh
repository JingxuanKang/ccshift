#!/bin/bash
# 把 ~/.claude/settings.json 里的 model / effortLevel 还原成 pin.json 钉住的默认值。
# 由 launchd WatchPaths 触发（settings.json 每次被改写时运行），也可手动执行。
# 安全性依据：Claude Code 的 model 键只在会话启动时读取一次、不热重载，
# 所以还原文件不会影响任何正在运行的会话，只决定新会话的起点。
PROJ="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"

exec /usr/bin/python3 - "$PROJ/pin.json" "$HOME/.claude/settings.json" "$PROJ/logs/pin-guard.log" <<'PY'
import datetime
import json
import os
import stat
import sys
import tempfile

pin_path, settings_path, log_path = sys.argv[1:4]

try:
    with open(pin_path) as f:
        pin = json.load(f)
    with open(settings_path) as f:
        settings = json.load(f)
except (OSError, json.JSONDecodeError):
    # settings.json 可能正处于写入中途；下一次触发会重试
    sys.exit(0)

changed = {}
for key in ("model", "effortLevel"):
    want = pin.get(key)
    if want is not None and settings.get(key) != want:
        changed[key] = (settings.get(key), want)
        settings[key] = want

if not changed:
    sys.exit(0)

mode = stat.S_IMODE(os.stat(settings_path).st_mode)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(settings_path), prefix=".settings-pin-")
try:
    with os.fdopen(fd, "w") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.chmod(tmp, mode)
    os.replace(tmp, settings_path)
except BaseException:
    os.unlink(tmp)
    raise

os.makedirs(os.path.dirname(log_path), exist_ok=True)
ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
with open(log_path, "a") as f:
    for key, (old, new) in changed.items():
        f.write(f"{ts} restored {key}: {old!r} -> {new!r}\n")
PY
