"""Inferencia ONNX, geometria e diagnosticos da linha da pista."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from time import monotonic, perf_counter
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


class ErroDetectorNeural(RuntimeError):
    """Indica configuracao, modelo ou quadro neural invalido."""


@dataclass(frozen=True, slots=True)
class ConfiguracaoDetectorNeural:
    """Parametros congelados do caminho de inferencia e geometria."""

    arquivo_modelo: Path
    sha256_modelo: str
    largura: int
    altura: int
    roi_y: float
    limiar_mascara: float
    quantidade_faixas: int
    altura_faixa: int
    cobertura_minima: float
    fator_largura_intersecao: float
    distancia_objetivo_reta: float
    distancia_objetivo_curva: float
    angulo_reta_graus: float
    angulo_curva_fechada_graus: float
    limiar_encontrada: float
    limiar_incerta: float
    suavizacao: float
    quadros_confirmacao: int
    idade_maxima_temporal_ms: float
    limiar_mascara_visual: float = 0.55
    quantidade_faixas_intersecao: int = 40
    bootstrap_faixas_intersecao: int = 5
    persistencia_alargamento_intersecao: int = 2
    fator_largura_continuacao_intersecao: float = 1.65
    faixas_continuacao_intersecao: int = 8
    faixas_continuacao_borda_intersecao: int = 7
    tolerancia_alinhamento_largura_intersecao: float = 0.55
    tolerancia_alinhamento_intersecao: float = 0.08

    def __post_init__(self) -> None:
        if self.largura < 32 or self.altura < 32:
            raise ErroDetectorNeural("Resolucao neural deve ser ao menos 32x32")
        if not 0.0 <= self.roi_y <= 0.5:
            raise ErroDetectorNeural("roi_y deve estar entre zero e 0.5 para cobrir o quadro")
        for nome in (
            "limiar_mascara",
            "cobertura_minima",
            "distancia_objetivo_reta",
            "distancia_objetivo_curva",
            "limiar_encontrada",
            "suavizacao",
        ):
            valor = getattr(self, nome)
            if not 0.0 < valor <= 1.0:
                raise ErroDetectorNeural(f"{nome} deve estar entre zero exclusivo e um")
        if not 0.0 <= self.limiar_incerta < self.limiar_encontrada:
            raise ErroDetectorNeural("Limiares de confianca invalidos")
        if self.quantidade_faixas < 3 or self.altura_faixa < 1:
            raise ErroDetectorNeural("Amostragem geometrica insuficiente")
        if self.fator_largura_intersecao <= 1.0:
            raise ErroDetectorNeural("fator_largura_intersecao deve ser maior que um")
        if not 0.0 < self.limiar_mascara_visual < self.limiar_mascara:
            raise ErroDetectorNeural(
                "limiar_mascara_visual deve ser positivo e menor que limiar_mascara"
            )
        if self.quantidade_faixas_intersecao < 3:
            raise ErroDetectorNeural("quantidade_faixas_intersecao deve ser ao menos tres")
        if not 1 <= self.bootstrap_faixas_intersecao < self.quantidade_faixas_intersecao:
            raise ErroDetectorNeural("bootstrap_faixas_intersecao invalido")
        if self.persistencia_alargamento_intersecao < 2:
            raise ErroDetectorNeural("persistencia_alargamento_intersecao deve ser ao menos dois")
        if not 1.0 < self.fator_largura_continuacao_intersecao < self.fator_largura_intersecao:
            raise ErroDetectorNeural("fator_largura_continuacao_intersecao invalido")
        if self.faixas_continuacao_intersecao < 1:
            raise ErroDetectorNeural("faixas_continuacao_intersecao deve ser positiva")
        if not 1 <= self.faixas_continuacao_borda_intersecao <= self.faixas_continuacao_intersecao:
            raise ErroDetectorNeural("faixas_continuacao_borda_intersecao invalido")
        for nome in (
            "tolerancia_alinhamento_largura_intersecao",
            "tolerancia_alinhamento_intersecao",
        ):
            valor = getattr(self, nome)
            if not 0.0 < valor <= 1.0:
                raise ErroDetectorNeural(f"{nome} deve estar entre zero exclusivo e um")
        if self.angulo_reta_graus <= 0.0:
            raise ErroDetectorNeural("angulo_reta_graus deve ser positivo")
        if self.angulo_curva_fechada_graus <= self.angulo_reta_graus:
            raise ErroDetectorNeural("Limites de curva invalidos")
        if self.idade_maxima_temporal_ms <= 0.0:
            raise ErroDetectorNeural("idade_maxima_temporal_ms deve ser positiva")
        if self.quadros_confirmacao < 1:
            raise ErroDetectorNeural("quadros_confirmacao deve ser ao menos um")


@dataclass(frozen=True, slots=True)
class DiagnosticoGeometria:
    """Medidas explicaveis usadas para confianca e painel."""

    cobertura_faixas: float
    probabilidade_media_linha: float
    continuidade: float
    area_mascara: float
    largura_referencia: float
    largura_maxima: float
    intersecao_detectada: bool


@dataclass(frozen=True, slots=True)
class ResultadoDetectorNeural:
    """Saida completa do detector antes do rastreamento temporal."""

    probabilidade: np.ndarray
    mascara: np.ndarray
    estimativa: EstimativaLinha
    diagnostico: DiagnosticoGeometria
    probabilidade_quadro: np.ndarray | None = None
    mascara_quadro: np.ndarray | None = None


def _sha256_arquivo(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def _numero(secao: dict[str, Any], nome: str, tipo: type[int] | type[float]) -> Any:
    valor = secao.get(nome)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroDetectorNeural(f"Parametro ausente ou invalido: {nome}")
    return tipo(valor)


def carregar_configuracao_detector_neural(
    caminho: Path,
    *,
    raiz: Path | None = None,
) -> ConfiguracaoDetectorNeural:
    """Carrega o perfil neural e resolve o modelo em relacao a raiz do projeto."""

    dados = carregar_toml(caminho)
    modelo = exigir_secao(dados, "modelo")
    geometria = exigir_secao(dados, "geometria")
    confianca = exigir_secao(dados, "confianca")
    rastreamento = exigir_secao(dados, "rastreamento")
    arquivo = modelo.get("arquivo")
    sha256 = modelo.get("sha256")
    if not isinstance(arquivo, str) or not arquivo.strip():
        raise ErroDetectorNeural("modelo.arquivo deve ser texto nao vazio")
    if not isinstance(sha256, str) or len(sha256) != 64:
        raise ErroDetectorNeural("modelo.sha256 deve ter 64 caracteres")
    base = caminho.resolve().parent.parent if raiz is None else raiz.resolve()
    return ConfiguracaoDetectorNeural(
        arquivo_modelo=(base / arquivo).resolve(),
        sha256_modelo=sha256.lower(),
        largura=_numero(modelo, "largura", int),
        altura=_numero(modelo, "altura", int),
        roi_y=_numero(modelo, "roi_y", float),
        limiar_mascara=_numero(modelo, "limiar_mascara", float),
        limiar_mascara_visual=_numero(
            modelo,
            "limiar_mascara_visual",
            float,
        ),
        quantidade_faixas=_numero(geometria, "quantidade_faixas", int),
        altura_faixa=_numero(geometria, "altura_faixa", int),
        cobertura_minima=_numero(geometria, "cobertura_minima", float),
        fator_largura_intersecao=_numero(geometria, "fator_largura_intersecao", float),
        quantidade_faixas_intersecao=_numero(
            geometria,
            "quantidade_faixas_intersecao",
            int,
        ),
        bootstrap_faixas_intersecao=_numero(
            geometria,
            "bootstrap_faixas_intersecao",
            int,
        ),
        persistencia_alargamento_intersecao=_numero(
            geometria,
            "persistencia_alargamento_intersecao",
            int,
        ),
        fator_largura_continuacao_intersecao=_numero(
            geometria,
            "fator_largura_continuacao_intersecao",
            float,
        ),
        faixas_continuacao_intersecao=_numero(
            geometria,
            "faixas_continuacao_intersecao",
            int,
        ),
        faixas_continuacao_borda_intersecao=_numero(
            geometria,
            "faixas_continuacao_borda_intersecao",
            int,
        ),
        tolerancia_alinhamento_largura_intersecao=_numero(
            geometria,
            "tolerancia_alinhamento_largura_intersecao",
            float,
        ),
        tolerancia_alinhamento_intersecao=_numero(
            geometria,
            "tolerancia_alinhamento_intersecao",
            float,
        ),
        distancia_objetivo_reta=_numero(geometria, "distancia_objetivo_reta", float),
        distancia_objetivo_curva=_numero(geometria, "distancia_objetivo_curva", float),
        angulo_reta_graus=_numero(geometria, "angulo_reta_graus", float),
        angulo_curva_fechada_graus=_numero(
            geometria,
            "angulo_curva_fechada_graus",
            float,
        ),
        limiar_encontrada=_numero(confianca, "limiar_encontrada", float),
        limiar_incerta=_numero(confianca, "limiar_incerta", float),
        suavizacao=_numero(rastreamento, "suavizacao", float),
        quadros_confirmacao=_numero(rastreamento, "quadros_confirmacao", int),
        idade_maxima_temporal_ms=_numero(
            rastreamento,
            "idade_maxima_temporal_ms",
            float,
        ),
    )


def preprocessar_quadro(
    quadro_bgr: np.ndarray,
    configuracao: ConfiguracaoDetectorNeural,
) -> np.ndarray:
    """Aplica exatamente o recorte e a normalizacao usados no treinamento."""

    if not isinstance(quadro_bgr, np.ndarray) or quadro_bgr.ndim != 3:
        raise ErroDetectorNeural("Quadro deve ser uma matriz BGR com tres dimensoes")
    if quadro_bgr.shape[2] != 3 or quadro_bgr.size == 0:
        raise ErroDetectorNeural("Quadro BGR vazio ou com canais invalidos")
    y0 = round(quadro_bgr.shape[0] * configuracao.roi_y)
    return _preprocessar_janela(quadro_bgr[y0:], configuracao)


def _preprocessar_janela(
    janela_bgr: np.ndarray,
    configuracao: ConfiguracaoDetectorNeural,
) -> np.ndarray:
    if janela_bgr.size == 0:
        raise ErroDetectorNeural("Janela BGR vazia")
    redimensionado = cv2.resize(
        janela_bgr,
        (configuracao.largura, configuracao.altura),
        interpolation=cv2.INTER_AREA,
    )
    rgb = cv2.cvtColor(redimensionado, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = (rgb - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
        [0.229, 0.224, 0.225],
        dtype=np.float32,
    )
    return np.ascontiguousarray(np.transpose(rgb, (2, 0, 1))[None], dtype=np.float32)


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    positivos = logits >= 0
    saida = np.empty_like(logits, dtype=np.float32)
    saida[positivos] = 1.0 / (1.0 + np.exp(-logits[positivos]))
    exponencial = np.exp(logits[~positivos])
    saida[~positivos] = exponencial / (1.0 + exponencial)
    return saida


def _compor_probabilidade_quadro(
    probabilidade_superior: np.ndarray,
    probabilidade_inferior: np.ndarray,
    *,
    altura_quadro: int,
    largura_quadro: int,
    y0: int,
) -> tuple[np.ndarray, np.ndarray]:
    altura_janela = altura_quadro - y0
    tamanho_janela = (largura_quadro, altura_janela)
    superior = cv2.resize(
        probabilidade_superior,
        tamanho_janela,
        interpolation=cv2.INTER_LINEAR,
    )
    inferior = cv2.resize(
        probabilidade_inferior,
        tamanho_janela,
        interpolation=cv2.INTER_LINEAR,
    )
    probabilidade_quadro = np.zeros(
        (altura_quadro, largura_quadro),
        dtype=np.float32,
    )
    probabilidade_quadro[:altura_janela] = superior
    probabilidade_quadro[y0:] = np.maximum(probabilidade_quadro[y0:], inferior)
    return np.ascontiguousarray(probabilidade_quadro), inferior


def _criar_mascara_histerese_conectada(
    probabilidade_quadro: np.ndarray,
    probabilidade_inferior_redimensionada: np.ndarray,
    *,
    y0: int,
    configuracao: ConfiguracaoDetectorNeural,
) -> np.ndarray:
    candidata = np.where(
        probabilidade_quadro >= configuracao.limiar_mascara_visual,
        1,
        0,
    ).astype(np.uint8)
    sementes = np.zeros_like(candidata)
    sementes[y0:] = np.where(
        probabilidade_inferior_redimensionada >= configuracao.limiar_mascara,
        1,
        0,
    ).astype(np.uint8)
    quantidade_sementes, rotulos_sementes, estatisticas, centroides = (
        cv2.connectedComponentsWithStats(sementes, connectivity=8)
    )
    if quantidade_sementes <= 1:
        return np.zeros_like(candidata, dtype=np.uint8)
    rotulos_validos = list(range(1, quantidade_sementes))
    rotulos_na_borda = [
        rotulo
        for rotulo in rotulos_validos
        if estatisticas[rotulo, cv2.CC_STAT_TOP] + estatisticas[rotulo, cv2.CC_STAT_HEIGHT]
        >= sementes.shape[0]
    ]
    if rotulos_na_borda:
        centro_quadro = sementes.shape[1] / 2
        rotulo_semente = min(
            rotulos_na_borda,
            key=lambda rotulo: (
                abs(float(centroides[rotulo, 0]) - centro_quadro),
                -int(estatisticas[rotulo, cv2.CC_STAT_AREA]),
            ),
        )
    else:
        rotulo_semente = max(
            rotulos_validos,
            key=lambda rotulo: int(estatisticas[rotulo, cv2.CC_STAT_AREA]),
        )
    semente_principal = rotulos_sementes == rotulo_semente
    quantidade_candidatos, rotulos_candidatos, estatisticas_candidatos, _ = (
        cv2.connectedComponentsWithStats(candidata, connectivity=8)
    )
    if quantidade_candidatos <= 1:
        return np.zeros_like(candidata, dtype=np.uint8)
    sobreposicoes = np.bincount(
        rotulos_candidatos[semente_principal],
        minlength=quantidade_candidatos,
    )
    sobreposicoes[0] = 0
    maior_sobreposicao = int(np.max(sobreposicoes))
    if maior_sobreposicao == 0:
        return np.zeros_like(candidata, dtype=np.uint8)
    candidatos_principais = np.flatnonzero(sobreposicoes == maior_sobreposicao)
    rotulo_candidato = max(
        candidatos_principais,
        key=lambda rotulo: int(estatisticas_candidatos[rotulo, cv2.CC_STAT_AREA]),
    )
    return np.where(rotulos_candidatos == rotulo_candidato, 255, 0).astype(np.uint8)


class ExtratorGeometriaLinha:
    """Converte a probabilidade neural em uma trajetoria explicavel."""

    def __init__(self, configuracao: ConfiguracaoDetectorNeural) -> None:
        self.configuracao = configuracao

    def extrair(
        self,
        probabilidade: np.ndarray,
        *,
        id_quadro: int,
        instante_monotonico_s: float,
        tempos: TemposProcessamento | None = None,
        mascara_quadro: np.ndarray | None = None,
    ) -> tuple[np.ndarray, EstimativaLinha, DiagnosticoGeometria]:
        cfg = self.configuracao
        if probabilidade.shape != (cfg.altura, cfg.largura):
            raise ErroDetectorNeural(f"Probabilidade deve ter forma {(cfg.altura, cfg.largura)}")
        inicio = perf_counter()
        mascara = np.where(probabilidade >= cfg.limiar_mascara, 255, 0).astype(np.uint8)
        mascara_topologia = mascara if mascara_quadro is None else mascara_quadro
        if mascara_topologia.ndim != 2 or mascara_topologia.size == 0:
            raise ErroDetectorNeural("mascara_quadro deve ser uma matriz bidimensional nao vazia")
        intersecao = self._confirmar_intersecao_t(mascara_topologia)
        pontos, larguras, alargamento_curva = self._extrair_centro(
            mascara,
            intersecao_confirmada=intersecao,
        )
        cobertura = len(pontos) / cfg.quantidade_faixas
        suporte = probabilidade[mascara > 0]
        probabilidade_media = float(np.mean(suporte)) if suporte.size else 0.0
        continuidade = self._continuidade(pontos)
        area = float(np.count_nonzero(mascara)) / float(mascara.size)
        largura_referencia = (
            float(np.median(larguras[: max(1, len(larguras) // 2)])) if larguras else 0.0
        )
        largura_maxima = max(larguras, default=0.0)
        diagnostico = DiagnosticoGeometria(
            cobertura_faixas=cobertura,
            probabilidade_media_linha=probabilidade_media,
            continuidade=continuidade,
            area_mascara=area,
            largura_referencia=largura_referencia / cfg.largura,
            largura_maxima=largura_maxima / cfg.largura,
            intersecao_detectada=intersecao,
        )
        confianca = float(
            np.clip(0.55 * probabilidade_media + 0.30 * cobertura + 0.15 * continuidade, 0, 1)
        )
        if cobertura < cfg.cobertura_minima:
            confianca = min(confianca, cfg.limiar_incerta * 0.9)
        tempo_geometria = (perf_counter() - inicio) * 1000.0
        tempos_base = tempos or TemposProcessamento()
        tempos_finais = replace(
            tempos_base,
            geometria_ms=tempos_base.geometria_ms + tempo_geometria,
        )
        estimativa = self._criar_estimativa(
            pontos,
            confianca,
            intersecao,
            alargamento_curva=alargamento_curva,
            id_quadro=id_quadro,
            instante_monotonico_s=instante_monotonico_s,
            tempos=tempos_finais,
        )
        return mascara, estimativa, diagnostico

    def _extrair_centro(
        self,
        mascara: np.ndarray,
        *,
        intersecao_confirmada: bool,
    ) -> tuple[tuple[PontoNormalizado, ...], list[float], bool]:
        cfg = self.configuracao
        ys = np.linspace(mascara.shape[0] - 1, 0, cfg.quantidade_faixas, dtype=int)
        pontos: list[PontoNormalizado] = []
        larguras: list[float] = []
        x_anterior: float | None = None
        largura_referencia: float | None = None
        alargamento_curva = False
        metade_faixa = cfg.altura_faixa // 2
        for y in ys:
            y0 = max(0, y - metade_faixa)
            y1 = min(mascara.shape[0], y + metade_faixa + 1)
            perfil = np.count_nonzero(mascara[y0:y1] > 0, axis=0)
            xs = np.flatnonzero(perfil > 0)
            if xs.size == 0:
                continue
            grupos = np.split(xs, np.where(np.diff(xs) > 1)[0] + 1)
            if x_anterior is None:
                grupo = min(
                    grupos,
                    key=lambda item: abs(float(np.mean(item)) - mascara.shape[1] / 2),
                )
            else:
                grupo = min(grupos, key=lambda item: abs(float(np.mean(item)) - x_anterior))
            pesos = perfil[grupo].astype(np.float64)
            centro_grupo = float(np.average(grupo, weights=pesos))
            largura = float(grupo[-1] - grupo[0] + 1)
            if largura_referencia is None:
                largura_referencia = largura
            alargamento = (
                x_anterior is not None
                and largura_referencia is not None
                and largura > largura_referencia * cfg.fator_largura_intersecao
                and grupo[0] <= x_anterior <= grupo[-1]
            )
            alargamento_curva = alargamento_curva or alargamento
            if alargamento and intersecao_confirmada:
                centro = x_anterior
            else:
                centro = centro_grupo
                largura_referencia = 0.85 * largura_referencia + 0.15 * largura
            x_anterior = centro
            larguras.append(largura)
            pontos.append(
                PontoNormalizado(
                    x=float(np.clip(centro / max(1, mascara.shape[1] - 1), 0, 1)),
                    y=float(y / max(1, mascara.shape[0] - 1)),
                )
            )
        return tuple(reversed(pontos)), larguras, alargamento_curva

    def _confirmar_intersecao_t(self, mascara: np.ndarray) -> bool:
        cfg = self.configuracao
        altura, largura_quadro = mascara.shape
        ys = np.linspace(
            altura - 1,
            0,
            cfg.quantidade_faixas_intersecao,
            dtype=int,
        )
        escala_vertical = altura / cfg.altura
        metade_faixa = max(0, round((cfg.altura_faixa * escala_vertical - 1) / 2))
        faixas: list[tuple[int, np.ndarray, list[np.ndarray]]] = []

        for y in ys:
            perfil = np.count_nonzero(
                mascara[max(0, y - metade_faixa) : min(altura, y + metade_faixa + 1)] > 0,
                axis=0,
            )
            xs = np.flatnonzero(perfil > 0)
            if xs.size == 0:
                continue
            grupos = np.split(xs, np.where(np.diff(xs) > 1)[0] + 1)
            faixas.append((y, perfil, grupos))

        bootstrap = cfg.bootstrap_faixas_intersecao
        if len(faixas) < bootstrap + cfg.persistencia_alargamento_intersecao:
            return False
        observacoes: list[tuple[int, float, float, int, int]] = []
        x_rastreio: float | None = None
        for y, perfil, grupos in faixas[:bootstrap]:
            referencia_x = largura_quadro / 2 if x_rastreio is None else x_rastreio
            grupo = min(grupos, key=lambda item: abs(float(np.mean(item)) - referencia_x))
            centro = float(np.average(grupo, weights=perfil[grupo].astype(np.float64)))
            observacoes.append(
                (y, centro, float(grupo[-1] - grupo[0] + 1), int(grupo[0]), int(grupo[-1]))
            )
            x_rastreio = centro

        largura_tronco = float(np.median([item[2] for item in observacoes]))
        x_tronco = float(np.median([item[1] for item in observacoes]))
        for y, perfil, grupos in faixas[bootstrap:]:
            grupo = min(
                grupos,
                key=lambda item: (
                    0.0
                    if item[0] <= x_tronco <= item[-1]
                    else min(abs(float(item[0]) - x_tronco), abs(float(item[-1]) - x_tronco)),
                    abs(float(np.mean(item)) - x_tronco),
                ),
            )
            centro = float(np.average(grupo, weights=perfil[grupo].astype(np.float64)))
            observacoes.append(
                (y, centro, float(grupo[-1] - grupo[0] + 1), int(grupo[0]), int(grupo[-1]))
            )
        tolerancia = max(
            cfg.tolerancia_alinhamento_largura_intersecao * largura_tronco,
            cfg.tolerancia_alinhamento_intersecao * largura_quadro,
        )
        limite_alargamento = largura_tronco * cfg.fator_largura_intersecao
        limite_continuacao = largura_tronco * cfg.fator_largura_continuacao_intersecao
        alargadas_consecutivas = 0
        alargamento_confirmado = False
        continuacao_consecutiva = 0

        for y, centro, largura, x_minimo, x_maximo in observacoes[bootstrap:]:
            contem_tronco = x_minimo - tolerancia <= x_tronco <= x_maximo + tolerancia
            if largura >= limite_alargamento and contem_tronco:
                alargadas_consecutivas += 1
                continuacao_consecutiva = 0
                if alargadas_consecutivas >= cfg.persistencia_alargamento_intersecao:
                    alargamento_confirmado = True
                continue
            if not alargamento_confirmado:
                alargadas_consecutivas = 0
                continue
            estreita = largura <= limite_continuacao
            alinhada = abs(centro - x_tronco) <= tolerancia
            if estreita and alinhada:
                continuacao_consecutiva += 1
                if continuacao_consecutiva >= cfg.faixas_continuacao_intersecao:
                    return True
                if y == 0 and continuacao_consecutiva >= cfg.faixas_continuacao_borda_intersecao:
                    return True
            else:
                continuacao_consecutiva = 0
        return False

    @staticmethod
    def _continuidade(pontos: tuple[PontoNormalizado, ...]) -> float:
        if len(pontos) < 2:
            return 0.0
        saltos = np.abs(np.diff([ponto.x for ponto in pontos]))
        return float(np.clip(1.0 - np.percentile(saltos, 80) / 0.15, 0, 1))

    def _criar_estimativa(
        self,
        pontos: tuple[PontoNormalizado, ...],
        confianca: float,
        intersecao: bool,
        *,
        alargamento_curva: bool,
        id_quadro: int,
        instante_monotonico_s: float,
        tempos: TemposProcessamento,
    ) -> EstimativaLinha:
        cfg = self.configuracao
        if len(pontos) < 2 or confianca < cfg.limiar_incerta:
            return EstimativaLinha(
                id_quadro=id_quadro,
                instante_monotonico_s=instante_monotonico_s,
                estado=EstadoDeteccao.PERDIDA,
                confianca=confianca,
                fonte=FonteEstimativa.IA if pontos else FonteEstimativa.NENHUMA,
                motivo="sem_evidencia_neural_suficiente",
                tempos=tempos,
            )
        ponto_atual = pontos[-1]
        ponto_distante = pontos[0]
        dx_distante = ponto_distante.x - ponto_atual.x
        dy_distante = max(1e-6, ponto_atual.y - ponto_distante.y)
        angulo_distante = float(np.degrees(np.arctan2(dx_distante, dy_distante)))
        distancia = (
            cfg.distancia_objetivo_reta
            if abs(angulo_distante) <= cfg.angulo_reta_graus or intersecao
            else cfg.distancia_objetivo_curva
        )
        y_objetivo = max(0.0, ponto_atual.y - distancia)
        ponto_objetivo = min(pontos, key=lambda ponto: abs(ponto.y - y_objetivo))
        if intersecao:
            ponto_objetivo = PontoNormalizado(x=ponto_atual.x, y=ponto_objetivo.y)
        dx = ponto_objetivo.x - ponto_atual.x
        dy = max(1e-6, ponto_atual.y - ponto_objetivo.y)
        erro_angular = float(np.degrees(np.arctan2(dx, dy)))
        curvatura = float(np.clip(angulo_distante / 45.0, -1.0, 1.0))
        tipo = self._classificar_curva(
            angulo_distante,
            intersecao,
            alargamento_curva=alargamento_curva,
        )
        estado = (
            EstadoDeteccao.ENCONTRADA
            if confianca >= cfg.limiar_encontrada
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
            erro_lateral_normalizado=float(np.clip((ponto_atual.x - 0.5) * 2.0, -1, 1)),
            erro_angular_graus=erro_angular,
            curvatura_normalizada=curvatura,
            tipo_curva=tipo,
            fonte=FonteEstimativa.IA,
            motivo=("intersecao_t_continuacao_reta" if intersecao else "evidencia_neural_atual"),
            tempos=tempos,
        )

    def _classificar_curva(
        self,
        angulo: float,
        intersecao: bool,
        *,
        alargamento_curva: bool,
    ) -> TipoCurva:
        cfg = self.configuracao
        if intersecao or abs(angulo) <= cfg.angulo_reta_graus:
            return TipoCurva.RETA
        fechada = alargamento_curva or abs(angulo) >= cfg.angulo_curva_fechada_graus
        if angulo < 0:
            return TipoCurva.ESQUERDA_FECHADA if fechada else TipoCurva.ESQUERDA_SUAVE
        return TipoCurva.DIREITA_FECHADA if fechada else TipoCurva.DIREITA_SUAVE


class DetectorNeuralLinha:
    """Executa o modelo ONNX e devolve a mesma fronteira usada pelo restante do robo."""

    def __init__(
        self,
        configuracao: ConfiguracaoDetectorNeural,
        *,
        sessao: Any | None = None,
    ) -> None:
        self.configuracao = configuracao
        if sessao is None:
            if not configuracao.arquivo_modelo.is_file():
                raise ErroDetectorNeural(f"Modelo ONNX ausente: {configuracao.arquivo_modelo}")
            obtido = _sha256_arquivo(configuracao.arquivo_modelo)
            if obtido.lower() != configuracao.sha256_modelo:
                raise ErroDetectorNeural(
                    "SHA-256 do ONNX diverge: "
                    f"esperado {configuracao.sha256_modelo}, obtido {obtido}"
                )
            try:
                import onnxruntime as ort
            except (ImportError, ModuleNotFoundError) as erro:
                raise ErroDetectorNeural("ONNX Runtime nao esta instalado") from erro
            sessao = ort.InferenceSession(
                str(configuracao.arquivo_modelo),
                providers=["CPUExecutionProvider"],
            )
        self._sessao = sessao
        self._geometria = ExtratorGeometriaLinha(configuracao)

    def processar(
        self,
        quadro_bgr: np.ndarray,
        *,
        id_quadro: int = 0,
        instante_monotonico_s: float | None = None,
    ) -> ResultadoDetectorNeural:
        """Processa o quadro atual sem manter fila ou estado temporal."""

        instante = monotonic() if instante_monotonico_s is None else instante_monotonico_s
        inicio = perf_counter()
        entrada_inferior = preprocessar_quadro(quadro_bgr, self.configuracao)
        altura_quadro, largura_quadro = quadro_bgr.shape[:2]
        y0 = round(altura_quadro * self.configuracao.roi_y)
        entrada_superior = (
            entrada_inferior
            if y0 == 0
            else _preprocessar_janela(
                quadro_bgr[: altura_quadro - y0],
                self.configuracao,
            )
        )
        apos_pre = perf_counter()
        try:
            if y0 == 0:
                logits_inferiores = np.asarray(
                    self._sessao.run(["logits"], {"imagem": entrada_inferior})[0],
                    dtype=np.float32,
                )
                logits_superiores = logits_inferiores
            else:
                logits_superiores = np.asarray(
                    self._sessao.run(["logits"], {"imagem": entrada_superior})[0],
                    dtype=np.float32,
                )
                logits_inferiores = np.asarray(
                    self._sessao.run(["logits"], {"imagem": entrada_inferior})[0],
                    dtype=np.float32,
                )
        except Exception as erro:
            raise ErroDetectorNeural(f"Falha na inferencia ONNX: {erro}") from erro
        apos_inferencia = perf_counter()
        forma_esperada = (1, 1, self.configuracao.altura, self.configuracao.largura)
        if logits_superiores.shape != forma_esperada:
            raise ErroDetectorNeural(
                "Saida ONNX superior incompativel: "
                f"esperado {forma_esperada}, obtido {logits_superiores.shape}"
            )
        if logits_inferiores.shape != forma_esperada:
            raise ErroDetectorNeural(
                "Saida ONNX inferior incompativel: "
                f"esperado {forma_esperada}, obtido {logits_inferiores.shape}"
            )
        probabilidade_superior = _sigmoid(logits_superiores[0, 0])
        probabilidade = _sigmoid(logits_inferiores[0, 0])
        probabilidade_quadro, probabilidade_inferior_redimensionada = _compor_probabilidade_quadro(
            probabilidade_superior,
            probabilidade,
            altura_quadro=altura_quadro,
            largura_quadro=largura_quadro,
            y0=y0,
        )
        mascara_quadro = _criar_mascara_histerese_conectada(
            probabilidade_quadro,
            probabilidade_inferior_redimensionada,
            y0=y0,
            configuracao=self.configuracao,
        )
        tempos = TemposProcessamento(
            pre_processamento_ms=(apos_pre - inicio) * 1000.0,
            inferencia_ms=(apos_inferencia - apos_pre) * 1000.0,
        )
        mascara, estimativa, diagnostico = self._geometria.extrair(
            probabilidade,
            id_quadro=id_quadro,
            instante_monotonico_s=instante,
            tempos=tempos,
            mascara_quadro=mascara_quadro,
        )
        return ResultadoDetectorNeural(
            probabilidade=probabilidade,
            mascara=mascara,
            estimativa=estimativa,
            diagnostico=diagnostico,
            probabilidade_quadro=probabilidade_quadro,
            mascara_quadro=mascara_quadro,
        )
