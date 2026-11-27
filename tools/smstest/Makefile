# Local copy of the skill's headless SMS emulator (MIT, see LICENSE) with one
# addition: a "reset" script command (console reset; RAM and cartridge RAM kept).
CFLAGS := -O2 -w
all: smstest
smstest: smstest.c z80.c z80.h
	$(CC) $(CFLAGS) -o $@ smstest.c z80.c
clean:
	rm -f smstest
.PHONY: all clean
