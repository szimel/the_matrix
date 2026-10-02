#!/usr/bin/env bash
# =============================================================================
# create-user.sh — add a Radicale user and optionally share a calendar
# Run on The Matrix from /home/abed_23/apps/calendar
#
#   ./scripts/create-user.sh add-user  kamrie
#   ./scripts/create-user.sh add-calendar abed family
#   ./scripts/create-user.sh share      abed family kamrie
# =============================================================================
set -euo pipefail

RADICALE_URL="${RADICALE_URL:-http://127.0.0.1:5232}"
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$COMPOSE_DIR"

usage() {
  cat <<'EOF'
Usage:
  create-user.sh add-user     <username>
  create-user.sh add-calendar <owner> <calendar>
  create-user.sh share        <owner> <calendar> <recipient> [permissions]
  create-user.sh list-shared  <username>

add-user creates the htpasswd entry (bcrypt). You will be prompted for a password.
add-calendar creates a calendar collection that supports events AND todos.
share makes <owner>'s calendar appear inside <recipient>'s account.
         Default permissions are rw (recipient can add events too).
EOF
  exit 1
}

dc() { docker compose "$@"; }

cmd_add_user() {
  local user="$1"
  echo "==> Adding user '$user' (bcrypt). Enter the password at the prompt."
  if dc exec -T radicale test -f /etc/radicale/users; then
    dc exec radicale htpasswd -B /etc/radicale/users "$user"
  else
    dc exec radicale htpasswd -B -c /etc/radicale/users "$user"
  fi
  echo "==> Verifying the hash is not plaintext:"
  dc exec -T radicale cat /etc/radicale/users | sed "s/^/    /"
  cat <<EOF

==> Check the new line starts with \$2y\$ or \$2b\$ (or \$5\$ with a 16-char salt).
    A bare password with no \$ prefix means it fell back to plaintext.
EOF
}

cmd_add_calendar() {
  local owner="$1" cal="$2"
  local body
  body="$(mktemp)"
  cat > "$body" <<XML
<?xml version="1.0" encoding="UTF-8" ?>
<create xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
 <set><prop>
  <resourcetype><collection /><C:calendar /></resourcetype>
  <C:supported-calendar-component-set>
   <C:comp name="VEVENT" />
   <C:comp name="VJOURNAL" />
   <C:comp name="VTODO" />
  </C:supported-calendar-component-set>
  <displayname>${cal}</displayname>
 </prop></set>
</create>
XML
  echo "==> Creating /$owner/$cal/ with VEVENT + VTODO support"
  read -rsp "Password for $owner: " pw; echo
  curl -s -o /dev/null -w "    create -> %{http_code}\n" \
    -u "$owner:$pw" -X MKCALENDAR \
    -H 'Content-Type: application/xml' \
    --data-binary "@${body}" \
    "$RADICALE_URL/$owner/$cal/"
  unset pw
  rm -f "$body"
}

cmd_share() {
  local owner="$1" cal="$2" recip="$3" perms="${4:-rw}"
  read -rsp "Password for $owner: " pw; echo
  echo "==> Mapping /$owner/$cal/ into $recip's account at /$recip/$cal/"
  curl -s -w "\n    map/create -> %{http_code}\n" \
    -u "$owner:$pw" -X POST \
    --data-urlencode "PathOrToken=/$recip/$cal/" \
    --data-urlencode "PathMapped=/$owner/$cal/" \
    --data-urlencode "User=$recip" \
    --data-urlencode "Permissions=$perms" \
    --data-urlencode "Enabled=True" \
    --data-urlencode "Hidden=False" \
    "$RADICALE_URL/.sharing/v1/map/create"
  unset pw

  read -rsp "Password for $recip: " pw2; echo
  echo "==> $recip accepting the share (both sides must enable it)"
  curl -s -w "\n    map/update -> %{http_code}\n" \
    -u "$recip:$pw2" -X POST \
    --data-urlencode "PathOrToken=/$recip/$cal/" \
    --data-urlencode "Enabled=True" \
    --data-urlencode "Hidden=False" \
    "$RADICALE_URL/.sharing/v1/map/update"
  unset pw2

  echo "==> Done. $recip should see '$cal' after the next phone sync."
}

cmd_list_shared() {
  local user="$1"
  read -rsp "Password for $user: " pw; echo
  curl -s -H 'Accept: text/plain' -d "" -u "$user:$pw" \
    "$RADICALE_URL/.sharing/v1/all/list"
  unset pw
}

case "${1:-}" in
  add-user)     shift; [ $# -eq 1 ] || usage; cmd_add_user "$@" ;;
  add-calendar) shift; [ $# -eq 2 ] || usage; cmd_add_calendar "$@" ;;
  share)        shift; [ $# -ge 3 ] || usage; cmd_share "$@" ;;
  list-shared)  shift; [ $# -eq 1 ] || usage; cmd_list_shared "$@" ;;
  *) usage ;;
esac
