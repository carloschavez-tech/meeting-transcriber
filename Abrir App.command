#!/bin/bash
# Doble click para abrir la app de grabación de reuniones en el navegador.
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d ".venv" ]; then
  echo "No encontré el entorno instalado."
  echo "Corré primero 'Configurar.command' (doble click) para instalar todo."
  echo
  read -p "Presioná Enter para cerrar esta ventana..."
  exit 1
fi

source .venv/bin/activate

if curl -s -o /dev/null -m 1 http://127.0.0.1:5055/api/status; then
  echo "La app ya estaba abierta. Abriendo el navegador de nuevo..."
  open http://127.0.0.1:5055
  echo
  read -p "Presioná Enter para cerrar esta ventana (la app sigue corriendo en la otra)..."
  exit 0
fi

echo "Iniciando la app... se va a abrir sola en tu navegador en un momento."
echo "No cierres esta ventana mientras usás la app — minimizala si querés."
echo
python -m src.webapp
