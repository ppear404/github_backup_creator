#!/usr/bin/env python3
"""Backup all repositories owned by a GitHub user using the GitHub REST API."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone

OWNER = os.environ['GITHUB_OWNER']
TOKEN = os.environ['GH_TOKEN']
BASE = pathlib.Path(os.environ['BACKUP_CACHE'])
STATUS = pathlib.Path('/var/lib/github-backup/status')

def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, timeout=3600,
                   env={**os.environ, 'GIT_TERMINAL_PROMPT': '0',
                        'GIT_CONFIG_COUNT': '1',
                        'GIT_CONFIG_KEY_0': 'credential.helper',
                        'GIT_CONFIG_VALUE_0': '!f() { echo username=x-access-token; echo password="$GH_TOKEN"; }; f'})

def repositories():
    page = 1
    result = []
    while True:
        url = f'https://api.github.com/user/repos?affiliation=owner&per_page=100&page={page}&sort=full_name'
        request = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {TOKEN}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'github-backup-local/1.0'})
        with urllib.request.urlopen(request, timeout=60) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise RuntimeError('Unexpected GitHub API response')
        result.extend(repo for repo in batch if repo['owner']['login'].lower() == OWNER.lower())
        if len(batch) < 100:
            break
        page += 1
    return result

def main():
    BASE.mkdir(parents=True, exist_ok=True)
    STATUS.mkdir(parents=True, exist_ok=True)
    repos = repositories()
    if not repos:
        raise RuntimeError('No owned repositories returned; refusing empty backup')
    errors = []
    for repo in repos:
        full = repo['full_name']
        dest = BASE / repo['owner']['login'] / (repo['name'] + '.git')
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f'Backing up {full}', flush=True)
        try:
            if dest.exists():
                if not (dest / 'HEAD').exists():
                    raise RuntimeError('Target exists but is not a bare repository')
                run('git', '-C', str(dest), 'remote', 'update', '--prune')
            else:
                with tempfile.TemporaryDirectory(dir=dest.parent, prefix='.clone-') as tmp:
                    candidate = pathlib.Path(tmp) / 'repo.git'
                    run('git', 'clone', '--mirror', repo['clone_url'], str(candidate))
                    candidate.rename(dest)
            run('git', '-C', str(dest), 'lfs', 'fetch', '--all')
            run('git', '-C', str(dest), 'fsck', '--full', '--no-reflogs')
        except Exception as exc:
            print(f'ERROR {full}: {exc}', file=sys.stderr, flush=True)
            errors.append(full)
    summary = {'timestamp': datetime.now(timezone.utc).isoformat(),
               'owner': OWNER, 'discovered': len(repos), 'failures': errors,
               'repositories': [r['full_name'] for r in repos]}
    (STATUS / 'last-run.json').write_text(json.dumps(summary, indent=2) + '\n')
    if errors:
        raise RuntimeError(f'{len(errors)} repositories failed: {errors}')
    print(f'Successfully synchronized {len(repos)} repositories', flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FATAL: {exc}', file=sys.stderr)
        sys.exit(1)
