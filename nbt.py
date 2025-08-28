#!/usr/bin/env python3
import argparse, os, sys, json
from glob import glob
import nbtlib
import numpy as np

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

def hunger(level: int) -> str:
    full = level // 2
    half = level % 2
    return "🍗" * full + ("🍗🤍" if half else "") + "🤍" * (10 - full - half)

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
    xp = p.get("XpLevel", 0)
    totalxp = p.get("XpTotal", 0)
    score = p.get("Score", 0)
    dim = p.get("Dimension", "unknown").replace("minecraft:", "")
    gm = GAMEMODES.get(p.get("playerGameType", -1), str(p.get("playerGameType")))
    seen = "✓" if p.get("seenCredits", 0) else "✗"
    pos = p.get("Pos", [0,0,0])
    if isinstance(pos, np.ndarray):
        pos = pos.tolist()
    pos_str = f"X={pos[0]:.1f} Y={pos[1]:.1f} Z={pos[2]:.1f}"
    return (
        f"Joueur: {name}\n"
        f"  Santé : {hearts(health)} ({health})\n"
        f"  Faim  : {hunger(food)} ({food})\n"
        f"  XP    : niveau {xp} (total {totalxp})\n"
        f"  Score : {score}\n"
        f"  Monde : {dim}, Gamemode: {gm}\n"
        f"  Crédits vus : {seen}\n"
        f"  Position : {pos_str}\n"
    )

def main():
    p = argparse.ArgumentParser()
    p.add_argument("path", nargs="?", default="/srv/minecraft/world/playerdata")
    p.add_argument("--usernamecache", default="/srv/minecraft/usernamecache.json")
    args = p.parse_args()

    if os.path.isdir(args.path):
        files = sorted(glob(os.path.join(args.path, "*.dat")))
    elif os.path.isfile(args.path):
        files = [args.path]
    else:
        print("chemin introuvable", file=sys.stderr); sys.exit(1)

    if not files:
        print("aucun fichier .dat trouvé", file=sys.stderr); sys.exit(2)

    names = load_usernames(args.usernamecache)

    for fp in files:
        player = read_file(fp)
        print(format_player(player, names))
        print("-" * 40)

if __name__ == "__main__":
    main()
