# chat.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys, time, select, termios, tty, re, shutil, socket, struct, threading
from collections import deque
from typing import Deque, List, Tuple
from rich import print
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.box import ROUNDED, DOUBLE

CHAT_RE = re.compile(r'^\[(\d{2}:\d{2}:\d{2})\]\s+\[.*?\]:\s+<([^>]+)>\s+(.*)$')
JOINLEAVE_RE = re.compile(r'^\[(\d{2}:\d{2}:\d{2})\]\s+\[.*?\]:\s+(.*? (?:joined|left) the game)$')
SERVER_RE = re.compile(r'^\[(\d{2}:\d{2}:\d{2})\]\s+\[.*?\]:\s+\[Server\]\s+(.*)$')
RCON_SAY_RE = re.compile(r'^\[(\d{2}:\d{2}:\d{2})\]\s+\[.*?\]:\s+\[(?:Rcon|Server)\]\s+(.*)$')

STATIC_CMDS = {
    "help","list","say","tellraw","msg","teammsg","me",
    "op","deop","whitelist","ban","ban-ip","banlist","pardon","pardon-ip","kick",
    "save-all","save-on","save-off","stop","setidletimeout","reload","datapack","seed","debug","jfr",
    "gamemode","defaultgamemode","gamerule",
    "give","clear","effect","enchant","experience","xp","attribute",
    "advancement","recipe","loot","title","playsound","stopsound","particle",
    "tag","team","scoreboard","summon","kill","damage","ride","spectate","trigger",
    "time","weather","difficulty",
    "teleport","tp","spreadplayers","setworldspawn","spawnpoint","worldborder",
    "setblock","fill","clone","place","locate","function","schedule","data","item","execute",
}
ALIASES = {"xp":"experience","tp":"teleport"}

DIFFICULTIES = ["peaceful","easy","normal","hard"]
WEATHERS = ["clear","rain","thunder"]
GAMEMODES = ["survival","creative","adventure","spectator"]
SCOREBOARD = {
    "players": ["set","add","remove","reset","get","enable","list","operation"],
    "objectives": ["add","remove","list","setdisplay","modify"]
}
TEAM = ["add","remove","modify","join","leave","list","empty"]
TITLE = ["title","subtitle","actionbar","clear","reset","times"]
TIME = ["set","add","query"]
TELEPORT_TEMPLATES = [
    "teleport <target> <x> <y> <z>",
    "teleport <target> <destination>",
    "teleport <x> <y> <z>",
]
EXECUTE_SUBS = ["as","at","in","positioned","rotated","facing","anchored","align","if","unless","store","run"]
DATA_SUBS = ["get","modify","merge","remove"]
DATAPACK_SUBS = ["enable","disable","list","move"]
EFFECT_SUBS = ["give","clear"]
EXPERIENCE_SUBS = ["add","set","query"]
LOOT_SUBS = ["give","insert","replace","spawn","fish","kill"]
LOCATE_SUBS = ["structure","biome","poi"]
ITEM_SUBS = ["replace","modify"]
WORLDBORDER_SUBS = ["add","set","center","damage","get","warning","lerp"]
ATTRIBUTE_SUBS = ["base","get","modifier"]
ADVANCEMENT_SUBS = ["grant","revoke","test"]
RECIPE_SUBS = ["give","take"]

COMMAND_TREE = {
    "teleport": {"subs": [], "templates": TELEPORT_TEMPLATES},
    "tp": {"subs": [], "templates": TELEPORT_TEMPLATES},
    "time": {"subs": TIME, "templates": ["time set <noon|midnight|value>", "time add <value>", "time query <day|daytime|gametime>"]},
    "weather": {"subs": WEATHERS},
    "difficulty": {"subs": DIFFICULTIES},
    "gamemode": {"subs": GAMEMODES, "templates": [f"gamemode <{'|'.join(GAMEMODES)}> <target>"]},
    "gamerule": {"subs": [
        "doDaylightCycle","doWeatherCycle","keepInventory","doMobSpawning","doImmediateRespawn",
        "showDeathMessages","doFireTick","doInsomnia","doLimitedCrafting","commandBlockOutput",
        "doTileDrops","doEntityDrops","mobGriefing","naturalRegeneration","reducedDebugInfo",
        "sendCommandFeedback","universalAnger","announceAdvancements","drowningDamage","fallDamage",
        "fireDamage","freezeDamage","playersSleepingPercentage","maxCommandChainLength","randomTickSpeed",
        "spawnRadius","tntExplosionDropDecay","snowAccumulationHeight","blockExplosionDropDecay","projectilesCanBreakBlocks"
    ]},
    "execute": {"subs": EXECUTE_SUBS},
    "data": {"subs": DATA_SUBS},
    "datapack": {"subs": DATAPACK_SUBS},
    "effect": {"subs": EFFECT_SUBS},
    "experience": {"subs": EXPERIENCE_SUBS},
    "xp": {"subs": EXPERIENCE_SUBS},
    "loot": {"subs": LOOT_SUBS},
    "locate": {"subs": LOCATE_SUBS},
    "item": {"subs": ITEM_SUBS},
    "worldborder": {"subs": WORLDBORDER_SUBS},
    "attribute": {"subs": ATTRIBUTE_SUBS},
    "advancement": {"subs": ADVANCEMENT_SUBS},
    "recipe": {"subs": RECIPE_SUBS},
    "scoreboard": {"subs": list(SCOREBOARD.keys())},
    "team": {"subs": TEAM},
    "title": {"subs": TITLE},
}

class RconClientInline:
    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0):
        self.host = host; self.port = int(port); self.password = password
        self.timeout = float(timeout); self.sock: socket.socket | None = None
        self._rid = 0
    def _pack(self, req_id: int, req_type: int, body: str) -> bytes:
        payload = body.encode("utf-8") + b"\x00\x00"
        return struct.pack("<iii", len(payload)+8, req_id, req_type) + payload
    def _recv_packet(self) -> tuple[int,int,str]:
        data = self.sock.recv(4)
        if len(data) < 4: raise RuntimeError("RCON : réponse incomplète")
        (length,) = struct.unpack("<i", data)
        packet = b""
        while len(packet) < length:
            chunk = self.sock.recv(length - len(packet))
            if not chunk: break
            packet += chunk
        if len(packet) < length: raise RuntimeError("RCON : trame tronquée")
        req_id, req_type = struct.unpack("<ii", packet[:8])
        body = packet[8:-2].decode("utf-8", errors="replace")
        return req_id, req_type, body
    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self._rid += 1
        self.sock.sendall(self._pack(self._rid, 3, self.password))
        rid, rtype, _ = self._recv_packet()
        if rid != self._rid or rtype == -1:
            self.close(); raise RuntimeError("Auth RCON échouée")
    def cmd(self, command: str) -> str:
        if not self.sock: raise RuntimeError("Non connecté")
        self._rid += 1
        self.sock.sendall(self._pack(self._rid, 2, command))
        chunks = []
        end_at = time.time() + self.timeout
        while True:
            try:
                rid, _, body = self._recv_packet()
                if rid == self._rid: chunks.append(body)
                if time.time() > end_at: break
                self.sock.settimeout(0.12)
            except socket.timeout:
                break
            finally:
                self.sock.settimeout(self.timeout)
        return "\n".join(chunks).strip()
    def close(self):
        try:
            if self.sock: self.sock.close()
        finally:
            self.sock = None

def _read_key(timeout=0.06) -> str | None:
    r, _, _ = select.select([sys.stdin], [], [], timeout)
    if not r: return None
    ch = os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
    if ch != "\x1b": return ch
    seq = ""; end = time.time()+0.06
    while time.time() < end:
        r, _, _ = select.select([sys.stdin], [], [], max(0, end-time.time()))
        if not r: break
        seq += os.read(sys.stdin.fileno(), 1).decode(errors="ignore")
        if len(seq) >= 2: break
    if seq.startswith("["):
        m = seq[1:2]; return {"A":"UP","B":"DOWN","C":"RIGHT","D":"LEFT"}.get(m,"ESC")
    return "ESC"

class RawInput:
    def __init__(self, stream): self.stream = stream; self.fd = stream.fileno(); self.old=None
    def __enter__(self): self.old = termios.tcgetattr(self.fd); tty.setcbreak(self.fd); return self
    def __exit__(self, exc_type, exc, tb):
        if self.old is not None: termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

def _load_commands() -> List[str]:
    out = set(STATIC_CMDS)|set(COMMAND_TREE.keys())|set(ALIASES.keys())
    return sorted(out, key=str.lower)

def _read_backlog(path: str, max_lines: int = 12000) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            dq = deque(f, maxlen=max_lines)
        return [ln.rstrip("\n") for ln in dq]
    except FileNotFoundError:
        return []

def _tail_follow(path: str):
    f = None; ino=None; last_size=0
    while True:
        try:
            if f is None:
                try:
                    f = open(path, "r", encoding="utf-8", errors="replace")
                    ino = os.fstat(f.fileno()).st_ino
                    f.seek(0, os.SEEK_END); last_size = f.tell()
                except FileNotFoundError:
                    yield None; time.sleep(0.05); continue
            line = f.readline()
            if line:
                last_size = f.tell(); yield line.rstrip("\n"); continue
            time.sleep(0.03)
            try:
                st = os.stat(path)
                if st.st_ino != ino or st.st_size < last_size:
                    f.close(); f=None
            except FileNotFoundError:
                if f: f.close(); f=None
            yield None
        except KeyboardInterrupt:
            return

def _escape_markup(s: str) -> str:
    return s.replace("[", r"\[").replace("]", r"\]")

def _md_inline_to_rich(s: str) -> str:
    s = _escape_markup(s)
    s = re.sub(r'\\\[(.*?)\\\]\\\((https?://[^\s)]+)\\\)', r'[link=\2]\1[/link]', s)
    s = re.sub(r'`([^`]+)`', r'[bold bright_black]\1[/bold bright_black]', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"[bold]\1[/bold]", s)
    s = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"[italic]\1[/italic]", s)
    s = re.sub(r"__(.+?)__", r"[underline]\1[/underline]", s)
    s = re.sub(r"~~(.+?)~~", r"[strike]\1[/strike]", s)
    return s

def _fmt_chat_line(raw: str) -> Text | None:
    m = CHAT_RE.match(raw)
    if m:
        ts, user, msg = m.group(1), m.group(2), _md_inline_to_rich(m.group(3))
        t = Text.assemble(
            Text("[", style="dim"), Text(ts, style="white"), Text("] ", style="dim"),
            Text(user, style="bold cyan"), Text(" : ", style="dim"),
        )
        t.append_text(Text.from_markup(msg, style="white"))
        t.no_wrap = True
        return t
    m = RCON_SAY_RE.match(raw)
    if m:
        ts, body = m.group(1), _md_inline_to_rich(m.group(2))
        t = Text.assemble(
            Text("[", style="dim"), Text(ts, style="white"), Text("] ", style="dim"),
            Text("RCON", style="bold magenta"), Text(" : ", style="dim"),
        )
        t.append_text(Text.from_markup(body, style="white"))
        t.no_wrap = True
        return t
    m = JOINLEAVE_RE.match(raw)
    if m:
        ts, body = m.group(1), _md_inline_to_rich(m.group(2))
        t = Text.assemble(Text("[", style="dim"), Text(ts, style="white"), Text("] ", style="dim"))
        t.append_text(Text.from_markup(body, style="yellow"))
        t.no_wrap = True
        return t
    m = SERVER_RE.match(raw)
    if m:
        ts, body = m.group(1), _md_inline_to_rich(m.group(2))
        t = Text.assemble(Text("[", style="dim"), Text(ts, style="white"), Text("] ", style="dim"))
        t.append_text(Text.from_markup(body, style="white"))
        t.no_wrap = True
        return t
    return None

def _tokenize(buf: str) -> List[str]:
    s = buf.strip()
    if s.startswith("/"): s = s[1:]
    return s.split() if s else []

def _canon(cmd: str) -> str:
    c = cmd.lower()
    return ALIASES.get(c, c)

def _prefix_filter(candidates: List[str], prefix: str) -> List[str]:
    pref = prefix.lower()
    if not pref: return candidates
    hits = [c for c in candidates if c.lower().startswith(pref)]
    return hits if hits else [c for c in candidates if pref in c.lower()]

def _suggest(cmds: List[str], buf: str) -> Tuple[List[str], List[str]]:
    toks = _tokenize(buf)
    if not toks: return (sorted(cmds)[:30], [])
    base = toks[0]
    if len(toks) == 1 and not buf.endswith(" "):
        roots = _prefix_filter(cmds, base)
        return (roots[:30], [])
    cmd = _canon(base); node = COMMAND_TREE.get(cmd)
    if node:
        if cmd == "scoreboard" and len(toks) >= 2:
            if not buf.endswith(" "):
                subs = _prefix_filter(list(SCOREBOARD.keys()), toks[1]); return (subs[:30], [])
            if len(toks) >= 3:
                ops = SCOREBOARD.get(toks[1].lower(), []); subs = _prefix_filter(ops, toks[2] if len(toks)>=3 else ""); return (subs[:30], [])
        subs = list(node.get("subs") or [])
        if subs and not buf.endswith(" "): subs = _prefix_filter(subs, toks[1] if len(toks)>=2 else "")
        else: subs = []
        tips = node.get("templates") or []
        return (subs[:30], tips[:6])
    return ([], [])

def _autocomplete(buf: str, suggestions: List[str], cycle: dict) -> str:
    if not suggestions: cycle.clear(); return buf
    raw = buf.strip(); lead = buf[:len(buf)-len(raw)]
    has_slash = raw.startswith("/")
    if has_slash: raw = raw[1:]; lead += "/"
    if buf.endswith(" "):
        choice = suggestions[cycle.get("idx", 0) % len(suggestions)]; cycle["idx"] = (cycle.get("idx", 0)+1) % len(suggestions)
        return buf + choice + " "
    parts = raw.split(); cur_idx = max(0, len(parts)-1)
    prefix = parts[cur_idx] if parts else ""
    key = (cur_idx, prefix.lower())
    if cycle.get("key") != key: cycle["key"] = key; cycle["idx"] = 0
    choice = suggestions[cycle["idx"] % len(suggestions)]; cycle["idx"] = (cycle["idx"]+1) % len(suggestions)
    parts[cur_idx] = choice
    return lead + " ".join(parts) + (" " if cur_idx == 0 else "")

def _outer_frame(content: Group, width: int) -> Panel:
    return Panel(content, box=DOUBLE, width=width)

def _ui(chat: Deque[Text], prompt: str, sugg: List[str], connected: bool, width: int, blink: bool) -> Panel:
    chat_tbl = Table.grid(expand=True); chat_tbl.add_column(ratio=1, no_wrap=False)
    for line in list(chat)[-30:]: chat_tbl.add_row(line)
    top = Panel(chat_tbl, title="Chat (logs)", box=ROUNDED, width=width-4)

    status = Text("Connecté RCON" if connected else "Hors ligne", style=("green" if connected else "red"))
    cmd_help = Text("Commandes : [Tab]=Auto-completion [F5]=Recharger [Q/Esc]=Quitter", style="dim")
    sug_line = Text("Suggestions : ", style="dim")
    if sugg: sug_line += Text(" · ".join(sugg[:16]), style="yellow")

    cursor = "█" if blink else " "
    input_line = Text(prompt, style="white", no_wrap=True)
    input_line.append(cursor, style="white")

    bot = Panel(
        Group(status, cmd_help, sug_line, Text(""), input_line),
        title="Commande libre + Chat", box=ROUNDED, width=width-4
    )

    return _outer_frame(Group(top, bot), width)

def _send_async(client: RconClientInline, command: str):
    def _run():
        try:
            client.cmd(command)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

def run_chat_console(conf: dict, rc_unused=None) -> None:
    logs_path = conf.get("logs_path") or "/srv/minecraft/logs/latest.log"
    host = conf.get("rcon", {}).get("host"); port = conf.get("rcon", {}).get("port")
    password = conf.get("rcon", {}).get("password"); timeout = conf.get("rcon", {}).get("timeout", 5.0)

    client = None; connected = False
    if host and port and password:
        try:
            client = RconClientInline(str(host), int(port), str(password), float(timeout))
            client.connect(); connected = True
        except Exception as e:
            print(f"[red]RCON OFFLINE : {e}[/red]"); client = None; connected = False

    cmds = _load_commands()
    chat: Deque[Text] = deque(maxlen=16000)
    for ln in _read_backlog(logs_path, max_lines=12000):
        t = _fmt_chat_line(ln)
        if t: chat.append(t)
    tail = _tail_follow(logs_path)

    width = max(70, min(int(shutil.get_terminal_size((120, 40)).columns * 0.95), 180))
    buf = ""; hist: List[str] = []; hist_i = 0; cycle_state: dict = {}

    try:
        with Live(refresh_per_second=20, screen=False) as live, RawInput(sys.stdin):
            while True:
                pulled = 0
                while pulled < 80:
                    line = next(tail)
                    if line is None: break
                    t = _fmt_chat_line(line)
                    if t: chat.append(t)
                    pulled += 1

                suggestions, _ = _suggest(cmds, buf)
                blink = bool(int(time.time()*2) % 2)
                live.update(_ui(chat, buf, suggestions, connected, width, blink))

                k = _read_key(timeout=0.06)
                if not k: continue
                if k in ("\r","\n"):
                    s = buf.strip()
                    if s:
                        hist.append(buf); hist_i = len(hist); cycle_state.clear()
                        send = s[1:] if s.startswith("/") else (s if (s.split()[0] in cmds) else f"say {s}")
                        if connected and client:
                            _send_async(client, send)
                        else:
                            chat.append(Text(f"[OFFLINE] {send}", style="yellow"))
                    buf = ""
                elif k == "\t":
                    buf = _autocomplete(buf, suggestions, cycle_state)
                elif k.lower() == "q" or k == "ESC":
                    break
                elif k == "\x7f":
                    if buf: buf = buf[:-1]; cycle_state.clear()
                elif k == "UP":
                    if hist:
                        hist_i = max(0, hist_i-1); buf = hist[hist_i]; cycle_state.clear()
                elif k == "DOWN":
                    if hist:
                        hist_i = min(len(hist), hist_i+1); buf = hist[hist_i] if hist_i < len(hist) else ""; cycle_state.clear()
                elif k == "\x1b[15~":
                    cycle_state.clear()
                else:
                    if 0x20 <= ord(k) <= 0x7E: buf += k
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if client: client.close()
        except Exception:
            pass
