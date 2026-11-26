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

OUT = sys.argv[1] if len(sys.argv) > 1 else "gen"
os.makedirs(OUT, exist_ok=True)

W, H, HALF = 64, 48, 24          # logical view (each logical pixel = 2x2 screen pixels)
FOCAL = 32.0                     # logical px per unit at distance 1 (90 deg FOV)
S = 6                            # sub-steps per move / turn
MAXD = 12.0                      # view distance (fog beyond)
NPOSE = 1 + 3 * (S - 1) + 6      # + quarter-step poses for "quick" mode

# ----------------------------------------------------------------------------- palette
PAL = [
    (0, 0, 0), (1, 1, 1), (2, 2, 2), (3, 3, 3),
    (1, 0, 0), (2, 1, 0), (3, 2, 1), (0, 1, 0),
    (1, 2, 0), (2, 3, 1), (0, 0, 1), (0, 1, 2),
    (1, 2, 3), (2, 3, 3), (2, 2, 1), (3, 3, 2),
]
BLACK, DGRAY, GRAY, WHITE, DRED, BROWN, TAN, DGREEN, GREEN, LGREEN, NAVY, BLUE, SKY, PSKY, KHAKI, CREAM = range(16)


# shaded (east/west) faces use these darker colours
DARK = [BLACK, BLACK, DGRAY, GRAY, BLACK, DRED, BROWN, BLACK,
        DGREEN, GREEN, BLACK, NAVY, BLUE, SKY, DGRAY, KHAKI]
rng = random.Random(1234)


def noise2(w, h, scale, seed, wrapx=True):
    """tileable value noise in [0,1)"""
    r = np.random.RandomState(seed)
    gw, gh = max(1, int(w / scale)), max(1, int(h / scale))
    g = r.rand(gh + 1, gw + 1)
    if wrapx:
        g[:, gw] = g[:, 0]
    g[gh, :] = g[0, :]
    out = np.zeros((h, w))
    for y in range(h):
        for x in range(w):
            fx, fy = x / w * gw, y / h * gh
            ix, iy = int(fx), int(fy)
            tx, ty = fx - ix, fy - iy
            tx = tx * tx * (3 - 2 * tx)
            ty = ty * ty * (3 - 2 * ty)
            a = g[iy, ix] * (1 - tx) + g[iy, ix + 1] * tx
            b = g[iy + 1, ix] * (1 - tx) + g[iy + 1, ix + 1] * tx
            out[y, x] = a * (1 - ty) + b * ty
    return out


BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0


def pick(levels, v, x, y):
    """ordered-dithered choice from a list of colours by value v in [0,1]"""
    v = min(max(v, 0.0), 0.999) * (len(levels) - 1)
    i = int(v)
    f = v - i
    if f > BAYER4[y & 3][x & 3] and i + 1 < len(levels):
        i += 1
    return levels[i]


# ----------------------------------------------------------------------------- textures
# A texture is an array [y][x] of palette indices.
def tex_bricks(colors, mortar, seed, moss=None):
    n = noise2(32, 32, 6, seed)
    n2 = noise2(32, 32, 3, seed + 7)
    t = np.zeros((32, 32), dtype=int)
    for y in range(32):
        row = y // 8
        for x in range(32):
            xo = (x + (8 if row & 1 else 0)) % 32
            edge = (y % 8 == 7) or (xo % 16 == 15)
            if edge:
                t[y, x] = mortar
            else:
                v = 0.25 + 0.6 * n2[y, x] + 0.15 * ((xo // 16 + row) % 2)
                if y % 8 == 0 or xo % 16 == 0:
                    v += 0.25            # lit top/left edge of each brick
                if y % 8 == 6 or xo % 16 == 14:
                    v -= 0.25
                t[y, x] = pick(colors, v, x, y)
            if moss and n[y, x] > 0.58:
                t[y, x] = pick(moss, (n[y, x] - 0.58) * 2.4 + n2[y, x] * 0.3, x, y)
    return t


def tex_planks():
    n = noise2(32, 32, 4, 99)
    t = np.zeros((32, 32), dtype=int)
    for y in range(32):
        for x in range(32):
            p = x // 8
            if x % 8 == 7:
                t[y, x] = DRED
                continue
            grain = math.sin((y + p * 13) * 0.9 + n[y, x] * 6) * 0.5 + 0.5
            v = 0.2 + 0.5 * grain + 0.2 * (p % 2)
            if x % 8 == 0:
                v += 0.25
            t[y, x] = pick([DRED, BROWN, TAN], v, x, y)
            if (y == 4 or y == 27) and x % 8 == 3:
                t[y, x] = DGRAY          # nails
    return t


def tex_hedge():
    n = noise2(32, 32, 3, 55)
    n2 = noise2(32, 32, 8, 56)
    t = np.zeros((32, 32), dtype=int)
    for y in range(32):
        for x in range(32):
            v = n[y, x] * 0.8 + n2[y, x] * 0.4 - 0.1
            t[y, x] = pick([BLACK, DGREEN, GREEN, LGREEN], v, x, y)
            if rng.random() < 0.012:
                t[y, x] = CREAM          # tiny flowers
    return t


def tex_flag(seed):
    n = noise2(16, 16, 4, seed)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            if x % 8 == 7 or y % 8 == 7:
                t[y, x] = DGRAY
            else:
                v = 0.3 + n[y, x] * 0.7 + 0.12 * (((x // 8) + (y // 8)) % 2)
                if x % 8 == 0 or y % 8 == 0:
                    v += 0.2
                t[y, x] = pick([DGRAY, GRAY, KHAKI, GRAY], v, x, y)
    return t


def tex_grass():
    n = noise2(16, 16, 3, 77)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            t[y, x] = pick([DGREEN, GREEN, GREEN, LGREEN], n[y, x], x, y)
    t[3][4] = CREAM
    t[11][12] = CREAM
    return t


def tex_boards():
    n = noise2(16, 16, 4, 31)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            if y % 4 == 3 or (x == ((y // 4) * 5) % 16):
                t[y, x] = DRED
            else:
                t[y, x] = pick([BROWN, TAN], n[y, x] * 0.9 + 0.1 * (y % 4 == 0), x, y)
    return t


def tex_beams():
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            if x in (0, 1, 8, 9):
                t[y, x] = BROWN if x in (0, 8) else DRED
            elif y in (0, 1):
                t[y, x] = TAN if y == 0 else BROWN
            else:
                t[y, x] = DGRAY if (x + y) % 5 else BLACK
    return t


def tex_ceilstone():
    n = noise2(16, 16, 4, 11)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            if x % 16 == 15 or y % 8 == 7 or (x == 7 and y < 8) or (x == 3 and y >= 8):
                t[y, x] = BLACK
            else:
                t[y, x] = pick([BLACK, DGRAY, GRAY], 0.35 + n[y, x] * 0.5, x, y)
    return t


def tex_sky():
    """64 wide (one 90 degree period, tileable), 24 rows down to the horizon"""
    n = noise2(64, 24, 8, 4242)
    n2 = noise2(64, 24, 4, 4243)
    t = np.zeros((24, 64), dtype=int)
    for y in range(24):
        for x in range(64):
            g = y / 23.0
            v = g * 1.05
            c = pick([NAVY, BLUE, SKY, PSKY], v, x, y)
            cl = n[y, x] * 0.7 + n2[y, x] * 0.4 - (0.62 - 0.25 * abs(y - 9) / 12.0)
            if cl > 0.18:
                c = pick([SKY, PSKY, CREAM, WHITE], (cl - 0.18) * 2.2, x, y)
            if y >= 21:             # distant hills near the horizon
                hh = 21 + 2.5 * (math.sin(x * 2 * math.pi / 64 * 2) * 0.5 + 0.5)
                if y >= hh:
                    c = DGREEN if y >= 23 or (x + y) & 1 else GREEN
            t[y, x] = c
    return t


WALLS = [
    tex_bricks([DGRAY, GRAY, GRAY, GRAY, WHITE], BLACK, 1),                      # 0 grey stone
    tex_bricks([DGRAY, KHAKI, GRAY], BLACK, 2, moss=[DGREEN, GREEN, LGREEN]),  # 1 mossy stone
    tex_planks(),                                                         # 2 wood
    tex_hedge(),                                                          # 3 hedge
]
FLATS = [tex_flag(5), tex_grass(), tex_boards(), tex_beams(), tex_ceilstone()]
FLOOR_TEX = {0: 0, 1: 1, 2: 2}       # floor type -> flat texture
CEIL_TEX = {1: 3, 2: 4}              # ceil type -> flat texture (0 = sky)
SKY = tex_sky()

# ----------------------------------------------------------------------------- map
# '#' grey stone  'M' mossy  'W' wood wall  'H' hedge
# floor/ceiling for open cells:
#   '.' flagstone / stone ceiling   ',' grass / sky   ':' flagstone / sky
#   '=' wooden boards / wooden beams  '-' flagstone / wooden beams
MAP = [
    "################",
    "#.....#=====W..#",
    "#.###.#=WW==W..#",
    "#.#.#.#=W====..#",
    "#.#...--=W=WW..#",
    "#.####.#=W=....#",
    "#......M,,,,MWW#",
    "###.MM,,,,,,,MW#",
    "#...H,,HH,,,,H.#",
    "#.#.M,,,,::,,M.#",
    "#.#.MM,,,::,MM.#",
    "#.#..........#.#",
    "#.###.###.####.#",
    "#...#...#....#.#",
    "#.#...#...##...#",
    "################",
]
START = (1, 1, 2)  # x, y, facing (south)
assert len(MAP) == 16 and all(len(r) == 16 for r in MAP), "map must be 16x16"

WALLCH = {'#': 0, 'M': 1, 'W': 2, 'H': 3}
OPENCH = {'.': (0, 2), ',': (1, 0), ':': (0, 0), '=': (2, 1), '-': (0, 1)}


def map_bytes():
    out = []
    for y in range(16):
        for x in range(16):
            ch = MAP[y][x]
            if ch in WALLCH:
                out.append(16 + WALLCH[ch])
            else:
                f, c = OPENCH[ch]
                out.append(f | (c << 2))
    return out


def validate_map():
    m = MAP
    for i in range(16):
        assert m[0][i] in WALLCH and m[15][i] in WALLCH and m[i][0] in WALLCH and m[i][15] in WALLCH
    sx, sy, _ = START
    assert m[sy][sx] not in WALLCH
    seen = {(sx, sy)}
    st = [(sx, sy)]
    while st:
        x, y = st.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if m[ny][nx] not in WALLCH and (nx, ny) not in seen:
                seen.add((nx, ny))
                st.append((nx, ny))
    opens = sum(1 for y in range(16) for x in range(16) if m[y][x] not in WALLCH)
    assert len(seen) == opens, f"unreachable open cells: {opens - len(seen)}"


validate_map()

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
FLOORBANK, WALLBANK, POSEBANK0 = 2, 3, 4


def build_floor_bank():
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
                c = int(SKY[row][col])
                b[0x800 + par * 1536 + col * 24 + row] = (c << 4) if par == 0 else c
    # flats: page 0x14 + (t*4+f)*2 + parity
    for ti, tex in enumerate(FLATS):
        for f in range(4):
            for par in range(2):
                pg = 0x14 + (ti * 4 + f) * 2 + par
                assert pg < 0x40
                b[pg * 256:(pg + 1) * 256] = flat_page(tex, f, par)
    return b


def build_wall_bank():
    b = bytearray(BANK)
    for t, tex in enumerate(WALLS):
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
        assert p < BANK - 16, "pose bank overflow"
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
    assert len(tiles) <= 64, len(tiles)
    return tiles


HUD = hud_tiles()
T_BG = HUD_BASE
T_FONT = HUD_BASE + 1
T_FRAME = HUD_BASE + 1 + len(FONTCHARS)

VIEW_TX, VIEW_TY = 8, 3          # view position on screen in tiles (16x12 tiles)


# ----------------------------------------------------------------------------- emit
def c_array(name, data, typ="unsigned char", per=16):
    s = f"const {typ} {name}[{len(data)}] = {{\n"
    for i in range(0, len(data), per):
        s += "  " + ",".join(f"0x{v:02X}" if typ == "unsigned char" else f"0x{v:04X}" for v in data[i:i + per]) + ",\n"
    return s + "};\n"


def main():
    banks = {}
    banks[FLOORBANK] = build_floor_bank()
    banks[WALLBANK] = build_wall_bank()
    PL = poses()
    stats = []
    for i, ps in enumerate(PL):
        bb, used, nc = build_pose_bank(ps)
        banks[POSEBANK0 + i] = bb
        stats.append((i, used, nc))
    for k, v in banks.items():
        with open(os.path.join(OUT, f"bank{k:02d}.bin"), "wb") as f:
            f.write(v)
    nbanks = max(banks) + 1

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

    with open(os.path.join(OUT, "gen.h"), "w") as f:
        f.write("/* generated by tools/gen.py - do not edit */\n#ifndef GEN_H\n#define GEN_H\n")
        f.write(f"#define VIEW_W {W}\n#define VIEW_H {H}\n#define SUBSTEPS {S}\n#define NPOSE {NPOSE}\n")
        f.write(f"#define FLOOR_BANK {FLOORBANK}\n#define WALL_BANK {WALLBANK}\n#define POSE_BANK0 {POSEBANK0}\n")
        f.write(f"#define ROM_BANKS {nbanks}\n#define POSE_HDR (0x8000+0x{POSE_HDR:04X})\n")
        f.write(f"#define Q_FOG {Q_FOG}\n#define FLOOR_ROWS {FLOOR_ROWS}\n")
        f.write(f"#define T_BG {T_BG}\n#define T_FONT {T_FONT}\n#define T_FRAME {T_FRAME}\n#define HUD_TILES {len(HUD)}\n")
        f.write(f"#define VIEW_TX {VIEW_TX}\n#define VIEW_TY {VIEW_TY}\n")
        f.write(f"#define START_X {START[0]}\n#define START_Y {START[1]}\n#define START_F {START[2]}\n")
        f.write(f'#define FONTCHARS "{FONTCHARS}"\n')
        f.write("extern const unsigned char pal_bg[16];\nextern const unsigned char hud_tiles[];\n")
        f.write("extern const unsigned char map_init[256];\nextern const unsigned char view_nt[768];\n")
        f.write("extern const unsigned char cell_kind[128];\n")
        f.write("#endif\n")
    with open(os.path.join(OUT, "gen.c"), "w") as f:
        f.write('/* generated by tools/gen.py - do not edit */\n#include "gen.h"\n')
        f.write(c_array("pal_bg", pal))
        f.write(c_array("hud_tiles", list(hudbytes)))
        f.write(c_array("map_init", map_bytes()))
        f.write(c_array("view_nt", nt))
        # floor type (0..2) -> page base (facing 0, parity 0); ceil type 1..2 -> 3+ ; 0 = sky
        # per map byte m (0..19): wall type+1, floor page, ceiling page (0 = sky)
        xw, xf, xc = [], [], []
        for m in range(32):
            if 16 <= m < 20:
                xw.append(m - 15); xf.append(0x40 + 0x14); xc.append(0x40 + 0x14 + CEIL_TEX[2] * 8)
            elif m < 16:
                ft, ct = m & 3, (m >> 2) & 3
                xw.append(0); xf.append(0x40 + 0x14 + FLOOR_TEX.get(ft, 0) * 8)
                xc.append(0x40 + 0x14 + CEIL_TEX[ct] * 8 if ct in CEIL_TEX else 0)
            else:
                xw.append(1); xf.append(0x54); xc.append(0)
        f.write(c_array("cell_kind", xw + xf + [0] * 32 + xc))
    print("poses:", " ".join(f"{i}:{u}/{n}c" for i, u, n in stats))
    print("q_fog", Q_FOG, "w_fog", W_FOG, "floor rows", FLOOR_ROWS, "banks", nbanks, "hud tiles", len(HUD))
    # preview image of textures
    try:
        from PIL import Image
        def rgb(c):
            r, g, b = PAL[c]
            return (r * 85, g * 85, b * 85)
        img = Image.new("RGB", (32 * 4 + 16 * 5 + 64 + 20, 34))
        x = 0
        for t in WALLS:
            for yy in range(32):
                for xx in range(32):
                    img.putpixel((x + xx, yy), rgb(int(t[yy][xx])))
            x += 34
        for t in FLATS:
            for yy in range(16):
                for xx in range(16):
                    img.putpixel((x + xx, yy), rgb(int(t[yy][xx])))
            x += 18
        for yy in range(24):
            for xx in range(64):
                img.putpixel((min(img.width - 1, x + xx), yy), rgb(int(SKY[yy][xx])))
        img.resize((img.width * 4, img.height * 4), Image.NEAREST).save(os.path.join(OUT, "textures.png"))
    except Exception as e:
        print("preview failed", e)


if __name__ == "__main__":
    main()
