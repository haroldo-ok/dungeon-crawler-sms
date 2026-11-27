"""Example: new content added purely as data, on top of tools/content.py.

It adds a fifth level (a roof garden reached by a new stair in the keep) with
its own texture set, a new monster, a new weapon sold by a merchant there, and
a chest - without touching any C code.  tests/content_check.py compiles it and
tests/demo_content.sh builds a ROM from it and plays it:

    SMS_CONTENT=demo_garden PYTHONPATH=tests make
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from content import *                    # everything in tools/content.py ...

# ... plus a texture set: green-glazed brick, a trellis of planks, lawn and sky
THEMES["GARDEN"] = dict(
    walls={'#': tex_bricks([DGREEN, GREEN, LGREEN, KHAKI], BLACK, 5), 'W': tex_planks(), 'H': tex_hedge()},
    door=tex_door(), locked=tex_door(True), stairs=tex_stairs(),
    flats={"grass": tex_grass(), "flag": tex_flag(9), "beams": tex_beams()},
    opens={'.': ("flag", "beams"), ',': ("grass", None), ':': ("flag", None)},
    sky=tex_dusk_sky(), open_as='.')

# a monster (re-using the bat's art at another size)
MONSTERS["MOTH"] = dict(name="GIANT MOTH", plural="GIANT MOTHS", group="A CLOUD OF",
                        sprite=(spr_bat(0), spr_bat(1)), size="standing",
                        hp=8, atk=7, df=1, xp=6, gold=3, run=50,
                        attack="MOTHS FLUTTER AT YOU!", death=" DROPS!")

# a weapon, stocked by the garden's merchant
WEAPONS.append(("SILVER SWORD", 16, 400))

# the level, linked to the keep by a stair in the keep's north wall
_keep = next(L for L in LEVELS if L["id"] == "KEEP")
_keep["map"][0] = "#S##############"
_keep["events"].append(stairs(1, 0, "GARDEN", 1, 1, 2, "STEPS LEAD UP TO A|ROOF GARDEN"))
LEVELS.append(dict(
    id="GARDEN", name="THE GARDEN", theme="GARDEN", music="KEEP",
    map=["#S##############",
         "#.....,,,,,,,..#",
         "#.###H,,,,,,H#.#",
         "#...#H,,::,,H..#",
         "###.#H,,::,,H#.#",
         "#...W,,,,,,,,W.#",
         "#.###,,,,,,,,#.#",
         "#.....,,,,,,...#"] + ["################"] * 8,
    events=[stairs(1, 0, "KEEP", 1, 1, 2, "BACK DOWN TO THE KEEP"),
            msg(8, 3, "ROSES AND THORNS. THE AIR|IS SWEET UP HERE"),
            chest(14, 7, "A CHEST! 2 ELIXIRS", ELIXIR=2)],
    objects=[("MOTH", 9, 5, 2), ("CHEST", 14, 7, 1), ("MERCHANT", 2, 7, 1)],
    shop=dict(weapons=5, armors=4, goods=["POTION", "ELIXIR"], inn=10)))
