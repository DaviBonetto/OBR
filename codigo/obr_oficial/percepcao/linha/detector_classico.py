"""Baseline classico explicavel para segmentar e localizar a linha preta."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2
import numpy as np

from obr_oficial.nucleo.configuracao import carregar_toml, exigir_secao
from obr_oficial.nucleo.contratos import (
    EstadoDeteccao,
    EstimativaLinha,
    FonteEstimativa,
    PontoNormalizado,
    TemposProcessamento,
    TipoCurva,
)


class ErroDetectorClassico(ValueError):
    """Indica configuracao ou entrada invalida do detector."""


@dataclass(frozen=True, slots=True)
class ConfiguracaoDetectorClassico:
    """Parametros versionados do baseline, independentes da camera fisica."""

    largura: int
    altura: int
    roi_y: float
    roi_altura: float
    limite_clahe: float
    grade_clahe: int
    bloco_adaptativo: int
    constante_adaptativa: float
    kernel_abertura: int
    kernel_fechamento: int
    area_minima: float
    area_maxima: float
    altura_minima: float
    nitidez_borda_minima: float
    confianca_encontrada: float
    confianca_incerta: float
    linhas_centro: int
    fator_largura_intersecao: float

    def __post_init__(self) -> None:
        if self.largura < 32 or self.altura < 32:
            raise ErroDetectorClassico("Resolucao do detector deve ser ao menos 32x32")
        if not 0.0 <= self.roi_y < 1.0 or not 0.0 < self.roi_altura <= 1.0:
            raise ErroDetectorClassico("ROI deve estar normalizada")
        if self.roi_y + self.roi_altura > 1.0:
            raise ErroDetectorClassico("ROI ultrapassa a imagem")
        if self.grade_clahe < 1:
            raise ErroDetectorClassico("grade_clahe deve ser positiva")
        for nome in ("kernel_abertura", "kernel_fechamento"):
            valor = getattr(self, nome)
            if valor < 1 or valor % 2 == 0:
                raise ErroDetectorClassico(f"{nome} deve ser impar e positivo")
        if self.bloco_adaptativo < 3 or self.bloco_adaptativo % 2 == 0:
            raise ErroDetectorClassico("bloco_adaptativo deve ser impar e >= 3")
        if not 0.0 < self.area_minima < self.area_maxima < 1.0:
            raise ErroDetectorClassico("Limites de area devem estar entre zero e um")
        if not 0.0 < self.altura_minima <= 1.0:
            raise ErroDetectorClassico("altura_minima deve estar entre zero e um")
        if self.nitidez_borda_minima < 0.0:
            raise ErroDetectorClassico("nitidez_borda_minima nao pode ser negativa")
        if not 0.0 <= self.confianca_incerta < self.confianca_encontrada <= 1.0:
            raise ErroDetectorClassico("Limiares de confianca invalidos")
        if self.linhas_centro < 2:
            raise ErroDetectorClassico("linhas_centro deve ser >= 2")
        if self.fator_largura_intersecao <= 1.0:
            raise ErroDetectorClassico("fator_largura_intersecao deve ser > 1")


@dataclass(frozen=True, slots=True)
class ResultadoDetectorClassico:
    """Saida completa do baseline para auditoria, painel e rotulacao assistida."""

    mascara: np.ndarray
    estimativa: EstimativaLinha
    area_normalizada: float
    altura_normalizada: float
    contato_inferior: float
    brilho_linha: float | None
    nitidez_borda: float


def _numero(secao: dict[str, Any], nome: str, tipo: type[int] | type[float]) -> Any:
    valor = secao.get(nome)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroDetectorClassico(f"Parametro ausente ou invalido: {nome}")
    return tipo(valor)


def carregar_configuracao_detector_classico(caminho: Path) -> ConfiguracaoDetectorClassico:
    """Carrega e valida o arquivo TOML do baseline classico."""

    dados = carregar_toml(caminho)
    entrada = exigir_secao(dados, "entrada")
    segmento = exigir_secao(dados, "segmentacao")
    componente = exigir_secao(dados, "componente")
    geometria = exigir_secao(dados, "geometria")
    return ConfiguracaoDetectorClassico(
        largura=_numero(entrada, "largura", int),
        altura=_numero(entrada, "altura", int),
        roi_y=_numero(entrada, "roi_y", float),
        roi_altura=_numero(entrada, "roi_altura", float),
        limite_clahe=_numero(segmento, "limite_clahe", float),
        grade_clahe=_numero(segmento, "grade_clahe", int),
        bloco_adaptativo=_numero(segmento, "bloco_adaptativo", int),
        constante_adaptativa=_numero(segmento, "constante_adaptativa", float),
        kernel_abertura=_numero(segmento, "kernel_abertura", int),
        kernel_fechamento=_numero(segmento, "kernel_fechamento", int),
        area_minima=_numero(componente, "area_minima", float),
        area_maxima=_numero(componente, "area_maxima", float),
        altura_minima=_numero(componente, "altura_minima", float),
        nitidez_borda_minima=_numero(componente, "nitidez_borda_minima", float),
        confianca_encontrada=_numero(componente, "confianca_encontrada", float),
        confianca_incerta=_numero(componente, "confianca_incerta", float),
        linhas_centro=_numero(geometria, "linhas_centro", int),
        fator_largura_intersecao=_numero(geometria, "fator_largura_intersecao", float),
    )


class DetectorClassicoLinha:
    """Segmenta linha escura e extrai uma trajetoria sem estado temporal."""

    def __init__(self, configuracao: ConfiguracaoDetectorClassico) -> None:
        self.configuracao = configuracao
        grade = configuracao.grade_clahe
        self._clahe = cv2.createCLAHE(
            clipLimit=configuracao.limite_clahe,
            tileGridSize=(grade, grade),
        )

    def processar(
        self,
        quadro_bgr: np.ndarray,
        *,
        id_quadro: int = 0,
        instante_monotonico_s: float | None = None,
    ) -> ResultadoDetectorClassico:
        """Processa um quadro BGR e devolve mascara e contrato geometrico."""

        if not isinstance(quadro_bgr, np.ndarray) or quadro_bgr.ndim != 3:
            raise ErroDetectorClassico("Quadro deve ser uma matriz BGR com tres dimensoes")
        if quadro_bgr.shape[2] != 3 or quadro_bgr.size == 0:
            raise ErroDetectorClassico("Quadro BGR vazio ou com canais invalidos")

        inicio = perf_counter()
        cinza, mascara_bruta = self._segmentar(quadro_bgr)
        apos_segmentacao = perf_counter()
        mascara, diagnostico = self._selecionar_componente(mascara_bruta, cinza)
        pontos = self._extrair_centro(mascara)
        confianca = self._calcular_confianca(diagnostico, len(pontos))
        estimativa = self._criar_estimativa(
            pontos,
            confianca,
            id_quadro=id_quadro,
            instante_monotonico_s=(
                perf_counter() if instante_monotonico_s is None else instante_monotonico_s
            ),
            pre_processamento_ms=(apos_segmentacao - inicio) * 1_000.0,
            geometria_ms=(perf_counter() - apos_segmentacao) * 1_000.0,
        )
        return ResultadoDetectorClassico(
            mascara=mascara,
            estimativa=estimativa,
            area_normalizada=diagnostico["area"],
            altura_normalizada=diagnostico["altura"],
            contato_inferior=diagnostico["contato_inferior"],
            brilho_linha=diagnostico["brilho"],
            nitidez_borda=float(diagnostico["nitidez_borda"] or 0.0),
        )

    def _segmentar(self, quadro_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        cfg = self.configuracao
        altura_original = quadro_bgr.shape[0]
        y0 = round(altura_original * cfg.roi_y)
        y1 = round(altura_original * (cfg.roi_y + cfg.roi_altura))
        roi = quadro_bgr[y0:y1]
        redimensionado = cv2.resize(
            roi,
            (cfg.largura, cfg.altura),
            interpolation=cv2.INTER_AREA,
        )
        cinza = cv2.cvtColor(redimensionado, cv2.COLOR_BGR2GRAY)
        equalizado = self._clahe.apply(cinza)
        suavizado = cv2.GaussianBlur(equalizado, (5, 5), 0)

        _, global_otsu = cv2.threshold(
            suavizado,
            0,
            255,
            cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
        )
        adaptativo = cv2.adaptiveThreshold(
            suavizado,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            cfg.bloco_adaptativo,
            cfg.constante_adaptativa,
        )
        fundo_local = cv2.GaussianBlur(equalizado, (0, 0), sigmaX=15, sigmaY=15)
        contraste_local = cv2.subtract(fundo_local, equalizado)
        evidencia_local = np.where(contraste_local >= 10, 255, 0).astype(np.uint8)
        mascara = cv2.bitwise_or(global_otsu, cv2.bitwise_and(adaptativo, evidencia_local))

        abertura = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (cfg.kernel_abertura, cfg.kernel_abertura),
        )
        fechamento = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (cfg.kernel_fechamento, cfg.kernel_fechamento),
        )
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, abertura)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, fechamento)
        return cinza, mascara

    def _selecionar_componente(
        self,
        mascara: np.ndarray,
        cinza: np.ndarray,
    ) -> tuple[np.ndarray, dict[str, float | None]]:
        cfg = self.configuracao
        quantidade, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(
            mascara,
            connectivity=8,
        )
        total_pixels = float(mascara.size)
        gradiente_x = cv2.Sobel(cinza, cv2.CV_32F, 1, 0, ksize=3)
        gradiente_y = cv2.Sobel(cinza, cv2.CV_32F, 0, 1, ksize=3)
        magnitude_gradiente = cv2.magnitude(gradiente_x, gradiente_y)
        melhor: tuple[float, int, dict[str, float | None]] | None = None
        for rotulo in range(1, quantidade):
            x, _y, largura, altura, area = estatisticas[rotulo]
            area_n = float(area) / total_pixels
            altura_n = float(altura) / mascara.shape[0]
            if area_n < cfg.area_minima or area_n > cfg.area_maxima:
                continue
            if altura_n < cfg.altura_minima:
                continue
            componente = rotulos == rotulo
            componente_uint8 = np.where(componente, 255, 0).astype(np.uint8)
            borda = cv2.morphologyEx(
                componente_uint8,
                cv2.MORPH_GRADIENT,
                np.ones((3, 3), dtype=np.uint8),
            )
            nitidez_borda = float(np.mean(magnitude_gradiente[borda > 0]))
            if nitidez_borda < cfg.nitidez_borda_minima:
                continue
            faixa_inferior = componente[round(mascara.shape[0] * 0.85) :]
            contato = float(np.count_nonzero(faixa_inferior)) / max(1.0, float(faixa_inferior.size))
            centro_x = (x + largura / 2.0) / mascara.shape[1]
            centralidade = 1.0 - min(1.0, abs(centro_x - 0.5) * 2.0)
            brilho = float(np.mean(cinza[componente]))
            escuridao = 1.0 - brilho / 255.0
            area_util = min(1.0, area_n / 0.20)
            contato_util = min(1.0, contato / 0.12)
            pontuacao = (
                0.25 * area_util
                + 0.30 * altura_n
                + 0.25 * contato_util
                + 0.10 * centralidade
                + 0.10 * escuridao
            )
            diagnostico: dict[str, float | None] = {
                "area": area_n,
                "altura": altura_n,
                "contato_inferior": contato,
                "brilho": brilho,
                "nitidez_borda": nitidez_borda,
                "pontuacao": pontuacao,
            }
            if melhor is None or pontuacao > melhor[0]:
                melhor = (pontuacao, rotulo, diagnostico)

        if melhor is None:
            vazia = np.zeros_like(mascara)
            return vazia, {
                "area": 0.0,
                "altura": 0.0,
                "contato_inferior": 0.0,
                "brilho": None,
                "nitidez_borda": 0.0,
                "pontuacao": 0.0,
            }
        selecionada = np.where(rotulos == melhor[1], 255, 0).astype(np.uint8)
        return selecionada, melhor[2]

    def _extrair_centro(self, mascara: np.ndarray) -> tuple[PontoNormalizado, ...]:
        cfg = self.configuracao
        if not np.any(mascara):
            return ()
        ys = np.linspace(mascara.shape[0] - 1, 0, cfg.linhas_centro, dtype=int)
        pontos_inferior_para_superior: list[PontoNormalizado] = []
        x_anterior: float | None = None
        largura_referencia: float | None = None
        for y in ys:
            xs = np.flatnonzero(mascara[y] > 0)
            if xs.size == 0:
                continue
            grupos = np.split(xs, np.where(np.diff(xs) > 1)[0] + 1)
            if x_anterior is None:
                grupo = min(
                    grupos,
                    key=lambda atual: abs(float(np.mean(atual)) - mascara.shape[1] / 2),
                )
            else:
                grupo = min(grupos, key=lambda atual: abs(float(np.mean(atual)) - x_anterior))
            largura = float(grupo[-1] - grupo[0] + 1)
            centro_grupo = float(np.mean(grupo))
            if largura_referencia is None:
                largura_referencia = largura
            elif largura <= largura_referencia * cfg.fator_largura_intersecao:
                largura_referencia = 0.8 * largura_referencia + 0.2 * largura

            # No T, a barra horizontal alarga muito a faixa. Manter o x anterior
            # preserva a continuacao frontal em vez de puxar a trajetoria para um ramo.
            if (
                x_anterior is not None
                and largura_referencia is not None
                and largura > largura_referencia * cfg.fator_largura_intersecao
                and grupo[0] <= x_anterior <= grupo[-1]
            ):
                centro = x_anterior
            else:
                centro = centro_grupo
            x_anterior = centro
            pontos_inferior_para_superior.append(
                PontoNormalizado(
                    x=centro / max(1, mascara.shape[1] - 1),
                    y=float(y) / max(1, mascara.shape[0] - 1),
                )
            )
        return tuple(reversed(pontos_inferior_para_superior))

    def _calcular_confianca(
        self,
        diagnostico: dict[str, float | None],
        quantidade_pontos: int,
    ) -> float:
        pontuacao = float(diagnostico["pontuacao"] or 0.0)
        cobertura = min(1.0, quantidade_pontos / self.configuracao.linhas_centro)
        return max(0.0, min(1.0, 0.8 * pontuacao + 0.2 * cobertura))

    def _criar_estimativa(
        self,
        pontos: tuple[PontoNormalizado, ...],
        confianca: float,
        *,
        id_quadro: int,
        instante_monotonico_s: float,
        pre_processamento_ms: float,
        geometria_ms: float,
    ) -> EstimativaLinha:
        cfg = self.configuracao
        tempos = TemposProcessamento(
            pre_processamento_ms=pre_processamento_ms,
            geometria_ms=geometria_ms,
        )
        if len(pontos) < 2 or confianca < cfg.confianca_incerta:
            return EstimativaLinha(
                id_quadro=id_quadro,
                instante_monotonico_s=instante_monotonico_s,
                estado=EstadoDeteccao.PERDIDA,
                confianca=confianca,
                fonte=FonteEstimativa.CLASSICA if pontos else FonteEstimativa.NENHUMA,
                motivo="sem_evidencia_suficiente",
                tempos=tempos,
            )
        ponto_atual = pontos[-1]
        indice_objetivo = max(0, len(pontos) // 3)
        ponto_objetivo = pontos[indice_objetivo]
        erro_lateral = max(-1.0, min(1.0, (ponto_atual.x - 0.5) * 2.0))
        dx = ponto_objetivo.x - ponto_atual.x
        dy = max(1e-6, ponto_atual.y - ponto_objetivo.y)
        erro_angular = float(np.degrees(np.arctan2(dx, dy)))
        estado = (
            EstadoDeteccao.ENCONTRADA
            if confianca >= cfg.confianca_encontrada
            else EstadoDeteccao.INCERTA
        )
        return EstimativaLinha(
            id_quadro=id_quadro,
            instante_monotonico_s=instante_monotonico_s,
            estado=estado,
            confianca=confianca,
            centro_linha=pontos,
            ponto_atual=ponto_atual,
            ponto_objetivo=ponto_objetivo,
            erro_lateral_normalizado=erro_lateral,
            erro_angular_graus=erro_angular,
            tipo_curva=TipoCurva.INDEFINIDA,
            fonte=FonteEstimativa.CLASSICA,
            motivo="baseline_classico_sem_rastreamento_temporal",
            tempos=tempos,
        )
