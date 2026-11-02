"""
Arogya Acoustic Biomarkers Engine
===================================
Lightweight, ultra-fast speech feature extraction using only numpy and scipy.
Zero heavy deep learning or PyTorch models required (Render 512MB RAM safe, <1ms execution).

Features extracted:
- Fundamental frequency (f0) & semitone normalization (pYIN/autocorrelation approximation)
- Pitch stability & semitone deviation (standard deviation in semitones)
- Vocal Jitter (absolute cycle-to-cycle pitch period variability, %)
- Vocal Shimmer (cycle-to-cycle peak amplitude variability, %)
- Speech duration, RMS power energy, and frame-based pause/silence ratio
- Guard condition: audio < 0.6s early-returns "insufficient_duration" placeholder
"""

import io
import os
from typing import Dict, Any, Union, Tuple, Optional
import numpy as np
from scipy.signal import find_peaks

def load_audio_to_numpy(audio_input: Union[str, bytes, io.BytesIO]) -> Tuple[Optional[np.ndarray], int]:
    """
    Decodes audio from path, bytes, or BytesIO in pure memory.
    Supports WAV, MP3, OGG via soundfile, and WebM Opus via PyAV.
    """
    # 1. If already bytes or BytesIO
    if isinstance(audio_input, bytes):
        bio = io.BytesIO(audio_input)
    elif isinstance(audio_input, io.BytesIO):
        bio = audio_input
        bio.seek(0)
    elif isinstance(audio_input, str) and os.path.exists(audio_input):
        with open(audio_input, "rb") as f:
            bio = io.BytesIO(f.read())
    else:
        return None, 0

    # Try soundfile first (fastest for WAV / MP3 / OGG)
    try:
        import soundfile as sf
        bio.seek(0)
        data, sr = sf.read(bio)
        if data is not None and len(data) > 0:
            if data.ndim > 1:
                y = np.mean(data, axis=1)
            else:
                y = data.astype(np.float32)
            return y, sr
    except Exception:
        pass

    # Try PyAV for WebM / Opus containers in-memory
    try:
        import av
        bio.seek(0)
        container = av.open(bio)
        frames = []
        sr = 16000
        for frame in container.decode(audio=0):
            sr = frame.sample_rate
            frames.append(frame.to_ndarray())
        if frames:
            audio_np = np.concatenate(frames, axis=1)
            if audio_np.ndim > 1:
                y = np.mean(audio_np, axis=0).astype(np.float32)
            else:
                y = audio_np.astype(np.float32)
            return y, sr
    except Exception:
        pass

    return None, 0


def calculate_jitter_and_shimmer(y: np.ndarray, sr: int) -> Tuple[Optional[float], Optional[float]]:
    """
    Pure mathematical calculations for vocal Jitter and Shimmer.
    - Jitter: Absolute difference between consecutive peak-to-peak pitch periods divided by mean period (%)
    - Shimmer: Variability of peak amplitudes between consecutive voice cycles divided by mean amplitude (%)
    """
    if len(y) < int(sr * 0.25):
        return None, None

    # Expected human pitch range: 75 Hz to 450 Hz
    min_dist = max(1, int(sr / 450)) # ~35 samples at 16kHz
    peaks, _ = find_peaks(y, distance=min_dist, height=0.015)
    
    if len(peaks) < 4:
        return None, None

    periods = np.diff(peaks)
    if len(periods) < 3:
        return None, None

    mean_period = float(np.mean(periods))
    if mean_period <= 0:
        return None, None

    # Relative local Jitter (%)
    jitter = float(np.mean(np.abs(np.diff(periods))) / mean_period * 100.0)

    # Relative local Shimmer (%)
    peak_amps = np.abs(y[peaks])
    mean_amp = float(np.mean(peak_amps))
    if mean_amp <= 1e-6:
        return jitter, None

    shimmer = float(np.mean(np.abs(np.diff(peak_amps))) / mean_amp * 100.0)
    
    return round(jitter, 2), round(shimmer, 2)


def extract_acoustic_features(audio_input: Union[str, bytes, io.BytesIO, np.ndarray]) -> Dict[str, Any]:
    """
    Extracts acoustic speech biomarkers with strict early-guard duration checks.
    If audio duration < 0.6s, populates metrics with "insufficient_duration" placeholders.
    """
    if isinstance(audio_input, np.ndarray):
        y = audio_input
        sr = 16000
    else:
        y, sr = load_audio_to_numpy(audio_input)

    if y is None or len(y) == 0 or sr <= 0:
        return {
            "duration": 0.0,
            "pitch_semitone_std": "insufficient_duration",
            "median_f0": "insufficient_duration",
            "jitter_percent": "insufficient_duration",
            "shimmer_percent": "insufficient_duration",
            "rms_energy": 0.0,
            "pause_ratio": 0.0,
            "is_valid_speech": False,
            "note": "Empty or unparseable audio sample"
        }

    duration = float(len(y) / sr)

    # 1. Early-Return Guard: Audio duration shorter than 0.6 seconds
    if duration < 0.6:
        rms_val = float(np.sqrt(np.mean(y**2)))
        return {
            "duration": round(duration, 2),
            "pitch_semitone_std": "insufficient_duration",
            "median_f0": "insufficient_duration",
            "jitter_percent": "insufficient_duration",
            "shimmer_percent": "insufficient_duration",
            "rms_energy": round(rms_val, 4),
            "pause_ratio": 0.0,
            "is_valid_speech": False,
            "note": "Audio sample too brief for stable acoustic biomarker extraction"
        }

    # Limit analysis window to first 8 seconds for speed and low CPU
    analysis_y = y[:int(sr * 8.0)] if duration > 8.0 else y
    rms_energy = float(np.sqrt(np.mean(analysis_y**2)))

    # Frame-based pause/silence ratio (100ms frames)
    frame_len = max(1, int(sr * 0.1))
    n_frames = len(analysis_y) // frame_len
    if n_frames > 0:
        frames = analysis_y[:n_frames * frame_len].reshape(n_frames, frame_len)
        frame_rms = np.sqrt(np.mean(frames**2, axis=1))
        silent_frames = np.sum(frame_rms < (0.15 * (np.max(frame_rms) + 1e-6)))
        pause_ratio = round(float(silent_frames / n_frames), 2)
    else:
        pause_ratio = 0.0

    # Fast autocorrelation pitch estimation on 30ms voiced windows
    frame_size = int(sr * 0.03)
    hop_size = int(sr * 0.015)
    fmin, fmax = 75, 400
    min_lag = max(1, int(sr / fmax))
    max_lag = min(frame_size - 1, int(sr / fmin))

    pitches = []
    for start in range(0, len(analysis_y) - frame_size, hop_size):
        frame = analysis_y[start:start + frame_size]
        f_rms = np.sqrt(np.mean(frame**2))
        if f_rms < 0.015:
            continue
        corr = np.correlate(frame, frame, mode='full')[frame_size - 1:]
        if len(corr) > max_lag:
            window_corr = corr[min_lag:max_lag]
            if len(window_corr) > 0:
                best_lag = min_lag + np.argmax(window_corr)
                if corr[best_lag] > 0.3 * corr[0]:
                    freq = float(sr / best_lag)
                    pitches.append(freq)

    # Calculate Jitter and Shimmer
    jitter, shimmer = calculate_jitter_and_shimmer(analysis_y, sr)

    if len(pitches) >= 3:
        median_f0 = float(np.median(pitches))
        if median_f0 > 0:
            semitones = 12.0 * np.log2(np.array(pitches) / median_f0)
            semitone_std = round(float(np.std(semitones)), 2)
            is_valid = True
        else:
            semitone_std = "insufficient_duration"
            is_valid = False
    else:
        median_f0 = "insufficient_duration"
        semitone_std = "insufficient_duration"
        is_valid = False

    return {
        "duration": round(duration, 2),
        "pitch_semitone_std": semitone_std,
        "median_f0": round(median_f0, 1) if isinstance(median_f0, (int, float)) else median_f0,
        "jitter_percent": jitter if jitter is not None else "insufficient_duration",
        "shimmer_percent": shimmer if shimmer is not None else "insufficient_duration",
        "rms_energy": round(rms_energy, 4),
        "pause_ratio": pause_ratio,
        "is_valid_speech": is_valid,
        "note": "Acoustic biomarkers extracted successfully"
    }
