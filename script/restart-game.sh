#!/bin/zsh
# Kill the running RimWorld (process name has spaces) and relaunch through Steam so Workshop mods load.
set -u
pids=$(pgrep -f "RimWorldMac.app/Contents/MacOS/RimWorld" || true)
if [[ -n "$pids" ]]; then
  echo "killing RimWorld pid(s): $pids"
  kill $pids 2>/dev/null || true
  for i in {1..20}; do
    sleep 0.5
    pgrep -f "RimWorldMac.app/Contents/MacOS/RimWorld" >/dev/null || break
  done
  pgrep -f "RimWorldMac.app/Contents/MacOS/RimWorld" >/dev/null && kill -9 $pids 2>/dev/null || true
  sleep 1
fi
open "steam://rungameid/294100"
echo "relaunched via Steam"
