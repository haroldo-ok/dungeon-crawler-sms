#!/bin/bash
# Build a ROM from tests/demo_garden.py (tools/content.py + a new level, texture
# set, monster and weapon - data only) in a scratch copy, then play it: climb the
# new stair, check the view pixel-for-pixel, buy the new weapon.
set -e
cd "$(dirname "$0")/.."
D=/tmp/sms_demo_content
rm -rf $D && mkdir -p $D
cp -r Makefile src tools tests $D/
cd $D && rm -rf gen *.rel
SMS_CONTENT=demo_garden PYTHONPATH=$D/tests make >/tmp/demo_build.txt 2>&1 || { tail -20 /tmp/demo_build.txt; exit 1; }
grep -E "content:|bank 1|RAM globals" /tmp/demo_build.txt
G=$(python3 -c "import json; print([l['id'] for l in json.load(open('gen/meta.json'))['levels']].index('GARDEN'))")
mkdir -p shots
cat > /tmp/demo_play.txt <<SCRIPT
symbols dungeon.noi
poke 0xDAF0 23
poke 0xDAF1 90
waituntil game_ready == 1 3000 w1
waituntil frames_rendered >= 1 600
poke ai_off 1 w1
poke bt_say_frames 6 w1
echo face the new stair in the keep's north wall and climb it
poke pf 0 w1
run 10
hold up
run 4
hold none
waituntil level == $G 2000 w1
run 150
expect px == 1 w1
expect py == 1 w1
screenshot shots/demo_garden.ppm
print shown_cx w1
print shown_cy w1
print shown_f w1
print shown_pose w1
print level w1
echo the merchant sells the new SILVER SWORD (weapon 5)
poke px 1 w1
poke py 7 w1
poke pf 1 w1
poke gold 900 w2
poke weapon 4 w1
run 30
hold 1
run 4
hold none
run 80
hold 1
run 4
hold none
run 30
hold 1
run 4
hold none
run 120
expect weapon == 5 w1
expect gold == 500 w2
SCRIPT
out=$(tools/smstest/smstest dungeon.sms /tmp/demo_play.txt 2>/dev/null || smstest dungeon.sms /tmp/demo_play.txt)
echo "$out" | grep -E "FAIL|RESULT"
vals=$(echo "$out" | grep -E "print: (shown|level)" | sed 's/.*= \([0-9]*\).*/\1/' | tr '\n' ' ')
python3 tools/cmpview.py shots/demo_garden.ppm $vals && echo "ok   demo_garden view ($vals)"
cp shots/demo_garden.ppm /home/claude/dungeon/shots/ 2>/dev/null || true
echo "$out" | grep -q "ALL PASSED"
