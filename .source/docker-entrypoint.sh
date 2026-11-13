#!/bin/sh
# PrivateGlue container entrypoint.
#
# The app runs as the unprivileged "appuser". Older images ran as root, so bind-mounted
# folders from existing installs (./data, ./notes, ...) are often owned by root and the
# app could not write to them after upgrading. When started as root, this script fixes
# ownership of the data folders and then drops privileges before starting the app.
#
# Optional: PUID / PGID set the user and group id the app runs as (default 1000:1000),
# useful when bind-mounted folders should stay owned by a specific host user.
set -e

DATA_DIRS="/app/data /app/notes /app/backups /app/secret"

# Fail fast with one clear line instead of letting every gunicorn worker crash with a
# traceback (gunicorn can also take up to 30s to give up, which looks like a hang).
if [ -z "${SECRET_KEY:-}" ]; then
    echo "[entrypoint] ERROR: SECRET_KEY is not set. Add it to your .env file, for example:" >&2
    echo "[entrypoint]   echo \"SECRET_KEY=\$(openssl rand -hex 32)\" >> .env" >&2
    exit 1
fi

if [ "$(id -u)" = "0" ]; then
    PUID="${PUID:-1000}"
    PGID="${PGID:-1000}"

    if [ "$(id -g appuser)" != "$PGID" ]; then
        groupmod -o -g "$PGID" appgroup
    fi
    if [ "$(id -u appuser)" != "$PUID" ]; then
        usermod -o -u "$PUID" appuser
    fi

    for dir in $DATA_DIRS; do
        mkdir -p "$dir"
        # Only walk the tree when something is actually owned by someone else.
        if [ -n "$(find "$dir" \( ! -user appuser -o ! -group appgroup \) -print -quit)" ]; then
            echo "[entrypoint] Fixing ownership of $dir for uid=$PUID gid=$PGID"
            chown -R appuser:appgroup "$dir"
        fi
    done

    exec setpriv --reuid=appuser --regid=appgroup --init-groups "$@"
fi

# Started as a non-root user (for example with "user:" in compose): we can't fix
# ownership, so fail early with a clear message instead of a stack trace.
for dir in $DATA_DIRS; do
    if [ -d "$dir" ] && [ ! -w "$dir" ]; then
        echo "[entrypoint] ERROR: $dir is not writable by uid $(id -u)." >&2
        echo "[entrypoint] Fix it on the host, e.g.: sudo chown -R $(id -u):$(id -g) <your $dir mount>" >&2
        exit 1
    fi
done

exec "$@"
