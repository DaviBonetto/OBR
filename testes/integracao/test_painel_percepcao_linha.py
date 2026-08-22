from __future__ import annotations

from pathlib import Path

import numpy as np

from obr_oficial.dispositivos import CameraSimulada
from obr_oficial.painel import criar_painel_percepcao_linha
from obr_oficial.percepcao.linha import (
    ConfiguracaoDetectorNeural,
    DetectorNeuralLinha,
    ProcessadorContinuoLinha,
    RastreadorLinha,
)


class _SessaoLinhaReta:
    def __init__(self) -> None:
        probabilidade = np.full((192, 320), 0.02, dtype=np.float32)
        probabilidade[:, 150:170] = 0.97
        self.logits = np.log(probabilidade / (1.0 - probabilidade))[None, None].astype(
            np.float32
        )
        self.chamadas = 0

    def run(self, _saidas, _entradas):
        self.chamadas += 1
        return [self.logits]


def _configuracao(tmp_path: Path) -> ConfiguracaoDetectorNeural:
    return ConfiguracaoDetectorNeural(
        arquivo_modelo=tmp_path / "modelo.onnx",
        sha256_modelo="0" * 64,
        largura=320,
        altura=192,
        roi_y=0.3,
        limiar_mascara=0.8,
        limiar_mascara_visual=0.55,
        quantidade_faixas=24,
        altura_faixa=5,
        cobertura_minima=0.2,
        fator_largura_intersecao=2.2,
        quantidade_faixas_intersecao=40,
        faixas_continuacao_intersecao=8,
        tolerancia_alinhamento_intersecao=0.08,
        distancia_objetivo_reta=0.42,
        distancia_objetivo_curva=0.25,
        angulo_reta_graus=6.0,
        angulo_curva_fechada_graus=24.0,
        limiar_encontrada=0.75,
        limiar_incerta=0.45,
        suavizacao=0.55,
        quadros_confirmacao=2,
        idade_maxima_temporal_ms=120.0,
    )


def test_dashboard_observa_ultimo_resultado_sem_comandos(tmp_path: Path) -> None:
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    configuracao = _configuracao(tmp_path)
    sessao = _SessaoLinhaReta()
    detector = DetectorNeuralLinha(configuracao, sessao=sessao)
    processador = ProcessadorContinuoLinha(camera, detector, RastreadorLinha(configuracao))
    camera.iniciar()
    processador.iniciar()
    try:
        primeiro = processador.obter_ultimo_resultado(timeout_s=2.0)
        assert primeiro is not None
        segundo = processador.obter_ultimo_resultado(
            depois_de=primeiro.id_quadro,
            timeout_s=2.0,
        )
        assert segundo is not None
        assert segundo.estimativa.estado.value == "encontrada"
        app = criar_painel_percepcao_linha(camera, processador)
        cliente = app.test_client()

        pagina = cliente.get("/")
        assert pagina.status_code == 200
        assert "Percepção da linha" in pagina.get_data(as_text=True)

        resposta = cliente.get("/api/estado")
        assert resposta.status_code == 200
        estado = resposta.get_json()
        assert estado["somente_leitura"] is True
        assert estado["atuadores_habilitados"] is False
        assert estado["percepcao"]["estimativa"]["estado"] == "encontrada"
        assert estado["processador"]["total_processados"] >= 1
        assert sessao.chamadas >= 4

        video = cliente.get("/video-linha.mjpg", buffered=False)
        primeiro_bloco = next(video.response)
        assert b"Content-Type: image/jpeg" in primeiro_bloco
        video.close()

        assert cliente.post("/api/comandos", json={}).status_code == 404
    finally:
        processador.parar()
        camera.parar()
