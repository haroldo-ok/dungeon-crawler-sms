#ifndef CORE_H
#define CORE_H
/* state shared with the VBlank handler (core.c, bank 0) */
extern volatile unsigned int frame_count;
extern unsigned int last_flip;
extern unsigned char last_frame_vblanks;
extern unsigned int frames_rendered;
extern unsigned char shown_cx, shown_cy, shown_f, shown_pose;
extern volatile unsigned char flip_pending;
extern volatile unsigned int pad_edges;
extern unsigned int isr_prev;
extern unsigned char pend_buf, pend_cx, pend_cy, pend_f, pend_pose;
void frame_isr(void);
void music_play(unsigned char id);                       /* no-op if already playing */
void music_play_then(unsigned char id, unsigned char after); /* jingle, then `after`    */
extern unsigned char music_cur, music_notes;
#endif
