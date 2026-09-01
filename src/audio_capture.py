"""Graba el audio de una reunión: lo que se escucha por los parlantes (los
demás participantes, vía BlackHole) y el micrófono (tu propia voz) al mismo
tiempo, y los mezcla en un solo archivo.

La grabación se puede controlar de dos formas:
- CLI: record() bloquea hasta que el usuario presiona Enter o Ctrl+C.
- Programática (ej. la app web): start_recording() devuelve un RecordingHandle
  que se detiene llamando a handle.stop() desde otro lugar del código.
"""

import os
import subprocess
import sys
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

WARNING_AFTER_SECONDS = 60 * 60  # avisar al llegar a 1 hora
MAX_DURATION_SECONDS = 2 * 60 * 60  # cortar sola a las 2 horas


def _notify_macos(title: str, message: str) -> None:
    """Muestra una notificación nativa de macOS. No hace nada si falla
    (por ejemplo, en un sistema que no sea macOS) — nunca debe interrumpir
    la grabación."""
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    script = f'display notification "{escape(message)}" with title "{escape(title)}" sound name "Glass"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
    except Exception:
        pass


def list_devices() -> None:
    print(sd.query_devices())


def find_device_index(name: str) -> int:
    devices = sd.query_devices()
    for index, device in enumerate(devices):
        if name.lower() in device["name"].lower() and device["max_input_channels"] > 0:
            return index
    raise RuntimeError(
        f'No se encontró un dispositivo de entrada llamado "{name}". '
        'Corré "devices" para ver los dispositivos disponibles y confirmá '
        "que BlackHole esté instalado (ver README.md)."
    )


def _find_default_mic_index(exclude_index: int):
    """Devuelve el índice del micrófono por defecto del sistema, o None si
    coincide con el dispositivo del sistema (para no grabarlo dos veces) o
    si no hay ninguno disponible."""
    try:
        mic_info = sd.query_devices(kind="input")
    except Exception:
        return None
    mic_index = mic_info.get("index")
    if mic_index is None or mic_index == exclude_index or mic_info["max_input_channels"] < 1:
        return None
    return mic_index


def _record_stream(
    device_index: int,
    channels: int,
    samplerate: int,
    path: str,
    stop_event: threading.Event,
    frames_written: list,
    chunk_sink: list = None,
    chunk_lock: threading.Lock = None,
) -> None:
    """Graba de un dispositivo a un archivo hasta que se activa stop_event.
    Acumula la cantidad de frames escritos en frames_written[0] (para que el
    llamador pueda leerlo incluso si esta función termina por una excepción).
    Si se pasan chunk_sink/chunk_lock, además va acumulando ahí una copia de
    cada bloque recibido (para las sugerencias en vivo)."""
    with sf.SoundFile(path, mode="w", samplerate=samplerate, channels=channels) as sound_file:
        def callback(indata, frame_count, time_info, status):
            if status:
                print(status, file=sys.stderr)
            sound_file.write(indata)
            frames_written[0] += frame_count
            if chunk_sink is not None:
                with chunk_lock:
                    chunk_sink.append(indata.copy())

        with sd.InputStream(
            samplerate=samplerate,
            device=device_index,
            channels=channels,
            callback=callback,
        ):
            while not stop_event.is_set():
                sd.sleep(200)


def _mix_arrays(system_data: np.ndarray, mic_data: np.ndarray) -> np.ndarray:
    """Suma el audio del sistema y del micrófono (arrays en memoria,
    siempre 2D), rellenando con silencio el más corto."""
    length = max(len(system_data), len(mic_data))
    if len(system_data) < length:
        system_data = np.pad(system_data, ((0, length - len(system_data)), (0, 0)))
    if len(mic_data) < length:
        mic_data = np.pad(mic_data, ((0, length - len(mic_data)), (0, 0)))

    # Sumar el mic (mono o el canal que tenga) a cada canal del sistema.
    mic_mono = mic_data.mean(axis=1, keepdims=True)
    return np.clip(system_data + mic_mono, -1.0, 1.0)


def _mix_and_cleanup(system_path: str, mic_path: str, output_path: str, samplerate: int) -> None:
    """Suma el audio del sistema y del micrófono en un solo archivo y borra
    los archivos temporales."""
    system_data, _ = sf.read(system_path, always_2d=True)
    mic_data, _ = sf.read(mic_path, always_2d=True)
    mixed = _mix_arrays(system_data, mic_data)
    sf.write(output_path, mixed, samplerate)
    os.remove(system_path)
    os.remove(mic_path)


def _run_chunk_loop(
    chunk_seconds: int,
    samplerate: int,
    dual: bool,
    system_sink: list,
    mic_sink: list,
    chunk_lock: threading.Lock,
    stop_event: threading.Event,
    on_chunk,
) -> None:
    """Cada chunk_seconds, toma lo acumulado en los buffers desde la última
    vez, lo mezcla, lo escribe a un WAV temporal, y llama a on_chunk(path)
    con él. on_chunk es responsable de borrar ese archivo cuando termine.
    Cualquier error acá se ignora — nunca debe afectar la grabación real."""
    while not stop_event.wait(chunk_seconds):
        try:
            with chunk_lock:
                system_blocks, mic_blocks = list(system_sink), list(mic_sink)
                system_sink.clear()
                mic_sink.clear()

            if not system_blocks and not mic_blocks:
                continue

            system_data = np.concatenate(system_blocks, axis=0) if system_blocks else np.zeros((0, 2))
            if dual:
                mic_data = np.concatenate(mic_blocks, axis=0) if mic_blocks else np.zeros((0, 1))
                mixed = _mix_arrays(system_data, mic_data)
            else:
                mixed = system_data

            if len(mixed) == 0:
                continue

            chunk_path = f"/tmp/meeting_chunk_{time.time_ns()}.wav"
            sf.write(chunk_path, mixed, samplerate)
            on_chunk(chunk_path)
        except Exception:
            pass


class RecordingHandle:
    """Representa una grabación en curso. Llamar a .stop() para detenerla,
    mezclar el audio del sistema + micrófono, y obtener la duración final.

    Programa sola una notificación de macOS a la hora de grabación, y se
    corta sola a las 2 horas (ver WARNING_AFTER_SECONDS / MAX_DURATION_SECONDS)
    para no quedar grabando indefinidamente si alguien se olvida de pararla."""

    def __init__(self, output_path: str, samplerate: int, dual: bool):
        self.output_path = output_path
        self.samplerate = samplerate
        self.dual = dual
        self.stop_event = threading.Event()
        self.system_frames = [0]
        self.mic_frames = [0]
        self.system_path = output_path + ".system.tmp.wav"
        self.mic_path = output_path + ".mic.tmp.wav"
        self.started_at = time.monotonic()
        self.duration = None
        self.auto_stopped = False
        self._threads: list = []
        self._stopped = False
        self._stop_lock = threading.Lock()
        self._warning_timer = None
        self._max_duration_timer = None
        self._chunk_thread = None

    def _cancel_timers(self) -> None:
        for timer in (self._warning_timer, self._max_duration_timer):
            if timer is not None:
                timer.cancel()

    def stop(self) -> float:
        """Detiene la grabación, mezcla si corresponde, y devuelve la
        duración en segundos. Es seguro llamarla más de una vez (por
        ejemplo, manualmente y por el corte automático a la vez)."""
        with self._stop_lock:
            if self._stopped:
                return self.duration or 0.0
            self._stopped = True
            self._cancel_timers()

            self.stop_event.set()
            for thread in self._threads:
                thread.join()
            if self._chunk_thread is not None:
                # Le damos un margen corto al fragmento en vivo que pudiera
                # estar procesándose, para que alcance a limpiar su archivo
                # temporal. No esperamos indefinido: es una ayuda en vivo,
                # no debe demorar el cierre de la grabación real.
                self._chunk_thread.join(timeout=5)

            try:
                if self.dual:
                    frames_written = max(self.system_frames[0], self.mic_frames[0])
                    if os.path.exists(self.system_path) and os.path.exists(self.mic_path):
                        _mix_and_cleanup(self.system_path, self.mic_path, self.output_path, self.samplerate)
                else:
                    frames_written = self.system_frames[0]
            finally:
                for tmp in (self.system_path, self.mic_path):
                    if os.path.exists(tmp):
                        os.remove(tmp)

            self.duration = frames_written / self.samplerate
            return self.duration


def start_recording(
    output_path: str,
    device_name: str,
    samplerate: int = 48000,
    channels: int = 2,
    on_chunk=None,
    chunk_seconds: int = 45,
) -> RecordingHandle:
    """Arranca a grabar el audio del sistema (y el micrófono, si hay uno
    disponible) en background. Devuelve un RecordingHandle: llamá a
    handle.stop() para terminar.

    Si se pasa on_chunk (una función que recibe una ruta a un .wav), cada
    chunk_seconds se le va a entregar un fragmento con el audio mezclado
    grabado desde la última entrega — pensado para transcripción/sugerencias
    en vivo. on_chunk es responsable de borrar ese archivo. Un error ahí
    nunca interrumpe la grabación real."""
    device_index = find_device_index(device_name)
    device_info = sd.query_devices(device_index)
    system_channels = min(channels, device_info["max_input_channels"])

    mic_index = _find_default_mic_index(exclude_index=device_index)
    dual = mic_index is not None

    if dual:
        mic_info = sd.query_devices(mic_index)
        mic_channels = min(channels, mic_info["max_input_channels"]) or 1
        print(
            f'Grabando "{device_info["name"]}" (voces de la reunión) '
            f'+ "{mic_info["name"]}" (tu voz) -> {output_path}'
        )
    else:
        print(
            f'Grabando solo "{device_info["name"]}" (no encontré un micrófono para grabar tu voz) '
            f"-> {output_path}"
        )

    handle = RecordingHandle(output_path, samplerate, dual)

    chunk_lock = threading.Lock()
    system_chunk_sink = [] if on_chunk else None
    mic_chunk_sink = [] if (on_chunk and dual) else None

    if dual:
        t_system = threading.Thread(
            target=_record_stream,
            args=(device_index, system_channels, samplerate, handle.system_path, handle.stop_event, handle.system_frames),
            kwargs=dict(chunk_sink=system_chunk_sink, chunk_lock=chunk_lock),
        )
        t_mic = threading.Thread(
            target=_record_stream,
            args=(mic_index, mic_channels, samplerate, handle.mic_path, handle.stop_event, handle.mic_frames),
            kwargs=dict(chunk_sink=mic_chunk_sink, chunk_lock=chunk_lock),
        )
        handle._threads = [t_system, t_mic]
    else:
        t_system = threading.Thread(
            target=_record_stream,
            args=(device_index, system_channels, samplerate, output_path, handle.stop_event, handle.system_frames),
            kwargs=dict(chunk_sink=system_chunk_sink, chunk_lock=chunk_lock),
        )
        handle._threads = [t_system]

    for thread in handle._threads:
        thread.start()

    if on_chunk:
        handle._chunk_thread = threading.Thread(
            target=_run_chunk_loop,
            args=(
                chunk_seconds,
                samplerate,
                dual,
                system_chunk_sink,
                mic_chunk_sink if dual else [],
                chunk_lock,
                handle.stop_event,
                on_chunk,
            ),
            daemon=True,
        )
        handle._chunk_thread.start()

    def _warn() -> None:
        _notify_macos(
            "Grabador de Reuniones",
            f"Llevás {WARNING_AFTER_SECONDS // 60} minutos grabando. "
            f"Se va a detener sola a las {MAX_DURATION_SECONDS // 3600} horas si no hacés nada.",
        )

    def _auto_stop() -> None:
        handle.auto_stopped = True
        handle.stop()

    handle._warning_timer = threading.Timer(WARNING_AFTER_SECONDS, _warn)
    handle._warning_timer.daemon = True
    handle._warning_timer.start()

    handle._max_duration_timer = threading.Timer(MAX_DURATION_SECONDS, _auto_stop)
    handle._max_duration_timer.daemon = True
    handle._max_duration_timer.start()

    return handle


def record(output_path: str, device_name: str, samplerate: int = 48000, channels: int = 2) -> float:
    """Graba hasta que el usuario presiona Enter (o Ctrl+C), o hasta que se
    corta sola por el límite de tiempo. Devuelve la duración en segundos.
    Pensado para uso desde el CLI."""
    handle = start_recording(output_path, device_name, samplerate=samplerate, channels=channels)
    print("Cuando termine la reunión, presioná Enter (o Ctrl+C) para detener la grabación.")
    print(
        f"(Se va a avisar a la hora y a detener sola a las "
        f"{MAX_DURATION_SECONDS // 3600} horas si te olvidás.)"
    )

    def wait_for_enter() -> None:
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        handle.stop_event.set()

    listener = threading.Thread(target=wait_for_enter, daemon=True)
    listener.start()

    # Se desbloquea con Enter/Ctrl+C, o cuando el corte automático llama a handle.stop().
    handle.stop_event.wait()
    duration = handle.stop()

    if handle.auto_stopped:
        print(f"\nSe cortó sola por el límite de {MAX_DURATION_SECONDS // 3600} horas. Duración: {duration:.1f}s")
    else:
        print(f"\nGrabación detenida. Duración: {duration:.1f}s")
    return duration
