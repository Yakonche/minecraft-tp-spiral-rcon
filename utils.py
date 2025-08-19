import math

def human_eta(seconds):
    if seconds is None or math.isinf(seconds) or seconds < 0:
        return '—'
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d>0: return f"{d}j {h}h {m}m {s}s"
    if h>0: return f"{h}h {m}m {s}s"
    if m>0: return f"{m}m {s}s"
    return f"{s}s"
