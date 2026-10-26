"""Ensure the dedicated call-recording bucket exists and is private."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.infra.storage import _call_storage_client, CALL_RECORDING_BUCKET


def check(apply=False):
    storage = _call_storage_client().storage
    buckets = storage.list_buckets()
    bucket = next((item for item in buckets if
                   (item.get("id") if isinstance(item, dict) else getattr(item, "id", None)) == CALL_RECORDING_BUCKET), None)
    if bucket is None:
        if not apply:
            print("Call-recordings bucket is missing")
            return 1
        storage.create_bucket(CALL_RECORDING_BUCKET, options={"public": False})
    else:
        public = bucket.get("public") if isinstance(bucket, dict) else getattr(bucket, "public", None)
        if public is not False:
            if not apply:
                print("Call-recordings bucket must be private")
                return 1
            storage.update_bucket(CALL_RECORDING_BUCKET, options={"public": False})
    print("Call-recordings bucket is private")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raise SystemExit(check(args.apply))
