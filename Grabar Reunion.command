#!/bin/bash
# Doble click para grabar, transcribir y generar el informe de una reunión.
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d ".venv" ]; then
  echo "No encontré el entorno instalado."
  echo "Corré primero 'Configurar.command' (doble click) para instalar todo."
  echo
  read -p "Presioná Enter para cerrar esta ventana..."
  exit 1
fi

source .venv/bin/activate
python -m src.main run

echo
read -p "Listo. Presioná Enter para cerrar esta ventana..."
