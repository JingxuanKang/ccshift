#!/bin/bash
# Entry point for the tmux MouseDown1Pane binding:
#   hud-click.sh <socket_path> <pane_id> <mouse_x> <mouse_y>
# socket_path must come from the binding (#{socket_path}) so we act on the
# exact tmux server that saw the click.
PROJ="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
mkdir -p "$PROJ/logs"
exec /usr/bin/python3 "$PROJ/bin/hud_click.py" --socket "$1" --pane "$2" --x "$3" --y "$4" \
  >>"$PROJ/logs/hud-click.log" 2>&1
