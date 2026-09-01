# meeting-transcriber

App local para grabar el audio de una reunión (Meet, Zoom, Teams, etc.), transcribirla
y generar un informe con IA — sin subir el audio a ningún servidor.

- **Captura de audio**: audio del sistema (todo lo que se escucha), no solo el micrófono.
- **Transcripción**: local con [faster-whisper](https://github.com/SYSTRAN/faster-whisper), sin costo.
- **Informe**: generado con Claude a través de [OpenRouter](https://openrouter.ai/).
- **Email automático** (opcional): el informe y la transcripción se pueden enviar por correo
  apenas termina de procesarse la reunión.
- **App con botón**: interfaz web local (se abre en el navegador, sin internet) con un
  botón de Grabar/Detener — no hace falta usar la Terminal.
- **Sugerencias de preguntas en vivo** (opcional): mientras grabás, un panel en la app va
  sugiriendo preguntas de requerimientos para hacerle al cliente, según lo conversado hasta
  el momento. No afecta la transcripción/informe final, que sigue usando el audio completo.
- **Corte automático de seguridad**: si te olvidás de parar, avisa a la hora (notificación de
  macOS) y se corta sola a las 2 horas, procesando todo automáticamente.
- **Diarización de hablantes**: no implementada todavía (ver `src/diarize.py`).

## Instalación rápida (en esta Mac o en otra)

Para llevar esto a otra computadora: copiá toda la carpeta `meeting-transcriber` (por
AirDrop, USB, o comprimida) a la otra Mac, y ahí:

1. **Doble click en `Configurar.command`.**
   Instala Homebrew (si falta), BlackHole, Python y todas las dependencias. Va a pedir
   la contraseña de la Mac una o dos veces (es normal, hace falta para instalar el
   driver de audio).
   > Si al hacer doble click dice "no se puede abrir porque es de un desarrollador no
   > identificado": click derecho sobre el archivo → **Abrir** → confirmar. Es un aviso
   > normal de macOS para archivos que llegaron desde otra computadora, no del App Store.
2. Si fue la primera vez que instaló BlackHole, **reiniciá la Mac**.
3. Configurá el **Multi-Output Device** (una sola vez, ver sección "Configuración de audio" abajo).
4. Completá el archivo `.env` con tu API key de OpenRouter (y, si querés, los datos de email — ver abajo).
5. **Doble click en `Abrir App.command`** cada vez que quieras grabar una reunión — se abre
   sola en el navegador con un botón de Grabar/Detener.

Todo lo demás de este documento es la referencia detallada de cada paso, por si algo falla.

## Configuración de audio (Multi-Output Device)

BlackHole por sí solo "captura" el audio del sistema pero no lo reproduce en tus
parlantes. Para poder escuchar la reunión mientras se graba, hay que crear un dispositivo
combinado (una sola vez por Mac):

1. Abrí **Audio MIDI Setup** (Spotlight → "Audio MIDI Setup", viene con macOS).
2. Click en el `+` abajo a la izquierda → **Create Multi-Output Device**.
3. Tildá **BlackHole 2ch** y **Bocinas de MacBook Air** (o tus parlantes/auriculares).
4. Renombrá el dispositivo a algo como "Reunion" (click derecho → Rename).

**Antes de cada reunión**, seleccioná ese dispositivo como salida de audio: icono 🔊 en la
barra de menú → elegí el que creaste (puede aparecer como "Dispositivo de salida múltiple"
aunque lo hayas renombrado, es el mismo).

## API key de OpenRouter

Creá una en [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) y
guardala en `.env` como `OPENROUTER_API_KEY`. El informe se genera con Claude a través de
OpenRouter (modelo `anthropic/claude-sonnet-4.5`).

## Email automático (opcional)

Para que el informe y la transcripción lleguen solos por correo al terminar cada reunión,
usá tu Gmail (o Google Workspace) con una **contraseña de aplicación** — no hace falta
crear ni pagar ninguna cuenta nueva:

1. Andá a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   (necesitás tener la verificación en 2 pasos activada en tu cuenta de Google).
2. Generá una contraseña de aplicación nueva, con el nombre que quieras (ej. "meeting-transcriber").
3. Copiá la contraseña de 16 caracteres que te muestra.
4. En `.env`, completá:

```
EMAIL_ENABLED=true
EMAIL_FROM=tu_correo@gmail.com
EMAIL_APP_PASSWORD=la contraseña de 16 caracteres (con o sin espacios)
EMAIL_TO=destinatario1@empresa.com, destinatario2@empresa.com
```

`EMAIL_TO` puede tener uno o varios correos separados por coma (por ejemplo, el tuyo y el
de tu jefe). Si usás otro proveedor de correo (no Gmail), cambiá también `SMTP_HOST` y
`SMTP_PORT` por los de tu proveedor.

## Uso

### Opción 1 — App con botón (recomendado)

Doble click en **`Abrir App.command`**. Se abre una ventana de Terminal (dejala abierta,
minimizala si querés) y automáticamente se abre tu navegador en `http://127.0.0.1:5055`
con la app:

1. Click en el botón rojo redondo para **empezar a grabar**.
2. Click de nuevo (ahora es un cuadrado) para **detener** — automáticamente transcribe,
   genera el informe con IA, lo muestra en la misma página y (si configuraste `EMAIL_*`)
   lo envía por correo.

Para cerrar la app: cerrá la pestaña del navegador y la ventana de Terminal.

### Opción 2 — Doble click sin navegador

**`Grabar Reunion.command`**: se abre una ventana de Terminal, arranca a grabar, y cuando
termina la reunión presionás **Enter** en esa ventana para parar — automáticamente
transcribe, genera el informe y (si lo configuraste) lo envía por email.

### Opción 3 — Desde Terminal

```bash
cd ~/meeting-transcriber
source .venv/bin/activate

# Confirmar que BlackHole aparece como dispositivo de entrada
python -m src.main devices

# Pipeline completo: graba (Enter o Ctrl+C para parar) -> transcribe -> informe -> email
python -m src.main run

# O paso a paso:
python -m src.main record --output meetings/mi_reunion
python -m src.main transcribe meetings/mi_reunion/audio.wav
python -m src.main report meetings/mi_reunion/transcript.txt
```

Cada corrida sin `--output` crea una carpeta con timestamp en `meetings/` con:

```
meetings/2026-07-28_15-30-00/
├── audio.wav          # grabación
├── transcript.txt      # transcripción con timestamps
├── transcript.json     # segmentos (base para diarización futura)
└── report.md            # informe generado con IA
```

## Instalación manual (si `Configurar.command` falla)

### Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### BlackHole 2ch

```bash
brew install blackhole-2ch
```

### Entorno de Python

```bash
cd ~/meeting-transcriber
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Editá `.env` con tu `OPENROUTER_API_KEY` (y los datos de `EMAIL_*` si querés).

## Notas

- El modelo Whisper "medium" es un buen balance calidad/velocidad en un Apple M4. Para
  mayor calidad (más lento) probá `WHISPER_MODEL=large-v3` en `.env`; para más velocidad,
  `small`.
- La primera vez que corrés `transcribe`, `faster-whisper` descarga el modelo (puede
  tardar unos minutos según el tamaño).
- Cada Mac que use esto necesita su propia instalación de BlackHole y su propio Multi-Output
  Device (son configuraciones del sistema operativo, no del proyecto), pero podés reutilizar
  la misma `OPENROUTER_API_KEY` y configuración de email en todas.
- Diarización de hablantes: ver `src/diarize.py` para los pasos de habilitarla más adelante.
