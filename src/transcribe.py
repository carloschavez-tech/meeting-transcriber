"""Transcribe un archivo de audio a texto usando faster-whisper (local)."""

import json
import os
from typing import Optional

from faster_whisper import WhisperModel


def _format_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def transcribe(
    audio_path: str,
    output_dir: str,
    model_size: str = "medium",
    language: Optional[str] = None,
) -> str:
    """Transcribe audio_path y escribe transcript.txt / transcript.json en output_dir.
    Devuelve la ruta al transcript.txt."""
    print(f'Cargando modelo Whisper "{model_size}" (puede tardar la primera vez)...')
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"Transcribiendo {audio_path}...")
    segments_iter, info = model.transcribe(audio_path, language=language or None)

    segments = []
    lines = []
    for segment in segments_iter:
        text = segment.text.strip()
        segments.append({"start": segment.start, "end": segment.end, "text": text})
        lines.append(f"[{_format_timestamp(segment.start)}] {text}")
        print(lines[-1])

    os.makedirs(output_dir, exist_ok=True)
    txt_path = os.path.join(output_dir, "transcript.txt")
    json_path = os.path.join(output_dir, "transcript.json")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"language": info.language, "duration": info.duration, "segments": segments},
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\nTranscripción guardada en {txt_path}")
    return txt_path
