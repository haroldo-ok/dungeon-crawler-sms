/* Real-time renderer: walls, floor, ceiling and sky into a chunky RAM buffer,
   then chunky->planar conversion straight into a back buffer in VRAM.

   Per-pose ray tables (generated offline, one ROM bank per camera pose) list,
   for every screen column, the cells the ray crosses with the wall distance and
   texture column at each crossing, and for every floor row the cell + texel
   it samples.  At run time we look the cells up in the live map, stop each ray
   at the first solid cell and texture-map wall, floor, ceiling or sky from it. */
#include <SMSlib.h>
#include "engine.h"

__sfr __at 0xBE VDP_DATA;
__sfr __at 0xBF VDP_CTRL;

unsigned char r_cx, r_cy, r_f, r_pose, r_buf, flip_buf;

/* kernel parameters shared with the asm (render_asm.s) */
unsigned char k_x;                   /* current column                         */

#define QW   ((const unsigned char *)0x8000)
#define QV0L ((const unsigned char *)0x8100)
#define QV0H ((const unsigned char *)0x8200)
#define QSL  ((const unsigned char *)0x8300)
#define QSH  ((const unsigned char *)0x8400)
#define HDR  ((const unsigned char *)POSE_HDR)
#define COLTAB (HDR + 16)

#define XK ((unsigned char *)0xDA00)   /* RAM copy of cell_kind: W at +0, F at +0x20, C at +0x60 */

#ifndef ASM_CELLS
static void setup_cells(void)
{
    unsigned char n = HDR[0], i, base = (r_cy << 4) + r_cx;
    const unsigned char *d = (const unsigned char *)(0x8500 + ((unsigned int)r_f << 8));
    for (i = 0; i < n; i++) {
        unsigned char m = map_ram[(unsigned char)(base + d[i])];
        CELL_W[i] = XK[m];
        CELL_F[i] = XK[0x20 + m];
        CELL_C[i] = XK[0x60 + m];
    }
    CELL_W[255] = 0x80;
}
#endif

#ifndef ASM_RAYS
static void ray_walk(void)
{
    unsigned char x;
    for (x = 0; x < 64; x++) {
        const unsigned char *rp = *(const unsigned char * const *)(COLTAB + 4 * x);
        unsigned char ci, q, wt;
        for (;;) {
            ci = rp[0];
            if (ci == 0xFF) { q = rp[1]; wt = 0; break; }
            wt = CELL_W[ci];
            if (wt) { q = rp[1]; if (wt & 0x80) wt = 0; break; }
            rp += 3;
        }
        col_W[x] = QW[q];
        if (wt) {
            unsigned char tcs = rp[2], tc = tcs & 31;
            unsigned char shade = ((tcs >> 7) ^ r_f) & 1;
            col_page[x] = 0x40 + (((((wt - 1) << 1) + shade) << 1) + (x & 1) << 2) + (tc >> 3);
            col_acc[x] = ((unsigned int)((tc & 7) << 5) << 8) + (QV0L[q] | (QV0H[q] << 8));
            col_step[x] = QSL[q] | (QSH[q] << 8);
        } else {
            col_page[x] = 0;
        }
    }
}
#endif

static unsigned char *fb_col(unsigned char x)
{
    return (unsigned char *)(((unsigned int)(FB_PAGE + (x >> 2)) << 8) | (((x >> 1) & 1) << 7) | (x & 1));
}

#ifndef ASM_FLOOR
static void floor_column(void)
{
    unsigned char x = k_x, par = x & 1, fp2 = par + (r_f << 1);
    unsigned char rows = 24 - col_W[x];
    unsigned char *fl = fb_col(x) + 2 * 47;
    unsigned char *ce = fb_col(x);
    const unsigned char *fp = *(const unsigned char * const *)(COLTAB + 4 * x + 2);
    const unsigned char *sky = (const unsigned char *)(0x4800 + par * 1536 + ((HDR[1] + x) & 63) * 24);
    while (rows) {
        unsigned char ci = fp[0], cnt = fp[1], k, j;
        const unsigned char *ft = (const unsigned char *)((unsigned int)(CELL_F[ci] + fp2) << 8);
        unsigned char cp = CELL_C[ci];
        const unsigned char *offs = fp + 2;
        k = cnt < rows ? cnt : rows;
        if (cp) {
            const unsigned char *ct = (const unsigned char *)((unsigned int)(cp + fp2) << 8);
            for (j = 0; j < k; j++) {
                unsigned char o = offs[j];
                *fl = ft[o]; fl -= 2;
                *ce = ct[o]; ce += 2;
            }
        } else {
            for (j = 0; j < k; j++) {
                *fl = ft[offs[j]]; fl -= 2;
                *ce = *sky; ce += 2;
                sky++;
            }
            sky -= k;
        }
        sky += k;
        fp += 2 + cnt;
        rows -= k;
    }
}
#endif

#ifndef ASM_WALL
static void wall_column(void)
{
    unsigned char x = k_x, w = col_W[x], n;
    unsigned char *p;
    if (!w) return;
    p = fb_col(x) + 2 * (24 - w);
    n = 2 * w;
    if (col_page[x]) {
        unsigned int acc = col_acc[x], st = col_step[x];
        unsigned char pg = col_page[x];
        while (n--) {
            *p = *(const unsigned char *)(((unsigned int)pg << 8) | (acc >> 8));
            p += 2;
            acc += st;
        }
    } else {
        while (n--) { *p = 0; p += 2; }
    }
}
#endif

#ifndef ASM_C2P
static void c2p_upload(void)
{
    unsigned int addr = (unsigned int)r_buf * 6144;
    unsigned char g, lr;
    const unsigned char *lut = (const unsigned char *)0x4000;
    __asm__("di");                   /* keep the ISR off the VDP address latch */
    VDP_CTRL = addr & 255;
    VDP_CTRL = (addr >> 8) | 0x40;
    __asm__("ei");
    for (g = 0; g < 16; g++) {
        const unsigned char *fb = (const unsigned char *)((unsigned int)(FB_PAGE + g) << 8);
        for (lr = 0; lr < 48; lr++) {
            unsigned char a = fb[2 * lr] | fb[2 * lr + 1];
            unsigned char b = fb[128 + 2 * lr] | fb[128 + 2 * lr + 1];
            unsigned char v0 = lut[a] | lut[1024 + b];
            unsigned char v1 = lut[256 + a] | lut[1280 + b];
            unsigned char v2 = lut[512 + a] | lut[1536 + b];
            unsigned char v3 = lut[768 + a] | lut[1792 + b];
            VDP_DATA = v0; VDP_DATA = v1; VDP_DATA = v2; VDP_DATA = v3;
            VDP_DATA = v0; VDP_DATA = v1; VDP_DATA = v2; VDP_DATA = v3;
        }
    }
}
#endif


unsigned char prof_stage;            /* which stage is running (for profiling) */

void render_frame(void)
{
    MAP_SLOT2(POSE_BANK0 + r_pose);  /* this pose's ray tables              */
    MAP_SLOT1(FLOOR_BANK);           /* floor/ceiling/sky textures           */
    prof_stage = 1;
#ifdef ASM_CELLS
    asm_setup_cells();
#else
    setup_cells();
#endif
    prof_stage = 2;
#ifdef ASM_RAYS
    asm_ray_walk();
#else
    ray_walk();
#endif
    prof_stage = 3;
#ifdef ASM_FLOOR
    asm_floor_column();
#else
    for (k_x = 0; k_x < 64; k_x++) floor_column();
#endif
    prof_stage = 4;
    MAP_SLOT1(WALL_BANK);
#ifdef ASM_WALL
    asm_wall_column();
#else
    for (k_x = 0; k_x < 64; k_x++) wall_column();
#endif
    prof_stage = 0;
}

/* chunky->planar into VRAM buffer r_buf (must not be the one on screen) */
void render_upload(void)
{
    prof_stage = 5;
    MAP_SLOT1(FLOOR_BANK);
#ifdef ASM_C2P
    asm_c2p_upload();
#else
    c2p_upload();
#endif
    prof_stage = 0;
}

void render_init(void)
{
    unsigned char i;
    for (i = 0; i < 128; i++) XK[i] = cell_kind[i];
}

void show_buffer(unsigned char buf)
{
#ifdef ASM_SHOW
    flip_buf = buf;
    asm_show_buffer();
#else
    const unsigned char *src = view_nt + (unsigned int)buf * 384;
    unsigned char ty, i;
    for (ty = 0; ty < 12; ty++) {
        unsigned int a = 0x3800 + ((VIEW_TY + ty) * 32 + VIEW_TX) * 2;
        VDP_CTRL = a & 255;
        VDP_CTRL = (a >> 8) | 0x40;
        for (i = 0; i < 32; i++) VDP_DATA = *src++;
    }
#endif
}
