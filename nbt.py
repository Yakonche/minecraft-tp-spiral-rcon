#!/usr/bin/env python3
import argparse
import json
import os
import sys
from glob import glob

import nbtlib
import numpy as np

from config import load_config

FIELDS = {
    "Health",
    "Pos",
    "XpLevel",
    "XpTotal",
    "foodLevel",
    "foodSaturationLevel",
    "Score",
    "Dimension",
    "playerGameType",
    "seenCredits",
}

GAMEMODES = {0: "Survie", 1: "Créatif", 2: "Aventure", 3: "Spectateur"}


def hearts(health: float) -> str:
    full = int(health // 2)
    half = int(health % 2 >= 1)
    return "❤️" * full + ("❤️🤍" if half else "") + "🤍" * (10 - full - half)


def hunger(level: int, saturation: float = 0.0) -> str:
    full = level // 2
    half = level % 2
    sat_units = max(0, int(round(float(saturation) / 2.0)))
    sat_units = min(sat_units, full)
    return "🍖" * sat_units + "🍗" * (full - sat_units) + ("🍗🤍" if half else "") + "🤍" * (10 - full - half)


def load_usernames(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def read_file(fp):
    nbt_obj = nbtlib.load(fp)
    data = nbt_obj.unpack()
    filtered = {k: v for k, v in data.items() if k in FIELDS}
    filtered["UUID_str"] = os.path.splitext(os.path.basename(fp))[0]
    return filtered


def format_player(p: dict, names: dict) -> str:
    uuid = p.get("UUID_str", "unknown")
    name = names.get(uuid, uuid)
    health = p.get("Health", 0)
    food = p.get("foodLevel", 0)
    sat = p.get("foodSaturationLevel", 0)
    xp = p.get("XpLevel", 0)
    totalxp = p.get("XpTotal", 0)
    score = p.get("Score", 0)
    dim = p.get("Dimension", "unknown").replace("minecraft:", "")
    gm = GAMEMODES.get(p.get("playerGameType", -1), str(p.get("playerGameType")))
    seen = "✓" if p.get("seenCredits", 0) else "✗"
    pos = p.get("Pos", [0, 0, 0])
    if isinstance(pos, np.ndarray):
        pos = pos.tolist()
    pos_str = f"X={pos[0]:.1f} Y={pos[1]:.1f} Z={pos[2]:.1f}"
    return (
        f"Joueur : {name}\n"
        f"  Santé : {hearts(health)} ({health})\n"
        f"  Faim  : {hunger(food, sat)} ({food})\n"
        f"  XP    : niveau {xp} (total {totalxp})\n"
        f"  Score : {score}\n"
        f"  Monde : {dim}, Gamemode : {gm}\n"
        f"  Crédits vus : {seen}\n"
        f"  Position : {pos_str}\n"
    )


def main():
    p = argparse.ArgumentParser()
    try:
        _conf = load_config("config.json")
        _nbt = _conf.get("nbt", {})
        _def_path = _nbt.get("playerdata", "/srv/minecraft/world/playerdata")
        _def_username = _nbt.get("usernamecache", "/srv/minecraft/usernamecache.json")
    except Exception:
        _def_path = "/srv/minecraft/world/playerdata"
        _def_username = "/srv/minecraft/usernamecache.json"
    p.add_argument("path", nargs="?", default=_def_path)
    p.add_argument("--playerdata", default=None)
    p.add_argument("--usernamecache", default=_def_username)
    p.add_argument("--dims-json", action="store_true")
    args = p.parse_args()

    base_path = args.playerdata or args.path
    if os.path.isdir(base_path):
        files = sorted(glob(os.path.join(base_path, "*.dat")))
    elif os.path.isfile(base_path):
        files = [base_path]
    else:
        print("chemin introuvable", file=sys.stderr)
        sys.exit(1)

    if not files:
        print("aucun fichier .dat trouvé", file=sys.stderr)
        sys.exit(2)

    names = load_usernames(args.usernamecache)

    if args.dims_json:

        def _name_from_uuid(uuid, names):
            if isinstance(names, dict):
                return names.get(uuid) or names.get(uuid.replace("-", ""))
            if isinstance(names, list):
                for ent in names:
                    if isinstance(ent, dict):
                        k = (ent.get("uuid") or ent.get("uuidWithoutDashes") or "").replace("-", "").lower()
                        if k == uuid.replace("-", "").lower():
                            return ent.get("name") or ent.get("username")
            return None

        out = {}
        for fp in files:
            uuid = os.path.splitext(os.path.basename(fp))[0]
            name = _name_from_uuid(uuid, names) or uuid
            try:
                pdat = read_file(fp)
                dim = pdat.get("Dimension")
                if hasattr(dim, "value"):
                    dim = dim.value
                if isinstance(dim, int):
                    dim = {0: "minecraft:overworld", -1: "minecraft:the_nether", 1: "minecraft:the_end"}.get(dim)
                if name and dim:
                    out[name] = dim
            except Exception:
                pass
        print(json.dumps(out, ensure_ascii=False))
        return

    for fp in files:
        player = read_file(fp)
        print(format_player(player, names))
        print("-" * 40)


if __name__ == "__main__":
    main()
