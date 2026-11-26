#!/usr/bin/env python3
"""Splice generated data banks into the ROM produced by ihx2sms.
usage: mkrom.py in.sms gendir out.sms"""
import sys, os, re
src, gdir, out = sys.argv[1:4]
rom = bytearray(open(src, "rb").read())
banks = {}
for fn in os.listdir(gdir):
    m = re.match(r"bank(\d+)\.bin$", fn)
    if m:
        banks[int(m.group(1))] = open(os.path.join(gdir, fn), "rb").read()
need = max(banks) + 1
size = 1
while size < need:
    size *= 2
size = max(size, 2)
# code must not spill into bank 2+ (slot 2 is remapped), and should stay < 0x4000
if len(rom) > 0x8000:
    assert all(b == 0xFF for b in rom[0x8000:]) or False, "code/data spilled past 32 KiB"
rom = rom[:0x8000] + bytearray([0xFF]) * (size * 0x4000 - 0x8000)
for k, v in banks.items():
    assert k >= 2 and len(v) == 0x4000
    rom[k * 0x4000:(k + 1) * 0x4000] = v
open(out, "wb").write(rom)
print(f"{out}: {len(rom)//1024} KiB, {len(banks)} data banks")
