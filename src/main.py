"""CLI para grabar, transcribir e informar reuniones.

Uso:
    python -m src.main devices
    python -m src.main record [--output DIR]
    python -m src.main transcribe AUDIO_WAV [--output DIR]
    python -m src.main report TRANSCRIPT_TXT [--output DIR]
    python -m src.main run [--output DIR]
"""

import argparse
import os

from dotenv import load_dotenv

from src import audio_capture, email_sender, report, spec_generator, transcribe
from src.meetings import new_meeting_dir

load_dotenv()

DEFAULT_DEVICE_NAME = os.environ.get("AUDIO_DEVICE_NAME", "BlackHole 2ch")
DEFAULT_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "medium")
DEFAULT_WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE") or None


def cmd_devices(_args) -> None:
    audio_capture.list_devices()


def cmd_record(args) -> None:
    output_dir = args.output or new_meeting_dir()
    os.makedirs(output_dir, exist_ok=True)
    audio_path = os.path.join(output_dir, "audio.wav")
    audio_capture.record(audio_path, DEFAULT_DEVICE_NAME)
    print(f"Audio guardado en {audio_path}")


def cmd_transcribe(args) -> None:
    output_dir = args.output or os.path.dirname(os.path.abspath(args.audio))
    transcribe.transcribe(
        args.audio, output_dir, model_size=DEFAULT_WHISPER_MODEL, language=DEFAULT_WHISPER_LANGUAGE
    )


def cmd_report(args) -> None:
    output_dir = args.output or os.path.dirname(os.path.abspath(args.transcript))
    report_path = report.generate_report(args.transcript, output_dir)
    spec_path = spec_generator.generate_spec(args.transcript, output_dir)
    email_sender.send_meeting_email(report_path, args.transcript, spec_path=spec_path)


def cmd_run(args) -> None:
    output_dir = args.output or new_meeting_dir()
    os.makedirs(output_dir, exist_ok=True)

    audio_path = os.path.join(output_dir, "audio.wav")
    audio_capture.record(audio_path, DEFAULT_DEVICE_NAME)

    transcript_path = transcribe.transcribe(
        audio_path, output_dir, model_size=DEFAULT_WHISPER_MODEL, language=DEFAULT_WHISPER_LANGUAGE
    )

    report_path = report.generate_report(transcript_path, output_dir)
    spec_path = spec_generator.generate_spec(transcript_path, output_dir)
    email_sender.send_meeting_email(report_path, transcript_path, spec_path=spec_path)
    print(f"\nListo. Todo guardado en {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcriptor e informador de reuniones")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("devices", help="Listar dispositivos de audio").set_defaults(func=cmd_devices)

    record_parser = subparsers.add_parser("record", help="Grabar audio hasta Ctrl+C")
    record_parser.add_argument("--output", help="Carpeta de salida")
    record_parser.set_defaults(func=cmd_record)

    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribir un archivo de audio")
    transcribe_parser.add_argument("audio", help="Ruta al archivo .wav")
    transcribe_parser.add_argument("--output", help="Carpeta de salida")
    transcribe_parser.set_defaults(func=cmd_transcribe)

    report_parser = subparsers.add_parser("report", help="Generar informe desde una transcripción")
    report_parser.add_argument("transcript", help="Ruta al archivo transcript.txt")
    report_parser.add_argument("--output", help="Carpeta de salida")
    report_parser.set_defaults(func=cmd_report)

    run_parser = subparsers.add_parser("run", help="Pipeline completo: grabar, transcribir e informar")
    run_parser.add_argument("--output", help="Carpeta de salida")
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
