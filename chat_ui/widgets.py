import curses, re, textwrap
from .utils import add_safe, add_cols, cols_len, clip_cols
from .consts import B

def box(win, title, color_white, color_title):
    h,w=win.getmaxyx()
    win.erase()
    if h<2 or w<2: return
    add_safe(win,0,0,B["tl"]+(B["h"]*(w-2))+B["tr"],curses.color_pair(color_white))
    for y in range(1,h-1):
        add_safe(win,y,0,B["v"],curses.color_pair(color_white))
        add_safe(win,y,w-1,B["v"],curses.color_pair(color_white))
    add_safe(win,h-1,0,B["bl"]+(B["h"]*(w-2))+B["br"],curses.color_pair(color_white))
    t=f" {title} "
    tx=max(1,(w-len(t))//2)
    add_safe(win,0,tx,t,curses.color_pair(color_title))

def render_dimension(win,y,x,left_w,card_w,dim_raw,cp):
    dim_raw=dim_raw.strip('"')
    if ":" in dim_raw: ns,name_dim=dim_raw.split(":",1)
    else: ns,name_dim="minecraft",dim_raw
    ns_attr=curses.color_pair(cp["green_dk"]) if ns=="minecraft" else curses.color_pair(cp["white"])
    colon_attr=curses.color_pair(cp["white"])
    if ns=="minecraft" and name_dim in ("overworld","the_end","the_nether"):
        name_attr=curses.color_pair(cp["green"]) if name_dim=="overworld" else (curses.color_pair(cp["magenta"]) if name_dim=="the_end" else curses.color_pair(cp["red"]))
    else:
        name_attr=curses.color_pair(cp["white"])
    base=f"│ {'Dimension':{left_w}} │ "
    add_safe(win,y,x,base,curses.color_pair(cp["white"]))
    cx=x+len(base)
    add_safe(win,y,cx,ns,ns_attr); cx+=len(ns)
    add_safe(win,y,cx,":",colon_attr); cx+=1
    add_safe(win,y,cx,name_dim,name_attr)

def render_position(win,y,x,left_w,card_w,pos_txt,cp):
    base=f"│ {'Position':{left_w}} │ "
    add_safe(win,y,x,base,curses.color_pair(cp["white"]))
    cx=x+len(base)
    m=re.match(r"X=([^ ]+)\s+Y=([^ ]+)\s+Z=([^ ]+)",pos_txt)
    def fmt(v):
        mm=re.match(r"[-+]?\d+(?:\.\d+)?",v)
        return str(int(float(mm.group(0)))) if mm else v
    if m:
        add_safe(win,y,cx,"X=",curses.color_pair(cp["yellow_dk"])); cx+=2
        v=fmt(m.group(1)); add_safe(win,y,cx,v,curses.color_pair(cp["yellow_lt"])); cx+=len(v)
        add_safe(win,y,cx," Y=",curses.color_pair(cp["yellow_dk"])); cx+=3
        v=fmt(m.group(2)); add_safe(win,y,cx,v,curses.color_pair(cp["yellow_lt"])); cx+=len(v)
        add_safe(win,y,cx," Z=",curses.color_pair(cp["yellow_dk"])); cx+=3
        v=fmt(m.group(3)); add_safe(win,y,cx,v,curses.color_pair(cp["yellow_lt"]))
    else:
        add_safe(win,y,cx,pos_txt,curses.color_pair(cp["yellow_lt"]))

def wrap_segments(segs,width):
    lines=[[]]; used=0
    for text,attr in segs:
        if not text: continue
        tokens=re.findall(r"\S+\s*|\s+",text)
        for tok in tokens:
            while tok:
                if used==0 and tok.strip()=="": tok=""; break
                space_left=width-used
                if space_left<=0:
                    lines.append([]); used=0; space_left=width
                if len(tok)<=space_left:
                    lines[-1].append((tok,attr)); used+=len(tok); tok=""
                else:
                    if len(tok)<=width:
                        lines.append([]); used=0; continue
                    else:
                        lines[-1].append((tok[:space_left],attr)); tok=tok[space_left:]; used=width
    return lines

def line_row(left_label,right_text,left_w,right_w):
    left_txt=str(left_label)
    left_pad=max(0,left_w-cols_len(left_txt))
    right_txt=str(right_text or "")
    right_trim,_=clip_cols(right_txt,right_w)
    right_pad=max(0,right_w-cols_len(right_trim))
    return f"│ {left_txt}{' '*left_pad} │ {right_trim}{' '*right_pad} │"
