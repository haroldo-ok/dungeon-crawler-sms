# SMS Dungeon

A first-person, grid-based dungeon crawler for the **Sega Master System**.

**The quest:** recover the Lost Crown from the Lich King, four levels down. Each level has its own texture set (walls, doors, stairs, floors, ceilings and sky) and its own music.
- **The keep:** grey and mossy stone, timber halls, hedges and a sunny courtyard. A hollow wall hides an iron key, and the key opens the locked door to the stairs.
- **The crypt:** blue-grey ashlar, sealed tombs, stained-glass windows, iron gates, chequered marble and a cloister under a starry night sky.
- **The mines:** rough rock, timber shoring, crystal veins, lanterns and rail tunnels, with an old air shaft open to a dusk sky. A lever opens the way down, and a rock golem guards it.
- **The catacombs:** skull niches, piles of skulls and torches. The Lich King waits behind a stone door at the far end.

Skeletons, giant bats, ghosts, slimes, giant spiders, a rock golem and the Lich King roam the levels, and you fight them in turn-based battles. Merchants sell better gear and run an inn. There is PSG music throughout, a title screen with an animated logo, and an ending. Progress is kept in battery-backed cartridge RAM.

- You move cell by cell, but every step, strafe and 90° turn is animated as a smooth glide or rotation. There are 6 in-between frames in *smooth* mode and 3 in *quick* mode.
- Walls, floor and ceiling are texture-mapped in real time from the live map.
- Any cell without a ceiling shows a scrolling sky panorama, so courtyards are open to the sky and roof edges look right.

Everything the game is about (levels, texture sets, monsters, items, events, texts and music) is data in one file, `tools/content.py`. The C code runs that data, so adding content means editing data in the generator; see [Adding content](#adding-content).

`dungeon.sms` is a 1 MiB ROM using the standard Sega mapper. It runs in any SMS emulator (Emulicious, MEKA, Genesis Plus GX…) and should run on a flash cart.

## Controls

| Pad | Action |
|---|---|
| Up / Down | step forward / back |
| Left / Right | turn 90° |
| Button 1 (tap) | use the cell ahead: open doors, unlock with a key, find secret walls, take stairs, pull levers, trade with the merchant, or start a fight |
| Button 1 + Left/Right | strafe |
| Button 2 | pause menu: MAP, ITEM, STATUS, SAVE |
| Left/Right while the map is open | toggle step mode (smooth 6 sub-steps / quick 4) |
| Up while the map is open | drink a potion |
| Any menu | Left/Right choose, 1 confirm, 2 back |

## Gameplay

- **Doors, locked doors and secret walls.** Doors open with button 1. Locked doors use up a key. Secret walls look exactly like the level's main wall, and a nearby message hints at them. Opened walls stay open: each level keeps a 32-byte bitmap of opened cells, and its map is rebuilt from ROM plus those bits.
- **Events** are small scripts on a cell, written in `tools/content.py`. On an open cell they run when you step there. On a wall cell (stairs, a lever) they run when you walk into it or press 1 at it. They are built from messages, items, keys, gold, healing, teleports, stairs, removing the object on the cell, opening a wall anywhere on the level, sounds and winning. Chests, keys, springs, the cloister teleporter, the mine lever and the crown are all just events.
- **Monsters.** Each roaming monster is a group of 1–3 of one kind. Groups wake within 7 cells and walk toward you, one step per action or about every 1.7 s while you wait. A group that reaches you starts a battle, and so does walking into one or pressing 1 at it. You always turn to face the group first.
- **Battles** are turn-based:
  - The current view stays as the backdrop, and the group is drawn large in front of it. Hit enemies flash white, and attacking ones change pose.
  - A zoomed hardware-sprite arrow picks the target.
  - Commands: **FIGHT**, **MAGIC** (HEAL 3 MP, FIRE 2 MP; ghosts and slimes take double from fire), **ITEM** (any potion) and **RUN** (the group is then stunned for 4 turns).
  - Some monsters have a special attack every few rounds: slimes spit acid that ignores armour, the golem hurls boulders, the Lich King casts Soul Fire. Armour only half blocks the last two.
  - Winning gives XP and gold, sometimes a potion, and level-ups (+6 HP, +3 MP, +2 attack, +1 defence, up to level 12). At 0 HP you fall, and button 1 restarts.
- **Bosses.** The rock golem and the Lich King wait in place rather than roaming, can't be fled, and get the boss music. Taking the crown from the Lich King's chamber starts the ending: your final level, foes slain, gold and steps, then THE END and back to the title.
- **Chests** (drawn in the world) hold potions and gold. Healing springs restore HP and MP.
- **Equipment.** Weapons are dagger, short sword (+2), long sword (+5), battle axe (+9) and rune blade (+13). Armour is cloth, leather (+2), chain mail (+4), plate (+7) and mithril (+10). Each purchase is the next tier and is equipped at once.
- **Items.** Potions give +25 HP, ethers +12 MP, and elixirs restore everything. All can be used in battle (ITEM) or from the pause menu.
- **Merchants** stand in the keep, the crypt and the mines, and each has its own stock and inn price. The keep and crypt sell up to the battle axe and plate (30/80/180 and 25/70/160 gold), potions (10) and ethers (25). The mines merchant also has the rune blade (320), mithril (300) and elixirs (70).
- **Status screen.** Shows level, XP and next level, HP and MP, attack and defence including gear, equipment, and items.
- **Saving.** SAVE from the pause menu writes cartridge RAM, then reads it back and checks it. At power-on, a valid save offers CONTINUE or NEW GAME, and falling in battle continues from the last save. The save is the per-level visited and opened bitmaps (256 bytes) plus a state block of about 300 bytes, behind a magic header, length and checksum. It holds only ids and counters, never pointers.
- **Automap.** It's drawn into the view framebuffer, so it costs no extra tiles. It shows visited cells in their floor's colour, the walls next to them, doors (brown), locked doors (cream), stairs (blue) and you (white, with a red mark on the side you face).
- **HUD.** Shows HP, MP, level, keys, each kind of potion, gold and the level name, plus a two-line message area that wraps automatically. During battles it becomes the battle panel.
- **Music.** Ten tunes: title, a theme for each level, battle, boss, a victory jingle, game over and the ending. Melody and bass run on PSG tone channels 1 and 2, stepped from the VBlank interrupt with a gentle decay envelope. Tunes are note text in `tools/content.py`; `tools/music.py` compiles them to 908 bytes of note data.
- **Sound effects.** Footsteps, bumps, hits, taking damage, doors and pickups, on tone channel 0 and the noise channel, so they never cut the music.
- **Title screen.** A logo (generated from the font with an outline, gradient and shadow, stored as runs in a data bank) is stamped over a slow 360° turn in the keep's courtyard. It's rendered live with the normal engine.

## Adding content

All content is in `tools/content.py`, and `tools/gen.py` compiles it into ROM banks and C tables. Nothing in `src/` names a level, monster, item or event.

| To add | Edit in `tools/content.py` |
|---|---|
| a level | a `LEVELS` entry: id, name, texture set, song, 16×16 map, events, objects and the merchant's stock. Link it with a `STAIRS` event from another level. |
| a texture set | a `THEMES` entry: up to 4 wall textures (each gets a map character), door, locked door and stairs textures, an optional extra wall (the mines' lever), up to 5 floor/ceiling textures, a sky, and which map characters are open cells with which floor and ceiling (or open sky). |
| a monster | a `MONSTERS` entry: two sprite frames (the hit flash is generated), a size class, HP/attack/defence/XP/gold, flee chance, weak to fire, boss, an optional special attack, and its texts. |
| an item | a row in `WEAPONS` or `ARMORS`, or an entry in `CONSUMABLES` (up to 3), then add it to a shop's stock or a chest. |
| an event | an entry in a level's `events`: a cell, `once`, and a list of actions (`MSG`, `ITEM`, `KEYS`, `GOLD`, `HEAL`, `TELE`, `STAIRS`, `TAKE`, `OPEN`, `SOUND`, `WIN`). Helpers make the common ones one line: `msg`, `chest`, `stairs`, `spring`. |
| art | paint it with the functions in `tools/art.py`, or load a PNG with `load_png()` (walls and sprites 32×32, floors 16×16, skies 64×24; magenta is transparent). |

The generator checks content before it builds and names the level, monster or event at fault:
- each map is 16×16 with a solid border, uses only its texture set's characters, and every open cell is reachable from where you arrive (doors, secret walls and walls opened by events count as passable);
- events and objects sit on valid cells, stairs and teleports land in open cells of a real level, every stair has an event, `TAKE` has an object to take;
- every message, and every battle message a monster's name and texts produce, fits the two-line message box and the font;
- texture sizes, the limits of a texture set, group sizes, menu widths, and the bank, sprite, event and level budgets.

```sh
make check          # validate content + run the balance simulator, without building
python3 tools/balance.py 5000
```

`tests/demo_garden.py` is a worked example. It adds a fifth level (a roof garden up a new stair in the keep) with its own texture set, a new monster, a new weapon sold by a merchant there, and a chest, all as data on top of `content.py`. `make test` builds a ROM from it in a scratch directory, climbs the stair, checks the view pixel for pixel, and buys the new weapon.

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
src/state.c       the persistent game state (one contiguous block of globals)
src/core.c        VBlank handler: buffer flip, input latch, music driver (bank 0)
src/render.c      renderer driver + C reference kernels
src/render_asm.s  Z80 kernels: cell setup, ray walk, floor/ceiling/sky, walls, c2p upload
src/engine.h      fixed RAM map, mapper macros
tools/content.py  ALL game content: texture sets, levels, monsters, items, events, texts, music
tools/art.py      the palette and the procedural texture / sprite painters (+ PNG loader)
tools/gen.py      checks content.py and compiles it, plus pose tables, HUD font, logos -> gen/
tools/music.py    compiles the tunes -> gen/music.c
tools/balance.py  Monte Carlo of every battle on the way, for three play styles
tools/simrender.py  Python renderer that walks the same bank data (test oracle)
tools/mkrom.py    splices the generated banks into the ROM
tools/smstest/    local copy of the skill's test emulator + a `reset` command (RAM/SRAM kept)
tests/            harness scripts (boot, pad-only exploration, pixel-exact views, benchmark)
```

Map characters come from each level's texture set, plus `D` door, `L` locked door, `S` stairs and `X` secret wall everywhere.

## Building and testing

Requirements: SDCC ≥ 4.2, devkitSMS (SMSlib), Python 3 with Pillow and NumPy.

```sh
make          # generates data, builds dungeon.sms
make check    # content validation + balance simulation (no build)
make test     # content checks, boot, title screen, courtyard walk, the whole
              # game start to ending, battle mechanics, shop + save/continue
              # (incl. console reset), sound, 36 pixel-exact view checks,
              # benchmark, and a ROM built from new content (demo_garden)
```

The tests run headlessly in `smstest`. They:
- check the content compiler: ten kinds of broken content are rejected with the right message, and the demo level, monster and weapon are accepted;
- play the whole game using only the pad, through all four levels: secret wall → key → locked door → crypt → stairs → mines → lever → rock golem → catacombs → boss door → Lich King → crown → ending → title. It reads the maps and monsters from `content.py`, uses path-finding, and fights every monster on the route;
- check the title screen (logo over the turning view, title music, press 1 to start);
- buy a weapon, armour, a potion, an ether and a night at the inn. Then show the status screen, save, spoil the state, die and continue: everything comes back from cartridge RAM. Then reset the console and CONTINUE from the title;
- check battle mechanics at normal stats: two skeletons → victory, XP, gold and level-up; HEAL, potion and FIRE against bats; running away; defeat and restart;
- compare emulator screenshots pixel-for-pixel with `tools/simrender.py`, including billboards, occlusion, doors and stairs, and views in every texture set (crypt cloister, window and gate; mines tunnel, shaft, lever and crystals; catacomb corridors) and the slime and Lich battles;
- drive the pad from the start cell into the courtyard;
- check step and bump sounds in the PSG log;
- assert that no VRAM write happens faster than the VDP allows during active display.

Not verified: real hardware, and PAL consoles. Nothing in the code depends on 60 Hz.

## Memory layout

RAM: the chunky framebuffer is at 0xC400. Per-frame tables and the live map are at 0xD400–0xDA7F. The level state (a visited bitmap and an opened-cells bitmap per level, 64 bytes each) starts at 0xDB00. The stack sits above 0xDE00 and was measured at under 100 bytes deep. The rest of the save is one contiguous block of C globals (`state.c`, from `state_begin` to `state_end`). The save writes the level state and that block as one checksummed stream. About 110 bytes of C globals are free.

ROM: 1 MiB (41 of 64 banks used). The layout is computed by the generator from the content:
- Banks 0–1: code.
- 2–23: the 22 camera poses (ray tables, billboard tables, sprite scale classes).
- 24–27: sprites, 8 frames per bank.
- 28: the title and ending logos, and the level maps (read only when a level is loaded).
- 29 on: three banks per texture set: floor/ceiling/sky (with the chunky-to-planar table), walls, and doors/stairs/extra.

Rendering borrows the 0x4000 window (slot 1) for textures, and the VBlank handler can fire during rendering. So:
- **Bank 0:** the renderer, the handler (`core.c`), SMSlib, the battle and menu code, and the name tables the handler reads. Cartridge RAM is paged into slot 2 only while saving or loading, between frames.
- **ROM bank 1 (0x4000):** the exploration logic and the content tables. The renderer puts bank 1 back before it returns.

The build checks every limit (bank 0 and bank 1 code, the save block, RAM globals). About 2.8 KB is free in bank 0 and 1.5 KB in bank 1. A new level costs ROM only (its map goes in the data bank, its texture set in new banks), plus 64 bytes of RAM, up to 12 levels.

**Balance** comes from `tools/balance.py`, which plays every chest, merchant, spring and monster group on the way, with the same battle rules as `battle.c` (3,000 runs per style):

| Play style | Wins | Notes |
|---|---|---|
| Careful (heals at 40% HP, rests at springs) | 100% | meets the golem at level 6 and the Lich King at level 8 |
| Reckless, with gear | 91% | most losses at the Lich King |
| Reckless, no gear | 9% | the bosses and early skeleton packs stop it |

**Test hooks:** `0x5A17` at RAM 0xDAF0 skips the title screen, `dbg_level` jumps to a level, and `ai_off` freezes monsters. Tests use them; they do nothing in normal play.
