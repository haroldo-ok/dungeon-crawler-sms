#!/bin/bash
# Step into an open cell (footstep) and into a wall (bump); both must reach the PSG.
cd "$(dirname "$0")/.."
cat > /tmp/snd.txt <<'S'
symbols dungeon.noi
waituntil game_ready == 1 3000 w1
psglog /tmp/snd.log
hold up
run 4
hold none
waituntil moves >= 1 3000
run 120
hold 1+right
run 4
hold none
waituntil bumps >= 1 600
run 60
psgstop
S
smstest ${1:-dungeon.sms} /tmp/snd.txt | tail -1
grep -q " E6$" /tmp/snd.log && echo "ok   footstep noise written" || { echo "FAIL footstep"; exit 1; }
grep -q " E5$" /tmp/snd.log && grep -q " F0$" /tmp/snd.log && echo "ok   bump noise at full volume" || { echo "FAIL bump"; exit 1; }
