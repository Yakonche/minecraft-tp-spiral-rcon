COMMANDS = {
"advancement":"grant|revoke everything|only|from|through|until",
"attribute":"get|base set|get|modifier add|remove|value get",
"ban":"<joueur> [raison]",
"ban-ip":"<ip|joueur>",
"banlist":"players|ips",
"bossbar":"add|remove|list|get|set",
"clear":"[cible] [item] [quantité] [nbt]",
"clone":"<pos1> <pos2> <dest> replace|masked [force|move|normal]",
"damage":"<cible> <amount> [source] [by] [at]",
"data":"get|modify|remove|merge (block|entity|storage)",
"datapack":"enable|disable|list|priorities",
"debug":"start|stop|report",
"defaultgamemode":"survival|creative|adventure|spectator",
"deop":"<joueur>",
"difficulty":"peaceful|easy|normal|hard",
"effect":"give|clear",
"enchant":"<cible> <ench> [niveau]",
"execute":"as|at|positioned|rotated|facing|anchored|align|in|on|store|if|unless|run",
"experience":"add|set|query",
"fill":"<pos1> <pos2> <bloc> [mode]",
"fillbiome":"<pos1> <pos2> <biome> [replace]",
"forceload":"add|remove|query",
"function":"<nom_fonction>",
"gamemode":"survival|creative|adventure|spectator [cible]",
"gamerule":"<règle> <valeur>",
"give":"<cible> <item> [quantité] [nbt/components]",
"help":"[commande]",
"item":"replace|modify|display",
"jfr":"start|stop|dump",
"kick":"<joueur> [raison]",
"kill":"<cible>",
"list":"[uuids]",
"locate":"structure|biome|poi",
"loot":"give|insert|replace|spawn",
"me":"<texte>",
"msg":"<cible> <message>",
"op":"<joueur>",
"pardon":"<joueur>",
"pardon-ip":"<ip>",
"particle":"<particule> [pos] [delta] [speed] [count] [force|normal] [cible]",
"place":"feature|jigsaw|structure|template",
"playsound":"<son> <source> <cible> [pos] [vol] [pitch] [minVol]",
"publish":"[port]",
"recipe":"give|take <cible> <recette|*>",
"reload":"recharge datapacks",
"ride":"mount|dismount|start_riding|stop_riding|summon_rider",
"save-all":"[flush]",
"save-off":"désactive autosave",
"save-on":"réactive autosave",
"say":"<message>",
"schedule":"function|clear",
"scoreboard":"objectives|players",
"seed":"affiche graine",
"setblock":"<pos> <bloc> [mode]",
"spawnpoint":"[cible] [pos] [angle]",
"spreadplayers":"<centreX> <centreZ> <distMin> <distMax> <respectTeams> <cibles>",
"stop":"arrête serveur",
"stopsound":"<cible> [source] [son]",
"structure":"save|load|delete|list",
"summon":"<entité> [pos] [nbt/components]",
"tag":"<cible> add|remove|list",
"team":"add|remove|empty|join|leave|list|modify",
"teammsg":"<message>",
"tellraw":"<cible> <json>",
"time":"set|add|query",
"title":"<cible> title|subtitle|actionbar|times|clear|reset",
"tp":"<cible> <dest|pos [rot]>",
"trigger":"<objectif> [add|set]",
"weather":"clear|rain|thunder [durée]",
"whitelist":"on|off|add|remove|list|reload",
"worldborder":"set|add|center|damage|warning"
}

STRUCTURES = {
"Overworld":["ancient_city","buried_treasure","desert_pyramid","igloo","jungle_pyramid","mansion","mineshaft","monument","ocean_ruin_cold","ocean_ruin_warm","pillager_outpost","ruined_portal","shipwreck","stronghold","swamp_hut","trail_ruins","village_desert","village_plains","village_savanna","village_snowy","village_taiga"],
"Nether":["bastion_remnant","fortress","nether_fossil","ruined_portal"],
"The End":["end_city"]
}

def flat_commands():
    return list(COMMANDS.keys())

def suggest_commands(prefix):
    if not prefix:
        return []
    p = prefix.strip()
    if p.startswith('/'):
        p = p[1:]
    keys = sorted(COMMANDS.keys())
    res = [k for k in keys if k.startswith(p)]
    return res if res else [k for k in keys if p in k]
