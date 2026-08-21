#!/usr/bin/env bash
set -euo pipefail

RAIZ_OBR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ_OBR"

exec uv run --locked --extra captura obr-capturar \
  --configuracao-camera "${OBR_CAMERA_CONFIGURACAO:-camera_usb.toml}" \
  --origem "${OBR_CAMERA_ORIGEM:-/dev/video0}" \
  --host "${OBR_PAINEL_HOST:-0.0.0.0}" \
  --porta "${OBR_PAINEL_PORTA:-8080}"
