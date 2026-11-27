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
def canvas(fill=0):
    return np.full((32, 32), fill, dtype=int)


def tex_door(locked=False):
    t = canvas()
    n = noise2(32, 32, 4, 17)
    for y in range(32):
        for x in range(32):
            if x < 3 or x > 28 or y < 3:            # stone frame
                v = 0.4 + 0.4 * n[y, x]
                t[y, x] = pick([DGRAY, GRAY], v, x, y) if (x % 3 and y % 4) else DGRAY
                continue
            p = (x - 3) // 6
            grain = math.sin(y * 0.7 + p * 5 + n[y, x] * 5) * 0.5 + 0.5
            c = pick([DRED, BROWN, TAN], 0.2 + 0.55 * grain, x, y)
            if (x - 3) % 6 == 5:
                c = DRED
            if y in (9, 10, 23, 24):                # iron bands
                c = GRAY if y in (9, 23) else DGRAY
                if x % 5 == 0:
                    c = WHITE
            t[y, x] = c
    for y in range(15, 19):                          # ring handle
        t[y][22] = t[y][25] = GRAY
    t[19][23] = t[19][24] = GRAY
    t[14][23] = t[14][24] = DGRAY
    if locked:
        for y in range(13, 21):
            for x in range(10, 17):
                t[y][x] = CREAM if (x in (10, 16) or y in (13, 20)) else TAN
        t[15][13] = t[16][13] = t[17][13] = BLACK
        t[16][12] = t[16][14] = BLACK
    return t


def tex_stairs():
    t = tex_bricks([DGRAY, GRAY, GRAY], BLACK, 3)
    for y in range(5, 32):
        for x in range(6, 26):
            # an arch opening with steps going down into the dark
            if y < 9 and (x - 15.5) ** 2 + (y - 9) ** 2 * 2.2 > 100:
                continue
            step = (31 - y) // 4
            shade = [GRAY, DGRAY, DGRAY, BLACK, BLACK, BLACK, BLACK, BLACK][min(step, 7)]
            if (31 - y) % 4 == 0 and step < 4:
                shade = WHITE if step == 0 else GRAY
            t[y, x] = shade
    for y in range(5, 32):
        for x in (5, 26):
            t[y, x] = CREAM if y % 2 else KHAKI
    return t


TRANSP = 255


def spr_skeleton(pose):
    """32x32, TRANSP = transparent.  pose: 0 idle, 1 attack"""
    from PIL import Image, ImageDraw
    im = Image.new("L", (32, 32), TRANSP)
    d = ImageDraw.Draw(im)
    bone, dark = CREAM, KHAKI
    # legs + feet
    d.line([(14, 21), (13, 26), (13, 30)], fill=bone, width=2)
    d.line([(18, 21), (19, 26), (19, 30)], fill=bone, width=2)
    d.line([(11, 31), (14, 31)], fill=dark)
    d.line([(18, 31), (21, 31)], fill=dark)
    d.point([(13, 26), (19, 26)], fill=WHITE)
    # pelvis
    d.rectangle([12, 19, 20, 21], fill=dark)
    d.point([(14, 20), (18, 20)], fill=BLACK)
    # spine + ribs
    d.line([(16, 10), (16, 19)], fill=dark, width=1)
    for y in (11, 13, 15):
        d.line([(12, y), (20, y)], fill=bone)
        d.point([(16, y)], fill=dark)
    d.line([(13, 17), (19, 17)], fill=dark)
    # shoulders
    d.line([(10, 10), (22, 10)], fill=bone)
    # left arm with shield
    d.line([(10, 10), (8, 15), (9, 19)], fill=bone, width=2)
    d.ellipse([3, 13, 10, 22], fill=BROWN, outline=DRED)
    d.point([(6, 17)], fill=GRAY)
    if pose == 0:
        d.line([(22, 10), (24, 15), (24, 18)], fill=bone, width=2)
        d.line([(25, 18), (29, 3)], fill=GRAY, width=2)          # sword up-right
        d.line([(26, 17), (29, 4)], fill=WHITE)
        d.line([(23, 18), (27, 19)], fill=TAN)
    else:
        d.line([(22, 10), (25, 6), (26, 3)], fill=bone, width=2)
        d.line([(27, 2), (13, 0)], fill=GRAY, width=2)           # sword raised overhead
        d.line([(27, 1), (12, 0)], fill=WHITE)
        d.line([(25, 0), (27, 4)], fill=TAN)
    # skull
    d.ellipse([12, 1, 20, 9], fill=bone)
    d.rectangle([13, 7, 19, 9], fill=bone)
    eye = DRED if pose == 1 else BLACK
    d.rectangle([13, 4, 14, 5], fill=eye)
    d.rectangle([17, 4, 18, 5], fill=eye)
    d.point([(16, 6)], fill=BLACK)
    for x in (13, 15, 17, 19):
        d.point([(x, 8)], fill=DGRAY)
    d.point([(13, 2), (14, 2)], fill=WHITE)
    return np.array(im, dtype=int)


def spr_hurt(src):
    return np.where(src == TRANSP, TRANSP, WHITE)


def spr_key():
    from PIL import Image, ImageDraw
    im = Image.new("L", (32, 32), TRANSP)
    d = ImageDraw.Draw(im)
    d.ellipse([0, 12, 15, 27], outline=TAN, width=5)
    d.ellipse([2, 14, 13, 25], outline=CREAM, width=1)
    d.rectangle([14, 17, 31, 22], fill=TAN)
    d.line([(14, 17), (31, 17)], fill=CREAM)
    d.rectangle([19, 22, 22, 30], fill=TAN)
    d.rectangle([26, 22, 29, 28], fill=TAN)
    d.line([(15, 22), (31, 22)], fill=BROWN)
    d.point([(4, 13), (16, 18)], fill=WHITE)
    return np.array(im, dtype=int)


def spr_bat(pose):
    from PIL import Image, ImageDraw
    im = Image.new("L", (32, 32), TRANSP)
    d = ImageDraw.Draw(im)
    tip = 4 if pose == 0 else 0
    lw = [(15, 15), (9, 10 + tip), (2, 8 + tip), (4, 15 + tip // 2), (7, 13 + tip // 2), (9, 18), (12, 16)]
    rw = [(31 - x, y) for (x, y) in lw]
    for w in (lw, rw):
        d.polygon(w, fill=BROWN, outline=DRED)
        d.line([w[0], w[2]], fill=TAN)
        d.line([w[0], w[4]], fill=TAN)
        d.line([w[0], w[6]], fill=DRED)
    d.ellipse([12, 11, 19, 21], fill=DRED, outline=BLACK)       # body
    d.ellipse([13, 13, 18, 20], fill=BROWN)
    d.polygon([(12, 12), (13, 8), (14, 12)], fill=DRED)         # ears
    d.polygon([(17, 12), (18, 8), (19, 12)], fill=DRED)
    eye = CREAM if pose == 0 else LGREEN
    d.point([(14, 14), (17, 14)], fill=eye)
    if pose == 1:
        d.point([(14, 18), (17, 18)], fill=WHITE)                 # fangs
        d.point([(15, 17), (16, 17)], fill=DRED)
    return np.array(im, dtype=int)


def spr_ghost(pose):
    from PIL import Image, ImageDraw
    im = Image.new("L", (32, 32), TRANSP)
    d = ImageDraw.Draw(im)
    body = [(8, 12), (9, 6), (13, 2), (19, 2), (23, 6), (24, 12), (26, 22), (27, 29),
            (24, 26), (21, 30), (18, 26), (15, 30), (12, 26), (9, 30), (5, 29), (6, 22)]
    d.polygon(body, fill=PSKY, outline=SKY)
    d.polygon([(10, 14), (22, 14), (24, 24), (8, 24)], fill=WHITE)
    for y in range(4, 28, 3):                                     # wispy shading
        d.point([(10 + (y * 3) % 12, y)], fill=SKY)
    if pose == 0:
        d.line([(8, 14), (3, 20)], fill=PSKY, width=2)
        d.line([(24, 14), (29, 20)], fill=PSKY, width=2)
        d.ellipse([12, 6, 15, 10], fill=BLACK)
        d.ellipse([17, 6, 20, 10], fill=BLACK)
        d.ellipse([14, 12, 18, 15], fill=NAVY)
    else:
        d.line([(8, 12), (1, 6)], fill=PSKY, width=2)              # claws up
        d.line([(24, 12), (31, 6)], fill=PSKY, width=2)
        d.point([(0, 5), (1, 4), (30, 4), (31, 5)], fill=WHITE)
        d.ellipse([12, 6, 15, 10], fill=DRED)
        d.ellipse([17, 6, 20, 10], fill=DRED)
        d.ellipse([13, 12, 19, 18], fill=BLACK)                   # wailing mouth
    return np.array(im, dtype=int)


def spr_chest():
    from PIL import Image, ImageDraw
    im = Image.new("L", (32, 32), TRANSP)
    d = ImageDraw.Draw(im)
    d.rectangle([3, 15, 28, 31], fill=BROWN, outline=DRED)
    d.pieslice([3, 6, 28, 24], 180, 360, fill=TAN, outline=DRED)
    d.rectangle([3, 15, 28, 16], fill=DRED)
    for y in (20, 25):
        d.line([(4, y), (27, y)], fill=DRED)
    for x in (6, 25):
        d.line([(x, 9), (x, 30)], fill=GRAY)
    d.rectangle([13, 14, 18, 20], fill=CREAM, outline=KHAKI)
    d.point([(15, 17), (16, 17), (15, 18)], fill=BLACK)
    d.point([(8, 9), (9, 8)], fill=CREAM)
    return np.array(im, dtype=int)


def spr_merchant():
    from PIL import Image, ImageDraw
    im = Image.new("L", (32, 32), TRANSP)
    d = ImageDraw.Draw(im)
    d.polygon([(10, 10), (22, 10), (26, 31), (6, 31)], fill=BLUE, outline=NAVY)     # robe
    d.line([(16, 12), (16, 31)], fill=NAVY)
    d.polygon([(9, 13), (6, 22), (9, 23), (12, 15)], fill=BLUE, outline=NAVY)      # sleeves
    d.polygon([(23, 13), (26, 22), (23, 23), (20, 15)], fill=BLUE, outline=NAVY)
    d.ellipse([10, 1, 22, 14], fill=BLUE, outline=NAVY)                           # hood
    d.ellipse([12, 4, 20, 13], fill=BLACK)
    d.ellipse([13, 6, 19, 13], fill=TAN)                                          # face
    d.point([(14, 8), (17, 8)], fill=BLACK)
    d.line([(14, 11), (17, 11)], fill=WHITE)                                      # beard
    d.polygon([(14, 12), (18, 12), (16, 16)], fill=WHITE)
    d.rectangle([24, 22, 28, 27], fill=TAN, outline=BROWN)                        # lantern
    d.point([(26, 24), (25, 25), (27, 25)], fill=CREAM)
    d.line([(26, 21), (25, 18)], fill=DGRAY)
    d.rectangle([4, 18, 9, 24], fill=BROWN, outline=DRED)                         # pack
    d.point([(7, 25), (8, 24)], fill=TAN)
    d.ellipse([6, 22, 9, 25], fill=CREAM)                                         # hand
    return np.array(im, dtype=int)


def spr_spider(pose):
    from PIL import Image, ImageDraw
    im = Image.new("L", (32, 32), TRANSP)
    d = ImageDraw.Draw(im)
    lift = 0 if pose == 0 else -3
    for side in (-1, 1):                                        # 4 legs a side
        for k, (kx, ky) in enumerate([(5, 14), (8, 10), (9, 22), (6, 27)]):
            x0 = 16 + side * 4
            knee = (16 + side * (kx + 5), ky - 6 + lift * (k < 2))
            foot = (16 + side * (kx + 10), 31 if k >= 2 else ky + 6)
            d.line([(x0, 20), knee, foot], fill=BLACK, width=2)
            d.line([(x0, 20), knee], fill=DGRAY)
    d.ellipse([9, 15, 23, 30], fill=DGRAY, outline=BLACK)       # abdomen
    d.ellipse([12, 18, 20, 27], fill=DRED)
    d.line([(16, 19), (16, 26)], fill=TAN)
    d.ellipse([11, 9 + lift, 21, 18 + lift], fill=BLACK)        # head
    for ex in (13, 15, 17, 19):
        d.point([(ex, 12 + lift)], fill=LGREEN if pose == 0 else WHITE)
    d.line([(14, 18 + lift), (13, 21 + lift)], fill=CREAM)      # fangs
    d.line([(18, 18 + lift), (19, 21 + lift)], fill=CREAM)
    return np.array(im, dtype=int)


def spr_lich(pose):
    from PIL import Image, ImageDraw
    im = Image.new("L", (32, 32), TRANSP)
    d = ImageDraw.Draw(im)
    d.polygon([(9, 11), (23, 11), (29, 31), (3, 31)], fill=NAVY, outline=BLACK)      # robe
    d.polygon([(13, 11), (19, 11), (17, 31), (15, 31)], fill=DRED)                   # sash
    d.line([(4, 30), (28, 30)], fill=KHAKI)
    d.polygon([(9, 3), (12, 0), (14, 3), (16, 0), (18, 3), (20, 0), (23, 3), (22, 6), (10, 6)],
              fill=TAN, outline=BROWN)                                               # crown
    d.point([(16, 2)], fill=LGREEN)
    d.ellipse([11, 4, 21, 13], fill=GRAY)                                            # skull
    d.ellipse([12, 4, 19, 10], fill=WHITE)
    d.rectangle([12, 7, 14, 9], fill=BLACK)                                          # sockets
    d.rectangle([18, 7, 20, 9], fill=BLACK)
    d.point([(13, 8), (19, 8)], fill=LGREEN if pose == 0 else WHITE)                # glowing eyes
    d.point([(16, 10)], fill=BLACK)
    for x in (14, 16, 18):
        d.point([(x, 12)], fill=BLACK)
    if pose == 0:
        d.line([(9, 13), (5, 21)], fill=NAVY, width=3)
        d.line([(23, 13), (27, 21)], fill=NAVY, width=3)
        d.line([(27, 4), (27, 31)], fill=BROWN, width=2)                             # staff
        d.ellipse([24, 0, 30, 6], fill=LGREEN, outline=GREEN)
        d.point([(4, 22), (6, 22), (26, 22)], fill=CREAM)
    else:
        d.line([(9, 13), (2, 4)], fill=NAVY, width=3)                                # arms raised
        d.line([(23, 13), (30, 4)], fill=NAVY, width=3)
        d.point([(1, 3), (2, 2), (30, 2), (31, 3)], fill=CREAM)
        for (x, y) in [(5, 0), (16, -1), (27, 0), (3, 8), (29, 8)]:                  # green fire
            d.ellipse([x - 2, y, x + 2, y + 4], fill=LGREEN, outline=GREEN)
    return np.array(im, dtype=int)


def spr_crown():
    from PIL import Image, ImageDraw
    im = Image.new("L", (32, 32), TRANSP)
    d = ImageDraw.Draw(im)
    d.ellipse([4, 26, 28, 31], fill=DGRAY)                                           # cushion
    d.polygon([(4, 27), (4, 12), (10, 19), (16, 9), (22, 19), (28, 12), (28, 27)], fill=TAN, outline=BROWN)
    d.rectangle([4, 23, 28, 27], fill=CREAM, outline=BROWN)
    for x, c in ((9, DRED), (16, LGREEN), (23, BLUE)):
        d.ellipse([x - 2, 23, x + 2, 27], fill=c)
    d.point([(4, 11), (16, 8), (28, 11), (8, 15)], fill=WHITE)
    return np.array(im, dtype=int)


def tex_bones():
    """dark catacomb stone with rows of small skulls in shadowed niches"""
    t = tex_bricks([BLACK, DGRAY, DGRAY, GRAY], BLACK, 9)
    from PIL import Image, ImageDraw
    im = Image.fromarray(t.astype(np.uint8), "L")
    d = ImageDraw.Draw(im)
    for row, cy in enumerate((7, 23)):
        for cx in ((4, 12, 20, 28) if row == 0 else (8, 16, 24)):
            d.rectangle([cx - 4, cy - 5, cx + 3, cy + 4], fill=BLACK)         # niche
            d.ellipse([cx - 3, cy - 4, cx + 2, cy + 1], fill=GRAY)            # skull
            d.rectangle([cx - 2, cy, cx + 1, cy + 2], fill=GRAY)
            d.point([(cx - 2, cy - 2), (cx + 1, cy - 2)], fill=BLACK)         # eyes
            d.point([(cx - 2, cy - 3)], fill=WHITE)
            d.point([(cx - 1, cy + 2), (cx + 1, cy + 2)], fill=DGRAY)         # teeth
        d.line([(0, cy + 6), (31, cy + 6)], fill=DGRAY)                       # shelf
    return np.array(im, dtype=int)


# global sprite frame numbers (8 per sprite bank)
SPRITES = [spr_skeleton(0), spr_skeleton(1), spr_hurt(spr_skeleton(0)), spr_key(),     # 0-3
           spr_bat(0), spr_bat(1), spr_hurt(spr_bat(0)), spr_chest(),                  # 4-7
           spr_ghost(0), spr_ghost(1), spr_hurt(spr_ghost(0)), spr_merchant(),         # 8-11
           spr_spider(0), spr_spider(1), spr_hurt(spr_spider(0)), spr_crown(),         # 12-15
           spr_lich(0), spr_lich(1), spr_hurt(spr_lich(0))]                            # 16-18
# scale classes: (world units tall, height of the sprite's bottom above the floor)
SPR_CLASS = [(0.85, 0.0),   # 0 standing monster (skeleton, ghost)
             (0.45, 0.0),   # 1 key
             (0.75, 0.22),  # 2 flying (bat)
             (0.55, 0.0),   # 3 chest, spider
             (1.05, 0.0)]   # 4 boss
WALLS2 = [tex_door(False), tex_door(True), tex_stairs(), tex_bones()]

FLATS = [tex_flag(5), tex_grass(), tex_boards(), tex_beams(), tex_ceilstone()]
FLOOR_TEX = {0: 0, 1: 1, 2: 2}       # floor type -> flat texture
CEIL_TEX = {1: 3, 2: 4}              # ceil type -> flat texture (0 = sky)
SKY = tex_sky()

# ----------------------------------------------------------------------------- levels
# walls: '#' grey stone  'M' mossy  'W' wood  'H' hedge
#        'D' door  'L' locked door (needs a key)  'S' stairs  'X' secret wall (looks like '#')
# open cells (floor / ceiling):
#   '.' flagstone / stone ceiling   ',' grass / sky   ':' flagstone / sky
#   '=' wooden boards / wooden beams  '-' flagstone / wooden beams
LEVELS = [
    {   # level 1: the keep
        "name": "THE KEEP",
        "map": [
            "################",
            "#.....#=====W..#",
            "#.###.#=WW==W..#",
            "#.#.#.#=W===W..#",
            "#.#...--=W=WW..#",
            "#.####.#=W=..X##",
            "#......M,,,,MWW#",
            "###DMM,,,,,,,MW#",
            "#...H,,HH,,,,H.#",
            "#.#.M,,,,::,,M.#",
            "#.#.MM,,,::,MM.#",
            "#.#..........#.#",
            "#.###.###.####.#",
            "#...#...#....#.#",
            "#.#...#...##..L#",
            "##############S#",
        ],
        # (x, y, kind, p1, p2, p3, p4, message)
        "events": [
            (1, 3, "MSG", 0, 0, 0, 0, "STAIRS LIE BEHIND A LOCKED|DOOR IN THE SOUTH EAST"),
            (12, 5, "MSG", 0, 0, 0, 0, "THE EAST WALL SOUNDS|HOLLOW. TRY BUTTON 1"),
            (14, 1, "KEY", 0, 0, 0, 0, "YOU FOUND AN IRON KEY!"),
            (8, 9, "HEAL", 0, 0, 0, 0, "A COOL SPRING. YOU FEEL|REFRESHED"),
            (3, 3, "CHEST", 2, 15, 0, 0, "A CHEST! 2 POTIONS|AND 15 GOLD"),
            (14, 12, "CHEST", 1, 40, 0, 0, "A CHEST! A POTION|AND 40 GOLD"),
            (14, 15, "STAIRS", 1, 14, 14, 0, "YOU DESCEND INTO THE|CRYPT..."),
        ],
        "objects": [("KEY", 14, 1, 1), ("CHEST", 3, 3, 1), ("CHEST", 14, 12, 1),
                    ("SKEL", 6, 13, 1), ("SKEL", 11, 11, 2), ("BAT", 1, 10, 2), ("BAT", 10, 7, 3),
                    ("SKEL", 13, 2, 1), ("MERCHANT", 12, 9, 1)],
    },
    {   # level 2: the crypt
        "name": "THE CRYPT",
        "map": [
            "################",
            "#......#.......#",
            "#.####.#.###S#.#",
            "#.#....#.#...#.#",
            "#.#.####.#.#.#.#",
            "#.#......D.#...#",
            "#.########.#####",
            "#....M::::.....#",
            "####.M::::.###.#",
            "#....M::::.#...#",
            "#.##.MMMMMM#.#.#",
            "#.#........#.#.#",
            "#.#.######.#.#.#",
            "#.#......#...#.#",
            "#...####.#####.#",
            "##############S#",
        ],
        "events": [
            (14, 13, "MSG", 0, 0, 0, 0, "THE AIR IS COLD AND STILL"),
            (1, 13, "TELE", 8, 1, 1, 0, "A SHIMMERING LIGHT CARRIES|YOU AWAY!"),
            (12, 2, "STAIRS", 2, 13, 13, 3, "A NARROW STAIR WINDS DOWN|INTO THE CATACOMBS..."),
            (12, 3, "MSG", 0, 0, 0, 0, "A COLD DRAUGHT RISES FROM|THE STAIRS TO THE NORTH"),
            (7, 8, "HEAL", 0, 0, 0, 0, "MOONLIGHT HEALS YOUR|WOUNDS"),
            (1, 7, "CHEST", 3, 60, 0, 0, "A CHEST! 3 POTIONS|AND 60 GOLD"),
            (12, 9, "CHEST", 1, 90, 0, 0, "A CHEST! A POTION|AND 90 GOLD"),
            (14, 15, "STAIRS", 0, 14, 14, 0, "YOU CLIMB BACK TO THE KEEP"),
        ],
        "objects": [("CHEST", 1, 7, 1), ("CHEST", 12, 9, 1), ("MERCHANT", 13, 9, 1),
                    ("GHOST", 13, 7, 1), ("GHOST", 3, 11, 2), ("SKEL", 6, 1, 2), ("BAT", 14, 4, 3),
                    ("SKEL", 8, 13, 2), ("GHOST", 10, 3, 1)],
    },
]
LEVELS.append({   # level 3: the catacombs
    "name": "CATACOMBS",
    "map": [
        "################",
        "#...K.....K....#",
        "#...D.KKK.K.KK.#",
        "#...K.K...K..K.#",
        "#KKKK.K.KKKKK..#",
        "#.....K.....K..#",
        "#.KKK.KKKKK.K.K#",
        "#.K.K.....K.K..#",
        "#.K.KKKKK.K.KK.#",
        "#...K...K.K....#",
        "#KK.K.K.K.KKKK.#",
        "#...K.K...K....#",
        "#.KKK.KKK.K.KK.#",
        "#.....K....K...#",
        "#.KKKKKKKKKK.S.#",
        "################",
    ],
    "events": [
        (13, 13, "MSG", 0, 0, 0, 0, "BONES LINE THE WALLS.|SOMETHING WATCHES YOU"),
        (13, 14, "STAIRS", 1, 12, 3, 2, "YOU CLIMB BACK TO THE CRYPT"),
        (9, 9, "HEAL", 0, 0, 0, 0, "A BLESSED FONT. YOUR|STRENGTH RETURNS"),
        (3, 9, "CHEST", 2, 120, 0, 0, "A CHEST! 2 POTIONS|AND 120 GOLD"),
        (14, 3, "CHEST", 3, 80, 0, 0, "A CHEST! 3 POTIONS|AND 80 GOLD"),
        (5, 2, "MSG", 0, 0, 0, 0, "AN ICY VOICE: TURN BACK,|MORTAL. THE CROWN IS MINE"),
        (1, 2, "WIN", 0, 0, 0, 0, "THE LOST CROWN IS YOURS!"),
    ],
    "objects": [("CROWN", 1, 2, 1), ("LICH", 2, 2, 1), ("CHEST", 3, 9, 1), ("CHEST", 14, 3, 1),
                ("SPIDER", 13, 9, 2), ("SPIDER", 5, 11, 3), ("SPIDER", 9, 1, 2),
                ("GHOST", 1, 13, 2), ("SKEL", 9, 5, 3), ("SKEL", 3, 7, 2), ("BAT", 14, 5, 3)],
})

START = (0, 1, 1, 2)  # level, x, y, facing (south)

WALLCH = {'#': 16, 'M': 17, 'W': 18, 'H': 19, 'D': 20, 'L': 21, 'S': 22, 'X': 23, 'K': 24}
OPENCH = {'.': (0, 2), ',': (1, 0), ':': (0, 0), '=': (2, 1), '-': (0, 1)}
EVKIND = {"MSG": 1, "KEY": 2, "TELE": 3, "HEAL": 4, "WIN": 5, "STAIRS": 6, "CHEST": 7}
OBJKIND = {"SKEL": 1, "KEY": 2, "BAT": 3, "GHOST": 4, "CHEST": 5, "MERCHANT": 6,
           "SPIDER": 7, "LICH": 8, "CROWN": 9}
PASSABLE_FOR_CHECK = set(OPENCH) | {'D', 'L', 'X'}


def map_bytes(m):
    out = []
    for y in range(16):
        for x in range(16):
            ch = m[y][x]
            if ch in WALLCH:
                out.append(WALLCH[ch])
            else:
                f, c = OPENCH[ch]
                out.append(f | (c << 2))
    return out


def validate_level(L, start):
    m = L["map"]
    assert len(m) == 16 and all(len(r) == 16 for r in m), "map must be 16x16"
    for i in range(16):
        for ch in (m[0][i], m[15][i], m[i][0], m[i][15]):
            assert ch in WALLCH and ch not in "DLX", "border must be solid"
    sx, sy = start
    assert m[sy][sx] in OPENCH
    seen = {(sx, sy)}
    st = [(sx, sy)]
    while st:
        x, y = st.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if m[ny][nx] in PASSABLE_FOR_CHECK and (nx, ny) not in seen:
                seen.add((nx, ny))
                st.append((nx, ny))
    opens = sum(1 for y in range(16) for x in range(16) if m[y][x] in PASSABLE_FOR_CHECK)
    assert len(seen) == opens, f"{L['name']}: unreachable cells: {opens - len(seen)}"
    for ev in L["events"]:
        x, y, k = ev[0], ev[1], ev[2]
        if k == "STAIRS":
            assert m[y][x] == 'S', ev
        else:
            assert m[y][x] in OPENCH, ev
    for k, x, y, n in L["objects"]:
        assert m[y][x] in OPENCH, (k, x, y)
        if k == "CHEST":
            assert any(e[0] == x and e[1] == y and e[2] == "CHEST" for e in L["events"]), (k, x, y)


MAX_VIS = 12
for L in LEVELS:
    assert len(L["objects"]) <= MAX_VIS, f"{L['name']}: too many objects for MAX_VIS"
validate_level(LEVELS[0], START[1:3])
validate_level(LEVELS[1], (14, 14))
validate_level(LEVELS[2], (13, 13))

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
WALLBANK2 = POSEBANK0 + NPOSE        # doors / stairs
SPRBANK = WALLBANK2 + 1              # billboard sprites, frames 0-7
SPRBANK2 = SPRBANK + 1               # frames 8-15
SPRBANK3 = SPRBANK2 + 1              # frames 16-23


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
    b = bytearray(BANK)
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
DATABANK = SPRBANK3 + 1
LOGO_OFF, END_OFF = 0x0000, 0x1000
assert len(LOGO) <= END_OFF and len(THE_END) <= 0x1000

# ----------------------------------------------------------------------------- emit
def c_array(name, data, typ="unsigned char", per=16):
    s = f"const {typ} {name}[{len(data)}] = {{\n"
    for i in range(0, len(data), per):
        s += "  " + ",".join(f"0x{v:02X}" if typ == "unsigned char" else f"0x{v:04X}" for v in data[i:i + per]) + ",\n"
    return s + "};\n"


def main():
    banks = {}
    banks[FLOORBANK] = build_floor_bank()
    banks[WALLBANK] = build_wall_bank(WALLS)
    banks[WALLBANK2] = build_wall_bank(WALLS2)
    banks[SPRBANK] = build_sprite_bank(0)
    banks[SPRBANK2] = build_sprite_bank(8)
    banks[SPRBANK3] = build_sprite_bank(16)
    db = bytearray(BANK)                      # misc data bank (mapped into slot 2 on demand)
    db[LOGO_OFF:LOGO_OFF + len(LOGO)] = bytes(LOGO)
    db[END_OFF:END_OFF + len(THE_END)] = bytes(THE_END)
    banks[DATABANK] = db
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
        f.write(f"#define T_BG {T_BG}\n#define T_FONT {T_FONT}\n#define T_FRAME {T_FRAME}\n#define T_ARROW {T_ARROW}\n#define HUD_TILES {len(HUD)}\n")
        f.write(f"#define VIEW_TX {VIEW_TX}\n#define VIEW_TY {VIEW_TY}\n")
        f.write(f"#define START_L {START[0]}\n#define START_X {START[1]}\n#define START_Y {START[2]}\n#define START_F {START[3]}\n")
        f.write(f"#define SPR_BANK2 {SPRBANK2}\n#define SPR_BANK3 {SPRBANK3}\n")
        f.write(f"#define WALL_BANK2 {WALLBANK2}\n#define SPR_BANK {SPRBANK}\n#define SCALE_TAB (0x8000+0x{SCALE_OFF:04X})\n")
        f.write(f"#define BB_TABLE (0x8000+0x{BB_OFF:04X})\n#define BB_DA0 ({BB_DA0})\n#define BB_DA1 {BB_DA1}\n")
        f.write(f"#define BB_DB0 ({BB_DB0})\n#define BB_DB1 {BB_DB1}\n#define BB_NA {BB_NA}\n")
        f.write(f"#define NLEVELS {len(LEVELS)}\n#define NOBJ {sum(len(L['objects']) for L in LEVELS)}\n")
        for k, v in EVKIND.items():
            f.write(f"#define EV_{k} {v}\n")
        for k, v in OBJKIND.items():
            f.write(f"#define OBJ_{k} {v}\n")
        f.write("#define M_DOOR 20\n#define M_LOCKED 21\n#define M_STAIRS 22\n#define M_SECRET 23\n#define M_OPEN 8\n")
        f.write(f'#define FONTCHARS "{FONTCHARS}"\n')
        f.write("extern const unsigned char pal_bg[16];\nextern const unsigned char hud_tiles[];\n")
        f.write("extern const unsigned char map_init[NLEVELS * 256];\nextern const unsigned char view_nt[768];\n")
        f.write("extern const unsigned char ev_data[];\nextern const unsigned char ev_start[NLEVELS + 1];\n")
        f.write("extern const char * const messages[];\nextern const char * const level_name[NLEVELS];\n")
        f.write("extern const unsigned char obj_init[NOBJ * 5];\n")
        f.write("extern const unsigned char cell_kind[128];\nextern const unsigned char glyph_tab[96];\n")
        f.write(f"#define DATA_BANK {DATABANK}\n#define LOGO_RLE (0x8000+0x{LOGO_OFF:04X})\n#define THE_END_RLE (0x8000+0x{END_OFF:04X})\n")
        f.write("#endif\n")
    with open(os.path.join(OUT, "gen_nt.c"), "w") as f:     # bank 0: read by the VBlank flip
        f.write('/* generated by tools/gen.py - do not edit */\n#include "gen.h"\n')
        f.write(c_array("view_nt", nt))
    with open(os.path.join(OUT, "gen.c"), "w") as f:
        f.write('/* generated by tools/gen.py - do not edit */\n#include "gen.h"\n')
        f.write(c_array("pal_bg", pal))
        f.write(c_array("hud_tiles", list(hudbytes)))
        allmaps = []
        for L in LEVELS:
            allmaps += map_bytes(L["map"])
        f.write(c_array("map_init", allmaps))
        msgs, evd, evs = [], [], [0]
        for L in LEVELS:
            for (x, y, k, a, b_, c, d, txt) in L["events"]:
                evd += [x, y, EVKIND[k], a, b_, c, d, len(msgs)]
                msgs.append(txt)
            evs.append(len(evd) // 8)
        f.write(c_array("ev_data", evd))
        f.write(c_array("ev_start", evs))
        f.write("const char * const messages[] = {\n" + "".join(f'  "{m}",\n' for m in msgs) + "};\n")
        f.write("const char * const level_name[NLEVELS] = {" + ",".join(f'"{L["name"]}"' for L in LEVELS) + "};\n")
        objs = []
        for li, L in enumerate(LEVELS):
            for k, x, y, n in L["objects"]:
                objs += [OBJKIND[k], li, x, y, n]
        f.write(c_array("obj_init", objs))
        # floor type (0..2) -> page base (facing 0, parity 0); ceil type 1..2 -> 3+ ; 0 = sky
        # per map byte m (0..19): wall type+1, floor page, ceiling page (0 = sky)
        xw, xf, xc = [], [], []
        WT = {16: 1, 17: 2, 18: 3, 19: 4, 20: 5, 21: 6, 22: 7, 23: 1, 24: 8}
        for m in range(32):
            if m in WT:
                xw.append(WT[m]); xf.append(0x40 + 0x14); xc.append(0x40 + 0x14 + CEIL_TEX[2] * 8)
            elif m < 16:
                ft, ct = m & 3, (m >> 2) & 3
                xw.append(0); xf.append(0x40 + 0x14 + FLOOR_TEX.get(ft, 0) * 8)
                xc.append(0x40 + 0x14 + CEIL_TEX[ct] * 8 if ct in CEIL_TEX else 0)
            else:
                xw.append(1); xf.append(0x54); xc.append(0)
        f.write(c_array("cell_kind", xw + xf + [0] * 32 + xc))
        gt = [0] * 96                                    # ASCII 32..127 -> font tile
        for i, ch in enumerate(FONTCHARS):
            gt[ord(ch) - 32] = i
        f.write(c_array("glyph_tab", gt))

    print("poses:", " ".join(f"{i}:{u}/{n}c" for i, u, n in stats))
    print("q_fog", Q_FOG, "w_fog", W_FOG, "floor rows", FLOOR_ROWS, "banks", nbanks, "hud tiles", len(HUD))
    # preview image of textures
    try:
        from PIL import Image
        def rgb(c):
            r, g, b = PAL[c]
            return (r * 85, g * 85, b * 85)
        img = Image.new("RGB", (34 * (len(WALLS) + len(WALLS2) + len(SPRITES)) + 18 * 5 + 66, 34), (255, 0, 255))
        x = 0
        for t in WALLS + WALLS2 + SPRITES:
            for yy in range(32):
                for xx in range(32):
                    if int(t[yy][xx]) != TRANSP:
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
