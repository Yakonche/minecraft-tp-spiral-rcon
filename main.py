#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import sys, os, termios, tty, select
from rich import print
from rich.prompt import Prompt, IntPrompt, FloatPrompt
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.box import ROUNDED

from config import load_config, save_config, compute_save_path
from state import SpiralState, SaveManager
from rcon_client import RconClient
from tui import run_loop
from spiral import rebuild_state_from_steps
from control import run_free_control
from chat import run_chat_console

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

def banner():
    console.print(Panel.fit("[bold cyan]RCON Spiral Explorer[/bold cyan] — Exploration automatique en spirale carrée", box=ROUNDED))

def show_config(conf):
    t = Table(title="Configuration", show_lines=False, show_header=False, box=ROUNDED)
    t.add_column(justify="left"); t.add_column(justify="right")
    t.add_row("RCON host", str(conf['rcon']['host']))
    t.add_row("RCON port", str(conf['rcon']['port']))
    t.add_row("RCON timeout (s)", str(conf['rcon']['timeout']))
    e = conf['exploration']
    t.add_row("Joueur", e['player']); t.add_row("Dimension", e['dimension'])
    t.add_row("Hauteur (Y=)", str(e['y'])); t.add_row("Chunks", str(e['chunks']))
    t.add_row("Spawn (X)", str(e['spawn_x'])); t.add_row("Spawn (Z)", str(e['spawn_z']))
    t.add_row("Intervalle (s)", str(e['interval'])); t.add_row("/tp max", str(e['max_tps']))
    console.print(t)

def edit_config(conf) -> dict:
    console.print("[bold]Modifier la configuration[/bold] (laisser vide pour conserver)")
    r = conf['rcon']; e = conf['exploration']
    host = Prompt.ask("RCON host", default=str(r['host']))
    port = IntPrompt.ask("RCON port", default=int(r['port']))
    timeout = FloatPrompt.ask("RCON timeout (s)", default=float(r['timeout']))
    password = Prompt.ask("RCON password", default=str(r['password']), password=False)
    player = Prompt.ask("Joueur", default=str(e['player']))
    dimension = Prompt.ask("Dimension", default=str(e['dimension']))
    y = IntPrompt.ask("Hauteur (Y=)", default=int(e['y']))
    chunks = IntPrompt.ask("Chunks", default=int(e['chunks']))
    spawn_x = IntPrompt.ask("Spawn (X)", default=int(e['spawn_x']))
    spawn_z = IntPrompt.ask("Spawn (Z)", default=int(e['spawn_z']))
    interval = FloatPrompt.ask("Intervalle (s)", default=float(e['interval']))
    max_tps = IntPrompt.ask("/tp max (-1 = illimité)", default=int(e['max_tps']))
    save_file = Prompt.ask("Fichier de sauvegarde ('auto' conseillé)", default=str(conf.get('save_file', 'auto')))
    save_dir = Prompt.ask("Dossier de sauvegarde (si 'auto')", default=str(conf.get('save_dir', 'saves')))
    return {
        "rcon": {"host": host, "port": port, "password": password, "timeout": timeout},
        "exploration": {
            "player": player, "dimension": dimension, "y": y, "chunks": chunks,
            "spawn_x": spawn_x, "spawn_z": spawn_z, "interval": interval, "max_tps": max_tps
        },
        "save_file": save_file,
        "save_dir": save_dir
    }

def build_state(conf) -> SpiralState:
    e = conf['exploration']
    return SpiralState(
        player=e['player'], dimension=e['dimension'], y=int(e['y']),
        chunk_step=int(e['chunks']), step_blocks=int(e['chunks']) * 16,
        spawn_x=int(e['spawn_x']), spawn_z=int(e['spawn_z']),
        current_x=int(e['spawn_x']), current_z=int(e['spawn_z']),
        interval_s=float(e['interval']),
        max_tps=(None if int(e['max_tps']) == -1 else int(e['max_tps'])),
        host=str(conf['rcon']['host']), port=int(conf['rcon']['port'])
    )

def connect_rcon(conf, dry_run=False):
    rc = RconClient(
        host=str(conf['rcon']['host']),
        port=int(conf['rcon']['port']),
        password=str(conf['rcon']['password']),
        timeout=float(conf['rcon']['timeout']),
        dry_run=dry_run
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
    show_config(conf)
    console.print("\nMenu :")
    console.print("1) Démarrer / Reprendre (automatique depuis la sauvegarde si existante)")
    console.print("2) Démarrer à zéro (ignorer la sauvegarde)")
    console.print("3) Reconstruire une sauvegarde (comme si N TP avaient été faits)")
    console.print("4) Modifier la configuration et enregistrer")
    console.print("5) Tester la connexion RCON")
    console.print("6) Mode simulation — Aucune commande n'est envoyée au serveur")
    console.print("7) Contrôle libre")
    console.print("8) Chat + Commandes RCON")
    console.print("9) Obtenir IPs d'un serveur")
    console.print("")
    console.print("Appuyez sur [bold]1-9[/bold] pour choisir, ou [bold]Esc[/bold] pour quitter…")
    console.print("")
    ch = read_key(allowed=set("123456789") | {"\x1b"})
    label = "Esc" if ch == "\x1b" else ch
    console.print(f"Choix : {label}\n")
    return ch

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
            conf = edit_config(conf)
            save_config(conf, "config.json")
            console.print("[green]Configuration enregistrée[/green]\n")
        elif ch == "5":
            rc = connect_rcon(conf, dry_run=dry_run)
            if rc: rc.close()
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
