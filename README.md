# GitHub backup via Ansible, Git mirrors, Restic, systemd

## Scope
Backs up **repositories owned by the authenticated GitHub user**, including private, archived and forked repositories. Does not include organization-owned repos, GitHub issues/PR discussions, release binaries, wiki repos, Actions secrets, or other platform metadata. Git LFS objects are fetched. Restic snapshots preserve previous mirror states even if refs are deleted upstream.

## Setup
1. Install Ansible and the `ansible.posix` collection on your controller: `ansible-galaxy collection install -r requirements.yml`.
2. Update `inventory.ini` and `group_vars/github_backup.yml`. Select `backup_nas_type: nfs` or `cifs`, and set the source.
3. Create `secrets.yml` with `github_token`, `restic_password` and (for CIFS) `nas_username`/`nas_password`; encrypt it with `ansible-vault encrypt secrets.yml`. Do not commit unencrypted secrets.
4. GitHub token: use a classic PAT with `repo` scope for personal private repositories, or a fine-grained token with repository **Contents: read** and **Metadata: read** access to all desired owned repos. Verify token access and renewal; GitHub permissions and policies can limit visibility.
5. **NFS**: ensure the NAS export maps the `githubbackup` service user's UID/GID to a writable directory. NFS root squashing and mismatched UID/GID are common causes of permission failures. **CIFS**: set credentials and optionally adjust mount options for NAS compatibility.
6. Run: `ansible-playbook -i inventory.ini site.yml -e @secrets.yml --ask-vault-pass`.
7. Run initial backup: `sudo systemctl start github-backup.service`. Review `sudo journalctl -u github-backup.service -n 100 --no-pager`.
8. Check timers: `systemctl list-timers 'github-backup*'`.

## Operations
- Backup status: `sudo journalctl -u github-backup.service --since yesterday`.
- Maintenance status: `sudo journalctl -u github-backup-maintenance.service --since '7 days ago'`.
- Restic snapshots (run as service user with EnvironmentFile loaded): `sudo systemctl cat github-backup.service` to locate config; use `sudo -u githubbackup env RESTIC_REPOSITORY=/mnt/github-backups/restic RESTIC_PASSWORD='...' restic snapshots` (avoid passwords in shell history; prefer loading secrets securely).
- `last-run.json` in `/var/lib/github-backup/status` records discovered repos and failures.
- Alerts: configure your existing monitoring (e.g., Zabbix) to alert when systemd service fails, or the last successful Restic snapshot becomes stale. Logs are in journald.
- The maintenance timer runs Sunday at 04:00 and performs `forget --prune` plus `restic check`. Pruning can be expensive; schedule outside the backup window.

## Restore
1. Ensure NAS is mounted and Restic credentials are available to an authorized administrator.
2. List snapshots: `restic -r /mnt/github-backups/restic snapshots`.
3. Restore into an **empty** directory: `restic -r /mnt/github-backups/restic restore SNAPSHOT_ID --target /tmp/github-restore`.
4. Find the mirror: `/tmp/github-restore/var/lib/github-backup/mirrors/OWNER/REPO.git` (depending on the snapshot path shown by `restic ls SNAPSHOT_ID`).
5. Restore a working copy: `git clone /tmp/github-restore/var/lib/github-backup/mirrors/OWNER/REPO.git /tmp/restored-repo`.
6. To republish a repository, create an **empty** GitHub repository, then run `git -C /path/to/REPO.git push --mirror https://github.com/OWNER/NEW_REPO.git`. For LFS: `git -C /path/to/REPO.git lfs push --all https://github.com/OWNER/NEW_REPO.git` (authentication required). **Warning:** `push --mirror` replaces/deletes remote refs. Only push to a new empty destination or after explicit review.
7. Test restores quarterly and verify commit history, tags, branches and LFS objects.

## Limitations / hardening
- The backup service uses an EnvironmentFile with secrets readable by root; systemd services run as an unprivileged user. For strict isolation, move secrets to systemd credentials and a root-only mount helper.
- Never allow a missing NAS mount to redirect writes to local disk. Runner checks `mountpoint` before Restic operations.
- `restic check` validates structure; schedule occasional `restic check --read-data-subset=...` to verify actual content.
- Do not expose Restic storage to untrusted users; a compromised backup account could delete snapshots. NAS snapshots or immutable/offline copies provide stronger ransomware protection.
- A new GitHub token may be needed after expiration or revocation. Backups should be monitored.
- `git fsck` is performed on every mirror; for very large repositories this can be slow.
