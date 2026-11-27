#ifndef ENGINE_H
#define ENGINE_H
#include "gen.h"

/* ---- fixed RAM layout -------------------------------------------------------
   0xC000-0xC3FF  C globals (devkitSMS crt0 clears RAM from 0xC000; checked)
   0xC400-0xD3FF  chunky framebuffer: page 0xC4+g holds view columns 4g..4g+3.
                  offset = ((x>>1)&1)*128 + (x&1) + 2*row      (rows 0..47)
                  even columns hold colour<<4, odd columns colour (so a byte
                  pair ORs straight into a "two pixel" index for the c2p LUT)
   0xD400         CELL_F  floor texture page per visible cell (parity 0)
   0xD500         CELL_C  ceiling texture page per visible cell, 0 = sky
   0xD600         CELL_W  wall type+1 per visible cell, 0 = open
   0xD700         map_ram (16x16 live map)
   0xD800-0xD9BF  per-column ray results (W, page, acc, step, q)
   0xDA00-0xDA7F  cell kind tables (wall type / floor page / ceiling page per map byte)
   0xDB00         level state: visited[NLEVELS][32] then opened[NLEVELS][32]
                  (bitmaps; a level's map is rebuilt from ROM + its opened bits)
   0xDE00-0xDFF0  stack (measured: < 100 bytes deep)                                                       */
#define FB_PAGE   0xC4
#define CELL_F    ((volatile unsigned char *)0xD400)
#define CELL_C    ((volatile unsigned char *)0xD500)
#define CELL_W    ((volatile unsigned char *)0xD600)

/* Sega mapper: slot 1 (0x4000) = texture bank, slot 2 (0x8000) = pose bank.
   The texture banks (floor, walls, doors) are chosen per level (tex_*bank).
   All code must stay below 0x4000 (checked by the build).                    */
#define MAP_SLOT1(b) (*(volatile unsigned char *)0xFFFE = (b))
#define MAP_SLOT2(b) (*(volatile unsigned char *)0xFFFF = (b))

/* renderer inputs (globals so asm can read them) */
extern unsigned char r_cx, r_cy, r_f, r_pose, r_buf, flip_buf;
#define map_ram   ((unsigned char *)0xD700)

/* per-column results of the ray walk */
#define col_W    ((unsigned char *)0xD800)  /* visible half-height of the wall (rows) */
#define col_page ((unsigned char *)0xD840)  /* wall texture page in slot 1, 0 = fog   */
#define col_acc  ((unsigned int *)0xD880)   /* texture v accumulator start (8.8)      */
#define col_step ((unsigned int *)0xD900)   /* texture v step per row (8.8)           */
#define col_q    ((unsigned char *)0xD980)  /* wall depth (q, bigger = nearer)        */

void render_set_theme(unsigned char t);   /* the level's texture set + cell kinds */
extern unsigned char tex_fbank, tex_wbank, tex_wbank2;
#define LVLSTATE     ((unsigned char *)0xDB00)
#define LVLSTATE_LEN (NLEVELS * 64)
#define VISITED(l)   ((unsigned char *)0xDB00 + ((unsigned int)(l) << 5))
#define OPENED(l)    ((unsigned char *)0xDB00 + NLEVELS * 32 + ((unsigned int)(l) << 5))
void render_frame(void);             /* draws the view into the RAM framebuffer */
void render_upload(void);            /* converts + uploads it to VRAM buffer r_buf */
void show_buffer(unsigned char buf); /* call in VBlank: point the name table   */

/* asm kernels (render_asm.s) */
void asm_floor_column(void);
void asm_wall_column(void);
void asm_c2p_upload(void);
void asm_setup_cells(void);
void asm_ray_walk(void);
void asm_show_buffer(void);
void asm_spr_column(void);

/* objects to draw this frame (world cells on the current level) */
#define MAX_VIS 12
extern unsigned char vis_n, vis_direct;   /* vis_type = scale class, vis_frame = sprite frame */
extern unsigned char vis_x[MAX_VIS], vis_y[MAX_VIS], vis_frame[MAX_VIS], vis_type[MAX_VIS];
#endif
