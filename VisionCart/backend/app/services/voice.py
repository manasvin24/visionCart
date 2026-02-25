"""
VisionCart – Voice-to-Text Service (Whisper Integration)

Handles real-time audio transcription for Customer-to-Shopper voice communication.
Supports both OpenAI Whisper API (cloud) and local whisper model (edge).
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from typing import Optional

import numpy as np

from app.config import get_settings

logger = logging.getLogger("visioncart.voice")
settings = get_settings()


class WhisperTranscriber:
    """
    Real-time voice transcription using OpenAI Whisper.

    Modes:
      1. API mode: Sends audio to OpenAI Whisper API (lower latency, requires key)
      2. Local mode: Runs whisper model on-device (higher latency, no key needed)

    Audio format: PCM float32, 16kHz mono
    """

    def __init__(self, mode: str = "api"):
        self.mode = mode
        self._model = None
        self._api_key = settings.WHISPER_API_KEY

        if not self._api_key and mode == "api":
            logger.warning("No WHISPER_API_KEY set, falling back to local mode")
            self.mode = "local"

    async def transcribe(
        self,
        audio_b64: str,
        sample_rate: int = 16000,
        language: str = "en",
    ) -> Optional[dict]:
        """
        Transcribe an audio chunk.

        Args:
            audio_b64: Base64-encoded PCM audio data
            sample_rate: Audio sample rate (default 16kHz)
            language: Language hint for transcription

        Returns:
            Dict with 'text', 'confidence', 'language', 'duration_ms' keys
            or None if transcription failed.
        """
        start = time.perf_counter()

        try:
            audio_bytes = base64.b64decode(audio_b64)
            audio_array = np.frombuffer(audio_bytes, dtype=np.float32)

            if len(audio_array) < sample_rate * 0.1:  # < 100ms
                return None  # Too short

            if self.mode == "api":
                result = await self._transcribe_api(audio_array, sample_rate, language)
            else:
                result = await self._transcribe_local(audio_array, sample_rate, language)

            if result:
                result["duration_ms"] = round(
                    (time.perf_counter() - start) * 1000, 1
                )

            return result

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None

    async def _transcribe_api(
        self,
        audio: np.ndarray,
        sample_rate: int,
        language: str,
    ) -> Optional[dict]:
        """Transcribe using OpenAI Whisper API."""
        import httpx

        # Convert to WAV format for API
        wav_buffer = self._to_wav(audio, sample_rate)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": ("audio.wav", wav_buffer, "audio/wav")},
                data={
                    "model": "whisper-1",
                    "language": language,
                    "response_format": "verbose_json",
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                logger.error(f"Whisper API error: {response.status_code}")
                return None

            data = response.json()
            return {
                "text": data.get("text", "").strip(),
                "confidence": self._estimate_confidence(data),
                "language": data.get("language", language),
            }

    async def _transcribe_local(
        self,
        audio: np.ndarray,
        sample_rate: int,
        language: str,
    ) -> Optional[dict]:
        """Transcribe using local Whisper model."""
        if self._model is None:
            try:
                import whisper
                self._model = whisper.load_model(settings.WHISPER_MODEL)
                logger.info(f"Local Whisper model loaded: {settings.WHISPER_MODEL}")
            except ImportError:
                logger.error("openai-whisper not installed for local mode")
                return None

        # Run in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._model.transcribe(
                audio,
                language=language,
                fp16=False,
            ),
        )

        if not result or not result.get("text"):
            return None

        return {
            "text": result["text"].strip(),
            "confidence": self._avg_segment_confidence(result),
            "language": result.get("language", language),
        }

    @staticmethod
    def _to_wav(audio: np.ndarray, sample_rate: int) -> io.BytesIO:
        """Convert float32 numpy array to WAV byte buffer."""
        import struct

        buffer = io.BytesIO()
        # Convert to 16-bit PCM
        pcm = (audio * 32767).astype(np.int16)
        data = pcm.tobytes()

        # WAV header
        buffer.write(b"RIFF")
        buffer.write(struct.pack("<I", 36 + len(data)))
        buffer.write(b"WAVE")
        buffer.write(b"fmt ")
        buffer.write(struct.pack("<I", 16))      # chunk size
        buffer.write(struct.pack("<H", 1))        # PCM format
        buffer.write(struct.pack("<H", 1))        # mono
        buffer.write(struct.pack("<I", sample_rate))
        buffer.write(struct.pack("<I", sample_rate * 2))
        buffer.write(struct.pack("<H", 2))        # block align
        buffer.write(struct.pack("<H", 16))       # bits per sample
        buffer.write(b"data")
        buffer.write(struct.pack("<I", len(data)))
        buffer.write(data)

        buffer.seek(0)
        return buffer

    @staticmethod
    def _estimate_confidence(api_response: dict) -> float:
        """Estimate confidence from API verbose JSON response."""
        segments = api_response.get("segments", [])
        if not segments:
            return 0.5
        avg_prob = sum(
            s.get("avg_logprob", -1.0) for s in segments
        ) / len(segments)
        # Map log probability to [0, 1] confidence
        return max(0.0, min(1.0, 1.0 + avg_prob))

    @staticmethod
    def _avg_segment_confidence(result: dict) -> float:
        """Average confidence across segments for local model."""
        segments = result.get("segments", [])
        if not segments:
            return 0.5
        avg_prob = sum(
            s.get("avg_logprob", -1.0) for s in segments
        ) / len(segments)
        return max(0.0, min(1.0, 1.0 + avg_prob))
