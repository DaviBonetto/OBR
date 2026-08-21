#!/usr/bin/env bash
set -euo pipefail

RAIZ_OBR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ_OBR"

UV_OBR="${OBR_UV_BIN:-${HOME}/.local/bin/uv}"
if [[ ! -x "$UV_OBR" ]]; then
  UV_OBR="$(command -v uv || true)"
fi
if [[ -z "$UV_OBR" || ! -x "$UV_OBR" ]]; then
  printf 'Erro: uv nao encontrado no PATH nem em ~/.local/bin.\n' >&2
  exit 127
fi

exec "$UV_OBR" run --locked --extra captura obr-capturar \
  --configuracao-camera "${OBR_CAMERA_CONFIGURACAO:-camera_usb.toml}" \
  --origem "${OBR_CAMERA_ORIGEM:-/dev/video0}" \
  --host "${OBR_PAINEL_HOST:-0.0.0.0}" \
  --porta "${OBR_PAINEL_PORTA:-8080}"
