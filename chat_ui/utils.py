# chat_ui/utils.py
import curses
import unicodedata

try:
    from wcwidth import wcswidth as _wcs
    from wcwidth import wcwidth as _wc
except Exception:
    _wc = None
    _wcs = None

# Séquences à traiter comme un seul glyphe largeur 2
_WIDE_CLUSTERS = ("❤️",)  # U+2764 + U+FE0F
# Emojis à forcer en largeur 2
_FORCE_WIDE = {"🤍"}  # U+1F90D


def _wcw(ch: str) -> int:
    if ch in _FORCE_WIDE:
        return 2
    if _wc is not None:
        w = _wc(ch)
        return 0 if w < 0 else w
    if ch == "\ufe0f":  # VS16
        return 0
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _iter_glyphs(s: str):
    i = 0
    n = len(s)
    while i < n:
        # Priorité aux séquences larges
        for seq in _WIDE_CLUSTERS:
            if s.startswith(seq, i):
                yield seq, 2
                i += len(seq)
                break
        else:
            ch = s[i]
            yield ch, _wcw(ch)
            i += 1


def cols_len(s: str) -> int:
    if s is None:
        return 0
    if _wcs is not None:
        w = _wcs(s)
        if w >= 0:
            return w
    return sum(w for _, w in _iter_glyphs(s))


def clip_cols(s: str, max_cols: int):
    if s is None:
        return "", 0
    out = []
    used = 0
    for frag, w in _iter_glyphs(s):
        if used + w > max_cols:
            break
        out.append(frag)
        used += w
    return "".join(out), used


def add_safe(win, y, x, s, attr=0):
    h, w = win.getmaxyx()
    if h <= 0 or w <= 0 or y < 0 or y >= h or x >= w:
        return
    if x < 0:
        s = s[-x:]
        x = 0
    try:
        win.addnstr(y, x, s, len(s), attr)
    except curses.error:
        pass


def add_cols(win, y, x, s, max_cols, attr=0):
    s2, _ = clip_cols(s, max_cols)
    add_safe(win, y, x, s2, attr)
