#!/bin/bash
# Average console frames (VBlanks, 60 Hz) per rendered view frame in a few scenarios.
cd "$(dirname "$0")/.."
bench () {
  { echo "symbols dungeon.noi"; echo "poke 0xDAF0 23"; echo "poke 0xDAF1 90"; echo "waituntil game_ready == 1 3000 w1"; echo "waituntil frames_rendered >= 1 600"; echo "poke ai_off 1 w1"; printf "%b\n" "$2";
    echo "print frames_rendered"; echo "run 600"; echo "print frames_rendered"; } > /tmp/b.txt
  smstest dungeon.sms /tmp/b.txt | grep "print: frames" | sed 's/.*= \([0-9]*\).*/\1/' | tr '\n' ' ' |
    awk -v n="$1" '{ d=$2-$1; printf "%-22s %3d frames/600 -> %.1f fps (%.2f vblanks/frame)\n", n, d, d/10, 600/d }'
}
bench "corridor walk"   "hold up"
bench "corridor turn"   "hold right"
bench "courtyard turn"  "poke px 9 w1\npoke py 9 w1\npoke pf 0 w1\nhold right"
bench "wood hall turn"  "poke px 10 w1\npoke py 3 w1\npoke pf 0 w1\nhold right"
