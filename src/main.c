/* SMS Dungeon - a first-person grid dungeon crawler for the Sega Master System.
   Grid movement with smooth interpolated steps/turns, real-time texture mapped
   walls, floor and ceiling, and a sky wherever a cell has no ceiling.        */
#include <SMSlib.h>
#include "engine.h"

SMS_EMBED_SEGA_ROM_HEADER(9999, 0);
SMS_EMBED_SDSC_HEADER_AUTO_DATE(1, 0, "Claude", "SMS Dungeon", "First-person textured dungeon crawler");

__sfr __at 0xBE VDP_DATA2;
__sfr __at 0xBF VDP_CTRL2;
__sfr __at 0x7F PSG_PORT;


static const signed char DX[4] = { 0, 1, 0, -1 };
static const signed char DY[4] = { -1, 0, 1, 0 };

/* ---- game state (globals so the test harness can read/poke them) ---------- */
unsigned char px, py, pf;            /* resting cell + facing (0 N,1 E,2 S,3 W) */
unsigned char anim_len, anim_pos;
unsigned char seq_cx[8], seq_cy[8], seq_f[8], seq_pose[8];
unsigned char back_buf;
volatile unsigned int frame_count;   /* VBlank counter                         */
unsigned int last_flip;
unsigned char last_frame_vblanks;    /* VBlanks the previous rendered frame took */
unsigned int frames_rendered;
unsigned int moves, turns, bumps;
unsigned char sfx_timer;
unsigned int keys, prev_keys;
unsigned char quick_mode;            /* 0: 6 sub-steps per move, 1: 4         */
unsigned char game_ready;
unsigned char shown_cx, shown_cy, shown_f, shown_pose;   /* what is on screen */

volatile unsigned char flip_pending;  /* a finished buffer waits for VBlank */
unsigned char pend_buf, pend_cx, pend_cy, pend_f, pend_pose;

/* VBlank: swap the view buffers here so the main loop never waits for it */
static void frame_isr(void)
{
    frame_count++;
    if (flip_pending) {
        show_buffer(pend_buf);
        shown_cx = pend_cx; shown_cy = pend_cy; shown_f = pend_f; shown_pose = pend_pose;
        last_frame_vblanks = (unsigned char)(frame_count - last_flip);
        last_flip = frame_count;
        frames_rendered++;
        flip_pending = 0;
    }
}

/* ---- HUD ------------------------------------------------------------------ */
static void put_tile(unsigned char x, unsigned char y, unsigned int t)
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

static void print(unsigned char x, unsigned char y, const char *s)
{
    while (*s) {
        const char *f = FONTCHARS;
        unsigned char i = 0;
        while (f[i] && f[i] != *s) i++;
        if (!f[i]) i = 0;
        put_tile(x++, y, T_FONT + i);
        s++;
    }
}

static void print_num2(unsigned char x, unsigned char y, unsigned char v)
{
    char b[3];
    b[0] = '0' + v / 10; b[1] = '0' + v % 10; b[2] = 0;
    print(x, y, b);
}

static const char * const FACING_NAME[4] = { "NORTH", "EAST ", "SOUTH", "WEST " };

static void draw_mode(void)
{
    print(10, 19, quick_mode ? "STEPS QUICK " : "STEPS SMOOTH");
}

static void draw_status(void)
{
    print(10, 17, "FACING");
    print(17, 17, FACING_NAME[pf]);
    print(10, 18, "X");
    print_num2(12, 18, px);
    print(16, 18, "Y");
    print_num2(18, 18, py);
}

static void draw_static_hud(void)
{
    unsigned char x, y;
    /* frame around the 16x12-tile view */
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
    print(10, 0, "SMS DUNGEON");
    print(4, 21, "UP/DOWN WALK  L/R TURN");
    print(4, 22, "1+L/R STRAFE  2 STEP MODE");
}

/* ---- sound ---------------------------------------------------------------- */
unsigned char sfx_atten;

static void sfx_play(unsigned char noise, unsigned char atten, unsigned char len)
{
    PSG_PORT = 0xE0 | noise;         /* noise channel control                  */
    PSG_PORT = 0xF0 | atten;
    sfx_atten = atten;
    sfx_timer = len;
}

static void sfx_bump(void) { sfx_play(0x05, 0, 12); }      /* white noise thud */
static void sfx_step(void) { sfx_play(0x06, 5, 4); }       /* soft footstep    */

static void sfx_update(void)
{
    if (sfx_timer) {
        sfx_timer--;
        if (sfx_atten < 15) sfx_atten++;
        PSG_PORT = 0xF0 | (sfx_timer ? sfx_atten : 15);
    }
}

/* ---- movement --------------------------------------------------------------
   Poses: 0 rest, 1..5 forward k/6, 6..10 right k/6, 11..15 turned right k*15deg,
   all relative to a base cell + facing.  Moving back/left/turning left runs a
   forward/right/right-turn sequence backwards from the destination.          */
static unsigned char open_cell(unsigned char x, unsigned char y)
{
    return map_ram[((y & 15) << 4) | (x & 15)] < 16;
}

static void push(unsigned char cx, unsigned char cy, unsigned char f, unsigned char pose)
{
    seq_cx[anim_len] = cx; seq_cy[anim_len] = cy; seq_f[anim_len] = f; seq_pose[anim_len] = pose;
    anim_len++;
}

/* pose sequences: [mode][kind] , kind 0 forward, 1 lateral (right), 2 turn right */
static const unsigned char SEQ[2][3][5] = {
    { { 1, 2, 3, 4, 5 }, { 6, 7, 8, 9, 10 }, { 11, 12, 13, 14, 15 } },   /* smooth */
    { { 16, 3, 17 },     { 18, 8, 19 },      { 20, 13, 21 } },           /* quick  */
};
static const unsigned char SEQ_LEN[2] = { 5, 3 };
static void start_move(signed char dx, signed char dy, unsigned char base_first, unsigned char kind)
{
    unsigned char nx = px + dx, ny = py + dy, k, n = SEQ_LEN[quick_mode];
    const unsigned char *sq = SEQ[quick_mode][kind];
    anim_len = 0; anim_pos = 0;
    if (!open_cell(nx, ny)) {
        bumps++;
        sfx_bump();
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

static void start_turn(unsigned char right)
{
    unsigned char k, f, n = SEQ_LEN[quick_mode];
    const unsigned char *sq = SEQ[quick_mode][2];
    anim_len = 0; anim_pos = 0;
    if (right) {
        for (k = 0; k < n; k++) push(px, py, pf, sq[k]);
        f = (pf + 1) & 3;
    } else {
        f = (pf - 1) & 3;
        for (k = n; k > 0; k--) push(px, py, f, sq[k - 1]);
    }
    push(px, py, f, 0);
    turns++;
}

static void handle_input(void)
{
    unsigned char r = (pf + 1) & 3;
    if (keys & PORT_A_KEY_UP)
        start_move(DX[pf], DY[pf], 1, 0);
    else if (keys & PORT_A_KEY_DOWN)
        start_move(-DX[pf], -DY[pf], 0, 0);
    else if (keys & PORT_A_KEY_1) {
        if (keys & PORT_A_KEY_RIGHT) start_move(DX[r], DY[r], 1, 1);
        else if (keys & PORT_A_KEY_LEFT) start_move(-DX[r], -DY[r], 0, 1);
    } else if (keys & PORT_A_KEY_RIGHT)
        start_turn(1);
    else if (keys & PORT_A_KEY_LEFT)
        start_turn(0);
}

static void render_and_flip(unsigned char cx, unsigned char cy, unsigned char f, unsigned char pose)
{
    r_cx = cx; r_cy = cy; r_f = f; r_pose = pose;
    render_frame();                  /* RAM work overlaps the previous flip   */
    while (flip_pending) ;           /* back buffer still on screen?          */
    r_buf = back_buf;
    render_upload();
    pend_buf = back_buf; pend_cx = cx; pend_cy = cy; pend_f = f; pend_pose = pose;
    flip_pending = 1;
    back_buf ^= 1;
}

void main(void)
{
    unsigned int i;
    SMS_displayOff();
    flip_pending = 0;
    frame_count = 0; last_flip = 0;
    frames_rendered = 0;
    SMS_setFrameInterruptHandler(frame_isr);
    SMS_loadBGPalette(pal_bg);
    SMS_loadSpritePalette(pal_bg);
    SMS_setBackdropColor(10);
    SMS_VRAMmemset(0, 0, 384 * 32);
    SMS_loadTiles(hud_tiles, T_BG, HUD_TILES * 32);
    VDP_CTRL2 = 0x00; VDP_CTRL2 = 0x38 | 0x40;
    for (i = 0; i < 32 * 24; i++) { VDP_DATA2 = T_BG & 255; VDP_DATA2 = T_BG >> 8; }
    SMS_initSprites();
    SMS_finalizeSprites();
    SMS_copySpritestoSAT();
    PSG_PORT = 0x9F; PSG_PORT = 0xBF; PSG_PORT = 0xDF; PSG_PORT = 0xFF;

    for (i = 0; i < 256; i++) map_ram[i] = map_init[i];
    render_init();
    px = START_X; py = START_Y; pf = START_F;
    anim_len = anim_pos = 0;
    back_buf = 0;
    flip_pending = 0;
    frame_count = 0; last_flip = 0;
    frames_rendered = 0; moves = turns = bumps = 0;
    sfx_timer = 0;
    last_frame_vblanks = 0;

    quick_mode = 0;
    keys = prev_keys = 0;
    draw_static_hud();
    draw_status();
    draw_mode();
    SMS_displayOn();

    render_and_flip(px, py, pf, 0);
    game_ready = 1;

    for (;;) {
        keys = SMS_getKeysStatus();
        if ((keys & ~prev_keys) & PORT_A_KEY_2) {
            quick_mode ^= 1;
            draw_mode();
        }
        prev_keys = keys;
        if (anim_pos >= anim_len) handle_input();
        if (anim_pos < anim_len) {
            unsigned char k = anim_pos;
            render_and_flip(seq_cx[k], seq_cy[k], seq_f[k], seq_pose[k]);
            anim_pos++;
            if (anim_pos == anim_len) {
                if (seq_cx[k] != px || seq_cy[k] != py) sfx_step();
                px = seq_cx[k]; py = seq_cy[k]; pf = seq_f[k];
                draw_status();
            }
        } else {
            SMS_waitForVBlank();
        }
        sfx_update();
    }
}
