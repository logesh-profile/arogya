"""
Arogya Real-Time Voice Streaming Gateway
Full-Duplex WebSocket Engine with Silero VAD (ONNX on CPU),
Streaming Groq LLM, and Sentence-Level Progressive Audio Pipelining.
"""

import os
import sys
import time
import io
import wave
import json
import base64
import asyncio
import numpy as np
from typing import Optional, Dict, Any, List
from fastapi import WebSocket, WebSocketDisconnect

import onnxruntime as ort
from voice_engine import (
    transcribe_with_groq_whisper,
    synthesize_fast_speech,
    stream_edge_tts_chunks,
    DEFAULT_VOICE,
    VALID_VOICE_IDS
)
from services.llm_router import get_groq_client
from prompts.companion_persona import REALTIME_VOICE_STREAM_INSTRUCTION
from database import (
    save_message,
    save_mental_health_record,
    get_session_messages,
    get_historical_context,
    get_user_baseline_stats,
    get_latest_mental_health_record
)
from mental_health_engine import (
    extract_acoustic_features,
    classify_user_emotion_from_voice_tone
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SILERO_MODEL_PATH = os.path.join(BASE_DIR, "models", "silero_vad.onnx")

class SileroVADDetector:
    """
    Ultra-lightweight Voice Activity Detector using Silero VAD (ONNX on CPU).
    Operates on 16kHz Mono 16-bit PCM chunks in 576-sample windows (~36ms).
    Uses < 1% CPU and 0 MB GPU.
    """
    def __init__(self, model_path: str = SILERO_MODEL_PATH):
        if not os.path.exists(model_path):
            alt_paths = [
                os.path.join(os.path.dirname(BASE_DIR), "mental_health_voice_ai", "models", "silero_vad.onnx"),
                r"C:\chatbot\venv\Lib\site-packages\faster_whisper\assets\silero_vad_v6.onnx",
                os.path.join(os.path.expanduser("~"), ".cache", "silero_vad.onnx")
            ]
            for ap in alt_paths:
                if os.path.exists(ap):
                    model_path = ap
                    break
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self):
        self.h = np.zeros((1, 1, 128), dtype=np.float32)
        self.c = np.zeros((1, 1, 128), dtype=np.float32)
        self.pcm_buffer = bytearray()
        self.is_speech_active = False
        self.has_spoken = False
        self.consecutive_speech_frames = 0
        self.consecutive_silence_frames = 0
        self.audio_time = 0.0
        self.last_speech_time = 0.0
        self.speech_start_time = 0.0

    def feed_pcm(self, pcm_data: bytes) -> Dict[str, Any]:
        """
        Feed raw 16kHz 16-bit mono PCM bytes.
        Returns state dict: {'speech_prob': float, 'is_speech': bool, 'has_spoken': bool, 'speech_ended': bool}
        """
        self.pcm_buffer.extend(pcm_data)
        window_bytes = 576 * 2  # 576 samples of 16-bit (2 bytes) = 1152 bytes
        frame_duration = 576.0 / 16000.0  # 0.036s (~36ms)
        last_prob = 0.0
        speech_ended = False

        while len(self.pcm_buffer) >= window_bytes:
            chunk_bytes = bytes(self.pcm_buffer[:window_bytes])
            del self.pcm_buffer[:window_bytes]

            self.audio_time += frame_duration

            audio_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
            audio_float32 = (audio_int16.astype(np.float32) / 32768.0).reshape(1, 576)

            prob_out, self.h, self.c = self.session.run(
                None,
                {"input": audio_float32, "h": self.h, "c": self.c}
            )
            last_prob = float(prob_out[0])

            # Speech threshold: > 0.35 probability flags vocal presence
            if last_prob >= 0.35:
                self.consecutive_speech_frames += 1
                self.consecutive_silence_frames = 0
                if self.consecutive_speech_frames >= 2:
                    if not self.is_speech_active:
                        self.is_speech_active = True
                        self.speech_start_time = self.audio_time
                    self.has_spoken = True
                    self.last_speech_time = self.audio_time
            else:
                self.consecutive_speech_frames = max(0, self.consecutive_speech_frames - 1)
                if self.is_speech_active:
                    self.consecutive_silence_frames += 1
                    # Conversational pause threshold: 0.95s of silence after speaking
                    silence_duration = self.audio_time - self.last_speech_time
                    if silence_duration >= 0.95 and self.consecutive_silence_frames >= 5:
                        speech_ended = True
                        self.is_speech_active = False

        return {
            "speech_prob": last_prob,
            "is_speech": self.is_speech_active,
            "has_spoken": self.has_spoken,
            "speech_ended": speech_ended
        }


def pcm_to_wav_bytes(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    """Pack raw 16-bit mono PCM into standard in-memory WAV bytes for Groq Whisper."""
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    bio.seek(0)
    return bio.getvalue()


class StreamingVoiceSession:
    """
    Manages a live WebSocket voice session for a single user.
    Coordinates VAD, Groq Whisper STT, Groq Streaming LLM, and Edge-TTS chunking.
    """
    def __init__(self, websocket: WebSocket):
        self.ws = websocket
        self.vad = SileroVADDetector()
        self.session_id: str = "sess_guest"
        self.user_id: str = "guest_user"
        self.voice_id: str = DEFAULT_VOICE
        self.turn_id: int = 0
        self.is_interrupted: bool = False
        self.active_generator_task: Optional[asyncio.Task] = None
        self.accumulated_turn_pcm = bytearray()
        self.pre_speech_ring_buffer = bytearray()

    async def handle_connect(self):
        await self.ws.accept()
        print(f"[*] Voice WebSocket connected for session: {self.session_id}")
        await self.send_json({
            "type": "ready",
            "message": "Connected to Arogya Real-Time Voice Gateway"
        })

    async def send_json(self, data: Dict[str, Any]):
        try:
            await self.ws.send_text(json.dumps(data))
        except Exception:
            pass

    async def send_audio_chunk(self, turn_id: int, chunk_index: int, text_chunk: str, audio_bytes: bytes):
        """Send a synthesized audio chunk to the client for immediate playback."""
        if self.is_interrupted or turn_id != self.turn_id:
            return
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        await self.send_json({
            "type": "audio_chunk",
            "turn_id": turn_id,
            "chunk_index": chunk_index,
            "text": text_chunk,
            "audio_b64": audio_b64
        })

    def interrupt(self, turn_id: Optional[int] = None):
        """Instant Barge-In: Abort ongoing turn synthesis immediately."""
        self.is_interrupted = True
        if self.active_generator_task and not self.active_generator_task.done():
            self.active_generator_task.cancel()
        print(f"[*] Turn {self.turn_id} interrupted by user speech barge-in.")

    async def process_utterance(self, turn_pcm: bytes, turn_id: int):
        """
        Processes a single conversational turn:
        1. Groq Whisper STT (~200ms)
        2. Acoustic telemetry & Emotion Tone Classification
        3. Groq LLM Streaming Tokens (~250ms)
        4. Slices sentences and streams audio chunks down the WebSocket
        """
        loop = asyncio.get_event_loop()
        try:
            # 1. Convert to WAV and transcribe via Groq Whisper LPU
            wav_bytes = pcm_to_wav_bytes(turn_pcm)
            bio = io.BytesIO(wav_bytes)
            bio.name = "audio.wav"

            transcript = await loop.run_in_executor(None, transcribe_with_groq_whisper, bio)
            if not transcript or not transcript.strip():
                print("[*] Whisper returned empty transcription, resuming listening.")
                await self.send_json({"type": "status", "state": "listening"})
                return

            transcript = transcript.strip()
            print(f"[+] User [{turn_id}]: {transcript}")

            # Notify UI immediately with user's words
            await self.send_json({
                "type": "transcript",
                "role": "user",
                "turn_id": turn_id,
                "text": transcript
            })

            # 2. Extract Acoustic Biomarkers & Detect User's Emotional Tone Concurrently
            acoustic_features = {}
            tone_emotion = {"emotion": "calm", "tone_label": "Calm & Steady", "listening_face": "caring", "speaking_face": "happy"}
            try:
                acoustic_features = await loop.run_in_executor(None, extract_acoustic_features, wav_bytes)
                tone_emotion = classify_user_emotion_from_voice_tone(acoustic_features, transcript)
                await self.send_json({
                    "type": "telemetry",
                    "turn_id": turn_id,
                    "emotion": tone_emotion.get("emotion", "calm"),
                    "tone_label": tone_emotion.get("tone_label", "Calm & Steady"),
                    "listening_face": tone_emotion.get("listening_face", "caring"),
                    "speaking_face": tone_emotion.get("speaking_face", "happy"),
                    "bpm": acoustic_features.get("bpm", 64)
                })
            except Exception as dsp_err:
                print(f"[!] DSP extraction notice: {dsp_err}")

            # Check for crisis triggers
            t_lower = transcript.lower()
            if any(w in t_lower for w in ["kill myself", "end my life", "suicide", "want to die"]):
                crisis_msg = (
                    "I want you to know that you are not alone, and your life has deep value. "
                    "Please stay with me right now. You can call 988 or 9152987821 for immediate free confidential support."
                )
                audio = await synthesize_fast_speech(crisis_msg, voice=self.voice_id)
                if audio and audio.startswith("data:audio"):
                    b64_part = audio.split(",", 1)[1]
                    raw_audio = base64.b64decode(b64_part)
                    await self.send_audio_chunk(turn_id, 0, crisis_msg, raw_audio)
                await self.send_json({"type": "turn_complete", "turn_id": turn_id})
                return

            # 3. Retrieve conversation context from DB
            session_messages = get_session_messages(self.session_id)
            historical_context = get_historical_context(self.session_id, user_id=self.user_id)

            history_lines = []
            for m in (session_messages or [])[-6:]:
                role_label = "User" if m.get("role") == "user" else "Arogya"
                history_lines.append(f"{role_label}: {m.get('text', '')}")
            history_str = "\n".join(history_lines)

            full_prompt = (
                f"Context from past reflections:\n{historical_context}\n\n"
                f"Recent conversation:\n{history_str}\n\n"
                f"User: {transcript}\n"
                f"Arogya (speak directly in 1-2 warm, natural spoken sentences):"
            )

            # 4. Stream LLM tokens from Groq LPU
            client = get_groq_client()
            if not client:
                fallback = "I'm right here with you, tell me more."
                await self.send_json({"type": "transcript", "role": "assistant", "turn_id": turn_id, "text": fallback})
                return

            stream = client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[
                    {"role": "system", "content": REALTIME_VOICE_STREAM_INSTRUCTION},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.25,
                max_tokens=90,
                stream=True
            )

            sentence_buffer = ""
            full_reply_text = ""
            chunk_idx = 0
            dominant_user_state = tone_emotion.get("emotion", "Calm")

            # Sentence boundary delimiters
            sentence_splitters = {".", "?", "!", "\n"}

            for chunk in stream:
                if self.is_interrupted or turn_id != self.turn_id:
                    print(f"[*] LLM stream cancelled for turn {turn_id} due to barge-in.")
                    break

                token = chunk.choices[0].delta.content or ""
                if not token:
                    continue

                sentence_buffer += token
                full_reply_text += token

                # Check if buffer has reached a natural sentence boundary
                has_terminal_punct = any(p in sentence_buffer for p in sentence_splitters)
                word_count = len(sentence_buffer.strip().split())

                if (has_terminal_punct and word_count >= 3) or word_count >= 10:
                    clean_sentence = sentence_buffer.strip()
                    sentence_buffer = ""

                    if clean_sentence and not self.is_interrupted:
                        # Stream text to UI bubble progressively
                        await self.send_json({
                            "type": "transcript_chunk",
                            "turn_id": turn_id,
                            "chunk_index": chunk_idx,
                            "text": clean_sentence
                        })

                        # Synthesize this sentence immediately with adaptive prosody
                        try:
                            audio_chunks = []
                            async for raw_chunk in stream_edge_tts_chunks(
                                clean_sentence,
                                voice=self.voice_id,
                                dominant_state=dominant_user_state
                            ):
                                if self.is_interrupted or turn_id != self.turn_id:
                                    break
                                audio_chunks.append(raw_chunk)

                            if audio_chunks and not self.is_interrupted:
                                combined_audio = b"".join(audio_chunks)
                                await self.send_audio_chunk(turn_id, chunk_idx, clean_sentence, combined_audio)
                                chunk_idx += 1
                        except Exception as tts_err:
                            print(f"[!] Streaming TTS error: {tts_err}")

            # Flush any remaining tail text in buffer
            remaining_text = sentence_buffer.strip()
            if remaining_text and not self.is_interrupted and turn_id == self.turn_id:
                await self.send_json({
                    "type": "transcript_chunk",
                    "turn_id": turn_id,
                    "chunk_index": chunk_idx,
                    "text": remaining_text
                })
                try:
                    audio_chunks = []
                    async for raw_chunk in stream_edge_tts_chunks(
                        remaining_text,
                        voice=self.voice_id,
                        dominant_state=dominant_user_state
                    ):
                        if self.is_interrupted or turn_id != self.turn_id:
                            break
                        audio_chunks.append(raw_chunk)
                    if audio_chunks and not self.is_interrupted:
                        combined_audio = b"".join(audio_chunks)
                        await self.send_audio_chunk(turn_id, chunk_idx, remaining_text, combined_audio)
                except Exception:
                    pass

            if not self.is_interrupted and turn_id == self.turn_id:
                await self.send_json({
                    "type": "turn_complete",
                    "turn_id": turn_id,
                    "full_text": full_reply_text.strip()
                })

                # Asynchronously save conversation messages and mental health record to DB
                clean_user = transcript
                clean_ai = full_reply_text.strip()
                await loop.run_in_executor(None, save_message, self.session_id, "user", clean_user, None, None, self.user_id)
                await loop.run_in_executor(None, save_message, self.session_id, "assistant", clean_ai, None, None, self.user_id)
                try:
                    await loop.run_in_executor(
                        None,
                        save_mental_health_record,
                        self.session_id,
                        75,
                        dominant_user_state,
                        tone_emotion.get("emotion", "calm"),
                        0,
                        clean_user,
                        clean_ai,
                        acoustic_features,
                        self.user_id
                    )
                except Exception as save_err:
                    print(f"[!] Background mental health record save notice: {save_err}")

        except asyncio.CancelledError:
            print(f"[*] Turn {turn_id} task was cancelled.")
        except Exception as e:
            print(f"[!] Error in process_utterance [{turn_id}]: {e}")
            await self.send_json({"type": "error", "message": str(e)})


async def handle_voice_websocket(websocket: WebSocket):
    """FastAPI WebSocket endpoint handler for /api/ws/voice."""
    session = StreamingVoiceSession(websocket)
    await session.handle_connect()

    try:
        while True:
            message = await websocket.receive()

            # 1. Text Messages (JSON control frames: config, ping, interrupt)
            if "text" in message:
                try:
                    payload = json.loads(message["text"])
                    msg_type = payload.get("type")

                    if msg_type == "config":
                        if payload.get("session_id"):
                            session.session_id = payload["session_id"]
                        if payload.get("user_id"):
                            session.user_id = payload["user_id"]
                        if payload.get("voice") in VALID_VOICE_IDS:
                            session.voice_id = payload["voice"]
                        print(f"[*] Config updated for session: {session.session_id}, voice: {session.voice_id}")

                    elif msg_type == "interrupt":
                        session.interrupt(payload.get("turn_id"))
                        await session.send_json({"type": "status", "state": "listening"})

                    elif msg_type == "ping":
                        await session.send_json({"type": "pong"})

                except Exception as json_err:
                    print(f"[!] WebSocket JSON parse notice: {json_err}")

            # 2. Binary Messages (Raw 16kHz 16-bit Mono PCM audio chunks from browser)
            elif "bytes" in message:
                pcm_chunk = message["bytes"]
                if not pcm_chunk:
                    continue

                # Run Silero VAD on CPU
                vad_result = session.vad.feed_pcm(pcm_chunk)

                # Keep a 300ms pre-speech buffer so initial syllables are never clipped
                if not session.vad.is_speech_active and not session.vad.has_spoken:
                    session.pre_speech_ring_buffer.extend(pcm_chunk)
                    # 300ms at 16kHz 16-bit = 9,600 bytes
                    if len(session.pre_speech_ring_buffer) > 9600:
                        del session.pre_speech_ring_buffer[:-9600]

                if vad_result["is_speech"]:
                    # Speech detected: If assistant was speaking, trigger instant barge-in!
                    if session.active_generator_task and not session.active_generator_task.done():
                        session.interrupt()
                        await session.send_json({"type": "interrupted", "turn_id": session.turn_id})
                        await session.send_json({"type": "status", "state": "listening"})

                    if len(session.accumulated_turn_pcm) == 0 and len(session.pre_speech_ring_buffer) > 0:
                        session.accumulated_turn_pcm.extend(session.pre_speech_ring_buffer)
                        session.pre_speech_ring_buffer.clear()

                    session.accumulated_turn_pcm.extend(pcm_chunk)

                elif vad_result["speech_ended"]:
                    # Speech turn completed by natural silence
                    print(f"[*] Speech end detected. Captured {len(session.accumulated_turn_pcm)} bytes of PCM audio.")
                    await session.send_json({"type": "status", "state": "processing"})

                    turn_pcm = bytes(session.accumulated_turn_pcm)
                    session.accumulated_turn_pcm.clear()
                    session.vad.reset()

                    # Only process if we have >= 400ms of audio
                    if len(turn_pcm) >= 12800:
                        session.turn_id += 1
                        session.is_interrupted = False
                        session.active_generator_task = asyncio.create_task(
                            session.process_utterance(turn_pcm, session.turn_id)
                        )
                    else:
                        await session.send_json({"type": "status", "state": "listening"})

    except (WebSocketDisconnect, RuntimeError):
        print(f"[*] Voice WebSocket disconnected for session: {session.session_id}")
    except Exception as e:
        print(f"[!] WebSocket loop error: {e}")
    finally:
        session.interrupt()
