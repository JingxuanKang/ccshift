# model-switch

Claude Code 的终端换挡面板——仿实体换挡杆的可点击 TUI，模型 / effort 切换**只影响当前会话**，新窗口永远从你的默认值启动。

```
 ● M O D E L  S H I F T
       1 HAIKU     3 SONNET-1M     5 FABLE       ╭──────────────────────────────────╮
          ┃             ┃             ┃          │ OPUS                 ▰▰▱▱ MEDIUM │
          ┣━━━━━━━━━━━━━╋━━━━━━━━━━━━━┫          │ 已切换 /effort medium · 默认未动 │
          ┃             ◉             ┃          │ R档: DEFAULT/xhigh · 目标 %0     │
      2 SONNET       4 OPUS       R DEFAULT      ╰──────────────────────────────────╯
   EFFORT   L LOW    M MED    H HIGH    X XHIGH      P 快照      Q QUIT
```

## 用法

```bash
cst    # 在 tmux 里 claude 所在 pane 运行：底部弹出换挡面板
cst    # 在 tmux 外运行：新建 tmux 会话（claude + 面板）并接入
```

- **鼠标点击**任意档位 / effort 拨片换挡（需要 tmux `mouse on`，cst 会自动打开）。
- 键盘：`1-5` 选模型，`l m h x` 选 effort，`r` 回 R 档（默认档位），`p` 刷新快照，`q` 关面板。
- 面板高度可调：`CST_HEIGHT=10 cst`。
- 改档位表：编辑 `bin/model_shift_tui.py` 顶部的 `GATE` / `EFFORTS` 常量。

## 原理

Claude Code 的 `/model <x>` 和 `/effort <x>` 命令切换会话的同时会把选择写进 `~/.claude/settings.json`（`model` / `effortLevel` 两键）——新窗口读它们，于是"继承"。面板每次换挡：

1. 向 claude 所在 pane 注入命令（`tmux send-keys`，带 composer 验证与重试，防止 claude 重渲染时吞字）；
2. 等命令生效后，把 settings.json 的两键**还原成面板启动时的快照**。

净效果 = 当前会话换挡、默认值纹丝不动。还原是安全的：`model` 键只在会话启动时读一次，不热重载（验证于 Claude Code 2.1.200）。

## 注意

- 换挡前 composer 别留没发的草稿——注入会先 `C-u` 清行。
- TUI 开着时若手动改了默认模型（如 `/model` 里按 Enter 想真的换默认），按 `p` 让面板把新默认认作 R 档，否则下次换挡会还原成旧快照。
- 不用 tmux 时的替代：`/model` 选择器里按 **`s`**（"use this session only"）本来就是会话级切换；`claude --model opus --effort high` 启动也是会话级。面板的价值是可点击、一键、且防 `/model` 直接命令写默认。

## 安装 / 卸载

```bash
ln -sf "$PWD/bin/cst" ~/.local/bin/cst   # 安装（仓库自带 symlink 即此命令）
rm ~/.local/bin/cst                       # 卸载；无守护进程、无 hook、无残留
```

依赖：tmux、python3（含 curses，macOS 自带即可）。
