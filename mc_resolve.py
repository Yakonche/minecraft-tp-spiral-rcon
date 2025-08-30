#!/usr/bin/env python3
import select
import socket
import sys
import time


def q_resolver(nameservers, timeout):
    import dns.resolver as d

    r = d.Resolver(configure=False)
    r.nameservers = nameservers
    r.lifetime = timeout
    r.timeout = timeout
    return r


def dns_simple(host, rr, timeout, nameservers=None):
    out = []
    try:
        import dns.resolver as d
    except Exception:
        return out
    try:
        if nameservers is None:
            r = d.Resolver()
            r.lifetime = timeout
        else:
            r = q_resolver(nameservers, timeout)
        ans = r.resolve(host, rr)
        for x in ans:
            out.append(x.to_text())
    except Exception:
        pass
    return out


def resolve_srv(host, timeout):
    try:
        import dns.resolver as d
    except Exception:
        return None
    try:
        r = d.Resolver()
        r.lifetime = timeout
        q = "_minecraft._tcp." + host.strip(".")
        a = r.resolve(q, "SRV")
        recs = [(x.priority, x.weight, x.port, str(x.target).rstrip(".")) for x in a]
        recs.sort(key=lambda x: (x[0], -x[1]))
        if not recs:
            return None
        b = recs[0]
        return {"target": b[3], "port": int(b[2])}
    except Exception:
        return None


def authoritative_nameservers(qname, timeout):
    try:
        import dns.name as dn
        import dns.resolver as d
    except Exception:
        return []
    labels = dn.from_text(qname).labels
    domain = dn.from_text(qname)
    ns_list = []
    for i in range(len(labels) - 1):
        try:
            zone = dn.Name(labels[i + 1 :])
            ans = d.resolve(zone, "NS")
            for rr in ans:
                ns_list.append(str(rr.target).rstrip("."))
            if ns_list:
                break
        except Exception:
            continue
    ns_ips = []
    for ns in ns_list:
        ns_ips += dns_simple(ns, "A", timeout) + dns_simple(ns, "AAAA", timeout)
    return ns_ips


def resolve_ips_all(name, timeout):
    v4 = set()
    v6 = set()
    for fam in (socket.AF_INET, socket.AF_INET6):
        try:
            infos = socket.getaddrinfo(name, None, family=fam, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        except Exception:
            infos = []
        for f, _, _, _, sockaddr in infos:
            if f == socket.AF_INET:
                v4.add(sockaddr[0])
            elif f == socket.AF_INET6:
                v6.add(sockaddr[0])
    for rr, acc in (("A", v4), ("AAAA", v6)):
        for ns in (
            None,
            ["1.1.1.1", "9.9.9.9", "8.8.8.8", "2606:4700:4700::1111", "2620:fe::fe", "2001:4860:4860::8888"],
        ):
            vals = dns_simple(name, rr, timeout, ns)
            for ip in vals:
                acc.add(ip)
    auth_ns = authoritative_nameservers(name, timeout)
    if auth_ns:
        try:
            import dns.message as dm
            import dns.query as dq

            for rr, acc in (("A", v4), ("AAAA", v6)):
                q = dm.make_query(name, rr)
                for nsip in auth_ns:
                    try:
                        resp = dq.udp(q, nsip, timeout=timeout)
                        if resp and resp.answer:
                            for ans in resp.answer:
                                for itm in ans.items:
                                    txt = getattr(itm, "address", None) or getattr(itm, "to_text", lambda: None)()
                                    if txt:
                                        if rr == "A":
                                            v4.add(txt if isinstance(txt, str) else str(txt))
                                        else:
                                            v6.add(txt if isinstance(txt, str) else str(txt))
                    except Exception:
                        try:
                            resp = dq.tcp(q, nsip, timeout=timeout)
                            if resp and resp.answer:
                                for ans in resp.answer:
                                    for itm in ans.items:
                                        txt = getattr(itm, "address", None) or getattr(itm, "to_text", lambda: None)()
                                        if txt:
                                            if rr == "A":
                                                v4.add(txt if isinstance(txt, str) else str(txt))
                                            else:
                                                v6.add(txt if isinstance(txt, str) else str(txt))
                        except Exception:
                            continue
        except Exception:
            pass
    return sorted(v4), sorted(v6)


def tty_input(prompt):
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    sys.stdout.write(prompt)
    sys.stdout.flush()
    buf = ""
    show = True
    last = time.monotonic()
    last_len = 0
    try:
        while True:
            now = time.monotonic()
            if now - last >= 0.5:
                show = not show
                last = now
            s = prompt + buf + ("█" if show else " ")
            pad = max(0, last_len - len(s))
            sys.stdout.write("\r" + s + (" " * pad))
            sys.stdout.flush()
            last_len = len(s)
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not r:
                continue
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                return None
            if ch in ("\r", "\n"):
                sys.stdout.write("\r" + " " * (len(prompt) + len(buf) + 2) + "\r")
                sys.stdout.flush()
                return buf.strip()
            if ch in ("\x7f", "\b"):
                if buf:
                    buf = buf[:-1]
                continue
            if " " <= ch <= "~":
                buf += ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main():
    host = tty_input("Entrez l'adresse du server : ")
    if host is None or not host:
        return
    target = host.strip(".")
    port = 25565
    srv = resolve_srv(target, 3.0)
    if srv:
        target = srv["target"]
        port = int(srv["port"])
    v4, v6 = resolve_ips_all(target, 3.0)
    print("Cible :", target)
    print("Port :", port)
    print("IPv4 :", ", ".join(v4) if v4 else "-")
    print("IPv6 :", ", ".join(v6) if v6 else "-")
    print("\nAppuyez sur Échap (Esc) pour quitter.\n")
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not r:
                continue
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                break
    except Exception:
        pass
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass


if __name__ == "__main__":
    main()
