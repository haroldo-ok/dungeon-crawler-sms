/* Everything a save game needs besides the level maps (0xDB00), in one
   contiguous block: the linker keeps a module's variables together in
   declaration order, so the save copies state_begin..state_end.
   new_game()/new_player() initialise all of it.                          */
#include "engine.h"
#include "game.h"

unsigned char state_begin;           /* marks the start of the saved block     */
unsigned char level, px, py, pf;     /* level, resting cell, facing (0 N,1 E,2 S,3 W) */
unsigned char hp, maxhp, mp, maxmp, plv, patk, pdef;
unsigned char potions, ethers, nkeys, weapon, armor;
unsigned int xp, gold;
unsigned char won, quick_mode;
unsigned char obj_type[NOBJ], obj_lvl[NOBJ], obj_x[NOBJ], obj_y[NOBJ], obj_n[NOBJ], obj_stun[NOBJ];
unsigned char ev_done[16];
unsigned char visited[NLEVELS][32];
unsigned char state_end;             /* marks the end of the saved block       */
