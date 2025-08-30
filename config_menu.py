import time

from rich.box import ROUNDED
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table


def edit_config(conf, console, read_key_ext) -> dict | None:
    fields = [
        ("RCON host", ("rcon", "host"), "str"),
        ("RCON port", ("rcon", "port"), "int"),
        ("RCON timeout (s)", ("rcon", "timeout"), "float"),
        ("RCON password", ("rcon", "password"), "str"),
        ("Joueur", ("exploration", "player"), "str"),
        ("Dimension", ("exploration", "dimension"), "str"),
        ("Hauteur (Y=)", ("exploration", "y"), "int"),
        ("Chunks", ("exploration", "chunks"), "int"),
        ("Spawn (X)", ("exploration", "spawn_x"), "int"),
        ("Spawn (Z)", ("exploration", "spawn_z"), "int"),
        ("Intervalle (s)", ("exploration", "interval"), "float"),
        ("/tp max (-1 = illimité)", ("exploration", "max_tps"), "int"),
        ("Fichier de sauvegarde", ("save_file",), "str"),
        ("Dossier de sauvegarde", ("save_dir",), "str"),
        ("Dossier playerdata", ("nbt", "playerdata"), "str"),
        ("Fichier usernamecache.json", ("nbt", "usernamecache"), "str"),
    ]

    def edit_value(label, default, typ, password=False):
        buf = str(default)
        error = False

        def render_prompt():
            s = "*" * len(buf) if password else buf
            head = Panel.fit("Modifier la configuration", box=ROUNDED)
            body = Panel.fit(f"{label} ({str(default)}): {s}", box=ROUNDED, border_style=("red" if error else "white"))
            foot = Table(show_header=False, show_lines=False, box=ROUNDED)
            foot.add_column()
            foot.add_column()
            foot.add_row(
                "[yellow]Entrée[/][grey50] : [/][cyan]Valider[/]", "[yellow]Échap[/][grey50] : [/][cyan]Annuler[/]"
            )
            return Group(head, body, foot)

        with Live(render_prompt(), console=console, refresh_per_second=30, screen=True) as lv:
            while True:
                k = read_key_ext()
                if k == "ESC":
                    return None
                if k == "ENTER":
                    try:
                        if typ == "int":
                            return int(buf)
                        if typ == "float":
                            return float(buf)
                        return buf
                    except Exception:
                        error = True
                        lv.update(render_prompt(), refresh=True)
                        continue
                if k in ("UP", "DOWN", "LEFT", "RIGHT"):
                    continue
                if k in ("\x7f", "\b"):
                    buf = buf[:-1]
                    error = False
                    lv.update(render_prompt(), refresh=True)
                    continue
                if isinstance(k, str) and len(k) == 1 and k != "\x1b":
                    buf += k
                    error = False
                    lv.update(render_prompt(), refresh=True)

    def getv(c, path):
        cur = c
        for k in path:
            cur = cur[k]
        return cur

    def setv(c, path, val):
        cur = c
        for k in path[:-1]:
            cur = cur[k]
        cur[path[-1]] = val

    conf2 = {
        "rcon": dict(conf["rcon"]),
        "exploration": dict(conf["exploration"]),
        "save_file": conf.get("save_file", "auto"),
        "save_dir": conf.get("save_dir", "saves"),
        "nbt": dict(
            conf.get(
                "nbt",
                {"playerdata": "/srv/minecraft/world/playerdata", "usernamecache": "/srv/minecraft/usernamecache.json"},
            )
        ),
    }
    sel = 0
    editing = False
    edit_buf = ""
    edit_typ = None
    edit_path = None
    cursor_on = True
    last_blink = time.time()

    def render():
        t = Table(show_header=False, show_lines=False, box=ROUNDED)
        t.add_column(justify="left")
        t.add_column(justify="left")
        for i, (name, path, _) in enumerate(fields):
            prefix = "➤ " if i == sel else "  "
            lb = prefix + (f"[yellow]{name}[/]" if i == sel else f"[cyan]{name}[/]")
            if editing and i == sel and path == edit_path:
                disp = edit_buf + ("█" if cursor_on else " ")
                v = f"[orange1]{disp}[/]"
            else:
                val = str(getv(conf2, path))
                v = f"[green]{val}[/]" if i == sel else f"[white]{val}[/]"
            t.add_row(lb, v)
        foot = Table(show_header=False, show_lines=False, box=ROUNDED)
        foot.add_column()
        foot.add_column()
        foot.add_column()
        foot.add_column()
        foot.add_column()
        foot.add_row(
            "[yellow]↑/↓[/][grey50] : [/][orange]Naviguer[/]",
            "[yellow]→[/][grey50] : [/][orange]Modifier[/]",
            "[yellow]←[/][grey50] : [/][orange]Retour[/]",
            "[yellow]Entrée[/][grey50] : [/][orange]Enregistrer[/]",
            "[yellow]Échap[/][grey50] : [/][orange]Annuler[/]",
        )
        return Group(Panel.fit("Modifier la configuration", box=ROUNDED), t, foot)

    with Live(render(), console=console, refresh_per_second=30, screen=True) as live:
        while True:
            now = time.time()
            if editing and now - last_blink >= 0.5:
                cursor_on = not cursor_on
                last_blink = now
                live.update(render(), refresh=True)

            k = read_key_ext(timeout=0.05)
            if k is None:
                continue
            if editing:
                if k == "ESC":
                    editing = False
                    live.update(render(), refresh=True)
                    continue
                if k == "ENTER":
                    try:
                        if edit_typ == "int":
                            val = int(edit_buf)
                        elif edit_typ == "float":
                            val = float(edit_buf)
                        else:
                            val = edit_buf
                        setv(conf2, edit_path, val)
                        editing = False
                        live.update(render(), refresh=True)
                    except Exception:
                        live.update(render(), refresh=True)
                    continue
                if k in ("UP", "DOWN", "LEFT", "RIGHT"):
                    continue
                if k in ("\x7f", "\b"):
                    edit_buf = edit_buf[:-1]
                    live.update(render(), refresh=True)
                    continue
                if isinstance(k, str) and len(k) == 1 and k != "\x1b":
                    edit_buf += k
                    live.update(render(), refresh=True)
                    continue
                continue
            if k == "UP":
                sel = (sel - 1) % len(fields)
                live.update(render(), refresh=True)
                continue
            if k == "DOWN":
                sel = (sel + 1) % len(fields)
                live.update(render(), refresh=True)
                continue
            if k == "LEFT":
                continue
            if k == "RIGHT":
                name, path, typ = fields[sel]
                edit_path = path
                edit_typ = typ
                edit_buf = str(getv(conf2, path))
                editing = True
                live.update(render(), refresh=True)
                continue
            if k == "ENTER":
                return conf2
            if k == "ESC":
                return None
