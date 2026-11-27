#ifndef GAME_H
#define GAME_H
/* shared between game.c (exploration, ROM bank 1) and battle.c (bank 0) */

/* player */
extern unsigned char level, px, py, pf;
extern unsigned char hp, maxhp, mp, maxmp, plv, patk, pdef;
extern unsigned char potions, ethers, nkeys, weapon, armor;
extern unsigned int xp, gold;
extern unsigned char won, quick_mode;
extern unsigned char dead, ai_off, in_battle;
extern unsigned char ev_done[16];
extern unsigned char visited[NLEVELS][32];
extern unsigned int kills, hits_taken;
extern unsigned char back_buf;

/* objects */
extern unsigned char obj_type[NOBJ], obj_lvl[NOBJ], obj_x[NOBJ], obj_y[NOBJ], obj_n[NOBJ], obj_stun[NOBJ];
extern unsigned char obj_frame[NOBJ];
#define IS_MONSTER(t) ((t) == OBJ_SKEL || (t) == OBJ_BAT || (t) == OBJ_GHOST || (t) == OBJ_SPIDER || (t) == OBJ_LICH)
#define BLOCKS(t)     (IS_MONSTER(t) || (t) == OBJ_MERCHANT)

/* HUD / text */
void put_tile(unsigned char x, unsigned char y, unsigned int t);
unsigned char glyph(char c);
const char *print(unsigned char x, unsigned char y, const char *s);
void print_num2(unsigned char x, unsigned char y, unsigned char v);
void clear_row(unsigned char y);
void message(const char *s);
void clear_message(void);
void draw_status(void);
void draw_explore_hud(void);

/* sound */
void sfx_noise(unsigned char noise, unsigned char atten, unsigned char len);
void sfx_tone(unsigned int period, unsigned char atten, unsigned char len);
void sfx_update(void);
#define SFX_BUMP()   sfx_noise(0x05, 0, 12)
#define SFX_STEP()   sfx_noise(0x06, 5, 4)
#define SFX_HURT()   sfx_noise(0x04, 0, 16)
#define SFX_HIT()    sfx_tone(0x1C0, 2, 10)
#define SFX_DOOR()   sfx_tone(0x3A0, 3, 20)
#define SFX_PICKUP() sfx_tone(0x060, 2, 16)
#define SFX_MAGIC()  sfx_tone(0x0A0, 1, 24)
#define SFX_WIN()    sfx_tone(0x050, 1, 30)

unsigned char rnd(void);
void render_and_flip(unsigned char cx, unsigned char cy, unsigned char f, unsigned char pose);
void present(unsigned char cx, unsigned char cy, unsigned char f, unsigned char pose);
void redraw(void);

/* battle.c */
void battle(unsigned char obj);      /* blocking; returns when it is over      */
void new_player(void);
unsigned char ui_menu(const char **items, unsigned char n);   /* 0xFF = back */
void say(const char *s);             /* message + short pause                   */
unsigned int poll_presses(void);
extern unsigned char bt_say_frames;

/* menus.c */
unsigned char eff_atk(void);
unsigned char eff_def(void);
unsigned char use_item_menu(void);   /* potion / ether; 1 if one was used      */
void shop(void);
void pause_menu(void);
unsigned char save_game(void);
unsigned char load_game(void);       /* 1 = a valid save was restored           */
unsigned char save_valid(void);
extern unsigned char saves_made, loads_made;
extern const char * const WEAPON_NAME[4];
extern const char * const ARMOR_NAME[4];

/* game.c */
void print_num(unsigned char x, unsigned char y, unsigned int v, unsigned char digits);
void draw_inventory(void);
void open_automap(void);
void after_load(void);
void store_level_map(void);
#endif
