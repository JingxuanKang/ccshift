#!/usr/bin/env python3
"""model-shift TUI — 在 tmux 里给 Claude Code 一个纯鼠标点击的换挡面板。

仿实体换挡杆：H 型拨杆（5 档模型 + R 复位）+ effort 拨片 + 通栏 LCD 仪表屏。
不绑定任何键盘按键，一切操作靠点击（左上 ● 关闭、↻ 刷新快照）。
点击换挡：把 /model <x> 或 /effort <x> 注入目标 pane，随后自动把
~/.claude/settings.json 里被顺带改写的默认值还原成启动时的快照，
从而做到「切换只影响当前会话，新窗口不继承」。
"""
import argparse
import curses
import json
import locale
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import queue
import unicodedata

SETTINGS = os.path.expanduser("~/.claude/settings.json")

# H 型换挡拨杆：(档位号, 档位标签, /model 值, 列, 排)  排: 0=上 1=下；R 档复位到快照
GATE = [
    ("1", "HAIKU", "haiku", 0, 0),
    ("2", "SONNET", "sonnet", 0, 1),
    ("3", "SONNET-1M", "sonnet[1m]", 1, 0),
    ("4", "OPUS", "opus", 1, 1),
    ("5", "FABLE", "fable", 2, 0),
    ("R", "DEFAULT", None, 2, 1),
]
EFFORTS = [
    ("LOW", "low"),
    ("MED", "medium"),
    ("HIGH", "high"),
    ("XHIGH", "xhigh"),
]

COL_W = 14          # 拨杆每列宽
GATE_LEFT = 3       # 拨杆左缘
LCD_LEFT = GATE_LEFT + COL_W * 3 + 4   # LCD 屏左缘（右缘随终端宽度伸展）


def wlen(s):
    """显示宽度（CJK 宽字符算 2）。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def wtrunc(s, w):
    while s and wlen(s) > w:
        s = s[:-1]
    return s


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def read_settings():
    try:
        with open(SETTINGS) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def restore_defaults(snap_model, snap_effort):
    """把 settings.json 的 model/effortLevel 还原为快照值（幂等、原子写）。"""
    data = read_settings()
    if data is None:
        return False
    changed = False
    if snap_model is not None and data.get("model") != snap_model:
        data["model"] = snap_model
        changed = True
    if snap_effort is not None and data.get("effortLevel") != snap_effort:
        data["effortLevel"] = snap_effort
        changed = True
    if not changed:
        return True
    mode = stat.S_IMODE(os.stat(SETTINGS).st_mode)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(SETTINGS), prefix=".shift-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, SETTINGS)
    except BaseException:
        os.unlink(tmp)
        raise
    return True


class Shifter:
    def __init__(self, target):
        self.target = target
        self.jobs = queue.Queue()
        self.lock = threading.Lock()
        s = read_settings() or {}
        self.snap_model = s.get("model")
        self.snap_effort = s.get("effortLevel")
        self.cur_model = self.snap_model
        self.cur_effort = self.snap_effort
        self.busy = False
        self.status = "就绪 · 点击档位换挡"
        threading.Thread(target=self._run, daemon=True).start()

    def _set(self, **kw):
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, v)

    def _composer_line(self):
        """目标 pane 里当前 composer 行（最后一个 ❯ 开头的行）。"""
        r = tmux("capture-pane", "-t", self.target, "-p")
        if r.returncode != 0:
            return None
        # composer 行的 ❯ 后是 U+00A0（历史行是普通空格），统一归一化
        lines = [l.strip().replace("\xa0", " ") for l in r.stdout.splitlines()
                 if l.strip().startswith("❯")]
        return lines[-1] if lines else ""

    def _send_command(self, text):
        """注入一条命令：清行 → 输入 → 验证 composer → 回车。

        claude 处理上一条命令时重渲染窗口期会吞掉注入的文本，
        所以回车前必须验证命令真的落进了 composer，没落就重试。
        """
        for _ in range(3):
            r = tmux("send-keys", "-t", self.target, "C-u")
            if r.returncode != 0:
                return False
            time.sleep(0.2)
            tmux("send-keys", "-t", self.target, "-l", "--", text)
            time.sleep(0.5)
            line = self._composer_line()
            if line is None:
                return False
            if line == f"❯ {text}":
                tmux("send-keys", "-t", self.target, "Enter")
                time.sleep(1.5)
                return True
            time.sleep(0.5)
        return False

    def _run(self):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            kind, value = job
            if kind == "model":
                cmds = [f"/model {value}"]
            elif kind == "effort":
                cmds = [f"/effort {value}"]
            else:  # reset：回 R 档（快照档位）
                cmds = []
                if self.snap_model:
                    cmds.append(f"/model {self.snap_model}")
                if self.snap_effort:
                    cmds.append(f"/effort {self.snap_effort}")
            self._set(busy=True)
            ok = True
            for c in cmds:
                self._set(status=f"换挡中 {c} …")
                if not self._send_command(c):
                    ok = False
                    break
            if not ok:
                self._set(busy=False, status="注入失败（claude 关了或 composer 被占用）")
                continue
            restore_defaults(self.snap_model, self.snap_effort)
            with self.lock:
                if kind == "model":
                    self.cur_model = value
                elif kind == "effort":
                    self.cur_effort = value
                else:
                    self.cur_model = self.snap_model
                    self.cur_effort = self.snap_effort
                self.busy = False
                self.status = f"已切换 {' · '.join(cmds)} · 默认未动"

    def shift(self, kind, value=None):
        self.jobs.put((kind, value))

    def resnapshot(self):
        s = read_settings() or {}
        self._set(snap_model=s.get("model"), snap_effort=s.get("effortLevel"),
                  status="快照已刷新（当前 settings 即 R 档）")


def gear_label(value, snap_model):
    for _, label, v, _, _ in GATE:
        if v is not None and v == value:
            return label
    if value == snap_model:
        return "DEFAULT"
    return value or "?"


def knob_pos(cur_model, snap_model):
    for _, _, v, col, row in GATE:
        if v is not None and v == cur_model:
            return col, row
    if cur_model == snap_model:
        return 2, 1  # R 档
    return None


C_LABEL, C_AMBER, C_RED, C_PURPLE, C_DIM, C_GREEN = 1, 2, 3, 4, 5, 6


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    if curses.COLORS >= 256:
        curses.init_pair(C_LABEL, 251, -1)   # 钢灰标签
        curses.init_pair(C_AMBER, 214, -1)   # 琥珀 LCD
        curses.init_pair(C_RED, 196, -1)     # 红点/knob
        curses.init_pair(C_PURPLE, 141, -1)  # 紫色大字（当前档）
        curses.init_pair(C_DIM, 240, -1)     # 暗灰线条
        curses.init_pair(C_GREEN, 114, -1)
    else:
        curses.init_pair(C_LABEL, curses.COLOR_WHITE, -1)
        curses.init_pair(C_AMBER, curses.COLOR_YELLOW, -1)
        curses.init_pair(C_RED, curses.COLOR_RED, -1)
        curses.init_pair(C_PURPLE, curses.COLOR_MAGENTA, -1)
        curses.init_pair(C_DIM, curses.COLOR_WHITE, -1)
        curses.init_pair(C_GREEN, curses.COLOR_GREEN, -1)


def draw(stdscr, sh, hitboxes):
    stdscr.erase()
    maxy, maxx = stdscr.getmaxyx()
    hitboxes.clear()
    with sh.lock:
        cur_model, cur_effort = sh.cur_model, sh.cur_effort
        snap_model, snap_effort = sh.snap_model, sh.snap_effort
        status, busy = sh.status, sh.busy

    def put(y, x, text, attr=0):
        if 0 <= y < maxy and x < maxx:
            try:
                stdscr.addstr(y, x, text, attr)
            except curses.error:
                pass

    def center(col):
        return GATE_LEFT + col * COL_W + COL_W // 2

    # ── 标题行：● 关闭 · ↻ 刷新快照（都是点击钮，无键盘） ──
    put(0, 1, "●", curses.A_BOLD | curses.color_pair(C_RED))
    hitboxes.append((0, 0, 2, ("quit", None)))
    put(0, 4, "M O D E L  S H I F T", curses.A_BOLD | curses.color_pair(C_LABEL))
    put(0, 27, "↻", curses.A_BOLD | curses.color_pair(C_DIM))
    hitboxes.append((0, 26, 28, ("snap", None)))

    # ── H 型拨杆：y1 上标签 y2 上滑槽 y3 横杆 y4 下滑槽 y5 下标签 ──
    knob = knob_pos(cur_model, snap_model)
    for key, label, value, col, row in GATE:
        cx = center(col)
        text = f"{key} {label}"
        tx = cx - wlen(text) // 2
        ly = 1 if row == 0 else 5
        active = (knob == (col, row))
        attr = (curses.A_BOLD | curses.color_pair(C_AMBER) | curses.A_REVERSE
                if active else curses.color_pair(C_LABEL))
        put(ly, tx, text, attr)
        action = ("reset", None) if value is None else ("model", value)
        hitboxes.append((ly, tx, tx + wlen(text) - 1, action))
        # 滑槽格子也可点
        sy = 2 if row == 0 else 4
        hitboxes.append((sy, cx - 1, cx + 1, action))

    lx, rx = center(0), center(2)
    for col in range(3):
        cx = center(col)
        put(2, cx, "┃", curses.color_pair(C_DIM))
        put(4, cx, "┃", curses.color_pair(C_DIM))
    bar = "┣" + "━" * (center(1) - lx - 1) + "╋" + "━" * (rx - center(1) - 1) + "┫"
    put(3, lx, bar, curses.color_pair(C_DIM))
    if knob:
        col, row = knob
        put(2 if row == 0 else 4, center(col), "◉",
            curses.A_BOLD | curses.color_pair(C_RED))

    # ── effort 拨片（y6，纯点击） ──
    y = 6
    put(y, GATE_LEFT, "EFFORT", curses.A_BOLD | curses.color_pair(C_LABEL))
    x = GATE_LEFT + 8
    for label, value in EFFORTS:
        txt = f" {label} "
        active = value == cur_effort
        attr = (curses.A_BOLD | curses.color_pair(C_AMBER) | curses.A_REVERSE
                if active else curses.color_pair(C_LABEL))
        put(y, x, txt, attr)
        hitboxes.append((y, x, x + wlen(txt) - 1, ("effort", value)))
        x += wlen(txt) + 2

    # ── LCD 仪表屏：从拨杆右侧一直铺到终端右缘 ──
    x0, x1 = LCD_LEFT, maxx - 2
    if x1 - x0 >= 32:
        dim = curses.color_pair(C_DIM)
        inner = x1 - x0 - 3   # 内容可用宽度
        put(1, x0, "╭" + "─" * (x1 - x0 - 1) + "╮", dim)
        for yy in (2, 3, 4):
            put(yy, x0, "│", dim)
            put(yy, x1, "│", dim)
        put(5, x0, "╰" + "─" * (x1 - x0 - 1) + "╯", dim)

        name = gear_label(cur_model, snap_model)
        put(2, x0 + 2, wtrunc(name, inner - 14),
            curses.A_BOLD | curses.color_pair(C_PURPLE))
        seg = {"low": 1, "medium": 2, "high": 3, "xhigh": 4}.get(cur_effort or "", 0)
        eff = "▰" * seg + "▱" * (4 - seg) + f" {(cur_effort or '?').upper()}"
        put(2, x1 - wlen(eff) - 1, eff, curses.color_pair(C_AMBER))

        st = ("⣾⣽⣻⢿⡿⣟⣯⣷"[int(time.time() * 8) % 8] + " " if busy else "")
        put(3, x0 + 2, wtrunc(f"{st}{status}", inner), curses.color_pair(C_AMBER))

        left3 = f"R档 {gear_label(snap_model, snap_model)} / {snap_effort}"
        right3 = f"目标 {sh.target}"
        put(4, x0 + 2, wtrunc(left3, inner - wlen(right3) - 2), dim)
        put(4, x1 - wlen(right3) - 1, right3, dim)
        # LCD 下沿与 effort 行对齐的通栏底线
        put(6, x0, "─" * (x1 - x0 + 1), dim)
    else:
        put(6, GATE_LEFT + 60 if maxx > GATE_LEFT + 70 else 0, "", 0)
        put(7 if maxy > 7 else 6, GATE_LEFT,
            wtrunc(("⣾ " if busy else "▸ ") + status, maxx - GATE_LEFT - 2),
            curses.color_pair(C_AMBER))

    stdscr.refresh()


def main(stdscr, target):
    curses.curs_set(0)
    init_colors()
    curses.mousemask(curses.ALL_MOUSE_EVENTS)
    curses.mouseinterval(150)
    # tmux 的 TERM=screen-256color 缺 XM 描述，ncurses 不一定替我们开鼠标上报；
    # 手动开 X10 + 按钮事件模式（1002），坐标 ≤223 列，所有点击目标都在左侧安全区
    os.write(sys.stdout.fileno(), b"\x1b[?1000h\x1b[?1002h")
    stdscr.timeout(150)  # 轮询刷新，让 worker 状态与 spinner 动起来
    stdscr.keypad(True)

    sh = Shifter(target)
    hitboxes = []

    while True:
        draw(stdscr, sh, hitboxes)
        try:
            c = stdscr.getch()
        except KeyboardInterrupt:
            return
        if c == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
            except curses.error:
                continue
            if not bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                continue
            for y, x1, x2, (kind, value) in hitboxes:
                if my == y and x1 <= mx <= x2:
                    if kind == "quit":
                        return
                    if kind == "snap":
                        sh.resnapshot()
                    else:
                        sh.shift(kind, value)
                    break
        # 其余一律忽略：本面板不绑定任何键盘按键


if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, "")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", required=True, help="claude 所在 tmux pane（如 %%1）")
    args = ap.parse_args()
    if tmux("display-message", "-t", args.target, "-p", "#{pane_id}").returncode != 0:
        sys.exit(f"目标 pane 不存在: {args.target}")
    try:
        curses.wrapper(main, args.target)
    finally:
        os.write(sys.stdout.fileno(), b"\x1b[?1002l\x1b[?1000l")
