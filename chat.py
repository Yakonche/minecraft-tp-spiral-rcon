import curses, locale
from chat_ui import TUI

locale.setlocale(locale.LC_ALL, '')
curses.set_escdelay(25)

def run_chat_console(conf, rc):
    curses.wrapper(lambda stdscr: TUI(stdscr, conf, rc).loop())
