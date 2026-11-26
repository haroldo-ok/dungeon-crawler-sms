#!/bin/bash
# Drive the game with the pad, grab screenshots mid-step/mid-turn and compare the
# view pixel-for-pixel with the Python reference renderer (tools/simrender.py).
set -e
cd "$(dirname "$0")/.."
ROM=${1:-dungeon.sms}
fail=0
run_case () {   # name, script-body
  local name=$1; shift
  { echo "symbols dungeon.noi"; echo "waituntil game_ready == 1 3000 w1"; printf "%b\n" "$@";
    echo "screenshot shots/$name.ppm"; for v in shown_cx shown_cy shown_f shown_pose; do echo "print $v w1"; done; } > /tmp/vis_$name.txt
  out=$(smstest $ROM /tmp/vis_$name.txt || true); echo "$out" | grep FAIL || true
  vals=$(echo "$out" | grep "print: shown" | sed 's/.*= \([0-9]*\).*/\1/' | tr '\n' ' ')
  if python3 tools/cmpview.py shots/$name.ppm $vals >/tmp/cmp.txt; then echo "ok   $name ($vals)"; else echo "FAIL $name ($vals) $(cat /tmp/cmp.txt)"; fail=1; fi
}
run_case boot      "run 10"
run_case walk_mid  "hold up\nwaituntil frames_rendered >= 4 4000\nhold none"
run_case turn_mid  "hold right\nwaituntil frames_rendered >= 3 4000\nhold none"
run_case strafe    "hold 1+left\nwaituntil frames_rendered >= 3 4000\nhold none"
run_case back      "hold down\nwaituntil bumps >= 1 4000\nhold up\nwaituntil frames_rendered >= 5 4000\nhold none"
run_case court     "poke px 9 w1\npoke py 11 w1\npoke pf 3 w1\nhold right\nwaituntil frames_rendered >= 4 4000\nhold none"
run_case courtyard "poke px 9 w1\npoke py 11 w1\npoke pf 3 w1\nhold right\nwaituntil pf == 0 4000 w1\nhold up\nwaituntil frames_rendered >= 11 4000\nhold none"
run_case sky_turn  "poke px 9 w1\npoke py 9 w1\npoke pf 0 w1\nhold left\nwaituntil frames_rendered >= 3 4000\nhold none"
run_case roof_edge "poke px 6 w1\npoke py 4 w1\npoke pf 2 w1\nhold 1+left\nwaituntil frames_rendered >= 3 4000\nhold none"
run_case quick_walk "tap 2\nhold up\nwaituntil frames_rendered >= 2 4000\nhold none"
run_case quick_turn "tap 2\nhold left\nwaituntil frames_rendered >= 3 4000\nhold none"
exit $fail
