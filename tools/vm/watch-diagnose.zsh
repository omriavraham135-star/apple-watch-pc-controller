#!/bin/zsh
# Reports what the Mac can see of the Apple Watch, one layer at a time, so a
# missing watch in Xcode can be traced to Bluetooth, the network, discovery or
# pairing rather than guessed at. Changes nothing.

section() { print "\n=== $1"; }

section "Bluetooth"
system_profiler SPBluetoothDataType 2>/dev/null | grep -E 'State|Chipset' | head -2

section "Network (the Mac must be on the same Wi-Fi as the watch)"
print "IPv4: $(ipconfig getifaddr en0 2>/dev/null || echo none)"
ifconfig en0 2>/dev/null | awk '/inet6 fe80/ {print "IPv6 link-local: yes"; exit}'

section "Devices CoreDevice knows"
xcrun devicectl list devices 2>&1 | tail -n +1

section "What the iPhone says about its watch"
# The name column can contain spaces, so pick the identifier out by its shape.
iphone=$(xcrun devicectl list devices 2>/dev/null | grep -E 'iPhone.*connected' \
  | grep -oE '[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}' | head -1)
if [[ -n $iphone ]]; then
  xcrun devicectl device info details --device "$iphone" 2>&1 \
    | grep -iE 'watch|companion|paired|developerMode' | head -15
else
  print "iPhone not connected"
fi

section "Advertised on the network (8 seconds each)"
for svc in _remotepairing._tcp _remotepairing-manual-pairing._tcp _apple-mobdev2._tcp; do
  print -r -- "-- $svc"
  dns-sd -B $svc local. > /tmp/dnssd.$$ 2>&1 &
  pid=$!
  sleep 8
  kill $pid 2>/dev/null
  grep -E 'Add' /tmp/dnssd.$$ | awk '{$1=$2=$3=$4=$5=""; print "  " $0}' | sort -u
done
rm -f /tmp/dnssd.$$

section "Recent log lines mentioning a watch (any process)"
log show --last 15m --info --style compact 2>/dev/null \
  | grep -iE 'apple ?watch|watchOS|companion' | grep -viE 'watchdog' | cut -c1-230 | tail -20

section "What the pairing daemon has been doing"
log show --last 15m --info --style compact --predicate 'process == "remotepairingd"' 2>/dev/null \
  | cut -c1-230 | tail -20
