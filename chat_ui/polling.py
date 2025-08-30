import os
import random
import re
import socket
import struct
import subprocess
import sys
import time


def _resolve_playerdata_dir(playerdata_dir: str) -> str:
    if os.path.isdir(playerdata_dir):
        return playerdata_dir
    base = os.path.dirname(os.path.dirname(playerdata_dir))
    if os.path.isfile(os.path.join(base, "server.properties")):
        try:
            with open(os.path.join(base, "server.properties"), encoding="utf-8", errors="ignore") as f:
                for ln in f:
                    m = re.match(r"^level-name\s*=\s*(.+)\s*$", ln)
                    if m:
                        cand = os.path.join(base, m.group(1), "playerdata")
                        if os.path.isdir(cand):
                            return cand
        except Exception:
            pass
    try:
        for d in os.listdir(base):
            cand = os.path.join(base, d, "playerdata")
            if os.path.isdir(cand):
                return cand
    except Exception:
        pass
    return playerdata_dir


def _run_nbt(nbt_py: str, playerdata_dir: str, usernamecache: str):
    real_dir = _resolve_playerdata_dir(playerdata_dir)
    py = sys.executable or "python3"
    cmd = [py, nbt_py, real_dir, "--usernamecache", usernamecache]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def poll_dims(stop_event, nbt_py, playerdata_dir, usernamecache, interval_s, setter):
    while not stop_event.is_set():
        try:
            p = _run_nbt(nbt_py, playerdata_dir, usernamecache)
            if p.returncode == 0 and p.stdout:
                out, cur = {}, None
                for ln in p.stdout.splitlines():
                    m1 = re.match(r"^Joueur\s*:\s*(.+)\s*$", ln)
                    if m1:
                        cur = m1.group(1).strip()
                        continue
                    m2 = re.match(r"^\s*Monde\s*:\s*([^,]+)", ln)
                    if m2 and cur:
                        out[cur] = m2.group(1).strip()
                        cur = None
                if out:
                    setter(out)
        except Exception:
            pass
        for _ in range(int(interval_s * 10)):
            if stop_event.is_set():
                break
            time.sleep(0.1)


def poll_stats(stop_event, nbt_py, playerdata_dir, usernamecache, interval_s, setter):
    while not stop_event.is_set():
        try:
            p = _run_nbt(nbt_py, playerdata_dir, usernamecache)
            players, cur = [], None
            for ln in (p.stdout or "").splitlines():
                m = re.match(r"^Joueur\s*:\s*(.+)\s*$", ln)
                if m:
                    if cur:
                        players.append(cur)
                    cur = {"name": m.group(1).strip()}
                    continue
                if cur is None:
                    continue
                m = re.match(r"^\s*Santé\s*:\s*[^(]*\(([-+]?\d+(?:\.\d+)?)\)", ln)
                if m:
                    cur["health"] = m.group(1)
                m = re.match(r"^\s*Faim\s*:\s*[^(]*\(([-+]?\d+(?:\.\d+)?)\)", ln)
                if m:
                    cur["hunger"] = m.group(1)
                m = re.match(r"^\s*XP\s*:\s*niveau\s*(\d+)", ln)
                if m:
                    cur["lvl"] = m.group(1)
                m = re.match(r"^\s*Score\s*:\s*(\d+)", ln)
                if m:
                    cur["score"] = m.group(1)
                m = re.match(r"^\s*Monde\s*:\s*([^,]+),\s*Gamemode\s*:\s*(.+)\s*$", ln)
                if m:
                    cur["dim"] = m.group(1).strip()
                    cur["gm"] = m.group(2).strip()
                m = re.match(r"^\s*Position\s*:\s*(.+)\s*$", ln)
                if m:
                    cur["pos"] = m.group(1).strip()
            if cur:
                players.append(cur)
            if players:
                setter(players)
        except Exception:
            pass
        for _ in range(int(interval_s * 10)):
            if stop_event.is_set():
                break
            time.sleep(0.1)


def _read_server_properties(base_dir):
    props = {}
    sp = os.path.join(base_dir, "server.properties")
    try:
        with open(sp, encoding="utf-8", errors="ignore") as f:
            for ln in f:
                if "=" in ln and not ln.lstrip().startswith("#"):
                    k, v = ln.split("=", 1)
                    props[k.strip()] = v.strip()
    except Exception:
        pass
    return props


def _resolve_query_target(playerdata_dir, host_override=None, port_override=None):
    base = os.path.dirname(os.path.dirname(_resolve_playerdata_dir(playerdata_dir)))
    props = _read_server_properties(base)
    host = host_override if host_override else (props.get("server-ip") or "127.0.0.1")
    port = None
    if port_override:
        port = int(port_override)
    else:
        qp = props.get("query.port")
        sp = props.get("server-port")
        if qp and qp.isdigit():
            port = int(qp)
        elif sp and sp.isdigit():
            port = int(sp)
    if port is None:
        port = 25565
    return host, port, props.get("enable-query", "").lower() == "true"


def _gs4_handshake(sock, addr):
    sid = random.randint(1, 0x7FFFFFFF)
    pkt = b"\xfe\xfd\x09" + struct.pack(">l", sid)
    sock.sendto(pkt, addr)
    data, _ = sock.recvfrom(2048)
    if not data or data[0] != 9:
        raise RuntimeError("bad handshake")
    token_str = data[5:].split(b"\x00", 1)[0]
    token = int(token_str)
    return sid, token


def _gs4_fullstat(sock, addr, sid, token):
    pkt = b"\xfe\xfd\x00" + struct.pack(">l", sid) + struct.pack(">l", token) + b"\x00\x00\x00\x00"
    sock.sendto(pkt, addr)
    data, _ = sock.recvfrom(4096)
    return data


def _parse_players(data):
    try:
        part = data.split(b"\x00\x00\x01player_\x00\x00", 1)[1]
    except Exception:
        return []
    names = [n.decode("utf-8", "ignore") for n in part.split(b"\x00") if n]
    return names


def query_players(host, port, timeout=1.5):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        sid, token = _gs4_handshake(s, (host, port))
        data = _gs4_fullstat(s, (host, port), sid, token)
    return _parse_players(data)


def poll_query(stop_event, playerdata_dir, interval_s, setter, host_override=None, port_override=None):
    last_ok = None
    while not stop_event.is_set():
        try:
            host, port, enabled = _resolve_query_target(playerdata_dir, host_override, port_override)
            if not enabled:
                pass
            else:
                names = query_players(host, port, timeout=1.5)
                setter(set(names))
                last_ok = True
        except Exception:
            if last_ok is None:
                setter(set())
            last_ok = False
        for _ in range(int(interval_s * 10)):
            if stop_event.is_set():
                break
            time.sleep(0.1)


def _max_mtime(root, extras=None):
    m = 0.0
    try:
        for dp, dn, fn in os.walk(root):
            for f in fn:
                try:
                    t = os.path.getmtime(os.path.join(dp, f))
                    if t > m:
                        m = t
                except Exception:
                    pass
    except Exception:
        pass
    for p in extras or []:
        try:
            t = os.path.getmtime(p)
            if t > m:
                m = t
        except Exception:
            pass
    return m


def poll_stats_dims(
    stop_event, nbt_py, playerdata_dir, usernamecache, interval_s, setter_stats, setter_dims, only_on_change=True
):
    last_mtime = 0.0
    while not stop_event.is_set():
        try:
            real_dir = _resolve_playerdata_dir(playerdata_dir)
            cur_mtime = _max_mtime(real_dir, [usernamecache])
            run_now = (not only_on_change) or cur_mtime > last_mtime
            if run_now:
                p = _run_nbt(nbt_py, playerdata_dir, usernamecache)
                players, cur = [], None
                for ln in (p.stdout or "").splitlines():
                    m = re.match(r"^Joueur\s*:\s*(.+)\s*$", ln)
                    if m:
                        if cur:
                            players.append(cur)
                        cur = {"name": m.group(1).strip()}
                        continue
                    if cur is None:
                        continue
                    m = re.match(r"^\s*Santé\s*:\s*([^\(]+)\(", ln)
                    if m:
                        cur["health"] = m.group(1).strip()
                    m = re.match(r"^\s*Faim\s*:\s*([^\(]+)\(", ln)
                    if m:
                        cur["hunger"] = m.group(1).strip()
                    m = re.match(r"^\s*XP\s*:\s*niveau\s*(\d+)", ln)
                    if m:
                        cur["lvl"] = m.group(1)
                    m = re.match(r"^\s*Score\s*:\s*(\d+)", ln)
                    if m:
                        cur["score"] = m.group(1)
                    m = re.match(r"^\s*Monde\s*:\s*([^,]+),\s*Gamemode\s*:\s*(.+)\s*$", ln)
                    if m:
                        cur["dim"] = m.group(1).strip()
                        cur["gm"] = m.group(2).strip()
                    m = re.match(r"^\s*Position\s*:\s*(.+)\s*$", ln)
                    if m:
                        cur["pos"] = m.group(1).strip()
                if cur:
                    players.append(cur)
                if players:
                    setter_stats(players)
                    dims = {p["name"]: p.get("dim", "") for p in players if p.get("name")}
                    if dims:
                        setter_dims(dims)
                last_mtime = cur_mtime
        except Exception:
            pass
        for _ in range(int(interval_s * 10)):
            if stop_event.is_set():
                break
            time.sleep(0.1)


def _parse_list_names(resp):
    if not resp:
        return []
    m = re.search(r":\s*(.+)$", resp.strip())
    if not m:
        return []
    names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    return names


def _to_gm(n):
    try:
        v = int(re.findall(r"-?\d+", n)[0])
    except Exception:
        return ""
    return {0: "Survival", 1: "Creative", 2: "Adventure", 3: "Spectator"}.get(v, "")


def _parse_data_map(resp):
    out = {}
    for ln in (resp or "").splitlines():
        m = re.match(r"^([A-Za-z0-9_]{1,16}) has the following entity data: (.+)$", ln.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _fmt_pos(s):
    m = re.findall(r"[-+]?\d+(?:\.\d+)?", s)
    if len(m) >= 3:
        return f"X={m[0]} Y={m[1]} Z={m[2]}"
    return ""


def poll_stats_rcon(stop_event, rcon, interval_s, setter_stats, setter_dims):
    while not stop_event.is_set():
        try:
            names = _parse_list_names(rcon.cmd("list"))
            if not names:
                setter_stats([])
                setter_dims({})
            else:
                pos = _parse_data_map(rcon.cmd("execute as @a run data get entity @s Pos"))
                hp = _parse_data_map(rcon.cmd("execute as @a run data get entity @s Health"))
                hunger = _parse_data_map(rcon.cmd("execute as @a run data get entity @s foodLevel"))
                lvl = _parse_data_map(rcon.cmd("execute as @a run data get entity @s XpLevel"))
                gm = _parse_data_map(rcon.cmd("execute as @a run data get entity @s playerGameType"))
                dim = _parse_data_map(rcon.cmd("execute as @a run data get entity @s Dimension"))
                players = []
                dims = {}
                for n in names:
                    p = dict(cache_nbt.get(n, {}))
                    p["name"] = n
                    if n in hp:
                        p["health"] = re.findall(r"[-+]?\d+(?:\.\d+)?", hp[n])[0]
                    if n in hunger:
                        p["hunger"] = re.findall(r"-?\d+", hunger[n])[0]
                    if n in lvl:
                        p["lvl"] = re.findall(r"-?\d+", lvl[n])[0]
                    if n in gm:
                        p["gm"] = _to_gm(gm[n])
                    if n in dim:
                        p["dim"] = dim[n]
                    if n in pos:
                        p["pos"] = _fmt_pos(pos[n])
                    if "dim" in p and p["dim"]:
                        dims[n] = p["dim"]
                    players.append(p)
                setter_stats(players)
                setter_dims(dims)
        except Exception:
            pass
        for _ in range(int(interval_s * 10)):
            if stop_event.is_set():
                break
            time.sleep(0.1)


def _rcon_cmd(rcon, s):
    fn = getattr(rcon, "cmd", None) or getattr(rcon, "command", None) or getattr(rcon, "send", None)
    return fn(s) if fn else ""


def _parse_list_names(resp):
    if not resp:
        return []
    m = re.search(r":\s*(.+)$", resp.strip())
    if not m:
        return []
    return [n.strip() for n in m.group(1).split(",") if n.strip()]


def _parse_data_map(resp):
    out = {}
    for ln in (resp or "").splitlines():
        m = re.match(r"^([A-Za-z0-9_]{1,16}) has the following entity data: (.+)$", ln.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _to_gm(n):
    try:
        v = int(re.findall(r"-?\d+", n)[0])
    except Exception:
        return ""
    return {0: "Survival", 1: "Creative", 2: "Adventure", 3: "Spectator"}.get(v, "")


def _fmt_pos(s):
    m = re.findall(r"[-+]?\d+(?:\.\d+)?", s)
    if len(m) >= 3:
        return f"X={m[0]} Y={m[1]} Z={m[2]}"
    return ""


def _read_usernamecache_names(usernamecache):
    names = set()
    try:
        import json

        with open(usernamecache, encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        if isinstance(data, list):
            for it in data:
                n = it.get("name")
                if isinstance(n, str) and n:
                    names.add(n)
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str) and v and len(v) <= 16:
                    names.add(v)
                elif isinstance(v, dict):
                    n = v.get("name") or v.get("Name")
                    if isinstance(n, str) and n:
                        names.add(n)
                elif isinstance(k, str) and len(k) <= 16:
                    names.add(k)
    except Exception:
        pass
    return names


def _read_nbt_players(nbt_py, playerdata_dir, usernamecache):
    p = _run_nbt(nbt_py, playerdata_dir, usernamecache)
    players, cur = [], None
    for ln in (p.stdout or "").splitlines():
        m = re.match(r"^Joueur\s*:\s*(.+)\s*$", ln)
        if m:
            if cur:
                players.append(cur)
            cur = {"name": m.group(1).strip()}
            continue
        if cur is None:
            continue
        m = re.match(r"^\s*Santé\s*:\s*([^\(]+)\(", ln)
        if m:
            cur["health"] = m.group(1).strip()
        m = re.match(r"^\s*Faim\s*:\s*([^\(]+)\(", ln)
        if m:
            cur["hunger"] = m.group(1).strip()
        m = re.match(r"^\s*XP\s*:\s*niveau\s*(\d+)", ln)
        if m:
            cur["lvl"] = m.group(1)
        m = re.match(r"^\s*Score\s*:\s*(\d+)", ln)
        if m:
            cur["score"] = m.group(1)
        m = re.match(r"^\s*Monde\s*:\s*([^,]+),\s*Gamemode\s*:\s*(.+)\s*$", ln)
        if m:
            cur["dim"] = m.group(1).strip()
            cur["gm"] = m.group(2).strip()
        m = re.match(r"^\s*Position\s*:\s*(.+)\s*$", ln)
        if m:
            cur["pos"] = m.group(1).strip()
    if cur:
        players.append(cur)
    return {p["name"]: p for p in players if p.get("name")}


def _max_mtime(root, extras=None):
    m = 0.0
    try:
        for dp, dn, fn in os.walk(root):
            for f in fn:
                try:
                    t = os.path.getmtime(os.path.join(dp, f))
                    if t > m:
                        m = t
                except Exception:
                    pass
    except Exception:
        pass
    for pth in extras or []:
        try:
            t = os.path.getmtime(pth)
            if t > m:
                m = t
        except Exception:
            pass
    return m


def poll_stats_hybrid(
    stop_event, rcon, nbt_py, playerdata_dir, usernamecache, interval_s, setter_stats, setter_dims, nbt_refresh_s=30
):
    cache_nbt = {}
    last_mtime = 0.0
    last_nbt_time = 0.0
    first = True
    while not stop_event.is_set():
        now = time.time()
        try:
            real_dir = _resolve_playerdata_dir(playerdata_dir)
            cur_mtime = _max_mtime(real_dir, [usernamecache])
            need_nbt = first or (cur_mtime > last_mtime) or (now - last_nbt_time >= nbt_refresh_s)
            if need_nbt:
                cache_nbt = _read_nbt_players(nbt_py, playerdata_dir, usernamecache)
                last_mtime = cur_mtime
                last_nbt_time = now
                first = False
            names_online = _parse_list_names(_rcon_cmd(rcon, "list")) if rcon else []
            pos = _parse_data_map(_rcon_cmd(rcon, "execute as @a run data get entity @s Pos")) if names_online else {}
            hp = _parse_data_map(_rcon_cmd(rcon, "execute as @a run data get entity @s Health")) if names_online else {}
            hunger = (
                _parse_data_map(_rcon_cmd(rcon, "execute as @a run data get entity @s foodLevel"))
                if names_online
                else {}
            )
            lvl = (
                _parse_data_map(_rcon_cmd(rcon, "execute as @a run data get entity @s XpLevel")) if names_online else {}
            )
            gm = (
                _parse_data_map(_rcon_cmd(rcon, "execute as @a run data get entity @s playerGameType"))
                if names_online
                else {}
            )
            dim = (
                _parse_data_map(_rcon_cmd(rcon, "execute as @a run data get entity @s Dimension"))
                if names_online
                else {}
            )
            names_all = set(cache_nbt.keys()) | set(names_online) | _read_usernamecache_names(usernamecache)
            players = []
            dims = {}
            for n in sorted(names_all):
                p = {}
                src = cache_nbt.get(n, {})
                p.update(src)
                p["name"] = n
                if n in hp:
                    v = re.findall(r"[-+]?\d+(?:\.\d+)?", hp[n])
                    if v:
                        p["health"] = v[0]
                if n in hunger:
                    v = re.findall(r"-?\d+", hunger[n])
                    if v:
                        p["hunger"] = v[0]
                if n in lvl:
                    v = re.findall(r"-?\d+", lvl[n])
                    if v:
                        p["lvl"] = v[0]
                if n in gm:
                    p["gm"] = _to_gm(gm[n])
                if n in dim:
                    dv = dim[n].strip('"')
                    if dv.startswith('"') and dv.endswith('"'):
                        dv = dv[1:-1]
                    p["dim"] = dv.strip('"')
                if n in pos:
                    p["pos"] = _fmt_pos(pos[n])
                if "dim" in p:
                    dims[n] = p["dim"]
                players.append(p)
            setter_stats(players)
            setter_dims(dims)
        except Exception:
            pass
        for _ in range(int(interval_s * 10)):
            if stop_event.is_set():
                break
            time.sleep(0.1)
