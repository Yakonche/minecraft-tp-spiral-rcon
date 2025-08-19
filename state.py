from dataclasses import dataclass, asdict
from typing import Optional
import json, os

@dataclass
class SpiralState:
    player: str = 'Yakonche'
    dimension: str = 'minecraft:overworld'
    y: int = 192
    chunk_step: int = 32
    step_blocks: int = 512
    spawn_x: int = 0
    spawn_z: int = 0
    step_index: int = 0
    current_x: int = 0
    current_z: int = 0
    dir_idx: int = 0
    leg_length: int = 1
    leg_progress: int = 0
    interval_s: float = 15.0
    max_tps: Optional[int] = 1000
    host: str = 'localhost'
    port: int = 25575
    def to_json(self):
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)
    @staticmethod
    def from_json(data: str):
        d = json.loads(data)
        if 'step_blocks' not in d:
            d['step_blocks'] = int(d.get('chunk_step',32))*16
        return SpiralState(**d)

class SaveManager:
    def __init__(self, path: str):
        self.path = path
    def exists(self):
        return os.path.isfile(self.path)
    def load(self):
        with open(self.path, 'r', encoding='utf-8') as f:
            return SpiralState.from_json(f.read())
    def save(self, state: SpiralState):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(state.to_json())
        os.replace(tmp, self.path)
