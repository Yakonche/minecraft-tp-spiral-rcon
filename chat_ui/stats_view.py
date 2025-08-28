import curses
import re
from .utils import add_safe, add_cols, cols_len, clip_cols
from .widgets import box, render_dimension, render_position, line_row

class StatsView:
    def __init__(self):
        self._stable_card_w = None

    def reset_width(self):
        self._stable_card_w = None

    def _hearts_bar(self, v):
        s = str(v or "")
        m = re.findall(r"[-+]?\d+(?:\.\d+)?", s)
        f = float(m[0]) if m else 20.0
        f = max(0.0, min(20.0, f))
        halves = int(f + 1e-6)
        full = halves // 2
        half = halves % 2
        return ("❤️" * full) + ("♥" if half else "")

    def _fmt_num(self, v):
        try:
            f = float(str(v).replace(",", "."))
            s = f"{f:.1f}".rstrip("0").rstrip(".")
            return s
        except Exception:
            return str(v or "")

    def _hunger_field(self, v):
        s = str(v or "").strip()
        if "🍗" in s:
            return s.replace(" ", "")
        m = re.findall(r"[-+]?\d+(?:\.\d+)?", s)
        if not m: return s
        f = max(0.0, min(20.0, float(m[0])))
        halves = int(f + 1e-6)
        bar = "🍗" * 10
        clipped, _ = clip_cols(bar, halves)
        return clipped

    def _max_field_width(self, items):
        m = 0
        for p in items:
            m = max(
                m,
                cols_len(str(p.get("name", ""))),
                20,
                cols_len(str(p.get("hunger", ""))),
                cols_len(str(p.get("lvl", ""))),
                cols_len(str(p.get("score", ""))),
                cols_len(str(p.get("dim", ""))),
                cols_len(str(p.get("gm", ""))),
                cols_len(str(p.get("pos", ""))),
            )
        return m

    def render(self, chat_win, cards, online_players, cp):
        Hs, Ws = chat_win.getmaxyx()
        win = curses.newwin(Hs, Ws, 0, 0)
        box(win, "STATUT JOUEURS (F2)", cp["white"], cp["cyan"])

        cards = cards or []
        if not cards:
            add_safe(win, 2, 2, "Aucun joueur trouvé", curses.color_pair(cp["gray"]))
            win.noutrefresh()
            return

        card_w = 42
        card_h = 10
        labels = ["Joueur", "Santé", "Faim", "LVL", "Score / XP", "Dimension", "Mode de Jeu", "Position"]
        left_w = max(cols_len(lbl) for lbl in labels)
        right_w = max(0, card_w - (left_w + 5))
        cols = max(1, Ws // card_w)


        for i, p in enumerate(cards):
            r = i // cols
            c = i % cols
            y = 1 + r * card_h
            x = 1 + c * card_w
            if y + card_h >= Hs - 1:
                break

            left_count = left_w + 2
            right_count = card_w - left_w - 5
            top = "╭" + ("─" * left_count) + "┬" + ("─" * right_count) + "╮"
            mid = "│" + (" " * (card_w - 2)) + "│"
            bot = "╰" + ("─" * left_count) + "┴" + ("─" * right_count) + "╯"
            add_safe(win, y, x, top, curses.color_pair(cp["white"]))
            for yy in range(1, card_h - 1):
                add_safe(win, y + yy, x, mid, curses.color_pair(cp["white"]))
            add_safe(win, y + card_h - 1, x, bot, curses.color_pair(cp["white"]))

            name = p.get("name", "")
            right_w = max(0, card_w - (left_w + 5))

            def repaint(row_y):
                add_safe(win, row_y, x, "│", curses.color_pair(cp["white"]))
                add_safe(win, row_y, x + 3 + left_w, "│", curses.color_pair(cp["white"]))
                add_safe(win, row_y, x + card_w - 1, "│", curses.color_pair(cp["white"]))

            name_trim, used = clip_cols(name, right_w)
            name_cell = name_trim + (" " * max(0, right_w - used))
            title_left = "Joueur" + " " * (left_w - cols_len("Joueur"))
            title = f"│ {title_left} │ {name_cell} │"
            add_cols(win, y + 1, x, title, card_w, curses.color_pair(cp["white"]))

            name_start = x + left_w + 5
            w_shown = min(cols_len(name_trim), right_w)
            dot_rel = min(w_shown + 1, max(0, right_w - 2))
            dot_x = name_start + dot_rel
            online = name in (online_players or set())
            add_safe(win, y + 1, dot_x, "●", curses.color_pair(cp["green"] if online else cp["red"]))
            repaint(y + 1)

            add_cols(win, y + 2, x, line_row("Santé", self._hearts_bar(p.get("health", "")), left_w, right_w),
                     card_w, curses.color_pair(cp["white"]))
            repaint(y + 2)

            add_cols(win, y + 3, x, line_row("Faim", self._hunger_field(p.get("hunger", "")), left_w, right_w),
                     card_w, curses.color_pair(cp["white"]))
            repaint(y + 3)

            add_cols(win, y + 4, x, line_row("LVL", p.get("lvl", ""), left_w, right_w),
                     card_w, curses.color_pair(cp["white"]))
            repaint(y + 4)

            add_cols(win, y + 5, x, line_row("Score / XP", p.get("score", ""), left_w, right_w),
                     card_w, curses.color_pair(cp["white"]))
            repaint(y + 5)

            render_dimension(win, y + 6, x, left_w, card_w, p.get("dim", ""), cp)
            repaint(y + 6)

            add_cols(win, y + 7, x, line_row("Mode de Jeu", p.get("gm", ""), left_w, right_w),
                     card_w, curses.color_pair(cp["white"]))
            repaint(y + 7)

            render_position(win, y + 8, x, left_w, card_w, p.get("pos", ""), cp)
            repaint(y + 8)

            win.noutrefresh()
