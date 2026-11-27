;; Hot loops of the renderer, hand-written Z80.  See render.c for the C
;; reference versions (the build can use either; outputs are pixel-identical).
;;
;; Fixed RAM (engine.h):  FB pages 0xC4..0xD3, CELL_F 0xD4xx, CELL_C 0xD5xx,
;; CELL_W 0xD6xx, map 0xD7xx, col_W 0xD800, col_page 0xD840, col_acc 0xD880,
;; col_step 0xD900, cell kinds 0xDA00 (W) / 0xDA20 (floor) / 0xDA60 (ceiling).
;; Slot 2 (0x8000) = pose bank: q tables 0x80..0x84, map deltas 0x85..0x88, header 0x8900.
;; Slot 1 (0x4000) = floor bank (c2p LUT 0x40-0x47, sky 0x4800, flats 0x54+)
;;                or wall bank.

        .module render_asm
        .globl  _asm_setup_cells
        .globl  _asm_ray_walk
        .globl  _asm_floor_column
        .globl  _asm_wall_column
        .globl  _asm_c2p_upload
        .globl  _asm_show_buffer
        .globl  _asm_spr_column
        .globl  _wc_pass, _wall_b_used, _spr_fb, _spr_n, _spr_acc, _spr_step, _spr_page
        .globl  _r_cx, _r_cy, _r_f, _r_buf, _flip_buf

FBPAGE  = 0xC4
CELLF   = 0xD4
CELLC   = 0xD5
CELLW   = 0xD6
MAPPG   = 0xD7
COLW    = 0xD800
COLPAGE = 0xD840
COLACC  = 0xD880
COLSTEP = 0xD900
FLUT    = 0xD980
CLUT    = 0xD990
HDR     = 0x8900
COLTAB  = 0x8910
DELTAPG = 0x85
XKPG    = 0xDA
VDPDATA = 0xBE
VDPCTRL = 0xBF

        .area   _DATA
fl_x:       .ds 1      ; current column
fl_par:     .ds 1
fl_rows:    .ds 1
fl_sky:     .ds 2
fl_f2:      .ds 1      ; facing&1 (wall shading)
fl_k:       .ds 1
fl_fp:      .ds 1      ; 2*facing + parity (flat texture page offset)

        .area   _CODE

;; ---------------------------------------------------------------------------
;; asm_setup_cells: for every cell of the pose, look up the live map through
;; the pose's packed index deltas for this facing and fill CELL_W/F/C from the
;; cell-kind tables (W at 0xDA00+m, floor page 0xDA20+m, ceiling page 0xDA60+m).
;; ---------------------------------------------------------------------------
_asm_setup_cells:
        ld      a,#0x80                 ; sentinel: ray terminator 0xFF "hits"
        ld      (#CELLW*256+0xFF),a
        ld      a,(#HDR)
        or      a
        ret     z
        dec     a
        ld      e,a                     ; E = i (counts down)
        ld      a,(_r_f)
        add     a,#DELTAPG
        ld      b,a                     ; B = delta page
        ld      a,(_r_cy)
        add     a,a
        add     a,a
        add     a,a
        add     a,a
        ld      hl,#_r_cx
        add     a,(hl)
        ld      c,a                     ; C = cy*16+cx
sc_loop:
        ld      d,b
        ld      a,(de)                  ; delta
        add     a,c
        ld      l,a
        ld      h,#MAPPG
        ld      l,(hl)                  ; m
        ld      h,#XKPG
        ld      a,(hl)                  ; wall type+1
        ld      d,#CELLW
        ld      (de),a
        set     5,l
        ld      a,(hl)                  ; floor page
        ld      d,#CELLF
        ld      (de),a
        set     6,l
        ld      a,(hl)                  ; ceiling page
        inc     d
        ld      (de),a
        ld      a,e
        or      a
        ret     z
        dec     e
        jr      sc_loop

;; ---------------------------------------------------------------------------
;; asm_ray_walk: for each column walk the pose's ray list until a solid cell
;; (or the 0xFF terminator = fog) and store wall height / texture setup.
;; ---------------------------------------------------------------------------
_asm_ray_walk:
        push    ix
        ld      a,(_r_f)
        and     #1
        ld      (fl_f2),a
        ld      ix,#COLTAB
        xor     a
        ld      (fl_x),a
rw_col:
        ld      l,0(ix)
        ld      h,1(ix)                 ; HL = ray list
        ld      d,#CELLW
rw_step:
        ld      e,(hl)
        ld      a,(de)
        or      a
        jr      nz,rw_hit
        inc     hl
        inc     hl
        inc     hl
        ld      e,(hl)
        ld      a,(de)
        or      a
        jr      nz,rw_hit
        inc     hl
        inc     hl
        inc     hl
        jr      rw_step
rw_hit:
        ld      b,a                     ; B = wall type+1 (0x80 = fog)
        inc     hl
        ld      c,(hl)                  ; C = q
        inc     hl
        ld      a,(hl)                  ; tcs
        ld      e,a
        ; col_W[x] = QW[q]
        ld      h,#0x80
        ld      l,c
        ld      d,(hl)                  ; D = W
        ld      a,(fl_x)
        ld      l,a
        ld      h,#>COLW
        ld      (hl),d
        ld      h,#0xD9
        set     7,l                     ; col_q = 0xD980 + x (depth for sprites)
        ld      (hl),c
        ld      h,#>COLW
        res     7,l
        bit     7,b
        jr      z,rw_wall
        ld      l,a
        set     6,l                     ; col_page = 0xD840 + x
        ld      (hl),#0
        jr      rw_next
rw_wall:
        ; page = 0x40 + (wt-1)*16 + shade*8 + par*4 + (tc>>3)
        ld      a,b
        dec     a
        add     a,a
        add     a,a
        add     a,a
        add     a,a
        add     a,#0x40
        ld      b,a
        ld      a,e
        rlca                            ; side -> bit 0
        and     #1
        ld      hl,#fl_f2
        xor     (hl)
        add     a,a
        add     a,a
        add     a,a
        add     a,b
        ld      b,a
        ld      a,(fl_x)
        and     #1
        add     a,a
        add     a,a
        add     a,b
        ld      b,a
        ld      a,e
        and     #31
        ld      d,a                     ; D = tc
        rrca
        rrca
        rrca
        and     #3
        add     a,b
        ld      b,a                     ; B = page
        bit     7,b
        jr      z,rw_pa
        ld      a,#1
        ld      (_wall_b_used),a        ; a door/stairs face is in view
rw_pa:  ld      a,(fl_x)
        ld      l,a
        ld      h,#>COLW
        set     6,l
        ld      (hl),b                  ; col_page
        ; acc = ((tc&7)<<5)<<8 + v0[q]
        ld      a,d
        and     #7
        rrca
        rrca
        rrca                            ; (tc&7)<<5
        ld      d,a
        ld      h,#0x81
        ld      l,c
        ld      e,(hl)                  ; v0 lo
        inc     h
        ld      a,(hl)                  ; v0 hi
        add     a,d
        ld      d,a                     ; DE = acc
        inc     h
        ld      b,(hl)                  ; step lo
        inc     h
        ld      c,(hl)                  ; step hi
        ld      a,(fl_x)
        add     a,a
        ld      l,a
        ld      h,#>COLACC
        set     7,l                     ; 0xD880 + 2x
        ld      (hl),e
        inc     l
        ld      (hl),d
        dec     l
        res     7,l
        inc     h                       ; 0xD900 + 2x
        ld      (hl),b
        inc     l
        ld      (hl),c
rw_next:
        ld      de,#4
        add     ix,de
        ld      hl,#fl_x
        inc     (hl)
        ld      a,(hl)
        cp      #64
        jp      c,rw_col
        pop     ix
        ret

;; ---------------------------------------------------------------------------
;; asm_floor_column: floor + ceiling (or sky) for all 64 columns.
;; Floor rows are drawn from the bottom up to the wall; the ceiling row is the
;; mirror and shares the texel offset.  Inner loops (shadow set active):
;;   main:   BC = texel-offset stream, D = floor page, HL = floor FB pointer
;;   shadow: D' = ceiling page (or DE' = sky pointer), HL' = ceiling FB ptr,
;;           B' = count, C' = rows left
;;   IXL = 2*facing + parity (flat page offset), IXH = column base offset
;;   IY  = column table pointer
;; ---------------------------------------------------------------------------
_asm_floor_column:
        push    ix
        push    iy
        xor     a
        ld      (fl_x),a
        ld      iy,#COLTAB+2
fc_col:
        ld      a,(fl_x)
        ld      l,a
        ld      h,#>COLW
        ld      a,#24
        sub     (hl)
        jp      z,fc_next               ; wall fills the column
        exx
        ld      c,a                     ; C' = rows left
        exx
        ; flat page offset = 2*facing + parity
        ld      a,l
        and     #1
        ld      e,a
        ld      a,(_r_f)
        add     a,a
        add     a,e
        .db     0xDD,0x6F               ; ld ixl,a
        ; sky column base: 0x4800 + par*1536 + ((sky+x)&63)*24
        ld      a,(#HDR+1)
        add     a,l
        and     #63
        ld      c,a
        ld      b,#0
        ld      h,b
        ld      l,c
        add     hl,hl
        add     hl,bc                   ; *3
        add     hl,hl
        add     hl,hl
        add     hl,hl                   ; *24
        ld      bc,#0x4800
        add     hl,bc
        dec     e
        jr      nz,fc_sk0
        ld      bc,#1536
        add     hl,bc
fc_sk0: ld      (fl_sky),hl
        ; FB column base: page FBPAGE + x>>2, offset ((x>>1)&1)<<7 | (x&1)
        ld      a,(fl_x)
        ld      e,a
        and     #2
        rrca
        rrca
        ld      d,a
        ld      a,e
        and     #1
        or      d
        .db     0xDD,0x67               ; ld ixh,a (base offset)
        ld      l,a
        ld      a,e
        rra
        rra
        and     #0x3F
        add     a,#FBPAGE
        ld      h,a                     ; HL = ceiling ptr (row 0)
        push    hl
        exx
        pop     hl                      ; HL' = ceiling ptr
        exx
        ld      a,#94
        add     a,l
        ld      l,a                     ; HL = floor ptr (row 47)
        ld      c,0(iy)
        ld      b,1(iy)                 ; BC = floor list
fc_run:
        ld      a,(bc)                  ; cell index
        inc     bc
        ld      e,a
        ld      d,#CELLC
        ld      a,(de)                  ; ceiling page (0 = sky)
        or      a
        jr      z,fc_skyrun
        .db     0xDD,0x85               ; add a,ixl
        ex      af,af'                  ; A' = ceiling page
        dec     d
        ld      a,(de)
        .db     0xDD,0x85               ; add a,ixl
        ld      d,a                     ; D = floor page
        ld      a,(bc)                  ; run length
        inc     bc
        exx
        ld      b,a
        cp      c
        jr      c,fc_k1
        ld      b,c                     ; k = min(cnt, rows left)
fc_k1:  ld      a,c
        sub     b
        ld      c,a
        ex      af,af'
        ld      d,a                     ; D' = ceiling page
fc_tex:
        exx
        ld      a,(bc)
        inc     bc
        ld      e,a
        ld      a,(de)
        ld      (hl),a
        dec     l
        dec     l
        ld      a,e
        exx
        ld      e,a
        ld      a,(de)
        ld      (hl),a
        inc     l
        inc     l
        djnz    fc_tex
        ld      a,c
        or      a
        exx
        jp      nz,fc_run
        jp      fc_next
fc_skyrun:
        dec     d
        ld      a,(de)
        .db     0xDD,0x85               ; add a,ixl
        ld      d,a                     ; D = floor page
        ld      a,(bc)                  ; run length
        inc     bc
        exx
        ld      b,a
        cp      c
        jr      c,fc_k2
        ld      b,c
fc_k2:  ld      a,c
        sub     b
        ld      c,a
        ; DE' = sky column + ceiling row = fl_sky + (L' - base)/2
        ld      a,l
        .db     0xDD,0x94               ; sub ixh
        rrca
        ld      e,a
        ld      d,#0
        push    hl
        ld      hl,(fl_sky)
        add     hl,de
        ex      de,hl
        pop     hl
fc_skl:
        exx
        ld      a,(bc)
        inc     bc
        ld      e,a
        ld      a,(de)
        ld      (hl),a
        dec     l
        dec     l
        exx
        ld      a,(de)
        inc     de
        ld      (hl),a
        inc     l
        inc     l
        djnz    fc_skl
        ld      a,c
        or      a
        exx
        jp      nz,fc_run
fc_next:
        ld      de,#4
        add     iy,de
        ld      hl,#fl_x
        inc     (hl)
        ld      a,(hl)
        cp      #64
        jp      c,fc_col
        pop     iy
        pop     ix
        ret

;; ---------------------------------------------------------------------------
;; asm_wall_column: textured wall strips for all 64 columns (slot 1 = walls).
;; Unrolled scaler, entered part-way (Duff) so the last copy writes the bottom
;; wall row:   HL = texture v (H = byte in page), DE = v step, B = texture page,
;;             IY = column base adjusted so copy k writes row offset 2k.
;; ---------------------------------------------------------------------------
_asm_wall_column:
        push    ix
        push    iy
        xor     a
        ld      (fl_x),a
wc_col:
        ld      a,(fl_x)
        ld      l,a
        ld      h,#>COLW
        ld      a,(hl)                  ; W
        or      a
        jp      z,wc_next
        ld      (fl_k),a
        set     6,l
        ld      a,(hl)                  ; texture page (0 = fog)
        res     6,l
        ld      b,a
        ; pass 0 draws fog + bank-A pages (0x40-0x7F), pass 1 bank-B pages (0x80-0xBF)
        ld      a,(_wc_pass)
        or      a
        jr      nz,wc_passb
        bit     7,b
        jp      nz,wc_next
        jr      wc_base
wc_passb:
        bit     7,b
        jp      z,wc_next
        ld      a,b
        sub     #0x40
        ld      b,a
wc_base:
        ; column base: page FBPAGE + x>>2, offset ((x>>1)&1)<<7 | (x&1)
        ld      a,l
        and     #2
        rrca
        rrca
        ld      e,a
        ld      a,l
        and     #1
        or      e
        ld      e,a
        ld      a,l
        rra
        rra
        and     #0x3F
        add     a,#FBPAGE
        ld      d,a                     ; DE = column base
        ld      a,b
        or      a
        jp      z,wc_fog
wc_draw:
        ; IY = base - 2*(24-W)
        ld      a,(fl_k)
        sub     #24                     ; W-24 (<= 0)
        add     a,a
        ld      l,a
        ld      h,#0xFF
        jr      nz,wc_neg
        ld      h,#0                    ; W == 24 -> offset 0
wc_neg: add     hl,de
        push    hl
        pop     iy
        ; entry = wc_unroll + 6*(48-2W) = wc_unroll + 288 - 12W
        ld      a,(fl_k)
        ld      l,a
        ld      h,#0
        add     hl,hl
        add     hl,hl                   ; 4W
        ld      d,h
        ld      e,l
        add     hl,hl                   ; 8W
        add     hl,de                   ; 12W
        ex      de,hl
        ld      hl,#wc_unroll+288
        or      a
        sbc     hl,de
        push    hl
        pop     ix
        ; HL = acc, DE = step
        ld      a,(fl_x)
        add     a,a
        ld      l,a
        ld      h,#>COLACC
        set     7,l
        ld      e,(hl)
        inc     l
        ld      d,(hl)
        dec     l
        res     7,l
        inc     h
        ld      a,(hl)
        inc     l
        ld      h,(hl)
        ld      l,a
        ex      de,hl                   ; HL = acc, DE = step
        jp      (ix)
wc_unroll:
        ld      c,h
        ld      a,(bc)
        ld      0(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      2(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      4(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      6(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      8(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      10(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      12(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      14(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      16(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      18(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      20(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      22(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      24(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      26(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      28(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      30(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      32(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      34(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      36(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      38(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      40(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      42(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      44(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      46(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      48(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      50(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      52(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      54(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      56(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      58(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      60(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      62(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      64(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      66(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      68(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      70(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      72(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      74(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      76(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      78(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      80(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      82(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      84(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      86(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      88(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      90(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      92(iy),a
        add     hl,de
        ld      c,h
        ld      a,(bc)
        ld      94(iy),a
        add     hl,de
        jr      wc_next
wc_fog:
        ld      a,(_wc_pass)
        or      a
        jr      nz,wc_next
        ld      a,(fl_k)
        add     a,a
        ld      b,a                     ; 2W rows
        ld      a,#24
        ld      hl,#fl_k
        sub     (hl)
        add     a,a
        add     a,e
        ld      l,a
        ld      h,d                     ; HL = base + 2*(24-W)
        xor     a
wc_fl:  ld      (hl),a
        inc     l
        inc     l
        djnz    wc_fl
wc_next:
        ld      hl,#fl_x
        inc     (hl)
        ld      a,(hl)
        cp      #64
        jp      c,wc_col
        pop     iy
        pop     ix
        ret

;; ---------------------------------------------------------------------------
;; asm_spr_column: one billboard column with transparency (texel 0xFF).
;;   spr_fb = FB pointer of the first row, spr_n = rows, spr_acc = texture v
;;   (8.8, high byte includes the column offset in the page), spr_step,
;;   spr_page = texture page (slot 1).
;; ---------------------------------------------------------------------------
_asm_spr_column:
        ld      a,(_spr_n)
        or      a
        ret     z
        exx
        ld      hl,(_spr_acc)
        ld      bc,(_spr_step)
        ld      a,(_spr_page)
        ld      d,a
        exx
        ld      b,a                     ; (overwritten below)
        ld      a,(_spr_n)
        ld      b,a
        ld      hl,(_spr_fb)
sp_l:   exx
        ld      e,h
        ld      a,(de)
        add     hl,bc
        exx
        cp      #0xFF
        jr      z,sp_s
        ld      (hl),a
sp_s:   inc     l
        inc     l
        djnz    sp_l
        ret

;; ---------------------------------------------------------------------------
;; asm_c2p_upload: chunky FB -> planar tiles, written straight to the back
;; buffer in VRAM (display on: every OUT is >= 27 cycles after the previous).
;; Tile order is column-major (tile = group*12 + tile_row), matching view_nt.
;; Each logical row becomes two identical screen lines (4 plane bytes x 2).
;;   shadow: HL' = FB pointer, B' = rows left in group, C' = groups left
;;   main:   BC = left-pair LUT (B = page 0x40+p), HL = right-pair LUT (0x44+p)
;;           D, E, A', B = plane bytes kept for the second line
;; ---------------------------------------------------------------------------
_asm_c2p_upload:
        ld      a,(_r_buf)
        or      a
        ld      hl,#0x4000              ; VRAM 0x0000 | write
        jr      z,cu_a
        ld      hl,#0x4000+6144
cu_a:   di
        ld      a,l
        out     (VDPCTRL),a
        ld      a,h
        out     (VDPCTRL),a
        ei
        exx
        ld      hl,#FBPAGE*256
        ld      c,#16
cu_grp:
        ld      b,#48
cu_row:                                 ; shadow active
        ld      a,(hl)
        inc     l
        or      (hl)                    ; left pair (c0<<4 | c1)
        set     7,l
        ex      af,af'
        ld      a,(hl)
        dec     l
        or      (hl)                    ; right pair
        res     7,l
        inc     l
        inc     l
        exx
        ld      l,a
        ex      af,af'
        ld      c,a
        ld      b,#0x40
        ld      h,#0x44
        ld      a,(bc)
        or      (hl)
        out     (VDPDATA),a             ; plane 0
        ld      d,a
        inc     b
        inc     h
        ld      a,(bc)
        or      (hl)
        out     (VDPDATA),a             ; plane 1
        ld      e,a
        inc     b
        inc     h
        ld      a,(bc)
        or      (hl)
        out     (VDPDATA),a             ; plane 2
        ex      af,af'
        inc     b
        inc     h
        ld      a,(bc)
        or      (hl)
        out     (VDPDATA),a             ; plane 3
        ld      b,a                     ; 4
        ld      a,d                     ; 4
        nop                             ; 4
        nop                             ; 4  -> 27 incl. OUT
        out     (VDPDATA),a             ; second screen line
        ld      a,e
        nop
        nop
        nop
        out     (VDPDATA),a
        ex      af,af'
        nop
        nop
        nop
        out     (VDPDATA),a
        ld      a,b
        nop
        nop
        nop
        out     (VDPDATA),a
        exx
        djnz    cu_row
        inc     h
        ld      l,#0
        dec     c
        jr      nz,cu_grp
        exx
        ret

;; ---------------------------------------------------------------------------
;; asm_show_buffer(A = buffer): point the 16x12 view in the name table at the
;; buffer's tiles.  Call right after VBlank (fast OTIR writes).
;; ---------------------------------------------------------------------------
        .globl  _view_nt
_asm_show_buffer:
        ld      a,(_flip_buf)
        ld      hl,#_view_nt
        or      a
        jr      z,sb_a
        ld      de,#384
        add     hl,de
sb_a:   ld      de,#0x7800+((3*32+8)*2)     ; VRAM write | 0x3800 + (VIEW_TY*32+VIEW_TX)*2
        ld      a,#12
sb_row: di
        ld      c,#VDPCTRL
        out     (c),e
        out     (c),d
        ei
        ld      c,#VDPDATA
        ld      b,#32
        otir
        ex      de,hl
        ld      bc,#64
        add     hl,bc
        ex      de,hl
        dec     a
        jr      nz,sb_row
        ret
