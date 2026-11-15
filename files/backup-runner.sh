#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
MODE="${1:-backup}"
REPO="${RESTIC_REPOSITORY:?}"
MOUNT="${REPO%/restic}"
# Prevent silently writing backups to the local directory when NAS is unavailable.
mountpoint -q "$MOUNT" || { echo "NAS not mounted: $MOUNT" >&2; exit 1; }
[[ -w "$MOUNT" ]] || { echo "NAS not writable: $MOUNT" >&2; exit 1; }
if [[ "$MODE" == backup ]]; then
  python3 /usr/local/libexec/github_backup.py
  if [[ ! -f "$REPO/config" ]]; then
    restic init
  fi
  restic backup "$BACKUP_CACHE" /var/lib/github-backup/status --tag github --host "$(hostname -s)"
elif [[ "$MODE" == maintenance ]]; then
  [[ -f "$REPO/config" ]] || { echo 'Restic repository missing' >&2; exit 1; }
  restic forget --tag github --keep-daily "${RETENTION_DAILY:-7}" --keep-weekly "${RETENTION_WEEKLY:-4}" --keep-monthly "${RETENTION_MONTHLY:-12}" --prune
  restic check
else
  echo "Unknown mode: $MODE" >&2; exit 2
fi
