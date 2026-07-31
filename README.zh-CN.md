# ccshift

[English](README.md) | **中文**

Claude Code statusline 里的**可点击换挡条**：鼠标点状态栏里的字，就地切换**当前会话**的 model / effort——你的默认配置纹丝不动，新开的会话永远从默认档启动。

```
  [Fable 5 ◕ xhigh] │ my-project git:(main)
  Context ░░░░░░░░░░ 0% │ Usage ██████░░░░ 57% (resets in 3h 32m)
  ⇧ GROK  SONNET  SONNET·1M  OPUS  FABLE  DEFAULT │ LOW  MED  HIGH  XHIGH   ← 点这行
```

当前 model / effort 以琥珀色加粗高亮。点 `DEFAULT` 一键回默认档（model + effort 一起复位）。

无守护进程、无轮询、无键盘绑定——只在点击的瞬间运行一次。

## 为什么需要它

Claude Code 内置的 `/model` / `/effort` 有个副作用：**选择会被写进 `~/.claude/settings.json`**，之后新开的每个会话都继承这次切换。想"这个会话临时降到 haiku 跑杂活，别的会话照常用大模型"，内置菜单做不到一键完成（`/model` 菜单里按 `s` 可以 session-only，但 effort 没有对应操作）。

ccshift 把这件事变成一次点击：注入 `/model` / `/effort` 命令让当前会话换挡，然后立刻把 `settings.json` 还原成点击前的快照。净效果 = **会话级换挡，默认档不漂移**。

## 安装

```bash
git clone https://github.com/JingxuanKang/ccshift.git
cd ccshift && ./install.sh
```

安装器只做两件事，都可逆：

1. **statusline** —— 把 `~/.claude/settings.json` 的 `statusLine.command` 指向一个生成的 wrapper。**已经在用别的 statusline（claude-hud / 自定义脚本 / 任何东西）会被自动保留**：wrapper 先跑它，再追加换挡条这一行。
2. **tmux** —— 往 `~/.tmux.conf` 写一个带标记的配置块（点击绑定），并 reload 运行中的 server。

随时可以重跑 `./install.sh`（`git pull` 之后、挪动仓库位置之后）——它是幂等的。卸载：

```bash
./install.sh --uninstall
```

> ⚠️ claude-hud 用户：重跑 `/claude-hud:setup` / `:configure` 会覆盖 `statusLine.command`，换挡条会消失——再跑一次 `./install.sh` 即可，它会把新的 claude-hud 命令重新包进 wrapper。

### 依赖

| 依赖 | 必需性 | 说明 |
|---|---|---|
| Claude Code | 必需 | — |
| tmux ≥ 3.1 + `mouse on` | **仅点击功能必需** | 绑定用了 `#{m/r:…}` 正则格式（tmux 3.1+）；`mouse on` 安装器会设置 |
| python3 | 仅点击功能必需 | 点击处理器；系统自带即可，无第三方包 |
| jq | 可选 | 高亮当前档；没有 jq 换挡条照常显示，只是不高亮 |
| claude-hud | **不需要** | 只是常见邻居：换挡条可以追加在任何 statusline 后面，也可以单独用 |

**边界说清楚**：换挡条在任何终端里都能**显示**，但**点击**必需 Claude Code 跑在 tmux 里——裸终端里鼠标事件直接进应用，外部程序拦不到，这是硬边界。不用 tmux 时换挡条退化为只读仪表，切模型请用内置 `/model`（菜单里按 `s` 为 session-only）。

## 工作原理（三层）

| 层 | 位置 | 职责 |
|---|---|---|
| 显示 | `bin/hud-shift-line.sh` | 作为 statusline 的追加行渲染换挡条；从 statusline JSON 高亮当前档 |
| 点击 | `~/.tmux.conf` 的 `MouseDown1Pane` 绑定 | 只拦截匹配 `⇧.*GROK.*XHIGH` 的行，其余一切点击原样放行 |
| 执行 | `bin/hud-click.sh` → `bin/hud_click.py` | 按显示列定位 token → 快照 settings → 注入命令（清行→输入→验证 composer→回车，带重试）→ 还原快照 |

还原的安全性依据：`settings.json` 的 `model` 键只在会话启动时读一次、不热重载（验证于 Claude Code 2.1.200），点击后还原不影响任何运行中的会话。并发点击用 `flock` 串行化。绑定传入 `#{socket_path}`，所以在**任意 tmux server / socket** 上都能工作。

## 使用须知（费用与缓存）

**会话中途切档 = prompt cache 作废**。Anthropic 的 prompt cache 按前缀分三层（`tools → system → messages`），失效是分层的：

| 改动 | tools 缓存 | system 缓存 | messages 缓存 |
|---|---|---|---|
| 换模型 / 改工具列表 | ❌ | ❌ | ❌ |
| 改 system prompt | 保留 | ❌ | ❌ |
| 改 thinking / effort 这类推理参数 | 保留 | 保留 | ❌ |

长会话里绝大部分 token 都堆在 messages（对话历史 + 工具输出），所以**换模型和换 effort 的实际效果都 ≈ 整段上下文按无缓存价重读一遍**（首字变慢；上下文越长越贵）。**这是 Claude Code / Anthropic API 的行为，与本工具无关**——用内置 `/model` / `/effort` 切完全一样。短时间内切回原模型，若缓存未过期（TTL 约 5 分钟）可再命中。

其余两点：

- **大上下文护栏弹窗**：上下文超过 200k 的会话上切 model / effort 时，Claude Code 会弹 usage-credits 确认弹窗（确认才切；取消则显示 "Kept model as … / Kept effort level as …"）。本工具**刻意不自动确认**——此时切换意味着缓存作废 + 长上下文计费，该不该切由你手动按，这是护栏不是 bug。
- 点击换挡会先 `C-u` 清空输入行——claude 输入框里别留没发的草稿。

## 手动安装

不想跑脚本的话，自己接两处集成点：

**1. statusline** —— Claude Code 会把一段 JSON 从 stdin 喂给 `statusLine.command`。把这段 JSON 同时喂给你原有的 statusline 和 `bin/hud-shift-line.sh`（它多打印一行）。可以直接指向脚本（只要换挡条）：

```json
"statusLine": { "type": "command", "command": "bash /路径/ccshift/bin/hud-shift-line.sh" }
```

或在你自己的 wrapper 脚本末尾追加（注意 stdin 只能读一次，先存进变量）：

```bash
printf '%s' "$input" | bash /路径/ccshift/bin/hud-shift-line.sh
```

**2. tmux** —— `~/.tmux.conf` 加入后 `tmux source-file` 生效：

```tmux
set -g mouse on
bind-key -n MouseDown1Pane if-shell -F '#{m/r:⇧.*GROK.*XHIGH,#{mouse_line}}' \
  'run-shell -b "/路径/ccshift/bin/hud-click.sh #{socket_path} #{pane_id} #{mouse_x} #{mouse_y}"' \
  'select-pane -t = ; send-keys -M'
```

## 自定义

档位表在三处**强耦合**，改任何一处必须同步另两处，否则点击定位错乱：

1. `bin/hud-shift-line.sh` —— 换挡条文案；
2. `bin/hud_click.py` 的 `TOKENS` 表 —— token → `/model` / `/effort` 参数映射（**长 token 必须排在前面**：`SONNET·1M` 先于 `SONNET`，`XHIGH` 先于 `HIGH`）；
3. tmux 绑定里的正则 `⇧.*GROK.*XHIGH` —— 识别换挡条行的特征。

未来 Claude Code 模型阵容变了（新档位 / 改名），照这三处改即可。

## 验证 / 排障

在 tmux 里开一个 Claude Code 会话，点一个别的模型档位：输入框自动出现 `/model <x>` 并回车，高亮跳到新档，而 `~/.claude/settings.json` 里仍是你的默认值。点击日志在 `logs/hud-click.log`。

## License

MIT
