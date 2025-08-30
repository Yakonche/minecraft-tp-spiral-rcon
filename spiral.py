from state import SpiralState

DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]


def next_step(state: SpiralState) -> tuple[int, int, SpiralState]:
    dx, dz = DIRS[state.dir_idx]
    x = state.current_x + dx * state.step_blocks
    z = state.current_z + dz * state.step_blocks
    state.leg_progress += 1
    if state.leg_progress >= state.leg_length:
        state.leg_progress = 0
        state.dir_idx = (state.dir_idx + 1) % 4
        if state.dir_idx % 2 == 0:
            state.leg_length += 1
    state.current_x = x
    state.current_z = z
    state.step_index += 1
    return x, z, state


def rebuild_state_from_steps(base: SpiralState, n: int) -> SpiralState:
    s = SpiralState(
        player=base.player,
        dimension=base.dimension,
        y=base.y,
        chunk_step=base.chunk_step,
        step_blocks=base.step_blocks,
        spawn_x=base.spawn_x,
        spawn_z=base.spawn_z,
        current_x=base.spawn_x,
        current_z=base.spawn_z,
        step_index=0,
        dir_idx=0,
        leg_length=1,
        leg_progress=0,
        interval_s=base.interval_s,
        max_tps=base.max_tps,
        host=base.host,
        port=base.port,
    )
    for _ in range(n):
        _, _, s = next_step(s)
    return s
