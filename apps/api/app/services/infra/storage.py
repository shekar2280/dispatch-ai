import asyncio
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

BUCKET_NAME = "emergency-audio"
CALL_RECORDING_BUCKET = "call-recordings"


def _call_storage_client():
    from supabase import create_client
    url = settings.SUPABASE_URL or settings.NEXT_PUBLIC_SUPABASE_URL
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    if not url or not key:
        raise RuntimeError("Call recording requires Supabase URL and service role credentials")
    return create_client(url, key)


async def upload_call_recording(org_id, call_id, wav_bytes: bytes, *, checkpoint=False) -> str:
    from uuid import UUID
    import io
    import wave
    org = UUID(str(org_id))
    call = UUID(str(call_id))
    with wave.open(io.BytesIO(wav_bytes), "rb") as audio:
        if audio.getnframes() == 0:
            raise ValueError("Cannot upload empty call recording")
    path = f"{org}/{call}{'.partial' if checkpoint else ''}.wav"

    def upload():
        client = _call_storage_client()
        bucket = client.storage.get_bucket(CALL_RECORDING_BUCKET)
        is_public = bucket.get("public") if isinstance(bucket, dict) else getattr(bucket, "public", None)
        if is_public is not False:
            raise RuntimeError("Call recordings bucket must be private")
        client.storage.from_(CALL_RECORDING_BUCKET).upload(
            path, wav_bytes, file_options={"content-type": "audio/wav", "upsert": "true"}
        )
        return f"{CALL_RECORDING_BUCKET}/{path}"

    return await asyncio.to_thread(upload)


async def sign_call_recording(storage_path: str, org_id, call_id, expires_in_seconds: int = 300) -> str:
    from uuid import UUID
    expected = f"{CALL_RECORDING_BUCKET}/{UUID(str(org_id))}/{UUID(str(call_id))}.wav"
    partial = expected.removesuffix('.wav') + '.partial.wav'
    if storage_path not in {expected, partial}:
        raise ValueError("Recording storage path does not match call tenant")
    if not 1 <= expires_in_seconds <= 3600:
        raise ValueError("Recording URL lifetime must be between 1 and 3600 seconds")

    def sign():
        client = _call_storage_client()
        result = client.storage.from_(CALL_RECORDING_BUCKET).create_signed_url(
            storage_path.removeprefix(f"{CALL_RECORDING_BUCKET}/"), expires_in_seconds
        )
        url = result.get("signedURL") or result.get("signedUrl") if isinstance(result, dict) else getattr(result, "signed_url", None)
        if not url:
            raise RuntimeError("Storage did not return a signed recording URL")
        return url

    return await asyncio.to_thread(sign)

async def upload_greeting_bytes_to_supabase(
    org_id: str,
    audio_bytes: bytes,
    content_type: str = "audio/mpeg"
) -> Optional[str]:
    storage_path = f"greetings/{org_id}/greeting.mp3"
    supabase_url = settings.SUPABASE_URL or settings.NEXT_PUBLIC_SUPABASE_URL
    supabase_key = settings.SUPABASE_SERVICE_ROLE_KEY

    if not supabase_url or not supabase_key:
        return None

    def _sync_upload() -> Optional[str]:
        try:
            from supabase import create_client
            supabase = create_client(supabase_url, supabase_key)
            try:
                supabase.storage.create_bucket(BUCKET_NAME, options={"public": False})
            except Exception:
                pass

            supabase.storage.from_(BUCKET_NAME).upload(
                path=storage_path,
                file=audio_bytes,
                file_options={"content-type": content_type, "x-upsert": "true"}
            )
            return f"{BUCKET_NAME}/{storage_path}"
        except Exception as e:
            logger.error(f"Supabase greeting upload error: {e}")
            return None

    try:
        return await asyncio.to_thread(_sync_upload)
    except Exception:
        return _sync_upload()

async def download_audio_bytes_from_supabase(storage_path: str) -> Optional[bytes]:
    clean_path = storage_path.replace(f"{BUCKET_NAME}/", "").lstrip("/")
    supabase_url = settings.SUPABASE_URL or settings.NEXT_PUBLIC_SUPABASE_URL
    supabase_key = settings.SUPABASE_SERVICE_ROLE_KEY

    if not supabase_url or not supabase_key:
        return None

    def _sync_download() -> Optional[bytes]:
        try:
            from supabase import create_client
            supabase = create_client(supabase_url, supabase_key)
            return supabase.storage.from_(BUCKET_NAME).download(clean_path)
        except Exception as e:
            logger.error(f"Supabase download error: {e}")
            return None

    try:
        return await asyncio.to_thread(_sync_download)
    except Exception:
        return _sync_download()
