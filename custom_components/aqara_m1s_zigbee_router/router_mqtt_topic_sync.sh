#!/bin/sh
set -eu

# The root override is used only by isolated filesystem tests.
ROOT="${M1S_TOPIC_SYNC_ROOT:-}"
BASE="$ROOT/data/m1s_router"
CONF="$BASE/mqtt_io.conf"
SERVICE="$BASE/mqtt_io_service.sh"
COORDINATOR="$ROOT/data/m1s_coordinator"
RUNTIME="$ROOT/tmp/m1s_router_mqtt_io_runtime.conf"
LOG="$ROOT/tmp/m1s_router_mqtt_io.log"
LOCK="$ROOT/tmp/m1s_router_topic_sync.lock"
MAINTENANCE="$ROOT/tmp/m1s_router_mqtt_uart_maintenance"
WAIT_SECONDS="${M1S_TOPIC_SYNC_WAIT_SECONDS:-20}"

skip() { echo M1S_ROUTER_TOPIC_SYNC_NOT_USED; exit 0; }
defer() { echo M1S_ROUTER_TOPIC_SYNC_DEFERRED; exit 1; }

[ ! -e "$COORDINATOR/dedicated_mode" ] || skip
if [ -x "$COORDINATOR/coordinator_status.sh" ] &&
   "$COORDINATOR/coordinator_status.sh" 2>/dev/null | grep -q '^role=coordinator$'; then
    skip
fi
[ -r "$CONF" ] && [ -x "$SERVICE" ] || skip
enabled="$(sed -n 's/^MQTT_IO_ENABLED=//p' "$CONF" | head -n 1)"
[ "$enabled" = 1 ] || skip
configured="$(sed -n 's/^TOPIC_ID=//p' "$CONF" | head -n 1)"
case "$configured" in AUTO|auto|'') ;; *) skip ;; esac

current_ip=''
for iface in wlan0 eth0; do
    current_ip="$(ifconfig "$iface" 2>/dev/null | sed -n \
        -e 's/.*inet addr:\([0-9.][0-9.]*\).*/\1/p' \
        -e 's/.*inet \([0-9.][0-9.]*\).*/\1/p' | head -n 1)"
    [ -z "$current_ip" ] || break
done
[ -n "$current_ip" ] && [ "$current_ip" = "${M1S_EXPECTED_IPV4:-}" ] || defer
expected="${current_ip##*.}"
case "$expected" in ''|*[!0-9]*) defer ;; esac
[ "$expected" -ge 1 ] && [ "$expected" -le 254 ] || defer

runtime="$(sed -n 's/^TOPIC_ID=//p' "$RUNTIME" 2>/dev/null | head -n 1)"
if [ "$runtime" = "$expected" ] && "$SERVICE" status >/dev/null 2>&1; then
    echo M1S_ROUTER_TOPIC_SYNC_READY
    exit 0
fi

# Do not interrupt an alert receiver or an explicit legacy UART session.
[ ! -e "$MAINTENANCE" ] || defer
if netstat -lnt 2>/dev/null | grep -q -e ':12347 ' -e ':12348 ' -e ':1886 '; then
    defer
fi
mkdir "$LOCK" 2>/dev/null || defer
trap 'rmdir "$LOCK" 2>/dev/null || true' 0 1 2 3 15

first_line=1
if [ -f "$LOG" ]; then
    first_line=$(( $(wc -l < "$LOG") + 1 ))
fi
"$SERVICE" restart >"$ROOT/tmp/m1s_router_topic_sync_restart.log" 2>&1 || defer
case "$WAIT_SECONDS" in ''|*[!0-9]*) defer ;; esac
waited=0
while :; do
    runtime="$(sed -n 's/^TOPIC_ID=//p' "$RUNTIME" 2>/dev/null | head -n 1)"
    if [ -f "$LOG" ]; then
        lines="$(wc -l < "$LOG")"
        [ "$lines" -ge "$((first_line - 1))" ] || first_line=1
        if [ "$runtime" = "$expected" ] && "$SERVICE" status >/dev/null 2>&1 &&
           sed -n "$first_line,\$p" "$LOG" | grep -q 'initial state, lux and telemetry published' &&
           sed -n "$first_line,\$p" "$LOG" | grep -q 'MQTT connected and command topics subscribed'; then
            echo M1S_ROUTER_TOPIC_SYNC_REPAIRED
            exit 0
        fi
    fi
    [ "$waited" -lt "$WAIT_SECONDS" ] || defer
    sleep 1
    waited=$((waited + 1))
done
