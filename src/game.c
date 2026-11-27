/* SMS Dungeon - a first-person grid dungeon crawler for the Sega Master System.
   Grid movement with smooth interpolated steps/turns, real-time texture mapped
   walls, floor and ceiling, sky wherever a cell has no ceiling, doors, keys,
   secret walls, an automap and monsters drawn as depth-tested billboards.
   Levels, monsters, items and events are data (tools/content.py -> gen.c):
   this file runs them - events are small scripts (run_event).             */
#include <SMSlib.h>
#include "engine.h"
#include "core.h"
#include "game.h"
#include "music.h"

SMS_EMBED_SEGA_ROM_HEADER(9999, 0);
SMS_EMBED_SDSC_HEADER_AUTO_DATE(1, 1, "Claude", "SMS Dungeon", "First-person textured dungeon crawler");

__sfr __at 0xBE VDP_DATA2;
__sfr __at 0xBF VDP_CTRL2;
__sfr __at 0x7F PSG_PORT;

static const signed char DX[4] = { 0, 1, 0, -1 };
static const signed char DY[4] = { -1, 0, 1, 0 };


#define WAKE_DIST  7
#define IDLE_TICK  100      /* VBlanks between monster moves while you wait  */

/* ---- game state (globals so the test harness can read/poke them) ---------- */
unsigned char dead, ai_off, map_open, battle_pending, in_battle, ending_pending;
unsigned char anim_len, anim_pos;
unsigned char seq_cx[16], seq_cy[16], seq_f[16], seq_pose[16];
unsigned char back_buf;
unsigned int last_action;
unsigned int moves, turns, bumps, uses, hits_taken, kills;
unsigned int pad, prev_pad;
unsigned char b1_armed, b1_used;     /* button 1: tap = use, held + L/R = strafe */
unsigned char game_ready;
unsigned char last_msg;              /* id of the last event message (tests)  */
unsigned char rng;

unsigned char obj_frame[NOBJ];

unsigned char rnd(void)
{
    rng ^= rng << 3; rng ^= rng >> 5; rng ^= rng << 1;
    return rng;
}

/* ---- HUD ------------------------------------------------------------------ */
void put_tile(unsigned char x, unsigned char y, unsigned int t)
{
    unsigned int a = 0x3800 + ((unsigned int)y * 32 + x) * 2;
    __asm__("di");                   /* the VBlank handler also talks to the VDP */
    VDP_CTRL2 = a & 255;
    VDP_CTRL2 = (a >> 8) | 0x40;
    VDP_DATA2 = t & 255;
    __asm__("nop"); __asm__("nop");
    VDP_DATA2 = t >> 8;
    __asm__("ei");
}

unsigned char glyph(char c)
{
    return glyph_tab[(c - 32) & 127];
}

/* prints until NUL or '|'; returns pointer to the stop character */
const char *print(unsigned char x, unsigned char y, const char *s)
{
    while (*s && *s != '|') put_tile(x++, y, T_FONT + glyph(*s++));
    return s;
}

void print_num2(unsigned char x, unsigned char y, unsigned char v)
{
    put_tile(x, y, T_FONT + glyph('0' + v / 10));
    put_tile(x + 1, y, T_FONT + glyph('0' + v % 10));
}

void clear_row(unsigned char y)
{
    unsigned int a = 0x3800 + ((unsigned int)y * 32 + 1) * 2;
    unsigned char x;
    __asm__("di");                   /* one address set, 30 paced entries     */
    VDP_CTRL2 = a & 255;
    VDP_CTRL2 = (a >> 8) | 0x40;
    for (x = 0; x < 30; x++) {
        VDP_DATA2 = T_BG & 255;
        __asm__("nop"); __asm__("nop"); __asm__("nop"); __asm__("nop");
        VDP_DATA2 = T_BG >> 8;
    }
    __asm__("ei");
}

unsigned char msg_shown;

#define MSG_W 27                      /* characters per message line          */

/* print one message line: stops at '|', NUL, or wraps at the last space
   that fits; returns where the next line starts */
static const char *print_line(unsigned char y, const char *s)
{
    unsigned char len = 0, cut, i;
    while (s[len] && s[len] != '|') len++;
    cut = len;
    if (len > MSG_W) {
        cut = MSG_W;
        while (cut && s[cut] != ' ') cut--;
        if (!cut) cut = MSG_W;
    }
    for (i = 0; i < cut; i++) put_tile(3 + i, y, T_FONT + glyph(s[i]));
    s += cut;
    if (*s == '|' || *s == ' ') s++;
    return s;
}

/* two-line message; '|' forces the break, long lines wrap */
void message(const char *s)
{
    clear_row(19); clear_row(20);
    s = print_line(19, s);
    if (*s) print_line(20, s);
    msg_shown = 1;
}

void clear_message(void)
{
    if (msg_shown) { clear_row(19); clear_row(20); msg_shown = 0; }
}

void print_num(unsigned char x, unsigned char y, unsigned int v, unsigned char digits)
{
    x += digits;
    while (digits--) {
        put_tile(--x, y, T_FONT + glyph('0' + v % 10));
        v /= 10;
    }
}

void draw_status(void)               /* row 16: HP / MP / level              */
{
    print(3, 16, "HP");
    print_num2(6, 16, hp);
    print(8, 16, "/");
    print_num2(9, 16, maxhp);
    print(13, 16, "MP");
    print_num2(16, 16, mp);
    print(18, 16, "/");
    print_num2(19, 16, maxmp);
    print(23, 16, "LV");
    print_num2(26, 16, plv);
}

void draw_inventory(void)            /* row 17: keys, consumables, gold      */
{
    unsigned char i;
    print(3, 17, "K");
    print_num(4, 17, nkeys, 1);
    for (i = 0; i < NCONS; i++) {
        print(6 + i * 6, 17, cons_hud[i]);
        print_num2(9 + i * 6, 17, items[i]);
    }
    print(24, 17, "G");
    print_num(25, 17, gold, 4);
    print(7, 0, "SMS DUNGEON");
    print(19, 0, "            ");
    print(19, 0, level_name[level]);
}

void draw_explore_hud(void)
{
    unsigned char y;
    for (y = 16; y < 24; y++) clear_row(y);
    msg_shown = 0;
    draw_status();
    draw_inventory();
    print(2, 22, "1 USE  1+L/R STRAFE  2 MENU");
    print(2, 23, "UP/DOWN WALK   L/R TURN");
}

static void draw_static_hud(void)
{
    unsigned char x, y;
    for (y = 0; y < 24; y++)
        for (x = 0; x < 32; x++) put_tile(x, y, T_BG);
    put_tile(VIEW_TX - 1, VIEW_TY - 1, T_FRAME + 0);
    put_tile(VIEW_TX + 16, VIEW_TY - 1, T_FRAME + 2);
    put_tile(VIEW_TX - 1, VIEW_TY + 12, T_FRAME + 5);
    put_tile(VIEW_TX + 16, VIEW_TY + 12, T_FRAME + 7);
    for (x = 0; x < 16; x++) {
        put_tile(VIEW_TX + x, VIEW_TY - 1, T_FRAME + 1);
        put_tile(VIEW_TX + x, VIEW_TY + 12, T_FRAME + 6);
    }
    for (y = 0; y < 12; y++) {
        put_tile(VIEW_TX - 1, VIEW_TY + y, T_FRAME + 3);
        put_tile(VIEW_TX + 16, VIEW_TY + y, T_FRAME + 4);
    }
}

/* ---- sound ---------------------------------------------------------------- */
unsigned char sfx_timer, sfx_atten, tone_timer, tone_atten;

/* PSG writes are di-guarded: the VBlank interrupt drives the music channels
   and a latch/data pair must not be split by it */
void sfx_noise(unsigned char noise, unsigned char atten, unsigned char len)
{
    __asm__("di");
    PSG_PORT = 0xE0 | noise;
    PSG_PORT = 0xF0 | atten;
    __asm__("ei");
    sfx_atten = atten;
    sfx_timer = len;
}

void sfx_tone(unsigned int period, unsigned char atten, unsigned char len)
{
    __asm__("di");
    PSG_PORT = 0x80 | (period & 15);
    PSG_PORT = (period >> 4) & 0x3F;
    PSG_PORT = 0x90 | atten;
    __asm__("ei");
    tone_atten = atten;
    tone_timer = len;
}

void sfx_update(void)
{
    if (sfx_timer) {
        sfx_timer--;
        if (sfx_atten < 15) sfx_atten++;
        PSG_PORT = 0xF0 | (sfx_timer ? sfx_atten : 15);
    }
    if (tone_timer) {
        tone_timer--;
        if (tone_atten < 15 && !(tone_timer & 1)) tone_atten++;
        PSG_PORT = 0x90 | (tone_timer ? tone_atten : 15);
    }
}

/* ---- world queries -------------------------------------------------------- */
static unsigned char cell(unsigned char x, unsigned char y)
{
    return map_ram[((y & 15) << 4) | (x & 15)];
}

/* open a wall / door for good: the live map plus the level's opened bits */
static void open_cell(unsigned char x, unsigned char y)
{
    unsigned char i = ((y & 15) << 4) | (x & 15);
    map_ram[i] = level_open[level];
    OPENED(level)[i >> 3] |= 1 << (i & 7);
}

/* rebuild a level's live map: ROM map + whatever was opened since */
static void load_level_map(unsigned char l)
{
    const unsigned char *src = (const unsigned char *)MAP_DATA + ((unsigned int)l << 8);
    unsigned char i = 0, o = level_open[l];
    MAP_SLOT2(DATA_BANK);                    /* the maps live in the data bank   */
    do {
        map_ram[i] = (OPENED(l)[i >> 3] & (1 << (i & 7))) ? o : src[i];
    } while (++i);
    render_set_theme(level_theme[l]);
}

static void engage(unsigned char i);

/* index of a live monster on this level at x,y, or 0xFF */
static unsigned char monster_at(unsigned char x, unsigned char y)
{
    unsigned char i;
    for (i = 0; i < NOBJ; i++)
        if (IS_MONSTER(obj_type[i]) && obj_lvl[i] == level && obj_x[i] == x && obj_y[i] == y)
            return i;
    return 0xFF;
}

/* index of a live object (any type) on this level at x,y, or 0xFF */
static unsigned char obj_at(unsigned char x, unsigned char y, unsigned char type)
{
    unsigned char i;
    for (i = 0; i < NOBJ; i++)
        if (obj_type[i] && obj_lvl[i] == level && obj_x[i] == x && obj_y[i] == y &&
            (!type || obj_type[i] == type))
            return i;
    return 0xFF;
}

static void mark_visited(void)
{
    VISITED(level)[(py << 1) | (px >> 3)] |= 1 << (px & 7);
}

static unsigned char is_visited(unsigned char l, unsigned char x, unsigned char y)
{
    return VISITED(l)[(y << 1) | (x >> 3)] & (1 << (x & 7));
}

/* ---- rendering glue ------------------------------------------------------- */

static void build_visible(unsigned char cx, unsigned char cy)
{
    unsigned char i, t;
    vis_n = 0;
    vis_direct = 0;
    for (i = 0; i < NOBJ && vis_n < MAX_VIS; i++) {
        signed char dx, dy;
        t = obj_type[i];
        if (!t || obj_lvl[i] != level) continue;
        dx = obj_x[i] - cx; dy = obj_y[i] - cy;
        if (dx < -12 || dx > 12 || dy < -12 || dy > 12) continue;
        vis_x[vis_n] = obj_x[i];
        vis_y[vis_n] = obj_y[i];
        vis_type[vis_n] = kind_cls[t];        /* scale class + sprite frame: gen.c */
        vis_frame[vis_n] = kind_frame[t] + obj_frame[i];
        vis_n++;
    }
}

void present(unsigned char cx, unsigned char cy, unsigned char f, unsigned char pose)
{
    while (flip_pending) ;           /* back buffer still on screen?          */
    r_buf = back_buf;
    render_upload();
    pend_buf = back_buf; pend_cx = cx; pend_cy = cy; pend_f = f; pend_pose = pose;
    flip_pending = 1;
    back_buf ^= 1;
}

void render_and_flip(unsigned char cx, unsigned char cy, unsigned char f, unsigned char pose)
{
    r_cx = cx; r_cy = cy; r_f = f; r_pose = pose;
    build_visible(cx, cy);
    render_frame();                  /* RAM work overlaps the previous flip   */
    present(cx, cy, f, pose);
}

/* ---- automap: drawn straight into the view framebuffer ---------------------- */
static void fb_px(unsigned char x, unsigned char y, unsigned char c)
{
    unsigned char *p = (unsigned char *)(((unsigned int)(FB_PAGE + (x >> 2)) << 8) |
                                         (((x >> 1) & 1) << 7) | (x & 1)) + 2 * y;
    *p = (x & 1) ? c : (c << 4);
}

static unsigned char map_colour(unsigned char m)    /* per texture set, from gen.c */
{
    return theme_mapcol[((unsigned int)level_theme[level] << 5) + (m & 31)];
}

static void draw_automap(void)
{
    unsigned char x, y, i, j;
    for (x = 0; x < 64; x++)
        for (y = 0; y < 48; y++) fb_px(x, y, 0);
    for (y = 0; y < 16; y++)
        for (x = 0; x < 16; x++) {
            unsigned char known = is_visited(level, x, y), c;
            if (!known) {            /* walls next to a visited cell are known too */
                if ((x > 0 && is_visited(level, x - 1, y)) || (x < 15 && is_visited(level, x + 1, y)) ||
                    (y > 0 && is_visited(level, x, y - 1)) || (y < 15 && is_visited(level, x, y + 1)))
                    known = cell(x, y) >= 16;
            }
            if (!known) continue;
            c = map_colour(cell(x, y));
            for (j = 0; j < 3; j++)
                for (i = 0; i < 3; i++) fb_px(8 + x * 3 + i, y * 3 + j, c);
        }
    /* player: white block with a red dot on the side it faces */
    for (j = 0; j < 3; j++)
        for (i = 0; i < 3; i++) fb_px(8 + px * 3 + i, py * 3 + j, 3);
    fb_px(8 + px * 3 + 1 + DX[pf], py * 3 + 1 + DY[pf], 4);
    present(px, py, pf, 0xFF);
}

static void calm_monsters(void);

void open_automap(void)
{
    map_open = 1;
    message(text_map);
    draw_automap();
}

/* ---- title & ending ----------------------------------------------------------
   Both draw a 3D view, then stamp a logo (runs of x, y, length, colour from
   the data bank, mapped into slot 2 - free between render and upload).     */
#define TITLE_SKIP (*(volatile unsigned int *)0xDAF0)  /* test hook: 0x5A17 skips the title */
unsigned char in_title, ending_seen, in_ending;
unsigned char dbg_level = 0xFF;      /* test hook: poke a level number to jump there */

static void stamp(unsigned int rle_addr)
{
    const unsigned char *r = (const unsigned char *)rle_addr;
    MAP_SLOT2(DATA_BANK);
    while (r[0] != 0xFF) {
        unsigned char x = r[0], n = r[2];
        while (n--) fb_px(x++, r[1], r[3]);
        r += 4;
    }
}

static void render_stamped(unsigned char cx, unsigned char cy, unsigned char f, unsigned char pose, unsigned int rle)
{
    r_cx = cx; r_cy = cy; r_f = f; r_pose = pose;
    build_visible(cx, cy);
    render_frame();
    stamp(rle);
    present(cx, cy, f, 0xFE);
}

/* logo over a slow 360-degree turn in the keep's courtyard */
static void title_screen(void)
{
    static const unsigned char ROT[6] = { 0, 11, 12, 13, 14, 15 };
    unsigned char f = 1, k = 0, y;
    if (TITLE_SKIP == 0x5A17) return;
    in_title = 1;
    music_play(MUS_TITLE);
    clear_row(0);
    for (y = 16; y < 24; y++) clear_row(y);
    print(TITLE_X, 17, text_title);
    print(8, 20, "PRESS 1 TO BEGIN");
    print(TAGLINE_X, 23, text_tagline);
    poll_presses();
    for (;;) {
        render_stamped(9, 9, f, ROT[k], LOGO_RLE);
        if (++k == 6) { k = 0; f = (f + 1) & 3; }
        if (poll_presses() & (PORT_A_KEY_1 | PORT_A_KEY_2)) break;
    }
    in_title = 0;
    SFX_PICKUP();
}

static void new_game(void);

/* title, then CONTINUE / NEW GAME when the cartridge holds a save */
static void start_menu(void)
{
    static const char * const TITLE_MENU[2] = { "CONTINUE", "NEW GAME" };
    new_game();                      /* level 1: the title shows its courtyard */
    title_screen();
    music_play(level_music[level]);
    draw_explore_hud();
    if (save_valid()) {
        while (anim_pos < anim_len) { render_and_flip(seq_cx[anim_pos], seq_cy[anim_pos], seq_f[anim_pos], seq_pose[anim_pos]); anim_pos++; }
        message("A SAVED ADVENTURE WAS|FOUND IN THE CARTRIDGE");
        if (ui_menu((const char **)TITLE_MENU, 2) == 0) { load_game(); return; }
        draw_explore_hud();
    }
    message(text_intro);
}

static void ending_say(const char *s)
{
    unsigned char n = bt_say_frames * 3;
    message(s);
    poll_presses();
    while (n--) {
        SMS_waitForVBlank();
        sfx_update();
        if (poll_presses() & (PORT_A_KEY_1 | PORT_A_KEY_2)) break;
    }
}

static void ending(void)
{
    unsigned char y;
    ending_pending = 0;
    in_ending = 1;
    music_play(MUS_ENDING);
    ending_say(text_ending[0]);
    ending_say(text_ending[1]);
    for (y = 16; y < 24; y++) clear_row(y);
    print(3, 16, "LEVEL");      print_num2(9, 16, plv);
    print(13, 16, "FOES SLAIN"); print_num(24, 16, kills, 3);
    print(3, 17, "GOLD");       print_num(9, 17, gold, 4);
    print(15, 17, "STEPS");     print_num(21, 17, moves, 5);
    ending_say(text_ending[2]);
    render_stamped(px, py, (pf + 2) & 3, 0, THE_END_RLE);   /* look back into the hall */
    message("PRESS 1 TO RETURN|TO THE TITLE");
    poll_presses();
    while (!(poll_presses() & PORT_A_KEY_1)) { SMS_waitForVBlank(); sfx_update(); }
    ending_seen = 1;
    in_ending = 0;
    start_menu();
}

/* ---- movement sequences -----------------------------------------------------
   Poses: 0 rest, 1..5 forward k/6, 6..10 right k/6, 11..15 turned right k*15deg,
   16..21 the quarter steps of quick mode; all relative to a base cell + facing. */
void push(unsigned char cx, unsigned char cy, unsigned char f, unsigned char pose)
{
    seq_cx[anim_len] = cx; seq_cy[anim_len] = cy; seq_f[anim_len] = f; seq_pose[anim_len] = pose;
    anim_len++;
}

void redraw(void)             /* re-render the resting view            */
{
    anim_len = 0; anim_pos = 0;
    push(px, py, pf, 0);
}

static const unsigned char SEQ[2][3][5] = {
    { { 1, 2, 3, 4, 5 }, { 6, 7, 8, 9, 10 }, { 11, 12, 13, 14, 15 } },   /* smooth */
    { { 16, 3, 17 },     { 18, 8, 19 },      { 20, 13, 21 } },           /* quick  */
};
static const unsigned char SEQ_LEN[2] = { 5, 3 };

/* after the save block was copied back into RAM */
void after_load(void)
{
    unsigned char i;
    load_level_map(level);
    for (i = 0; i < NOBJ; i++) obj_frame[i] = 0;
    dead = 0; map_open = 0; in_battle = 0; battle_pending = 0xFF;
    music_play(level_music[level]);
    draw_explore_hud();
    redraw();
}

static void change_level(unsigned char l, unsigned char x, unsigned char y, unsigned char f)
{
    level = l;
    load_level_map(l);
    music_play(level_music[l]);
    px = x; py = y; pf = f;
    mark_visited();
}

/* ---- events -------------------------------------------------------------------
   Each event is a cell + a little script of actions (OP_* in gen.h, written in
   tools/content.py).  On an open cell it runs when you step there; on a wall
   cell (stairs, a lever) when you walk into it or use it.                    */

/* the event on x,y of this level, or 0xFF */
static unsigned char event_at(unsigned char x, unsigned char y)
{
    unsigned char i;
    for (i = ev_start[level]; i < ev_start[level + 1]; i++)
        if (ev_x[i] == x && ev_y[i] == y) return i;
    return 0xFF;
}

static unsigned char ev_spent(unsigned char e)  /* a one-shot event that already ran */
{
    return ev_once[e] && (ev_done[e >> 3] & (1 << (e & 7)));
}

static void give(unsigned char *v, unsigned char n)
{
    *v = *v + n > 99 ? 99 : *v + n;
}

/* runs event e; returns 0 if there was nothing to do */
static unsigned char run_event(unsigned char e)
{
    const unsigned char *p;
    unsigned char k, ex = ev_x[e], ey = ev_y[e], need_redraw = 0, need_inv = 0;
    if (ev_spent(e)) return 0;
    ev_done[e >> 3] |= 1 << (e & 7);
    p = ev_script + ev_code[e];
    for (;;) {
        switch (*p++) {
        case OP_MSG:
            last_msg = *p;
            message(messages[*p++]);
            break;
        case OP_ITEM:   give(&items[p[0]], p[1]); p += 2; need_inv = 1; break;
        case OP_KEYS:   give(&nkeys, *p++); need_inv = 1; break;
        case OP_GOLD:   gold += p[0] | ((unsigned int)p[1] << 8); p += 2; need_inv = 1; break;
        case OP_HEAL:   hp = maxhp; mp = maxmp; draw_status(); break;
        case OP_TELE:
            px = p[0]; py = p[1]; pf = p[2]; p += 3;
            mark_visited();
            need_redraw = 1;
            break;
        case OP_STAIRS:
            change_level(p[0], p[1], p[2], p[3]); p += 4;
            need_inv = need_redraw = 1;          /* level name on the top line     */
            break;
        case OP_TAKE:
            k = obj_at(ex, ey, 0);
            if (k != 0xFF) obj_type[k] = 0;
            need_redraw = 1;
            break;
        case OP_OPEN:   open_cell(p[0], p[1]); p += 2; need_redraw = 1; break;
        case OP_SOUND:
            k = *p++;
            if (k == 0) SFX_PICKUP(); else if (k == 1) SFX_DOOR(); else SFX_MAGIC();
            break;
        case OP_WIN:    won = 1; ending_pending = 1; break;
        default:        goto done;               /* OP_END */
        }
    }
done:
    if (need_inv) draw_inventory();
    if (need_redraw) redraw();
    return 1;
}

/* the event in the wall cell ahead, if it still has something to do */
static unsigned char wall_event(unsigned char x, unsigned char y)
{
    unsigned char e = event_at(x, y);
    return (e != 0xFF && !ev_spent(e)) ? e : 0xFF;
}

/* the player has just arrived on px,py */
static void enter_cell(void)
{
    unsigned char e = event_at(px, py);
    mark_visited();
    clear_message();
    if (e != 0xFF) run_event(e);
}

static void start_move(signed char dx, signed char dy, unsigned char base_first, unsigned char kind)
{
    calm_monsters();
    unsigned char nx = px + dx, ny = py + dy, k, n = SEQ_LEN[quick_mode], m = cell(nx, ny);
    const unsigned char *sq = SEQ[quick_mode][kind];
    anim_len = 0; anim_pos = 0;
    if (m >= 16 && kind == 0 && base_first) {   /* walking into stairs, a lever... */
        k = wall_event(nx, ny);
        if (k != 0xFF) { run_event(k); moves++; return; }
    }
    k = monster_at(nx, ny);
    if (k != 0xFF) {                         /* walking into a monster: fight  */
        engage(k);
        return;
    }
    k = obj_at(nx, ny, 0);
    if (k != 0xFF && BLOCKS(obj_type[k])) {   /* a merchant or other solid prop */
        bumps++;
        k = kind_bump[obj_type[k]];
        if (k != 0xFF) message(messages[k]);
        return;
    }
    if (m >= 16) {
        bumps++;
        SFX_BUMP();
        if (m == M_DOOR) message("A HEAVY DOOR. PRESS 1|TO OPEN IT");
        else if (m == M_LOCKED) message("THIS DOOR IS LOCKED");
        if (kind == 0 && base_first) {       /* forward bump: nudge and back   */
            push(px, py, pf, sq[0]);
            push(px, py, pf, 0);
        }
        return;
    }
    if (base_first) {                        /* forward / strafe right         */
        for (k = 0; k < n; k++) push(px, py, pf, sq[k]);
    } else {                                 /* backward / strafe left         */
        for (k = n; k > 0; k--) push(nx, ny, pf, sq[k - 1]);
    }
    push(nx, ny, pf, 0);
    moves++;
}

/* queue a quarter turn starting from facing f (does not reset the queue) */
static unsigned char push_turn(unsigned char right, unsigned char f)
{
    unsigned char k, n = SEQ_LEN[quick_mode];
    const unsigned char *sq = SEQ[quick_mode][2];
    if (right) {
        for (k = 0; k < n; k++) push(px, py, f, sq[k]);
        f = (f + 1) & 3;
    } else {
        f = (f - 1) & 3;
        for (k = n; k > 0; k--) push(px, py, f, sq[k - 1]);
    }
    push(px, py, f, 0);
    return f;
}

static void start_turn(unsigned char right)
{
    calm_monsters();
    anim_len = 0; anim_pos = 0;
    push_turn(right, pf);
    turns++;
}

/* turn to face monster i (animated), then the battle starts */
static void engage(unsigned char i)
{
    signed char dx = obj_x[i] - px, dy = obj_y[i] - py;
    unsigned char nf = dy < 0 ? 0 : dx > 0 ? 1 : dy > 0 ? 2 : 3, f;
    battle_pending = i;
    anim_len = 0; anim_pos = 0;
    f = pf;
    if (((nf - f) & 3) == 3) f = push_turn(0, f);
    while (f != nf) f = push_turn(1, f);
}

/* ---- monsters -------------------------------------------------------------- */
static unsigned char monster_can_enter(unsigned char x, unsigned char y)
{
    if (cell(x, y) >= 16) return 0;
    if (x == px && y == py) return 0;
    return obj_at(x, y, 0) == 0xFF;
}

/* back to the idle pose before the player acts */
static void calm_monsters(void)
{
    unsigned char i;
    for (i = 0; i < NOBJ; i++) obj_frame[i] = 0;
}

/* one monster turn; returns 1 if anything visible changed.  A monster that
   reaches you starts a battle (engage) instead. */
static unsigned char monsters_turn(void)
{
    unsigned char i, changed = 0;
    if (ai_off || dead || battle_pending != 0xFF) return 0;
    for (i = 0; i < NOBJ; i++) {
        signed char dx, dy;
        unsigned char adx, ady, nx, ny;
        if (!IS_MONSTER(obj_type[i]) || obj_lvl[i] != level) continue;
        if (obj_stun[i]) { obj_stun[i]--; continue; }
        dx = px - obj_x[i]; dy = py - obj_y[i];
        adx = dx < 0 ? -dx : dx; ady = dy < 0 ? -dy : dy;
        if (adx + ady > WAKE_DIST) continue;
        if ((kind_flags[obj_type[i]] & KF_BOSS) && adx + ady > 1) continue;   /* bosses wait */
        if (adx + ady == 1) {                /* adjacent: it attacks           */
            message(MON(obj_type[i])->attack);
            engage(i);
            return 0;
        }
        /* step toward the player: larger axis first, then the other */
        nx = obj_x[i]; ny = obj_y[i];
        if (adx >= ady) nx += dx > 0 ? 1 : -1; else ny += dy > 0 ? 1 : -1;
        if (!monster_can_enter(nx, ny)) {
            nx = obj_x[i]; ny = obj_y[i];
            if (adx >= ady) { if (dy) ny += dy > 0 ? 1 : -1; }
            else { if (dx) nx += dx > 0 ? 1 : -1; }
            if ((nx == obj_x[i] && ny == obj_y[i]) || !monster_can_enter(nx, ny)) continue;
        }
        obj_x[i] = nx; obj_y[i] = ny;
        changed = 1;
    }
    return changed;
}

/* ---- the use button -------------------------------------------------------- */
static void use_ahead(void)
{
    unsigned char nx = px + DX[pf], ny = py + DY[pf], m = cell(nx, ny), k;
    uses++;
    calm_monsters();
    k = monster_at(nx, ny);
    if (k != 0xFF) {
        engage(k);
        return;
    } else if ((k = obj_at(nx, ny, 0)) != 0xFF && (kind_flags[obj_type[k]] & KF_SHOP)) {
        shop();
        draw_explore_hud();
        poll_presses();
        return;
    } else if ((k = wall_event(nx, ny)) != 0xFF) {   /* stairs, levers: content events */
        run_event(k);
        return;
    } else if (m == M_DOOR) {
        open_cell(nx, ny);
        SFX_DOOR();
        message("THE DOOR CREAKS OPEN");
    } else if (m == M_LOCKED) {
        if (nkeys) {
            nkeys--;
            open_cell(nx, ny);
            SFX_DOOR();
            message("THE KEY TURNS. THE DOOR|SWINGS OPEN");
        } else {
            SFX_BUMP();
            message("LOCKED. YOU NEED A KEY");
        }
    } else if (m == M_SECRET) {
        open_cell(nx, ny);
        SFX_DOOR();
        message("THE WALL SLIDES AWAY!|A SECRET PASSAGE");
    } else {
        message("NOTHING TO USE HERE");
        return;
    }
    redraw();
}

/* ---- game setup ------------------------------------------------------------ */
static void new_game(void)
{
    unsigned int j;
    unsigned char i;
    for (j = 0; j < LVLSTATE_LEN; j++) LVLSTATE[j] = 0;     /* nothing seen or opened */
    for (i = 0; i < NOBJ; i++) {
        obj_type[i] = obj_init[i * 5];
        obj_lvl[i] = obj_init[i * 5 + 1];
        obj_x[i] = obj_init[i * 5 + 2];
        obj_y[i] = obj_init[i * 5 + 3];
        obj_n[i] = obj_init[i * 5 + 4];
        obj_frame[i] = 0;
        obj_stun[i] = 0;
    }
    for (i = 0; i < 16; i++) ev_done[i] = 0;
    level = START_L;
    load_level_map(level);
    px = START_X; py = START_Y; pf = START_F;
    new_player();
    dead = 0; won = 0; map_open = 0; battle_pending = 0xFF; in_battle = 0; ending_pending = 0;
    mark_visited();
    music_play(level_music[level]);
    draw_explore_hud();
    message(text_intro);
    redraw();
}

void main(void)
{
    SMS_displayOff();
    flip_pending = 0;
    frame_count = 0; last_flip = 0; last_action = 0;
    frames_rendered = 0;
    SMS_setFrameInterruptHandler(frame_isr);
    SMS_loadBGPalette(pal_bg);
    SMS_loadSpritePalette(pal_bg);
    SMS_setBackdropColor(10);
    SMS_VRAMmemset(0, 0, 384 * 32);
    SMS_loadTiles(hud_tiles, T_BG, HUD_TILES * 32);
    SMS_initSprites();
    SMS_finalizeSprites();
    SMS_copySpritestoSAT();
    PSG_PORT = 0x9F; PSG_PORT = 0xBF; PSG_PORT = 0xDF; PSG_PORT = 0xFF;

    back_buf = 0;
    moves = turns = bumps = uses = hits_taken = kills = 0;
    sfx_timer = tone_timer = 0;
    last_frame_vblanks = 0;
    quick_mode = 0; ai_off = 0; last_msg = 0xFF; battle_pending = 0xFF;
    pad = prev_pad = 0;
    pad_edges = 0; isr_prev = 0;
    b1_armed = b1_used = 0;
    rng = 0x5A;

    SMS_useFirstHalfTilesforSprites(0);  /* sprite tiles 256+: the HUD tiles   */
    draw_static_hud();
    saves_made = loads_made = 0;
    in_title = ending_seen = in_ending = 0;
    SMS_displayOn();
    start_menu();
    game_ready = 1;

    for (;;) {
        unsigned int pressed, seen;
        pad = SMS_getKeysStatus();
        __asm__("di");
        pressed = pad_edges | (pad & ~prev_pad);
        pad_edges = 0;
        __asm__("ei");
        seen = pad | pressed;            /* held now, or tapped meanwhile      */
        rng += (unsigned char)pad;   /* stir the RNG with player timing      */

        if (dbg_level != 0xFF && anim_pos >= anim_len) {
            change_level(dbg_level, px, py, pf);
            dbg_level = 0xFF;
            draw_inventory();
            redraw();
        }
        if (anim_pos >= anim_len && ending_pending && !dead) {
            ending();
            prev_pad = pad = SMS_getKeysStatus();
            continue;
        }
        if (anim_pos >= anim_len && battle_pending != 0xFF && !dead) {
            unsigned char b = battle_pending;
            battle_pending = 0xFF;
            battle(b);                       /* blocking; draws its own screens */
            if (!dead) { draw_explore_hud(); redraw(); }
            last_action = frame_count;
            prev_pad = pad = SMS_getKeysStatus();
            continue;
        }
        if (anim_pos >= anim_len) {
            if (dead) {
                if (pressed & PORT_A_KEY_1) {
                    if (load_game()) message("YOU AWAKEN WHERE YOU|LAST SAVED...");
                    else new_game();
                }
            } else if (map_open) {
                if (pressed & (PORT_A_KEY_2 | PORT_A_KEY_1)) {
                    map_open = 0;
                    redraw();
                } else if (pressed & (PORT_A_KEY_LEFT | PORT_A_KEY_RIGHT)) {
                    quick_mode ^= 1;
                    message(quick_mode ? "STEP MODE: QUICK" : "STEP MODE: SMOOTH");
                } else if (pressed & PORT_A_KEY_UP) {     /* the first consumable */
                    if (hp == maxhp && items[0]) message("YOU ARE ALREADY HEALTHY");
                    else if (use_item(0)) message(cons_use[0]);
                }
            } else if (pressed & PORT_A_KEY_2) {
                pause_menu();                /* blocking; may open the map      */
                poll_presses();
                prev_pad = pad = SMS_getKeysStatus();
                continue;
            } else {
                unsigned char r = (pf + 1) & 3;
                if (pressed & PORT_A_KEY_1) { b1_armed = 1; b1_used = 0; }
                if (pad & PORT_A_KEY_1) {
                    if (seen & PORT_A_KEY_RIGHT) { b1_used = 1; start_move(DX[r], DY[r], 1, 1); }
                    else if (seen & PORT_A_KEY_LEFT) { b1_used = 1; start_move(-DX[r], -DY[r], 0, 1); }
                } else if (b1_armed) {       /* released without a direction  */
                    b1_armed = 0;
                    if (!b1_used) {
                        use_ahead();     /* acting costs a turn               */
                        if (battle_pending == 0xFF) {
                            monsters_turn();
                            if (battle_pending == 0xFF) redraw();
                        }
                    }
                    last_action = frame_count;
                } else if (seen & PORT_A_KEY_UP)
                    start_move(DX[pf], DY[pf], 1, 0);
                else if (seen & PORT_A_KEY_DOWN)
                    start_move(-DX[pf], -DY[pf], 0, 0);
                else if (seen & PORT_A_KEY_RIGHT)
                    start_turn(1);
                else if (seen & PORT_A_KEY_LEFT)
                    start_turn(0);
                else if ((unsigned int)(frame_count - last_action) > IDLE_TICK) {
                    last_action = frame_count;     /* monsters act while you wait */
                    calm_monsters();
                    if (monsters_turn()) redraw();
                }
            }
        }
        prev_pad = pad;

        if (anim_pos < anim_len) {
            unsigned char k = anim_pos;
            render_and_flip(seq_cx[k], seq_cy[k], seq_f[k], seq_pose[k]);
            anim_pos++;
            if (anim_pos == anim_len) {
                unsigned char moved = seq_cx[k] != px || seq_cy[k] != py, turned = seq_f[k] != pf;
                px = seq_cx[k]; py = seq_cy[k]; pf = seq_f[k];
                if (moved) { SFX_STEP(); enter_cell(); }
                if ((moved || turned) && battle_pending == 0xFF) {
                    if (monsters_turn() && anim_pos >= anim_len) redraw();
                    last_action = frame_count;
                }
            }
        } else {
            SMS_waitForVBlank();
        }
        sfx_update();
    }
}
