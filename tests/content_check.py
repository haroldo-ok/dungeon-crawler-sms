#!/usr/bin/env python3
"""The content compiler (tools/gen.py) must reject broken content with a clear
message, and accept new content added purely as data.  Each case reloads
tools/content.py, changes it in memory and compiles it."""
import importlib, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import content
SRC = open(os.path.join(TOOLS, "gen.py")).read()
CONTENT_PART = SRC[SRC.index("# ---------------------------------------------------------------------------"
                             "-- content"):SRC.index("# ---------------------------------------------------------------------------"
                                                     "-- projection")]


def compile_with(change):
    C = importlib.reload(content)
    change(C)
    ns = {"__name__": "content_check"}
    exec("import math, os, sys\nimport numpy as np\n" + CONTENT_PART, ns)
    return ns


def level(C, lid):
    return next(L for L in C.LEVELS if L["id"] == lid)


def wall_off(C):        # the key chamber's only way in is the secret wall: make it plain wall
    m = level(C, "KEEP")["map"]
    m[5] = m[5][:13] + "#" + m[5][14:]


def long_msg(C):
    level(C, "CRYPT")["events"].append(C.msg(14, 1, "THIS MESSAGE IS FAR TOO LONG TO FIT IN TWO LINES OF THE MESSAGE BOX"))


def bad_item(C):
    level(C, "KEEP")["events"][4]["do"][0] = ("ITEM", "MEGA POTION", 1)


def bad_stairs(C):
    level(C, "KEEP")["events"][-1]["do"][0] = ("STAIRS", "ATTIC", 1, 1, 0)


def obj_in_wall(C):
    level(C, "MINES")["objects"].append(("SLIME", 0, 0, 1))


def bad_char(C):
    m = level(C, "CRYPT")["map"]
    m[1] = m[1][:3] + "K" + m[1][4:]       # bone walls belong to the catacombs' texture set


def big_group(C):
    level(C, "KEEP")["objects"][3] = ("SKEL", 6, 13, 5)


def tile_size(C):
    C.THEMES["MINES"]["flats"]["dirt"] = C.THEMES["MINES"]["walls"]["#"]   # 32x32 used as a floor


def unknown_font(C):
    C.MONSTERS["BAT"]["death"] = " FALLS; DEAD!"


def lost_stairs(C):                        # stairs with no event
    del level(C, "CRYPT")["events"][2]


BAD = [(wall_off, "unreachable cells"), (long_msg, "does not fit"), (bad_item, "unknown item"),
       (bad_stairs, "unknown level"), (obj_in_wall, "inside a wall"), (bad_char, "not in theme"),
       (big_group, "group size"), (tile_size, "16x16"), (unknown_font, "missing from the font"),
       (lost_stairs, "lead nowhere")]


def new_content(C):
    sys.modules.pop("demo_garden", None)
    import demo_garden                            # applies its changes to the fresh content
    for k in ("THEMES", "MONSTERS", "WEAPONS", "LEVELS"):
        setattr(C, k, getattr(demo_garden, k))


fails = 0
for change, expect in BAD:
    try:
        compile_with(change)
        print(f"FAIL {change.__name__}: accepted")
        fails += 1
    except Exception as e:
        ok = expect in str(e)
        print(f"{'ok  ' if ok else 'FAIL'} {change.__name__}: {e}")
        fails += not ok
try:
    ns = compile_with(new_content)
    print(f"ok   new level + monster + item as data: {len(ns['C'].LEVELS)} levels, kinds {ns['KINDS']}")
except Exception as e:
    print(f"FAIL new content rejected: {e}")
    fails += 1
compile_with(lambda C: None)
print("RESULT:", "ALL PASSED" if not fails else f"{fails} FAILURE(S)")
sys.exit(1 if fails else 0)
