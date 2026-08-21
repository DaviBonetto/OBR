from time import sleep

import numpy as np
import pytest

from obr_oficial.dispositivos.buffer_ultimo_quadro import BufferUltimoQuadro
from obr_oficial.dispositivos.camera_base import MetricasImagem, QuadroCamera
from obr_oficial.dispositivos.camera_simulada import CameraSimulada
from obr_oficial.dispositivos.metricas_imagem import calcular_metricas_imagem


def _quadro(id_quadro: int, valor: int = 127) -> QuadroCamera:
    imagem = np.full((24, 32, 3), valor, dtype=np.uint8)
    return QuadroCamera(
        id_quadro=id_quadro,
        instante_monotonico_s=float(id_quadro),
        instante_utc="2026-08-18T00:00:00+00:00",
        imagem_bgr=imagem,
        metricas=MetricasImagem(127.0, 0.0, 0.0, 0.0),
    )


def test_buffer_descarta_quadro_antigo_e_entrega_copia() -> None:
    buffer = BufferUltimoQuadro()
    buffer.publicar(_quadro(1, 10))
    buffer.publicar(_quadro(2, 20))

    resultado = buffer.obter()

    assert resultado is not None
    assert resultado.id_quadro == 2
    resultado.imagem_bgr[:] = 99
    preservado = buffer.obter()
    assert preservado is not None
    assert int(preservado.imagem_bgr[0, 0, 0]) == 20


def test_buffer_respeita_id_minimo_sem_bloquear() -> None:
    buffer = BufferUltimoQuadro()
    buffer.publicar(_quadro(3))

    assert buffer.obter(depois_de=3) is None


def test_metricas_identificam_imagem_totalmente_clara() -> None:
    imagem = np.full((40, 50, 3), 255, dtype=np.uint8)

    metricas = calcular_metricas_imagem(imagem)

    assert metricas.brilho_medio == pytest.approx(255.0)
    assert metricas.percentual_claro == pytest.approx(100.0)
    assert metricas.percentual_escuro == pytest.approx(0.0)


def test_camera_simulada_entrega_quadros_e_fps() -> None:
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    camera.iniciar()
    try:
        primeiro = camera.obter_ultimo_quadro()
        assert primeiro is not None
        segundo = camera.obter_ultimo_quadro(depois_de=primeiro.id_quadro, timeout_s=0.3)
        assert segundo is not None
        assert segundo.id_quadro > primeiro.id_quadro
        sleep(0.06)
        estado = camera.obter_estado()
        assert estado.saudavel
        assert estado.largura == 160
        assert estado.altura == 120
    finally:
        camera.parar()
