DEVKIT  ?= $(HOME)/.devkitsms
PROG    := dungeon
CC      := sdcc
DEFS    ?= -DASM_CELLS -DASM_RAYS -DASM_FLOOR -DASM_WALL -DASM_C2P -DASM_SHOW -DASM_SPR
CFLAGS  := -mz80 -I$(DEVKIT)/include --peep-file $(DEVKIT)/include/peep-rules.txt -Isrc -Igen --opt-code-speed $(DEFS)
LDFLAGS := -mz80 --no-std-crt0 --data-loc 0xC000 -Wl-b_GAME=0x4000
GAMESEG := --codeseg GAME --constseg GAME
OBJS    := core.rel music.rel render.rel render_asm.rel gen_nt.rel battle.rel menus.rel game.rel gen.rel state.rel

all: $(PROG).sms

# all game content (levels, texture sets, monsters, items, events, music) is
# data in tools/content.py; gen.py checks it and compiles it to gen/
CONTENT := tools/content.py tools/art.py

gen/gen.c gen/gen_nt.c gen/gen.h: tools/gen.py $(CONTENT)
	python3 tools/gen.py gen

%.rel: src/%.c src/engine.h src/core.h src/game.h gen/gen.h
	$(CC) $(CFLAGS) -c $< -o $@

# game logic + its data live in ROM bank 1 (0x4000-0x7EFF)
game.rel: src/game.c src/engine.h src/core.h gen/gen.h
	$(CC) $(CFLAGS) $(GAMESEG) -c $< -o $@

gen.rel: gen/gen.c gen/gen.h
	$(CC) $(CFLAGS) $(GAMESEG) -c $< -o $@

gen/music.c gen/music.h: tools/music.py $(CONTENT)
	python3 tools/music.py gen

music.rel: gen/music.c gen/music.h
	$(CC) $(CFLAGS) -c $< -o $@

core.rel: src/core.c src/engine.h src/core.h gen/gen.h gen/music.h
	$(CC) $(CFLAGS) -c $< -o $@

gen_nt.rel: gen/gen_nt.c gen/gen.h
	$(CC) $(CFLAGS) -c $< -o $@

%.rel: src/%.s
	sdasz80 -plosgff $@ $<

$(PROG).ihx: $(OBJS)
	$(CC) -o $@ $(LDFLAGS) $(DEVKIT)/lib/crt0_sms.rel $(OBJS) $(DEVKIT)/lib/SMSlib.lib $(DEVKIT)/lib/PSGlib.lib

$(PROG).sms: $(PROG).ihx tools/mkrom.py
	python3 tools/checkcode.py $(PROG).ihx $(PROG).map
	ihx2sms $(PROG).ihx $(PROG)_code.sms
	python3 tools/mkrom.py $(PROG)_code.sms gen $(PROG).sms

# validate content + simulate the battles, without building
check:
	python3 tools/gen.py --check
	python3 tools/balance.py

test: $(PROG).sms
	python3 tests/content_check.py | tail -1
	smstest $(PROG).sms tests/boot.txt
	smstest $(PROG).sms tests/title.txt | tail -1
	python3 tests/mkexplore.py && smstest $(PROG).sms tests/explore.txt | tail -1
	python3 tests/mkplay.py && smstest $(PROG).sms tests/playthrough.txt | tail -1
	python3 tests/mkbattle.py && smstest $(PROG).sms tests/battle.txt | tail -1
	$(MAKE) -C tools/smstest
	python3 tests/mkshop.py && tools/smstest/smstest $(PROG).sms tests/shop_save.txt | tail -1
	tests/sound.sh $(PROG).sms
	tests/visual.sh $(PROG).sms
	tests/bench.sh
	tests/demo_content.sh | tail -1

clean:
	rm -f *.rel *.ihx *.sym *.lst *.map *.noi *.lk *.asm *.rst *.sms
.PHONY: all clean test check
