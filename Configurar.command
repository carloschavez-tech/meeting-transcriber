#!/bin/bash
# Doble click para instalar todo lo necesario en esta Mac (Homebrew, BlackHole,
# Python y sus dependencias).
cd "$(dirname "${BASH_SOURCE[0]}")"
./setup.sh

echo
read -p "Presioná Enter para cerrar esta ventana..."
