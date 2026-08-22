from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from obr_oficial.nucleo.contratos import (
    EstadoDeteccao,
    FonteEstimativa,
    PontoNormalizado,
    TipoCurva,
)
from obr_oficial.percepcao.linha import (
    ConfiguracaoDetectorNeural,
    DetectorNeuralLinha,
    ExtratorGeometriaLinha,
    RastreadorLinha,
    carregar_configuracao_detector_neural,
    desenhar_sobreposicao,
    preprocessar_quadro,
)


def _configuracao(tmp_path: Path) -> ConfiguracaoDetectorNeural:
    return ConfiguracaoDetectorNeural(
        arquivo_modelo=tmp_path / "modelo.onnx",
        sha256_modelo="0" * 64,
        largura=320,
        altura=192,
        roi_y=0.3,
        limiar_mascara=0.8,
        quantidade_faixas=24,
        altura_faixa=5,
        cobertura_minima=0.2,
        fator_largura_intersecao=1.8,
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


def _probabilidade_reta() -> np.ndarray:
    probabilidade = np.full((192, 320), 0.02, dtype=np.float32)
    probabilidade[:, 150:170] = 0.97
    return probabilidade


def test_carrega_configuracao_oficial() -> None:
    raiz_projeto = Path(__file__).resolve().parents[2]
    configuracao = carregar_configuracao_detector_neural(
        raiz_projeto / "configuracoes" / "percepcao_linha_neural.toml",
        raiz=raiz_projeto,
    )

    assert configuracao.limiar_mascara == 0.8
    assert configuracao.roi_y == 0.3
    assert configuracao.arquivo_modelo == (
        raiz_projeto / "modelos" / "linha" / "lraspp_v2" / "modelo.onnx"
    ).resolve()


def test_preprocessamento_tem_forma_e_tipo_congelados(tmp_path: Path) -> None:
    quadro = np.full((480, 640, 3), 127, dtype=np.uint8)

    entrada = preprocessar_quadro(quadro, _configuracao(tmp_path))

    assert entrada.shape == (1, 3, 192, 320)
    assert entrada.dtype == np.float32
    assert entrada.flags.c_contiguous


def test_extrai_reta_com_pontos_atual_e_objetivo(tmp_path: Path) -> None:
    extrator = ExtratorGeometriaLinha(_configuracao(tmp_path))

    _mascara, estimativa, diagnostico = extrator.extrair(
        _probabilidade_reta(),
        id_quadro=10,
        instante_monotonico_s=1.0,
    )

    assert estimativa.estado is EstadoDeteccao.ENCONTRADA
    assert estimativa.tipo_curva is TipoCurva.RETA
    assert estimativa.ponto_atual is not None
    assert estimativa.ponto_objetivo is not None
    assert estimativa.ponto_atual.x == pytest.approx(0.5, abs=0.01)
    assert estimativa.ponto_objetivo.y < estimativa.ponto_atual.y
    assert diagnostico.cobertura_faixas == 1.0


def test_intersecao_t_preserva_continuacao_frontal(tmp_path: Path) -> None:
    probabilidade = _probabilidade_reta()
    probabilidade[65:82, 25:295] = 0.97
    extrator = ExtratorGeometriaLinha(_configuracao(tmp_path))

    _mascara, estimativa, diagnostico = extrator.extrair(
        probabilidade,
        id_quadro=11,
        instante_monotonico_s=2.0,
    )

    assert diagnostico.intersecao_detectada is True
    assert estimativa.tipo_curva is TipoCurva.RETA
    assert estimativa.ponto_atual is not None
    assert estimativa.ponto_objetivo is not None
    assert estimativa.ponto_objetivo.x == pytest.approx(estimativa.ponto_atual.x)
    assert estimativa.motivo == "intersecao_t_continuacao_reta"


def test_classifica_curva_para_direita(tmp_path: Path) -> None:
    probabilidade = np.full((192, 320), 0.02, dtype=np.float32)
    for y in range(192):
        progresso = 1.0 - y / 191.0
        centro = round(160 + 90 * progresso**2)
        probabilidade[y, centro - 9 : centro + 10] = 0.97
    extrator = ExtratorGeometriaLinha(_configuracao(tmp_path))

    _mascara, estimativa, _diagnostico = extrator.extrair(
        probabilidade,
        id_quadro=12,
        instante_monotonico_s=3.0,
    )

    assert estimativa.tipo_curva in {TipoCurva.DIREITA_SUAVE, TipoCurva.DIREITA_FECHADA}
    assert estimativa.erro_angular_graus is not None
    assert estimativa.erro_angular_graus > 0


def test_recusa_fragmento_com_baixa_cobertura(tmp_path: Path) -> None:
    probabilidade = np.full((192, 320), 0.02, dtype=np.float32)
    probabilidade[170:192, 150:170] = 0.99
    extrator = ExtratorGeometriaLinha(_configuracao(tmp_path))

    _mascara, estimativa, diagnostico = extrator.extrair(
        probabilidade,
        id_quadro=13,
        instante_monotonico_s=3.5,
    )

    assert diagnostico.cobertura_faixas < 0.2
    assert estimativa.estado is EstadoDeteccao.PERDIDA


def test_gap_temporal_expira_sem_fingir_evidencia(tmp_path: Path) -> None:
    configuracao = _configuracao(tmp_path)
    extrator = ExtratorGeometriaLinha(configuracao)
    rastreador = RastreadorLinha(configuracao)
    _mascara, valida, _diagnostico = extrator.extrair(
        _probabilidade_reta(),
        id_quadro=20,
        instante_monotonico_s=10.0,
    )
    _mascara, perdida, _diagnostico = extrator.extrair(
        np.zeros((192, 320), dtype=np.float32),
        id_quadro=21,
        instante_monotonico_s=10.05,
    )

    primeira = rastreador.atualizar(valida)
    confirmada = rastreador.atualizar(
        replace(valida, id_quadro=21, instante_monotonico_s=10.01)
    )
    temporal = rastreador.atualizar(perdida)
    expirada = rastreador.atualizar(replace(perdida, id_quadro=22, instante_monotonico_s=10.2))

    assert primeira.estado is EstadoDeteccao.INCERTA
    assert confirmada.estado is EstadoDeteccao.ENCONTRADA
    assert temporal.estado is EstadoDeteccao.INCERTA
    assert temporal.fonte is FonteEstimativa.TEMPORAL
    assert temporal.idade_observacao_ms == pytest.approx(40.0)
    assert expirada.estado is EstadoDeteccao.PERDIDA
    assert expirada.fonte is FonteEstimativa.NENHUMA


def test_sombra_isolada_nao_vira_rota_encontrada(tmp_path: Path) -> None:
    configuracao = _configuracao(tmp_path)
    extrator = ExtratorGeometriaLinha(configuracao)
    rastreador = RastreadorLinha(configuracao)
    _mascara, sombra, _diagnostico = extrator.extrair(
        _probabilidade_reta(),
        id_quadro=30,
        instante_monotonico_s=20.0,
    )
    _mascara, vazia, _diagnostico = extrator.extrair(
        np.zeros((192, 320), dtype=np.float32),
        id_quadro=31,
        instante_monotonico_s=20.04,
    )

    candidata = rastreador.atualizar(sombra)
    perdida = rastreador.atualizar(vazia)

    assert candidata.estado is EstadoDeteccao.INCERTA
    assert candidata.motivo == "aguardando_confirmacao_temporal"
    assert perdida.estado is EstadoDeteccao.PERDIDA


def test_suavizacao_adaptativa_estabiliza_jitter_e_responde_a_curva(tmp_path: Path) -> None:
    configuracao = _configuracao(tmp_path)
    extrator = ExtratorGeometriaLinha(configuracao)
    rastreador = RastreadorLinha(configuracao)
    _mascara, base, _diagnostico = extrator.extrair(
        _probabilidade_reta(),
        id_quadro=40,
        instante_monotonico_s=30.0,
    )
    rastreador.atualizar(base)
    rastreador.atualizar(replace(base, id_quadro=41, instante_monotonico_s=30.01))

    jitter = rastreador.atualizar(
        replace(
            base,
            id_quadro=42,
            instante_monotonico_s=30.02,
            ponto_atual=PontoNormalizado(0.51, base.ponto_atual.y),
            ponto_objetivo=PontoNormalizado(0.51, base.ponto_objetivo.y),
        )
    )
    assert jitter.ponto_atual is not None
    assert 0.5 < jitter.ponto_atual.x < 0.505

    curva = rastreador.atualizar(
        replace(
            base,
            id_quadro=43,
            instante_monotonico_s=30.03,
            ponto_atual=PontoNormalizado(0.75, base.ponto_atual.y),
            ponto_objetivo=PontoNormalizado(0.75, base.ponto_objetivo.y),
        )
    )
    assert curva.ponto_atual is not None
    assert curva.ponto_atual.x > 0.68


class _SessaoFalsa:
    def __init__(self, logits: np.ndarray) -> None:
        self.logits = logits
        self.ultima_entrada: np.ndarray | None = None

    def run(self, saidas, entradas):
        assert saidas == ["logits"]
        self.ultima_entrada = entradas["imagem"]
        return [self.logits]


def test_detector_executa_sessao_injetada(tmp_path: Path) -> None:
    probabilidade = _probabilidade_reta()
    logits = np.log(probabilidade / (1.0 - probabilidade))[None, None].astype(np.float32)
    sessao = _SessaoFalsa(logits)
    detector = DetectorNeuralLinha(_configuracao(tmp_path), sessao=sessao)

    resultado = detector.processar(
        np.full((480, 640, 3), 180, dtype=np.uint8),
        id_quadro=33,
        instante_monotonico_s=4.0,
    )

    assert resultado.estimativa.id_quadro == 33
    assert resultado.estimativa.estado is EstadoDeteccao.ENCONTRADA
    assert sessao.ultima_entrada is not None
    assert sessao.ultima_entrada.shape == (1, 3, 192, 320)


def test_sobreposicao_suave_nao_altera_mascara_logica(tmp_path: Path) -> None:
    configuracao = _configuracao(tmp_path)
    probabilidade = _probabilidade_reta()
    logits = np.log(probabilidade / (1.0 - probabilidade))[None, None].astype(np.float32)
    detector = DetectorNeuralLinha(configuracao, sessao=_SessaoFalsa(logits))
    imagem = np.full((480, 640, 3), 180, dtype=np.uint8)
    resultado = detector.processar(imagem, id_quadro=50, instante_monotonico_s=40.0)
    mascara_original = resultado.mascara.copy()

    visual = desenhar_sobreposicao(
        imagem,
        resultado,
        resultado.estimativa,
        configuracao,
    )

    assert np.array_equal(resultado.mascara, mascara_original)
    assert np.array_equal(visual[20, 20], imagem[20, 20])
    assert visual.shape == imagem.shape
    assert int(visual[170, 335, 0]) > int(visual[170, 335, 2])
    assert int(visual[440, 335, 1]) > int(visual[170, 335, 1])
    assert tuple(int(canal) for canal in visual[479, 319]) == (255, 255, 255)
