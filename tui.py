#!/usr/bin/env python3
import os, time, select, sys, re, shutil
from rich import box
from rich import print
from rich.align import Align
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table
from rich.text import Text
import termios, tty
from utils import human_eta
from state import SpiralState, SaveManager
from spiral import next_step

RENDER_FPS = 5
LEFT_MIN_WIDTH = 44
_left_width = LEFT_MIN_WIDTH
_LOG_WIDTH_FROZEN = False

XZ_MIN_W = 1
Y_MAX_W = 3
_wxL = XZ_MIN_W
_wyL = Y_MAX_W
_wzL = XZ_MIN_W
_wxR = XZ_MIN_W
_wyR = Y_MAX_W
_wzR = XZ_MIN_W

OFFLINE_PATTERNS = [
    "no entity", "entity not found", "player not found", "cannot be found",
    "no player was found", "is not online", "no targets matched"
]

class RawInput:
    def __init__(self, stream):
        self.stream = stream
        self.fd = stream.fileno()
        self.old_settings = None
    def __enter__(self):
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self
    def __exit__(self, exc_type, exc, tb):
        if self.old_settings is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

def _kbd_tag(key_label: str) -> str:
    return f"[dim][[/dim][white]{key_label}[/white][dim]][/dim]"

def _format_dimension(dim: str) -> str:
    s = (dim or "").strip()
    if ":" in s:
        ns, name = s.split(":", 1)
    else:
        ns, name = "minecraft", s
    ns_markup = f"[green4]{ns}[/green4]"
    sep = "[white]:[/white]"
    name_low = name.lower()
    if name_low == "overworld":
        name_markup = "[green1]overworld[/green1]"
    elif name_low == "the_nether":
        name_markup = "[red]the_nether[/red]"
    elif name_low == "the_end":
        name_markup = "[magenta]the_end[/magenta]"
    else:
        name_markup = name
    return f"{ns_markup}{sep}{name_markup}"

def build_header(paused: bool, auto_reason: str | None, width: int) -> Panel:
    title = Text("Spirale Carrée RCON", style="bold cyan")
    subtitle_txt = (
        "[bold]Exploration-auto[/bold] — "
        f"{_kbd_tag('N')}[dim]=Suivant [/dim]"
        f"{_kbd_tag('P')}[dim]=Pause [/dim]"
        f"{_kbd_tag('Esc')}[dim]=Quitter [/dim]"
        f"{_kbd_tag('C')}[dim]=Contrôle[/dim]"
    )
    subtitle = Text.from_markup(subtitle_txt)
    subtitle.no_wrap = True
    subtitle.overflow = "ellipsis"
    row = Table.grid(expand=True)
    row.add_column(no_wrap=True, ratio=1)
    row.add_row(Align.center(title))
    row.add_row(Align.left(subtitle))
    return Panel(row, box=box.ROUNDED, width=width)

def build_stats_panel(state: SpiralState, paused: bool, next_due: float, now: float, width: int) -> Panel:
    table = Table.grid(expand=True)
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="right", ratio=1)
    remaining_tps = None
    if state.max_tps is not None and state.max_tps >= 0:
        remaining_tps = max(state.max_tps - state.step_index, 0)
    time_to_next = max(0.0, next_due - now) if not paused else None
    eta_total = None
    if remaining_tps is not None and not paused:
        eta_total = time_to_next + max(0, remaining_tps - 1) * state.interval_s
    table.add_row("Joueur", f"{state.player}")
    table.add_row("Dimension", _format_dimension(f"{state.dimension}"))
    table.add_row("Hauteur (Y=)", f"{state.y}")
    table.add_row("Chunks", f"{state.chunk_step} → {state.step_blocks} blocs")
    table.add_row("Spawn (X)", f"{state.spawn_x}")
    table.add_row("Spawn (Z)", f"{state.spawn_z}")
    table.add_row("TP effectués", f"{state.step_index}{f' / {state.max_tps}' if state.max_tps not in (None, -1) else ''}")
    table.add_row("Prochain TP dans", human_eta(time_to_next))
    table.add_row("ETA total", ("en pause" if paused else human_eta(eta_total)))
    return Panel(table, title="Statuts", box=box.ROUNDED, width=width)

def _progress_color(elapsed: float, total: float) -> str:
    if total <= 0:
        return "green"
    ratio = max(0.0, min(1.0, elapsed / total))
    if ratio < 0.5:
        return "green"
    if ratio < 0.8:
        return "yellow3"
    return "red"

def build_progress_panel(interval_s: float, next_due: float, paused: bool, now: float, width: int) -> Panel:
    elapsed = 0.0
    if not paused:
        elapsed = max(0.0, min(interval_s, interval_s - max(0.0, next_due - now)))
    color = _progress_color(elapsed, float(interval_s))
    progress = Progress(
        TextColumn("{task.description}", justify="left"),
        BarColumn(complete_style=color, bar_width=None),
        TextColumn("{task.completed:.1f}s / {task.total:.1f}s", justify="right"),
        expand=True,
    )
    progress.add_task("Temps restant", total=float(interval_s), completed=float(elapsed))
    return Panel(progress, title="Prochain TP", box=box.ROUNDED, width=width)

def _looks_offline_or_error(resp: str) -> str | None:
    r = resp or ""
    r_low = r.lower()
    if r.startswith("ERREUR RCON"):
        return "RCON indisponible"
    for p in OFFLINE_PATTERNS:
        if p in r_low:
            return "joueur introuvable"
    return None

def _target_width() -> int:
    cols = shutil.get_terminal_size(fallback=(120, 40)).columns
    return max(80, min(int(cols * 0.68), 120))

_TELEPORTED_RE = re.compile(
    r"^Teleported\s+.+?\s+to\s+([+-]?\d+(?:\.\d+)?),\s*([+-]?\d+(?:\.\d+)?),\s*([+-]?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)

def _fmt_num(n: str | float | int) -> str:
    try:
        f = float(n); i = int(f)
        return str(i) if f == i else f"{f:.6f}".rstrip("0").rstrip(".")
    except Exception:
        return str(n)

def _upd_left(sx: str, sy: str, sz: str) -> None:
    global _wxL, _wyL, _wzL
    _wxL = max(_wxL, len(sx))
    _wyL = min(max(_wyL, len(sy)), Y_MAX_W)
    _wzL = max(_wzL, len(sz))

def _upd_right(sx: str, sy: str, sz: str) -> None:
    global _wxR, _wyR, _wzR
    _wxR = max(_wxR, len(sx))
    _wyR = min(max(_wyR, len(sy)), Y_MAX_W)
    _wzR = max(_wzR, len(sz))

def _coords_dual_pad_left(x, y, z) -> str:
    sx, sy, sz = map(_fmt_num, (x, y, z))
    _upd_left(sx, sy, sz)
    return (
        f"[gold1]X=[/gold1][khaki1]{sx.ljust(_wxL)}[/khaki1] "
        f"[gold1]Y=[/gold1][khaki1]{sy.ljust(_wyL)}[/khaki1] "
        f"[gold1]Z=[/gold1][khaki1]{sz.ljust(_wzL)}[/khaki1]"
    )

def _coords_dual_pad_right(x, y, z) -> str:
    sx, sy, sz = map(_fmt_num, (x, y, z))
    _upd_right(sx, sy, sz)
    return (
        f"[gold1]X=[/gold1][khaki1]{sx.ljust(_wxR)}[/khaki1] "
        f"[gold1]Y=[/gold1][khaki1]{sy.ljust(_wyR)}[/khaki1] "
        f"[gold1]Z=[/gold1][khaki1]{sz.ljust(_wzR)}[/khaki1]"
    )

def _coords_error_pad_right(x, y, z) -> str:
    sx, sy, sz = map(_fmt_num, (x, y, z))
    _upd_right(sx, sy, sz)
    return (
        f"[magenta]X=[/magenta][red]{sx.ljust(_wxR)}[/red] "
        f"[magenta]Y=[/magenta][red]{sy.ljust(_wyR)}[/red] "
        f"[magenta]Z=[/magenta][red]{sz.ljust(_wzR)}[/red]"
    )

def _build_right_segment(resp: str, player: str, cmd_x: int, cmd_y: int, cmd_z: int) -> str:
    if resp and resp.startswith("[DRY-RUN]"):
        return f"[white]Teleported {player} to[/white] {_coords_error_pad_right(cmd_x, cmd_y, cmd_z)} [yellow](simulation)[/yellow]"
    m = _TELEPORTED_RE.match((resp or "").strip())
    if m:
        rx, ry, rz = (m.group(1), m.group(2), m.group(3))
        return f"[white]Teleported {player} to[/white] {_coords_dual_pad_right(rx, ry, rz)}"
    extra = f" [red dim]{resp}[/red dim]" if resp else ""
    return f"[white]Teleported {player} to[/white] {_coords_error_pad_right(cmd_x, cmd_y, cmd_z)}{extra}"

def _fmt_ts_markup() -> str:
    h, m, s = time.strftime("%H:%M:%S").split(":")
    return (
        f"[dim][[/dim][white]{h}[/white]"
        f"[dim]:[/dim][white]{m}[/white]"
        f"[dim]:[/dim][white]{s}[/white][dim]][/dim]"
    )

def _print_aligned_log(left_markup: str, right_markup: str) -> None:
    global _left_width, _LOG_WIDTH_FROZEN
    left_text = Text.from_markup(left_markup); left_text.no_wrap = True; left_text.overflow = "crop"
    right_text = Text.from_markup(right_markup); right_text.no_wrap = True; right_text.overflow = "crop"
    if not _LOG_WIDTH_FROZEN:
        vis = getattr(left_text, "cell_len", len(left_text.plain))
        cols = shutil.get_terminal_size(fallback=(120, 40)).columns
        _left_width = min(max(LEFT_MIN_WIDTH, vis), int(cols * 0.55))
        _LOG_WIDTH_FROZEN = True
    grid = Table.grid(padding=(0, 1))
    grid.add_column(width=_left_width, no_wrap=True)
    grid.add_column(width=1, justify="center", no_wrap=True)
    grid.add_column(ratio=1, no_wrap=True)
    grid.add_row(left_text, Text("│", style="dim"), right_text)
    print(grid)

def run_loop(state: SpiralState, save: SaveManager, rcon) -> str | None:
    if state.step_index == 0 and (state.current_x, state.current_z) == (0, 0):
        state.current_x = state.spawn_x
        state.current_z = state.spawn_z
    paused = False
    auto_reason: str | None = None
    next_due = time.time() + state.interval_s
    force_next = False
    with Live(refresh_per_second=RENDER_FPS, screen=False) as live, RawInput(sys.stdin):
        next_render = 0.0
        width = _target_width()
        next_width_check = time.time() + 2.0
        dirty = True
        while True:
            now = time.time()
            if now >= next_width_check:
                new_w = _target_width()
                if new_w != width:
                    width = new_w
                    dirty = True
                next_width_check = now + 2.0
            if dirty or now >= next_render:
                adj_width = max(60, width - 5)
                header = build_header(paused, auto_reason, adj_width)
                stats  = build_stats_panel(state, paused, next_due, now, adj_width)
                prog   = build_progress_panel(state.interval_s, next_due, paused, now, adj_width)
                body = Panel(Group(header, stats, prog), box=box.DOUBLE, width=adj_width)
                live.update(Group(Text(""), body))
                next_render = now + 1.0 / RENDER_FPS
                dirty = False
            time_to_next = max(0.0, next_due - now)
            timeout = min(1.0 / RENDER_FPS, max(0.05, time_to_next))
            rlist, _, _ = select.select([sys.stdin], [], [], timeout)
            if rlist:
                ch = os.read(sys.stdin.fileno(), 1)
                if ch:
                    k = ch.decode(errors="ignore")
                    k_low = k.lower()
                    if k_low == "n":
                        force_next = True; save.save(state); dirty = True
                    elif k_low == "p":
                        paused = not paused
                        if not paused:
                            auto_reason = None
                            next_due = time.time() + state.interval_s
                        save.save(state); dirty = True
                    elif k_low == "c":
                        save.save(state)
                        return "CONTROL"
                    elif k == "\x1b":
                        save.save(state)
                        return None
            if (not paused and time.time() >= next_due) or force_next:
                if state.max_tps is not None and state.max_tps >= 0 and state.step_index >= state.max_tps:
                    save.save(state); return None
                x, z, state = next_step(state)
                cmd = f"execute in {state.dimension} run tp {state.player} {x} {state.y} {z}"
                try:
                    resp = rcon.cmd(cmd)
                except Exception as e:
                    resp = f"ERREUR RCON : {e}"
                ts = _fmt_ts_markup()
                left = f"{ts} [bold cyan]TP {state.step_index}[/bold cyan] -> {_coords_dual_pad_left(x, state.y, z)}"
                right = _build_right_segment(resp, state.player, x, state.y, z)
                _print_aligned_log(left, right)
                issue = _looks_offline_or_error(resp)
                if issue:
                    paused = True; auto_reason = issue
                save.save(state)
                next_due = time.time() + state.interval_s
                force_next = False; dirty = True
