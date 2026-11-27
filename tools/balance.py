#!/usr/bin/env python3
"""Monte Carlo balance check, straight from tools/content.py.

Plays the whole game many times - every chest, every monster group on every
level in order, the merchants, springs and the boss - with the same battle
rules as src/battle.c, for three play styles:

  careful         heals (spell, then potions) below 40% HP, rests at springs
                  between fights, buys the best gear it can afford
  reckless        buys gear, but only drinks a potion below 25% HP and never
                  rests between fights on a level
  reckless/no gear  the same without ever buying weapons or armour

usage: balance.py [runs]          (default 2000 per style)
Prints the win rate, where runs die, and the hero's level at each boss.
"""
import os, random, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content as C

P = C.PLAYER
CONS = list(C.CONSUMABLES)
MAX_LEVEL = len(P["next_xp"]) + 1


class Hero:
    def __init__(self):
        self.lv, self.maxhp, self.maxmp = 1, P["hp"], P["mp"]
        self.hp, self.mp, self.atk, self.df = self.maxhp, self.maxmp, P["atk"], P["df"]
        self.xp = self.gold = 0
        self.items = {k: C.CONSUMABLES[k]["start"] for k in CONS}
        self.weapon = self.armor = 0

    def eff_atk(self): return self.atk + C.WEAPONS[self.weapon][1]
    def eff_def(self): return self.df + C.ARMORS[self.armor][1]

    def drink(self, k):
        c = C.CONSUMABLES[k]
        self.items[k] -= 1
        self.hp = min(self.maxhp, self.hp + c["hp"])
        self.mp = min(self.maxmp, self.mp + c["mp"])

    def gain(self, xp, gold, r):
        self.xp += xp
        self.gold += gold
        g = P["per_level"]
        while self.lv < MAX_LEVEL and self.xp >= P["next_xp"][self.lv - 1]:
            self.lv += 1
            self.maxhp = min(99, self.maxhp + g["hp"]); self.maxmp = min(99, self.maxmp + g["mp"])
            self.atk += g["atk"]; self.df += g["df"]
            self.hp = min(self.maxhp, self.hp + g["hp"]); self.mp = min(self.maxmp, self.mp + g["mp"])
        if r.randrange(C.LOOT["one_in"]) == 0:
            self.items[C.LOOT["item"]] = min(99, self.items[C.LOOT["item"]] + 1)


def roll(r, atk, df):
    d = atk + r.randrange(256) % (atk // 2 + 1)
    return d - df if d > df else 1


def heal_needed(h, frac):
    return h.hp < h.maxhp * frac


def battle(h, kind, n, style, r):
    md = C.MONSTERS[kind]
    hps = [md["hp"]] * n
    rnd_ = 0
    frac = 0.4 if style == "careful" else 0.25
    while True:
        rnd_ += 1
        # player
        if heal_needed(h, frac):
            if style == "careful" and h.mp >= P["heal"]["mp"]:
                h.mp -= P["heal"]["mp"]
                h.hp = min(h.maxhp, h.hp + P["heal"]["base"] + h.lv * P["heal"]["per_level"])
            else:
                k = next((k for k in CONS if h.items[k] and C.CONSUMABLES[k]["hp"]), None)
                if k:
                    h.drink(k)
                else:
                    attack(h, md, hps, r, style)
        else:
            attack(h, md, hps, r, style)
        if not any(hps):
            h.gain(md["xp"] * n, md["gold"] * n, r)
            return True
        # monsters
        for i in range(n):
            if not hps[i]:
                continue
            sp = md.get("spell")
            if sp and rnd_ % sp["every"] == 0:
                div = {"full": 1, "half": 2, "none": 0}[sp["armor"]]
                a = h.eff_def() // div if div else 0
                d = sp["dmg"] + r.randrange(256) % sp["rnd"]
                d = d - a if d > a else 1
            elif r.randrange(8) == 0:
                continue
            else:
                d = roll(r, md["atk"], h.eff_def())
            h.hp = max(0, h.hp - d)
            if not h.hp:
                return False


def attack(h, md, hps, r, style):
    t = next(i for i, v in enumerate(hps) if v)
    fire = P["fire"]
    if md.get("fire_weak") and h.mp >= fire["mp"] and style == "careful":
        h.mp -= fire["mp"]
        d = (fire["base"] + h.lv * fire["per_level"] + r.randrange(4)) * 2
    else:
        if r.randrange(16) == 1:
            return
        d = roll(r, h.eff_atk(), md["df"])
        if r.randrange(16) == 0:
            d *= 2
    hps[t] = max(0, hps[t] - min(d, 255))


def shop(h, sh, gear, r):
    if not sh:
        return
    while gear:
        bought = False
        for lst, attr, cap in ((C.WEAPONS, "weapon", sh["weapons"]), (C.ARMORS, "armor", sh["armors"])):
            nxt = getattr(h, attr) + 1
            if nxt <= cap and h.gold >= lst[nxt][2]:
                h.gold -= lst[nxt][2]
                setattr(h, attr, nxt)
                bought = True
        if not bought:
            break
    for k in sh["goods"]:                         # stock up on healing with what is left
        c = C.CONSUMABLES[k]
        while c["hp"] and h.items[k] < 5 and h.gold >= c["price"] + 20:
            h.gold -= c["price"]
            h.items[k] += 1


def play(style, r):
    h = Hero()
    boss_lv = {}
    for L in C.LEVELS:
        chests = [e for e in L["events"] if any(a[0] == "TAKE" for a in e["do"])]
        for e in chests:
            for a in e["do"]:
                if a[0] == "ITEM":
                    h.items[a[1]] = min(99, h.items[a[1]] + a[2])
                elif a[0] == "GOLD":
                    h.gold += a[1]
        springs = any(a[0] == "HEAL" for e in L["events"] for a in e["do"])
        h.hp, h.mp = h.maxhp, h.maxmp             # an inn or a spring on arrival
        shop(h, L.get("shop"), style != "reckless/no gear", r)
        groups = [(k, n) for k, x, y, n in L["objects"] if k in C.MONSTERS]
        groups.sort(key=lambda g: bool(C.MONSTERS[g[0]].get("boss")))     # bosses last
        for k, n in groups:
            if C.MONSTERS[k].get("boss"):
                boss_lv[k] = h.lv
                if springs:
                    h.hp, h.mp = h.maxhp, h.maxmp
                shop(h, L.get("shop"), style != "reckless/no gear", r)
            elif style == "careful" and springs:
                h.hp, h.mp = h.maxhp, h.maxmp
            if not battle(h, k, n, style, r):
                return False, f"{L['id']}: {k}", boss_lv, h
    return True, None, boss_lv, h


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    for style in ("careful", "reckless", "reckless/no gear"):
        r = random.Random(1)
        wins, deaths, lvs, final = 0, Counter(), Counter(), Counter()
        for _ in range(runs):
            ok, where, boss_lv, h = play(style, r)
            wins += ok
            if not ok:
                deaths[where] += 1
            for k, v in boss_lv.items():
                lvs[(k, v)] += 1
            if ok:
                final[h.lv] += 1
        print(f"{style:17s} wins {100 * wins / runs:5.1f}%", end="")
        if deaths:
            print("   deaths: " + ", ".join(f"{w} {100 * c / runs:.1f}%" for w, c in deaths.most_common(4)), end="")
        print()
        for boss in [k for k in C.MONSTERS if C.MONSTERS[k].get("boss")]:
            v = sorted((lv, c) for (k, lv), c in lvs.items() if k == boss)
            if v:
                print(f"{'':17s} reaches {boss} at level " + " ".join(f"{lv}:{100 * c / runs:.0f}%" for lv, c in v))


if __name__ == "__main__":
    main()
