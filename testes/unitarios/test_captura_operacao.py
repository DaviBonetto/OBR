from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from obr_oficial.dispositivos import CameraSimulada
from obr_oficial.painel.operacao.captura import CapturadorOperacao


def _camera_ativa() -> CameraSimulada:
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    camera.iniciar()
    return camera


def test_capturar_foto_salva_png_na_pasta_do_dia(tmp_path: Path) -> None:
    camera = _camera_ativa()
    try:
        capturador = CapturadorOperacao(camera, tmp_path)
        caminho = capturador.capturar_foto()
        assert caminho.is_file()
        assert caminho.suffix == ".png"
        assert caminho.parent.parent == tmp_path
        situacao = capturador.estado()
        assert situacao["total_fotos"] == 1
        assert situacao["ultimo_arquivo"] == str(caminho.relative_to(tmp_path))
    finally:
        camera.parar()


def test_sequencia_captura_e_para(tmp_path: Path) -> None:
    camera = _camera_ativa()
    try:
        capturador = CapturadorOperacao(camera, tmp_path)
        resposta = capturador.alternar_sequencia(intervalo_ms=60, maximo=3)
        assert resposta["sequencia_ativa"] is True
        limite = time.monotonic() + 5.0
        while time.monotonic() < limite:
            if capturador.estado()["sequencia_capturados"] >= 3:
                break
            time.sleep(0.05)
        situacao = capturador.estado()
        assert situacao["sequencia_capturados"] == 3
        time.sleep(0.3)
        assert situacao["sequencia_ativa"] is False or not capturador.estado()["sequencia_ativa"]
        frames = sorted(Path(tmp_path).rglob("frame_*.png"))
        assert len(frames) == 3
    finally:
        camera.parar()


def test_video_grava_e_para(tmp_path: Path) -> None:
    camera = _camera_ativa()
    try:
        capturador = CapturadorOperacao(camera, tmp_path)
        resposta = capturador.alternar_video()
        assert resposta["video_ativo"] is True
        assert capturador.estado()["video_ativo"] is True
        time.sleep(0.6)
        encerramento = capturador.alternar_video()
        assert encerramento["video_ativo"] is False
        limite = time.monotonic() + 3.0
        while time.monotonic() < limite:
            if not capturador.estado()["video_ativo"]:
                break
            time.sleep(0.05)
        assert capturador.estado()["video_ativo"] is False
        videos = [c for c in Path(tmp_path).rglob("video_*") if c.is_file()]
        assert len(videos) == 1
        assert videos[0].stat().st_size > 0
    finally:
        camera.parar()


def test_estado_inicial_sem_capturas(tmp_path: Path) -> None:
    camera = _camera_ativa()
    try:
        capturador = CapturadorOperacao(camera, tmp_path)
        situacao = capturador.estado()
        assert situacao["video_ativo"] is False
        assert situacao["sequencia_ativa"] is False
        assert situacao["total_fotos"] == 0
        assert situacao["ultimo_arquivo"] == ""
        quadro = camera.obter_ultimo_quadro(timeout_s=1.0)
        assert quadro is not None
        assert quadro.imagem_bgr.shape == (120, 160, 3)
        assert quadro.imagem_bgr.dtype == np.uint8
    finally:
        camera.parar()
