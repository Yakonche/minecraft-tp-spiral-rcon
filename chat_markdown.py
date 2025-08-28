import re, curses

BOLD = re.compile(r"\*\*(.+?)\*\*")
ITAL = re.compile(r"\*(.+?)\*")
CODE = re.compile(r"`([^`]+)`")

def render_segments(s):
    segs = []
    i = 0
    while i < len(s):
        m_code = CODE.search(s, i)
        m_bold = BOLD.search(s, i)
        m_ital = ITAL.search(s, i)
        ms = [m for m in (m_code, m_bold, m_ital) if m]
        if not ms:
            segs.append((s[i:], curses.color_pair(1)))
            break
        m = min(ms, key=lambda x: x.start())
        if m.start() > i:
            segs.append((s[i:m.start()], curses.color_pair(1)))
        if m.re is CODE:
            segs.append((m.group(1), curses.A_REVERSE))
        elif m.re is BOLD:
            segs.append((m.group(1), curses.A_BOLD))
        else:
            segs.append((m.group(1), curses.A_DIM))
        i = m.end()
    return segs
