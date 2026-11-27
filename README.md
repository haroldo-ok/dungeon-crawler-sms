# SMS Dungeon

A first-person, grid-based dungeon crawler for the **Sega Master System**.

**The quest:** recover the Lost Crown from the Lich King, three levels down.
- **The keep:** a hollow wall hides an iron key, and the key opens the locked door to the stairs.
- **The crypt:** a narrow stair leads from here down into the bone-walled catacombs.
- **The catacombs:** the Lich King waits behind a door at the far end.

Skeletons, giant bats, ghosts and giant spiders roam the levels, and you fight them in turn-based battles. Merchants sell better gear and run an inn. There is PSG music throughout, a title screen with an animated logo, and an ending. Progress is kept in battery-backed cartridge RAM.

- You move cell by cell, but every step, strafe and 90° turn is animated as a smooth glide or rotation. There are 6 in-between frames in *smooth* mode and 3 in *quick* mode.
- Walls, floor and ceiling are texture-mapped in real time from the live map.
- Any cell without a ceiling shows a scrolling sky panorama, so courtyards are open to the sky and roof edges look right.

`dungeon.sms` is a 512 KiB ROM using the standard Sega mapper. It runs in any SMS emulator (Emulicious, MEKA, Genesis Plus GX…) and should run on a flash cart.

## Controls

| Pad | Action |
|---|---|
| Up / Down | step forward / back |
| Left / Right | turn 90° |
| Button 1 (tap) | use the cell ahead: open doors, unlock with a key, find secret walls, take stairs, trade with the merchant, or start a fight |
| Button 1 + Left/Right | strafe |
| Button 2 | pause menu: MAP, ITEM, STATUS, SAVE |
| Left/Right while the map is open | toggle step mode (smooth 6 sub-steps / quick 4) |
| Up while the map is open | drink a potion |
| Any menu | Left/Right choose, 1 confirm, 2 back |

## Gameplay

- **Doors, locked doors and secret walls.** Doors open with button 1. Locked doors use up a key. Secret walls look exactly like stone, and a nearby message hints at them. Opened doors stay open when you change levels, because each level's live map is kept in RAM.
- **Cell events** are defined per level in `tools/gen.py`:
  - messages, shown once;
  - key pickups;
  - healing springs;
  - a teleporter;
  - stairs between the two 16×16 levels;
  - the winning cell.
- **Monsters.** Each roaming monster is a group of 1–3 skeletons, giant bats, ghosts or giant spiders. Groups wake within 7 cells and walk toward you, one step per action or about every 1.7 s while you wait. A group that reaches you starts a battle, and so does walking into one or pressing 1 at it. You always turn to face the group first.
- **Battles** are turn-based:
  - The current view stays as the backdrop, and the group is drawn large in front of it. Hit enemies flash white, and attacking ones change pose.
  - A zoomed hardware-sprite arrow picks the target.
  - Commands: **FIGHT**, **MAGIC** (HEAL 3 MP, FIRE 2 MP; ghosts take double from fire), **ITEM** (potion, +25 HP) and **RUN** (the group is then stunned for 4 turns).
  - Winning gives XP and gold, sometimes a potion, and level-ups (+6 HP, +3 MP, +2 attack, +1 defence, up to level 10). At 0 HP you fall, and button 1 restarts.
- **The Lich King** guards the crown at the far end of the catacombs. He waits in his chamber rather than roaming, can't be fled, and every other round casts Soul Fire, which armour only half blocks. Taking the crown starts the ending: your final level, foes slain, gold and steps, then THE END and back to the title.
- **Chests** (drawn in the world) hold potions and gold. Healing springs restore HP and MP.
- **Equipment.** Weapons are dagger, short sword (+2), long sword (+5) and battle axe (+9). Armour is cloth, leather (+2), chain mail (+4) and plate (+7). Each purchase is the next tier and is equipped at once.
- **Items.** Potions give +25 HP and ethers +12 MP. Both can be used in battle (ITEM) or from the pause menu.
- **Merchants** stand in the keep's courtyard and in the crypt. Press 1 facing him to buy the next weapon or armour (30/80/180 and 25/70/160 gold), potions (10) and ethers (25), or to rest at the inn (8 gold, full HP and MP).
- **Status screen.** Shows level, XP and next level, HP and MP, attack and defence including gear, equipment, and items.
- **Saving.** SAVE from the pause menu writes cartridge RAM, then reads it back and checks it. At power-on, a valid save offers CONTINUE or NEW GAME, and falling in battle continues from the last save. The save is the two live level maps plus a 205-byte state block, behind a magic header, length and checksum. It holds only ids and counters, never pointers.
- **Automap.** It's drawn into the view framebuffer, so it costs no extra tiles. It shows visited cells, the walls next to them, doors (brown), locked doors (cream), stairs (blue) and you (white, with a red mark on the side you face).
- **HUD.** Shows HP, MP, level, keys, potions, gold and the level name, plus a two-line message area that wraps automatically. During battles it becomes the battle panel.
- **Music.** Nine tunes: title, a theme for each level, battle, boss, a victory jingle, game over and the ending. Melody and bass run on PSG tone channels 1 and 2, stepped from the VBlank interrupt with a gentle decay envelope. Tunes are written as note text in `tools/music.py`, which compiles them to 716 bytes of note data.
- **Sound effects.** Footsteps, bumps, hits, taking damage, doors and pickups, on tone channel 0 and the noise channel, so they never cut the music.
- **Title screen.** A logo (generated from the font with an outline, gradient and shadow, stored as runs in a data bank) is stamped over a slow 360° turn in the keep's courtyard. It's rendered live with the normal engine.

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
4. **Billboards.** Monsters, chests and keys always stand at cell centres, and the camera only has the 22 poses, so each pose bank also holds a 17×15 table:
   - the table gives the screen column and depth of an object at the centre of each nearby cell;
   - at run time the object's cell offset is rotated into the pose's frame and looked up;
   - the sprite is then scaled column by column and depth-tested against the wall in each column, skipping transparent texels;
   - objects are drawn far-to-near;
   - scale classes decide size and height above the floor, so bats fly at eye level;
   - in battles the same drawer runs in a direct mode: fixed screen positions and sizes, no depth test.
5. **Flip in VBlank.** The VBlank interrupt re-points the 16×12 tiles of the view at the finished buffer, so the CPU starts the next frame immediately.

Textures are 32×32 for walls and 16×16 for floor and ceiling. Doors and stairs live in a second wall bank, drawn in a second pass that only runs when one is in view. Sprites are 32×32 with transparency, spread over three sprite banks. Skeleton, bat, ghost, spider and the Lich King each have idle, attack and hit-flash frames, and there are a key, a chest, a merchant and the crown. The catacombs use a fourth wall texture: dark stone with skull niches. There are pre-rotated copies for each facing, nibble-shifted copies so two pixels OR into one lookup index, and a darker variant for east/west faces.

`src/render.c` contains a plain-C reference version of every kernel. Building with `make DEFS=` uses it, and it renders the same pixels as the assembly.

### Speed (NTSC, measured in the bundled emulator)

| Scene | Rendered fps |
|---|---|
| corridor walk / turn | ~6.2 |
| wooden hall turn | ~5.7 |
| open courtyard turn | ~5.3 |

About half of each frame is the planar conversion and upload: 6 KiB of tile data at the VDP's paced write rate. Nothing is rendered while you stand still. A smooth step takes about 0.9 s, a quick step about 0.6 s.

## Layout

```
src/game.c        exploration: game loop, input, movement, events, monsters, HUD, sound (ROM bank 1)
src/battle.c      turn-based battles, stats, levelling, shared menu/message UI (bank 0)
src/menus.c       equipment, items, merchant shop + inn, status, pause menu, battery save (bank 0)
src/state.c       the persistent game state (own data segment at 0xDD00)
src/core.c        VBlank handler: buffer flip, input latch, music driver (bank 0)
src/render.c      renderer driver + C reference kernels
src/render_asm.s  Z80 kernels: cell setup, ray walk, floor/ceiling/sky, walls, c2p upload
src/engine.h      fixed RAM map, mapper macros
tools/gen.py      textures, levels, sprites, palette, HUD font, logos, pose tables -> gen/
tools/music.py    the tunes (note text) -> gen/music.c
tools/simrender.py  Python renderer that walks the same bank data (test oracle)
tools/mkrom.py    splices the generated banks into the ROM
tools/smstest/    local copy of the skill's test emulator + a `reset` command (RAM/SRAM kept)
tests/            harness scripts (boot, pad-only exploration, pixel-exact views, benchmark)
```

Levels are 16×16 grids in `tools/gen.py` (`LEVELS`), each with its event and object lists.
- Walls: `#` stone, `M` mossy, `W` wood, `H` hedge, `D` door, `L` locked door, `S` stairs, `X` secret wall.
- Open cells: `.` flagstone + stone ceiling, `-` flagstone + beams, `=` boards + beams, `,` grass + sky, `:` flagstone + sky.

The generator checks that each border is solid, every cell is reachable, and events and objects sit on valid cells.

## Building and testing

Requirements: SDCC ≥ 4.2, devkitSMS (SMSlib), Python 3 with Pillow and NumPy.

```sh
make          # generates data, builds dungeon.sms
make test     # boot, title screen, courtyard walk, the whole game start to
              # ending, battle mechanics, shop + save/continue (incl. console
              # reset), sound, 28 pixel-exact view checks, benchmark
```

The tests run headlessly in `smstest`. They:
- play the whole game using only the pad, through all three levels: secret wall → key → locked door → crypt → stairs → catacombs → boss door → Lich King → crown → ending → title. It uses path-finding for the catacombs and fights every monster on the route;
- check the title screen (logo over the turning view, title music, press 1 to start);
- buy a weapon, armour, a potion, an ether and a night at the inn. Then show the status screen, save, spoil the state, die and continue: everything comes back from cartridge RAM. Then reset the console and CONTINUE from the title;
- check battle mechanics at normal stats: two skeletons → victory, XP, gold and level-up; HEAL, potion and FIRE against bats; running away; defeat and restart;
- compare emulator screenshots pixel-for-pixel with `tools/simrender.py`, including billboards, occlusion, doors and stairs;
- drive the pad from the start cell into the courtyard;
- check step and bump sounds in the PSG log;
- assert that no VRAM write happens faster than the VDP allows during active display.

Not verified: real hardware, and PAL consoles. Nothing in the code depends on 60 Hz.

## Memory layout

RAM: the chunky framebuffer is at 0xC400. Per-frame tables and the live map are at 0xD400–0xDA7F. The three levels' saved maps are at 0xDB00–0xDDFF. The stack sits above 0xDE00 and was measured at under 100 bytes deep. The rest of the save is one contiguous block of C globals (`state.c`, from `state_begin` to `state_end`). The save writes the maps and that block as one checksummed stream. About 95 bytes of C globals are free.

ROM: 512 KiB.
- Banks 0–1: code.
- 2–3: floor and wall textures.
- 4–25: the 22 camera poses (ray tables, billboard tables, sprite scale classes).
- 26: doors, stairs and bone walls.
- 27–29: sprites.
- 30: the title and ending logos.

Rendering borrows the 0x4000 window (slot 1) for textures, and the VBlank handler can fire during rendering. So:
- **Bank 0:** the renderer, the handler (`core.c`), SMSlib, the battle and menu code, and the name tables the handler reads. Cartridge RAM is paged into slot 2 only while saving or loading, between frames.
- **ROM bank 1 (0x4000):** the exploration logic and its data. The renderer puts bank 1 back before it returns.

The build checks every limit (bank 0 and bank 1 code, the save block, RAM globals). About 5 KB is free in each code bank and about 450 bytes of RAM.

**Balance** was tuned with a Monte Carlo run of every battle in the game, including the boss, shopping and healing springs:

| Play style | Wins |
|---|---|
| Careful (heals at 40% HP) | 100%, finishing around level 9 |
| Reckless, with gear | 96% |
| Reckless, no gear | 43% (most losses at the Lich King) |

**Test hooks:** `0x5A17` at RAM 0xDAF0 skips the title screen, `dbg_level` jumps to a level, and `ai_off` freezes monsters. Tests use them; they do nothing in normal play.
