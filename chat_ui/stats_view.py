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
        try:
            f = float(s.replace(",", "."))
            full = int(f // 2.0)
        except Exception:
            # Fallback: count heart glyphs or parse numbers
            if "❤️" in s or "❤" in s:
                full = s.count("❤️") + s.count("❤")
            else:
                m = re.findall(r"[-+]?\d+(?:\.\d+)?", s)
                full = int(float(m[0]) // 2.0) if m else 0
        if full < 0: full = 0
        if full > 10: full = 10
        return "❤️" * full + "🤍" * (10 - full)

    def _fmt_num(self, v):
        try:
            f = float(str(v).replace(",", "."))
            s = f"{f:.1f}".rstrip("0").rstrip(".")
            return s
        except Exception:
            return str(v or "")

    def _max_field_width(self, items):
        m = 0
        for p in items:
            m = max(
                m,
                cols_len(str(p.get("name", ""))),
                20,  # fixed display width for the hearts bar
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

        min_w, max_w, card_h = 34, 72, 10
        labels = ["Joueur", "Santé", "Faim", "LVL", "Score / XP", "Dimension", "Mode de Jeu", "Position"]
        left_w = max(cols_len(lbl) for lbl in labels)
        right_w_needed = self._max_field_width(cards)
        card_w_needed = left_w + right_w_needed + 5

        base_w = max(min_w, min(max_w, card_w_needed))
        cols_try = max(1, Ws // base_w)
        card_w_try = min(max_w, max(min_w, min(Ws // cols_try if cols_try else Ws, card_w_needed)))

        if self._stable_card_w is None:
            self._stable_card_w = card_w_try
        else:
            self._stable_card_w = max(self._stable_card_w, card_w_try)
        card_w = self._stable_card_w
        cols = max(1, Ws // card_w)

        for i, p in enumerate(cards):
            r = i // cols
            c = i % cols
            y = 1 + r * card_h
            x = 1 + c * card_w
            if y + card_h >= Hs - 1:
                break

            # card frame
            top = "╭" + "─" * (card_w - 2) + "╮"
            mid = "│" + " " * (card_w - 2) + "│"
            bot = "╰" + "─" * (card_w - 2) + "╯"
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

            # Title row
            name_trim, used = clip_cols(name, right_w)
            name_cell = name_trim + (" " * max(0, right_w - used))
            title_left = "Joueur" + " " * (left_w - cols_len("Joueur"))
            title = f"│ {title_left} │ {name_cell} │"
            add_cols(win, y + 1, x, title, card_w, curses.color_pair(cp["white"]))

            # Online dot
            name_start = x + left_w + 5
            w_shown = min(cols_len(name_trim), right_w)
            dot_rel = min(w_shown + 1, max(0, right_w - 2))
            dot_x = name_start + dot_rel
            online = name in (online_players or set())
            add_safe(win, y + 1, dot_x, "●", curses.color_pair(cp["green"] if online else cp["red"]))
            repaint(y + 1)

            # Rows
            add_cols(win, y + 2, x, line_row("Santé", self._hearts_bar(p.get("health", "")), left_w, right_w),
                     card_w, curses.color_pair(cp["white"]))
            repaint(y + 2)

            add_cols(win, y + 3, x, line_row("Faim", f"🍗 {self._fmt_num(p.get('hunger', ''))}", left_w, right_w),
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
