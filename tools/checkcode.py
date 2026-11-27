#!/usr/bin/env python3
"""Fail if anything other than the SEGA header lives in 0x4000-0x7FFF (slot 1 is remapped at run time)."""
import sys
hi = 0
for line in open(sys.argv[1]):
    if not line.startswith(":"): continue
    n = int(line[1:3], 16); addr = int(line[3:7], 16); typ = int(line[7:9], 16)
    if typ != 0 or n == 0: continue
    end = addr + n - 1
    if addr >= 0x7F00: continue          # SEGA / SDSC header area
    if addr >= 0x4000: continue          # bank 1 = GAME area, checked below
    hi = max(hi, end)
print(f"bank 0 (renderer, ISR, SMSlib) top: 0x{hi:04X} ({0x4000-hi-1} bytes free below 0x4000)")
if hi >= 0x4000:
    sys.exit("ERROR: bank-0 code crosses into slot 1 (0x4000)")

if len(sys.argv) > 2:
    import re
    syms = dict((m.group(2), int(m.group(1), 16)) for m in re.finditer(r"([0-9A-F]{8})\s+(\S+)", open(sys.argv[2]).read()))
    g0, gl = syms.get("s__GAME", 0x4000), syms.get("l__GAME", 0)
    print(f"bank 1 (game logic): 0x{g0:04X}-0x{g0+gl-1:04X} ({0x7F00-g0-gl} bytes free)")
    if g0 + gl > 0x7F00:
        sys.exit("ERROR: GAME area runs into the ROM header")
    top = syms["s__HEAP"]
    print(f"RAM globals end: 0x{top:04X} ({0xC400-top} bytes free below the framebuffer)")
    if top > 0xC400:
        sys.exit("ERROR: C globals overlap the framebuffer at 0xC400")
