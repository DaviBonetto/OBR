from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import cv2
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
from obr_oficial.percepcao.linha.execucao_continua import (
    _desenhar_contorno_mascara,
    _desenhar_marcador,
    _eh_cotovelo_ortogonal,
    _extrair_rota_visual,
)


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
    assert configuracao.limiar_mascara_visual == 0.55
    assert configuracao.roi_y == 0.3
    assert configuracao.quantidade_faixas == 24
    assert configuracao.quantidade_faixas_intersecao == 40
    assert configuracao.fator_largura_intersecao == 2.2
    assert configuracao.faixas_continuacao_intersecao == 8
    assert configuracao.tolerancia_alinhamento_intersecao == 0.08
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


@pytest.mark.parametrize(
    ("lado", "tipo_esperado"),
    (
        ("direita", TipoCurva.DIREITA_FECHADA),
        ("esquerda", TipoCurva.ESQUERDA_FECHADA),
    ),
)
def test_curva_em_l_nao_e_confundida_com_t(
    tmp_path: Path,
    lado: str,
    tipo_esperado: TipoCurva,
) -> None:
    probabilidade = np.full((192, 320), 0.02, dtype=np.float32)
    probabilidade[72:, 150:170] = 0.97
    if lado == "direita":
        probabilidade[64:84, 160:320] = 0.97
    else:
        probabilidade[64:84, 0:160] = 0.97
    extrator = ExtratorGeometriaLinha(_configuracao(tmp_path))

    _mascara, estimativa, diagnostico = extrator.extrair(
        probabilidade,
        id_quadro=12,
        instante_monotonico_s=3.0,
    )

    assert diagnostico.intersecao_detectada is False
    assert estimativa.tipo_curva is tipo_esperado
    assert estimativa.motivo == "evidencia_neural_atual"


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
    def __init__(self, logits: np.ndarray | tuple[np.ndarray, ...]) -> None:
        self.logits = (logits,) if isinstance(logits, np.ndarray) else logits
        self.ultima_entrada: np.ndarray | None = None
        self.entradas: list[np.ndarray] = []

    def run(self, saidas, entradas):
        assert saidas == ["logits"]
        self.ultima_entrada = entradas["imagem"]
        self.entradas.append(self.ultima_entrada.copy())
        indice = min(len(self.entradas) - 1, len(self.logits) - 1)
        return [self.logits[indice]]


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
    assert len(sessao.entradas) == 2
    assert resultado.mascara_quadro.shape == (480, 640)
    assert np.count_nonzero(resultado.mascara_quadro[0]) > 0
    assert np.count_nonzero(resultado.mascara_quadro[-1]) > 0


def test_mascara_quadro_descarta_mancha_superior_desconectada(tmp_path: Path) -> None:
    probabilidade_superior = np.full((192, 320), 0.02, dtype=np.float32)
    probabilidade_superior[5:45, 20:65] = 0.97
    probabilidade_inferior = _probabilidade_reta()
    logits_superiores = np.log(
        probabilidade_superior / (1.0 - probabilidade_superior)
    )[None, None].astype(np.float32)
    logits_inferiores = np.log(
        probabilidade_inferior / (1.0 - probabilidade_inferior)
    )[None, None].astype(np.float32)
    detector = DetectorNeuralLinha(
        _configuracao(tmp_path),
        sessao=_SessaoFalsa((logits_superiores, logits_inferiores)),
    )

    resultado = detector.processar(
        np.full((480, 640, 3), 180, dtype=np.uint8),
        id_quadro=34,
        instante_monotonico_s=4.1,
    )

    assert np.count_nonzero(resultado.mascara_quadro[:100, :150]) == 0
    assert np.count_nonzero(resultado.mascara_quadro[150:, 290:350]) > 0


def test_contorno_aberto_nas_bordas_e_fechado_no_interior() -> None:
    regiao = np.full((120, 160, 3), 180, dtype=np.uint8)
    original = regiao.copy()
    mascara = np.zeros((120, 160), dtype=np.uint8)
    mascara[:, 60:100] = 255
    mascara[30:80, 15:35] = 255

    _desenhar_contorno_mascara(regiao, mascara)

    # O componente que sai do quadro conserva apenas suas laterais: nao ha
    # uma tampa colorida atravessando a moldura superior ou inferior.
    assert np.array_equal(regiao[0, 68:92], original[0, 68:92])
    assert np.array_equal(regiao[-1, 68:92], original[-1, 68:92])
    assert np.count_nonzero(regiao[20:100, 57:64] != original[20:100, 57:64]) > 0
    assert np.count_nonzero(regiao[20:100, 97:104] != original[20:100, 97:104]) > 0
    assert np.array_equal(regiao[60, 75], original[60, 75])

    # Um componente totalmente interno continua com o contorno completo e
    # tambem nao recebe preenchimento.
    assert np.count_nonzero(regiao[27:34, 15:35] != original[27:34, 15:35]) > 0
    assert np.array_equal(regiao[50, 25], original[50, 25])


def test_rota_visual_percorre_curva_de_90_graus() -> None:
    mascara = np.zeros((480, 640), dtype=np.uint8)
    mascara[:360, 440:540] = 255
    mascara[260:360, 80:540] = 255

    rota = _extrair_rota_visual(mascara, intersecao_t=False)

    assert rota is not None
    assert rota.tolist() == [[320, 310], [490, 310], [490, 14]]
    assert len(rota) == 3
    assert rota[0, 1] > 250
    assert rota[-1, 1] < 30
    assert np.ptp(rota[:, 0]) > 100
    assert np.ptp(rota[:, 1]) > 250
    assert abs(int(rota[0, 1]) - int(rota[1, 1])) <= 2
    assert abs(int(rota[1, 0]) - int(rota[2, 0])) <= 2
    assert _eh_cotovelo_ortogonal(rota)
    assert all(mascara[y, x] > 0 for x, y in rota)


def test_rota_visual_do_t_permanece_reta() -> None:
    mascara = np.zeros((480, 640), dtype=np.uint8)
    mascara[:, 285:355] = 255
    mascara[150:230, 45:600] = 255

    rota = _extrair_rota_visual(mascara, intersecao_t=True)

    assert rota is not None
    assert len(rota) == 2
    assert rota[0, 1] > 450
    assert rota[-1, 1] < 30
    assert abs(int(rota[0, 0]) - int(rota[-1, 0])) <= 8


def test_rota_visual_reta_centraliza_bolinha_atual() -> None:
    mascara = np.zeros((480, 640), dtype=np.uint8)
    mascara[:, 200:380] = 255

    rota = _extrair_rota_visual(mascara, intersecao_t=False)

    assert rota is not None
    assert abs(int(rota[0, 0]) - 290) <= 2
    assert np.max(np.abs(rota[:, 0] - 290)) <= 2


def test_rota_visual_curva_aberta_centraliza_bolinha_atual() -> None:
    mascara = np.zeros((480, 640), dtype=np.uint8)
    centros = np.asarray(((260, 479), (270, 360), (300, 240), (340, 120), (360, 0)))
    cv2.polylines(mascara, [centros], False, 255, 90, cv2.LINE_AA)

    rota = _extrair_rota_visual(mascara, intersecao_t=False)

    assert rota is not None
    x_atual, y_atual = rota[0]
    intervalo = np.flatnonzero(mascara[y_atual] > 0)
    centro_real = 0.5 * (int(intervalo[0]) + int(intervalo[-1]))
    assert abs(float(x_atual) - centro_real) <= 2.0
    assert not _eh_cotovelo_ortogonal(rota)


def test_rota_visual_do_t_centraliza_tronco_sem_entrar_no_ramo() -> None:
    mascara = np.zeros((480, 640), dtype=np.uint8)
    mascara[:220, 200:320] = 255
    mascara[150:250, 100:600] = 255
    mascara[220:, 120:300] = 255

    rota = _extrair_rota_visual(mascara, intersecao_t=True)

    assert rota is not None
    assert len(rota) == 2
    assert abs(int(rota[0, 0]) - 210) <= 2
    assert abs(int(rota[-1, 0]) - 260) <= 2
    assert rota[0, 1] > 450
    assert rota[-1, 1] < 30


def test_rota_visual_nao_inventa_cotovelo_em_linha_diagonal() -> None:
    mascara = np.zeros((480, 640), dtype=np.uint8)
    cv2.line(mascara, (280, 479), (470, 0), 255, 90)

    rota = _extrair_rota_visual(mascara, intersecao_t=False)

    assert rota is not None
    assert not _eh_cotovelo_ortogonal(rota)


def test_marcador_minimalista_nao_esconde_a_linha() -> None:
    imagem = np.full((60, 60, 3), 180, dtype=np.uint8)
    original = imagem.copy()

    _desenhar_marcador(imagem, (30, 30), (255, 230, 0))

    alterados = np.argwhere(np.any(imagem != original, axis=2))
    raios = np.linalg.norm(alterados - np.array([30, 30]), axis=1)
    assert float(np.max(raios)) <= 9.5
    assert tuple(int(canal) for canal in imagem[30, 30]) == (255, 230, 0)


def test_sobreposicao_suave_nao_altera_mascara_logica(tmp_path: Path) -> None:
    configuracao = _configuracao(tmp_path)
    probabilidade = _probabilidade_reta()
    logits = np.log(probabilidade / (1.0 - probabilidade))[None, None].astype(np.float32)
    detector = DetectorNeuralLinha(configuracao, sessao=_SessaoFalsa(logits))
    imagem = np.full((480, 640, 3), 180, dtype=np.uint8)
    resultado = detector.processar(imagem, id_quadro=50, instante_monotonico_s=40.0)
    mascara_original = resultado.mascara.copy()
    mascara_quadro_original = resultado.mascara_quadro.copy()

    visual = desenhar_sobreposicao(
        imagem,
        resultado,
        resultado.estimativa,
        configuracao,
    )

    assert np.array_equal(resultado.mascara, mascara_original)
    assert np.array_equal(resultado.mascara_quadro, mascara_quadro_original)
    assert np.array_equal(visual[20, 20], imagem[20, 20])
    assert visual.shape == imagem.shape
    assert np.array_equal(visual[250, 330], imagem[250, 330])

    # A mascara visual agora cobre o quadro inteiro; as laterais da linha
    # aparecem tanto no topo quanto na base sem fechar a linha na moldura.
    assert np.count_nonzero(visual[0:80, 294:307] != imagem[0:80, 294:307]) > 30
    assert np.count_nonzero(visual[400:480, 294:307] != imagem[400:480, 294:307]) > 30
    assert np.array_equal(visual[0, 307:333], imagem[0, 307:333])

    borda_distante = visual[170:350, 294:307]
    pixels_distantes = (
        (borda_distante[..., 0] > 220)
        & (borda_distante[..., 1] < 130)
        & (borda_distante[..., 2] < 160)
    )
    borda_proxima = visual[400:455, 294:307]
    pixels_proximos = (
        (borda_proxima[..., 0] > 220)
        & (borda_proxima[..., 1] > 180)
        & (borda_proxima[..., 2] < 80)
    )
    assert np.count_nonzero(pixels_distantes) > 100
    assert np.count_nonzero(pixels_proximos) > 30
    rota = _extrair_rota_visual(resultado.mascara_quadro, intersecao_t=False)
    assert rota is not None
    atual_x, atual_y = rota[0]
    objetivo_x, objetivo_y = rota[-1]
    assert tuple(int(canal) for canal in visual[atual_y, atual_x]) == (255, 230, 0)
    assert tuple(int(canal) for canal in visual[objetivo_y, objetivo_x]) == (165, 55, 10)
