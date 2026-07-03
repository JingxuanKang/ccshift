# model-switch

Claude Code 的终端换挡面板——仿实体换挡杆的**纯鼠标点击** TUI，模型 / effort 切换**只影响当前会话**，新窗口永远从你的默认值启动。不绑定任何键盘按键。

```
 ●  M O D E L  S H I F T   ↻
       1 HAIKU     3 SONNET-1M     5 FABLE       ╭───────────────────────────────────────────────╮
          ┃             ┃             ┃          │ OPUS                               ▰▰▰▱ HIGH  │
          ┣━━━━━━━━━━━━━╋━━━━━━━━━━━━━┫          │ 已切换 /effort high · 默认未动                │
          ┃             ◉             ┃          │ R档 DEFAULT / xhigh                   目标 %0 │
      2 SONNET       4 OPUS       R DEFAULT      ╰───────────────────────────────────────────────╯
   EFFORT   LOW    MED    HIGH    XHIGH          ─────────────────────────────────────────────────
```

LCD 仪表屏从拨杆右侧一直铺到终端右缘（宽屏不会留白），显示当前档位（紫）、effort 电量表（琥珀）、最近一次换挡结果、R 档内容与目标 pane。

## 用法

```bash
cst    # 在 tmux 里 claude 所在 pane 运行：底部弹出换挡面板
cst    # 在 tmux 外运行：新建 tmux 会话（claude + 面板）并接入
```

全部操作都是点击：

| 点击 | 效果 |
|---|---|
| 档位标签（或滑槽格）| 当前会话切换模型，`◉` 钮移到该档 |
| effort 拨片 LOW / MED / HIGH / XHIGH | 当前会话切换 effort |
| `R DEFAULT` | 回默认档（模型 + effort 一起复位到快照）|
| 左上 `●` | 关闭面板（不影响 claude）|
| 标题旁 `↻` | 把当前 settings 重新认作 R 档快照 |

- 面板高度：`CST_HEIGHT=10 cst`；改档位表：编辑 `bin/model_shift_tui.py` 顶部 `GATE` / `EFFORTS`。
- 需要 tmux `mouse on`（cst 自动打开）。

## 原理

Claude Code 的 `/model <x>` 和 `/effort <x>` 命令切换会话的同时会把选择写进 `~/.claude/settings.json`（`model` / `effortLevel` 两键）——新窗口读它们，于是"继承"。面板每次点击：

1. 向 claude 所在 pane 注入命令（`tmux send-keys`，带 composer 验证与重试：claude 重渲染窗口期会吞字，composer 行 `❯` 后是 U+00A0 需归一化比对）；
2. 命令生效后，把 settings.json 的两键**还原成面板启动时的快照**。

净效果 = 当前会话换挡、默认值纹丝不动。还原是安全的：`model` 键只在会话启动时读一次，不热重载（验证于 Claude Code 2.1.200）。

鼠标可用性：tmux 内 `TERM=screen-256color` 的 terminfo 缺鼠标能力描述，curses 的 `mousemask()` 不一定真的开启终端鼠标上报——面板启动时手动发 `\e[?1000h\e[?1002h` 开启（X10 协议，坐标上限 223 列，所有点击目标都布置在左侧安全区内；右侧 LCD 纯显示）。

## 注意

- 点击换挡会先 `C-u` 清行——claude 输入框里别留没发的草稿。
- 面板开着时若真想改默认（settings 里的 model/effortLevel），改完点 `↻` 刷新快照，否则下次换挡会把旧默认写回去。
- 不用 tmux 时的替代：`/model` 选择器里按 `s`（"use this session only"）是内置的会话级切换；`claude --model opus --effort high` 启动同理。

## 安装 / 卸载

```bash
ln -sf "$PWD/bin/cst" ~/.local/bin/cst   # 安装
rm ~/.local/bin/cst                       # 卸载；无守护进程、无 hook、无残留
```

依赖：tmux、python3（含 curses，macOS 自带即可）。
