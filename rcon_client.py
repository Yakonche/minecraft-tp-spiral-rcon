from typing import Optional
try:
    from mcrcon import MCRcon
except Exception:
    MCRcon = None

class RconClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0, dry_run: bool = False):
        self.host = host
        self.port = int(port)
        self.password = password
        self.timeout = float(timeout)
        self.conn: Optional[MCRcon] = None
        self.dry_run = dry_run

    def connect(self):
        if self.dry_run:
            return
        if MCRcon is None:
            raise RuntimeError("Le module 'mcrcon' est introuvable. Installez-le avec: pip install mcrcon")
        # Certaines versions de mcrcon ne gèrent pas 'timeout' correctement -> n'utiliser que host/password/port
        self.conn = MCRcon(self.host, self.password, port=self.port)
        self.conn.connect()

    def close(self):
        if self.conn is not None:
            try:
                self.conn.disconnect()
            except Exception:
                pass
            self.conn = None

    def cmd(self, command: str) -> str:
        if self.dry_run:
            return f"[DRY-RUN] {command}"
        if not self.conn:
            self.connect()
        try:
            assert self.conn is not None
            return self.conn.command(command)
        except Exception:
            self.close()
            self.connect()
            assert self.conn is not None
            return self.conn.command(command)
