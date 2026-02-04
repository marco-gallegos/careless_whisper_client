#!/bin/bash
fswatch -xnr /Users/marco.gallegos/Movies/voice | while read f; do
  echo "$(date): Cambio detectado en /Users/marco.gallegos/"
  echo "$f"
  # Aquí pones tu lógica cuando detectes cambios
  # Ejemplo: ejecutar un script, mover archivos, etc.
  # /ruta/a/tu/script-de-accion.sh
done
