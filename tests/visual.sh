#!/bin/bash
# Put the camera in a known spot (monster AI frozen), animate a step/turn, grab
# the screen and compare the 3D view pixel-for-pixel with tools/simrender.py.
cd "$(dirname "$0")/.."
ROM=${1:-dungeon.sms}
fail=0
run_case () {   # name, script-body [, battle line-up for the oracle]
  local name=$1; shift
  local lineup=${2:-}
  { echo "symbols dungeon.noi"; echo "poke 0xDAF0 23"; echo "poke 0xDAF1 90"; echo "waituntil game_ready == 1 3000 w1"; echo "waituntil frames_rendered >= 1 600";
    echo "poke ai_off 1 w1"; printf "%b\n" "$1";
    echo "screenshot shots/$name.ppm"; for v in shown_cx shown_cy shown_f shown_pose level; do echo "print $v w1"; done; } > /tmp/vis_$name.txt
  out=$(smstest $ROM /tmp/vis_$name.txt || true); echo "$out" | grep FAIL || true
  vals=$(echo "$out" | grep -E "print: (shown|level)" | sed 's/.*= \([0-9]*\).*/\1/' | tr '\n' ' ')
  if python3 tools/cmpview.py shots/$name.ppm $vals $lineup >/tmp/cmp.txt; then echo "ok   $name ($vals)"; else echo "FAIL $name ($vals) $(cat /tmp/cmp.txt)"; fail=1; fi
}
# teleport to x,y facing f-1, then turn right so the final rest frame faces f
at () { echo "poke px $1 w1\npoke py $2 w1\npoke pf $(( ($3 + 3) % 4 )) w1\nhold right\nwaituntil turns >= 1 4000\nhold none\nwaituntil frames_rendered >= 7 4000\nrun 20"; }
run_case boot        "run 10"
run_case walk_mid    "hold up\nwaituntil frames_rendered >= 4 4000\nhold none"
run_case turn_mid    "hold right\nwaituntil frames_rendered >= 3 4000\nhold none"
run_case strafe      "hold 1+left\nwaituntil frames_rendered >= 3 4000\nhold none"
run_case back        "hold down\nwaituntil bumps >= 1 4000\nhold up\nwaituntil frames_rendered >= 5 4000\nhold none"
run_case court       "poke px 9 w1\npoke py 11 w1\npoke pf 3 w1\nhold right\nwaituntil frames_rendered >= 4 4000\nhold none"
run_case sky_turn    "poke px 9 w1\npoke py 9 w1\npoke pf 0 w1\nhold left\nwaituntil frames_rendered >= 3 4000\nhold none"
run_case quick_walk  "poke quick_mode 1 w1\nhold up\nwaituntil frames_rendered >= 2 4000\nhold none"
run_case quick_turn  "poke quick_mode 1 w1\nhold left\nwaituntil frames_rendered >= 3 4000\nhold none"
run_case door        "$(at 3 6 2)"
run_case locked      "$(at 13 14 1)"
run_case secret      "$(at 12 5 1)"
run_case key         "$(at 14 4 0)"
run_case skel_near   "$(at 10 11 1)"
run_case skel_occl   "$(at 5 11 2)"
run_case skel_sky    "$(at 8 7 1)"
run_case skel_turn   "poke px 10 w1\npoke py 11 w1\npoke pf 0 w1\nhold right\nwaituntil frames_rendered >= 4 4000\nhold none"
run_case skel_walk   "poke px 8 w1\npoke py 7 w1\npoke pf 1 w1\nhold up\nwaituntil frames_rendered >= 4 4000\nhold none"
run_case merchant  "$(at 11 9 1)"
run_case shop_far  "$(at 9 9 1)"
# other levels (each with its own texture set): jump there with the dbg_level hook
lvl_at () { echo "poke px $2 w1\npoke py $3 w1\npoke pf $(( ($4 + 3) % 4 )) w1\npoke dbg_level $1 w1\nrun 60\nhold right\nwaituntil turns >= 1 4000\nhold none\nwaituntil frames_rendered >= 8 4000\nrun 20"; }
run_case crypt_court  "$(lvl_at 1 6 7 1)"
run_case crypt_window "$(lvl_at 1 4 1 0)"
run_case crypt_gate   "$(lvl_at 1 10 5 3)"
run_case mines_start  "$(lvl_at 2 1 1 2)"
run_case mines_shaft  "$(lvl_at 2 4 9 1)"
run_case mines_lever  "$(lvl_at 2 1 11 2)"
run_case mines_crystal "$(lvl_at 2 11 5 1)"
run_case mines_rails  "$(lvl_at 2 5 1 1)"
run_case cat_corridor "$(lvl_at 3 11 13 3)"
run_case cat_boss     "$(lvl_at 3 3 2 3)"
run_case cat_spiders  "$(lvl_at 3 11 9 1)"
# battles: walk into a group; the line-up is drawn in front of the corridor view
fightat () { echo "poke bt_say_frames 250 w1\npoke px $1 w1\npoke py $2 w1\npoke pf $3 w1\nhold up\nrun 4\nhold none\nwaituntil in_battle == 1 600 w1\nrun 60"; }
run_case battle_skel "$(fightat 10 11 1)" "20:72:0:0,44:72:0:0"
run_case battle_bats "$(fightat 9 7 1)" "12:58:2:3,32:58:2:3,52:58:2:3"
run_case battle_one  "$(fightat 7 13 3)" "32:92:0:0"
run_case battle_lich "poke dbg_level 3 w1\nrun 60\n$(fightat 3 2 3)" "32:92:4:18"
run_case battle_slime "poke dbg_level 2 w1\nrun 60\n$(fightat 8 3 3)" "20:72:3:9,44:72:3:9"
exit $fail
