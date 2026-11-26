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
D = {k: int(v, 0) for k, v in re.findall(r"#define (\w+) \(?(0x[0-9A-Fa-f]+|\d+)", hdr)}
src = open(os.path.join(G, "gen.c")).read()


def arr(name):
    m = re.search(name + r"\[\d+\] = \{(.*?)\};", src, re.S)
    return [int(x, 16) for x in re.findall(r"0x[0-9A-F]+", m.group(1))]


PAL = arr("pal_bg")
MAP = arr("map_init")
CK = arr("cell_kind")
FB, WB = banks[D["FLOOR_BANK"]], banks[D["WALL_BANK"]]


def render(cx, cy, f, pose):
    P = banks[D["POSE_BANK0"] + pose]
    hb = 0x900
    n = P[hb]
    sky = P[hb + 1]
    cw, cf, cc = [0] * 256, [0] * 256, [0] * 256
    for i in range(n):
        m = MAP[(cy * 16 + cx + P[0x500 + f * 256 + i]) & 255]
        cw[i] = CK[m]
        cf[i] = CK[32 + m] + f * 2
        c = CK[96 + m]
        cc[i] = c + f * 2 if c else 0
    img = [[0] * 64 for _ in range(48)]
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
                base = (((wt - 1) * 2 + shade) * 2 + par) * 1024 + tc * 32
                acc = v0
                for yy in range(24 - Wd, 24 + Wd):
                    img[yy][x] = WB[base + (acc >> 8)]
                    acc += st
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
    frames = [render(*args[i:i + 4]) for i in range(0, len(args), 4)]
    to_image(frames).save(sys.argv[2])
