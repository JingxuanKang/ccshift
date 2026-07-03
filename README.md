# model-switch

Claude Code HUD（statusline）里的**可点击换挡条**：点状态栏里的字换模型 / effort，只影响当前会话，新窗口永远从你的默认值启动。不占独立面板、不需要额外命令、不绑定任何键盘按键。

```
    MacBook
  [Fable 5 ◕ xhigh] │ model-switch git:(master*)
  Context ░░░░░░░░░░ 0% │ Usage ██████░░░░ 57% (resets in 3h 32m)
  ⇧ HAIKU  SONNET  SONNET·1M  OPUS  FABLE  DEFAULT │ LOW  MED  HIGH  XHIGH   ← 点这行
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

换挡条是 HUD 的一行，跟着 statusline 一起刷新；当前 model / effort 以琥珀色加粗高亮（读 statusline JSON 的 `.model.id` / `.effort.level`）。点 `DEFAULT` 回默认档（model + effort 一起复位）。

## 三层架构

| 层 | 位置 | 职责 |
|---|---|---|
| 显示 | `bin/hud-shift-line.sh`，由 `~/.claude/hud-with-host.sh` 末尾调用 | 渲染换挡条 + 高亮当前档 |
| 点击 | `~/.tmux.conf` 的 `MouseDown1Pane` 绑定 | 点击行匹配 `⇧.*HAIKU.*XHIGH` 才拦截，其余点击原样放行（`select-pane` + `send-keys -M`）|
| 执行 | `bin/hud-click.sh` → `bin/hud_click.py` | 按显示列定位 token → 注入 `/model` / `/effort`（验证+重试）→ 还原 settings 快照 |

无守护进程、无轮询——只在点击瞬间运行一次。

## 原理

Claude Code 的 `/model <x>` 和 `/effort <x>` 切换会话的同时会把选择写进 `~/.claude/settings.json`（`model` / `effortLevel`）——新窗口读它们，于是"继承"。每次点击：

1. 快照 settings 两键（点击前的值 = 你的默认；并发点击用 `flock` 串行化，防止把上一次的泄漏误当默认）；
2. `tmux send-keys` 注入命令：`C-u` 清行 → 输入 → capture 验证 composer（claude 重渲染会吞字；composer 行 `❯` 后是 U+00A0 需归一化）→ 回车，最多重试 4 次；
3. 把 settings 两键还原成快照。

净效果 = 当前会话换挡、默认纹丝不动。还原安全性：`model` 键只在会话启动时读一次、不热重载（验证于 Claude Code 2.1.200）。

## 前提与集成点

前提：claude 跑在 tmux 里（任意会话 / 任意 socket——绑定把 `#{socket_path}` 传给处理器）、`mouse on`（已有）。裸终端里点击事件只进 claude 自己，外部拦不到，这是硬边界；届时用内置的 `/model` → 按 `s`（session only）。

安装即两处（本机已接好；换机照抄）：

`~/.claude/hud-with-host.sh` 末尾：

```bash
# model-switch 换挡条（可点击，需 claude 跑在 tmux 里；真源与说明见 ~/Build/model-switch）
[ -x "$HOME/Build/model-switch/bin/hud-shift-line.sh" ] && \
  printf '%s' "$input" | bash "$HOME/Build/model-switch/bin/hud-shift-line.sh"
```

`~/.tmux.conf`：

```tmux
# === model-switch：点击 claude HUD 换挡条切模型/effort（会话级，不改默认；真源见 ~/Build/model-switch）===
bind-key -n MouseDown1Pane if-shell -F '#{m/r:⇧.*HAIKU.*XHIGH,#{mouse_line}}' 'run-shell -b "~/Build/model-switch/bin/hud-click.sh #{socket_path} #{pane_id} #{mouse_x} #{mouse_y}"' 'select-pane -t = ; send-keys -M'
```

卸载 = 删掉这两处，`tmux source-file ~/.tmux.conf`。无其它残留。

## 注意

- 点击换挡会先 `C-u` 清行——claude 输入框里别留没发的草稿。
- 换挡条文案（token 与 `⇧` 标记）和 tmux 绑定的正则、`hud_click.py` 的 `TOKENS` 三处耦合，改一处要同步另两处。
- 刚切完模型立刻再点，注入偶尔要多重试一两轮（claude 重渲染窗口），点了没反应等一两秒即可；日志在 `logs/hud-click.log`。
- **上下文超过 200k 的会话**（1M 模型下 Context >20%）里切 1M 模型 / effort，Claude Code 会弹 usage-credits 确认框，取消即显示 "Kept model as …"。处理器对此有兜底：没看到结果行时补按一次 Enter 选默认项并记日志（空输入框上补按是无操作，零风险）。普通会话（<200k）完全无感。
- 想换默认档：直接改 `~/.claude/settings.json` 的 `model`/`effortLevel`（或 `/model` 里按 Enter）——换挡条的 DEFAULT 永远指向点击瞬间 settings 里的值，无需刷新任何快照。

依赖：tmux ≥3.1（用到 `m/r:` 正则与 `mouse_line`）、jq、python3（macOS 自带）。
