#!/bin/bash
# claude statusline 追加行：换挡条（显示层）。
# stdin = claude statusline JSON（可选），用于高亮当前 model / effort。
# 点击层在 ~/.tmux.conf 的 MouseDown1Pane 绑定 → bin/hud-click.sh（点其它区域原样放行）。
# 行内必须同时含 "⇧"、"HAIKU"、"XHIGH"——tmux 绑定用这个特征识别换挡条行，改文案要同步改绑定正则。

input=$(cat 2>/dev/null || true)

id=""
eff=""
if [ -n "$input" ] && command -v jq >/dev/null 2>&1; then
  id=$(printf '%s' "$input" | jq -r '.model.id // ""' 2>/dev/null)
  eff=$(printf '%s' "$input" | jq -r '.effort.level // ""' 2>/dev/null)
fi

cur=""
case "$id" in
  *haiku*)         cur="HAIKU" ;;
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
  "$(tok HAIKU)" "$(tok SONNET)" "$(tok SONNET·1M)" "$(tok OPUS)" "$(tok FABLE)" "$(tok DEFAULT)" \
  "$SEP" "$R" \
  "$(tok LOW)" "$(tok MED)" "$(tok HIGH)" "$(tok XHIGH)"
