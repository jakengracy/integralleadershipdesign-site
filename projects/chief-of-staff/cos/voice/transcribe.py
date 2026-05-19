"""
cos/voice/transcribe.py — Local speech-to-text using faster-whisper.

faster-whisper is a CTranslate2-based reimplementation of OpenAI Whisper.
On M1 Ultra it runs on the Neural Engine/Metal — significantly faster than
the original Whisper. The model is loaded once at first call and cached in
module state; subsequent transcriptions do not re-load from disk.

Audio pipeline:
    1. record_audio()  — captures from default mic via sounddevice, returns WAV bytes
    2. transcribe()    — passes audio through faster-whisper, returns transcript string
    3. menu_bar.py     — calls both in sequence after PTT trigger

Whisper model sizes (accuracy vs. speed tradeoff on M1 Ultra):
    tiny   — fastest, lowest accuracy
    base   — good for short commands
    small  — solid middle ground
    medium — default: good accuracy, ~1–2s transcription time on M1 Ultra
    large-v3 — best accuracy, ~3–5s; upgrade here if medium misses words
"""

import io
import logging
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

from cos.config import WHISPER_LANGUAGE, WHISPER_MODEL_SIZE

logger = logging.getLogger(__name__)

# ── Model cache ────────────────────────────────────────────────────────────────
# Loaded on first transcribe() call. Loading takes ~5–10s; all subsequent
# calls are fast. Thread-safe for our single-voice-thread use case.
_model = None


def _get_model():
    """Load (or return cached) the faster-whisper model."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        logger.info(f"Loading Whisper model '{WHISPER_MODEL_SIZE}' — this may take a moment...")
        # device="auto" lets faster-whisper pick MPS (Apple Silicon) if available,
        # falling back to CPU. compute_type="int8" keeps memory usage reasonable.
        _model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device="auto",
            compute_type="int8",
        )
        logger.info(f"Whisper model '{WHISPER_MODEL_SIZE}' loaded successfully")
    return _model


# ── Recording ──────────────────────────────────────────────────────────────────

# Recording state for toggle mode (start/stop rather than hold/release)
_recording: bool        = False
_audio_buffer: list     = []
_sample_rate: int       = 16000  # Whisper was trained on 16kHz audio
_channels: int          = 1      # Mono — Whisper doesn't use stereo
_stream: Optional[object] = None


def start_recording() -> bool:
    """
    Start capturing audio from the default microphone.
    Uses toggle mode: call start_recording() to begin, stop_recording() to end.
    Returns True if recording started; False if already recording.
    """
    global _recording, _audio_buffer, _stream

    if _recording:
        logger.warning("start_recording() called while already recording — ignored")
        return False

    _audio_buffer = []
    _recording    = True

    def _callback(indata, frames, time_info, status):
        if status:
            logger.warning(f"sounddevice status: {status}")
        # Accumulate audio chunks into the buffer
        _audio_buffer.append(indata.copy())

    try:
        _stream = sd.InputStream(
            samplerate=_sample_rate,
            channels=_channels,
            dtype="float32",
            callback=_callback,
        )
        _stream.start()
        logger.info("Recording started")
        return True
    except Exception as e:
        _recording = False
        logger.error(f"Failed to open audio stream: {e}")
        return False


def stop_recording() -> Optional[bytes]:
    """
    Stop recording and return the captured audio as WAV bytes.
    Returns None if not recording or if the capture was too short to be useful.
    """
    global _recording, _stream

    if not _recording:
        logger.warning("stop_recording() called while not recording — ignored")
        return None

    _recording = False

    if _stream is not None:
        _stream.stop()
        _stream.close()
        _stream = None

    if not _audio_buffer:
        logger.warning("No audio captured")
        return None

    # Concatenate all captured chunks into a single array
    audio_array = np.concatenate(_audio_buffer, axis=0)

    # Reject very short clips (< 0.5s) — likely accidental triggers
    duration_secs = len(audio_array) / _sample_rate
    if duration_secs < 0.5:
        logger.warning(f"Audio too short ({duration_secs:.2f}s) — ignoring")
        return None

    logger.info(f"Recording stopped — captured {duration_secs:.2f}s of audio")
    return _audio_to_wav_bytes(audio_array, _sample_rate)


def record_audio(duration_seconds: float = 5.0) -> Optional[bytes]:
    """
    Convenience function for fixed-duration recording (used in tests/debug).
    Blocks for duration_seconds, then returns WAV bytes.
    For normal push-to-talk use, call start_recording() / stop_recording() instead.
    """
    logger.info(f"Recording for {duration_seconds}s...")
    audio_array = sd.rec(
        int(duration_seconds * _sample_rate),
        samplerate=_sample_rate,
        channels=_channels,
        dtype="float32",
    )
    sd.wait()
    return _audio_to_wav_bytes(audio_array, _sample_rate)


def _audio_to_wav_bytes(audio_array: np.ndarray, sample_rate: int) -> bytes:
    """Convert a numpy float32 audio array to WAV bytes using soundfile."""
    buf = io.BytesIO()
    sf.write(buf, audio_array, sample_rate, format="WAV", subtype="FLOAT")
    buf.seek(0)
    return buf.read()


# ── Transcription ──────────────────────────────────────────────────────────────

def transcribe(audio_bytes: bytes) -> str:
    """
    Run faster-whisper on audio_bytes and return the transcript string.

    Writes audio to a temp file because faster-whisper's transcribe() accepts
    a file path rather than in-memory bytes. The temp file is deleted after use.

    Logs a warning if the average segment confidence is below 0.7 — this usually
    means background noise or unclear speech; the transcript is still returned.
    """
    model = _get_model()

    # Write to a named temp file (faster-whisper needs a path, not a BytesIO)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, info = model.transcribe(
            tmp_path,
            language=WHISPER_LANGUAGE,
            beam_size=5,
            # vad_filter removes non-speech segments — reduces hallucination on silence
            vad_filter=True,
        )

        logger.debug(
            f"Detected language: {info.language} "
            f"(probability {info.language_probability:.2f})"
        )

        # Collect all segment texts and check confidence
        texts       = []
        confidences = []
        for seg in segments:
            texts.append(seg.text.strip())
            # avg_logprob is in log-space; convert to approximate probability
            confidence = float(np.exp(seg.avg_logprob)) if seg.avg_logprob else 0.0
            confidences.append(confidence)

        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            if avg_confidence < 0.7:
                logger.warning(
                    f"Low transcription confidence ({avg_confidence:.2f}) — "
                    f"consider upgrading to a larger Whisper model"
                )

        transcript = " ".join(texts).strip()
        logger.info(f"Transcript: {transcript!r}")
        return transcript

    except Exception as e:
        logger.exception(f"Transcription failed: {e}")
        return ""
    finally:
        Path(tmp_path).unlink(missing_ok=True)
