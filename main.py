#!/usr/bin/env python3
from __future__ import annotations

import os
import select
import sys
import termios
import tty

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt
from rich.table import Table

from chat import run_chat_console
from config import compute_save_path, load_config, save_config
from config_menu import edit_config
from control import run_free_control
from rcon_client import RconClient
from spiral import rebuild_state_from_steps
from state import SaveManager, SpiralState
from tui import run_loop

console = Console()


def read_key(allowed: set[str] | None = None, timeout: float | None = None) -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            r, _, _ = select.select([sys.stdin], [], [], timeout)
            if not r:
                continue
            ch = os.read(fd, 1).decode(errors="ignore")
            if not allowed or ch in allowed or ch.lower() in allowed:
                return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def read_key_ext(timeout: float | None = None) -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            r, _, _ = select.select([sys.stdin], [], [], timeout)
            if not r:
                return None
            b = os.read(fd, 1)
            if b == b"\x1b":
                r2, _, _ = select.select([sys.stdin], [], [], 0.02)
                if r2:
                    seq = os.read(fd, 2)
                    if seq == b"[A":
                        return "UP"
                    if seq == b"[B":
                        return "DOWN"
                    if seq == b"[C":
                        return "RIGHT"
                    if seq == b"[D":
                        return "LEFT"
                return "ESC"
            if b in (b"\r", b"\n"):
                return "ENTER"
            try:
                return b.decode(errors="ignore")
            except Exception:
                continue
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def banner():
    console.print(
        Panel.fit(
            "[bold cyan]RCON Spiral Explorer[/bold cyan] — Exploration automatique en spirale carrée", box=ROUNDED
        )
    )


def show_config(conf):
    t = Table(title="Configuration", show_lines=False, show_header=False, box=ROUNDED)
    t.add_column(justify="left")
    t.add_column(justify="right")
    t.add_row("RCON host", str(conf["rcon"]["host"]))
    t.add_row("RCON port", str(conf["rcon"]["port"]))
    t.add_row("RCON timeout (s)", str(conf["rcon"]["timeout"]))
    e = conf["exploration"]
    t.add_row("Joueur", e["player"])
    t.add_row("Dimension", e["dimension"])
    t.add_row("Hauteur (Y=)", str(e["y"]))
    t.add_row("Chunks", str(e["chunks"]))
    t.add_row("Spawn (X)", str(e["spawn_x"]))
    t.add_row("Spawn (Z)", str(e["spawn_z"]))
    t.add_row("Intervalle (s)", str(e["interval"]))
    t.add_row("/tp max", str(e["max_tps"]))
    t.add_row("Dossier playerdata", str(conf.get("nbt", {}).get("playerdata", "/srv/minecraft/world/playerdata")))
    t.add_row("usernamecache.json", str(conf.get("nbt", {}).get("usernamecache", "/srv/minecraft/usernamecache.json")))
    console.print(t)


def build_state(conf) -> SpiralState:
    e = conf["exploration"]
    return SpiralState(
        player=e["player"],
        dimension=e["dimension"],
        y=int(e["y"]),
        chunk_step=int(e["chunks"]),
        step_blocks=int(e["chunks"]) * 16,
        spawn_x=int(e["spawn_x"]),
        spawn_z=int(e["spawn_z"]),
        current_x=int(e["spawn_x"]),
        current_z=int(e["spawn_z"]),
        interval_s=float(e["interval"]),
        max_tps=(None if int(e["max_tps"]) == -1 else int(e["max_tps"])),
        host=str(conf["rcon"]["host"]),
        port=int(conf["rcon"]["port"]),
    )


def connect_rcon(conf, dry_run=False):
    rc = RconClient(
        host=str(conf["rcon"]["host"]),
        port=int(conf["rcon"]["port"]),
        password=str(conf["rcon"]["password"]),
        timeout=float(conf["rcon"]["timeout"]),
        dry_run=dry_run,
    )
    if dry_run:
        console.print("[yellow]Mode simulation activé (aucune commande n'est envoyée au serveur)[/yellow]\n")
        return rc

    console.print("[dim]Connexion RCON… (Ctrl+C pour annuler)[/dim]")
    try:
        rc.connect()
        try:
            rc.cmd("list")
        except Exception:
            pass
    except KeyboardInterrupt:
        console.print("\n[yellow]Connexion annulée.[/yellow]\n")
        try:
            rc.close()
        except Exception:
            pass
        return None
    except Exception as e:
        console.print(f"[red]Connexion RCON impossible : {e}[/red]\n")
        try:
            rc.close()
        except Exception:
            pass
        return None

    console.print("[green]Connexion RCON OK[/green]\n")
    return rc


def run_exploration(conf, reset=False, dry_run=False):
    state = build_state(conf)
    save_path = compute_save_path(conf)
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    save = SaveManager(save_path)
    if not reset and save.exists():
        try:
            state = save.load()
            console.print(f"[green]Sauvegarde chargée[/green] (TP effectués : {state.step_index})")
        except Exception as e:
            console.print(f"[yellow]Impossible de charger la sauvegarde : {e}. Reprise à zéro.[/yellow]")
    rc = connect_rcon(conf, dry_run=dry_run)
    if rc is None:
        return
    try:
        while True:
            action = run_loop(state, save, rc)
            if action == "CONTROL":
                try:
                    run_free_control(conf, rc)
                except KeyboardInterrupt:
                    pass
                continue
            break
    except KeyboardInterrupt:
        console.print("\n[bold]Interruption[/bold] — sauvegarde et sortie…")
        SaveManager(save_path).save(state)
    finally:
        rc.close()


def rebuild_save(conf):
    n = IntPrompt.ask("Nombre de TP déjà effectués ?", default=0)
    base = build_state(conf)
    rebuilt = rebuild_state_from_steps(base, n)
    save_path = compute_save_path(conf)
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    SaveManager(save_path).save(rebuilt)
    console.print(f"[green]Sauvegarde reconstruite[/green] comme si {n} /tp avaient été effectués.")
    console.print(f"Position attendue : X={rebuilt.current_x} Y={rebuilt.y} Z={rebuilt.current_z}")


def menu_once(conf, dry_run):
    sel = 0
    opts = [
        "Démarrer / Reprendre (automatique depuis la sauvegarde si existante)",
        "Démarrer à zéro (ignorer la sauvegarde)",
        "Reconstruire une sauvegarde (comme si N TP avaient été faits)",
        "Modifier la configuration",
        "Tester la connexion RCON",
        "Mode simulation — Aucune commande n'est envoyée au serveur",
        "Contrôle libre",
        "Chat + Commandes RCON",
        "Obtenir IPs d'un serveur",
    ]
    while True:
        console.clear()
        show_config(conf)
        console.print("\nMenu :")
        for i, text in enumerate(opts):
            pref = "➤ " if i == sel else "  "
            n = str(i + 1)
            if i == sel:
                console.print(f"{pref}[orange1][{n}][/orange1] [green]{text}[/]")
            else:
                console.print(f"{pref}[cyan][{n}][/cyan] [white]{text}[/]")
        console.print("")
        console.print("[grey50]Utilisez ↑/↓ puis Entrée, ou tapez 1-9, Échap pour quitter[/grey50]\n")
        k = read_key_ext()
        if k == "UP":
            sel = (sel - 1) % len(opts)
            continue
        if k == "DOWN":
            sel = (sel + 1) % len(opts)
            continue
        if k in set("123456789"):
            ch = k
            console.print(f"Choix : {ch}\n")
            return ch
        if k == "ENTER":
            ch = str(sel + 1)
            console.print(f"Choix : {ch}\n")
            return ch
        if k == "ESC":
            console.print("Choix : Esc\n")
            return "\x1b"


def main():
    console.print("")
    banner()
    conf = load_config("config.json")
    dry_run = False
    while True:
        ch = menu_once(conf, dry_run)
        if ch == "1":
            run_exploration(conf, reset=False, dry_run=dry_run)
        elif ch == "2":
            run_exploration(conf, reset=True, dry_run=dry_run)
        elif ch == "3":
            rebuild_save(conf)
        elif ch == "4":
            new_conf = edit_config(conf, console, read_key_ext)
            if new_conf is not None:
                conf = new_conf
                save_config(conf, "config.json")
                console.print("\n[green]Configuration enregistrée[/green]\n")
        elif ch == "5":
            rc = connect_rcon(conf, dry_run=dry_run)
            if rc:
                rc.close()
        elif ch == "6":
            dry_run = not dry_run
            console.print(f"Mode simulation = {'ON' if dry_run else 'OFF'}\n")
        elif ch == "7":
            rc = connect_rcon(conf, dry_run=dry_run)
            if rc:
                try:
                    run_free_control(conf, rc)
                finally:
                    rc.close()
        elif ch == "8":
            rc = connect_rcon(conf, dry_run=dry_run)
            if rc:
                try:
                    run_chat_console(conf, rc)
                finally:
                    rc.close()
        elif ch == "9":
            try:
                import mc_resolve as mcr

                mcr.main()
            except Exception as e:
                console.print(f"[red]Erreur mc_resolve : {e}[/red]")
        elif ch == "\x1b":
            console.print("\n --- PROGRAMME TERMINÉ --- \n")
            break


if __name__ == "__main__":
    sys.path.append(os.path.dirname(__file__))
    main()
