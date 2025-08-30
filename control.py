#!/usr/bin/env python3
import glob
import os
import re
import select
import shutil
import sys
import termios
import time
import tty
from collections import deque

from rich import print
from rich.align import Align
from rich.box import ROUNDED
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import compute_save_path


def _read_key(timeout=0.1) -> str | None:
    r, _, _ = select.select([sys.stdin], [], [], timeout)
    if not r:
        return None
    ch = os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
    if ch != "\x1b":
        return ch
    seq = ""
    end = time.time() + 0.06
    while time.time() < end:
        r, _, _ = select.select([sys.stdin], [], [], max(0, end - time.time()))
        if not r:
            break
        seq += os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
        if len(seq) >= 2:
            break
    if seq.startswith("["):
        m = seq[1:2]
        return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(m, "ESC")
    return "ESC"


class RawInput:
    def __init__(self, stream):
        self.stream = stream
        self.fd = stream.fileno()
        self.old = None

    def __enter__(self):
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.old is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)


def _dim_short(dim: str) -> str:
    mapping = {"minecraft:overworld": "ovw", "minecraft:the_nether": "net", "minecraft:the_end": "end"}
    if dim in mapping:
        return mapping[dim]
    dim = dim.replace("minecraft:", "")
    return "".join(c for c in dim if c.isalnum())[:8] or "dim"


def _find_latest_save(conf: dict) -> str | None:
    e = conf["exploration"]
    sd = conf.get("save_dir", "saves")
    player = e["player"]
    dim = _dim_short(e["dimension"])
    chunks = int(e["chunks"])
    sx = int(e["spawn_x"])
    sz = int(e["spawn_z"])
    y = int(e["y"])
    pattern = os.path.join(sd, f"{player}-{dim}-c{chunks}-sx{sx}-sz{sz}-y{y}-*.json")
    files = glob.glob(pattern)
    if not files:
        path = compute_save_path(conf)
        return path if os.path.isfile(path) else None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


_TELEPORTED_RE = re.compile(
    r"^Teleported\s+.+?\s+to\s+([+-]?\d+(?:\.\d+)?),\s*([+-]?\d+(?:\.\d+)?),\s*([+-]?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


def _fmt_num(n):
    try:
        f = float(n)
        i = int(f)
        return str(i) if f == i else f"{f:.6f}".rstrip("0").rstrip(".")
    except Exception:
        return str(n)


LEFT_MIN_WIDTH = 44
_left_width = LEFT_MIN_WIDTH


def _fmt_ts() -> str:
    h, m, s = time.strftime("%H:%M:%S").split(":")
    return f"[dim][[/dim][white]{h}[/white][dim]:[/dim][white]{m}[/white][dim]:[/dim][white]{s}[/white][dim]][/dim]"


def _coords_left(x, y, z):
    sx, sy, sz = map(_fmt_num, (x, y, z))
    return f"[gold1]X=[/gold1][khaki1]{sx}[/khaki1] [gold1]Y=[/gold1][khaki1]{sy}[/khaki1] [gold1]Z=[/gold1][khaki1]{sz}[/khaki1]"


_wxR = _wyR = _wzR = 1


def _upd_right_widths(sx, sy, sz):
    global _wxR, _wyR, _wzR
    _wxR = max(_wxR, len(sx))
    _wyR = max(_wyR, len(sy))
    _wzR = max(_wzR, len(sz))


def _coords_right_ok(x, y, z):
    sx, sy, sz = map(_fmt_num, (x, y, z))
    _upd_right_widths(sx, sy, sz)
    return f"[gold1]X=[/gold1][khaki1]{sx.ljust(_wxR)}[/khaki1] [gold1]Y=[/gold1][khaki1]{sy.ljust(_wyR)}[/khaki1] [gold1]Z=[/gold1][khaki1]{sz.ljust(_wzR)}[/khaki1]"


def _coords_right_err(x, y, z):
    sx, sy, sz = map(_fmt_num, (x, y, z))
    _upd_right_widths(sx, sy, sz)
    return f"[magenta]X=[/magenta][red]{sx.ljust(_wxR)}[/red] [magenta]Y=[/magenta][red]{sy.ljust(_wyR)}[/red] [magenta]Z=[/magenta][red]{sz.ljust(_wzR)}[/red]"


def _build_right(resp, player, x, y, z):
    if resp and resp.startswith("[DRY-RUN]"):
        return f"[white]Teleported {player} to[/white] {_coords_right_err(x,y,z)} [yellow](simulation)[/yellow]"
    m = _TELEPORTED_RE.match((resp or "").strip())
    if m:
        rx, ry, rz = _fmt_num(m.group(1)), _fmt_num(m.group(2)), _fmt_num(m.group(3))
        return f"[white]Teleported {player} to[/white] {_coords_right_ok(rx,ry,rz)}"
    extra = f" [red dim]{resp}[/red dim]" if resp else ""
    return f"[white]Teleported {player} to[/white] {_coords_right_err(x,y,z)}{extra}"


def _top_border(title: str, width: int) -> Text:
    inner = width - 2
    t = f" {title} "
    left = (inner - len(t)) // 2
    right = inner - len(t) - left
    return Text("╭" + "─" * left + t + "─" * right + "╮")


def _bottom_border_split(width: int, left_area: int, right_area: int) -> Text:
    L = left_area + 2
    R = max(0, width - 3 - L)
    return Text("╰" + "─" * L + "┴" + "─" * R + "╯")


def _pad_trunc(txt: Text, width: int) -> Text:
    if txt.cell_len > width:
        txt.truncate(width, overflow="crop")
    if txt.cell_len < width:
        txt.append(" " * (width - txt.cell_len))
    return txt


def _log_panel(rows, width):
    global _left_width
    left_w_measured = 0
    left_texts = []
    right_texts = []
    for left_markup, right_markup in rows:
        lt = Text.from_markup(left_markup)
        lt.no_wrap = True
        rt = Text.from_markup(right_markup)
        rt.no_wrap = True
        left_texts.append(lt)
        right_texts.append(rt)
        left_w_measured = max(left_w_measured, lt.cell_len)
    left_area = max(LEFT_MIN_WIDTH, left_w_measured, _left_width)
    cols_total = width
    right_area = max(20, cols_total - left_area - 7)
    _left_width = left_area
    lines = [_top_border("Historique TPs", width)]
    for lt, rt in zip(left_texts, right_texts, strict=False):
        lt = _pad_trunc(lt, left_area)
        rt = _pad_trunc(rt, right_area)
        line = Text()
        line.append("│ ")
        line += lt
        line.append(" │ ")
        line += rt
        line.append(" │")
        lines.append(line)
    lines.append(_bottom_border_split(width, left_area, right_area))
    return Group(*lines)


def _dim_mark_and_player_style(dim: str):
    ns_color = "dark_green"
    val_color = "green3"
    val = dim
    if ":" in dim:
        ns, val = dim.split(":", 1)
    else:
        ns = "minecraft"
    if val == "the_nether":
        val_color = "red3"
    elif val == "the_end":
        val_color = "medium_purple3"
    elif val == "overworld" or val == "minecraft:overworld":
        val_color = "green3"
    dim_markup = f"[{ns_color}]{ns}[/][white]:[/white][{val_color}]{val}[/]"
    return dim_markup, val_color


def _controls_block():
    l1 = Text.assemble(
        ("Déplacement", "bold cyan"),
        (" : ", "dim"),
        ("→←↑↓/ZQSD", "khaki1"),
        (" | ", "dim"),
        ("Hauteur", "bold cyan"),
        ("(Y=16)", "dim"),
        (" : ", "dim"),
        ("A/E", "khaki1"),
        (" | ", "dim"),
        ("Quitter", "bold cyan"),
        (" : ", "dim"),
        ("Esc", "khaki1"),
    )
    l2 = Text.assemble(
        ("Saut en chunks", "bold cyan"),
        (" : ", "dim"),
        ("+/-", "khaki1"),
        (" (×2/÷2)", "dim"),
        (" | ", "dim"),
        ("R", "bold cyan"),
        (" : ", "dim"),
        ("Reset", "khaki1"),
        (" | ", "dim"),
        ("Dimension", "bold cyan"),
        (" : ", "dim"),
        ("i", "khaki1"),
    )
    return [l1, l2]


def _ui(player, dim, x, y, z, chunks, tp_count, width):
    dim_markup, p_color = _dim_mark_and_player_style(dim)
    info = Table.grid(expand=True)
    info.add_column(justify="left", ratio=1, no_wrap=True)
    info.add_column(justify="right", ratio=1, no_wrap=True)
    info.add_row("Joueur", f"[{p_color}]{player}[/{p_color}]")
    info.add_row("Dimension", dim_markup)
    info.add_row("Position (X,Y,Z)", f"{x}, {y}, {z}")
    info.add_row("Saut (Chunks -> Blocs)", f"{chunks} -> {chunks*16}")
    info.add_row("Nombre de /tp", f"[gold1]{tp_count}[/gold1]")
    info_panel = Panel(info, title="Contrôle libre", box=ROUNDED, width=width)
    ctl = _controls_block()
    controls_panel = Panel(Group(ctl[0], ctl[1]), title="Contrôles", box=ROUNDED, width=width)
    return Group(info_panel, controls_panel)


def _normalize_dim(s: str) -> str:
    a = {"ovw": "minecraft:overworld", "net": "minecraft:the_nether", "end": "minecraft:the_end"}
    s = (s or "").strip()
    if s in a:
        return a[s]
    if ":" not in s and s:
        return f"minecraft:{s}"
    return s


def _read_dim_key(timeout=0.25):
    r, _, _ = select.select([sys.stdin], [], [], timeout)
    if not r:
        return None
    ch = os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
    if ch != "\x1b":
        return ch
    seq = ""
    end = time.time() + 0.1
    while time.time() < end:
        r, _, _ = select.select([sys.stdin], [], [], max(0, end - time.time()))
        if not r:
            break
        seq += os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
        if len(seq) >= 5:
            break
    if seq.startswith("[200~"):
        buf = []
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 1.0)
            if not r:
                break
            ch2 = os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
            if ch2 == "\x1b":
                tail = ""
                r2, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r2:
                    tail += os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
                    if tail == "[":
                        tail += os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
                        tail += os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
                        tail += os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
                        if tail == "[201~":
                            break
                        else:
                            buf.append("\x1b" + tail)
                            continue
                else:
                    buf.append(ch2)
                    continue
            else:
                buf.append(ch2)
        return "".join(buf)
    if seq.startswith("["):
        m = seq[1:2]
        return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(m, "ESC")
    return "ESC"


def _prompt_dimension(live, width, current_dim: str) -> str | None:
    buf = []
    while True:
        blink = "█" if int(time.time() * 2) % 2 == 0 else " "
        line1 = Text.assemble(
            ("Saisir une dimension (Entrée ou Esc pour choisir la dimension actuelle / Annuler) :", "dim")
        )
        line2 = Text.assemble(("> ", "bold"), ("".join(buf), "white"), (blink, "white"))
        panel = Panel(Group(line1, line2), title="Changer de dimension", box=ROUNDED, width=max(60, min(width, 100)))
        live.update(Group(panel))
        live.refresh()
        k = _read_dim_key(timeout=0.25)
        if not k:
            continue
        if k == "ESC":
            return None
        if k in ("\n", "\r"):
            s = "".join(buf).strip()
            if not s:
                return None
            return s
        if k in ("\x7f", "\b"):
            if buf:
                buf.pop()
            continue
        if isinstance(k, str) and len(k) > 1 and k not in ("UP", "DOWN", "LEFT", "RIGHT", "ESC"):
            buf.extend(list(k))
            continue
        if len(k) == 1 and (k.isalnum() or k in ":_-/."):
            buf.append(k)


def _coords_left(x, y, z):
    sx, sy, sz = map(_fmt_num, (x, y, z))
    return f"[gold1]X=[/gold1][khaki1]{sx}[/khaki1]  [gold1]Y=[/gold1][khaki1]{sy}[/khaki1] [gold1]Z=[/gold1][khaki1]{sz}[/khaki1]"


def _coords_right_ok(x, y, z):
    sx, sy, sz = map(_fmt_num, (x, y, z))
    _upd_right_widths(sx, sy, sz)
    return f"[gold1]X=[/gold1][khaki1]{sx.ljust(_wxR)}[/khaki1]  [gold1]Y=[/gold1][khaki1]{sy.ljust(_wyR)}[/khaki1] [gold1]Z=[/gold1][khaki1]{sz.ljust(_wzR)}[/khaki1]"


def _coords_right_err(x, y, z):
    sx, sy, sz = map(_fmt_num, (x, y, z))
    _upd_right_widths(sx, sy, sz)
    return f"[magenta]X=[/magenta][red]{sx.ljust(_wxR)}[/red]  [magenta]Y=[/magenta][red]{sy.ljust(_wyR)}[/red] [magenta]Z=[/magenta][red]{sz.ljust(_wzR)}[/red]"


def _load_from_current_player(conf: dict):
    e = conf.get("exploration", {})
    player = e.get("player", "Yakonche")
    usernamecache = conf.get("usernamecache", "/srv/minecraft/usernamecache.json")
    playerdata_dir = conf.get("playerdata_dir", "/srv/minecraft/world/playerdata")
    try:
        import nbt as nbtmod
    except Exception as ex:
        raise RuntimeError(f"import nbt.py impossible : {ex}")
    names = nbtmod.load_usernames(usernamecache)
    uuid = None
    for k, v in names.items():
        if v == player:
            uuid = k
            break
    if not uuid:
        raise RuntimeError(f"UUID introuvable pour {player} dans {usernamecache}")
    fp = os.path.join(playerdata_dir, f"{uuid}.dat")
    if not os.path.isfile(fp):
        raise RuntimeError(f"playerdata introuvable: {fp}")
    pdata = nbtmod.read_file(fp)
    dim = _normalize_dim(str(pdata.get("Dimension", "minecraft:overworld")))
    pos = pdata.get("Pos", [0, 192, 0])
    try:
        if hasattr(pos, "tolist"):
            pos = pos.tolist()
        x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
    except Exception:
        x, y, z = 0.0, 192.0, 0.0
    return dim, x, y, z


def run_free_control(conf: dict, rcon) -> None:
    e = conf.get("exploration", {})
    player = e.get("player", "Yakonche")
    dim = e.get("dimension", "minecraft:overworld")
    x0 = int(e.get("spawn_x", 0))
    z0 = int(e.get("spawn_z", 0))
    y = int(e.get("y", 192))
    step_chunks = int(e.get("chunks", 32))
    x, z = x0, z0

    print("\nContrôle libre — choisissez le point de départ :")
    print("1) Spawn")
    print("2) Charger depuis la sauvegarde")
    print("3) Charger depuis la position actuelle du joueur")
    print("4) Quitter (Esc)\n")

    choice = None
    with RawInput(sys.stdin):
        while True:
            k = _read_key(timeout=0.5)
            if not k:
                continue
            if k in "1234":
                choice = k
                break
            if k == "ESC":
                choice = "4"
                break

    if choice == "2":
        try:
            from state import SaveManager

            path = _find_latest_save(conf)
            if path:
                st = SaveManager(path).load()
                dim = st.dimension or dim
                x = st.current_x if st.current_x is not None else st.spawn_x
                z = st.current_z if st.current_z is not None else st.spawn_z
                y = st.y if st.y is not None else y
            else:
                print("[yellow]Aucune sauvegarde trouvée, utilisation du spawn.[/yellow]")
        except Exception as e:
            print(f"[yellow]Impossible de charger la sauvegarde : {e}[/yellow]")

    if choice == "3":
        try:
            dim2, x2, y2, z2 = _load_from_current_player(conf)
            dim = dim2
            x, y, z = x2, int(y2), z2
        except Exception as e:
            print(f"[yellow]Lecture NBT impossible, utilisation du spawn : {e}[/yellow]")

    if choice == "4":
        return

    cols = shutil.get_terminal_size((120, 40)).columns
    width = min(max(110, int(cols * 0.95)), max(120, cols - 2), 240)
    tp_count = 0
    last_sent = None
    logs = deque(maxlen=20)

    def send_tp(tx, ty, tz, tdim):
        nonlocal last_sent, tp_count
        tdim2 = _normalize_dim(tdim)
        target = (tdim2, tx, ty, tz)
        if target == last_sent:
            return False
        try:
            resp = rcon.cmd(f"execute in {tdim2} run tp {player} {tx} {ty} {tz}")
        except Exception as e:
            resp = f"ERREUR RCON : {e}"
        ts = _fmt_ts()
        left = f"{ts} [bold cyan]TP {tp_count}[/bold cyan] -> {_coords_left(tx,ty,tz)}"
        if resp and resp.strip():
            m = _TELEPORTED_RE.match(resp.strip())
            if m:
                rx, ry, rz = _fmt_num(m.group(1)), _fmt_num(m.group(2)), _fmt_num(m.group(3))
                right = f"[white]Teleported {player} to[/white] {_coords_right_ok(rx,ry,rz)}"
            else:
                right = f"[white]Teleported {player} to[/white] {_coords_right_err(tx,ty,tz)}"
                logs.append((left, right))
                logs.append(("", f"[red]{resp}[/red]"))
                last_sent = target
                return True
        else:
            right = f"[white]Teleported {player} to[/white] {_coords_right_ok(tx,ty,tz)}"
        logs.append((left, right))
        last_sent = target
        return True

    with Live(auto_refresh=False, screen=False) as live, RawInput(sys.stdin):
        dirty = True
        send_tp(x, y, z, dim)
        dirty = True
        last_cols = cols
        while True:
            if dirty:
                log_block = _log_panel(list(logs), width)
                ctrl_panel = _ui(player, dim, x, y, z, step_chunks, tp_count, max(90, min(120, int(width * 0.8))))
                live.update(Group(log_block, Align.center(ctrl_panel)))
                live.refresh()
                dirty = False

            start = time.time()
            moved = False
            while time.time() - start < 0.8:
                k = _read_key(timeout=0.1)
                if not k:
                    new_cols = shutil.get_terminal_size((120, 40)).columns
                    if new_cols != last_cols:
                        last_cols = new_cols
                        width = min(max(110, int(new_cols * 0.95)), max(120, new_cols - 2), 240)
                        dirty = True
                    continue
                if k == "RIGHT" or k.lower() == "d":
                    x += step_chunks * 16
                    tp_count += 1
                    moved = True
                    break
                if k == "LEFT" or k.lower() == "q":
                    x -= step_chunks * 16
                    tp_count += 1
                    moved = True
                    break
                if k == "UP" or k.lower() == "z":
                    z -= step_chunks * 16
                    tp_count += 1
                    moved = True
                    break
                if k == "DOWN" or k.lower() == "s":
                    z += step_chunks * 16
                    tp_count += 1
                    moved = True
                    break
                if k.lower() == "a":
                    y += 16
                    tp_count += 1
                    moved = True
                    break
                if k.lower() == "e":
                    y -= 16
                    tp_count += 1
                    moved = True
                    break
                if k == "+":
                    step_chunks = max(1, step_chunks * 2)
                    dirty = True
                    break
                if k == "-":
                    step_chunks = max(1, step_chunks // 2 or 1)
                    dirty = True
                    break
                if k.lower() == "r":
                    x, z = x0, z0
                    moved = True
                    break
                if k.lower() == "i":
                    panel = Panel(Text(""), title="Changer de dimension", box=ROUNDED, width=max(60, min(width, 100)))
                    live.update(Group(panel))
                    live.refresh()
                    new_dim = _prompt_dimension(live, width, dim)
                    if new_dim:
                        dim = _normalize_dim(new_dim)
                        tp_count += 1
                        if send_tp(x, y, z, dim):
                            dirty = True
                    dirty = True
                    break
                if k == "ESC":
                    return
            if moved:
                if send_tp(x, y, z, dim):
                    dirty = True
