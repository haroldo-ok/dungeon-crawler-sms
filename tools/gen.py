#!/usr/bin/env python3
"""
Data generator for the SMS first-person dungeon crawler.

Produces:
  gen/gen.h, gen/gen.c   - small fixed-bank data (palette, HUD tiles, map, name tables)
  gen/bank_floor.bin     - slot-1 bank: chunky->planar LUT, sky, floor/ceiling textures
  gen/bank_wall.bin      - slot-1 bank: wall textures (32x32, shade x parity variants)
  gen/pose_NN.bin        - slot-2 banks: per-camera-pose ray lists + floor LUT + q table

Geometry ("canonical" frame): a = right, b = forward, base cell centre = (0,0),
cells centred on integers.  World: x east, y south.  Facing f: 0=N 1=E 2=S 3=W.
"""
import math, os, sys, random
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CHECK_ONLY = "--check" in sys.argv
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = _args[0] if _args else "gen"

W, H, HALF = 64, 48, 24          # logical view (each logical pixel = 2x2 screen pixels)
FOCAL = 32.0                     # logical px per unit at distance 1 (90 deg FOV)
S = 6                            # sub-steps per move / turn
MAXD = 12.0                      # view distance (fog beyond)
NPOSE = 1 + 3 * (S - 1) + 6      # + quarter-step poses for "quick" mode

# ----------------------------------------------------------------------------- content
# Everything the game is about lives in tools/content.py; this section checks it
# and compiles it into tables.  Errors name the level / monster / event at fault.
from art import *
import importlib
C = importlib.import_module(os.environ.get("SMS_CONTENT", "content"))   # tools/content.py


class ContentError(Exception):
    pass


def need(cond, what):
    if not cond:
        raise ContentError(what)


MSG_W = 27                            # characters per message line (game.c)
FONTSET = set(" !'+,-./0123456789:>?ABCDEFGHIJKLMNOPQRSTUVWXYZ|")


def msg_fits(text, w=MSG_W, lines=2):
    """the game's word wrap (print_line): '|' breaks, long lines wrap at a space"""
    n, s = 0, text
    while s:
        seg = s.split('|', 1)[0]
        cut = len(seg)
        if cut > w:
            cut = w
            while cut and seg[cut] != ' ':
                cut -= 1
            if not cut:
                cut = w
        n += 1
        s = s[cut:]
        if s[:1] in ('|', ' '):
            s = s[1:]
    return n <= lines


def check_text(text, where, lines=2):
    bad = set(text) - FONTSET
    need(not bad, f"{where}: characters missing from the font: {''.join(sorted(bad))!r} in {text!r}")
    need(msg_fits(text, lines=lines), f"{where}: does not fit in {lines} message lines of {MSG_W}: {text!r}")


# ---- sprites and object kinds: monsters first (kind 1..NMON), then props
SIZE_NAMES = list(C.SIZES)
SPR_CLASS = [C.SIZES[k] for k in SIZE_NAMES]
need(len(SPR_CLASS) <= 5, "at most 5 sprite SIZES (scale tables share the pose banks)")
KINDS = list(C.MONSTERS) + list(C.PROPS)
NMON = len(C.MONSTERS)
OBJKIND = {k: i + 1 for i, k in enumerate(KINDS)}
SPRITES, KIND_FRAME, KIND_CLS = [], {}, {}
for k in KINDS:
    d = C.MONSTERS.get(k) or C.PROPS[k]
    need(d["size"] in C.SIZES, f"{k}: unknown size {d['size']!r}")
    KIND_CLS[k] = SIZE_NAMES.index(d["size"])
    KIND_FRAME[k] = len(SPRITES)
    if k in C.MONSTERS:
        idle, attack = d["sprite"]
        SPRITES += [idle, attack, spr_hurt(idle)]
    else:
        SPRITES.append(d["sprite"])
for i, s_ in enumerate(SPRITES):
    need(np.shape(s_) == (32, 32), f"sprite frame {i}: must be 32x32")
KF_MONSTER, KF_BLOCKS, KF_BOSS, KF_SHOP = 1, 2, 4, 8
ARMOR_DIV = {"full": 1, "half": 2, "none": 0}

# ---- items
need(1 <= len(C.CONSUMABLES) <= 3, "1 to 3 CONSUMABLES (HUD and item menu space)")
CONS = list(C.CONSUMABLES)
need(C.LOOT["item"] in CONS and C.LOOT["one_in"] >= 1, "LOOT: an item and a 1-in-N chance")
need(len(C.WEAPONS) <= 8 and len(C.ARMORS) <= 8, "at most 8 weapons / armours")
for nm, b, p in C.WEAPONS + C.ARMORS:
    need(len(nm) <= 12 and not set(nm) - FONTSET, f"item name {nm!r}: at most 12 font characters")
menu_w = 2 + sum(2 + len(k) for k in CONS + ["BACK"])
need(menu_w <= 32, f"item menu {CONS + ['BACK']} is {menu_w} columns, the screen has 32")
for k, c in C.CONSUMABLES.items():
    need(len(c["hud"]) == 3, f"{k}: hud label must be 3 characters")
    check_text(c["use"], f"consumable {k}")
    need(c["sound"] in ("PICKUP", "MAGIC", "DOOR"), f"{k}: unknown sound")
SOUNDS = {"PICKUP": 0, "DOOR": 1, "MAGIC": 2}

# ---- themes: texture sets -> map byte legend + cell kinds
WALL_BASE, DOOR_B, LOCKED_B, STAIRS_B, SECRET_B, EXTRA_B = 16, 20, 21, 22, 23, 24
THEME_NAMES = list(C.THEMES)
THEME = {}
for tn, T in C.THEMES.items():
    walls = list(T["walls"].items())
    need(1 <= len(walls) <= 4, f"theme {tn}: 1 to 4 plain walls")
    for ch, tex in walls:
        need(np.shape(tex) == (32, 32), f"theme {tn}: wall {ch!r} must be 32x32")
    flats = list(T["flats"])
    need(len(flats) <= 5, f"theme {tn}: at most 5 flats (one floor bank)")
    for fn, tex in T["flats"].items():
        need(np.shape(tex) == (16, 16), f"theme {tn}: flat {fn!r} must be 16x16")
    floors, ceils = [], [None]                      # ceiling index 0 = open sky
    legend = {}
    for ch, (fl, ce) in T["opens"].items():
        need(fl in T["flats"] and (ce is None or ce in T["flats"]), f"theme {tn}: open {ch!r} names an unknown flat")
        if fl not in floors:
            floors.append(fl)
        if ce not in ceils:
            ceils.append(ce)
        legend[ch] = floors.index(fl) | (ceils.index(ce) << 2)
    need(len(floors) <= 4 and len(ceils) <= 4, f"theme {tn}: at most 4 floors and 3 ceilings")
    for i, (ch, _) in enumerate(walls):
        legend[ch] = WALL_BASE + i
    legend.update({'D': DOOR_B, 'L': LOCKED_B, 'S': STAIRS_B, 'X': SECRET_B})
    extra = T.get("extra")
    if extra:
        legend[extra[0]] = EXTRA_B
    chars = [c for c, _ in walls] + list(T["opens"]) + ([extra[0]] if extra else [])
    need(len(chars) == len(set(chars)) and not set(chars) & set("DLSX"),
         f"theme {tn}: map characters clash: {chars}")
    need(T["open_as"] in T["opens"], f"theme {tn}: open_as must be an open char")
    need(np.shape(T["sky"]) == (24, 64), f"theme {tn}: sky must be 64x24")
    # cell kinds (render.c copies them to 0xDA00): wall type+1, floor page, ceiling page
    page = lambda name: 0x40 + 0x14 + flats.index(name) * 8
    xw, xf, xc = [0] * 32, [0] * 32, [0] * 32
    o_f, o_c = T["opens"][T["open_as"]]
    for m in range(32):
        if m < 16:
            fi, ci = m & 3, m >> 2
            xf[m] = page(floors[fi]) if fi < len(floors) else page(floors[0])
            xc[m] = page(ceils[ci]) if 0 < ci < len(ceils) else 0
        else:
            w = {DOOR_B: 5, LOCKED_B: 6, STAIRS_B: 7, SECRET_B: 1, EXTRA_B: 8}.get(m, m - WALL_BASE + 1)
            xw[m] = w if (m >= DOOR_B or m - WALL_BASE < len(walls)) else 1
            xf[m] = page(o_f)
            xc[m] = page(o_c) if o_c else 0
    # automap colours: an open cell shows its floor's most common colour
    def common(tex):
        v, c = np.unique(np.asarray(tex), return_counts=True)
        return int(v[np.argmax(c)])
    mapcol = [1] * 32
    for m in range(16):
        fi = m & 3
        mapcol[m] = common(T["flats"][floors[fi]]) if fi < len(floors) else 1
        if mapcol[m] in (0, 1):
            mapcol[m] = 2                             # keep floors visible against walls
    mapcol[DOOR_B], mapcol[LOCKED_B], mapcol[STAIRS_B] = 5, 15, 12
    wall_a = [t for _, t in walls] + [walls[0][1]] * (4 - len(walls))
    wall_b = [T["door"], T["locked"], T["stairs"], extra[1] if extra else T["door"]]
    THEME[tn] = dict(legend=legend, kinds=xw + xf + [0] * 32 + xc, open=legend[T["open_as"]], mapcol=mapcol,
                     wall_a=wall_a, wall_b=wall_b, flats=[T["flats"][n] for n in flats], sky=T["sky"],
                     walls=set(c for c, _ in walls) | {'D', 'L', 'S', 'X'} | ({extra[0]} if extra else set()))

# ---- levels
LEVEL_IDS = [L["id"] for L in C.LEVELS]
need(len(LEVEL_IDS) == len(set(LEVEL_IDS)), "level ids must be unique")
need(len(C.LEVELS) <= 12, "at most 12 levels (0xDB00 level-state area)")
SONG_NAMES = [s[0] for s in C.SONGS]
for need_song in ("TITLE", "BATTLE", "BOSS", "VICTORY", "GAMEOVER", "ENDING"):
    need(need_song in SONG_NAMES, f"SONGS needs {need_song}")
OPS = {"END": 0, "MSG": 1, "ITEM": 2, "KEYS": 3, "GOLD": 4, "HEAL": 5, "TELE": 6, "STAIRS": 7,
       "TAKE": 8, "OPEN": 9, "SOUND": 10, "WIN": 11}
MESSAGES = []


def msg_id(text, where):
    check_text(text, where)
    if text not in MESSAGES:
        MESSAGES.append(text)
    return MESSAGES.index(text)


START_L = LEVEL_IDS.index(C.START[0])
START = (START_L,) + tuple(C.START[1:])
MAX_VIS = 12
EV_ROWS, EV_SCRIPT, EV_START, LEVEL_BYTES, ARRIVALS = [], [], [0], [], {i: [] for i in range(len(C.LEVELS))}
ARRIVALS[START_L].append(START[1:3])
for li, L in enumerate(C.LEVELS):
    for e in L["events"]:
        for a in e["do"]:
            if a[0] == "STAIRS":
                need(a[1] in LEVEL_IDS, f"{L['id']}: stairs to unknown level {a[1]!r}")
                ARRIVALS[LEVEL_IDS.index(a[1])].append((a[2], a[3]))
for li, L in enumerate(C.LEVELS):
    where = f"level {L['id']}"
    need(L["theme"] in THEME, f"{where}: unknown theme {L['theme']!r}")
    need(L["music"] in SONG_NAMES, f"{where}: unknown song {L['music']!r}")
    need(len(L["name"]) <= 12 and not set(L["name"]) - FONTSET, f"{where}: name at most 12 font characters")
    TH = THEME[L["theme"]]
    m = L["map"]
    need(len(m) == 16 and all(len(r) == 16 for r in m), f"{where}: map must be 16x16")
    for y in range(16):
        for x in range(16):
            need(m[y][x] in TH["legend"], f"{where}: map char {m[y][x]!r} at {x},{y} is not in theme {L['theme']}")
    for i in range(16):
        for ch in (m[0][i], m[15][i], m[i][0], m[i][15]):
            need(ch in TH["walls"] and ch not in "DLX", f"{where}: the border must be solid wall")
    is_open = lambda x, y: m[y][x] not in TH["walls"]
    LEVEL_BYTES.append([TH["legend"][m[y][x]] for y in range(16) for x in range(16)])
    # objects
    objs = L.get("objects", [])
    need(len(objs) <= MAX_VIS, f"{where}: at most {MAX_VIS} objects")
    for k, x, y, n in objs:
        need(k in OBJKIND, f"{where}: unknown object kind {k!r}")
        need(is_open(x, y), f"{where}: object {k} at {x},{y} is inside a wall")
        if k in C.MONSTERS:
            need(1 <= n <= 3, f"{where}: {k} at {x},{y}: group size 1-3")
    # events
    opened = set()
    for e in L["events"]:
        x, y = e["at"]
        ew = f"{where} event at {x},{y}"
        need(0 < x < 15 and 0 <= y < 16, f"{ew}: off the map")
        need(sum(1 for e2 in L["events"] if e2["at"] == (x, y)) == 1, f"{ew}: two events on one cell")
        code = []
        for a in e["do"]:
            op = a[0]
            need(op in OPS and op != "END", f"{ew}: unknown action {op!r}")
            code.append(OPS[op])
            if op == "MSG":
                code.append(msg_id(a[1], ew))
            elif op == "ITEM":
                need(a[1] in CONS, f"{ew}: unknown item {a[1]!r}")
                code += [CONS.index(a[1]), a[2]]
            elif op in ("KEYS",):
                code.append(a[1])
            elif op == "GOLD":
                need(0 < a[1] < 65536, f"{ew}: gold")
                code += [a[1] & 255, a[1] >> 8]
            elif op == "TELE":
                need(is_open(a[1], a[2]), f"{ew}: teleport target is a wall")
                code += [a[1], a[2], a[3] & 3]
                ARRIVALS[li].append((a[1], a[2]))
            elif op == "STAIRS":
                tl = LEVEL_IDS.index(a[1])
                tm = C.LEVELS[tl]["map"]
                need(tm[a[3]][a[2]] not in THEME[C.LEVELS[tl]["theme"]]["walls"] - set("DLX"),
                     f"{ew}: stairs arrive in a wall")
                code += [tl, a[2], a[3], a[4] & 3]
            elif op == "TAKE":
                need(any((ox, oy) == (x, y) for _, ox, oy, _ in objs), f"{ew}: TAKE but no object here")
            elif op == "OPEN":
                need(not is_open(a[1], a[2]) and m[a[2]][a[1]] != 'S', f"{ew}: OPEN target must be a wall")
                code += [a[1], a[2]]
                opened.add((a[1], a[2]))
            elif op == "SOUND":
                need(a[1] in SOUNDS, f"{ew}: unknown sound {a[1]!r}")
                code.append(SOUNDS[a[1]])
        code.append(0)
        if m[y][x] == 'S':
            need(any(a[0] == "STAIRS" for a in e["do"]), f"{ew}: an event on stairs must use STAIRS")
        EV_ROWS.append((x, y, 1 if e.get("once") else 0, len(EV_SCRIPT)))
        EV_SCRIPT += code
    EV_START.append(len(EV_ROWS))
    for y in range(16):
        for x in range(16):
            if m[y][x] == 'S':
                need(any(e["at"] == (x, y) for e in L["events"]), f"{where}: stairs at {x},{y} lead nowhere")
    # every open cell reachable from where you arrive (doors, secret walls and
    # walls opened by events count as passable)
    passable = lambda x, y: is_open(x, y) or m[y][x] in "DLX" or (x, y) in opened
    starts = ARRIVALS[li]
    need(starts, f"{where}: nothing leads here")
    seen, st = set(starts), list(starts)
    while st:
        x, y = st.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if passable(nx, ny) and (nx, ny) not in seen:
                seen.add((nx, ny))
                st.append((nx, ny))
    lost = [(x, y) for y in range(16) for x in range(16) if passable(x, y) and (x, y) not in seen]
    need(not lost, f"{where}: unreachable cells {lost}")
    if L.get("shop"):
        sh = L["shop"]
        need(sh["weapons"] < len(C.WEAPONS) and sh["armors"] < len(C.ARMORS), f"{where}: shop stock past the item lists")
        need(all(g in CONS for g in sh["goods"]), f"{where}: shop sells an unknown item")
    if any(k == "MERCHANT" or C.PROPS.get(k, {}).get("shop") for k, *_ in objs):
        need(L.get("shop"), f"{where}: a merchant but no shop")
NEV = len(EV_ROWS)
need(NEV <= 128, "at most 128 events (ev_done bits)")
need(len(EV_SCRIPT) < 65536, "event scripts too long")
NOBJ = sum(len(L.get("objects", [])) for L in C.LEVELS)

# ---- monster texts must fit the battle messages (with 2-3 digit numbers)
for k, md in C.MONSTERS.items():
    w = f"monster {k}"
    need(len(md["name"]) <= 14, f"{w}: name at most 14 characters (battle panel)")
    for t in (f"{md['group']} 3 {md['plural']}!", f"A {md['name']} APPEARS!", f"THE {md['name']} HITS YOU|FOR 99 DAMAGE",
              f"YOU HIT THE {md['name']} FOR 999!", f"FIRE BURNS THE {md['name']} FOR 999!",
              f"THE {md['name']} MISSES", f"THE {md['name']}{md['death']}", md["attack"]):
        check_text(t, w)
    if md.get("spell"):
        sp = md["spell"]
        need(sp["armor"] in ARMOR_DIV and sp["every"] >= 1 and sp["rnd"] >= 1, f"{w}: spell (every >= 1, rnd >= 1)")
        check_text(f"THE {md['name']} {sp['text']} 99 DAMAGE!", w)
    need(0 <= md["run"] <= 100, f"{w}: run is a percentage")
for p in C.PROPS.values():
    if p.get("bump"):
        msg_id(p["bump"], "prop")
check_text(C.TEXT["intro"], "intro")
for k in ("title", "tagline"):
    need(len(C.TEXT[k]) <= 26 and not set(C.TEXT[k]) - FONTSET, f"TEXT {k}: at most 26 font characters")
MAP_HELP = f"MAP  L/R STEP MODE|UP DRINK {CONS[0]}  2 EXIT"
check_text(MAP_HELP, "automap help (first consumable's name)")
for t in C.TEXT["ending"]:
    check_text(t, "ending")


# ----------------------------------------------------------------------------- projection
def qtable():
    """q = round(4*hh), hh = half wall height in logical rows = 16/perp"""
    Wt, V0, ST = [], [], []
    for q in range(256):
        hh = max(q, 1) / 4.0
        w = 0
        while w < HALF and w + 0.5 < hh:
            w += 1
        step = 16.0 / hh
        st = int(step * 256)                    # floor: never overshoot
        v0 = 16.0 - (w - 0.5) * step if w else 0.0
        v0i = int(math.ceil(v0 * 256)) if w else 0
        if w:
            last = v0i + st * (2 * w - 1)
            while last >= 32 * 256:             # keep inside the 32-texel column
                v0i -= 1
                last -= 1
            assert v0i >= 0
        Wt.append(w)
        V0.append(v0i)
        ST.append(st)
    return Wt, V0, ST


QW, QV0, QST = qtable()
Q_FOG = int(math.ceil(16.0 / MAXD * 4))
W_FOG = QW[Q_FOG]
FLOOR_ROWS = HALF - W_FOG


def q_of(t):
    return max(1, min(255, int(math.floor(16.0 / max(t, 0.01) * 4)) + 1))


def poses():
    P = [(0.0, 0.0, 0.0)]
    for k in range(1, S):
        P.append((0.0, k / S, 0.0))
    for k in range(1, S):
        P.append((k / S, 0.0, 0.0))
    for k in range(1, S):
        P.append((0.0, 0.0, 90.0 * k / S))
    # quick mode (4 sub-steps; the half-way poses are shared with the S=6 set)
    P += [(0.0, 0.25, 0.0), (0.0, 0.75, 0.0), (0.25, 0.0, 0.0), (0.75, 0.0, 0.0),
          (0.0, 0.0, 22.5), (0.0, 0.0, 67.5)]
    assert len(P) == NPOSE
    return P


def cell_of(a, b):
    return (math.floor(a + 0.5), math.floor(b + 0.5))


def build_pose(pa, pb, th):
    t = math.radians(th)
    F = (math.sin(t), math.cos(t))
    R = (math.cos(t), -math.sin(t))
    cells = {}

    def cid(c):
        if c not in cells:
            cells[c] = len(cells)
        return cells[c]

    rays, floors = [], []
    for x in range(W):
        xc = (x + 0.5 - 32) / 32.0
        D = (F[0] + R[0] * xc, F[1] + R[1] * xc)
        # ---- DDA (t = forward/perpendicular distance since F.D == 1)
        ca, cb = cell_of(pa, pb)
        stepa = 1 if D[0] > 0 else -1
        stepb = 1 if D[1] > 0 else -1
        inva = abs(1 / D[0]) if abs(D[0]) > 1e-12 else 1e30
        invb = abs(1 / D[1]) if abs(D[1]) > 1e-12 else 1e30
        ta = ((ca + 0.5 * stepa) - pa) / D[0] if abs(D[0]) > 1e-12 else 1e30
        tb = ((cb + 0.5 * stepb) - pb) / D[1] if abs(D[1]) > 1e-12 else 1e30
        ents = []
        while True:
            if ta < tb:
                tt, side = ta, 1
                ca += stepa
                ta += inva
            else:
                tt, side = tb, 0
                cb += stepb
                tb += invb
            if tt > MAXD:
                break
            ha, hb = pa + D[0] * tt, pb + D[1] * tt
            if side == 0:
                fr = (ha + 0.5) - math.floor(ha + 0.5)
                tc = fr if D[1] > 0 else 1 - fr
            else:
                fr = (hb + 0.5) - math.floor(hb + 0.5)
                tc = 1 - fr if D[0] > 0 else fr
            tci = min(31, max(0, int(tc * 32)))
            ents.append((cid((ca, cb)), q_of(tt), tci | (side << 7)))
        rays.append(ents)
        # ---- floor samples, nearest row first
        runs = []
        for j in range(FLOOR_ROWS):
            r = 23.5 - j
            d = 16.0 / r
            Pa, Pb = pa + d * D[0], pb + d * D[1]
            c = cell_of(Pa, Pb)
            u, v = Pa + 0.5 - c[0], Pb + 0.5 - c[1]
            iu, iv = min(15, int(u * 16)), min(15, int(v * 16))
            off = iu * 16 + iv
            i = cid(c)
            if runs and runs[-1][0] == i:
                runs[-1][1].append(off)
            else:
                runs.append((i, [off]))
        floors.append(runs)
    sky = int(round(th / 90.0 * 64)) & 63
    cl = sorted(cells.items(), key=lambda kv: kv[1])
    assert len(cl) < 255, f"too many cells in pose: {len(cl)}"
    return [c for c, _ in cl], rays, floors, sky


# ----------------------------------------------------------------------------- floor-texture rotation
def world_from_canon(lu, lv, f):
    x, y = lu, -lv
    for _ in range(f):
        x, y = -y, x
    return x, y


def flat_page(tex, f, parity):
    out = bytearray(256)
    for iu in range(16):
        for iv in range(16):
            lu, lv = (iu + 0.5) / 16 - 0.5, (iv + 0.5) / 16 - 0.5
            wx, wy = world_from_canon(lu, lv, f)
            tx = min(15, max(0, int((wx + 0.5) * 16)))
            ty = min(15, max(0, int((wy + 0.5) * 16)))
            c = int(tex[ty][tx])
            out[iu * 16 + iv] = (c << 4) if parity == 0 else c
    return out


# ----------------------------------------------------------------------------- banks
BANK = 16384
POSEBANK0 = 2                         # 22 camera poses: ray lists, billboard + scale tables
SPRBANK = POSEBANK0 + NPOSE           # billboard sprites, 8 frames per bank
NSPRBANK = (len(SPRITES) + 7) // 8
DATABANK = SPRBANK + NSPRBANK         # title / ending logos
THEMEBANK0 = DATABANK + 1             # per texture set: floor bank, wall bank, door bank
THEMEBANK = {tn: THEMEBANK0 + 3 * i for i, tn in enumerate(THEME_NAMES)}
NBANKS = THEMEBANK0 + 3 * len(THEME_NAMES)
need(NBANKS <= 256, "ROM too big")


def build_floor_bank(T):
    b = bytearray(BANK)
    # chunky->planar: page p = left pair (c0<<4|c1) -> bits 7..4, page 4+p = right pair -> bits 3..0
    for p in range(4):
        for x in range(256):
            c0, c1 = x >> 4, x & 15
            l = (0xC0 if (c0 >> p) & 1 else 0) | (0x30 if (c1 >> p) & 1 else 0)
            b[p * 256 + x] = l
            b[(4 + p) * 256 + x] = l >> 4
    # sky: 0x0800 + parity*1536 + col*24 + row
    for par in range(2):
        for col in range(64):
            for row in range(24):
                c = int(T["sky"][row][col])
                b[0x800 + par * 1536 + col * 24 + row] = (c << 4) if par == 0 else c
    # flats: page 0x14 + (t*4+f)*2 + parity
    for ti, tex in enumerate(T["flats"]):
        need(np.shape(tex) == (16, 16), "floor / ceiling textures must be 16x16")
        for f in range(4):
            for par in range(2):
                pg = 0x14 + (ti * 4 + f) * 2 + par
                assert pg < 0x40
                b[pg * 256:(pg + 1) * 256] = flat_page(tex, f, par)
    return b


def build_wall_bank(walls):
    b = bytearray(BANK)
    for t, tex in enumerate(walls):
        for s in range(2):
            for par in range(2):
                base = ((t * 2 + s) * 2 + par) * 1024
                for c in range(32):
                    for r in range(32):
                        col = int(tex[r][c])
                        if s:
                            col = DARK[col]
                        b[base + c * 32 + r] = (col << 4) if par == 0 else col
    return b


def spr_tables(scale, lift):
    """per q: top row, height rows, texel step (8.8), half width (columns)"""
    top, hgt, st, w2 = [], [], [], []
    for q in range(256):
        hh = max(q, 1) / 4.0
        size = scale * 2 * hh
        hi = max(2, int(round(size)))
        bottom = 24 + hh - lift * 2 * hh
        t = int(math.floor(bottom - hi + 0.5))
        top.append(max(-128, min(127, t)))
        hgt.append(min(255, hi))
        step = (32 * 256) // min(255, hi)
        st.append(step)
        w2.append(min(255, hi) // 2)
    return top, hgt, st, w2


def scale_tables():
    b = bytearray()
    for sc, lift in SPR_CLASS:
        top, hgt, st, w2 = spr_tables(sc, lift)
        assert all(w == h // 2 for w, h in zip(w2, hgt))         # half width = height / 2
        b += bytes(t & 255 for t in top) + bytes(hgt) + bytes(s_ & 255 for s_ in st) + \
            bytes(s_ >> 8 for s_ in st)
    return b


SCALE_OFF = 0x2600       # scale tables live in every pose bank (slot 2), 4 pages per class


def build_sprite_bank(first):
    b = bytearray([0xFF]) * BANK
    for fi, spr in enumerate(SPRITES[first:first + 8]):
        for par in range(2):
            base = (fi * 2 + par) * 1024
            for c in range(32):
                for r in range(32):
                    v = int(spr[r][c])
                    b[base + c * 32 + r] = 0xFF if v == TRANSP else ((v << 4) if par == 0 else v)
    return b


# billboard table: object at the centre of canonical cell (da, db)
BB_DA0, BB_DA1, BB_DB0, BB_DB1 = -8, 8, -2, 12
BB_NA = BB_DA1 - BB_DA0 + 1
BB_OFF = 0x3C00


def billboard_table(pa, pb, th):
    t_ = math.radians(th)
    F = (math.sin(t_), math.cos(t_))
    R = (math.cos(t_), -math.sin(t_))
    out = bytearray()
    for db in range(BB_DB0, BB_DB1 + 1):
        for da in range(BB_DA0, BB_DA1 + 1):
            va, vb = da - pa, db - pb
            t = va * F[0] + vb * F[1]
            u = va * R[0] + vb * R[1]
            if t < 0.45 or t > MAXD:
                out += bytes([0, 0])
                continue
            xc = int(math.floor(32 + 32 * u / t))
            q = max(1, min(255, int(round(16.0 / t * 4))))
            hh = q / 4.0
            if xc + hh < -2 or xc - hh > 66 or xc < -100 or xc > 127:
                out += bytes([0, 0])
                continue
            out += bytes([xc & 255, q])
    return out


POSE_HDR = 0x0900      # after the 5-page q table + 4 delta pages


def build_pose_bank(pose):
    cells, rays, floors, sky = build_pose(*pose)
    b = bytearray(BANK)
    for q in range(256):
        b[0x000 + q] = QW[q]
        b[0x100 + q] = QV0[q] & 255
        b[0x200 + q] = QV0[q] >> 8
        b[0x300 + q] = QST[q] & 255
        b[0x400 + q] = QST[q] >> 8
    # packed map-index deltas per facing: world idx = (cy*16+cx + delta) & 255
    for f in range(4):
        for i, (a, bb) in enumerate(cells):
            dx, dy = [(a, -bb), (bb, a), (-a, bb), (-bb, -a)][f]
            b[0x500 + f * 256 + i] = (dy * 16 + dx) & 255
    h = POSE_HDR
    b[h + 0] = len(cells)
    b[h + 1] = sky
    coltab = h + 16
    celltab = coltab + 256
    for i, (a, bb) in enumerate(cells):
        assert -128 <= a < 128 and -128 <= bb < 128
        b[celltab + 2 * i] = a & 255
        b[celltab + 2 * i + 1] = bb & 255
    p = celltab + 2 * len(cells)
    for x in range(W):
        rp = p
        for (ci, q, tcs) in rays[x]:
            b[p:p + 3] = bytes([ci, q, tcs])
            p += 3
        b[p] = 0xFF
        b[p + 1] = Q_FOG
        p += 2
        fp = p
        for ci, offs in floors[x]:
            b[p] = ci
            b[p + 1] = len(offs)
            p += 2
            for o in offs:
                b[p] = o
                p += 1
        b[coltab + 4 * x + 0] = (0x8000 + rp) & 255
        b[coltab + 4 * x + 1] = (0x8000 + rp) >> 8
        b[coltab + 4 * x + 2] = (0x8000 + fp) & 255
        b[coltab + 4 * x + 3] = (0x8000 + fp) >> 8
        assert p < SCALE_OFF, "pose bank overflow"
    st = scale_tables()
    assert SCALE_OFF + len(st) <= BB_OFF
    b[SCALE_OFF:SCALE_OFF + len(st)] = st
    bb = billboard_table(*pose)
    b[BB_OFF:BB_OFF + len(bb)] = bb
    return b, p, len(cells)


# ----------------------------------------------------------------------------- HUD tiles + font
FONT = {
    'A': ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    'B': ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    'C': ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    'D': ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    'E': ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    'F': ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    'G': ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    'H': ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    'I': ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    'J': ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    'K': ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    'L': ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    'M': ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    'N': ["10001", "10001", "11001", "10101", "10011", "10001", "10001"],
    'O': ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    'P': ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    'Q': ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    'R': ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    'S': ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    'T': ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    'U': ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    'V': ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    'W': ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    'X': ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    'Y': ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    'Z': ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    '0': ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    '1': ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    '2': ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    '3': ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    '4': ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    '5': ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    '6': ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    '7': ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    '8': ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    '9': ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    ':': ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    '-': ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    '/': ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    '.': ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    '+': ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    '!': ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    ',': ["00000", "00000", "00000", "00000", "01100", "00100", "01000"],
    "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"],
    '>': ["01000", "00100", "00010", "00001", "00010", "00100", "01000"],
    '?': ["01110", "10001", "00001", "00110", "00100", "00000", "00100"],
}
FONTCHARS = " " + "".join(sorted(k for k in FONT))
HUD_BASE = 384                   # first HUD tile in VRAM (tiles 0..383 = two view buffers)


def planar_tile(px):
    """px: 8x8 colour indices -> 32 bytes"""
    out = bytearray()
    for y in range(8):
        for p in range(4):
            v = 0
            for x in range(8):
                if (px[y][x] >> p) & 1:
                    v |= 0x80 >> x
            out.append(v)
    return out


def hud_tiles():
    tiles = []
    BG, FG = NAVY, CREAM
    # 0: background
    tiles.append(planar_tile([[BG] * 8 for _ in range(8)]))
    # font glyphs (FONTCHARS order, starting at index 1)
    for ch in FONTCHARS:
        g = [[BG] * 8 for _ in range(8)]
        if ch != ' ':
            for y, row in enumerate(FONT[ch]):
                for x, bit in enumerate(row):
                    if bit == '1':
                        g[y][x + 1] = FG
                        if y + 1 < 8 and x + 2 < 8 and g[y + 1][x + 2] == BG:
                            g[y + 1][x + 2] = BLACK  # drop shadow
        tiles.append(planar_tile(g))
    # frame pieces: TL, T, TR, L, R, BL, B, BR
    def frame(kind):
        g = [[BG] * 8 for _ in range(8)]
        for y in range(8):
            for x in range(8):
                c = BG
                top = kind in ('TL', 'T', 'TR')
                bot = kind in ('BL', 'B', 'BR')
                left = kind in ('TL', 'L', 'BL')
                right = kind in ('TR', 'R', 'BR')
                if top and y >= 4:
                    c = TAN if y == 4 else (BROWN if y < 7 else DRED)
                if bot and y <= 3:
                    c = DRED if y == 3 else (BROWN if y > 0 else TAN)
                if left and x >= 4:
                    c2 = TAN if x == 4 else (BROWN if x < 7 else DRED)
                    if not (top and y < 4) and not (bot and y > 3):
                        c = c2
                if right and x <= 3:
                    c2 = DRED if x == 3 else (BROWN if x > 0 else TAN)
                    if not (top and y < 4) and not (bot and y > 3):
                        c = c2
                if (top or bot) and (left or right):
                    inside_y = (y >= 4) if top else (y <= 3)
                    inside_x = (x >= 4) if left else (x <= 3)
                    c = BG
                    if inside_x and inside_y:
                        c = GRAY if (x in (4, 3) or y in (4, 3)) else DGRAY
                g[y][x] = c
        return g
    for k in ('TL', 'T', 'TR', 'L', 'R', 'BL', 'B', 'BR'):
        tiles.append(planar_tile(frame(k)))
    # target arrow (hardware sprite, colour 0 = transparent): a bold down-pointer
    rows = ["01111110", "12222221", "01222210", "00122100", "00011000", "00000000", "00000000", "00000000"]
    arrow = [[[0, DRED, WHITE][int(c)] for c in r] for r in rows]
    tiles.append(planar_tile(arrow))
    assert len(tiles) <= 64, len(tiles)
    return tiles


HUD = hud_tiles()
T_BG = HUD_BASE
T_FONT = HUD_BASE + 1
T_FRAME = HUD_BASE + 1 + len(FONTCHARS)
T_ARROW = T_FRAME + 8

VIEW_TX, VIEW_TY = 8, 3          # view position on screen in tiles (16x12 tiles)


# ----------------------------------------------------------------------------- logos
def logo_overlay(lines):
    """lines: [(text, top_y)] -> runs (x, y, len, colour) over the 64x48 view.
    5x7 font, letters doubled vertically, gradient fill, black outline, shadow."""
    W_, H_ = 64, 48
    fill = [[None] * W_ for _ in range(H_)]
    for text, top in lines:
        width = len(text) * 6 - 1
        x0 = (W_ - width) // 2
        for ci, ch in enumerate(text):
            if ch == ' ':
                continue
            for gy, row in enumerate(FONT[ch]):
                for gx, bit in enumerate(row):
                    if bit != '1':
                        continue
                    for dy in range(2):
                        y = top + gy * 2 + dy
                        x = x0 + ci * 6 + gx
                        t = (gy * 2 + dy) / 13.0
                        fill[y][x] = CREAM if t < 0.3 else TAN if t < 0.65 else BROWN
    out = [[None] * W_ for _ in range(H_)]
    for y in range(H_):                       # shadow (down-right), then outline
        for x in range(W_):
            if fill[y][x] is not None:
                for dx, dy in ((1, 1), (2, 2)):
                    if 0 <= x + dx < W_ and 0 <= y + dy < H_:
                        out[y + dy][x + dx] = DRED
    for y in range(H_):
        for x in range(W_):
            if fill[y][x] is not None:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if 0 <= x + dx < W_ and 0 <= y + dy < H_ and fill[y + dy][x + dx] is None:
                            out[y + dy][x + dx] = BLACK
    for y in range(H_):
        for x in range(W_):
            if fill[y][x] is not None:
                out[y][x] = fill[y][x]
    runs = []
    for y in range(H_):
        x = 0
        while x < W_:
            c = out[y][x]
            if c is None:
                x += 1
                continue
            n = 1
            while x + n < W_ and out[y][x + n] == c:
                n += 1
            runs += [x, y, n, c]
            x += n
    return runs + [0xFF]


LOGO = logo_overlay([("SMS", 3), ("DUNGEON", 20)])
THE_END = logo_overlay([("THE END", 16)])
LOGO_OFF, END_OFF, MAPS_OFF = 0x0000, 0x1000, 0x2000     # data bank layout
assert len(LOGO) <= END_OFF and len(THE_END) <= 0x1000

# ----------------------------------------------------------------------------- emit
def c_array(name, data, typ="unsigned char", per=16):
    s = f"const {typ} {name}[{len(data)}] = {{\n"
    for i in range(0, len(data), per):
        s += "  " + ",".join(f"0x{v:02X}" if typ == "unsigned char" else f"0x{v:04X}" for v in data[i:i + per]) + ",\n"
    return s + "};\n"


def c_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def c_strings(name, items):
    return f"const char * const {name}[{len(items)}] = {{\n" + "".join(f"  {c_str(t)},\n" for t in items) + "};\n"


def report():
    print(f"content: {len(C.LEVELS)} levels, {len(THEME_NAMES)} texture sets, {NMON} monsters, "
          f"{len(C.PROPS)} props, {len(C.WEAPONS)} weapons, {len(C.ARMORS)} armours, {len(CONS)} consumables")
    print(f"         {NEV} events ({len(EV_SCRIPT)} script bytes), {len(MESSAGES)} messages, {NOBJ} objects, "
          f"{len(SPRITES)} sprite frames in {NSPRBANK} banks, ROM {NBANKS} banks")


def emit_tables():
    """gen.h + gen.c: the game's content tables (gen.c lives in ROM bank 1)"""
    H = []
    H.append(f"#define TITLE_X {16 - (len(C.TEXT['title']) + 1) // 2}\n#define TAGLINE_X {16 - (len(C.TEXT['tagline']) + 1) // 2}")
    H.append(f"#define NLEVELS {len(C.LEVELS)}\n#define NOBJ {NOBJ}\n#define NEV {NEV}\n#define NKINDS {len(KINDS)}\n#define NMON {NMON}")
    H.append(f"#define START_L {START[0]}\n#define START_X {START[1]}\n#define START_Y {START[2]}\n#define START_F {START[3]}")
    for k, v in OBJKIND.items():
        H.append(f"#define OBJ_{k} {v}")
    H.append(f"#define KF_MONSTER {KF_MONSTER}\n#define KF_BLOCKS {KF_BLOCKS}\n#define KF_BOSS {KF_BOSS}\n#define KF_SHOP {KF_SHOP}")
    for k, v in OPS.items():
        H.append(f"#define OP_{k} {v}")
    H.append(f"#define M_DOOR {DOOR_B}\n#define M_LOCKED {LOCKED_B}\n#define M_STAIRS {STAIRS_B}\n#define M_SECRET {SECRET_B}")
    H.append(f"#define NWEAPONS {len(C.WEAPONS)}\n#define NARMORS {len(C.ARMORS)}\n#define NCONS {len(CONS)}")
    for i, k in enumerate(CONS):
        H.append(f"#define ITEM_{k} {i}")
    P = C.PLAYER
    H.append(f"#define PL_HP {P['hp']}\n#define PL_MP {P['mp']}\n#define PL_ATK {P['atk']}\n#define PL_DEF {P['df']}\n#define PL_KEYS {P['keys']}")
    g = P["per_level"]
    H.append(f"#define LV_HP {g['hp']}\n#define LV_MP {g['mp']}\n#define LV_ATK {g['atk']}\n#define LV_DEF {g['df']}")
    H.append(f"#define MAX_LEVEL {len(P['next_xp']) + 1}")
    H.append(f"#define HEAL_MP {P['heal']['mp']}\n#define HEAL_BASE {P['heal']['base']}\n#define HEAL_LV {P['heal']['per_level']}")
    H.append(f'#define HEAL_LABEL "HEAL {P["heal"]["mp"]}MP"\n#define FIRE_LABEL "FIRE {P["fire"]["mp"]}MP"')
    H.append(f"#define LOOT_ITEM {CONS.index(C.LOOT['item'])}\n#define LOOT_ONE_IN {C.LOOT['one_in']}")
    H.append(f"#define FIRE_MP {P['fire']['mp']}\n#define FIRE_BASE {P['fire']['base']}\n#define FIRE_LV {P['fire']['per_level']}")
    for nm in ("TITLE", "BATTLE", "BOSS", "VICTORY", "GAMEOVER", "ENDING"):
        H.append(f"#define SONG_{nm} {SONG_NAMES.index(nm)}")
    H.append("""typedef struct {
    const char *name, *plural, *group, *attack, *death, *spell;
    unsigned char hp, atk, def, xp, gold, frame, cls, flags, run;
    unsigned char sp_every, sp_dmg, sp_rnd, sp_armor;   /* armour divisor, 0 = ignored */
} MonDef;
#define MON(kind) (&mon_tab[(kind) - 1])
extern const MonDef mon_tab[NMON];
extern const unsigned char kind_flags[NKINDS + 1], kind_cls[NKINDS + 1], kind_frame[NKINDS + 1], kind_bump[NKINDS + 1];
#define MAP_DATA (0x8000 + 0x2000)        /* level maps, 256 bytes each, in DATA_BANK */
extern const unsigned char ev_start[NLEVELS + 1], ev_x[NEV], ev_y[NEV], ev_once[NEV];
extern const unsigned int ev_code[NEV];
extern const unsigned char ev_script[];
extern const char * const messages[];
extern const char * const level_name[NLEVELS];
extern const unsigned char level_music[NLEVELS], level_theme[NLEVELS], level_open[NLEVELS];
extern const unsigned char theme_kinds[];             /* 128 per theme: cell kinds for render.c */
extern const unsigned char theme_bank[];              /* 3 per theme: floor, walls, doors      */
extern const unsigned char theme_mapcol[];            /* 32 per theme: automap colour per map byte */
extern const unsigned char obj_init[NOBJ * 5];
extern const char * const weapon_name[NWEAPONS];
extern const char * const armor_name[NARMORS];
extern const unsigned char weapon_atk[NWEAPONS], armor_def[NARMORS];
extern const unsigned int weapon_cost[NWEAPONS], armor_cost[NARMORS];
extern const char * const cons_name[NCONS];
extern const char * const cons_hud[NCONS];
extern const char * const cons_use[NCONS];
extern const unsigned char cons_hp[NCONS], cons_mp[NCONS], cons_sfx[NCONS], cons_start[NCONS];
extern const unsigned int cons_cost[NCONS];
extern const unsigned char shop_wmax[NLEVELS], shop_amax[NLEVELS], shop_goods[NLEVELS], shop_inn[NLEVELS];
extern const unsigned int next_xp[MAX_LEVEL];
extern const char * const text_intro;
extern const char * const text_title, * const text_tagline, * const text_map;
extern const char * const text_ending[3];""")
    S_ = []
    rows = []
    for k, md in C.MONSTERS.items():
        sp = md.get("spell") or dict(every=0, dmg=0, rnd=0, armor="full", text="")
        fl = KF_MONSTER | KF_BLOCKS | (KF_BOSS if md.get("boss") else 0) | (16 if md.get("fire_weak") else 0)
        rows.append("  { " + ", ".join(c_str(t) for t in (md["name"], md["plural"], md["group"], md["attack"],
                                                             md["death"], sp["text"])) +
                    ", " + ", ".join(str(v) for v in (md["hp"], md["atk"], md["df"], md["xp"], md["gold"],
                                                      KIND_FRAME[k], KIND_CLS[k], fl, md["run"], sp["every"],
                                                      sp["dmg"], sp["rnd"], ARMOR_DIV[sp["armor"]])) + " }")
    S_.append("const MonDef mon_tab[NMON] = {\n" + ",\n".join(rows) + "\n};\n")
    fl, cl, fr, bu = [0], [0], [0], [0xFF]
    for k in KINDS:
        if k in C.MONSTERS:
            md = C.MONSTERS[k]
            fl.append(KF_MONSTER | KF_BLOCKS | (KF_BOSS if md.get("boss") else 0))
            bu.append(0xFF)
        else:
            p = C.PROPS[k]
            fl.append((KF_BLOCKS if p.get("blocks") else 0) | (KF_SHOP if p.get("shop") else 0))
            bu.append(MESSAGES.index(p["bump"]) if p.get("bump") else 0xFF)
        cl.append(KIND_CLS[k])
        fr.append(KIND_FRAME[k])
    S_ += [c_array("kind_flags", fl), c_array("kind_cls", cl), c_array("kind_frame", fr), c_array("kind_bump", bu)]
    S_.append(c_array("ev_start", EV_START))
    S_.append(c_array("ev_x", [r[0] for r in EV_ROWS]) + c_array("ev_y", [r[1] for r in EV_ROWS]) +
              c_array("ev_once", [r[2] for r in EV_ROWS]) + c_array("ev_code", [r[3] for r in EV_ROWS], "unsigned int"))
    S_.append(c_array("ev_script", EV_SCRIPT))
    S_.append(c_strings("messages", MESSAGES))
    S_.append(c_strings("level_name", [L["name"] for L in C.LEVELS]))
    S_.append(c_array("level_music", [SONG_NAMES.index(L["music"]) for L in C.LEVELS]))
    S_.append(c_array("level_theme", [THEME_NAMES.index(L["theme"]) for L in C.LEVELS]))
    S_.append(c_array("level_open", [THEME[L["theme"]]["open"] for L in C.LEVELS]))
    S_.append(c_array("theme_kinds", [b for tn in THEME_NAMES for b in THEME[tn]["kinds"]]))
    S_.append(c_array("theme_mapcol", [b for tn in THEME_NAMES for b in THEME[tn]["mapcol"]]))
    S_.append(c_array("theme_bank", [THEMEBANK[tn] + i for tn in THEME_NAMES for i in range(3)]))
    objs = []
    for li, L in enumerate(C.LEVELS):
        for k, x, y, n in L.get("objects", []):
            objs += [OBJKIND[k], li, x, y, n]
    S_.append(c_array("obj_init", objs))
    S_.append(c_strings("weapon_name", [w[0] for w in C.WEAPONS]) + c_strings("armor_name", [a[0] for a in C.ARMORS]))
    S_.append(c_array("weapon_atk", [w[1] for w in C.WEAPONS]) + c_array("armor_def", [a[1] for a in C.ARMORS]))
    S_.append(c_array("weapon_cost", [w[2] for w in C.WEAPONS], "unsigned int") +
              c_array("armor_cost", [a[2] for a in C.ARMORS], "unsigned int"))
    CV = [C.CONSUMABLES[k] for k in CONS]
    S_.append(c_strings("cons_name", CONS) + c_strings("cons_hud", [c["hud"] for c in CV]) +
              c_strings("cons_use", [c["use"] for c in CV]))
    S_.append(c_array("cons_hp", [c["hp"] for c in CV]) + c_array("cons_mp", [c["mp"] for c in CV]) +
              c_array("cons_sfx", [SOUNDS[c["sound"]] for c in CV]) + c_array("cons_start", [c["start"] for c in CV]) +
              c_array("cons_cost", [c["price"] for c in CV], "unsigned int"))
    sh = [L.get("shop") or dict(weapons=0, armors=0, goods=[], inn=0) for L in C.LEVELS]
    S_.append(c_array("shop_wmax", [x["weapons"] for x in sh]) + c_array("shop_amax", [x["armors"] for x in sh]) +
              c_array("shop_goods", [sum(1 << CONS.index(g) for g in x["goods"]) for x in sh]) +
              c_array("shop_inn", [x["inn"] for x in sh]))
    S_.append(c_array("next_xp", C.PLAYER["next_xp"] + [0], "unsigned int"))
    S_.append(f"const char * const text_intro = {c_str(C.TEXT['intro'])};\n")
    S_.append(f"const char * const text_title = {c_str(C.TEXT['title'])};\n")
    S_.append(f"const char * const text_tagline = {c_str(C.TEXT['tagline'])};\n")
    S_.append(f"const char * const text_map = {c_str(MAP_HELP)};\n")
    S_.append(c_strings("text_ending", C.TEXT["ending"]))
    return "\n".join(H) + "\n", "\n".join(S_)


def write_meta():
    """what tools/simrender.py and the tests need to know about this build"""
    import json
    meta = dict(levels=[dict(id=L["id"], name=L["name"], banks=[THEMEBANK[L["theme"]] + i for i in range(3)],
                             kinds=THEME[L["theme"]]["kinds"]) for L in C.LEVELS],
                kinds={k: dict(id=OBJKIND[k], cls=KIND_CLS[k], frame=KIND_FRAME[k]) for k in KINDS},
                maps=[list(lb) for lb in LEVEL_BYTES], spr_bank=SPRBANK, pose_bank0=POSEBANK0, messages=MESSAGES,
                objects=[(k, li, x, y, n) for li, L in enumerate(C.LEVELS) for k, x, y, n in L.get("objects", [])])
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)


def main():
    report()
    if CHECK_ONLY:
        print("content OK")
        return
    os.makedirs(OUT, exist_ok=True)
    banks = {}
    for tn in THEME_NAMES:
        T = THEME[tn]
        banks[THEMEBANK[tn]] = build_floor_bank(T)
        banks[THEMEBANK[tn] + 1] = build_wall_bank(T["wall_a"])
        banks[THEMEBANK[tn] + 2] = build_wall_bank(T["wall_b"])
    for i in range(NSPRBANK):
        banks[SPRBANK + i] = build_sprite_bank(i * 8)
    db = bytearray(BANK)                      # misc data bank (mapped into slot 2 on demand)
    db[LOGO_OFF:LOGO_OFF + len(LOGO)] = bytes(LOGO)
    db[END_OFF:END_OFF + len(THE_END)] = bytes(THE_END)
    maps = bytes(b for lb in LEVEL_BYTES for b in lb)
    db[MAPS_OFF:MAPS_OFF + len(maps)] = maps
    banks[DATABANK] = db
    PL = poses()
    stats = []
    for i, ps in enumerate(PL):
        bb, used, nc = build_pose_bank(ps)
        banks[POSEBANK0 + i] = bb
        stats.append((i, used, nc))
    for fn in os.listdir(OUT):                # drop banks of an older layout
        if fn.startswith("bank") and fn.endswith(".bin"):
            os.remove(os.path.join(OUT, fn))
    for k, v in banks.items():
        with open(os.path.join(OUT, f"bank{k:02d}.bin"), "wb") as f:
            f.write(v)

    # name tables for the two view buffers (row-major, 12 rows x 16 entries x 2 bytes)
    nt = []
    for buf in range(2):
        for ty in range(12):
            for tx in range(16):
                t = buf * 192 + tx * 12 + ty
                nt += [t & 255, (t >> 8) & 1]
    pal = [(r | (g << 2) | (b << 4)) for (r, g, b) in PAL]
    hudbytes = bytearray()
    for t in HUD:
        hudbytes += t
    th, tc = emit_tables()

    with open(os.path.join(OUT, "gen.h"), "w") as f:
        f.write("/* generated by tools/gen.py from tools/content.py - do not edit */\n#ifndef GEN_H\n#define GEN_H\n")
        f.write(f"#define VIEW_W {W}\n#define VIEW_H {H}\n#define SUBSTEPS {S}\n#define NPOSE {NPOSE}\n")
        f.write(f"#define POSE_BANK0 {POSEBANK0}\n#define ROM_BANKS {NBANKS}\n#define POSE_HDR (0x8000+0x{POSE_HDR:04X})\n")
        f.write(f"#define Q_FOG {Q_FOG}\n#define FLOOR_ROWS {FLOOR_ROWS}\n")
        f.write(f"#define T_BG {T_BG}\n#define T_FONT {T_FONT}\n#define T_FRAME {T_FRAME}\n#define T_ARROW {T_ARROW}\n#define HUD_TILES {len(HUD)}\n")
        f.write(f"#define VIEW_TX {VIEW_TX}\n#define VIEW_TY {VIEW_TY}\n")
        f.write(f"#define SPR_BANK {SPRBANK}\n#define SCALE_TAB (0x8000+0x{SCALE_OFF:04X})\n")
        f.write(f"#define BB_TABLE (0x8000+0x{BB_OFF:04X})\n#define BB_DA0 ({BB_DA0})\n#define BB_DA1 {BB_DA1}\n")
        f.write(f"#define BB_DB0 ({BB_DB0})\n#define BB_DB1 {BB_DB1}\n#define BB_NA {BB_NA}\n")
        f.write(f'#define FONTCHARS "{FONTCHARS}"\n')
        f.write("extern const unsigned char pal_bg[16];\nextern const unsigned char hud_tiles[];\n")
        f.write("extern const unsigned char view_nt[768];\n")
        f.write("extern const unsigned char glyph_tab[96];\n")
        f.write(f"#define DATA_BANK {DATABANK}\n#define LOGO_RLE (0x8000+0x{LOGO_OFF:04X})\n#define THE_END_RLE (0x8000+0x{END_OFF:04X})\n")
        f.write(th)
        f.write("#endif\n")
    with open(os.path.join(OUT, "gen_nt.c"), "w") as f:     # bank 0: read by the VBlank flip
        f.write('/* generated by tools/gen.py - do not edit */\n#include "gen.h"\n')
        f.write(c_array("view_nt", nt))
    with open(os.path.join(OUT, "gen.c"), "w") as f:
        f.write('/* generated by tools/gen.py from tools/content.py - do not edit */\n#include "gen.h"\n')
        f.write(c_array("pal_bg", pal))
        f.write(c_array("hud_tiles", list(hudbytes)))
        gt = [0] * 96                                    # ASCII 32..127 -> font tile
        for i, ch in enumerate(FONTCHARS):
            gt[ord(ch) - 32] = i
        f.write(c_array("glyph_tab", gt))
        f.write(tc)
    write_meta()

    print("poses:", " ".join(f"{i}:{u}/{n}c" for i, u, n in stats))
    print("q_fog", Q_FOG, "w_fog", W_FOG, "floor rows", FLOOR_ROWS, "banks", NBANKS, "hud tiles", len(HUD))
    contact_sheet()


def contact_sheet():
    """gen/textures.png: every texture set and sprite, for a quick look"""
    from PIL import Image
    def rgb(c):
        r, g, b = PAL[c]
        return (r * 85, g * 85, b * 85)
    def paste(img, t, x0, y0):
        for yy in range(len(t)):
            for xx in range(len(t[0])):
                if int(t[yy][xx]) != TRANSP:
                    img.putpixel((x0 + xx, y0 + yy), rgb(int(t[yy][xx])))
    rows = len(THEME_NAMES) + (len(SPRITES) + 11) // 12
    img = Image.new("RGB", (34 * 13, 36 * rows), (255, 0, 255))
    for r, tn in enumerate(THEME_NAMES):
        T = THEME[tn]
        x = 0
        for t in T["wall_a"] + T["wall_b"]:
            paste(img, t, x, r * 36); x += 34
        for t in T["flats"]:
            paste(img, t, x, r * 36); x += 18
        paste(img, T["sky"], x, r * 36)
    for i, t in enumerate(SPRITES):
        paste(img, t, (i % 12) * 34, (len(THEME_NAMES) + i // 12) * 36)
    img.resize((img.width * 3, img.height * 3), Image.NEAREST).save(os.path.join(OUT, "textures.png"))


if __name__ == "__main__":
    main()
