"""
SMS Dungeon - all game content, as data.

tools/gen.py turns this file into ROM banks and C tables; nothing here needs a
matching code change.  To add content:

  * a level      -> add a texture set to THEMES (or reuse one), a song to SONGS,
                    and an entry to LEVELS; link it with STAIRS events.
  * a monster    -> add an entry to MONSTERS (sprite, size, stats, texts) and
                    place it in a level's "objects".
  * an item      -> add to WEAPONS / ARMORS / CONSUMABLES and to a shop's stock
                    or a chest.
  * an event     -> add to a level's "events" (helpers below, or a raw dict
                    with a list of actions).

`python3 tools/gen.py --check` validates everything (map reachability, event
targets, message widths, bank and RAM budgets) without building, and
tools/balance.py simulates every battle on the critical path.

Art: textures and sprites are numpy arrays of palette indices, painted by the
functions in tools/art.py, or loaded from PNGs with load_png("file.png")
(walls and sprites 32x32, floors/ceilings 16x16, skies 64x24; magenta is
transparent in sprites).
"""
from art import *

# ============================================================================ texture sets
# A theme is the look of a level.  Its textures go into three ROM banks:
#   walls   map char -> 32x32 texture, up to 4.  The first is also what a
#           secret wall ('X') looks like.
#   door, locked, stairs   textures for 'D', 'L', 'S'
#   extra   optional (char, texture): one more wall type
#   flats   name -> 16x16 floor/ceiling texture, up to 5
#   opens   map char -> (floor flat, ceiling flat or None = open sky);
#           at most 4 different floors and 3 different ceilings
#   sky     64x24 sky (one 90 degree period), seen where a cell has no ceiling
#   open_as the open char a door / secret wall turns into once opened
THEMES = {
    "KEEP": dict(
        walls={'#': tex_bricks([DGRAY, GRAY, GRAY, GRAY, WHITE], BLACK, 1),
               'M': tex_bricks([DGRAY, KHAKI, GRAY], BLACK, 2, moss=[DGREEN, GREEN, LGREEN]),
               'W': tex_planks(),
               'H': tex_hedge()},
        door=tex_door(False), locked=tex_door(True), stairs=tex_stairs(),
        flats={"flag": tex_flag(5), "grass": tex_grass(), "boards": tex_boards(),
               "beams": tex_beams(), "stone": tex_ceilstone()},
        opens={'.': ("flag", "stone"), ',': ("grass", None), ':': ("flag", None),
               '=': ("boards", "beams"), '-': ("flag", "beams")},
        sky=tex_sky(), open_as='.'),
    "CRYPT": dict(
        walls={'#': tex_ashlar(), 'M': tex_tomb(), 'W': tex_window()},
        door=tex_gate(), locked=tex_gate_locked(), stairs=tex_stairs(tex_ashlar(26), (GRAY, DGRAY)),
        flats={"marble": tex_marble(), "vault": tex_vault(), "flag": tex_darkflag()},
        opens={'.': ("marble", "vault"), ':': ("flag", None)},
        sky=tex_night_sky(), open_as='.'),
    "MINES": dict(
        walls={'#': tex_rock(), 'T': tex_shored(), 'C': tex_crystal(), 'O': tex_lantern()},
        door=tex_mine_door(), locked=tex_mine_door(True), stairs=tex_stairs(tex_rock(38), (TAN, BROWN)),
        extra=('V', tex_lever()),
        flats={"dirt": tex_dirt(), "rails": tex_rails(), "rock": tex_rock_ceil(), "beams": tex_beams()},
        opens={'.': ("dirt", "rock"), ',': ("dirt", None), '=': ("rails", "beams"), ':': ("rails", "rock")},
        sky=tex_dusk_sky(), open_as='.'),
    "CATACOMBS": dict(
        walls={'#': tex_catastone(), 'K': tex_bones(), 'T': tex_torch(), 'P': tex_skullpile()},
        door=tex_slab_door(), locked=tex_slab_door(True), stairs=tex_stairs(tex_catastone(), (KHAKI, DGRAY)),
        flats={"bones": tex_bone_floor(), "low": tex_low_ceil()},
        opens={'.': ("bones", "low")},
        sky=tex_night_sky(), open_as='.'),
}

# ============================================================================ sprites
# billboard sizes: (height in world units, height of its bottom above the floor); at most 5
SIZES = {"standing": (0.85, 0.0), "small": (0.45, 0.0), "flying": (0.75, 0.22),
         "low": (0.55, 0.0), "huge": (1.05, 0.0)}

# ============================================================================ monsters
# sprite: (idle, attack) - a white hit-flash frame is made from the idle one.
# hp/atk/df per enemy; xp/gold per enemy on victory; run = % chance to flee
# (0 = no escape).  boss: waits in place until you are next to it and plays the
# boss music.  fire_weak: FIRE does double damage.  spell: a special attack
# every N rounds, armour counts fully / half / not at all.
# Texts: "<group> 3 <plural>!" when a group appears, attack = message when it
# reaches you while exploring, death = shown after "THE <NAME>".
MONSTERS = {
    "SKEL": dict(name="SKELETON", plural="SKELETONS", group="A PACK OF",
                 sprite=(spr_skeleton(0), spr_skeleton(1)), size="standing",
                 hp=10, atk=6, df=2, xp=9, gold=6, run=60,
                 attack="A SKELETON ATTACKS!", death=" CRUMBLES!"),
    "BAT": dict(name="GIANT BAT", plural="GIANT BATS", group="A SWARM OF",
                sprite=(spr_bat(0), spr_bat(1)), size="flying",
                hp=6, atk=5, df=0, xp=4, gold=2, run=40,
                attack="BATS SWOOP DOWN ON YOU!", death=" FALLS!"),
    "GHOST": dict(name="GHOST", plural="GHOSTS", group="A PACK OF",
                  sprite=(spr_ghost(0), spr_ghost(1)), size="standing",
                  hp=22, atk=10, df=6, xp=24, gold=14, run=50, fire_weak=True,
                  attack="A GHOST DRIFTS AT YOU!", death=" FADES AWAY!"),
    "SLIME": dict(name="SLIME", plural="SLIMES", group="A HEAVING MASS OF",
                  sprite=(spr_slime(0), spr_slime(1)), size="low",
                  hp=14, atk=8, df=1, xp=12, gold=5, run=70, fire_weak=True,
                  spell=dict(every=3, dmg=6, rnd=4, armor="none", text="SPITS ACID|FOR"),
                  attack="A SLIME OOZES TOWARD YOU!", death=" DISSOLVES!"),
    "GOLEM": dict(name="ROCK GOLEM", plural="ROCK GOLEMS", group="A WALL OF",
                  sprite=(spr_golem(0), spr_golem(1)), size="huge",
                  hp=90, atk=15, df=10, xp=90, gold=60, run=0, boss=True,
                  spell=dict(every=3, dmg=14, rnd=6, armor="half", text="HURLS A|BOULDER FOR"),
                  attack="THE ROCK GOLEM STIRS!", death=" CRUMBLES TO GRAVEL!"),
    "SPIDER": dict(name="SPIDER", plural="SPIDERS", group="A NEST OF",
                   sprite=(spr_spider(0), spr_spider(1)), size="low",
                   hp=16, atk=10, df=3, xp=15, gold=8, run=50,
                   attack="SPIDERS DROP FROM ABOVE!", death=" FALLS!"),
    "LICH": dict(name="LICH KING", plural="LICH KINGS", group="A COVEN OF",
                 sprite=(spr_lich(0), spr_lich(1)), size="huge",
                 hp=180, atk=20, df=11, xp=200, gold=0, run=0, boss=True,
                 spell=dict(every=2, dmg=18, rnd=8, armor="half", text="CASTS SOUL|FIRE FOR"),
                 attack="THE LICH KING RISES!", death=" TURNS TO DUST!"),
}

# things in the world that are not monsters
# blocks: you can't walk through it.  shop: button 1 opens the level's shop.
PROPS = {
    "KEY": dict(sprite=spr_key(), size="small"),
    "CHEST": dict(sprite=spr_chest(), size="low"),
    "MERCHANT": dict(sprite=spr_merchant(), size="standing", blocks=True, shop=True,
                     bump="THE MERCHANT SMILES.|PRESS 1 TO TRADE"),
    "CROWN": dict(sprite=spr_crown(), size="small"),
}

# ============================================================================ items
# weapons / armour: (name, bonus, price); index 0 is what you start with.
# A shop sells the next one up, as far as its stock allows.
WEAPONS = [("DAGGER", 0, 0), ("SHORT SWORD", 2, 30), ("LONG SWORD", 5, 80),
           ("BATTLE AXE", 9, 180), ("RUNE BLADE", 13, 320)]
ARMORS = [("CLOTH", 0, 0), ("LEATHER", 2, 25), ("CHAIN MAIL", 4, 70),
          ("PLATE", 7, 160), ("MITHRIL", 10, 300)]
# consumables (at most 3): hp/mp restored (99 = all), hud = 3-letter HUD label
CONSUMABLES = {
    "POTION": dict(hud="POT", hp=25, mp=0, price=10, start=1, sound="PICKUP",
                   use="YOU DRINK A POTION.|+25 HP"),
    "ETHER": dict(hud="ETH", hp=0, mp=12, price=25, start=0, sound="MAGIC",
                  use="YOU DRINK AN ETHER.|+12 MP"),
    "ELIXIR": dict(hud="ELX", hp=99, mp=99, price=70, start=0, sound="MAGIC",
                   use="THE ELIXIR RESTORES BODY|AND MIND"),
}

# after a won battle there is a 1 in `one_in` chance of finding one of these
LOOT = dict(item="POTION", one_in=3)

# ============================================================================ the hero
PLAYER = dict(hp=24, mp=6, atk=6, df=2, keys=0,
              per_level=dict(hp=6, mp=3, atk=2, df=1),
              next_xp=[15, 40, 80, 140, 220, 320, 450, 600, 800, 1000, 1250],   # to reach level 2, 3, ...
              heal=dict(mp=3, base=12, per_level=3),            # spells
              fire=dict(mp=2, base=7, per_level=2))

# ============================================================================ events
# An event sits on a cell.  On an open cell it runs when you step there; on a
# wall cell (stairs, a lever) when you walk into it or press 1 facing it.
# once=True events run a single time.  Actions:
#   ("MSG", text)               show a message ('|' = line break)
#   ("ITEM", id, n)             give n of a consumable
#   ("KEYS", n)  ("GOLD", n)    give keys / gold
#   ("HEAL",)                   restore HP and MP
#   ("TELE", x, y, facing)      move on this level
#   ("STAIRS", level, x, y, f)  go to another level (by its id)
#   ("TAKE",)                   remove the object standing on this cell
#   ("OPEN", x, y)              open a wall cell on this level (remembered)
#   ("SOUND", "PICKUP"|"DOOR"|"MAGIC")
#   ("WIN",)                    the quest is complete: the ending follows
# facing: 0 north, 1 east, 2 south, 3 west
def msg(x, y, text, once=True):
    return dict(at=(x, y), once=once, do=[("MSG", text)])


def chest(x, y, text, gold=0, **items):
    acts = [("ITEM", k, n) for k, n in items.items()] + ([("GOLD", gold)] if gold else [])
    return dict(at=(x, y), once=True, do=acts + [("TAKE",), ("MSG", text), ("SOUND", "PICKUP")])


def stairs(x, y, level, ax, ay, af, text):
    return dict(at=(x, y), once=False, do=[("STAIRS", level, ax, ay, af), ("MSG", text), ("SOUND", "DOOR")])


def spring(x, y, text):
    return dict(at=(x, y), once=False, do=[("HEAL",), ("MSG", text), ("SOUND", "PICKUP")])


# ============================================================================ levels
# map: 16x16.  Wall chars come from the theme, plus 'D' door, 'L' locked door
# (needs a key), 'S' stairs, 'X' secret wall (press 1 to open).
# objects: (kind, x, y, n) - n = group size for monsters (1-3).
# shop: what a merchant on this level sells.
LEVELS = [
    dict(id="KEEP", name="THE KEEP", theme="KEEP", music="KEEP",
         map=["################",
              "#.....#=====W..#",
              "#.###.#=WW==W..#",
              "#.#.#.#=W===W..#",
              "#.#...--=W=WW..#",
              "#.####.#=W=..X##",
              "#......M,,,,MWW#",
              "###DMM,,,,,,,MW#",
              "#...H,,HH,,,,H.#",
              "#.#.M,,,,::,,M.#",
              "#.#.MM,,,::,MM.#",
              "#.#..........#.#",
              "#.###.###.####.#",
              "#...#...#....#.#",
              "#.#...#...##..L#",
              "##############S#"],
         events=[msg(1, 3, "STAIRS LIE BEHIND A LOCKED|DOOR IN THE SOUTH EAST"),
                 msg(12, 5, "THE EAST WALL SOUNDS|HOLLOW. TRY BUTTON 1"),
                 dict(at=(14, 1), once=True, do=[("KEYS", 1), ("TAKE",), ("MSG", "YOU FOUND AN IRON KEY!"),
                                                 ("SOUND", "PICKUP")]),
                 spring(8, 9, "A COOL SPRING. YOU FEEL|REFRESHED"),
                 chest(3, 3, "A CHEST! 2 POTIONS|AND 15 GOLD", gold=15, POTION=2),
                 chest(14, 12, "A CHEST! A POTION|AND 40 GOLD", gold=40, POTION=1),
                 stairs(14, 15, "CRYPT", 14, 14, 0, "YOU DESCEND INTO THE|CRYPT...")],
         objects=[("KEY", 14, 1, 1), ("CHEST", 3, 3, 1), ("CHEST", 14, 12, 1),
                  ("SKEL", 6, 13, 1), ("SKEL", 11, 11, 2), ("BAT", 1, 10, 2), ("BAT", 10, 7, 3),
                  ("SKEL", 13, 2, 1), ("MERCHANT", 12, 9, 1)],
         shop=dict(weapons=3, armors=3, goods=["POTION", "ETHER"], inn=8)),
    dict(id="CRYPT", name="THE CRYPT", theme="CRYPT", music="CRYPT",
         map=["####W######W####",
              "#......#.......#",
              "#.####.#.###S#.#",
              "#.#....#.#...#.#",
              "#.#.####.#.#.#.#",
              "#.#......D.#...#",
              "#.########.#####",
              "#....M::::.....#",
              "####.M::::.###.#",
              "#....M::::.#...#",
              "#.##.MMMMMM#.#.#",
              "#.#........#.#.#",
              "#.#.######.#.#.#",
              "#.#......#...#.#",
              "#...####.#####.#",
              "####W#########S#"],
         events=[msg(14, 13, "THE AIR IS COLD AND STILL"),
                 dict(at=(1, 13), once=False, do=[("TELE", 8, 1, 1), ("MSG", "A SHIMMERING LIGHT CARRIES|YOU AWAY!"),
                                                  ("SOUND", "DOOR")]),
                 stairs(12, 2, "MINES", 1, 1, 2, "A NARROW STAIR WINDS DOWN|INTO THE OLD MINES..."),
                 msg(12, 3, "A WARM DRAUGHT RISES FROM|THE STAIRS TO THE NORTH"),
                 spring(7, 8, "MOONLIGHT HEALS YOUR|WOUNDS"),
                 chest(1, 7, "A CHEST! 3 POTIONS|AND 60 GOLD", gold=60, POTION=3),
                 chest(12, 9, "A CHEST! A POTION|AND 90 GOLD", gold=90, POTION=1),
                 stairs(14, 15, "KEEP", 14, 14, 0, "YOU CLIMB BACK TO THE KEEP")],
         objects=[("CHEST", 1, 7, 1), ("CHEST", 12, 9, 1), ("MERCHANT", 13, 9, 1),
                  ("GHOST", 13, 7, 1), ("GHOST", 3, 11, 2), ("SKEL", 6, 1, 2), ("BAT", 14, 4, 3),
                  ("SKEL", 8, 13, 2), ("GHOST", 10, 3, 1)],
         shop=dict(weapons=3, armors=3, goods=["POTION", "ETHER"], inn=12)),
    dict(id="MINES", name="THE MINES", theme="MINES", music="MINES",
         map=["#S##############",
              "#...#=======...#",
              "#.#.#.#####T#..#",
              "#.#...#...#.#O.#",
              "#.###.#.#.#.#..#",
              "#...#...#...C..#",
              "###.#####T###.##",
              "#...O,,,,,,#...#",
              "#.#.#,,,,,,..#.#",
              "#.#..,,,,,,#.#.#",
              "#.####,,,,,#.#.#",
              "#......:::::.T.#",
              "#V#.###C##C###.#",
              "#...#.......#..#",
              "##T###.....T#..#",
              "######S#########"],
         events=[msg(1, 1, "THE AIR SMELLS OF DUST|AND OLD LAMP OIL"),
                 stairs(1, 0, "CRYPT", 12, 3, 2, "YOU CLIMB BACK TO THE CRYPT"),
                 msg(8, 9, "DUSK LIGHT FALLS DOWN AN|OLD AIR SHAFT"),
                 msg(3, 11, "A RUSTY LEVER IS SET IN|THE WALL TO THE WEST"),
                 dict(at=(1, 12), once=True, do=[("OPEN", 4, 13), ("MSG", "THE LEVER GROANS. ROCK|GRINDS ASIDE NEARBY!"),
                                                 ("SOUND", "DOOR")]),
                 msg(3, 13, "COLD AIR FLOWS FROM THE|NEW PASSAGE"),
                 chest(14, 3, "A CHEST! 2 ETHERS|AND 70 GOLD", gold=70, ETHER=2),
                 chest(2, 13, "A CHEST! AN ELIXIR|AND 50 GOLD", gold=50, ELIXIR=1),
                 spring(14, 14, "AN UNDERGROUND SPRING.|YOU FEEL RESTORED"),
                 stairs(6, 15, "CATACOMBS", 13, 13, 3, "STEPS CUT IN THE ROCK|LEAD DOWN TO THE DEAD...")],
         objects=[("MERCHANT", 13, 13, 1), ("GOLEM", 5, 13, 1), ("CHEST", 14, 3, 1), ("CHEST", 2, 13, 1),
                  ("SLIME", 7, 3, 2), ("SLIME", 9, 8, 3), ("SLIME", 1, 9, 1), ("BAT", 14, 8, 2),
                  ("SPIDER", 10, 1, 1)],
         shop=dict(weapons=4, armors=4, goods=["POTION", "ETHER", "ELIXIR"], inn=16)),
    dict(id="CATACOMBS", name="CATACOMBS", theme="CATACOMBS", music="CATACOMBS",
         map=["################",
              "#...K.....K....#",
              "#...D.KKK.T.KK.#",
              "#...K.K...K..K.#",
              "#KKKK.K.KKPKK..#",
              "#.....T.....K..#",
              "#.KKK.KKKKK.K.K#",
              "#.K.K.....K.T..#",
              "#.K.KKPKK.K.KK.#",
              "#...K...K.K....#",
              "#KK.T.K.K.KKPK.#",
              "#...K.K...K....#",
              "#.KKK.KPK.T.KK.#",
              "#.....K....K...#",
              "#.KKKKTKKKKK.S.#",
              "################"],
         events=[msg(13, 13, "BONES LINE THE WALLS.|SOMETHING WATCHES YOU"),
                 stairs(13, 14, "MINES", 6, 14, 0, "YOU CLIMB BACK TO THE MINES"),
                 spring(9, 9, "A BLESSED FONT. YOUR|STRENGTH RETURNS"),
                 chest(3, 9, "A CHEST! 2 POTIONS|AND 120 GOLD", gold=120, POTION=2),
                 chest(14, 3, "A CHEST! 3 POTIONS|AND 80 GOLD", gold=80, POTION=3),
                 msg(5, 2, "AN ICY VOICE: TURN BACK,|MORTAL. THE CROWN IS MINE"),
                 dict(at=(1, 2), once=True, do=[("TAKE",), ("MSG", "THE LOST CROWN IS YOURS!"),
                                                ("SOUND", "PICKUP"), ("WIN",)])],
         objects=[("CROWN", 1, 2, 1), ("LICH", 2, 2, 1), ("CHEST", 3, 9, 1), ("CHEST", 14, 3, 1),
                  ("SPIDER", 13, 9, 2), ("SPIDER", 5, 11, 3), ("SPIDER", 9, 1, 2),
                  ("GHOST", 1, 13, 2), ("SKEL", 9, 5, 3), ("SKEL", 3, 7, 2), ("BAT", 14, 5, 3)]),
]
START = ("KEEP", 1, 1, 2)            # level id, x, y, facing

# ============================================================================ texts
TEXT = dict(
    title="THE LOST CROWN",                       # under the logo (centred, up to 26 chars)
    tagline="A SEGA MASTER SYSTEM QUEST",
    intro="FIND THE LOST CROWN|DEEP BELOW THE KEEP",
    ending=["THE LOST CROWN IS YOURS!", "THE LICH KING IS NO MORE.|THE KEEP IS SAFE AT LAST",
            "THANK YOU FOR PLAYING!"],
)

# ============================================================================ music
# (name, frames per tick, loops, melody, bass).  Notes "C#4:4" = pitch:ticks,
# "r:4" = rest, '|' is only for reading.  Lowest note A2.  Each level names its
# song; TITLE, BATTLE, BOSS, VICTORY, GAMEOVER and ENDING are used by the game.
SONGS = [
    ("TITLE", 7, True,
     "A4:4 C5:2 E5:2 A5:6 G5:2 | E5:4 D5:2 C5:2 D5:8 | C5:4 D5:2 E5:2 F5:4 E5:2 D5:2 | E5:12 r:4 |"
     "A4:4 C5:2 E5:2 A5:6 B5:2 | C6:4 B5:2 A5:2 G5:8 | F5:4 E5:2 D5:2 E5:4 G#5:4 | A5:12 r:4",
     "A3:4 E3:4 A3:4 E3:4 | G3:4 D3:4 G3:4 D3:4 | F3:4 C3:4 G3:4 D3:4 | E3:4 B2:4 E3:4 G#3:4 |"
     "A3:4 E3:4 A3:4 E3:4 | C3:4 G3:4 E3:4 G3:4 | D3:4 A3:4 E3:4 E3:4 | A2:4 E3:4 A3:8"),
    ("KEEP", 9, True,
     "D4:6 F4:2 A4:8 | G4:4 F4:4 E4:8 | D4:6 F4:2 A4:4 C5:4 | B4:8 A4:8 |"
     "G4:6 A4:2 B4:4 A4:4 | G4:4 F4:4 E4:8 | F4:4 E4:4 D4:4 C4:4 | D4:12 r:4",
     "D3:8 A3:8 | C3:8 G3:8 | D3:8 A3:8 | G3:8 A3:8 |"
     "E3:8 B3:8 | C3:8 A2:8 | B2:8 A2:8 | D3:16"),
    ("CRYPT", 11, True,
     "E4:8 r:4 G4:4 | F#4:8 r:8 | E4:4 D#4:4 E4:4 B4:4 | A4:12 r:4 |"
     "G4:8 r:4 B4:4 | C5:8 B4:8 | A4:4 G4:4 F#4:4 D#4:4 | E4:12 r:4",
     "E3:16 | D#3:16 | E3:16 | C3:16 | E3:16 | A2:16 | B2:16 | E3:16"),
    ("MINES", 8, True,
     "D4:2 r:2 D4:2 F4:2 G4:4 A4:4 | C5:2 A4:2 G4:4 F4:4 r:4 | D4:2 r:2 D4:2 F4:2 G4:4 B4:4 | A4:12 r:4 |"
     "A4:2 r:2 A4:2 C5:2 D5:4 C5:4 | A4:2 G4:2 F4:4 G4:4 r:4 | F4:4 E4:4 D4:4 C4:4 | D4:12 r:4",
     "D3:2 r:2 A2:2 r:2 D3:2 r:2 A2:2 r:2 | F3:2 r:2 C3:2 r:2 F3:2 r:2 C3:2 r:2 |"
     "G3:2 r:2 D3:2 r:2 G3:2 r:2 D3:2 r:2 | A2:2 r:2 E3:2 r:2 A2:2 r:2 C#3:2 r:2 |"
     "D3:2 r:2 A2:2 r:2 D3:2 r:2 A2:2 r:2 | F3:2 r:2 C3:2 r:2 G3:2 r:2 D3:2 r:2 |"
     "B2:2 r:2 F3:2 r:2 C3:2 r:2 G3:2 r:2 | D3:4 A2:4 D3:8"),
    ("CATACOMBS", 10, True,
     "A3:4 r:4 D#4:4 r:4 | C4:8 B3:8 | A3:4 r:2 C4:2 F4:4 E4:4 | D#4:12 r:4 |"
     "A3:4 r:4 E4:4 r:4 | F4:8 E4:8 | D#4:4 C4:4 B3:4 G#3:4 | A3:12 r:4",
     "A2:8 A2:8 | F3:8 E3:8 | A2:8 D3:8 | B2:16 | A2:8 A2:8 | D3:8 C3:8 | B2:8 E3:8 | A2:16"),
    ("BATTLE", 5, True,
     "E5:2 E5:2 B4:2 E5:2 G5:2 F#5:2 E5:2 B4:2 | D5:2 D5:2 A4:2 D5:2 F#5:2 E5:2 D5:2 A4:2 |"
     "C5:2 C5:2 G4:2 C5:2 E5:2 D5:2 C5:2 G4:2 | B4:2 C5:2 D5:2 D#5:2 E5:4 r:4",
     "E3:2 E3:2 E4:2 E3:2 E3:2 E3:2 E4:2 E3:2 | D3:2 D3:2 D4:2 D3:2 D3:2 D3:2 D4:2 D3:2 |"
     "C3:2 C3:2 C4:2 C3:2 C3:2 C3:2 C4:2 C3:2 | B2:2 B2:2 B3:2 B2:2 B2:4 B3:4"),
    ("BOSS", 5, True,
     "A4:2 A4:2 C5:2 A4:2 D#5:2 D5:2 C5:2 A4:2 | G4:2 G4:2 A#4:2 G4:2 D5:2 C#5:2 A#4:2 G4:2 |"
     "F4:2 A4:2 C5:2 F5:2 E5:2 C5:2 A4:2 E5:2 | D#5:4 E5:4 A5:4 r:4",
     "A2:2 A3:2 A2:2 A3:2 A2:2 A3:2 A2:2 A3:2 | G3:2 D3:2 G3:2 D3:2 G3:2 D3:2 G3:2 D3:2 |"
     "F3:2 C3:2 F3:2 C3:2 E3:2 B2:2 E3:2 B2:2 | B2:4 E3:4 A2:8"),
    ("VICTORY", 6, False,
     "C5:2 E5:2 G5:2 C6:6 r:2 A5:2 B5:2 C6:8",
     "C3:6 E3:6 G3:4 C4:8"),
    ("GAMEOVER", 9, False,
     "E4:6 D4:6 C4:6 B3:12",
     "A2:12 E3:6 A2:12"),
    ("ENDING", 8, True,
     "C5:6 G4:2 C5:4 E5:4 | D5:6 C5:2 B4:8 | A4:6 B4:2 C5:4 A4:4 | G4:12 r:4 |"
     "C5:6 G4:2 C5:4 E5:4 | F5:6 E5:2 D5:4 F5:4 | E5:4 D5:4 C5:4 B4:4 | C5:12 r:4",
     "C3:8 G3:8 | G3:8 D3:8 | F3:8 C3:8 | G3:8 B2:8 | C3:8 G3:8 | F3:8 A3:8 | G3:8 D3:8 | C3:16"),
]
