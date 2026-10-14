#!/bin/sh
# SPDX-License-Identifier: MIT
root=/data/m1s_audio_03714
owner=/tmp/m1s_local_sound.owner
action=$1
token=$2
case "$token" in ''|*[!a-f0-9]*) exit 2;; esac
[ "${#token}" -eq 32 ] || exit 2
state=/tmp/m1s_local_sound_$token.state
stopfile=/tmp/m1s_local_sound_$token.stop
cache=/tmp/m1s_local_sound_$token.wav

case "$action" in
start|start-url)
    source=$3
    if [ "$action" = start ]; then
        case "$source" in /data/musics/*.wav|/data/musics/*.WAV) ;; *) exit 2;; esac
        case "$source" in */../*|*/./*) exit 2;; esac
        [ -f "$source" ] || exit 2
    else
        case "$source" in http://*|https://*) ;; *) exit 2;; esac
    fi
    if [ -e "$owner" ]; then
        prior_pid=$(awk '{print $2}' "$owner")
        prior_start=$(awk '{print $3}' "$owner")
        if [ -n "$prior_start" ] \
            && [ "$(awk '{print $22}' /proc/$prior_pid/stat 2>/dev/null)" = "$prior_start" ]; then
            printf 'M1S_SOUND_BUSY\n'
            exit 3
        fi
        rm -f "$owner"
    fi
    if ! grep -q '^closed$' /proc/asound/card0/pcm0p/sub0/status 2>/dev/null; then
        printf 'M1S_AUDIO_BUSY\n'
        exit 6
    fi
    printf 'PENDING\n' > "$state"
    (
        trap '' HUP
        finish() {
            code=$?
            printf 'DONE:%s\n' "$code" > "$state"
            if [ "$(awk '{print $1}' "$owner" 2>/dev/null)" = "$token" ]; then
                rm -f "$owner"
            fi
            rm -f "$cache" "$stopfile"
        }
        record() {
            start=$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)
            printf '%s %s %s\n' "$token" "$pid" "$start" > "$owner"
            printf '%s:%s:%s\n' "$1" "$pid" "$start" > "$state"
        }
        trap finish EXIT
        if [ "$action" = start-url ]; then
            wget -q "$source" -O "$cache" </dev/null \
                > /tmp/m1s_local_sound_$token.log 2>&1 &
            pid=$!
            record DOWNLOADING
            [ ! -f "$stopfile" ] || kill -TERM "$pid" 2>/dev/null
            wait "$pid" || exit $?
            [ ! -f "$stopfile" ] || exit 143
            source=$cache
        fi
        ALSA_CONFIG_PATH="$root/alsa.conf" aplay -D m1s_media -x 1 "$source" \
            </dev/null > /tmp/m1s_local_sound_$token.log 2>&1 &
        pid=$!
        record RUNNING
        [ ! -f "$stopfile" ] || kill -TERM "$pid" 2>/dev/null
        renice -3 -p "$pid" >/dev/null 2>&1 || true
        wait "$pid"
        exit $?
    ) </dev/null >/dev/null 2>&1 &
    count=0
    while [ "$(cat "$state")" = PENDING ] && [ "$count" -lt 40 ]; do
        sleep 0.02
        count=$((count + 1))
    done
    [ "$(cat "$state")" != PENDING ] || exit 4
    printf 'M1S_SOUND_STARTED:%s\n' "$token"
    ;;
status)
    if [ -f "$state" ]; then
        current=$(cat "$state")
        case "$current" in
        RUNNING:*|DOWNLOADING:*)
            record=${current#*:}
            pid=${record%%:*}
            start=${record#*:}
            if [ "$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)" != "$start" ]; then
                printf 'DONE:1\n'
            else
                printf '%s\n' "$current"
            fi
            ;;
        *) printf '%s\n' "$current";;
        esac
    else printf 'MISSING\n'; fi
    ;;
stop)
    touch "$stopfile"
    if [ "$(awk '{print $1}' "$owner" 2>/dev/null)" = "$token" ]; then
        pid=$(awk '{print $2}' "$owner")
        start=$(awk '{print $3}' "$owner")
        actual=$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)
        if [ -n "$start" ] && [ "$actual" = "$start" ]; then
            tr '\000' ' ' < /proc/$pid/cmdline \
                | grep -e 'aplay -D m1s_media' -e "m1s_local_sound_$token.wav" >/dev/null 2>&1 \
                || exit 5
            kill -TERM "$pid" 2>/dev/null || true
            count=0
            while [ "$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)" = "$start" ] \
                && [ "$count" -lt 10 ]; do
                sleep 0.1
                count=$((count + 1))
            done
            if [ "$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)" = "$start" ]; then
                kill -KILL "$pid" 2>/dev/null || true
                sleep 0.05
                if [ "$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)" = "$start" ] \
                    && [ "$(awk '{print $3}' /proc/$pid/stat 2>/dev/null)" != Z ]; then
                    exit 5
                fi
            fi
        fi
        if [ "$(awk '{print $1}' "$owner" 2>/dev/null)" = "$token" ]; then
            rm -f "$owner"
        fi
    fi
    printf 'M1S_SOUND_STOPPED:%s\n' "$token"
    ;;
cleanup)
    [ "$(awk '{print $1}' "$owner" 2>/dev/null)" != "$token" ] || exit 3
    rm -f "$state" "$stopfile" "$cache" /tmp/m1s_local_sound_$token.log
    ;;
*) exit 2;;
esac
