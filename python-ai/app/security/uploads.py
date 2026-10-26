"""Resolve Go-authorized upload references inside the shared upload directory.

This helper is for trusted internal processing, not an HTTP authorization endpoint.
Go checks file ownership before submitting image keys to the Python service.
"""
import os
from pathlib import Path
import re

_KEY = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(?:jpg|png|gif|webp)")


def read_upload(reference: str) -> bytes | None:
    if not reference.startswith('/uploads/'):
        return None
    key = reference[len('/uploads/'):]
    if not _KEY.fullmatch(key):
        return None
    project = Path(os.getenv('PROJECT_ROOT', str(Path(__file__).resolve().parents[3])))
    root = Path(os.getenv('LHA_UPLOAD_DIR', str(project / 'go-backend' / 'data' / 'uploads')))
    # Open relative to a directory descriptor. O_NOFOLLOW rejects symlinks even
    # if an attacker swaps the file between a path check and the actual open.
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fd = os.open(key, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, 'rb') as stream:
                import stat
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 10 * 1024 * 1024:
                    return None
                data = stream.read(10 * 1024 * 1024 + 1)
                return data if len(data) <= 10 * 1024 * 1024 else None
        finally:
            os.close(directory)
    except OSError:
        return None


def upload_data_url(reference: str) -> str:
    import base64
    data = read_upload(reference)
    if data is None:
        raise ValueError('Upload image unavailable')
    ext = reference.rsplit('.', 1)[-1]
    mime = 'image/jpeg' if ext == 'jpg' else f'image/{ext}'
    return f'data:{mime};base64,{base64.b64encode(data).decode("ascii")}'
