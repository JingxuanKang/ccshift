# model-switch

Claude Code statusline 里的**可点击换挡条**：鼠标点状态栏里的字，就地切换当前会话的 model / effort——**只影响当前会话，你的默认配置纹丝不动**，新开的窗口永远从默认档启动。

```
  [Fable 5 ◕ xhigh] │ model-switch git:(master)
  Context ░░░░░░░░░░ 0% │ Usage ██████░░░░ 57% (resets in 3h 32m)
  ⇧ HAIKU  SONNET  SONNET·1M  OPUS  FABLE  DEFAULT │ LOW  MED  HIGH  XHIGH   ← 点这行
```

当前 model / effort 以琥珀色加粗高亮。点 `DEFAULT` 一键回默认档（model + effort 一起复位）。

无守护进程、无轮询、无键盘绑定——只在点击的瞬间运行一次。

## 为什么需要它

Claude Code 内置的 `/model` / `/effort` 切换有个副作用：**选择会被写进 `~/.claude/settings.json`**，于是之后新开的每个会话都继承这次切换。想"这个会话临时降到 haiku 跑杂活，别的会话照常用大模型"，内置菜单做不到一键完成（`/model` 菜单里按 `s` 可以 session-only，但 effort 没有对应操作，且要进菜单翻选项）。

model-switch 把这件事变成一次点击：注入 `/model` / `/effort` 命令让当前会话换挡，然后立刻把 `settings.json` 还原成点击前的快照。净效果 = **会话级换挡，默认档不漂移**。

## 工作原理（三层）

| 层 | 文件 | 职责 |
|---|---|---|
| 显示 | `bin/hud-shift-line.sh` | 作为 statusline 的追加行渲染换挡条；从 statusline JSON（`.model.id` / `.effort.level`）高亮当前档 |
| 点击 | `~/.tmux.conf` 的 `MouseDown1Pane` 绑定 | 点击行匹配 `⇧.*HAIKU.*XHIGH` 才拦截，其余一切点击原样放行 |
| 执行 | `bin/hud-click.sh` → `bin/hud_click.py` | 按显示列定位点到的 token → 快照 settings → 注入命令（清行→输入→capture 验证→回车，最多重试 4 次）→ 还原快照 |

还原的安全性依据：`settings.json` 的 `model` 键只在会话启动时读一次、不热重载（验证于 Claude Code 2.1.200），所以点击后外部还原不影响任何运行中的会话。并发点击用 `flock` 串行化，防止把上一次点击的泄漏值误当默认。

## 依赖

| 依赖 | 必需性 | 用途 |
|---|---|---|
| Claude Code | 必需 | — |
| tmux ≥ 3.1 + `mouse on` | **仅点击功能必需** | 拦截鼠标点击、向 claude 注入命令。绑定用了 `#{m/r:…}` 正则格式（tmux 3.1+） |
| python3 | 仅点击功能必需 | 点击处理器（系统自带即可，无第三方包） |
| jq | 可选 | 高亮当前档；没有 jq 换挡条照常显示，只是不高亮 |
| claude-hud | **不需要** | 它只是常见邻居：换挡条可以追加在任何 statusline 后面，也可以单独用 |

**边界说清楚**：

- **显示不需要 tmux**——裸终端里换挡条照常渲染。
- **点击必需 tmux**——裸终端里鼠标事件直接进 claude 自己，外部程序拦不到，这是硬边界，不是本工具的取舍。不用 tmux 时换挡条退化为"只读仪表"，切模型请用内置 `/model`（菜单里按 `s` 为 session-only）。

## 安装

### 第 0 步：clone

```bash
git clone https://github.com/JingxuanKang/model-switch.git ~/Build/model-switch
```

放哪都行（脚本自身按相对路径定位），下文以 `~/Build/model-switch` 为例，换了路径就同步改后面两处配置。

### 第 1 步：把换挡条接进 statusline

原理都一样：Claude Code 的 statusline 命令从 stdin 收到一段 JSON；把这段 JSON **同时**喂给你原有的 statusline 和 `hud-shift-line.sh`，后者多打印一行。按你的现状三选一：

**A. 已在用 claude-hud**

claude-hud 的 `/claude-hud:setup` 会把 `statusLine.command` 写成直接调用它自己。改成一个 wrapper：先跑 claude-hud，再追加换挡条。建 `~/.claude/statusline.sh`：

```bash
#!/bin/bash
input=$(cat)

# —— claude-hud 本体（自动定位插件缓存里版本号最高的一份）——
NODE=$(command -v node || echo /opt/homebrew/bin/node)
plugin_dir=$(ls -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/plugins/cache/claude-hud/claude-hud/*/ 2>/dev/null \
  | awk -F/ '{ print $(NF-1) "\t" $0 }' \
  | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n | tail -1 | cut -f2-)
printf '%s' "$input" | "$NODE" "${plugin_dir}dist/index.js"

# —— 追加换挡条 ——
printf '%s' "$input" | bash "$HOME/Build/model-switch/bin/hud-shift-line.sh"
```

然后把 `~/.claude/settings.json` 的 statusLine 指向 wrapper：

```json
"statusLine": { "type": "command", "command": "bash ~/.claude/statusline.sh" }
```

⚠️ 之后如果重跑 `/claude-hud:setup` 或 `:configure`，它会把 `statusLine.command` 改回 claude-hud 本体，换挡条消失——重新指回 wrapper 即可。

**B. 在用其它 statusline（自己写的脚本 / 别的工具）**

同样套路：wrapper 里先把 stdin 存进变量、原样跑你现有的 `statusLine.command`，末尾追加：

```bash
printf '%s' "$input" | bash "$HOME/Build/model-switch/bin/hud-shift-line.sh"
```

如果你的 statusline 本来就是自己写的脚本，直接在它末尾加这一行（注意 stdin 只能读一次，要先存变量、两段都从变量喂）。

**C. 什么 statusline 都没有，只要换挡条**

`statusLine.command` 直接指向显示脚本，statusline 就是这一行换挡条：

```json
"statusLine": { "type": "command", "command": "bash /绝对路径/model-switch/bin/hud-shift-line.sh" }
```

改完保存，statusline 每次刷新就能看到换挡条了（此时还只能看，接第 2 步才能点）。

### 第 2 步：接 tmux 点击层

`~/.tmux.conf` 加：

```tmux
set -g mouse on

# model-switch：点击换挡条切模型/effort；其余点击原样放行
bind-key -n MouseDown1Pane if-shell -F '#{m/r:⇧.*HAIKU.*XHIGH,#{mouse_line}}' \
  'run-shell -b "~/Build/model-switch/bin/hud-click.sh #{socket_path} #{pane_id} #{mouse_x} #{mouse_y}"' \
  'select-pane -t = ; send-keys -M'
```

生效：`tmux source-file ~/.tmux.conf`。

要点：

- 绑定只在点击行同时含 `⇧`、`HAIKU`、`XHIGH` 时才拦截，**其余所有点击走原生行为**（选 pane、传鼠标事件给应用），不影响 tmux 日常使用。
- `#{socket_path}` 随点击传入，所以 claude 跑在**任意 tmux 会话 / 任意 socket** 上都能工作，不假定默认 server。
- claude 必须跑在 tmux 里点击才有效；裸终端见上文"边界"。

### 验证

在 tmux 里开一个 claude 会话，等 statusline 出现换挡条，点一个别的模型档位：输入框会自动出现 `/model <x>` 并回车，statusline 高亮跳到新档。此时看 `~/.claude/settings.json` 的 `model` 键——仍是你的默认值。点击日志在 `logs/hud-click.log`。

## 使用须知（费用与缓存）

- **会话中途切模型 = prompt cache 作废**。Anthropic 的 prompt cache 按模型隔离：切到另一个模型后，已有上下文对它是全新输入，下一条回复要整段重读（首字变慢、按无缓存价计费；上下文越长越明显）。**这是 Claude Code / Anthropic API 的行为，与本工具无关**——用内置 `/model` 菜单切完全一样。短时间内切回原模型，若缓存未过期（TTL 约 5 分钟）可再命中。
- **大上下文护栏弹窗**：上下文超过 200k 的会话上切 model / effort 时，Claude Code 会弹 usage-credits 确认弹窗（"Kept model as …"）。本工具**刻意不自动确认**——此时切换意味着缓存作废 + 长上下文计费，该不该切由你手动按，这是护栏不是 bug。
- 点击换挡会先 `C-u` 清空输入行——claude 输入框里别留没发的草稿。

## 自定义

档位表在三处**强耦合**，改任何一处必须同步另两处，否则点击定位错乱：

1. `bin/hud-shift-line.sh` —— 换挡条文案；
2. `bin/hud_click.py` 的 `TOKENS` 表 —— token → `/model` / `/effort` 参数映射（**长 token 必须排在前面**：`SONNET·1M` 先于 `SONNET`，`XHIGH` 先于 `HIGH`）；
3. `~/.tmux.conf` 绑定里的正则 `⇧.*HAIKU.*XHIGH` —— 识别换挡条行的特征。

未来 Claude Code 模型阵容变了（新档位 / 改名），照这三处改即可。

## 卸载

1. statusline wrapper 里删掉追加换挡条那行（或把 `statusLine.command` 改回原值）；
2. `~/.tmux.conf` 删掉那条绑定，`tmux source-file ~/.tmux.conf`；
3. `rm -rf` 本仓库。

无守护进程、无其它残留（只有一个空锁文件 `~/.cache/model-switch.lock` 可顺手删）。

## License

MIT
