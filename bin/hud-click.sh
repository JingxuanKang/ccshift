#!/bin/bash
# tmux MouseDown1Pane 绑定的入口：hud-click.sh <socket_path> <pane_id> <mouse_x> <mouse_y>
# socket_path 必须由绑定传入（#{socket_path}），保证操作的是触发点击的那个 tmux server。
PROJ="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
mkdir -p "$PROJ/logs"
exec /usr/bin/python3 "$PROJ/bin/hud_click.py" --socket "$1" --pane "$2" --x "$3" --y "$4" \
  >>"$PROJ/logs/hud-click.log" 2>&1
