# model-switch

Claude Code 模型 / effort 的"档位锁"：默认值钉死在 `pin.json`，所有切换只影响当前会话，新窗口永远从钉住的默认启动。

## 为什么需要

Claude Code 里 `/model` 选 Enter（或直接 `/model opus` 这种带参数命令）会把选择写进 `~/.claude/settings.json` 的 `model` / `effortLevel`——于是新开的窗口"继承"了上一次的切换。本工具用一个 launchd 守护监视 settings.json，一旦这两个键偏离 `pin.json`，几秒内自动还原。由于 Claude Code 的 `model` 键只在会话启动时读一次（不热重载），还原不会干扰任何正在运行的会话。

## 会话内切换（Claude Code 内置，无需本工具）

| 操作 | 效果 |
|---|---|
| `Option+P`（或 `/model`）呼出 picker → 方向键选 → **按 `s`** | 仅本会话切换，不碰默认 |
| picker 里按 Enter | 会写默认——有守护在，几秒后被还原 |
| `Option+T` | 切 thinking，`Option+O` 切 fast mode |

**习惯用 `s` 键确认，Enter 留给真想改默认的场合（但改默认请走 `cs pin`）。**

## cs 启动器

```bash
cs            # 钉住的默认值启动（= 裸 claude）
cs o          # opus（仅本会话）
cs o h        # opus + high effort（仅本会话）
cs s1m x -c   # sonnet[1m] + xhigh，继续上次对话；多余参数原样传给 claude
cs pin f1m x  # 改默认：pin.json 与 settings.json 一起更新（唯一正规通道）
cs status     # 钉住值 / settings 现值 / 守护状态
```

别名：模型 `f`=fable `o`=opus `s`=sonnet `h`=haiku `op`=opusplan，加 `1m` 后缀为 1M 上下文变体（`f1m` `o1m` `s1m`）；effort `l`=low `m`=medium `h`/`hi`=high `x`=xhigh。位置消歧：第一个参数是模型，第二个是 effort，所以 `cs h` 是 haiku、`cs o h` 是 opus+high。

## 安装 / 卸载

```bash
./install.sh   # symlink cs 到 ~/.local/bin；生成并加载 launchd 守护（幂等，可重复跑）
```

卸载：

```bash
launchctl bootout "gui/$(id -u)/uk.jingxuan.model-pin-guard"
rm ~/Library/LaunchAgents/uk.jingxuan.model-pin-guard.plist ~/.local/bin/cs
```

## 运维

- 守护还原日志：`logs/pin-guard.log`（每次还原记一行 old → new）；launchd 自身输出：`logs/pin-guard.launchd.log`。
- 健康检查：`cs status`（显示 pin/settings 是否一致、launchd 是否加载）。
- 验证守护：手动把 settings.json 的 `model` 改掉，几秒后应自动还原并出日志。

## 已知局限

- 守护是"读-改-写"整个 settings.json：若 Claude Code 恰好同一瞬间写入其他设置键，存在极小概率的丢失窗口（实测未遇到；还原仅发生在这两个键偏离时）。
- `effortLevel` 是否热重载官方未明确：若某会话用 Enter 把 effort 设为默认后被守护还原，该会话当前 effort 有小概率被一并拽回——用 `s` 键切换则完全不受影响。
- 机制验证于 Claude Code 2.1.200；大版本升级后若发现行为变化，先看 `.claude/CLAUDE.md` 的"机制依据"。
