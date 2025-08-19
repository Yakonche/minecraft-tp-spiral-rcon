# Minecraft Spiral Explorer

[🇫🇷 Lire en français](README-FR.md)

## Description
Python tool to automate Minecraft map exploration via RCON.  
It sends teleport commands to the player to explore the world in a spiral pattern.  
It can resume interrupted exploration using save files.  
TUI interface (based on `rich`) to control and monitor the program.

## Features
- Connect to a Minecraft server via RCON (`mcrcon`).
- Automatically move the player in a spiral in a chosen dimension.
- Save and resume state through JSON files in the `saves/` directory.
- Configurable through `config.json`.
- Text User Interface (TUI) for monitoring and controlling the process.
- Send custom RCON commands to the server.
- Read and display Minecraft chat messages.
- Send messages to the in-game chat.

## Requirements
- Full access to the target Minecraft server with RCON enabled.
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
Edit `config.json`:
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

## Usage
Activate the virtual environment, then run:
```bash
python main.py
```
Or just:
```bash
.venv/bin/python main.py
```

## Saves
- Multiple save states are stored in `saves/`.
