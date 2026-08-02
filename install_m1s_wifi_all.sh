#!/bin/sh
# Aqara M1S Gen1 - installer Wi-Fi fallback + portal local
# Usage:
#   sh install_m1s_wifi_all.sh "SSID" "PAROLA"
#
# Instaleaza:
# - backup sigur SSID/parola
# - restore STA nativ
# - manager: dupa 240s fara IPv4 porneste AP
# - portal local pe 8080
# - parola vizibila in formular
# - candidat bun => salvat ca backup sigur
# - candidat gresit => reapare AP + portal
# - revenire de urgenta la backup dupa 10 minute
#
# NU instaleaza captive DNS/redirect automat; partea aceea nu a fost validata.

set -u

SAFE_SSID="${1:-}"
SAFE_PASS="${2:-}"

BASE=/data/m1s_wifi
SAFE_DIR="$BASE/safe"
CAND_DIR="$BASE/candidate"
POST_INIT=/data/scripts/post_init.sh
LOG=/tmp/m1s_wifi_manager.log

NOIP_SECONDS=240
CANDIDATE_TIMEOUT=30
AP_WATCHDOG_SECONDS=180
FAILED_AP_EMERGENCY_SECONDS=600

die() {
    echo "EROARE: $*" >&2
    exit 1
}

[ -n "$SAFE_SSID" ] || die 'Lipseste SSID. Exemplu: sh install_m1s_wifi_all.sh "Paul" "parola"'
[ -n "$SAFE_PASS" ] || die 'Lipseste parola Wi-Fi.'

mkdir -p "$BASE" "$SAFE_DIR" "$CAND_DIR" /data/scripts || die "Nu pot crea directoarele"

STAMP="$(date +%Y%m%d_%H%M%S 2>/dev/null || echo backup)"
[ -f "$POST_INIT" ] && cp "$POST_INIT" "$POST_INIT.before_m1s_wifi_$STAMP"

printf '%s' "$SAFE_SSID" > "$SAFE_DIR/ssid" || die "Nu pot salva SSID"
printf '%s' "$SAFE_PASS" > "$SAFE_DIR/pass" || die "Nu pot salva parola"
chmod 600 "$SAFE_DIR/ssid" "$SAFE_DIR/pass"

cat > "$BASE/restore_sta.sh" <<'EOF'
#!/bin/sh
BASE=/data/m1s_wifi
SAFE_DIR="$BASE/safe"
LOG=/tmp/m1s_wifi_manager.log

SSID="$(cat "$SAFE_DIR/ssid" 2>/dev/null)"
PASS="$(cat "$SAFE_DIR/pass" 2>/dev/null)"
IFACE=wlan0
MAC="$(ifconfig "$IFACE" 2>/dev/null | sed -n 's/.*HWaddr \([^ ]*\).*/\1/p' | head -n 1)"

[ -n "$SSID" ] || exit 1
[ -n "$MAC" ] || MAC=54:EF:44:29:3C:E4

rm -f "$BASE/ap_hold" "$BASE/test_noip"

setprop persist.sys.wifi_ssid "$SSID" 2>/dev/null
setprop persist.sys.wifi_password "$PASS" 2>/dev/null
sync

echo "$(date) Revenire STA sigur: $SSID" >> "$LOG"
mbasis_cli -nwk -c "$IFACE" "$MAC" "$SSID" "$PASS" 0 >> "$LOG" 2>&1
EOF

cat > "$BASE/mark_ap_access.sh" <<'EOF'
#!/bin/sh
IP="$(ifconfig wlan0 2>/dev/null |
    sed -n 's/.*inet addr:\([^ ]*\).*/\1/p' |
    head -n 1)"

case "$IP" in
    192.168.1.1|192.168.49.1)
        touch /data/m1s_wifi/ap_hold
        echo "$(date) Portal accesat in AP IP=$IP; ap_hold activat" \
            >> /tmp/m1s_wifi_manager.log
        ;;
esac
EOF

cat > "$BASE/ap_watchdog.sh" <<'EOF'
#!/bin/sh
DELAY="${1:-180}"
LOG=/tmp/m1s_wifi_manager.log

echo "$(date) Watchdog AP armat pentru ${DELAY}s" >> "$LOG"
sleep "$DELAY"

if [ -e /data/m1s_wifi/ap_hold ]; then
    echo "$(date) Watchdog AP: ap_hold activ; AP ramane deschis" >> "$LOG"
    exit 0
fi

echo "$(date) Watchdog AP: revenire la reteaua STA salvata" >> "$LOG"
/data/m1s_wifi/restore_sta.sh >> "$LOG" 2>&1
EOF

cat > "$BASE/candidate_failed_to_ap.sh" <<EOF
#!/bin/sh
LOG=/tmp/m1s_wifi_manager.log
PIDFILE=/tmp/m1s_candidate_ap_emergency.pid

echo "\$(date) Candidat esuat; revenire in AP pentru reconfigurare" >> "\$LOG"

if [ -f "\$PIDFILE" ]; then
    OLDPID="\$(cat "\$PIDFILE" 2>/dev/null)"
    [ -n "\$OLDPID" ] && kill "\$OLDPID" 2>/dev/null
    rm -f "\$PIDFILE"
fi

touch /data/m1s_wifi/ap_hold
/bin/wifi_start.sh AP >> "\$LOG" 2>&1

i=0
APIP=""
while [ "\$i" -lt 60 ]; do
    APIP="\$(ifconfig wlan0 2>/dev/null |
        sed -n 's/.*inet addr:\([^ ]*\).*/\1/p' |
        head -n 1)"
    case "\$APIP" in
        192.168.1.1|192.168.49.1) break ;;
    esac
    sleep 2
    i=\$((i + 2))
done

echo "\$(date) AP IP detectat: \${APIP:-necunoscut}" >> "\$LOG"

for p in \$(ps | awk '/[m]1s_wifi_portal_safe.sh/{print \$1}'); do
    kill -9 "\$p" 2>/dev/null
done

for p in \$(ps | awk '/nc -l -p 8080/ && !/awk/ {print \$1}'); do
    kill -9 "\$p" 2>/dev/null
done

sleep 1
nohup /data/m1s_wifi/m1s_wifi_portal_safe.sh \
    >/tmp/m1s_wifi_portal_safe_console.log 2>&1 &

sleep 2
if netstat -lnt 2>/dev/null | grep -q ':8080'; then
    echo "\$(date) AP reactivat; portal 8080 activ" >> "\$LOG"
else
    echo "\$(date) EROARE: AP activ, dar portalul 8080 nu asculta" >> "\$LOG"
fi

nohup sh -c '
sleep $FAILED_AP_EMERGENCY_SECONDS
if [ -e /data/m1s_wifi/ap_hold ]; then
    echo "\$(date) Timeout portal dupa candidat esuat; revenire la STA sigur" \
        >> /tmp/m1s_wifi_manager.log
    rm -f /data/m1s_wifi/ap_hold
    /data/m1s_wifi/restore_sta.sh >> /tmp/m1s_wifi_manager.log 2>&1
fi
' >/tmp/m1s_candidate_ap_emergency_console.log 2>&1 &

echo \$! > "\$PIDFILE"
exit 0
EOF

cat > "$BASE/wifi_apply_candidate.sh" <<EOF
#!/bin/sh
BASE=/data/m1s_wifi
SAFE_DIR="\$BASE/safe"
CAND_DIR="\$BASE/candidate"
LOG=/tmp/m1s_wifi_manager.log
TIMEOUT=$CANDIDATE_TIMEOUT

SSID="\$(cat "\$CAND_DIR/ssid" 2>/dev/null)"
PASS="\$(cat "\$CAND_DIR/pass" 2>/dev/null)"
IFACE=wlan0
MAC="\$(ifconfig "\$IFACE" 2>/dev/null | sed -n 's/.*HWaddr \([^ ]*\).*/\1/p' | head -n 1)"

[ -n "\$SSID" ] || exit 1
[ -n "\$MAC" ] || MAC=54:EF:44:29:3C:E4

rm -f "\$BASE/ap_hold"
echo "\$(date) Incerc candidat Wi-Fi: \$SSID" >> "\$LOG"

mbasis_cli -nwk -c "\$IFACE" "\$MAC" "\$SSID" "\$PASS" 0 >> "\$LOG" 2>&1

i=0
while [ "\$i" -lt "\$TIMEOUT" ]; do
    IP="\$(ifconfig "\$IFACE" 2>/dev/null |
        sed -n 's/.*inet addr:\([^ ]*\).*/\1/p' |
        head -n 1)"

    case "\$IP" in
        ""|192.168.1.1|192.168.49.1) ;;
        *)
            printf '%s' "\$SSID" > "\$SAFE_DIR/ssid"
            printf '%s' "\$PASS" > "\$SAFE_DIR/pass"
            chmod 600 "\$SAFE_DIR/ssid" "\$SAFE_DIR/pass"
            rm -f "\$CAND_DIR/ssid" "\$CAND_DIR/pass" "\$BASE/ap_hold"
            sync
            echo "\$(date) Candidat confirmat: \$SSID IP=\$IP; backup actualizat" >> "\$LOG"
            exit 0
            ;;
    esac

    sleep 2
    i=\$((i + 2))
done

echo "\$(date) Candidat esuat: \$SSID; revin in AP" >> "\$LOG"
/data/m1s_wifi/candidate_failed_to_ap.sh >> "\$LOG" 2>&1
exit 1
EOF

cat > "$BASE/m1s_wifi_portal_safe.sh" <<'EOF'
#!/bin/sh
BASE=/data/m1s_wifi
SAFE_DIR="$BASE/safe"
CAND_DIR="$BASE/candidate"
FIFO=/tmp/m1s_wifi_portal_fifo
LOG=/tmp/m1s_wifi_manager.log
PORT=8080

url_decode() {
    value="$(printf '%s' "$1" | sed 's/+/ /g; s/%/\\x/g')"
    printf '%b' "$value"
}

html_escape() {
    printf '%s' "$1" |
        sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g'
}

send_page() {
    CURRENT_SSID="$(html_escape "$(cat "$SAFE_DIR/ssid" 2>/dev/null)")"

    BODY_HTML="<!doctype html>
<html lang=\"ro\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Aqara M1S Wi-Fi</title>
<style>
body{font-family:Arial,sans-serif;background:#f3f5f7;margin:0;padding:24px;color:#222}
.card{max-width:520px;margin:30px auto;background:#fff;padding:24px;border-radius:14px;box-shadow:0 4px 18px rgba(0,0,0,.12)}
h1{font-size:24px;margin-top:0}
label{display:block;margin-top:16px;font-weight:bold}
input{box-sizing:border-box;width:100%;margin-top:6px;padding:12px;border:1px solid #aaa;border-radius:8px;font-size:16px}
button{width:100%;margin-top:22px;padding:13px;border:0;border-radius:8px;background:#1677ff;color:#fff;font-size:17px}
.note{font-size:14px;color:#555;line-height:1.4}
</style>
</head>
<body>
<div class=\"card\">
<h1>Configurare Wi-Fi Aqara M1S</h1>
<form method=\"POST\" action=\"/\">
<label for=\"ssid\">Numele retelei Wi-Fi (SSID)</label>
<input id=\"ssid\" name=\"ssid\" value=\"$CURRENT_SSID\" required>
<label for=\"wifi_key\">Parola Wi-Fi</label>
<input id=\"wifi_key\" name=\"wifi_key\" type=\"text\" autocomplete=\"off\" spellcheck=\"false\" required>
<button type=\"submit\">Testeaza si salveaza</button>
</form>
<p class=\"note\">Daca datele sunt corecte, hubul revine in reteaua noua. Daca testul esueaza, reapare reteaua lumi si portalul se redeschide.</p>
</div>
</body>
</html>"

    LEN="$(printf '%s' "$BODY_HTML" | wc -c)"
    printf 'HTTP/1.1 200 OK\r\n'
    printf 'Content-Type: text/html; charset=utf-8\r\n'
    printf 'Cache-Control: no-store, no-cache, must-revalidate\r\n'
    printf 'Connection: close\r\n'
    printf 'Content-Length: %s\r\n' "$LEN"
    printf '\r\n'
    printf '%s' "$BODY_HTML"
}

send_started() {
    BODY_HTML='<!doctype html><html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Test Wi-Fi</title></head><body><h2>Test Wi-Fi pornit</h2><p>Hubul incearca noua retea. Daca primeste IP, aceasta devine noul backup sigur. Daca esueaza, reteaua lumi si portalul vor reaparea.</p></body></html>'
    LEN="$(printf '%s' "$BODY_HTML" | wc -c)"
    printf 'HTTP/1.1 200 OK\r\n'
    printf 'Content-Type: text/html; charset=utf-8\r\n'
    printf 'Cache-Control: no-store\r\n'
    printf 'Connection: close\r\n'
    printf 'Content-Length: %s\r\n\r\n' "$LEN"
    printf '%s' "$BODY_HTML"
}

cleanup() {
    rm -f "$FIFO"
}
trap cleanup EXIT INT TERM

mkdir -p "$CAND_DIR"

while :; do
    rm -f "$FIFO"
    mkfifo "$FIFO" || exit 1

    REQUEST_FILE="/tmp/m1s_wifi_request.$$"
    rm -f "$REQUEST_FILE"

    nc -l -p "$PORT" < "$FIFO" > "$REQUEST_FILE" &
    NCPID=$!

    i=0
    while [ "$i" -lt 100 ]; do
        [ -s "$REQUEST_FILE" ] && break
        kill -0 "$NCPID" 2>/dev/null || break
        sleep 0.1
        i=$((i + 1))
    done

    REQUEST_LINE="$(head -n 1 "$REQUEST_FILE" 2>/dev/null | tr -d '\r')"
    /data/m1s_wifi/mark_ap_access.sh

    if printf '%s' "$REQUEST_LINE" | grep -q '^POST '; then
        LENGTH="$(sed -n 's/^[Cc]ontent-[Ll]ength:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$REQUEST_FILE" | tr -d '\r' | head -n 1)"
        [ -n "$LENGTH" ] || LENGTH=0
        BODY="$(awk 'BEGIN{body=0} body{printf "%s",$0} /^\r?$/{body=1}' "$REQUEST_FILE")"

        RAW_SSID="$(printf '%s' "$BODY" | sed -n 's/.*ssid=\([^&]*\).*/\1/p')"
        RAW_PASS="$(printf '%s' "$BODY" | sed -n 's/.*wifi_key=\([^&]*\).*/\1/p')"

        SSID="$(url_decode "$RAW_SSID")"
        PASS="$(url_decode "$RAW_PASS")"

        if [ -n "$SSID" ] && [ -n "$PASS" ]; then
            printf '%s' "$SSID" > "$CAND_DIR/ssid"
            printf '%s' "$PASS" > "$CAND_DIR/pass"
            chmod 600 "$CAND_DIR/ssid" "$CAND_DIR/pass"

            echo "$(date) Portal: candidat primit SSID=$SSID" >> "$LOG"
            send_started > "$FIFO"
            wait "$NCPID" 2>/dev/null
            rm -f "$REQUEST_FILE" "$FIFO"

            nohup "$BASE/wifi_apply_candidate.sh" \
                >/tmp/m1s_wifi_apply_candidate_console.log 2>&1 &
            sleep 1
            continue
        fi
    fi

    send_page > "$FIFO"
    wait "$NCPID" 2>/dev/null
    rm -f "$REQUEST_FILE" "$FIFO"
done
EOF

cat > "$BASE/wifi_manager.sh" <<EOF
#!/bin/sh
BASE=/data/m1s_wifi
LOG=/tmp/m1s_wifi_manager.log
NOIP_LIMIT=$NOIP_SECONDS
COUNT=0

echo "\$(date) Manager pornit" >> "\$LOG"

while :; do
    IP="\$(ifconfig wlan0 2>/dev/null |
        sed -n 's/.*inet addr:\([^ ]*\).*/\1/p' |
        head -n 1)"

    case "\$IP" in
        192.168.1.1|192.168.49.1)
            COUNT=0
            echo "\$(date) Mod AP detectat IP=\$IP" >> "\$LOG"
            ;;
        "")
            if [ -e "\$BASE/test_noip" ]; then
                :
            fi
            COUNT=\$((COUNT + 10))
            if [ "\$COUNT" -ge "\$NOIP_LIMIT" ]; then
                if [ -e "\$BASE/actions_enabled" ]; then
                    echo "\$(date) \$NOIP_LIMIT secunde fara IP; pornire AP" >> "\$LOG"
                    rm -f "\$BASE/ap_hold"
                    /bin/wifi_start.sh AP >> "\$LOG" 2>&1
                    nohup "\$BASE/ap_watchdog.sh" $AP_WATCHDOG_SECONDS \
                        >/tmp/m1s_ap_watchdog_console.log 2>&1 &
                else
                    echo "\$(date) Fara IPv4, dar actiunile sunt dezactivate" >> "\$LOG"
                fi
                COUNT=0
            fi
            ;;
        *)
            COUNT=0
            ;;
    esac

    sleep 10
done
EOF

cat > /data/scripts/wifi_manager_start.sh <<'EOF'
#!/bin/sh
if ! ps | grep '[w]ifi_manager.sh' >/dev/null 2>&1; then
    nohup /data/m1s_wifi/wifi_manager.sh \
        >/tmp/m1s_wifi_manager_console.log 2>&1 &
fi
exit 0
EOF

cat > /data/scripts/wifi_portal_start.sh <<'EOF'
#!/bin/sh
if ! ps | grep '[m]1s_wifi_portal_safe.sh' >/dev/null 2>&1; then
    nohup /data/m1s_wifi/m1s_wifi_portal_safe.sh \
        >/tmp/m1s_wifi_portal_safe_console.log 2>&1 &
fi
exit 0
EOF

chmod 700 \
    "$BASE/restore_sta.sh" \
    "$BASE/mark_ap_access.sh" \
    "$BASE/ap_watchdog.sh" \
    "$BASE/candidate_failed_to_ap.sh" \
    "$BASE/wifi_apply_candidate.sh" \
    "$BASE/m1s_wifi_portal_safe.sh" \
    "$BASE/wifi_manager.sh" \
    /data/scripts/wifi_manager_start.sh \
    /data/scripts/wifi_portal_start.sh

for f in \
    "$BASE/restore_sta.sh" \
    "$BASE/mark_ap_access.sh" \
    "$BASE/ap_watchdog.sh" \
    "$BASE/candidate_failed_to_ap.sh" \
    "$BASE/wifi_apply_candidate.sh" \
    "$BASE/m1s_wifi_portal_safe.sh" \
    "$BASE/wifi_manager.sh" \
    /data/scripts/wifi_manager_start.sh \
    /data/scripts/wifi_portal_start.sh
do
    sh -n "$f" || die "Sintaxa invalida: $f"
done

touch "$BASE/actions_enabled"
rm -f "$BASE/test_noip" "$BASE/ap_hold"

if [ ! -f "$POST_INIT" ]; then
    cat > "$POST_INIT" <<'EOF'
#!/bin/sh
exit 0
EOF
    chmod 700 "$POST_INIT"
fi

# Scoate o instalare veche a blocului nostru, daca exista.
sed -i '/# BEGIN M1S WIFI FALLBACK/,/# END M1S WIFI FALLBACK/d' "$POST_INIT"

# Insereaza inainte de ultimul exit 0.
TMP=/tmp/post_init.m1s_wifi.$$
awk '
/^exit 0$/ && !done {
    print "# BEGIN M1S WIFI FALLBACK"
    print "if [ -x /data/scripts/wifi_manager_start.sh ]; then"
    print "    /data/scripts/wifi_manager_start.sh"
    print "fi"
    print "if [ -x /data/scripts/wifi_portal_start.sh ]; then"
    print "    /data/scripts/wifi_portal_start.sh"
    print "fi"
    print "# END M1S WIFI FALLBACK"
    done=1
}
{ print }
END {
    if (!done) {
        print "# BEGIN M1S WIFI FALLBACK"
        print "if [ -x /data/scripts/wifi_manager_start.sh ]; then"
        print "    /data/scripts/wifi_manager_start.sh"
        print "fi"
        print "if [ -x /data/scripts/wifi_portal_start.sh ]; then"
        print "    /data/scripts/wifi_portal_start.sh"
        print "fi"
        print "# END M1S WIFI FALLBACK"
        print "exit 0"
    }
}
' "$POST_INIT" > "$TMP" || die "Nu pot actualiza post_init"

mv "$TMP" "$POST_INIT"
chmod 700 "$POST_INIT"
sh -n "$POST_INIT" || die "post_init invalid; restaureaza backupul $POST_INIT.before_m1s_wifi_$STAMP"

# Opreste numai procesele noastre vechi.
for p in $(ps | awk '/[w]ifi_manager.sh/{print $1}'); do
    kill -9 "$p" 2>/dev/null
done
for p in $(ps | awk '/[m]1s_wifi_portal_safe.sh/{print $1}'); do
    kill -9 "$p" 2>/dev/null
done
for p in $(ps | awk '/nc -l -p 8080/ && !/awk/ {print $1}'); do
    kill -9 "$p" 2>/dev/null
done

sleep 2
/data/scripts/wifi_manager_start.sh
/data/scripts/wifi_portal_start.sh
sleep 3

sync

echo
echo "INSTALARE TERMINATA"
echo "SSID sigur: $SAFE_SSID"
echo "Timeout candidat: ${CANDIDATE_TIMEOUT}s"
echo "Fallback AP dupa: ${NOIP_SECONDS}s fara IPv4"
echo
echo "Verificare:"
ps | grep '[w]ifi_manager.sh'
ps | grep '[m]1s_wifi_portal_safe.sh'
netstat -lnt | grep ':8080'
ifconfig wlan0 | grep 'inet addr'
echo
echo "Portal manual in AP: http://192.168.49.1:8080/ sau http://192.168.1.1:8080/"
