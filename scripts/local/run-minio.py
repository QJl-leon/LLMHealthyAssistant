"""Run MinIO with credentials from the project's .env."""
import os
from pathlib import Path
from dotenv import dotenv_values
root = Path(__file__).resolve().parents[2]
config = dotenv_values(root / ".env")
env = os.environ.copy()
env["MINIO_ROOT_USER"] = config["MINIO_ACCESS_KEY"]
env["MINIO_ROOT_PASSWORD"] = config["MINIO_SECRET_KEY"]
binary = str(root.parent / ".tools/bin/minio")
os.execve(binary, [binary, "server", str(root / "data/minio"),
                  "--address", "127.0.0.1:9000", "--console-address", "127.0.0.1:9001"], env)
