#!/usr/bin/env bash
# Barter Express: deploy the reviewed public guest-valuation release.
# Run with sudo on srv1929638. No database restore or downgrade is performed.
set -Eeuo pipefail
umask 077

APP=/opt/barterex/app
PYTHON=/opt/barterex/venv-video-cedf280/bin/python
BASE=3b08d5d82fab35ea8d7d4023e1fcf54f2090d711
TARGET=f50c950024491ca3d700453238e73a4f378f1630
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
UNIT_PREFIX="barterex-guest-deploy-${STAMP}-$$"

die() { printf 'STOP: %s\n' "$*" >&2; exit 1; }
say() { printf '\n%s\n' "$*"; }
git_app() {
    # New public CSS/JS files must remain readable by Nginx, despite private backup permissions.
    runuser -u ayara -- /bin/sh -c 'app_dir=$1; shift; umask 022; exec git -C "$app_dir" "$@"' sh "$APP" "$@"
}
sql() {
    runuser -u postgres -- env -i PATH=/usr/bin:/bin LC_ALL=C \
        /usr/bin/psql -X -w -qAt --username=postgres \
        --host=/var/run/postgresql --port=5432 --dbname=barterxpress \
        --set=ON_ERROR_STOP=1 --command="$1"
}
run_app() {
    local step=$1
    shift
    systemd-run --quiet --wait --pipe --collect --expand-environment=no \
        --unit="${UNIT_PREFIX}-${step}" \
        --property=Type=exec --property=User=ayara --property=Group=www-data \
        --property="WorkingDirectory=$APP" \
        --property="EnvironmentFile=$APP/.env" --property=UMask=0077 \
        --setenv=PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$@"
}

[[ $EUID -eq 0 ]] || die 'Run this script with sudo.'
[[ $(hostname -s) == srv1929638 ]] || die 'This script is prepared for srv1929638 only.'
exec 9>>/run/lock/barterex-deployment.lock
flock -n 9 || die 'Another Barter Express deployment is running.'
exec 8>>/run/lock/barterex-valuator-deploy.lock
flock -n 8 || die 'A valuator deployment is running.'
cd "$APP"

say '1/7 Checking the current release and service configuration.'
[[ $(git_app rev-parse HEAD) == "$BASE" ]] || die 'The live Git revision has changed. Send the new revision for review.'
[[ $(git_app branch --show-current) == main ]] || die 'The live checkout is not on main.'
git_app diff --quiet || die 'Tracked files have local changes.'
git_app diff --cached --quiet || die 'There are staged changes.'
[[ -x $PYTHON ]] || die 'The expected Python environment is missing.'
for unit in barterex.service barterex-video-publishing.service barterex-maintenance.timer; do
    systemctl is-active --quiet "$unit" || die "$unit is not active."
done
for unit in barterex.service barterex-video-publishing.service barterex-maintenance.service; do
    [[ $(systemctl show "$unit" -p WorkingDirectory --value) == "$APP" ]] || die "$unit uses a different application directory."
    systemctl show "$unit" -p EnvironmentFiles --value | grep -Fq "$APP/.env" || die "$unit uses a different environment file."
done
[[ $(systemctl show barterex.service -p User --value) == ayara ]] || die 'Unexpected web-service user.'
[[ $(systemctl show barterex.service -p Group --value) == www-data ]] || die 'Unexpected web-service group.'
systemctl show barterex.service -p ExecStart --value | grep -Fq 'path=/opt/barterex/venv-video-cedf280/bin/gunicorn' || die 'Unexpected Gunicorn executable.'
case $(systemctl show barterex-maintenance.service -p User --value) in
    ayara|root|'') ;;
    *) die 'The maintenance user needs a review before private guest storage is created.' ;;
esac
for path in .env instance static/uploads migrations; do
    [[ -e $APP/$path && ! -L $APP/$path ]] || die "Review the storage/backup path: $APP/$path"
done

git_app fetch --no-tags origin main
git_app merge-base --is-ancestor "$TARGET" origin/main || die 'The reviewed release is not available on origin/main.'
git_app merge-base --is-ancestor "$BASE" "$TARGET" || die 'The release is not a fast-forward.'
git_app diff --quiet "$BASE" "$TARGET" -- requirements.txt || die 'Dependencies changed; review required.'

PRECHECK=$(run_app precheck -c '
import math
from app import app, db
from sqlalchemy import text
from models import SystemSettings
from valuator_client import _timeout, is_enabled
with app.app_context():
    if db.engine.url.get_backend_name() != "postgresql":
        raise SystemExit("STOP: the service environment is not using PostgreSQL.")
    with db.engine.connect() as connection:
        name, address, port = connection.execute(text("SELECT current_database(), inet_server_addr()::text, inet_server_port()")).one()
        revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if name != "barterxpress" or address not in (None, "127.0.0.1/32", "127.0.0.1", "::1/128", "::1") or port not in (None, 5432):
        raise SystemExit("STOP: the service database does not match the local backup target.")
    if revisions != ["service_fee_20261113"]:
        raise SystemExit("STOP: unexpected live migration revision.")
    settings = SystemSettings.query.limit(2).all()
    if len(settings) != 1 or settings[0].maintenance_mode is not False:
        raise SystemExit("STOP: existing maintenance settings need review.")
    if not is_enabled():
        raise SystemExit("STOP: the valuator is not configured in this service environment.")
    drain = max(30, math.ceil(_timeout()) + 15)
    if drain > 300:
        raise SystemExit("STOP: the valuator timeout requires a longer deployment window.")
    print("SETTINGS_ID=" + str(settings[0].id))
    print("DRAIN_SECONDS=" + str(drain))
    print("Production PostgreSQL and parent migration verified.")
')
printf '%s\n' "$PRECHECK"
SETTINGS_ID=$(printf '%s\n' "$PRECHECK" | sed -n 's/^SETTINGS_ID=//p')
DRAIN_SECONDS=$(printf '%s\n' "$PRECHECK" | sed -n 's/^DRAIN_SECONDS=//p')
[[ $SETTINGS_ID =~ ^[0-9]+$ && $DRAIN_SECONDS =~ ^[0-9]+$ ]] || die 'Could not parse the deployment precheck.'
[[ $(sql 'SELECT version_num FROM alembic_version;') == service_fee_20261113 ]] || die 'The backup connection has a different revision.'

install -d -o root -g root -m 0700 /var/backups/barterex
DB_BYTES=$(sql "SELECT pg_database_size('barterxpress');")
FILE_BYTES=$(du -sb .env instance static/uploads migrations | awk '{total += $1} END {printf "%.0f\n", total}')
FREE_BYTES=$(df -B1 --output=avail /var/backups/barterex | tail -n 1 | tr -d ' ')
[[ $DB_BYTES =~ ^[0-9]+$ && $FILE_BYTES =~ ^[0-9]+$ && $FREE_BYTES =~ ^[0-9]+$ ]] || die 'Could not calculate backup space.'
(( FREE_BYTES > 2 * (DB_BYTES + FILE_BYTES) + 536870912 )) || die 'Insufficient free space for the deployment backup.'
BACKUP=$(mktemp -d "/var/backups/barterex/guest-${STAMP}-XXXXXX")
printf '%s\n' "$BASE" > "$BACKUP/previous-commit.txt"
printf '%s\n' "$TARGET" > "$BACKUP/target-commit.txt"
printf 'Original maintenance_mode: false\nSettings row: %s\n' "$SETTINGS_ID" > "$BACKUP/maintenance-state.txt"
systemctl cat barterex.service barterex-video-publishing.service barterex-maintenance.service barterex-maintenance.timer > "$BACKUP/services.txt"
MAINTENANCE_CHANGED=0
TIMER_PAUSED=0
WRITERS_PAUSED=0

recover() {
    # Let the parent shell handle a failed command substitution exactly once.
    if (( BASH_SUBSHELL > 0 )); then exit 1; fi
    trap - ERR INT TERM HUP
    set +e
    say 'Deployment did not complete. Recovering the previous website code.'
    recovery_ok=1
    if [[ $MAINTENANCE_CHANGED == 1 ]]; then
        sql "UPDATE system_settings SET maintenance_mode = TRUE WHERE id = $SETTINGS_ID;" >/dev/null || recovery_ok=0
    fi
    if [[ $TIMER_PAUSED == 1 ]]; then
        systemctl stop barterex-maintenance.timer || recovery_ok=0
        for ((attempt=0; attempt<90; attempt++)); do
            state=$(systemctl show barterex-maintenance.service -p ActiveState --value)
            case $state in active|activating|deactivating) sleep 1 ;; *) break ;; esac
        done
        case $state in active|activating|deactivating) recovery_ok=0 ;; esac
    fi
    migration_state=$(systemctl show "${UNIT_PREFIX}-migrate.service" -p ActiveState --value 2>/dev/null)
    case $migration_state in
        active|activating|deactivating)
            systemctl stop "${UNIT_PREFIX}-migrate.service" || recovery_ok=0
            migration_state=$(systemctl show "${UNIT_PREFIX}-migrate.service" -p ActiveState --value 2>/dev/null)
            case $migration_state in active|activating|deactivating) recovery_ok=0 ;; esac
            ;;
    esac
    if [[ $WRITERS_PAUSED == 1 ]]; then
        systemctl stop barterex.service barterex-video-publishing.service || recovery_ok=0
        for unit in barterex.service barterex-video-publishing.service; do
            [[ $(systemctl show "$unit" -p ActiveState --value) == inactive ]] || recovery_ok=0
        done
        if [[ $recovery_ok == 1 && $(git_app rev-parse HEAD) != "$BASE" ]]; then
            git_app switch --detach "$BASE" || recovery_ok=0
        fi
        [[ $(git_app rev-parse HEAD) == "$BASE" ]] || recovery_ok=0
    fi
    if [[ $recovery_ok == 1 && $WRITERS_PAUSED == 1 ]]; then
        systemctl start barterex.service barterex-video-publishing.service || recovery_ok=0
    fi
    for unit in barterex.service barterex-video-publishing.service; do
        systemctl is-active --quiet "$unit" || recovery_ok=0
    done
    if [[ $recovery_ok == 1 && $MAINTENANCE_CHANGED == 1 ]]; then
        sql "UPDATE system_settings SET maintenance_mode = FALSE WHERE id = $SETTINGS_ID;" >/dev/null || recovery_ok=0
    fi
    if [[ $recovery_ok == 1 && $TIMER_PAUSED == 1 ]]; then
        systemctl start barterex-maintenance.timer || recovery_ok=0
        systemctl is-active --quiet barterex-maintenance.timer || recovery_ok=0
    fi
    if [[ $recovery_ok != 1 && $MAINTENANCE_CHANGED == 1 ]]; then
        sql "UPDATE system_settings SET maintenance_mode = TRUE WHERE id = $SETTINGS_ID;" >/dev/null
        systemctl stop barterex-maintenance.timer
    fi
    printf 'Recovery command status: %s\nBackup directory: %s\n' "$recovery_ok" "$BACKUP"
    if [[ $recovery_ok != 1 ]]; then printf 'Recovery is incomplete; manual review is required.\n'; fi
    printf 'No database downgrade or restore was performed. Send this output for review.\n'
    exit 1
}
trap recover ERR INT TERM HUP

say '2/7 Pausing new user activity and allowing current valuation requests to finish.'
TIMER_PAUSED=1
systemctl stop barterex-maintenance.timer
for ((attempt=0; attempt<90; attempt++)); do
    state=$(systemctl show barterex-maintenance.service -p ActiveState --value)
    case $state in active|activating|deactivating) sleep 1 ;; *) break ;; esac
done
case $state in active|activating|deactivating) false ;; esac
MAINTENANCE_CHANGED=1
[[ $(sql "UPDATE system_settings SET maintenance_mode = TRUE WHERE id = $SETTINGS_ID AND maintenance_mode IS FALSE RETURNING id;") == "$SETTINGS_ID" ]]
for ((remaining=DRAIN_SECONDS; remaining>0; remaining-=5)); do
    if (( remaining % 30 < 5 )); then printf 'Waiting for existing requests: about %s seconds remain.\n' "$remaining"; fi
    sleep 5
done
pending=$(sql "SELECT count(*) FROM item WHERE verification_status = 'pending_valuation' AND ai_valuated_at IS NULL;")
if [[ $pending != 0 ]]; then
    printf 'STOP: %s valuation record(s) are still pending. No code or schema has been changed.\n' "$pending" >&2
    false
fi
WRITERS_PAUSED=1
systemctl stop barterex.service barterex-video-publishing.service
for unit in barterex.service barterex-video-publishing.service; do
    [[ $(systemctl show "$unit" -p ActiveState --value) == inactive ]]
done

say '3/7 Backing up the database and private application files.'
runuser -u postgres -- env -i PATH=/usr/bin:/bin LC_ALL=C \
    /usr/bin/pg_dump -w --username=postgres --host=/var/run/postgresql --port=5432 \
    --format=custom --dbname=barterxpress > "$BACKUP/barterxpress.dump"
pg_restore --list "$BACKUP/barterxpress.dump" > "$BACKUP/barterxpress.dump.list"
archive_paths=(.env instance static/uploads migrations)
[[ ! -e $APP/.env.save ]] || archive_paths+=(.env.save)
tar --acls --xattrs -czf "$BACKUP/private-files.tar.gz" -C "$APP" "${archive_paths[@]}"

say '4/7 Installing the exact reviewed code revision.'
git_app diff --quiet
git_app diff --cached --quiet
git_app merge --ff-only "$TARGET"
[[ $(git_app rev-parse HEAD) == "$TARGET" ]]
install -d -o ayara -g www-data -m 0700 "$APP/instance/guest_valuations"

say '5/7 Applying the guest-valuation database migration.'
run_app migrate -c '
from app import app, db
from sqlalchemy import text, inspect
from flask_migrate import upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory
with app.app_context():
    if db.engine.url.get_backend_name() != "postgresql" or db.engine.url.database != "barterxpress":
        raise SystemExit("STOP: unexpected migration database.")
    config = Config("migrations/alembic.ini")
    config.set_main_option("script_location", "migrations")
    if ScriptDirectory.from_config(config).get_heads() != ["add_guest_valuations"]:
        raise SystemExit("STOP: unexpected migration heads.")
    with db.engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if revision != ["service_fee_20261113"]:
        raise SystemExit("STOP: unexpected starting revision.")
    upgrade(revision="add_guest_valuations")
    with db.engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if revision != ["add_guest_valuations"] or not inspect(db.engine).has_table("guest_valuation"):
        raise SystemExit("STOP: migration verification failed.")
    print("Migration verified: add_guest_valuations; guest_valuation table exists.")
'

say '6/7 Starting the application and video worker.'
systemctl start barterex.service barterex-video-publishing.service
systemctl is-active --quiet barterex.service
systemctl is-active --quiet barterex-video-publishing.service
sql "UPDATE system_settings SET maintenance_mode = FALSE WHERE id = $SETTINGS_ID;" >/dev/null

say '7/7 Checking the live HTTPS pages and new assets.'
index=0
for path in / /marketplace /login /admin/login /check-item-value /value/start /static/js/guest-valuation.js /static/css/item-form.css; do
    index=$((index+1))
    code=$(curl --silent --show-error --fail --retry 3 --retry-connrefused \
        --retry-delay 2 --retry-max-time 45 --connect-timeout 5 --max-time 15 \
        --output "$BACKUP/http-$index.html" --write-out '%{http_code}' \
        "https://barterxpress.com${path}?deploy=${TARGET}")
    printf '%s -> HTTP %s\n' "$path" "$code"
    [[ $code == 200 ]]
    if [[ $path == /value/start ]]; then
        grep -q 'guest-valuation.js' "$BACKUP/http-$index.html"
    fi
done
systemctl start barterex-maintenance.timer
systemctl is-active --quiet barterex-maintenance.timer
systemctl is-active --quiet barterex.service
systemctl is-active --quiet barterex-video-publishing.service
trap - ERR INT TERM HUP
printf '\nDEPLOYMENT COMPLETE\nRelease: %s\nMigration: %s\nBackup: %s\n' "$TARGET" add_guest_valuations "$BACKUP"
printf 'Web service, video worker, timer and HTTPS checks passed.\n'
printf 'Next: test one guest valuation and save it to your own account.\n'
