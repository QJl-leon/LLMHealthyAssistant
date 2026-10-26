"""Inventory legacy uploads and optionally import explicitly reviewed ownership.

Task references are clues, not proof: the old API allowed unverified image keys.
Inventory never assigns ownership. Import defaults to validation-only.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import UUID

from dotenv import dotenv_values
import psycopg
from PIL import Image

PROJECT = Path(__file__).resolve().parents[2]
KEY = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(jpg|png|gif|webp)')


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def image_metadata(directory, key):
    if not KEY.fullmatch(key):
        raise ValueError('Invalid image key')
    root = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fd = os.open(key, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 10 * 1024 * 1024:
                raise ValueError('Invalid image file')
            with Image.open(stream) as image:
                expected = {'jpg': 'JPEG', 'png': 'PNG', 'gif': 'GIF', 'webp': 'WEBP'}[key.rsplit('.', 1)[-1]]
                if image.format != expected or image.width * image.height > 40_000_000:
                    raise ValueError('Image metadata mismatch')
                image.verify()
            return {'size_bytes': info.st_size, 'mime': Image.MIME[expected]}
    finally:
        os.close(root)


def inventory(conn, directory):
    refs = {}
    rows = conn.execute('SELECT id::text, tenant_id::text, user_id::text, image_keys FROM tasks').fetchall()
    for task, tenant, user, keys in rows:
        for key in keys if isinstance(keys, list) else []:
            if isinstance(key, str):
                refs.setdefault(key, []).append({'task_id': task, 'tenant_id': tenant, 'user_id': user})
    tracked = set()
    if conn.execute("SELECT to_regclass('uploaded_files')").fetchone()[0]:
        tracked = {row[0] for row in conn.execute('SELECT image_key FROM uploaded_files')}
    files = []
    for path in sorted(directory.iterdir()):
        item = {'image_key': path.name, 'tracked': path.name in tracked,
                'task_reference_clues': refs.get(path.name, [])}
        try:
            item.update(image_metadata(directory, path.name))
            item['status'] = 'recorded' if item['tracked'] else 'requires_manual_review'
        except (OSError, ValueError, Image.DecompressionBombError):
            item['status'] = 'invalid_or_unreadable'
        files.append(item)
    return {'notice': 'Task references are not ownership proof. No ownership was assigned.',
            'files': files, 'referenced_but_missing': sorted(set(refs) - {p.name for p in directory.iterdir()})}


def import_reviewed(conn, directory, manifest, apply=False):
    entries = manifest.get('assignments')
    if not isinstance(entries, list):
        raise ValueError('Expected assignments array')
    seen = set()
    for item in entries:
        key = item['image_key']
        tenant, user = str(UUID(item['tenant_id'])), str(UUID(item['user_id']))
        if key in seen or item.get('reviewed') is not True or not str(item.get('evidence', '')).strip():
            raise ValueError('Each unique assignment requires reviewed=true and evidence')
        seen.add(key)
        meta = image_metadata(directory, key)
        if not conn.execute('SELECT 1 FROM users WHERE id=%s AND tenant_id=%s', (user, tenant)).fetchone():
            raise ValueError('User and tenant do not match')
        existing = conn.execute('SELECT tenant_id::text,user_id::text FROM uploaded_files WHERE image_key=%s', (key,)).fetchone()
        if existing and existing != (tenant, user):
            raise ValueError('Existing ownership must not be reassigned')
        if apply:
            # Plain insert fails on a concurrent conflicting claim. Never reassign.
            if not existing:
                conn.execute('INSERT INTO uploaded_files(image_key,tenant_id,user_id,mime,size_bytes) VALUES(%s,%s,%s,%s,%s)',
                             (key, tenant, user, meta['mime'], meta['size_bytes']))
    return len(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=PROJECT / 'go-backend/data/uploads')
    sub = parser.add_subparsers(dest='action', required=True)
    scan = sub.add_parser('inventory')
    scan.add_argument('--out', type=Path, required=True)
    load = sub.add_parser('import-reviewed')
    load.add_argument('--manifest', type=Path, required=True)
    load.add_argument('--apply', action='store_true', help='Write reviewed assignments; otherwise only validate')
    args = parser.parse_args()
    config = dotenv_values(PROJECT / '.env')
    with psycopg.connect(config['DATABASE_URL']) as conn:
        if args.action == 'inventory':
            conn.execute('SET TRANSACTION READ ONLY')
            report = inventory(conn, args.directory)
            write_private(args.out, report)
            print(f'Inventory: {len(report["files"])} files. No ownership changed.')
        else:
            count = import_reviewed(conn, args.directory, json.loads(args.manifest.read_text()), args.apply)
            print(f'{"Imported" if args.apply else "Validated only"}: {count} reviewed assignments.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Database exceptions can contain connection information. Do not echo it.
        print(f'Ownership operation failed ({type(exc).__name__}); no transaction committed.', file=sys.stderr)
        sys.exit(1)
