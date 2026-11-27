/* Bank-0 part of the game: everything the VBlank interrupt touches.  Game
   logic lives in ROM bank 1 (0x4000), which the renderer borrows for textures
   while it runs, so the interrupt handler must not live there.             */
#include <SMSlib.h>
#include "engine.h"
#include "core.h"

volatile unsigned int frame_count;   /* VBlank counter                         */
unsigned int last_flip;
unsigned char last_frame_vblanks;    /* VBlanks the previous rendered frame took */
unsigned int frames_rendered;
unsigned char shown_cx, shown_cy, shown_f, shown_pose;   /* what is on screen */
volatile unsigned char flip_pending;  /* a finished buffer waits for VBlank */
volatile unsigned int pad_edges;     /* buttons newly pressed since last poll  */
unsigned int isr_prev;
unsigned char pend_buf, pend_cx, pend_cy, pend_f, pend_pose;

/* VBlank: swap the view buffers here so the main loop never waits for it */
static void music_frame(void);

void frame_isr(void)
{
    frame_count++;
    music_frame();
    {                                    /* taps during a long render count */
        unsigned int cur = SMS_getKeysStatus();
        pad_edges |= cur & ~isr_prev;
        isr_prev = cur;
    }
    if (flip_pending) {
        show_buffer(pend_buf);
        shown_cx = pend_cx; shown_cy = pend_cy; shown_f = pend_f; shown_pose = pend_pose;
        last_frame_vblanks = (unsigned char)(frame_count - last_flip);
        last_flip = frame_count;
        frames_rendered++;
        flip_pending = 0;
    }
}


/* ---- music ------------------------------------------------------------------
   Two voices on PSG tone channels 1 (melody) and 2 (bass), stepped from the
   VBlank interrupt; sound effects keep tone channel 0 and the noise channel.
   Song data (gen/music.c, from tools/music.py) lives in bank 0 because the
   interrupt can fire while the renderer has other banks mapped.            */
#include "music.h"
__sfr __at 0x7F PSG_OUT;

typedef struct {
    const unsigned char *start, *p;
    unsigned char wait, att, base, floor_, slow, cnt, ch, done;
} Voice;

static Voice mv[2];
unsigned char music_cur = MUS_NONE;  /* playing song id (tests read this)     */
unsigned char music_after = MUS_NONE;/* song to start when a jingle ends      */
unsigned char music_tempo, music_tick, music_notes;

static void voice_vol(Voice *v, unsigned char a) { PSG_OUT = 0x90 | (v->ch << 5) | a; }

static void voice_step(Voice *v)
{
    unsigned char b;
    if (v->done || --v->wait) return;
    b = *v->p++;
    if (b == 0xFF) { v->p = v->start; b = *v->p++; }
    if (b == 0xFE) { v->done = 1; voice_vol(v, 15); return; }
    if (b == 0x40) {
        voice_vol(v, 15);
    } else {
        unsigned int per = music_period[b];
        PSG_OUT = 0x80 | (v->ch << 5) | (per & 15);
        PSG_OUT = (per >> 4) & 0x3F;
        v->att = v->base;
        v->cnt = 0;
        voice_vol(v, v->att);
        music_notes++;
    }
    v->wait = *v->p++;
}

static void start_song(unsigned char id)
{
    const Song *s;
    music_cur = id;
    if (id == MUS_NONE) {
        PSG_OUT = 0xBF; PSG_OUT = 0xDF;
        return;
    }
    s = &music_songs[id];
    mv[0].start = mv[0].p = s->mel;  mv[0].ch = 1; mv[0].base = 3; mv[0].floor_ = 9;  mv[0].slow = 3;
    mv[1].start = mv[1].p = s->bass; mv[1].ch = 2; mv[1].base = 5; mv[1].floor_ = 9;  mv[1].slow = 5;
    mv[0].wait = mv[1].wait = 1;
    mv[0].done = mv[1].done = 0;
    music_tempo = s->tempo;
    music_tick = 1;
}

/* called from frame_isr */
static void music_frame(void)
{
    unsigned char i;
    if (music_cur == MUS_NONE) return;
    for (i = 0; i < 2; i++) {                /* gentle decay envelope           */
        Voice *v = &mv[i];
        if (!v->done && v->att < v->floor_ && ++v->cnt >= v->slow) {
            v->cnt = 0;
            v->att++;
            voice_vol(v, v->att);
        }
    }
    if (--music_tick) return;
    music_tick = music_tempo;
    voice_step(&mv[0]);
    voice_step(&mv[1]);
    if (mv[0].done && mv[1].done) {          /* a jingle finished               */
        unsigned char nxt = music_after;
        music_after = MUS_NONE;
        start_song(nxt);
    }
}

void music_play(unsigned char id)
{
    if (id == music_cur) return;
    __asm__("di");
    music_after = MUS_NONE;
    start_song(id);
    __asm__("ei");
}

void music_play_then(unsigned char id, unsigned char after)
{
    __asm__("di");
    start_song(id);
    music_after = after;
    __asm__("ei");
}
