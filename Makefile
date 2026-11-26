DEVKIT  ?= $(HOME)/.devkitsms
PROG    := dungeon
CC      := sdcc
DEFS    ?= -DASM_CELLS -DASM_RAYS -DASM_FLOOR -DASM_WALL -DASM_C2P -DASM_SHOW
CFLAGS  := -mz80 -I$(DEVKIT)/include --peep-file $(DEVKIT)/include/peep-rules.txt -Isrc -Igen --opt-code-speed $(DEFS)
LDFLAGS := -mz80 --no-std-crt0 --data-loc 0xC000
OBJS    := main.rel render.rel gen.rel render_asm.rel

all: $(PROG).sms

gen/gen.c gen/gen.h: tools/gen.py
	python3 tools/gen.py gen

%.rel: src/%.c src/engine.h gen/gen.h
	$(CC) $(CFLAGS) -c $< -o $@

gen.rel: gen/gen.c gen/gen.h
	$(CC) $(CFLAGS) -c $< -o $@

%.rel: src/%.s
	sdasz80 -plosgff $@ $<

$(PROG).ihx: $(OBJS)
	$(CC) -o $@ $(LDFLAGS) $(DEVKIT)/lib/crt0_sms.rel $(OBJS) $(DEVKIT)/lib/SMSlib.lib $(DEVKIT)/lib/PSGlib.lib

$(PROG).sms: $(PROG).ihx tools/mkrom.py
	python3 tools/checkcode.py $(PROG).ihx $(PROG).map
	ihx2sms $(PROG).ihx $(PROG)_code.sms
	python3 tools/mkrom.py $(PROG)_code.sms gen $(PROG).sms

test: $(PROG).sms
	smstest $(PROG).sms tests/boot.txt
	python3 tests/mkexplore.py && smstest $(PROG).sms tests/explore.txt | tail -1
	tests/sound.sh $(PROG).sms
	tests/visual.sh $(PROG).sms
	tests/bench.sh

clean:
	rm -f *.rel *.ihx *.sym *.lst *.map *.noi *.lk *.asm *.rst *.sms
.PHONY: all clean test
