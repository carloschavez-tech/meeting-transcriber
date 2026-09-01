"""Interfaz web local (tipo app) para grabar reuniones con un botón.

Uso: python -m src.webapp   (o doble click en 'Abrir App.command')
Abre http://127.0.0.1:5055 en el navegador.
"""

import os
import threading
import webbrowser

from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory

from src import audio_capture, email_sender, report, spec_generator, transcribe
from src.live_assistant import LiveAssistant
from src.meetings import new_meeting_dir

load_dotenv()

DEFAULT_DEVICE_NAME = os.environ.get("AUDIO_DEVICE_NAME", "BlackHole 2ch")
DEFAULT_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "medium")
DEFAULT_WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE") or None

LIVE_SUGGESTIONS_ENABLED = os.environ.get("LIVE_SUGGESTIONS_ENABLED", "true").strip().lower() in (
    "1", "true", "yes", "si", "sí",
)
LIVE_CHUNK_SECONDS = int(os.environ.get("LIVE_CHUNK_SECONDS", "45"))

PORT = 5055
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")

app = Flask(__name__, static_folder=None)

_lock = threading.Lock()
_state = {
    "status": "idle",  # idle | recording | processing | done | error
    "message": "Listo para grabar.",
    "meeting_dir": None,
}
_handle = None
_auto_stop_timer = None
_live_assistant = None


def _set_state(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def _begin_processing(handle, meeting_dir: str) -> None:
    """Corre en background: detiene la grabación (si no estaba ya detenida),
    transcribe, genera el informe y manda el email."""

    def process() -> None:
        try:
            duration = handle.stop()
            audio_path = os.path.join(meeting_dir, "audio.wav")
            _set_state(message=f"Grabación de {duration:.0f}s. Transcribiendo...")

            transcript_path = transcribe.transcribe(
                audio_path, meeting_dir, model_size=DEFAULT_WHISPER_MODEL, language=DEFAULT_WHISPER_LANGUAGE
            )
            _set_state(message="Generando informe con IA...")

            report_path = report.generate_report(transcript_path, meeting_dir)

            _set_state(message="Generando spec de dominio...")
            spec_path = spec_generator.generate_spec(transcript_path, meeting_dir)

            if email_sender.is_enabled():
                _set_state(message="Enviando por email...")
                email_sender.send_meeting_email(report_path, transcript_path, spec_path=spec_path)

            _set_state(
                status="done",
                message="Listo. Revisá el informe y el spec abajo (y tu correo, si lo configuraste).",
            )
        except Exception as exc:
            _set_state(status="error", message=f"Error: {exc}")

    threading.Thread(target=process, daemon=True).start()


def _do_stop():
    """Si hay una grabación en curso, la corta y dispara el procesamiento.
    Devuelve el estado resultante, o None si no había nada grabando.
    La llaman tanto /api/stop como el corte automático por límite de tiempo."""
    global _handle, _auto_stop_timer
    with _lock:
        if _state["status"] != "recording" or _handle is None:
            return None
        handle = _handle
        meeting_dir = _state["meeting_dir"]
        _handle = None
        if _auto_stop_timer is not None:
            _auto_stop_timer.cancel()
            _auto_stop_timer = None

    _set_state(status="processing", message="Grabación detenida. Transcribiendo...")
    _begin_processing(handle, meeting_dir)
    return dict(_state)


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/api/status")
def api_status():
    with _lock:
        payload = dict(_state)
        assistant = _live_assistant
    payload["live_suggestions"] = assistant.get_suggestions() if assistant else []
    return jsonify(payload)


@app.route("/api/start", methods=["POST"])
def api_start():
    global _handle, _auto_stop_timer, _live_assistant
    with _lock:
        if _state["status"] not in ("idle", "done", "error"):
            return jsonify({"error": "Ya hay una grabación en curso."}), 409

    meeting_dir = new_meeting_dir()
    assistant = LiveAssistant(language=DEFAULT_WHISPER_LANGUAGE) if LIVE_SUGGESTIONS_ENABLED else None
    try:
        handle = audio_capture.start_recording(
            os.path.join(meeting_dir, "audio.wav"),
            DEFAULT_DEVICE_NAME,
            on_chunk=assistant.handle_chunk if assistant else None,
            chunk_seconds=LIVE_CHUNK_SECONDS,
        )
    except Exception as exc:
        _set_state(status="error", message=f"No se pudo empezar a grabar: {exc}", meeting_dir=None)
        return jsonify({"error": str(exc)}), 500

    # Si nadie la para antes, esta misma grabación se corta y procesa sola
    # al llegar al límite de horas (ver audio_capture.MAX_DURATION_SECONDS).
    timer = threading.Timer(audio_capture.MAX_DURATION_SECONDS, _do_stop)
    timer.daemon = True
    timer.start()

    with _lock:
        _handle = handle
        _auto_stop_timer = timer
        _live_assistant = assistant
    _set_state(status="recording", message="Grabando...", meeting_dir=meeting_dir)
    return jsonify(dict(_state))


@app.route("/api/stop", methods=["POST"])
def api_stop():
    result = _do_stop()
    if result is None:
        return jsonify({"error": "No hay ninguna grabación en curso."}), 409
    return jsonify(result)


@app.route("/api/last-report")
def api_last_report():
    with _lock:
        meeting_dir = _state.get("meeting_dir")
    if not meeting_dir:
        return jsonify({"error": "Todavía no hay ningún informe."}), 404
    report_path = os.path.join(meeting_dir, "report.md")
    if not os.path.exists(report_path):
        return jsonify({"error": "El informe todavía no está listo."}), 404
    with open(report_path, "r", encoding="utf-8") as f:
        return jsonify({"report": f.read()})


@app.route("/api/last-spec")
def api_last_spec():
    with _lock:
        meeting_dir = _state.get("meeting_dir")
    if not meeting_dir:
        return jsonify({"error": "Todavía no hay ningún spec."}), 404
    spec_path = os.path.join(meeting_dir, "spec.md")
    if not os.path.exists(spec_path):
        return jsonify({"error": "El spec todavía no está listo."}), 404
    with open(spec_path, "r", encoding="utf-8") as f:
        return jsonify({"spec": f.read()})


def main() -> None:
    def open_browser() -> None:
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    threading.Timer(1.0, open_browser).start()
    print(f"Abriendo en http://127.0.0.1:{PORT} — dejá esta ventana abierta mientras usás la app.")
    app.run(host="127.0.0.1", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
