#!/bin/bash
# 安装 model-switch：symlink cs 到 ~/.local/bin，生成并加载 launchd 守护。
# 可重复执行（幂等）。卸载见 README。
set -euo pipefail

PROJ="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LABEL="uk.jingxuan.model-pin-guard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$PROJ/logs" "$HOME/.local/bin" "$HOME/Library/LaunchAgents"
chmod +x "$PROJ/bin/cs" "$PROJ/bin/model-pin-guard.sh"

ln -sf "$PROJ/bin/cs" "$HOME/.local/bin/cs"

sed -e "s|__PROJ__|$PROJ|g" -e "s|__HOME__|$HOME|g" \
  "$PROJ/launchd/$LABEL.plist.template" > "$PLIST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "✓ cs        -> $HOME/.local/bin/cs"
echo "✓ launchd   -> ${LABEL}（监视 ~/.claude/settings.json）"
"$PROJ/bin/cs" status
