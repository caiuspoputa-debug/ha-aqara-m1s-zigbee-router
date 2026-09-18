#!/bin/sh
# Repair only the exact v0.9 validator shipped by this integration's hub kit.
set -eu
manager=/data/m1s_network/network_manager.sh
original=0cdf8f306908e0fab861c33adb4b6810
fixed=6366bf3fc3e21504fcd70cc4cbc8674c
digest=$(md5sum "$manager" | awk '{print $1}')
if [ "$digest" = "$fixed" ]; then
    echo M1S_NETWORK_COMPAT_READY
    exit 0
fi
if [ "$digest" != "$original" ]; then
    echo M1S_NETWORK_COMPAT_UNKNOWN
    exit 1
fi
if [ -f /tmp/m1s_network.pending ] || ps w | grep -q '[n]etwork_manager.sh candidate'; then
    echo M1S_NETWORK_COMPAT_BUSY
    exit 1
fi
temp="$manager.fix.$$"
trap 'rm -f "$temp"' 0
sed '/^valid_ipv4()/,/^}/ { s/^{/(/; s/^}/)/; }' "$manager" > "$temp"
/bin/sh -n "$temp"
[ "$(md5sum "$temp" | awk '{print $1}')" = "$fixed" ]
chmod 700 "$temp"
if [ ! -e "$manager.before-0.21.4" ]; then
    cp -p "$manager" "$manager.before-0.21.4"
fi
[ "$(md5sum "$manager" | awk '{print $1}')" = "$original" ]
mv "$temp" "$manager"
echo M1S_NETWORK_COMPAT_READY
