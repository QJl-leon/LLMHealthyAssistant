from pathlib import Path
from dotenv import dotenv_values
from minio import Minio

config = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
client = Minio(config["MINIO_ENDPOINT"], access_key=config["MINIO_ACCESS_KEY"],
               secret_key=config["MINIO_SECRET_KEY"], secure=False)
bucket = config.get("MINIO_BUCKET", "lha-uploads")
if not client.bucket_exists(bucket):
    client.make_bucket(bucket)
print("MinIO bucket ready:", bucket)
