import json, os, re, hashlib
from typing import Any, Dict
DEFAULT_CONFIG={'rcon':{'host':'localhost','port':25575,'password':'Password,'timeout':5.0},'exploration':{'player':'Player','dimension':'minecraft:overworld','y':192,'chunks':32,'spawn_x':0,'spawn_z':0,'interval':15.0,'max_tps':1000},'save_file':'auto','save_dir':'saves'}

def load_config(path='config.json'):
    if not os.path.isfile(path):
        save_config(DEFAULT_CONFIG,path)
        return DEFAULT_CONFIG.copy()
    with open(path,'r',encoding='utf-8') as f:
        data=json.load(f)
    def deep_merge(d,default):
        for k,v in default.items():
            if k not in d:
                d[k]=v
            elif isinstance(v,dict) and isinstance(d[k],dict):
                deep_merge(d[k],v)
    deep_merge(data,DEFAULT_CONFIG)
    return data

def save_config(conf,path='config.json'):
    tmp=path+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:
        json.dump(conf,f,indent=2,ensure_ascii=False)
    os.replace(tmp,path)

def _dim_short(dim:str)->str:
    mapping={'minecraft:overworld':'ovw','minecraft:the_nether':'net','minecraft:the_end':'end'}
    if dim in mapping: return mapping[dim]
    dim=dim.replace('minecraft:','')
    return re.sub(r'[^a-zA-Z0-9]+','',dim)[:8] or 'dim'

def _slug_player(p:str)->str:
    return re.sub(r'[^a-zA-Z0-9_-]+','',p)[:16] or 'player'

def compute_save_path(conf:Dict[str,Any])->str:
    save_file=str(conf.get('save_file','auto'))
    save_dir=str(conf.get('save_dir','saves'))
    e=conf['exploration']
    player=_slug_player(str(e['player']))
    dim=_dim_short(str(e['dimension']))
    y=int(e['y']); chunks=int(e['chunks']); sx=int(e['spawn_x']); sz=int(e['spawn_z']); interval=float(e['interval']); max_tps=int(e['max_tps'])
    payload=json.dumps({'player':player,'dim':dim,'y':y,'chunks':chunks,'sx':sx,'sz':sz,'interval':interval,'max_tps':max_tps,'host':str(conf['rcon']['host']),'port':int(conf['rcon']['port'])},sort_keys=True).encode('utf-8')
    h=hashlib.sha1(payload).hexdigest()[:6]
    auto_name=f"{player}-{dim}-c{chunks}-sx{sx}-sz{sz}-y{y}-{h}.json"
    if save_file!='auto':
        if save_file.endswith('/') or os.path.isdir(save_file):
            return os.path.join(save_file, auto_name)
        return save_file
    return os.path.join(save_dir, auto_name)
