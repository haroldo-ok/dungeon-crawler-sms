#!/usr/bin/env python3
"""Fail if anything other than the SEGA header lives in 0x4000-0x7FFF (slot 1 is remapped at run time)."""
import sys
hi = 0
for line in open(sys.argv[1]):
    if not line.startswith(":"): continue
    n = int(line[1:3], 16); addr = int(line[3:7], 16); typ = int(line[7:9], 16)
    if typ != 0 or n == 0: continue
    end = addr + n - 1
    if addr >= 0x7FF0: continue          # SEGA / SDSC header area
    if addr >= 0x7F00: continue                    # SDSC strings
    hi = max(hi, end)
print(f"code+const top: 0x{hi:04X} ({0x4000-hi-1} bytes free below 0x4000)")
if hi >= 0x4000:
    sys.exit("ERROR: code/const data crosses into slot 1 (0x4000)")

if len(sys.argv) > 2:
    import re
    syms = dict((m.group(2), int(m.group(1), 16)) for m in re.finditer(r"([0-9A-F]{8})\s+(\S+)", open(sys.argv[2]).read()))
    top = syms["s__HEAP"]
    print(f"RAM globals end: 0x{top:04X} ({0xC400-top} bytes free below the framebuffer)")
    if top > 0xC400:
        sys.exit("ERROR: C globals overlap the framebuffer at 0xC400")
