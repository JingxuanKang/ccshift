#!/bin/bash
# Appended line for the Claude Code statusline: the shift bar (display layer).
# stdin = statusline JSON (optional), used to highlight the current model/effort.
# The click layer is the MouseDown1Pane binding in ~/.tmux.conf -> bin/hud-click.sh
# (clicks anywhere else pass through untouched).
# The line must contain "⇧", "GROK" and "XHIGH" together — the tmux binding uses
# that signature to recognize the shift bar; change the labels and you must update
# the binding regex too. Labels here must stay in sync with TOKENS in hud_click.py.

input=$(cat 2>/dev/null || true)

id=""
eff=""
if [ -n "$input" ] && command -v jq >/dev/null 2>&1; then
  id=$(printf '%s' "$input" | jq -r '.model.id // ""' 2>/dev/null)
  eff=$(printf '%s' "$input" | jq -r '.effort.level // ""' 2>/dev/null)
fi

cur=""
case "$id" in
  *grok*)      cur="GROK" ;;
  *gemini*)    cur="GEMINI" ;;
  *gpt*)       cur="GPT" ;;
  *claude-opus-5*) cur="OPUS" ;;
  *opus*)      cur="OPUS4.8" ;;   # bare *opus* only reaches here after the 4-8 arm above
  *fable*)     cur="FABLE" ;;
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

ESC=$'\033'

# Wrap a token in an OSC 8 hyperlink so Herdr's plugin link handler can claim it.
# Herdr routes Ctrl+click on a matching URL to the plugin instead of the browser;
# the label stays "OPUS", the URL never shows. Harmless in other hosts: terminals
# that ignore OSC 8 just render the label.
tok() {
  local color
  if [ "$1" = "$cur" ] || [ "$1" = "$cure" ]; then color="$HOT"; else color="$DIM"; fi
  printf '%s]8;;https://ccshift.local/shift/%s%s\\%s%s%s%s]8;;%s\\' \
    "$ESC" "$1" "$ESC" "$color" "$1" "$R" "$ESC" "$ESC"
}

printf '%s⇧%s %s  %s  %s  %s  %s  %s %s│%s %s  %s  %s  %s\n' \
  "$MARK" "$R" \
  "$(tok GROK)" "$(tok GEMINI)" "$(tok GPT)" "$(tok OPUS)" "$(tok OPUS4.8)" "$(tok FABLE)" \
  "$SEP" "$R" \
  "$(tok LOW)" "$(tok MED)" "$(tok HIGH)" "$(tok XHIGH)"
