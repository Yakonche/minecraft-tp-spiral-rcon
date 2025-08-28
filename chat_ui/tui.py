import curses, time, threading, queue, textwrap, re, unicodedata, math
from chat_logs import LogTail, parse_chat
from mc_commands import COMMANDS, suggest_commands, STRUCTURES
from chat_markdown import render_segments
from .consts import LOG_PATH, PLAYERDATA_DIR, USERNAMECACHE, NBT_PY, B
from .utils import add_safe, add_cols, cols_len
from .widgets import box, render_dimension, render_position, wrap_segments, line_row
from .stats_view import StatsView
from .polling import poll_stats_hybrid, poll_query

try:
    from wcwidth import wcwidth as _wc
except Exception:
    _wc = None

class TUI:
    def __init__(self, stdscr, conf, rc):
        curses.curs_set(0)
        curses.use_default_colors()
        self.use_256=curses.COLORS>=256
        self.stats_view = StatsView()
        self.stdscr=stdscr
        self.conf=conf or {}
        self._init_colors()
        self.chat_lines=[]
        self.cursor_visible=True
        self.search_cursor_visible=True
        self.last_blink=time.time()
        self.mode="chat"
        self.search=""
        self.input_buf=""
        self.suggestions=[]
        self.scroll=0
        self.help_view="cmd"
        self.help_scroll=0
        self.tail = LogTail(LOG_PATH)
        self.q = queue.Queue()
        self.stop = threading.Event()
        threading.Thread(target=self._reader_loop, daemon=True).start()
        self.rcon = rc
        self.rcon_status = "Connecté RCON" if self.rcon else "Erreur RCON : non initialisé"
        self.dim_map = {}
        self.stats_data = []
        self.stats_interval = 1
        threading.Thread(target=poll_stats_hybrid, args=(
            self.stop, self.rcon, NBT_PY, PLAYERDATA_DIR, USERNAMECACHE, self.stats_interval, self._set_stats,
            self._set_dims, 30
        ), daemon=True).start()
        self.online_players = set()
        self.query_interval = 3
        q_host = self.conf.get("host")
        q_port = self.conf.get("query_port")
        threading.Thread(target=poll_query,
                         args=(self.stop, PLAYERDATA_DIR, self.query_interval, self._set_online, q_host, q_port),
                         daemon=True).start()

        self.chat_win=None; self.cmd_win=None
        self.needs_render=True
        self._resize()
        self.stdscr.timeout(100)

    def _hearts(self, v):
        s = str(v)
        try:
            f = float(s.replace(",", "."))
        except Exception:
            m = re.findall(r"[-+]?\d+(?:\.\d+)?", s)
            f = float(m[0]) if m else 0.0
        full = max(0, min(10, int(round(f / 2.0))))
        return "♥" * full + "♡" * (10 - full)

    def _set_dims(self, d): self.dim_map=d

    def _set_stats(self, s):
        self.stats_data = s
        if self.mode == "stats":
            self.needs_render = True

    def _set_online(self, names):
        self.online_players = set(names or [])
        if self.mode == "stats":
            self.needs_render = True

    def _init_colors(self):
        WHITE=15 if self.use_256 else curses.COLOR_WHITE
        GRAY=244 if self.use_256 else curses.COLOR_BLACK
        GREEN=10 if self.use_256 else curses.COLOR_GREEN
        RED=196 if self.use_256 else curses.COLOR_RED
        MAGENTA=171 if self.use_256 else curses.COLOR_MAGENTA
        ORANGE=208 if self.use_256 else curses.COLOR_YELLOW
        CYAN=14 if self.use_256 else curses.COLOR_CYAN
        YELLOW=11 if self.use_256 else curses.COLOR_YELLOW
        YELLOW_DK=178 if self.use_256 else curses.COLOR_YELLOW
        YELLOW_LT=229 if self.use_256 else curses.COLOR_YELLOW
        GREEN_DK=28 if self.use_256 else curses.COLOR_GREEN
        colors={"white":WHITE,"gray":GRAY,"green":GREEN,"red":RED,"magenta":MAGENTA,"orange":ORANGE,"cyan":CYAN,"yellow":YELLOW,"yellow_dk":YELLOW_DK,"yellow_lt":YELLOW_LT,"green_dk":GREEN_DK}
        for i,(k,v) in enumerate(colors.items(),start=1):
            curses.init_pair(i,v,-1)
        self.cp={k:i for i,(k,_) in enumerate(colors.items(),start=1)}

    def _reader_loop(self):
        for line in self.tail.follow(self.stop):
            m=parse_chat(line)
            if m:
                ts,speaker,msg,kind=m
                if kind in ("player","rcon_say"):
                    self.q.put((ts,speaker,msg,kind))
                continue
            j=re.match(r"^\[(\d{2}:\d{2}:\d{2})] \[Server thread/INFO\]: ([A-Za-z0-9_]{1,16}) joined the game",line)
            l=re.match(r"^\[(\d{2}:\d{2}:\d{2})] \[Server thread/INFO\]: ([A-Za-z0-9_]{1,16}) left the game",line)
            if j:
                ts=j.group(1); name=j.group(2)
                self.q.put((ts,"",f"{name} joined the game","event_join"))
            elif l:
                ts=l.group(1); name=l.group(2)
                self.q.put((ts,"",f"{name} left the game","event_leave"))

    def _resize(self):
        self.stdscr.erase()
        H,W=self.stdscr.getmaxyx()
        min_cmd_h=7
        self.cmd_win=curses.newwin(min_cmd_h,W,H-min_cmd_h,0)
        self.chat_win=curses.newwin(H-min_cmd_h,W,0,0)
        self.needs_render=True
        self.stats_view = StatsView()

    def loop(self):
        while not self.stop.is_set():
            try:
                while True:
                    self.chat_lines.append(self.q.get_nowait())
                    if self.scroll==0: self.needs_render=True
                break
            except queue.Empty:
                pass
            c=self.stdscr.getch()
            if c==curses.KEY_RESIZE:
                self._resize()
            elif c in (27,):
                if self.mode=="chat":
                    self.stop.set(); break
                else:
                    self.mode="chat"; self.search=""; self.needs_render=True
            elif c==curses.KEY_F5:
                self.tail.force_refresh()
            elif c==curses.KEY_F1:
                if self.mode!="help":
                    self.mode="help"; self.search=""; self.help_view="cmd"; self.help_scroll=0; self.needs_render=True
                else:
                    self.help_view=("struct" if self.help_view=="cmd" else "cmd"); self.help_scroll=0; self.needs_render=True
            elif c==curses.KEY_F2:
                if self.mode!="stats":
                    self.mode="stats"; self.needs_render=True
                else:
                    self.mode="chat"; self.needs_render=True
            elif c in (curses.KEY_UP,curses.KEY_PPAGE):
                if self.mode=="help":
                    self.help_scroll=max(0,self.help_scroll-1); self.needs_render=True
                else:
                    self.scroll=min(self.scroll+1,max(0,len(self.chat_lines)-1)); self.needs_render=True
            elif c in (curses.KEY_DOWN,curses.KEY_NPAGE):
                if self.mode=="help":
                    self.help_scroll=self.help_scroll+1; self.needs_render=True
                else:
                    self.scroll=max(0,self.scroll-1); self.needs_render=True
            elif self.mode=="help":
                if c in (curses.KEY_BACKSPACE,127,8):
                    if self.search: self.search=self.search[:-1]; self.help_scroll=0; self.needs_render=True
                elif 32<=c<=126:
                    self.search+=chr(c); self.help_scroll=0; self.needs_render=True
            elif c==9:
                if self.input_buf:
                    sug=suggest_commands(self.input_buf)
                    if sug: self.input_buf=sug[0]; self.needs_render=True
            elif c in (10,13):
                if self.input_buf.strip():
                    cmd=self.input_buf.strip()
                    if self.rcon:
                        try:
                            resp=self.rcon.cmd(cmd)
                            if resp:
                                now=time.strftime("%H:%M:%S")
                                self.chat_lines.append((now,"RCON",resp.replace("\r\n"," "),"rcon_say"))
                                if self.scroll==0: self.needs_render=True
                        except Exception as e:
                            self.rcon_status=f"Erreur RCON : {e}"; self.needs_render=True
                    self.input_buf=""; self.needs_render=True
            elif c!=-1:
                if c in (curses.KEY_BACKSPACE,127,8):
                    if self.input_buf: self.input_buf=self.input_buf[:-1]; self.needs_render=True
                elif 32<=c<=126:
                    self.input_buf+=chr(c); self.needs_render=True
            now=time.time()
            if now-self.last_blink>=0.5:
                self.cursor_visible=not self.cursor_visible
                self.search_cursor_visible=not self.search_cursor_visible
                self.last_blink=now; self.needs_render=True
            if self.needs_render:
                self._render(); self.needs_render=False

    def _render(self):
        self._render_chat()
        self._render_cmd()
        if self.mode=="help": self._render_help()
        if self.mode=="stats": self.stats_view.render(self.chat_win, self.stats_data, self.online_players, self.cp)
        curses.doupdate()

    def _render_chat(self):
        win=self.chat_win
        H,W=win.getmaxyx()
        box(win,"Chat (logs)",self.cp["white"],self.cp["cyan"])
        inner_h=H-2; x=1
        lines=self.chat_lines
        visible=lines[max(0,len(lines)-inner_h-self.scroll):len(lines)-self.scroll]
        y=H-2; inner_w=W-2
        for ts,speaker,msg,kind in reversed(visible):
            name_color=self._name_color(speaker,kind)
            segs=[(msg,curses.color_pair(self.cp["yellow"]))] if kind in ("event_join","event_leave") else render_segments(msg)
            start_cx=x+(7+len(ts)+len(speaker) if speaker else 4+len(ts))
            max_width=max(1,inner_w-(start_cx-x))
            wrapped=wrap_segments(segs,max_width) or [[]]
            for idx in range(len(wrapped)-1,-1,-1):
                if y<=0: break
                if idx==0:
                    add_safe(win,y,x," [",curses.color_pair(self.cp["gray"]))
                    add_safe(win,y,x+2,ts,curses.color_pair(self.cp["white"]))
                    add_safe(win,y,x+2+len(ts),"] ",curses.color_pair(self.cp["gray"]))
                    if speaker:
                        add_safe(win,y,x+4+len(ts),speaker,curses.color_pair(name_color))
                        add_safe(win,y,x+4+len(ts)+len(speaker)," : ",curses.color_pair(self.cp["gray"]))
                cx=start_cx
                for text,attr in wrapped[idx]:
                    add_safe(win,y,cx,text,attr); cx+=len(text)
                y-=1
            if y<=0: break
        win.noutrefresh()

    def _render_cmd(self):
        placeholder="Écrivez vos commandes ici..."
        content=self.input_buf if self.input_buf else placeholder
        text_width=max(1,self.cmd_win.getmaxyx()[1]-4)
        lines=textwrap.wrap(content,width=text_width,break_long_words=True,drop_whitespace=False) or [""]
        needed=5+len(lines)+1
        H,W=self.stdscr.getmaxyx()
        bot_h=max(needed,7)
        self.cmd_win=curses.newwin(bot_h,W,H-bot_h,0)
        self.chat_win=curses.newwin(H-bot_h,W,0,0)
        win=self.cmd_win
        box(win,"Commande libre",self.cp["white"],self.cp["cyan"])
        add_safe(win,1,1," "+self.rcon_status,curses.color_pair(self.cp["green"] if self.rcon and not self.rcon_status.startswith("Erreur") else self.cp["gray"]))
        add_safe(win,2,1," Commandes : ",curses.color_pair(self.cp["gray"]))
        sx=1+len(" Commandes : ")
        for k,label in [("Tab","Auto-complétion"),("F1","Aide"),("F2","Stats"),("F5","Recharger"),("Esc","Quitter")]:
            add_safe(win,2,sx,f"[{k}]",curses.color_pair(self.cp["white"])); sx+=len(f"[{k}]")
            add_safe(win,2,sx,"="+label+" ",curses.color_pair(self.cp["gray"])); sx+=len("="+label+" ")
        add_safe(win,3,1," Suggestions : ",curses.color_pair(self.cp["gray"]))
        self.suggestions=suggest_commands(self.input_buf)
        sx=1+len(" Suggestions : ")
        for s in self.suggestions:
            s2=s+"  "
            add_safe(win,3,sx,s2,curses.color_pair(self.cp["orange"])); sx+=len(s2)
        add_safe(win,4,0,B["tee_l"]+(B["h"]*(W-2))+B["tee_r"],curses.color_pair(self.cp["white"]))
        y=5
        attr=curses.color_pair(self.cp["white"]) if self.input_buf else curses.color_pair(self.cp["gray"])
        for i,line in enumerate(lines):
            add_safe(win,y+i,1," "+line[:text_width],attr)
        ghost=""
        if self.input_buf and self.suggestions:
            s=self.suggestions[0]
            if s.startswith(self.input_buf): ghost=s[len(self.input_buf):]
        if ghost:
            last=lines[-1] if lines else ""
            space_left=max(0,text_width-len(last))
            if space_left>0:
                add_safe(win,y+len(lines)-1,2+len(last),ghost[:space_left],curses.color_pair(self.cp["gray"]))
        if self.cursor_visible:
            last=lines[-1] if lines else ""
            cur_y=y+len(lines)-1
            cur_x=2+min(len(last),text_width)
            add_safe(win,cur_y,cur_x,"█",curses.color_pair(self.cp["white"]))
        win.noutrefresh()

    def _render_help(self):
        H,W=self.stdscr.getmaxyx()
        w=max(40,int(W*0.9))
        if self.help_view=="struct":
            content_y=3; sep_x=2+11; width=max(1,w-(sep_x+3)); needed=content_y
            vals=list(STRUCTURES.values())
            for i,names in enumerate(vals):
                lines=textwrap.wrap(", ".join(names),width=width) or [""]
                needed+=len(lines)
                if i<len(vals)-1: needed+=1
            h=max(10,needed+1)
        else:
            h=max(12,int(H*0.8))
        y=(H-h)//2; x=(W-w)//2
        win=curses.newwin(h,w,y,x)
        box(win,"COMMANDES MINECRAFT JAVA 1.20.1",self.cp["white"],self.cp["cyan"])
        label="Recherche :"; lx=2
        add_safe(win,1,lx,label,curses.color_pair(self.cp["gray"]))
        ix=lx+len(label)+1
        add_safe(win,1,ix,self.search[:max(0,w-ix-2)],curses.color_pair(self.cp["white"]))
        if self.search_cursor_visible:
            add_safe(win,1,ix+len(self.search),"█",curses.color_pair(self.cp["white"]))
        if not self.search:
            hint="Appuyer sur F1 pour switcher entre les commandes et les structures"
            hx=max(1,w-2-len(hint)-20+1)
            add_safe(win,1,hx,hint,curses.color_pair(self.cp["gray"]))
        if self.help_view=="cmd":
            left_w=18; sep_x=2+left_w
            left_count=max(1,sep_x-1); right_count=max(0,(w-2)-sep_x)
            header="├"+("─"*left_count)+"┬"+("─"*right_count)+"┤"
            add_safe(win,2,0,header,curses.color_pair(self.cp["white"]))
            content_y=3
            rows_max=h-content_y-1
            keys=sorted(COMMANDS.keys())
            aliases={"experience":"experience (/xp)","msg":"msg (/tell)","teammsg":"teammsg (/tm)"}
            items=[]
            for k in keys:
                if self.search and self.search.lower() not in k.lower(): continue
                left=aliases.get(k,k)
                items.append((left,COMMANDS[k]))
            start=min(self.help_scroll,max(0,len(items)-rows_max))
            visible=items[start:start+rows_max]
            y2=content_y
            for left,right in visible:
                add_safe(win,y2,1," ",curses.color_pair(self.cp["white"]))
                add_safe(win,y2,2,f"{left:<{left_w}}",curses.color_pair(self.cp["orange"]))
                add_safe(win,y2,sep_x,"│",curses.color_pair(self.cp["white"]))
                add_safe(win,y2,sep_x+2,right[:max(0,w-(sep_x+3))],curses.color_pair(self.cp["gray"]))
                y2+=1
            footer="╰"+("─"*left_count)+"┴"+("─"*right_count)+"╯"
            add_safe(win,h-1,0,footer,curses.color_pair(self.cp["white"]))
        else:
            left_w=11; sep_x=2+left_w
            left_count=max(1,sep_x-1); right_count=max(0,(w-2)-sep_x)
            header="├"+("─"*left_count)+"┬"+("─"*right_count)+"┤"
            add_safe(win,2,0,header,curses.color_pair(self.cp["white"]))
            content_y=3
            for yy in range(content_y,h-1):
                add_safe(win,yy,sep_x,"│",curses.color_pair(self.cp["white"]))
            groups=[("Overworld",STRUCTURES["Overworld"],self.cp["green"]),("Nether",STRUCTURES["Nether"],self.cp["red"]),("The End",STRUCTURES["The End"],self.cp["magenta"])]
            y2=content_y
            for gi,(label_g,names,color) in enumerate(groups):
                text=", ".join(names)
                width=max(1,w-(sep_x+3))
                wrapped=textwrap.wrap(text,width=width) or [""]
                for i,line in enumerate(wrapped):
                    add_safe(win,y2,1," ",curses.color_pair(self.cp["white"]))
                    add_safe(win,y2,2,(label_g if i==0 else " "*left_w).ljust(left_w),curses.color_pair(self.cp["white"]))
                    add_safe(win,y2,sep_x,"│",curses.color_pair(self.cp["white"]))
                    add_safe(win,y2,sep_x+2,line,curses.color_pair(color))
                    y2+=1
                if gi<len(groups)-1 and y2<h-1:
                    sep="├"+("─"*left_count)+"┼"+("─"*right_count)+"┤"
                    add_safe(win,y2,0,sep,curses.color_pair(self.cp["white"])); y2+=1
            footer="╰"+("─"*left_count)+"┴"+("─"*right_count)+"╯"
            add_safe(win,h-1,0,footer,curses.color_pair(self.cp["white"]))
        win.noutrefresh()
        return


    def _name_color(self,speaker,kind):
        if speaker=="RCON" or kind=="rcon_say": return self.cp["orange"]
        dn=self.dim_map.get(speaker,"unknown")
        if dn=="overworld": return self.cp["green"]
        if dn in ("the_nether","nether"): return self.cp["red"]
        if dn in ("the_end","end"): return self.cp["magenta"]
        return self.cp["white"]
