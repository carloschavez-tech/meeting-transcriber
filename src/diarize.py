"""Punto de extensión para diarización de hablantes (quién dijo qué).

No implementado todavía. Cuando quieras habilitarlo:

1. Crear una cuenta gratuita en https://huggingface.co/ y generar un token en
   https://huggingface.co/settings/tokens
2. Aceptar la licencia de los modelos:
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0
3. `pip install pyannote.audio` y agregar HUGGINGFACE_TOKEN a tu .env
4. Implementar diarize(audio_path, transcript_segments) -> segments con
   speaker asignado, cruzando los timestamps de pyannote con los de
   transcribe.py (ver transcript.json).
"""
