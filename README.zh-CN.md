# ccshift

[English](README.md) | **中文**

Claude Code statusline 里的**可点击换挡条**：鼠标点状态栏里的字，就地切换**当前会话**的 model / effort——你的默认配置纹丝不动，新开的会话永远从默认档启动。

```
  [Fable 5 ◕ xhigh] │ my-project git:(main)
  Context ░░░░░░░░░░ 0% │ Usage ██████░░░░ 57% (resets in 3h 32m)
  ⇧ GROK  GEMINI  GPT  OPUS  OPUS4.8  FABLE │ LOW  MED  HIGH  XHIGH   ← 点这行
```

当前 model / effort 以琥珀色加粗高亮。

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
| tmux ≥ 3.1 + `mouse on` | **仅点击功能必需** | 绑定用了 `#{m/r:…}` 正则格式（tmux 3.1+）；`mouse on` 安装器会设置。**目前只有 tmux 能提供点击层**，见下方边界 |
| python3 | 仅点击功能必需 | 点击处理器；系统自带即可，无第三方包 |
| jq | 可选 | 高亮当前档；没有 jq 换挡条照常显示，只是不高亮 |
| claude-hud | **不需要** | 只是常见邻居：换挡条可以追加在任何 statusline 后面，也可以单独用 |

**边界说清楚**：换挡条在任何终端、任何 multiplexer 里都能**显示**——它只是 statusline 多打印的一行，跟宿主无关。但**点击**要求宿主满足一个很窄的条件：**能拦截 pane 内的鼠标点击，并把点击坐标交给一个外部 shell 命令**。

目前只有 tmux 有这个口子（`bind-key -n MouseDown1Pane` + `#{mouse_x} #{mouse_y}`）。裸终端里鼠标事件直接进应用，外部拦不到；**其它 multiplexer 即使能拦截鼠标，也普遍不把坐标暴露给外部命令**，同样点不了。

宿主不满足条件时，换挡条**退化为只读仪表**：高亮照常跟随当前档，只是点不动。此时切档用内置 `/model`（菜单里按 `s` = 仅本会话）和 `/effort`。

> 为什么不用键盘绑定兜底？**「不加键盘绑定、不做独立面板」是本项目的设计红线**——ccshift 要的就是「HUD 里点一下」这一个交互，退化时宁可只读，也不长出第二套操作方式。

<details>
<summary>已知宿主兼容性（2026-08 实测）</summary>

| 宿主 | 显示 | 点击 | 说明 |
|---|---|---|---|
| tmux ≥ 3.1 | ✅ | ✅ | 唯一完整支持 |
| tmux < 3.1 | ✅ | ❌ | 缺 `#{m/r:…}` 正则格式 |
| [Herdr](https://herdr.dev) 0.8.0 | ✅ | ❌ | 见下 |
| 裸终端（Ghostty / iTerm / …） | ✅ | ❌ | 鼠标事件直达 claude，外部无法拦截 |

**Herdr 细节**（换 multiplexer 时最常撞的一个）：它的自定义命令 `[[keys.command]]` 只接**键盘**绑定语法（`prefix+x` / `ctrl+letter` / 功能键），没有鼠标事件绑定，也没有把点击坐标传给外部脚本的口子——所以点击层无法移植，这不是配置问题。

不过 Herdr 把本项目**执行层**依赖的两个 tmux 原语都提供了，而且更省事：

| ccshift 用的 tmux | Herdr 等价 |
|---|---|
| `tmux capture-pane -p` | `herdr pane read <pane-id> --source visible` |
| `hud_click.py` 的 `send_command()`（C-u 清行 → 逐字输入 → 验证 composer → 回车 → ≤4 次重试） | `herdr agent prompt <pane-id> "/model opus"` —— 原子提交文本 + Enter，尊重 bracketed-paste |

也就是说：**若 Herdr 将来支持鼠标事件绑定并传坐标，点击层可以直接移植，且执行层能大幅简化**（`hud_click.py` 最脆的重试逻辑可整段删除）。在那之前，Herdr 下按上面的只读仪表用法。
</details>

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
2. `bin/hud_click.py` 的 `TOKENS` 表 —— token → `/model` / `/effort` 参数映射（**长 token 必须排在前面**：`OPUS4.8` 先于 `OPUS`，`XHIGH` 先于 `HIGH`）；
3. tmux 绑定里的正则 `⇧.*GROK.*XHIGH` —— 识别换挡条行的特征。

未来 Claude Code 模型阵容变了（新档位 / 改名），照这三处改即可。

## 验证 / 排障

在 tmux 里开一个 Claude Code 会话，点一个别的模型档位：输入框自动出现 `/model <x>` 并回车，高亮跳到新档，而 `~/.claude/settings.json` 里仍是你的默认值。点击日志在 `logs/hud-click.log`。

**点了没反应？** 先分清是哪一层坏了：

```bash
echo "$TMUX"                                   # 空 = 没跑在 tmux 里 → 点击层不存在，见上方边界表
tmux show -g mouse                             # 应为 mouse on
grep -c 'MouseDown1Pane' ~/.tmux.conf          # 应 ≥ 1；改完 conf 记得 tmux source-file
tail ~/Build/ccshift/logs/hud-click.log        # 有行 = 点击已被拦到，问题在执行层
```

换挡条**还在显示、只是点不动**，通常意味着换了宿主（比如从 tmux 换到 Herdr 或裸终端）——显示层与宿主无关，所以看起来一切正常。这不是 bug，是上方边界表里的已知限制。

## License

MIT
