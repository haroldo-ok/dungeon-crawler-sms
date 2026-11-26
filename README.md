# SMS Dungeon

A first-person, grid-based dungeon crawler for the **Sega Master System**.

- You move cell by cell, but every step, strafe and 90° turn is animated as a smooth glide or rotation. There are 6 in-between frames in *smooth* mode and 3 in *quick* mode.
- Walls, floor and ceiling are texture-mapped in real time from the live map.
- Any cell without a ceiling shows a scrolling sky panorama, so courtyards are open to the sky and roof edges look right.

`dungeon.sms` is a 512 KiB ROM using the standard Sega mapper. It runs in any SMS emulator (Emulicious, MEKA, Genesis Plus GX…) and should run on a flash cart.

## Controls

| Pad | Action |
|---|---|
| Up / Down | step forward / back |
| Left / Right | turn 90° |
| Button 1 + Left/Right | strafe |
| Button 2 | toggle step mode (smooth 6 sub-steps / quick 4) |

## How the engine works

The view is 64×48 "logical" pixels, shown as 2×2 blocks in a 128×96 window.

1. **Pose tables (offline, `tools/gen.py`).** A camera between grid cells can only be at a few positions: at rest, k/6 of the way forward or sideways, or turned by k×15° (plus the quarter steps used by quick mode). That gives 22 poses relative to the current cell and facing. For each pose the generator ray-casts in floating point and stores one 16 KiB ROM bank containing:
   - for every screen column, the list of cells the ray crosses, with the wall height and texture column at each crossing;
   - for every floor row, which cell and which texel it samples;
   - packed map offsets for each facing (the other facings are 90° rotations).
2. **Per frame (Z80, `src/render_asm.s`).** Nothing about the world is precomputed:
   - The relative cells are looked up in the live map.
   - Each ray stops at the first solid cell (beyond 12 cells it ends in black fog).
   - Each column gets a scaled wall strip, then floor and ceiling texels mirrored around the horizon. Cells with no ceiling get sky.
   - All of this goes into a chunky framebuffer in RAM.
3. **Chunky→planar upload.** A 2 KiB lookup table converts pixel pairs to the VDP's 4 bitplanes. The bytes go straight into a back buffer in VRAM, with every write paced ≥27 cycles apart so it's safe with the display on.
4. **Flip in VBlank.** The VBlank interrupt re-points the 16×12 tiles of the view at the finished buffer, so the CPU starts the next frame immediately.

Textures are 32×32 for walls and 16×16 for floor and ceiling. There are pre-rotated copies for each facing, nibble-shifted copies so two pixels OR into one lookup index, and a darker variant for east/west faces.

`src/render.c` contains a plain-C reference version of every kernel. Building with `make DEFS=` uses it, and it renders the same pixels as the assembly.

### Speed (NTSC, measured in the bundled emulator)

| Scene | Rendered fps |
|---|---|
| corridor walk / turn | ~6.6 |
| wooden hall turn | ~6.2 |
| open courtyard turn | ~5.9 |

About half of each frame is the planar conversion and upload: 6 KiB of tile data at the VDP's paced write rate. Nothing is rendered while you stand still. A smooth step takes about 0.9 s, a quick step about 0.6 s.

## Layout

```
src/main.c        game loop, input, movement sequences, HUD, sound, VBlank flip
src/render.c      renderer driver + C reference kernels
src/render_asm.s  Z80 kernels: cell setup, ray walk, floor/ceiling/sky, walls, c2p upload
src/engine.h      fixed RAM map, mapper macros
tools/gen.py      textures, map, palette, HUD font, pose tables -> gen/
tools/simrender.py  Python renderer that walks the same bank data (test oracle)
tools/mkrom.py    splices the generated banks into the ROM
tests/            harness scripts (boot, pad-only exploration, pixel-exact views, benchmark)
```

The map is a 16×16 grid in `tools/gen.py` (`MAP`). Its legend: `#` stone, `M` mossy, `W` wood, `H` hedge. Open cells: `.` flagstone + stone ceiling, `-` flagstone + beams, `=` boards + beams, `,` grass + sky, `:` flagstone + sky. The generator checks that the border is solid and every open cell is reachable.

## Building and testing

Requirements: SDCC ≥ 4.2, devkitSMS (SMSlib), Python 3 with Pillow and NumPy.

```sh
make          # generates data, builds dungeon.sms
make test     # boot, pad-only walk into the courtyard, 11 pixel-exact view checks, benchmark
```

The tests run headlessly in `smstest`. They:
- compare emulator screenshots pixel-for-pixel with `tools/simrender.py`;
- drive the pad from the start cell into the courtyard;
- check step and bump sounds in the PSG log;
- assert that no VRAM write happens faster than the VDP allows during active display.

Not verified: real hardware, and PAL consoles. Nothing in the code depends on 60 Hz.
