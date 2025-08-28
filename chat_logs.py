import os, time, re, io

CHAT_MAIN = re.compile(r"^\[([0-9]{2}:[0-9]{2}:[0-9]{2})\].*?: <([^>]+)> (.*)$")
CHAT_SERVER = re.compile(r"^\[([0-9]{2}:[0-9]{2}:[0-9]{2})\].*?\]: \[(?:Server|RCON|Rcon)\] (.*)$")

def _tail_last_lines(path, n=200):
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 4096
            data = b''
            pos = size
            while pos > 0 and data.count(b'\n') <= n:
                delta = block if pos >= block else pos
                pos -= delta
                f.seek(pos)
                data = f.read(delta) + data
            text = data.decode('utf-8', errors='ignore').splitlines()[-n:]
            return text
    except FileNotFoundError:
        return []
    except Exception:
        return []

class LogTail:
    def __init__(self, path):
        self.path = path
        self.pos = None
        self.inode = None
        self.preloaded = False

    def _open(self):
        f = open(self.path, 'r', encoding='utf-8', errors='ignore')
        st = os.fstat(f.fileno())
        inode = st.st_ino
        size = st.st_size
        if self.inode != inode:
            self.inode = inode
            self.pos = 0
            self.preloaded = False
        if self.pos is None:
            self.pos = 0
        f.seek(self.pos, os.SEEK_SET)
        return f

    def follow(self, stop_event):
        # preload last lines once
        if not self.preloaded:
            for line in _tail_last_lines(self.path, n=200):
                yield line
            self.preloaded = True
        while not stop_event.is_set():
            try:
                with self._open() as f:
                    while not stop_event.is_set():
                        line = f.readline()
                        if not line:
                            self.pos = f.tell()
                            time.sleep(0.1)
                            break
                        self.pos = f.tell()
                        yield line.rstrip('\n')
            except FileNotFoundError:
                time.sleep(0.5)

    def force_refresh(self):
        try:
            with open(self.path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, os.SEEK_END)
                self.pos = f.tell()
        except Exception:
            pass

def parse_chat(line):
    m = CHAT_MAIN.match(line)
    if m:
        return m.group(1), m.group(2), m.group(3), "player"
    m = CHAT_SERVER.match(line)
    if m:
        return m.group(1), "RCON", m.group(2), "rcon_say"
    return None
