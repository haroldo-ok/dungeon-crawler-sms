"""Procedural art for SMS Dungeon: the 16-colour palette, texture and
sprite painters.  tools/content.py picks from these by name (or loads PNGs)."""
import math, random
import numpy as np

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


def tex_stairs(base=None, post=(CREAM, KHAKI)):
    """an arch opening with steps going down into the dark, cut into `base`"""
    t = tex_bricks([DGRAY, GRAY, GRAY], BLACK, 3) if base is None else base.copy()
    for y in range(5, 32):
        for x in range(6, 26):
            if y < 9 and (x - 15.5) ** 2 + (y - 9) ** 2 * 2.2 > 100:
                continue
            step = (31 - y) // 4
            shade = [GRAY, DGRAY, DGRAY, BLACK, BLACK, BLACK, BLACK, BLACK][min(step, 7)]
            if (31 - y) % 4 == 0 and step < 4:
                shade = WHITE if step == 0 else GRAY
            t[y, x] = shade
    for y in range(5, 32):
        for x in (5, 26):
            t[y, x] = post[0] if y % 2 else post[1]
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
# scale classes: (world units tall, height of the sprite's bottom above the floor)




# ============================================================================ phase 6 art
def _img(t=None, fill=TRANSP):
    from PIL import Image, ImageDraw
    im = Image.fromarray(t.astype(np.uint8), "L") if t is not None else Image.new("L", (32, 32), fill)
    return im, ImageDraw.Draw(im)


def _arr(im):
    return np.array(im, dtype=int)


# ---- the crypt: cold blue-grey ashlar, sealed tombs, stained glass, chequered marble
def tex_ashlar(seed=21):
    return tex_bricks([NAVY, DGRAY, DGRAY, GRAY, BLUE], BLACK, seed)


def tex_tomb():
    im, d = _img(tex_ashlar(22))
    n = noise2(32, 32, 4, 23)
    d.rectangle([4, 5, 27, 29], fill=BLACK)                                   # recess
    for y in range(7, 28):
        for x in range(6, 26):
            im.putpixel((x, y), pick([GRAY, KHAKI, CREAM], 0.25 + 0.6 * n[y, x], x, y))
    d.rectangle([6, 7, 25, 27], outline=DGRAY)
    d.line([(15, 10), (15, 18)], fill=DGRAY, width=2)                         # carved cross
    d.line([(11, 13), (20, 13)], fill=DGRAY, width=2)
    for y in (21, 23, 25):                                                    # inscription
        d.line([(9, y), (22, y)], fill=DGRAY)
        d.point([(10 + (y * 3) % 7, y), (18 - y % 5, y)], fill=KHAKI)
    d.line([(4, 30), (27, 30)], fill=GRAY)                                    # ledge
    return _arr(im)


def tex_window():
    """a moonlit stained-glass lancet in ashlar"""
    im, d = _img(tex_ashlar(24))
    d.rectangle([8, 9, 23, 31], fill=BLACK)
    d.ellipse([8, 2, 23, 17], fill=BLACK)
    panes = [BLUE, SKY, DRED, NAVY, TAN, BLUE, PSKY, DRED]
    for y in range(4, 31):
        for x in range(10, 22):
            if y < 10 and (x - 15.5) ** 2 + (y - 10) ** 2 > 36:
                continue
            k = ((x - 10) // 3 + (y - 4) // 5) % len(panes)
            c = panes[k]
            if (x - 10) % 3 == 2 or (y - 4) % 5 == 4:
                c = BLACK                                                     # lead came
            im.putpixel((x, y), c)
    d.ellipse([13, 5, 18, 10], fill=CREAM, outline=BLACK)                     # rose
    d.line([(15, 14), (15, 30)], fill=DGRAY)                                  # mullion
    return _arr(im)


def tex_gate():
    """iron portcullis gate (the crypt's doors)"""
    t = tex_ashlar(25)
    for y in range(3, 32):
        for x in range(3, 29):
            bar = (x - 3) % 5 in (0, 1)
            rail = y in (8, 9, 22, 23)
            if bar or rail:
                t[y, x] = GRAY if ((x - 3) % 5 == 0 or y in (8, 22)) else DGRAY
            else:
                t[y, x] = BLACK if (x + y) % 7 else NAVY
    for x in range(4, 28, 5):
        t[31, x] = WHITE                                                      # spikes
    return t


def tex_gate_locked():
    t = tex_gate()
    im, d = _img(t)
    d.rectangle([12, 12, 19, 20], fill=TAN, outline=BROWN)
    d.point([(15, 15), (15, 16), (15, 17), (14, 16), (16, 16)], fill=BLACK)
    d.line([(4, 11), (27, 19)], fill=DGRAY, width=2)                          # chain
    d.line([(4, 19), (27, 11)], fill=DGRAY, width=2)
    return _arr(im)


def tex_marble():
    n = noise2(16, 16, 4, 61)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            light = ((x // 8) + (y // 8)) % 2 == 0
            v = 0.3 + 0.5 * n[y, x]
            vein = abs(math.sin((x + y * 0.6) * 0.8 + n[y, x] * 4)) < 0.12
            if light:
                t[y, x] = DGRAY if vein else pick([GRAY, WHITE], v, x, y)
            else:
                t[y, x] = GRAY if vein else pick([BLACK, NAVY], v, x, y)
    return t


def tex_vault():
    t = np.zeros((16, 16), dtype=int)
    n = noise2(16, 16, 4, 62)
    for y in range(16):
        for x in range(16):
            rib = x in (0, 15) or y in (0, 15) or x == y or x == 15 - y
            t[y, x] = GRAY if rib and (x + y) % 3 else DGRAY if rib else pick([BLACK, NAVY], 0.3 + 0.5 * n[y, x], x, y)
    return t


def tex_darkflag():
    n = noise2(16, 16, 4, 63)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            if x % 8 == 7 or y % 8 == 7:
                t[y, x] = BLACK
            else:
                t[y, x] = pick([NAVY, DGRAY, GRAY], 0.2 + 0.6 * n[y, x], x, y)
                if n[y, x] > 0.8:
                    t[y, x] = DGREEN                                          # moss
    return t


def tex_night_sky():
    n = noise2(64, 24, 8, 4300)
    r = random.Random(77)
    t = np.zeros((24, 64), dtype=int)
    for y in range(24):
        for x in range(64):
            t[y, x] = pick([BLACK, NAVY, NAVY, BLUE], y / 23.0 * 0.9 + n[y, x] * 0.15, x, y)
    for _ in range(26):
        x, y = r.randrange(64), r.randrange(18)
        t[y, x] = WHITE if r.random() < 0.4 else PSKY
    for x in range(64):                                                       # tree line
        h = 20 + int(2.5 * (math.sin(x * 0.7) * 0.5 + 0.5) + (x * 7 % 5 == 0))
        for y in range(h, 24):
            t[y, x] = BLACK
    return t


# ---- the mines: rough rock, timber shoring, crystal veins, lanterns, rails
def tex_rock(seed=31, colors=None):
    colors = colors or [BLACK, DRED, DRED, BROWN, BROWN, TAN]
    n = noise2(32, 32, 5, seed)
    n2 = noise2(32, 32, 2, seed + 1)
    t = np.zeros((32, 32), dtype=int)
    for y in range(32):
        for x in range(32):
            v = 0.05 + 0.6 * n[y, x] + 0.35 * n2[y, x]
            crack = abs(n[y, x] - 0.5) < 0.03 or abs(n2[y, x] - 0.45) < 0.025
            t[y, x] = BLACK if crack else pick(colors, v, x, y)
    return t


def tex_shored():
    t = tex_rock(33)
    for y in range(32):
        for x in range(32):
            post = x in range(2, 7) or x in range(25, 30)
            lintel = y in range(1, 6)
            if post or lintel:
                grain = math.sin((y if post else x) * 0.9 + (x if post else y) * 2.1) * 0.5 + 0.5
                c = pick([DRED, BROWN, TAN], 0.25 + 0.5 * grain, x, y)
                if (post and x in (2, 25)) or (lintel and y == 1):
                    c = TAN
                if (post and x in (6, 29)) or (lintel and y == 5):
                    c = DRED
                t[y, x] = c
    for (x, y) in ((4, 3), (27, 3)):
        t[y, x] = GRAY                                                        # bolts
    return t


def tex_crystal():
    t = tex_rock(34)
    im, d = _img(t)
    for (cx, cy, h) in ((8, 22, 10), (13, 26, 7), (22, 12, 9), (26, 16, 6), (18, 28, 5), (5, 9, 5)):
        d.polygon([(cx - 2, cy), (cx, cy - h), (cx + 2, cy)], fill=BLUE, outline=NAVY)
        d.line([(cx, cy - h + 1), (cx, cy - 1)], fill=SKY)
        d.point([(cx - 1, cy - 2)], fill=PSKY)
        d.point([(cx, cy - h + 1)], fill=WHITE)
    return _arr(im)


def tex_lantern():
    t = tex_rock(35)
    im, d = _img(t)
    for r_, c in ((11, BROWN), (8, TAN), (5, KHAKI)):                         # glow on the rock
        for y in range(32):
            for x in range(32):
                if (x - 16) ** 2 + (y - 17) ** 2 < r_ * r_ and t[y, x] not in (BLACK,) and (x + y) % 2:
                    im.putpixel((x, y), c)
    d.line([(16, 3), (16, 9)], fill=DGRAY)                                    # hook + chain
    d.line([(12, 3), (20, 3)], fill=GRAY)
    d.rectangle([12, 10, 20, 22], fill=BLACK, outline=DGRAY)
    d.rectangle([13, 12, 19, 20], fill=TAN)
    d.ellipse([14, 13, 18, 19], fill=CREAM)
    d.point([(16, 15)], fill=WHITE)
    d.line([(11, 10), (21, 10)], fill=GRAY)
    d.line([(12, 22), (20, 22)], fill=GRAY)
    return _arr(im)


def tex_mine_door(locked=False):
    t = tex_rock(36)
    im, d = _img(t)
    d.rectangle([4, 4, 27, 31], fill=DRED)
    for x in range(5, 27):
        for y in range(5, 32):
            p = (x - 5) // 5
            g = math.sin(y * 0.8 + p * 3) * 0.5 + 0.5
            im.putpixel((x, y), DRED if (x - 5) % 5 == 4 else pick([BROWN, TAN], 0.2 + 0.6 * g, x, y))
    d.line([(5, 6), (26, 30)], fill=DRED, width=3)                            # cross brace
    d.line([(26, 6), (5, 30)], fill=DRED, width=3)
    d.line([(5, 6), (26, 30)], fill=TAN)
    d.line([(26, 6), (5, 30)], fill=TAN)
    d.rectangle([2, 2, 29, 4], fill=BROWN)
    if locked:
        d.rectangle([12, 14, 19, 22], fill=DGRAY, outline=BLACK)
        d.point([(15, 17), (15, 18), (16, 17), (16, 18)], fill=BLACK)
    return _arr(im)


def tex_dirt():
    n = noise2(16, 16, 3, 71)
    r = random.Random(71)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            t[y, x] = pick([DRED, BROWN, BROWN, TAN], 0.15 + 0.7 * n[y, x], x, y)
    for _ in range(7):
        x, y = r.randrange(15), r.randrange(15)
        t[y, x] = KHAKI
        t[y, x + 1] = DGRAY
    return t


def tex_rails():
    t = tex_dirt()
    for y in range(16):
        for x in range(16):
            if y % 4 == 1 and 2 <= x <= 13:
                t[y, x] = BROWN if x % 2 else DRED                            # sleepers
            if x in (4, 11):
                t[y, x] = GRAY                                                # rails
            if x in (5, 12):
                t[y, x] = DGRAY
    return t


def tex_rock_ceil():
    n = noise2(16, 16, 4, 72)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            t[y, x] = pick([BLACK, DRED, BROWN], 0.1 + 0.8 * n[y, x], x, y)
    return t


def tex_dusk_sky():
    n = noise2(64, 24, 8, 4400)
    t = np.zeros((24, 64), dtype=int)
    for y in range(24):
        for x in range(64):
            g = y / 23.0
            c = pick([NAVY, DRED, BROWN, TAN, KHAKI], g * 1.05 + n[y, x] * 0.12, x, y)
            if 6 <= y <= 12 and n[y, x] > 0.62:
                c = DGRAY if n[y, x] > 0.7 else DRED                          # dark clouds
            t[y, x] = c
    for x in range(64):                                                       # crags
        h = 19 + int(4 * abs(math.sin(x * 0.21)) * (0.6 + 0.4 * math.sin(x * 0.9)))
        for y in range(h, 24):
            t[y, x] = BLACK
    return t


# ---- the catacombs: dark rubble stone, skull walls, torches, bone-strewn earth
def tex_catastone():
    return tex_rock(41, [BLACK, BLACK, DGRAY, DGRAY, GRAY, KHAKI])


def tex_torch():
    im, d = _img(tex_catastone())
    for y in range(32):
        for x in range(32):
            r2 = (x - 16) ** 2 + (y - 11) ** 2
            if r2 < 100 and (x + y) % 2 and im.getpixel((x, y)) != BLACK:
                im.putpixel((x, y), BROWN if r2 > 49 else TAN)
    d.polygon([(13, 16), (19, 16), (17, 26), (15, 26)], fill=BROWN, outline=DRED)   # sconce
    d.line([(12, 16), (20, 16)], fill=GRAY)
    d.ellipse([12, 4, 20, 16], fill=DRED)                                     # flame
    d.ellipse([13, 6, 19, 15], fill=TAN)
    d.ellipse([14, 9, 18, 15], fill=CREAM)
    d.point([(16, 12)], fill=WHITE)
    d.point([(16, 3)], fill=DRED)
    return _arr(im)


def tex_skullpile():
    t = np.full((32, 32), BLACK, dtype=int)
    im, d = _img(t)
    for row in range(5):
        cy = 3 + row * 7
        for k in range(5):
            cx = 3 + k * 7 + (3 if row % 2 else 0)
            col = [KHAKI, GRAY, KHAKI, CREAM][(row * 3 + k) % 4]
            d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=col)
            d.rectangle([cx - 2, cy + 1, cx + 2, cy + 3], fill=col)
            d.point([(cx - 1, cy), (cx + 1, cy)], fill=BLACK)
            d.point([(cx - 1, cy - 2)], fill=WHITE)
            d.point([(cx, cy + 3)], fill=DGRAY)
    return _arr(im)


def tex_slab_door(locked=False):
    t = tex_catastone()
    im, d = _img(t)
    d.rectangle([4, 3, 27, 31], fill=BLACK)
    n = noise2(32, 32, 4, 45)
    for y in range(5, 32):
        for x in range(6, 26):
            im.putpixel((x, y), pick([DGRAY, GRAY, KHAKI], 0.25 + 0.6 * n[y, x], x, y))
    d.ellipse([11, 8, 20, 17], fill=DGRAY)                                    # carved skull
    d.rectangle([13, 15, 18, 19], fill=DGRAY)
    d.point([(13, 12), (14, 12), (17, 12), (18, 12)], fill=BLACK)
    d.line([(6, 24), (25, 24)], fill=DGRAY)
    if locked:
        d.rectangle([13, 25, 18, 30], fill=TAN, outline=BROWN)
    return _arr(im)


def tex_bone_floor():
    n = noise2(16, 16, 3, 81)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            t[y, x] = pick([BLACK, DGRAY, BROWN], 0.15 + 0.7 * n[y, x], x, y)
    for (x0, y0, x1, y1) in ((2, 3, 6, 5), (9, 11, 13, 9), (10, 2, 11, 6)):
        n_ = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(n_ + 1):
            t[y0 + (y1 - y0) * i // n_, x0 + (x1 - x0) * i // n_] = CREAM
    t[13][3] = KHAKI; t[13][4] = KHAKI; t[12][3] = CREAM
    return t


def tex_low_ceil():
    n = noise2(16, 16, 4, 82)
    t = np.zeros((16, 16), dtype=int)
    for y in range(16):
        for x in range(16):
            t[y, x] = BLACK if (y % 8 == 7 or (x + (y // 8) * 4) % 8 == 7) else \
                pick([BLACK, DGRAY], 0.2 + 0.7 * n[y, x], x, y)
    return t


# ---- new monsters
def spr_slime(pose):
    im, d = _img()
    if pose == 0:
        box = [3, 14, 28, 31]
    else:
        box = [7, 4, 24, 31]                                                  # rears up
    d.ellipse(box, fill=GREEN, outline=DGREEN)
    x0, y0, x1, y1 = box
    d.ellipse([x0 + 3, y0 + 2, x1 - 8, y0 + (y1 - y0) // 2], fill=LGREEN)    # sheen
    d.rectangle([x0 + 1, 29, x1 - 1, 31], fill=DGREEN)
    ey = y0 + (y1 - y0) // 3 + 2
    for ex in (13, 19):
        d.ellipse([ex - 2, ey - 2, ex + 2, ey + 2], fill=WHITE)
        d.point([(ex, ey)], fill=BLACK)
    if pose == 1:
        d.ellipse([12, ey + 5, 19, ey + 11], fill=BLACK)                      # open maw
        d.point([(15, 0), (16, 2), (12, 1)], fill=LGREEN)                     # acid drops
    d.point([(x0 + 5, y0 + 3), (x0 + 6, y0 + 3)], fill=WHITE)
    d.point([(6, 26), (25, 24), (10, 29)], fill=DGREEN)                       # bubbles
    return _arr(im)


def spr_golem(pose):
    im, d = _img()
    rock, lit, dark = BROWN, TAN, DRED
    d.rectangle([10, 22, 14, 31], fill=rock, outline=dark)                    # legs
    d.rectangle([18, 22, 22, 31], fill=rock, outline=dark)
    d.polygon([(7, 9), (25, 9), (23, 24), (9, 24)], fill=rock, outline=dark)   # torso
    d.line([(9, 10), (23, 10)], fill=lit)
    d.line([(12, 14), (15, 18), (13, 22)], fill=dark)                         # cracks
    d.line([(20, 12), (18, 17)], fill=dark)
    d.polygon([(13, 15), (19, 15), (16, 19)], fill=BLUE)                      # crystal heart
    d.point([(16, 16)], fill=PSKY)
    if pose == 0:
        d.rectangle([2, 10, 7, 23], fill=rock, outline=dark)                  # arms down
        d.rectangle([25, 10, 30, 23], fill=rock, outline=dark)
        d.rectangle([1, 22, 8, 27], fill=rock, outline=dark)                  # fists
        d.rectangle([24, 22, 31, 27], fill=rock, outline=dark)
    else:
        d.rectangle([2, 0, 7, 11], fill=rock, outline=dark)                   # arms up
        d.rectangle([25, 0, 30, 11], fill=rock, outline=dark)
        d.rectangle([0, 0, 31, 4], fill=GRAY, outline=DGRAY)                  # boulder overhead
        d.point([(5, 1), (14, 2), (25, 1)], fill=WHITE)
    d.rectangle([12, 3 if pose == 0 else 5, 20, 10], fill=rock, outline=dark)   # head
    ey = 6 if pose == 0 else 8
    d.point([(14, ey), (18, ey)], fill=LGREEN if pose == 0 else CREAM)
    d.point([(15, ey), (17, ey)], fill=dark)
    return _arr(im)


def load_png(path, transparent=(255, 0, 255)):
    """Load an image as palette indices (nearest SMS colour; magenta = transparent).
    Walls and sprites are 32x32, flats 16x16, skies 64x24."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    out = np.zeros((im.height, im.width), dtype=int)
    for y in range(im.height):
        for x in range(im.width):
            p = im.getpixel((x, y))
            if p == transparent:
                out[y, x] = TRANSP
                continue
            out[y, x] = min(range(16), key=lambda c: sum((PAL[c][i] * 85 - p[i]) ** 2 for i in range(3)))
    return out


def tex_lever():
    """a rusty lever set in the rock"""
    im, d = _img(tex_rock(37))
    d.rectangle([10, 14, 21, 25], fill=DGRAY, outline=BLACK)                  # mounting plate
    d.point([(11, 15), (20, 15), (11, 24), (20, 24)], fill=GRAY)
    d.line([(16, 20), (22, 6)], fill=GRAY, width=2)                           # handle
    d.line([(17, 20), (23, 6)], fill=WHITE)
    d.ellipse([20, 3, 26, 9], fill=DRED, outline=BLACK)                       # knob
    d.ellipse([14, 18, 18, 22], fill=BLACK)
    return _arr(im)
