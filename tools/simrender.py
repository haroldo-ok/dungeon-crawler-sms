#!/usr/bin/env python3
"""Reference renderer: walks the generated bank data exactly like the Z80 code does.
usage: simrender.py gendir out.png cx cy facing pose [cx cy f pose ...]"""
import sys, os, re
from PIL import Image

G = sys.argv[1]
banks = {}
for fn in os.listdir(G):
    m = re.match(r"bank(\d+)\.bin", fn)
    if m:
        banks[int(m.group(1))] = open(os.path.join(G, fn), "rb").read()
hdr = open(os.path.join(G, "gen.h")).read()
D = {k: int(v, 0) for k, v in re.findall(r"#define (\w+) \(?(0x[0-9A-Fa-f]+|-?\d+)", hdr)}
src = open(os.path.join(G, "gen.c")).read()


def arr(name):
    m = re.search(name + r"\[\d+\] = \{(.*?)\};", src, re.S)
    return [int(x, 16) for x in re.findall(r"0x[0-9A-F]+", m.group(1))]


PAL = arr("pal_bg")
MAP = arr("map_init")
CK = arr("cell_kind")
FB, WB, WB2 = banks[D["FLOOR_BANK"]], banks[D["WALL_BANK"]], banks[D["WALL_BANK2"]]
SBK = [banks[D["SPR_BANK"]], banks[D["SPR_BANK2"]], banks[D["SPR_BANK3"]]]
OBJI = arr("obj_init")


# object kind -> (scale class, idle frame)
KIND = {1: (0, 0), 2: (1, 3), 3: (2, 4), 4: (0, 8), 5: (3, 7), 6: (0, 11), 7: (3, 12), 8: (4, 16), 9: (1, 15)}


def render(cx, cy, f, pose, level=0, objs=None, mapdata=None, direct=None):
    """objs: list of (world x, world y, class, frame); default = the level's initial objects.
    direct: battle line-up, list of (xc, q, class, frame) drawn in front of everything"""
    MAPL = mapdata if mapdata is not None else MAP[level * 256:(level + 1) * 256]
    if objs is None:
        objs = []
        for i in range(0, len(OBJI), 5):
            t, l, x, y, n = OBJI[i:i + 5]
            if l == level:
                objs.append((x, y) + KIND[t])
    P = banks[D["POSE_BANK0"] + pose]
    hb = 0x900
    n = P[hb]
    sky = P[hb + 1]
    cw, cf, cc = [0] * 256, [0] * 256, [0] * 256
    for i in range(n):
        m = MAPL[(cy * 16 + cx + P[0x500 + f * 256 + i]) & 255]
        cw[i] = CK[m]
        cf[i] = CK[32 + m] + f * 2
        c = CK[96 + m]
        cc[i] = c + f * 2 if c else 0
    img = [[0] * 64 for _ in range(48)]
    colq = [0] * 64
    for x in range(64):
        par = x & 1
        rp = P[hb + 16 + 4 * x] | (P[hb + 17 + 4 * x] << 8)
        fp = P[hb + 18 + 4 * x] | (P[hb + 19 + 4 * x] << 8)
        rp -= 0x8000
        fp -= 0x8000
        while True:
            ci = P[rp]
            if ci == 0xFF:
                q = P[rp + 1]
                wt = 0
                break
            if cw[ci]:
                q, tcs = P[rp + 1], P[rp + 2]
                wt = cw[ci]
                break
            rp += 3
        Wd = P[q]
        colq[x] = q
        # floor / ceiling
        rows = 24 - Wd
        y = 47
        cyr = 0
        while rows > 0:
            ci, cnt = P[fp], P[fp + 1]
            fp += 2
            k = min(cnt, rows)
            for j in range(k):
                off = P[fp + j]
                img[y][x] = FB[((cf[ci] + par - 0x40) << 8) + off]
                if cc[ci]:
                    img[cyr][x] = FB[((cc[ci] + par - 0x40) << 8) + off]
                else:
                    img[cyr][x] = FB[0x800 + par * 1536 + ((sky + x) & 63) * 24 + cyr]
                y -= 1
                cyr += 1
            fp += cnt
            rows -= k
        # wall
        if Wd:
            if wt == 0:
                for yy in range(24 - Wd, 24 + Wd):
                    img[yy][x] = 0
            else:
                v0 = P[0x100 + q] | (P[0x200 + q] << 8)
                st = P[0x300 + q] | (P[0x400 + q] << 8)
                tc = tcs & 31
                shade = ((tcs >> 7) ^ f) & 1
                bank = WB if wt <= 4 else WB2
                base = ((((wt - 1) & 3) * 2 + shade) * 2 + par) * 1024 + tc * 32
                acc = v0
                for yy in range(24 - Wd, 24 + Wd):
                    img[yy][x] = bank[base + (acc >> 8)]
                    acc += st
    # billboards (same integer maths as draw_objects in render.c)
    vis = []
    for (ox, oy, typ, frame) in ([] if direct else objs):
        dx, dy = ox - cx, oy - cy
        if not (-12 <= dx <= 12 and -12 <= dy <= 12):
            continue
        da, db = [(dx, -dy), (dy, dx), (-dx, dy), (-dy, -dx)][f]
        if not (D["BB_DA0"] <= da <= D["BB_DA1"] and D["BB_DB0"] <= db <= D["BB_DB1"]):
            continue
        e = 0x3C00 + ((db - D["BB_DB0"]) * D["BB_NA"] + (da - D["BB_DA0"])) * 2
        xc, q = P[e], P[e + 1]
        if not q:
            continue
        xc = xc - 256 if xc > 127 else xc
        vis.append((q, len(vis), xc, typ, frame))
    if direct:
        vis = [(q, i, xc, typ, frame) for i, (xc, q, typ, frame) in enumerate(direct)]
    vis.sort(key=lambda v: (v[0], v[1]))
    for q, _, xc, typ, frame in vis:
        tb = 0x2600 + typ * 0x400
        top = P[tb + q]; top = top - 256 if top > 127 else top
        hgt = P[tb + 0x100 + q]; w2 = hgt >> 1
        step = P[tb + 0x200 + q] | (P[tb + 0x300 + q] << 8)
        dq = 255 if direct else q
        SB = SBK[frame >> 3]
        frame &= 7
        x0, x1 = xc - w2, min(64, xc + w2)
        ys, ye = max(0, top), min(48, top + hgt)
        if ys >= ye:
            continue
        v0 = ((ys - top) * step) & 0xFFFF
        xs = max(0, x0)
        u = ((xs - x0) * step) & 0xFFFF
        while xs < x1:
            if colq[xs] < dq:
                uc = u >> 8
                base = ((frame * 2 + (xs & 1)) * 1024) + (uc >> 3) * 256
                acc = ((((uc & 7) << 5) << 8) + v0) & 0xFFFF
                for yy in range(ys, ye):
                    t = SB[base + (acc >> 8)]
                    if t != 0xFF:
                        img[yy][xs] = t
                    acc = (acc + step) & 0xFFFF
            xs += 1
            u = (u + step) & 0xFFFF
    # decode nibble storage
    out = [[(img[y][x] >> 4) if (x & 1) == 0 else (img[y][x] & 15) for x in range(64)] for y in range(48)]
    return out


def to_image(frames):
    im = Image.new("RGB", (130 * len(frames), 96))
    for k, fr in enumerate(frames):
        for y in range(48):
            for x in range(64):
                c = PAL[fr[y][x]]
                rgb = ((c & 3) * 85, ((c >> 2) & 3) * 85, ((c >> 4) & 3) * 85)
                for a in range(2):
                    for b in range(2):
                        im.putpixel((k * 130 + 2 * x + a, 2 * y + b), rgb)
    return im


if __name__ == "__main__":
    args = list(map(int, sys.argv[3:]))
    frames = [render(*args[i:i + 5]) for i in range(0, len(args), 5)]
    to_image(frames).save(sys.argv[2])
