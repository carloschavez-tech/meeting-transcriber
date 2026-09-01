#!/bin/bash
# Instalador de un solo paso para meeting-transcriber.
# Uso: ./setup.sh   (o doble click en "Configurar.command")
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "=================================================="
echo " meeting-transcriber — instalación"
echo "=================================================="
echo

# 1. Homebrew
if ! command -v brew &> /dev/null; then
  echo "-> Homebrew no está instalado. Instalando (te va a pedir tu contraseña de Mac)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Agregar Homebrew al PATH de esta sesión y de forma permanente (Apple Silicon)
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
    if ! grep -q "brew shellenv" "$HOME/.zprofile" 2>/dev/null; then
      echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"
    fi
  fi
else
  echo "-> Homebrew ya está instalado, OK."
  eval "$(brew shellenv)"
fi
echo

# 2. BlackHole
if ! brew list --cask blackhole-2ch &> /dev/null; then
  echo "-> Instalando BlackHole 2ch (driver de audio, te puede pedir tu contraseña otra vez)..."
  brew install blackhole-2ch
  echo
  echo "*** IMPORTANTE: reiniciá la Mac después de que termine este script para que BlackHole quede activo. ***"
else
  echo "-> BlackHole 2ch ya está instalado, OK."
fi
echo

# 3. Entorno virtual de Python
if [ ! -d ".venv" ]; then
  echo "-> Creando entorno virtual de Python..."
  python3 -m venv .venv
else
  echo "-> Entorno virtual ya existe, OK."
fi

echo "-> Instalando dependencias de Python..."
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo

# 4. Archivo .env
if [ ! -f ".env" ]; then
  echo "-> Creando .env desde la plantilla..."
  cp .env.example .env
  echo "   Completá .env con tu OPENROUTER_API_KEY y, si querés emails automáticos,"
  echo "   los datos de EMAIL_* (ver README.md)."
else
  echo "-> .env ya existe, no lo toco."
fi

echo
echo "=================================================="
echo " Instalación completa."
echo "=================================================="
echo
echo "Próximos pasos:"
echo "  1. Si instalé BlackHole por primera vez arriba, REINICIÁ LA MAC ahora."
echo "  2. Configurá el 'Multi-Output Device' en Audio MIDI Setup (ver README.md, sección 1.3)."
echo "  3. Completá el archivo .env con tu API key (y datos de email, si querés)."
echo "  4. Usá 'Grabar Reunion.command' (doble click) para grabar tu próxima reunión."
echo
