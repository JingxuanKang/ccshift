# ccshift

[English](README.md) | **中文**

Claude Code statusline 里的**可点击换挡条**：鼠标点状态栏里的字，就地切换**当前会话**的 model / effort——你的默认配置纹丝不动，新开的会话永远从默认档启动。

```
  [Fable 5 ◕ xhigh] │ my-project git:(main)
  Context ░░░░░░░░░░ 0% │ Usage ██████░░░░ 57% (resets in 3h 32m)
  ⇧ OPUS  OPUS4.8  FABLE │ LOW  MED  HIGH  XHIGH   ← 点这行
```

当前 model / effort 以琥珀色加粗高亮。**tmux 下单击，Herdr 下 Ctrl+click**（原因见下）。

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

跑在 **Herdr** 里的话，点击层改为装插件（安装器暂不代劳）：

```bash
herdr plugin link /path/to/ccshift    # 项目根的 herdr-plugin.toml
```

两条路互不冲突，可以同时装着——用哪个宿主就走哪条。

随时可以重跑 `./install.sh`（`git pull` 之后、挪动仓库位置之后）——它是幂等的。卸载：

```bash
./install.sh --uninstall
```

> ⚠️ claude-hud 用户：重跑 `/claude-hud:setup` / `:configure` 会覆盖 `statusLine.command`，换挡条会消失——再跑一次 `./install.sh` 即可，它会把新的 claude-hud 命令重新包进 wrapper。

### 依赖

| 依赖 | 必需性 | 说明 |
|---|---|---|
| Claude Code | 必需 | — |
| tmux ≥ 3.1 + `mouse on` | tmux 宿主下点击必需 | 绑定用了 `#{m/r:…}` 正则格式（tmux 3.1+）；`mouse on` 安装器会设置 |
| [Herdr](https://herdr.dev) ≥ 0.8.0 | Herdr 宿主下点击必需 | 用插件的 link handler，见下方「两种宿主」 |
| python3 | 仅点击功能必需 | 两种宿主的处理器都是它；系统自带即可，无第三方包 |
| jq | 可选 | 高亮当前档；没有 jq 换挡条照常显示，只是不高亮 |
| claude-hud | **不需要** | 只是常见邻居：换挡条可以追加在任何 statusline 后面，也可以单独用 |

**边界说清楚**：换挡条在任何终端、任何 multiplexer 里都能**显示**——它只是 statusline 多打印的一行，跟宿主无关。但**点击**需要宿主把点击事件交出来，各家给的口子不一样：

| 宿主 | 显示 | 点击 | 怎么点 |
|---|---|---|---|
| tmux ≥ 3.1 | ✅ | ✅ | **单击** |
| [Herdr](https://herdr.dev) ≥ 0.8.0 | ✅ | ✅ | **Ctrl+click** |
| tmux < 3.1 | ✅ | ❌ | 缺 `#{m/r:…}` 正则格式 |
| 裸终端（Ghostty / iTerm / …） | ✅ | ❌ | 鼠标事件直达 claude，外部无法拦截 |

宿主不在支持列表时，换挡条**退化为只读仪表**：高亮照常跟随当前档，只是点不动。此时切档用内置 `/model`（菜单里按 `s` = 仅本会话）和 `/effort`。

> 为什么不用键盘绑定兜底？**「不加键盘绑定、不做独立面板」是本项目的设计红线**——ccshift 要的就是「HUD 里点一下」这一个交互，退化时宁可只读，也不长出第二套操作方式。（Ctrl+click 仍是点击，不算破例。）

### 两种宿主，两条点击路径

两条路可以**同时装**，各走各的，互不干扰：

| | tmux | Herdr |
|---|---|---|
| 拦截方式 | `~/.tmux.conf` 的 `MouseDown1Pane` 绑定 | `herdr-plugin.toml` 的 `[[link_handlers]]` |
| 怎么识别点到哪 | 正则匹配换挡条行 + 按显示列反查 token（CJK 宽字符算 2 列） | URL 直接编码档位：`https://ccshift.local/shift/OPUS4.8` |
| 触发操作 | 单击 | **Ctrl+click** |
| 注入方式 | C-u 清行 → 逐字输入 → capture 验证 composer → 回车，≤4 次重试 | `herdr agent prompt <pane> "/model …"`，原子提交文本 + Enter |
| 处理器 | `bin/hud_click.py` | `bin/herdr_shift.py`（复用前者的档位表与快照逻辑） |

换挡条的每个 token 都用 **OSC 8 超链接**包着（`bin/hud-shift-line.sh`），标签仍显示 `OPUS`，URL 藏在背后。Claude Code 会原样透传 OSC 8，Herdr 认得。tmux 和裸终端不处理 OSC 8，只渲染标签，所以**这层包装对它们完全无害**。

**为什么 Herdr 必须按 Ctrl**：终端上报鼠标事件的协议（SGR mouse）里修饰键只有 Shift / Meta / Control 三个 bit，**没有 Command/Super 的位置**。Herdr 收到的字节流中 Cmd+click 和普通单击完全相同，无法区分；Shift 被终端普遍占用于扩展选区。所以 Control 是唯一可用的修饰键，这是协议限制不是 Herdr 的选择，也没有配置项可改。普通单击必须留给光标定位和文本选择。

Herdr 侧安装：

```bash
herdr plugin link /path/to/ccshift    # 项目根有 herdr-plugin.toml
```

## 工作原理（三层）

| 层 | 位置 | 职责 |
|---|---|---|
| 显示 | `bin/hud-shift-line.sh` | 作为 statusline 的追加行渲染换挡条；从 statusline JSON 高亮当前档；每个 token 包一层 OSC 8 超链接 |
| 点击 | tmux：`~/.tmux.conf` 的 `MouseDown1Pane` 绑定<br>Herdr：`herdr-plugin.toml` 的 `[[link_handlers]]` | tmux 只拦截匹配 `⇧.*OPUS.*XHIGH` 的行，其余点击原样放行<br>Herdr 只认 `^https://ccshift\.local/shift/` 的 Ctrl+click，其余点击与链接照常 |
| 执行 | tmux：`bin/hud-click.sh` → `bin/hud_click.py`<br>Herdr：`bin/herdr_shift.py` | 定位 token → 快照 settings → 注入命令 → 还原快照 |

两个执行器共享同一份档位表和快照/还原逻辑——`herdr_shift.py` 直接 `from hud_click import ACTIONS, LOCK, read_settings, restore_defaults`，所以档位只维护一处。

还原的安全性依据：`settings.json` 的 `model` 键只在会话启动时读一次、不热重载（验证于 Claude Code 2.1.200），点击后还原不影响任何运行中的会话。并发点击用同一个 `flock` 串行化（两条路径共用锁文件）。tmux 绑定传入 `#{socket_path}`，所以在**任意 tmux server / socket** 上都能工作；Herdr 侧的目标 pane 由 `HERDR_PLUGIN_CONTEXT_JSON` 的 `focused_pane_id` 给出，并校验 `focused_pane_agent == "claude"` 后才注入，避免打字到别的 agent 里。

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

**2a. tmux** —— `~/.tmux.conf` 加入后 `tmux source-file` 生效：

```tmux
set -g mouse on
bind-key -n MouseDown1Pane if-shell -F '#{m/r:⇧.*OPUS.*XHIGH,#{mouse_line}}' \
  'run-shell -b "/路径/ccshift/bin/hud-click.sh #{socket_path} #{pane_id} #{mouse_x} #{mouse_y}"' \
  'select-pane -t = ; send-keys -M'
```

**2b. Herdr** —— 项目根已带 `herdr-plugin.toml`，直接 link 即可：

```bash
herdr plugin link /路径/ccshift
```

manifest 的内容就是一个 action 加一个 link handler：

```toml
[[actions]]
id = "shift"
title = "ccshift: switch model/effort"
command = ["python3", "bin/herdr_shift.py"]

[[link_handlers]]
id = "shift-bar"
title = "ccshift: switch model/effort"
pattern = "^https://ccshift\\.local/shift/"   # Rust 正则,匹配被点的 URL
action = "shift"
```

Herdr 把 Ctrl+click 命中的 URL 通过 `HERDR_PLUGIN_CLICKED_URL` 传给处理器，连同 `HERDR_PLUGIN_CONTEXT_JSON`（内含 `focused_pane_id` / `focused_pane_agent`）。

## 自定义

档位表在三处**强耦合**，改任何一处必须同步另两处，否则点击定位错乱：

1. `bin/hud-shift-line.sh` —— 换挡条文案，以及 `$id` → 当前档的 `case` 匹配（高亮用）；
2. `bin/hud_click.py` 的 `TOKENS` 表 —— token → `/model` / `/effort` 参数映射（**长 token 必须排在前面**：`OPUS4.8` 先于 `OPUS`，`XHIGH` 先于 `HIGH`）；
3. tmux 绑定里的正则 `⇧.*OPUS.*XHIGH` —— 识别换挡条行的特征。

Herdr 那条路**不增加耦合点**：URL 里带的就是 token 文案本身（`/shift/OPUS4.8`），处理器查的是同一张 `TOKENS` 表，`herdr-plugin.toml` 的 pattern 只匹配前缀不关心具体档位。

未来模型阵容变了（新档位 / 改名），照上面三处改即可。

内置模型 id 都是官方、不带前缀的 Claude id。ccshift 不再附带任何网关专用 lane；若自建 Claude 端点还暴露额外模型，请显式定制档位表。

## 验证 / 排障

开一个 Claude Code 会话，按你宿主对应的方式点一个别的模型档位（tmux 单击 / Herdr Ctrl+click）：输入框自动出现 `/model <x>` 并回车，高亮跳到新档，而 `~/.claude/settings.json` 里仍是你的默认值。日志在 `logs/hud-click.log`（tmux）和 `logs/herdr-shift.log`（Herdr）。

**点了没反应？** 先确认宿主，再分层排查：

```bash
echo "$TMUX" "$HERDR_ENV"        # 两个都空 = 裸终端,点击层不存在

# --- tmux 路径 ---
tmux show -g mouse                            # 应为 mouse on
grep -c 'MouseDown1Pane' ~/.tmux.conf         # 应 ≥ 1;改完 conf 记得 tmux source-file
tail logs/hud-click.log                       # 有行 = 点击已被拦到,问题在执行层

# --- Herdr 路径 ---
herdr plugin list --json | grep ccshift       # 应存在且 enabled
tail logs/herdr-shift.log                     # 有行 = link handler 已触发
herdr plugin log list                         # 处理器的 exit code / stderr
```

几个典型现象：

- **换挡条还在显示、只是点不动** —— 显示层与宿主无关，所以换了宿主后看起来一切正常。先按上面确认宿主对应的点击层装没装。
- **Herdr 下单击/双击没反应，只是把词复制走了** —— 那是正常的文本选择行为，Herdr 需要 **Ctrl+click**，原因见上方「两种宿主」。
- **注入成功但报 `Model '…' not found`** —— 点击链路是好的，问题在档位表的 id。日志里 `ok=True` 就说明命令已提交。照「自定义」一节列出网关真实可用的 id 再对。

## License

MIT
