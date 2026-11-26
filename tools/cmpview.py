#!/usr/bin/env python3
"""Compare the view area of an smstest screenshot against simrender's output.
usage: cmpview.py shot.ppm cx cy f pose"""
import sys, subprocess
from PIL import Image
sys.argv, args = sys.argv[:2], sys.argv[2:]
exec(open('tools/simrender.py').read().split('if __name__')[0].replace("G = sys.argv[1]", "G = 'gen'"))
cx, cy, f, pose = map(int, args)
ref = render(cx, cy, f, pose)
im = Image.open(sys.argv[1]).convert('RGB')
bad = 0
for y in range(48):
    for x in range(64):
        c = PAL[ref[y][x]]
        rgb = ((c & 3) * 85, ((c >> 2) & 3) * 85, ((c >> 4) & 3) * 85)
        for a in range(2):
            for b in range(2):
                p = im.getpixel((64 + 2 * x + a, 24 + 2 * y + b))
                if tuple(p[:3]) != rgb:
                    bad += 1
print(f"view mismatch pixels: {bad}")
sys.exit(1 if bad else 0)
