#!/bin/bash
# Appended line for the Claude Code statusline: the shift bar (display layer).
# stdin = statusline JSON (optional), used to highlight the current model/effort.
# The click layer is the MouseDown1Pane binding in ~/.tmux.conf -> bin/hud-click.sh
# (clicks anywhere else pass through untouched).
# The line must contain "⇧", "GROK" and "XHIGH" together — the tmux binding uses
# that signature to recognize the shift bar; change the labels and you must update
# the binding regex too.

input=$(cat 2>/dev/null || true)

id=""
eff=""
if [ -n "$input" ] && command -v jq >/dev/null 2>&1; then
  id=$(printf '%s' "$input" | jq -r '.model.id // ""' 2>/dev/null)
  eff=$(printf '%s' "$input" | jq -r '.effort.level // ""' 2>/dev/null)
fi

cur=""
case "$id" in
  *grok*)          cur="GROK" ;;
  *sonnet*"[1m]"*) cur="SONNET·1M" ;;
  *sonnet*)        cur="SONNET" ;;
  *opus*)          cur="OPUS" ;;
  *fable*)         cur="FABLE" ;;
esac
cure=""
case "$eff" in
  low)    cure="LOW" ;;
  medium) cure="MED" ;;
  high)   cure="HIGH" ;;
  xhigh)  cure="XHIGH" ;;
esac

DIM=$'\033[38;5;245m'
HOT=$'\033[1;38;5;214m'
MARK=$'\033[38;5;214m'
SEP=$'\033[38;5;240m'
R=$'\033[0m'

tok() {
  if [ "$1" = "$cur" ] || [ "$1" = "$cure" ]; then
    printf '%s%s%s' "$HOT" "$1" "$R"
  else
    printf '%s%s%s' "$DIM" "$1" "$R"
  fi
}

printf '%s⇧%s %s  %s  %s  %s  %s  %s %s│%s %s  %s  %s  %s\n' \
  "$MARK" "$R" \
  "$(tok GROK)" "$(tok SONNET)" "$(tok SONNET·1M)" "$(tok OPUS)" "$(tok FABLE)" "$(tok DEFAULT)" \
  "$SEP" "$R" \
  "$(tok LOW)" "$(tok MED)" "$(tok HIGH)" "$(tok XHIGH)"
