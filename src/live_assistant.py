"""Sugerencias en vivo durante una reunión: transcribe fragmentos cortos de
audio a medida que se graban y le pide a la IA preguntas de sondeo (técnicas
del skill 'entrevista-a-spec') para hacerle al cliente, según lo conversado
hasta el momento.

Las preguntas se van ACUMULANDO en una lista que solo crece hacia abajo — se
le pide explícitamente a la IA que no repita ni reformule preguntas ya
sugeridas, para no confundir a quien está mirando en medio de la reunión.

Esto es una ayuda en vivo, no reemplaza el pipeline final (transcripción
completa + informe + spec de dominio), que sigue corriendo igual sobre el
audio completo al terminar. Cualquier error acá debe degradarse en
silencio — nunca debe interrumpir la grabación ni el resultado final."""

import os
import threading

from faster_whisper import WhisperModel
from openai import OpenAI

from src.report import OPENROUTER_BASE_URL, REPORT_MODEL

DEFAULT_LIVE_MODEL = "medium"
NO_NEW_QUESTIONS_MARKER = "NADA_NUEVO"

SYSTEM_PROMPT = (
    "Sos un asistente en vivo para alguien que está entrevistando a un cliente ahora "
    "mismo, aplicando la metodología 'entrevista a spec': el objetivo final es armar una "
    "especificación de dominio con reglas, invariantes y casos de verificación con cifras "
    "reales — no una lista de deseos.\n\n"
    "Te paso la transcripción de la reunión hasta este momento, y las preguntas que ya le "
    "sugeriste antes. Tu trabajo es sugerir hasta 3 preguntas NUEVAS — que no repitan ni "
    "reformulen una ya sugerida — para que el entrevistador se las haga al cliente A "
    "CONTINUACIÓN.\n\n"
    "El valor está en lo que la persona NO dijo porque le pareció obvio. Para encontrarlo, "
    "cazá estos disparadores de ambigüedad en lo último que se dijo:\n"
    "- 'normalmente' / 'en general' / 'casi siempre' → preguntar por la excepción: ¿y la "
    "vez que no fue así?\n"
    "- 'el sistema valida' → ¿contra qué exactamente? ¿qué pasa si no pasa la validación?\n"
    "- 'automáticamente' → ¿qué lo dispara? ¿alguien puede hacerlo a mano también?\n"
    "- 'debería' → ¿hoy pasa así en la realidad, o es un deseo? ¿quién decidió que debería "
    "ser así?\n"
    "- 'obvio' / 'eso ya se sabe' → pedir que lo digan completo, ahí vive lo no escrito\n"
    "- 'se notifica' / 'se informa' → ¿a quién exactamente, con qué, y qué pasa si no "
    "llega?\n"
    "- 'rápido' / 'muchos' / 'un tiempo' (sin cifra) → pedir el número exacto, sin número "
    "no es un requerimiento\n\n"
    "Además, si un tema ya quedó cerrado con una regla general, priorizá preguntar por el "
    "CONTRAEJEMPLO en vez de repetir la regla ('¿alguna vez pasó que no fue así? ¿qué pasó "
    "ahí?'), o pedir el CASO FEO ('¿cuál fue la vez más rara o más grande que viste de "
    "esto?') — de ahí salen los invariantes y los casos de verificación reales.\n\n"
    "No preguntes nada que la transcripción ya conteste. No preguntes por pantallas, "
    "tecnología ni implementación — mantené el foco en el negocio. Sé concreto y breve: "
    "esto se lee de un vistazo en medio de la reunión, no es un cuestionario. Respondé "
    "siempre en español. Si hay preguntas nuevas, respondé ÚNICAMENTE con la lista (una "
    f"por línea, empezando con '- '), sin introducción ni cierre. Si no hay ninguna "
    f"pregunta nueva que valga la pena agregar todavía, respondé ÚNICAMENTE con la palabra "
    f"{NO_NEW_QUESTIONS_MARKER}."
)


class LiveAssistant:
    """Una instancia por grabación. Acumula el transcript en vivo y la lista
    de preguntas sugeridas hasta el momento (solo crece, nunca se reemplaza)."""

    def __init__(self, whisper_model_size: str = None, language: str = None):
        self.whisper_model_size = whisper_model_size or os.environ.get("LIVE_WHISPER_MODEL", DEFAULT_LIVE_MODEL)
        self.language = language
        self.transcript = ""
        self.suggested_questions: list = []
        self._lock = threading.Lock()
        self._model = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(self.whisper_model_size, device="cpu", compute_type="int8")
        return self._model

    def handle_chunk(self, chunk_path: str) -> None:
        """Pensado para pasarse como on_chunk a audio_capture.start_recording.
        Transcribe el fragmento, lo suma al transcript en vivo, y agrega
        preguntas nuevas (si las hay) a la lista acumulada. Nunca levanta
        excepción hacia afuera."""
        try:
            segments, _ = self._get_model().transcribe(chunk_path, language=self.language or None)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            if text:
                with self._lock:
                    self.transcript = (self.transcript + " " + text).strip()
                self._refresh_suggestions()
        except Exception:
            pass
        finally:
            try:
                os.remove(chunk_path)
            except OSError:
                pass

    def _refresh_suggestions(self) -> None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            return
        with self._lock:
            transcript = self.transcript
            already_asked = list(self.suggested_questions)
        if len(transcript) < 40:
            return

        already_asked_text = (
            "\n".join(f"- {q}" for q in already_asked) if already_asked else "Ninguna todavía."
        )

        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
        response = client.chat.completions.create(
            model=REPORT_MODEL,
            max_tokens=400,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Transcripción completa de la reunión hasta ahora:\n---\n{transcript}\n---\n\n"
                        f"Preguntas que ya sugeriste antes (no las repitas ni las reformules):\n"
                        f"{already_asked_text}"
                    ),
                },
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        if not text or NO_NEW_QUESTIONS_MARKER in text:
            return

        new_questions = [
            line.strip()[2:].strip()
            for line in text.splitlines()
            if line.strip().startswith("- ") and line.strip()[2:].strip()
        ]
        if not new_questions:
            return

        with self._lock:
            existing_lower = {q.lower() for q in self.suggested_questions}
            for question in new_questions:
                if question.lower() not in existing_lower:
                    self.suggested_questions.append(question)
                    existing_lower.add(question.lower())

    def get_suggestions(self) -> list:
        with self._lock:
            return list(self.suggested_questions)
