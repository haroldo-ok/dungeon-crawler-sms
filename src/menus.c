/* Out-of-battle menus: equipment, items, the merchant (shop + inn), the
   status screen, the pause menu and the battery save.  Bank 0.

   Battery save: cartridge RAM is paged into slot 2 (0x8000) by setting bit 3
   of the mapper control register 0xFFFC.  Slot 2 normally holds the pose
   bank, so the save code runs only between frames and nothing it needs lives
   in slot 2.  The saved block is the level state (0xDB00: visited + opened
   bitmaps, so a map is rebuilt from ROM) followed by the state block
   (state.c, state_begin..state_end) - no pointers, only ids and counters, so
   saves survive rebuilds that keep state.c's layout.                        */
#include <SMSlib.h>
#include "engine.h"
#include "core.h"
#include "game.h"

/* ---- equipment & items (tables in gen.c, from tools/content.py) ----------- */
unsigned char saves_made, loads_made;

unsigned char eff_atk(void) { return patk + weapon_atk[weapon < NWEAPONS ? weapon : 0]; }
unsigned char eff_def(void) { return pdef + armor_def[armor < NARMORS ? armor : 0]; }

static char mbuf[48];
static unsigned char mp_;
static void mb_str(const char *s) { while (*s && mp_ < 47) mbuf[mp_++] = *s++; mbuf[mp_] = 0; }
static void mb_num(unsigned int v)
{
    char t[6];
    unsigned char n = 0;
    do { t[n++] = '0' + v % 10; v /= 10; } while (v);
    while (n && mp_ < 47) mbuf[mp_++] = t[--n];
    mbuf[mp_] = 0;
}
static void mb_start(const char *s) { mp_ = 0; mbuf[0] = 0; mb_str(s); }

static const char *menu[5];          /* menus built from the item tables         */

static void sfx_kind(unsigned char k)
{
    if (k == 2) SFX_MAGIC(); else if (k == 1) SFX_DOOR(); else SFX_PICKUP();
}

/* drink / use consumable i; 0 if you have none */
unsigned char use_item(unsigned char i)
{
    if (!items[i]) {
        mb_start("YOU HAVE NO "); mb_str(cons_name[i]); mb_str("S");
        message(mbuf);
        return 0;
    }
    items[i]--;
    hp = hp + cons_hp[i] > maxhp ? maxhp : hp + cons_hp[i];
    mp = mp + cons_mp[i] > maxmp ? maxmp : mp + cons_mp[i];
    sfx_kind(cons_sfx[i]);
    draw_status();
    draw_inventory();
    return 1;
}

/* used from the pause menu and in battle; 1 if something was used */
unsigned char use_item_menu(void)
{
    unsigned char i;
    mb_start("");
    for (i = 0; i < NCONS; i++) {
        mb_str(cons_name[i]); mb_str(" "); mb_num(items[i]);
        if (i + 1 < NCONS) mb_str("  ");
        menu[i] = cons_name[i];
    }
    menu[NCONS] = "BACK";
    message(mbuf);
    i = ui_menu(menu, NCONS + 1);
    if (i >= NCONS) return 0;
    if (!use_item(i)) { say(mbuf); return 0; }
    say(cons_use[i]);
    return 1;
}

/* ---- the merchant: stock depends on the level (shop_* tables) --------------- */
static const char * const SHOP_MENU[4] = { "WEAPON", "ARMOR", "ITEMS", "INN" };
static const char * const BUY_MENU[2] = { "BUY", "NO" };

static unsigned char pay(unsigned int cost)
{
    if (gold < cost) { say("YOU CAN'T AFFORD THAT"); return 0; }
    gold -= cost;
    SFX_PICKUP();
    draw_inventory();
    return 1;
}

/* offer the next tier of weapon or armour, if this merchant stocks it */
static void offer(unsigned char is_armor)
{
    unsigned char cur = is_armor ? armor : weapon, nxt = cur + 1;
    const char *name;
    unsigned int cost;
    if (nxt > (is_armor ? shop_amax[level] : shop_wmax[level])) {
        say(is_armor ? "YOU WEAR THE BEST ARMOR|I HAVE" : "YOU CARRY THE FINEST|BLADE I HAVE");
        return;
    }
    cost = is_armor ? armor_cost[nxt] : weapon_cost[nxt];
    name = is_armor ? armor_name[nxt] : weapon_name[nxt];
    mb_start(name);
    mb_str(" +");
    mb_num(is_armor ? armor_def[nxt] : weapon_atk[nxt]);
    mb_str(is_armor ? " DEF|FOR " : " ATK|FOR ");
    mb_num(cost);
    mb_str(" GOLD. BUY IT?");
    message(mbuf);
    if (ui_menu((const char **)BUY_MENU, 2) != 0) return;
    if (!pay(cost)) return;
    if (is_armor) armor = nxt; else weapon = nxt;
    mb_start("YOU EQUIP THE ");
    mb_str(name);
    say(mbuf);
}

static void goods(void)
{
    unsigned char i, n, sel, which[NCONS];
    for (;;) {
        mb_start("");
        for (i = n = 0; i < NCONS; i++) {
            if (!(shop_goods[level] & (1 << i))) continue;
            if (n) mb_str("  ");
            mb_str(cons_name[i]); mb_str(" "); mb_num(cons_cost[i]); mb_str("G");
            menu[n] = cons_name[i];
            which[n++] = i;
        }
        menu[n] = "BACK";
        message(mbuf);
        sel = ui_menu(menu, n + 1);
        if (sel >= n) return;
        i = which[sel];
        if (pay(cons_cost[i])) {
            if (items[i] < 99) items[i]++;
            draw_inventory();
            mb_start("ONE "); mb_str(cons_name[i]); mb_str(". ANYTHING ELSE?");
            say(mbuf);
        }
    }
}

void shop(void)
{
    unsigned char y;
    for (y = 19; y < 24; y++) clear_row(y);
    say("WELCOME, TRAVELLER!|WHAT WILL IT BE?");
    for (;;) {
        mb_start("YOUR GOLD: "); mb_num(gold);
        message(mbuf);
        switch (ui_menu((const char **)SHOP_MENU, 4)) {
        case 0: offer(0); break;
        case 1: offer(1); break;
        case 2: goods(); break;
        case 3:
            mb_start("A WARM BED FOR "); mb_num(shop_inn[level]); mb_str(" GOLD.|STAY THE NIGHT?");
            message(mbuf);
            if (ui_menu((const char **)BUY_MENU, 2) == 0 && pay(shop_inn[level])) {
                hp = maxhp; mp = maxmp;
                draw_status();
                SFX_MAGIC();
                say("YOU SLEEP SOUNDLY AND|WAKE FULLY RESTORED");
            }
            break;
        default:
            say("SAFE TRAVELS!");
            return;
        }
    }
}

/* ---- status screen ------------------------------------------------------------ */
static void status_screen(void)
{
    unsigned char y;
    for (y = 16; y < 24; y++) clear_row(y);
    print(3, 16, "LV");  print_num2(6, 16, plv);
    print(10, 16, "XP"); print_num(13, 16, xp, 4);
    if (plv < MAX_LEVEL) { print(19, 16, "NEXT"); print_num(24, 16, next_xp[plv - 1], 4); }
    print(3, 17, "HP");  print_num2(6, 17, hp); print(8, 17, "/"); print_num2(9, 17, maxhp);
    print(13, 17, "MP"); print_num2(16, 17, mp); print(18, 17, "/"); print_num2(19, 17, maxmp);
    print(3, 18, "ATTACK");  print_num2(10, 18, eff_atk());
    print(14, 18, "DEFENSE"); print_num2(22, 18, eff_def());
    print(3, 19, "WEAPON"); print(10, 19, weapon_name[weapon < NWEAPONS ? weapon : 0]);
    print(3, 20, "ARMOR");  print(10, 20, armor_name[armor < NARMORS ? armor : 0]);
    for (y = 0; y < NCONS; y++) {
        print(3 + y * 8, 21, cons_hud[y]);
        print_num2(7 + y * 8, 21, items[y]);
    }
    print(3, 23, "PRESS A BUTTON");
    poll_presses();
    while (!(poll_presses() & (PORT_A_KEY_1 | PORT_A_KEY_2))) { SMS_waitForVBlank(); sfx_update(); }
}

/* ---- pause menu (button 2) ------------------------------------------------------ */
static const char * const PAUSE_MENU[4] = { "MAP", "ITEM", "STATUS", "SAVE" };

void pause_menu(void)
{
    unsigned char y;
    for (y = 19; y < 24; y++) clear_row(y);
    message("PAUSED");
    switch (ui_menu((const char **)PAUSE_MENU, 4)) {
    case 0:
        draw_explore_hud();
        open_automap();
        return;
    case 1:
        use_item_menu();
        break;
    case 2:
        status_screen();
        break;
    case 3:
        if (save_game()) say("YOUR PROGRESS IS SAVED");
        else say("THE SAVE FAILED!");
        break;
    }
    draw_explore_hud();
}

/* ---- battery save --------------------------------------------------------------- */
extern unsigned char state_begin, state_end;
#define MAPS       LVLSTATE                  /* visited + opened bitmaps       */
#define MAPS_LEN   LVLSTATE_LEN
#define SRAM       ((volatile unsigned char *)0x8000)
#define SRAM_ON()  (*(volatile unsigned char *)0xFFFC = 0x08)
#define SRAM_OFF() (*(volatile unsigned char *)0xFFFC = 0x00)
static const char MAGIC[4] = { 'S', 'D', 'G', 3 };

/* the save = level state + the state block, treated as one byte stream */
static unsigned int state_len(void) { return (unsigned int)(&state_end - &state_begin) + 1; }
static unsigned int save_len(void) { return MAPS_LEN + state_len(); }
static unsigned char *save_byte(unsigned int i)
{
    return i < MAPS_LEN ? MAPS + i : &state_begin + (i - MAPS_LEN);
}

static unsigned int checksum(unsigned int n)
{
    unsigned int s = 0x1234, i;
    for (i = 0; i < n; i++) s = (s << 1 | s >> 15) ^ *save_byte(i);
    return s;
}

/* header: magic[4], length[2], data, checksum[2] */
unsigned char save_valid(void)
{
    unsigned int n, i, c, s = 0x1234;
    unsigned char ok = 1;
    SRAM_ON();
    for (i = 0; i < 4; i++) if (SRAM[i] != (unsigned char)MAGIC[i]) ok = 0;
    n = SRAM[4] | (SRAM[5] << 8);
    if (n != save_len()) ok = 0;
    if (ok) {
        for (i = 0; i < n; i++) s = (s << 1 | s >> 15) ^ SRAM[6 + i];
        c = SRAM[6 + n] | (SRAM[7 + n] << 8);
        if (c != s) ok = 0;
    }
    SRAM_OFF();
    return ok;
}

unsigned char save_game(void)
{
    unsigned int n, i, c;
    unsigned char ok;
    n = save_len();
    c = checksum(n);
    SRAM_ON();
    for (i = 0; i < 4; i++) SRAM[i] = MAGIC[i];
    SRAM[4] = n & 255; SRAM[5] = n >> 8;
    for (i = 0; i < n; i++) SRAM[6 + i] = *save_byte(i);
    SRAM[6 + n] = c & 255; SRAM[7 + n] = c >> 8;
    SRAM_OFF();
    ok = save_valid();                       /* read back and verify           */
    if (ok) { saves_made++; SFX_PICKUP(); }
    return ok;
}

unsigned char load_game(void)
{
    unsigned int n = save_len(), i;
    if (!save_valid()) return 0;
    SRAM_ON();
    for (i = 0; i < n; i++) *save_byte(i) = SRAM[6 + i];
    SRAM_OFF();
    loads_made++;
    after_load();
    return 1;
}
