from __future__ import annotations

from pathlib import Path

import numpy as np

from obr_oficial.dispositivos import CameraSimulada
from obr_oficial.painel.operacao import GerenciadorViradas, criar_painel_operacao
from obr_oficial.painel.operacao.persistencia import valores_iniciais
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
        self.logits = np.log(probabilidade / (1.0 - probabilidade))[None, None].astype(np.float32)
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


def _pipeline_percepcao(camera: CameraSimulada, tmp_path: Path) -> ProcessadorContinuoLinha:
    configuracao = _configuracao(tmp_path)
    detector = DetectorNeuralLinha(configuracao, sessao=_SessaoLinhaReta())
    rastreador = RastreadorLinha(configuracao)
    return ProcessadorContinuoLinha(camera, detector, rastreador)


def _montar_painel_completo(
    camera: CameraSimulada,
    tmp_path: Path,
) -> tuple[ProcessadorContinuoLinha, object]:
    processador = _pipeline_percepcao(camera, tmp_path)
    gerenciador = GerenciadorViradas(tmp_path / "viradas.toml")
    painel = criar_painel_operacao(camera, processador, gerenciador)
    return processador, painel


def test_pagina_e_estado_inicial_sem_comandos(tmp_path: Path) -> None:
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    processador, painel = _montar_painel_completo(camera, tmp_path)
    camera.iniciar()
    processador.iniciar()
    try:
        primeiro = processador.obter_ultimo_resultado(timeout_s=2.0)
        assert primeiro is not None
        assert (
            processador.obter_ultimo_resultado(
                depois_de=primeiro.id_quadro,
                timeout_s=2.0,
            )
            is not None
        )
        cliente = painel.test_client()

        pagina = cliente.get("/")
        assert pagina.status_code == 200
        assert pagina.headers["Cache-Control"] == "no-store"
        corpo = pagina.get_data(as_text=True)
        assert 'id="cronometro"' in corpo
        assert "/painel.css" in corpo
        assert "CAM/DISP 0" in corpo
        assert "CAM/DISP 1" in corpo

        assert cliente.get("/painel.js").headers["Cache-Control"] == "no-store"
        assert cliente.get("/painel.css").headers["Cache-Control"] == "no-store"
        estado = cliente.get("/api/estado").get_json()
        assert estado["ok"] is True
        assert estado["modo_percepcao"] is True
        assert estado["viradas"]["esquerda.giro_ms"] == 0
        assert estado["percepcao"]["estimativa"]["estado"] == "encontrada"
        assert estado["sistema"]["tempo_ativo_s"] >= 0
        assert set(estado["sistema"]["raspberry"]) == {
            "tensao_nucleo_v",
            "subtensao_atual",
            "subtensao_ocorreu",
            "temperatura_cpu_c",
            "memoria_disponivel_mb",
        }
    finally:
        processador.parar()
        camera.parar()


def test_video_mjpeg_entrega_blocos_jpeg(tmp_path: Path) -> None:
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    processador, painel = _montar_painel_completo(camera, tmp_path)
    camera.iniciar()
    processador.iniciar()
    try:
        primeiro = processador.obter_ultimo_resultado(timeout_s=2.0)
        assert primeiro is not None
        cliente = painel.test_client()
        resposta = cliente.get("/video.mjpg", buffered=False)
        primeiro_bloco = next(resposta.response)
        assert b"Content-Type: image/jpeg" in primeiro_bloco
        resposta.close()
    finally:
        processador.parar()
        camera.parar()


def test_video_bruto_funciona_sem_processador(tmp_path: Path) -> None:
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    gerenciador = GerenciadorViradas(tmp_path / "viradas.toml")
    painel = criar_painel_operacao(camera, None, gerenciador)
    camera.iniciar()
    try:
        cliente = painel.test_client()
        estado = cliente.get("/api/estado").get_json()
        assert estado["modo_percepcao"] is False
        assert estado["percepcao"] is None

        resposta = cliente.get("/video.mjpg", buffered=False)
        primeiro_bloco = next(resposta.response)
        assert b"Content-Type: image/jpeg" in primeiro_bloco
        resposta.close()
    finally:
        camera.parar()


def test_viradas_valida_limitas_persiste_e_rejeita(tmp_path: Path) -> None:
    caminho_arquivo = tmp_path / "configuracoes" / "viradas.toml"
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    gerenciador = GerenciadorViradas(caminho_arquivo)
    painel = criar_painel_operacao(camera, None, gerenciador)
    camera.iniciar()
    try:
        cliente = painel.test_client()

        listagem = cliente.get("/api/viradas").get_json()
        assert listagem["ok"] is True
        assert listagem["atuadores_habilitados"] is False
        grupos = {grupo["id"]: grupo for grupo in listagem["grupos"]}
        assert set(grupos) == {"esquerda", "direita", "verde", "verde90", "gap"}
        esquerda = {campo["campo"]: campo for campo in grupos["esquerda"]["campos"]}
        assert esquerda["giro_ms"]["minimo_ms"] == 0
        assert esquerda["giro_ms"]["maximo_ms"] == 4000
        assert esquerda["giro_ms"]["valor_ms"] == 0
        gap = {campo["campo"]: campo for campo in grupos["gap"]["campos"]}
        assert set(gap) == {"avanco_ms", "confirmacao_ms"}
        assert gap["avanco_ms"]["valor_ms"] == 0

        aceito = cliente.post(
            "/api/viradas/esquerda/giro_ms",
            json={"valor": 2100},
        )
        assert aceito.status_code == 200
        documento = aceito.get_json()
        assert documento == {
            "ok": True,
            "chave": "esquerda.giro_ms",
            "valor_ms": 2100,
        }
        assert caminho_arquivo.is_file()

        rejeitado_acima = cliente.post(
            "/api/viradas/esquerda/giro_ms",
            json={"valor": 9999},
        )
        assert rejeitado_acima.status_code == 400
        assert rejeitado_acima.get_json()["ok"] is False

        desconhecido = cliente.post("/api/viradas/esquerda/inexistente", json={"valor": 10})
        assert desconhecido.status_code == 400

        sem_corpo = cliente.post("/api/viradas/esquerda/giro_ms")
        assert sem_corpo.status_code == 400

        recarregado = GerenciadorViradas(caminho_arquivo)
        assert recarregado.como_dict()["esquerda.giro_ms"] == 2100
        indefinidos = [
            chave for chave, valor in valores_iniciais().items() if chave != "esquerda.giro_ms"
        ]
        assert all(recarregado.como_dict()[chave] == 0 for chave in indefinidos)
    finally:
        camera.parar()


def test_endpoint_controle_manual(tmp_path: Path) -> None:
    camera = CameraSimulada(largura=160, altura=120, fps=20.0)
    _processador, painel = _montar_painel_completo(camera, tmp_path)
    cliente = painel.test_client()

    for acao in ("avancar", "parar", "recuar", "led_on", "led_off"):
        resp = cliente.post(f"/api/controle/{acao}")
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True, "comando": acao}

    invalido = cliente.post("/api/controle/voar")
    assert invalido.status_code == 400
    assert invalido.get_json()["ok"] is False
