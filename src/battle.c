/* Turn-based battles.  A roaming monster object stands for a group of 1-3
   enemies of one kind.  The battle keeps the current first-person view as the
   backdrop and draws the group large in front of it with the same billboard
   renderer (direct mode, no depth test), so hit flashes and attack poses are
   just re-renders.  The HUD area becomes the battle panel; a hardware sprite
   arrow marks the target.  Lives in bank 0 (the game logic is in bank 1).  */
#include <SMSlib.h>
#include "engine.h"
#include "core.h"
#include "game.h"
#include "music.h"

/* Monster stats, texts and spells come from mon_tab (tools/content.py). */
#define FIRE_WEAK 16                 /* mon_tab flags bit (gen.py)              */

/* where the group stands: screen column centres and depth (q) by group size */
static const signed char LINE_X[3][3] = { { 32, 0, 0 }, { 20, 44, 0 }, { 12, 32, 52 } };
static const unsigned char LINE_Q[3] = { 92, 72, 58 };

unsigned char e_kind, e_n, e_hp[3], e_frame[3];
unsigned char bt_round, bt_result;   /* 1 won, 2 ran, 3 lost (tests)          */
unsigned char bt_say_frames = 70;    /* message pause; tests may poke it lower */

static const MonDef *md;

/* ---- text helpers ----------------------------------------------------------- */
static char sbuf[48];
static unsigned char sp;

static void sb_str(const char *s) { while (*s && sp < 47) sbuf[sp++] = *s++; sbuf[sp] = 0; }
static void sb_num(unsigned int v)
{
    char t[6];
    unsigned char n = 0;
    do { t[n++] = '0' + v % 10; v /= 10; } while (v);
    while (n && sp < 47) sbuf[sp++] = t[--n];
    sbuf[sp] = 0;
}
static void sb_start(const char *s) { sp = 0; sbuf[0] = 0; sb_str(s); }

/* new presses since the last call (latched by the VBlank handler) */
unsigned int poll_presses(void)
{
    unsigned int p;
    __asm__("di");
    p = pad_edges;
    pad_edges = 0;
    __asm__("ei");
    return p;
}

static void wait_frames(unsigned char n)
{
    while (n--) { SMS_waitForVBlank(); sfx_update(); }
}

/* show a message and pause (any button skips) */
void say(const char *s)
{
    unsigned char n = bt_say_frames;
    message(s);
    poll_presses();
    while (n--) {
        SMS_waitForVBlank();
        sfx_update();
        if (poll_presses() & (PORT_A_KEY_1 | PORT_A_KEY_2)) break;
    }
}

/* ---- drawing ------------------------------------------------------------------ */
static void render_lineup(void)
{
    unsigned char i;
    vis_n = 0;
    for (i = 0; i < e_n; i++) {
        if (!e_hp[i]) continue;
        vis_x[vis_n] = (unsigned char)LINE_X[e_n - 1][i];
        vis_y[vis_n] = LINE_Q[e_n - 1];
        vis_type[vis_n] = md->cls;
        vis_frame[vis_n] = md->frame + e_frame[i];
        vis_n++;
    }
    vis_direct = 1;
    r_cx = px; r_cy = py; r_f = pf; r_pose = 0;
    render_frame();
    vis_direct = 0;
    present(px, py, pf, 0x80);
}

static void draw_group(void)
{
    unsigned char i, alive = 0;
    for (i = 0; i < e_n; i++) if (e_hp[i]) alive++;
    clear_row(17);
    sb_start(md->name);
    if (alive > 1) { sb_str(" X"); sb_num(alive); }
    print(3, 17, sbuf);
}

static void hide_arrow(void)
{
    SMS_VDPturnOffFeature(VDPFEATURE_ZOOMSPRITES);
    SMS_initSprites();
    SMS_finalizeSprites();
    SMS_waitForVBlank();
    SMS_copySpritestoSAT();
}

static void show_arrow(unsigned char t)
{
    SMS_VDPturnOnFeature(VDPFEATURE_ZOOMSPRITES);   /* 16x16 pointer */
    SMS_initSprites();
    SMS_addSprite(VIEW_TX * 8 + LINE_X[e_n - 1][t] * 2 - 8, VIEW_TY * 8 + 4, T_ARROW - 256);
    SMS_finalizeSprites();
    SMS_waitForVBlank();
    SMS_copySpritestoSAT();
}

/* one-row menu on line 22; returns the index or 0xFF for "back" */
unsigned char ui_menu(const char **items, unsigned char n)
{
    unsigned char sel = 0, i, x;
    clear_row(22);
    clear_row(23);
    print(3, 23, "L/R CHOOSE  1 OK  2 BACK");
    for (;;) {
        for (i = 0, x = 2; i < n; i++) {
            const char *s = items[i];
            put_tile(x, 22, i == sel ? T_FONT + glyph('>') : T_BG);
            s = print(x + 1, 22, s);
            x += 2 + (unsigned char)(s - items[i]);
        }
        for (;;) {
            unsigned int p;
            SMS_waitForVBlank();
            sfx_update();
            p = poll_presses();
            if (p & PORT_A_KEY_RIGHT) { sel = sel + 1 < n ? sel + 1 : 0; break; }
            if (p & PORT_A_KEY_LEFT) { sel = sel ? sel - 1 : n - 1; break; }
            if (p & PORT_A_KEY_1) { SFX_STEP(); return sel; }
            if (p & PORT_A_KEY_2) return 0xFF;
        }
        SFX_STEP();
    }
}

/* pick a living enemy with the arrow; 0xFF = back */
static unsigned char pick_target(void)
{
    unsigned char t = 0, alive = 0, i;
    for (i = 0; i < e_n; i++) if (e_hp[i]) { alive++; t = i; }
    if (alive == 1) return t;
    for (t = 0; !e_hp[t]; t++) ;
    clear_row(22);
    print(4, 22, "WHICH ONE?");
    for (;;) {
        unsigned int p;
        show_arrow(t);
        for (;;) {
            SMS_waitForVBlank();
            sfx_update();
            p = poll_presses();
            if (p) break;
        }
        if (p & PORT_A_KEY_1) { hide_arrow(); return t; }
        if (p & PORT_A_KEY_2) { hide_arrow(); return 0xFF; }
        if (p & PORT_A_KEY_RIGHT) do { t = t + 1 < e_n ? t + 1 : 0; } while (!e_hp[t]);
        if (p & PORT_A_KEY_LEFT) do { t = t ? t - 1 : e_n - 1; } while (!e_hp[t]);
        SFX_STEP();
    }
}

/* ---- actions ----------------------------------------------------------------- */
static unsigned char roll(unsigned char atk, unsigned char def)
{
    unsigned char d = atk + rnd() % (atk / 2 + 1);
    return d > def ? d - def : 1;
}

static void hurt_enemy(unsigned char t, unsigned char dmg, const char *verb)
{
    e_hp[t] = e_hp[t] > dmg ? e_hp[t] - dmg : 0;
    e_frame[t] = 2;                          /* white flash                    */
    render_lineup();
    sb_start(verb); sb_str(md->name); sb_str(" FOR "); sb_num(dmg); sb_str("!");
    say(sbuf);
    e_frame[t] = 0;
    if (!e_hp[t]) {
        render_lineup();                     /* gone                           */
        sb_start("THE "); sb_str(md->name);
        sb_str(md->death);
        say(sbuf);
        kills++;
        draw_group();
    }
}

static const char * const MAIN_MENU[4] = { "FIGHT", "MAGIC", "ITEM", "RUN" };
static const char * const MAGIC_MENU[3] = { HEAL_LABEL, FIRE_LABEL, "BACK" };

/* returns 1 if the player escaped */
static void clear_prompt(void) { clear_row(22); clear_row(23); }

static unsigned char player_turn(void)
{
    unsigned char t, d;
    for (;;) {
        t = ui_menu((const char **)MAIN_MENU, 4);
        if (t != 1) clear_prompt();
        switch (t) {
        case 0:                                          /* FIGHT */
            t = pick_target();
            if (t == 0xFF) continue;
            clear_prompt();
            SFX_HIT();
            if ((rnd() & 15) == 1) { say("YOU SWING AND MISS!"); return 0; }
            d = roll(eff_atk(), md->def);
            if ((rnd() & 15) == 0) { d <<= 1; say("A CRITICAL HIT!"); }
            hurt_enemy(t, d, "YOU HIT THE ");
            return 0;
        case 1:                                          /* MAGIC */
            t = ui_menu((const char **)MAGIC_MENU, 3);
            clear_prompt();
            if (t == 0) {
                if (mp < HEAL_MP) { say("NOT ENOUGH MP!"); continue; }
                mp -= HEAL_MP;
                d = HEAL_BASE + plv * HEAL_LV;
                hp = hp + d > maxhp ? maxhp : hp + d;
                SFX_MAGIC();
                draw_status();
                say("A WARM LIGHT HEALS YOU");
                return 0;
            }
            if (t == 1) {
                if (mp < FIRE_MP) { say("NOT ENOUGH MP!"); continue; }
                t = pick_target();
                if (t == 0xFF) continue;
                clear_prompt();
                mp -= FIRE_MP;
                draw_status();
                SFX_MAGIC();
                d = FIRE_BASE + plv * FIRE_LV + (rnd() & 3);
                if (md->flags & FIRE_WEAK) { d <<= 1; say("THE FLAMES SEAR IT!"); }
                hurt_enemy(t, d, "FIRE BURNS THE ");
                return 0;
            }
            continue;
        case 2:                                          /* ITEM */
            if (use_item_menu()) return 0;
            continue;
        case 3:                                          /* RUN */
            if (!md->run) { say("THERE IS NO ESCAPE!"); return 0; }
            if (rnd() % 100 < md->run) { say("YOU GOT AWAY!"); return 1; }
            say("YOU CAN'T ESCAPE!");
            return 0;
        default:
            continue;
        }
    }
}

static void enemies_turn(void)
{
    unsigned char i, d;
    for (i = 0; i < e_n && hp; i++) {
        if (!e_hp[i]) continue;
        e_frame[i] = 1;                      /* attack pose                    */
        render_lineup();
        e_frame[i] = 0;
        if (md->sp_every && bt_round % md->sp_every == 0) {   /* its special attack */
            unsigned char a = md->sp_armor ? eff_def() / md->sp_armor : 0;
            d = md->sp_dmg + rnd() % md->sp_rnd;
            d = d > a ? d - a : 1;
            hp = hp > d ? hp - d : 0;
            hits_taken++;
            SFX_MAGIC();
            draw_status();
            sb_start("THE "); sb_str(md->name); sb_str(" "); sb_str(md->spell);
            sb_str(" "); sb_num(d); sb_str(" DAMAGE!");
            say(sbuf);
            continue;
        }
        if ((rnd() & 7) == 0) {
            sb_start("THE "); sb_str(md->name); sb_str(" MISSES");
            say(sbuf);
            continue;
        }
        d = roll(md->atk, eff_def());
        hp = hp > d ? hp - d : 0;
        hits_taken++;
        SFX_HURT();
        draw_status();
        sb_start("THE "); sb_str(md->name); sb_str(" HITS YOU|FOR "); sb_num(d); sb_str(" DAMAGE");
        say(sbuf);
    }
}

static void victory(void)
{
    unsigned int gx = md->xp * e_n, gg = md->gold * e_n;
    sb_start("VICTORY! "); sb_num(gx); sb_str(" XP|AND "); sb_num(gg); sb_str(" GOLD");
    say(sbuf);
    xp += gx;
    gold += gg;
    while (plv < MAX_LEVEL && xp >= next_xp[plv - 1]) {
        plv++;
        maxhp = maxhp > 99 - LV_HP ? 99 : maxhp + LV_HP;
        maxmp = maxmp > 99 - LV_MP ? 99 : maxmp + LV_MP;
        patk += LV_ATK; pdef += LV_DEF;
        hp += LV_HP; mp += LV_MP;
        if (hp > maxhp) hp = maxhp;
        if (mp > maxmp) mp = maxmp;
        draw_status();
        SFX_MAGIC();
        sb_start("LEVEL UP! YOU ARE NOW|LEVEL "); sb_num(plv);
        say(sbuf);
    }
    if (rnd() % LOOT_ONE_IN == 0 && items[LOOT_ITEM] < 99) {
        items[LOOT_ITEM]++;
        SFX_PICKUP();
        sb_start("YOU FOUND A "); sb_str(cons_name[LOOT_ITEM]); sb_str("!");
        say(sbuf);
    }
}

void new_player(void)
{
    unsigned char i;
    plv = 1;
    maxhp = hp = PL_HP;
    maxmp = mp = PL_MP;
    patk = PL_ATK; pdef = PL_DEF;
    xp = 0; gold = 0;
    for (i = 0; i < NCONS; i++) items[i] = cons_start[i];
    nkeys = PL_KEYS;
    weapon = 0; armor = 0;
}

void battle(unsigned char obj)
{
    unsigned char i, alive, y;
    in_battle = 1;
    bt_round = 0;
    e_kind = obj_type[obj];
    md = MON(e_kind);
    e_n = obj_n[obj];
    if (e_n < 1) e_n = 1;
    if (e_n > 3) e_n = 3;
    for (i = 0; i < 3; i++) { e_hp[i] = i < e_n ? md->hp : 0; e_frame[i] = 0; }

    music_play((md->flags & KF_BOSS) ? MUS_BOSS : MUS_BATTLE);
    for (y = 16; y < 24; y++) clear_row(y);
    draw_status();
    draw_group();
    render_lineup();
    if (e_n > 1) {
        sb_start(md->group); sb_str(" ");
        sb_num(e_n); sb_str(" "); sb_str(md->plural); sb_str("!");
    } else {
        sb_start("A "); sb_str(md->name); sb_str(" APPEARS!");
    }
    say(sbuf);

    for (;;) {
        bt_round++;
        if (player_turn()) {                 /* ran away                        */
            obj_stun[obj] = 4;
            bt_result = 2;
            music_play(level_music[level]);
            break;
        }
        for (alive = 0, i = 0; i < e_n; i++) if (e_hp[i]) alive++;
        if (!alive) {
            obj_type[obj] = 0;
            bt_result = 1;
            music_play_then(MUS_VICTORY, level_music[level]);
            victory();
            break;
        }
        clear_row(22); clear_row(23);
        enemies_turn();
        if (!hp) {
            bt_result = 3;
            dead = 1;
            music_play(MUS_GAMEOVER);
            SFX_HURT();
            message("YOU HAVE FALLEN...|PRESS 1 TO TRY AGAIN");
            break;
        }
    }
    hide_arrow();
    in_battle = 0;
}
