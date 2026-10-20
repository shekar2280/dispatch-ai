import os
import httpx
from typing import Dict, Any, Optional, Callable, Awaitable
from dotenv import load_dotenv

load_dotenv()


async def transcribe_audio_bytes(
    audio_bytes: bytes, content_type: str = "audio/mp3"
) -> Dict[str, Any]:
    """
    Speech-to-Text (STT) Engine with Deepgram Nova-2 medical keyword boosting.
    Provides sub-200ms audio transcription.
    """
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if api_key:
        try:
            med_keywords = "&".join(
                [
                    "keywords=rash:2",
                    "keywords=rashes:2",
                    "keywords=cardiology:2",
                    "keywords=dermatology:2",
                    "keywords=neurology:2",
                    "keywords=orthopedic:2",
                    "keywords=pediatric:2",
                    "keywords=general checkup:2",
                    "keywords=fever:2",
                    "keywords=headache:2",
                    "keywords=consultation:2",
                ]
            )
            url = f"https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true&{med_keywords}"
            headers = {
                "Authorization": f"Token {api_key}",
                "Content-Type": content_type,
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, headers=headers, content=audio_bytes)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", {})
                    channels = results.get("channels", [])
                    transcript = ""
                    confidence = 0.0
                    if channels:
                        alternatives = channels[0].get("alternatives", [])
                        if alternatives:
                            transcript = alternatives[0].get("transcript", "")
                            confidence = alternatives[0].get("confidence", 0.0)
                    if transcript.strip():
                        return {
                            "transcript": transcript,
                            "confidence": confidence,
                            "raw_response": data,
                        }
        except Exception:
            pass

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {groq_key.strip()}"}
            files = {"file": ("audio.mp3", audio_bytes, content_type)}
            data = {"model": "whisper-large-v3-turbo", "response_format": "json"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, headers=headers, files=files, data=data)
                if res.status_code == 200:
                    out = res.json()
                    text = out.get("text", "").strip()
                    if text:
                        return {
                            "transcript": text,
                            "confidence": 0.95,
                            "raw_response": out,
                        }
        except Exception:
            pass

    return {
        "transcript": "",
        "confidence": 0.0,
        "raw_response": {"fallback": True},
    }


class DeepgramLiveStream:
    """
    [DEPRECATED / HISTORICAL]: Custom raw WebSocket client for Deepgram STT.
    NOTE: Active voice calls use LiveKit native STT orchestration via `livekit.plugins.deepgram.STT`
    inside `app.agent.agent_worker.AgentSession`, eliminating custom raw WebSocket audio piping.
    """

    def __init__(
        self,
        on_transcript_callback: Optional[Callable[[str, bool], Awaitable[None]]] = None,
    ):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        self.on_transcript_callback = on_transcript_callback
        self.ws = None
        self.is_connected = False
        self.listen_task = None
        self.keep_alive_task = None

    async def connect(self):
        if not self.api_key:
            print("[DEEPGRAM STREAM WARNING] No DEEPGRAM_API_KEY found in .env.")
            return

        med_keywords = "&".join(
            [
                "keywords=rash:2",
                "keywords=cardiology:2",
                "keywords=dermatology:2",
                "keywords=neurology:2",
                "keywords=general checkup:2",
                "keywords=fever:2",
            ]
        )
        url = (
            "wss://api.deepgram.com/v1/listen?"
            "model=nova-2&encoding=linear16&sample_rate=16000&channels=1&"
            f"smart_format=true&punctuate=true&{med_keywords}"
        )
        headers = {"Authorization": f"Token {self.api_key}"}

        try:
            import websockets

            self.ws = await websockets.connect(url, extra_headers=headers)
            self.is_connected = True
            self.listen_task = asyncio.create_task(self._listen_loop())
            self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())
            print("[DEEPGRAM STREAM] Connected to Deepgram Live Streaming STT with KeepAlive active.")
        except Exception as e:
            print(f"[DEEPGRAM STREAM ERROR] Connection failed: {type(e).__name__}")
            self.is_connected = False

    async def send_audio_chunk(self, chunk_bytes: bytes):
        if self.is_connected and self.ws:
            try:
                await self.ws.send(chunk_bytes)
            except Exception as e:
                print(f"[DEEPGRAM STREAM ERROR] Failed sending audio chunk: {type(e).__name__}")

    async def _keep_alive_loop(self):
        """Send a keepalive every five seconds while the stream is connected."""
        import json

        while self.is_connected and self.ws:
            try:
                await asyncio.sleep(5.0)
                if self.is_connected and self.ws:
                    await self.ws.send(json.dumps({"type": "KeepAlive"}))
            except Exception:
                break

    async def _listen_loop(self):
        try:
            import json

            async for message in self.ws:
                data = json.loads(message)
                channel = data.get("channel", {})
                alternatives = channel.get("alternatives", [])
                if alternatives:
                    transcript = alternatives[0].get("transcript", "")
                    is_final = data.get("is_final", False)
                    if transcript.strip() and self.on_transcript_callback:
                        await self.on_transcript_callback(transcript, is_final)
        except Exception as e:
            print(f"[DEEPGRAM STREAM LISTEN ERROR] {type(e).__name__}")
        finally:
            self.is_connected = False

    async def close(self):
        self.is_connected = False
        if self.ws:
            try:
                import json

                await self.ws.send(json.dumps({"type": "CloseStream"}))
                await self.ws.close()
            except Exception:
                pass
        if self.listen_task:
            self.listen_task.cancel()
        if self.keep_alive_task:
            self.keep_alive_task.cancel()
