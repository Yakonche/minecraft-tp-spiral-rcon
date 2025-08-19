# Explorateur Spirale Minecraft

[🇬🇧 Read in English](README.md)

## Description
Outil Python pour automatiser l'exploration de cartes Minecraft via RCON.  
Il envoie des commandes de téléportation au joueur pour parcourir le monde en spirale.  
Il peut reprendre une exploration interrompue grâce à des fichiers de sauvegarde.  
Interface TUI (basée sur `rich`) pour contrôler et suivre l'état du programme.

## Fonctionnalités
- Connexion à un serveur Minecraft via RCON (`mcrcon`).
- Déplacement automatique du joueur en spirale dans une dimension choisie.
- Sauvegarde et reprise d'état via fichiers JSON (`.mc_spiral_save.json` ou répertoires de `saves/`).
- Paramétrage par fichier `config.json`.
- Interface texte (TUI) pour suivre l'exploration et gérer l'état.
- Contrôles pour lancer, stopper, et superviser l'exploration.

## Dépendances
- Python 3.8+
- [mcrcon](https://pypi.org/project/mcrcon/) >= 0.7.0
- [rich](https://pypi.org/project/rich/) >= 13.7.0

## Installation
```bash
git clone <repo>
cd <repo>
python3 -m venv .venv
source .venv/bin/activate   # Linux / Mac
.venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

## Configuration
Modifier `config.json` :
```json
{
  "rcon": {
    "host": "localhost",
    "port": 25575,
    "password": "Password",
    "timeout": 5.0
  },
  "exploration": {
    "player": "Player",
    "dimension": "minecraft:the_nether",
    "y": 128,
    "chunks": 32,
    "spawn_x": 0,
    "spawn_z": 0,
    "interval": 75.0,
    "max_tps": 4096
  },
  "save_file": "auto",
  "save_dir": "saves"
}
```

## Utilisation
Activer l'environnement virtuel, puis exécuter :
```bash
python main.py
```

## Sauvegardes
- L’état de l’exploration est sauvegardé automatiquement dans `.mc_spiral_save.json`.
- Les sauvegardes multiples se trouvent dans `saves/`.
