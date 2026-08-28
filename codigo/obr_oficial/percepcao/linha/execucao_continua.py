"""Processamento continuo da linha consumindo sempre o quadro mais recente."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from itertools import pairwise
from threading import Condition, Event, Lock, Thread
from time import monotonic

import cv2
import numpy as np

from obr_oficial.dispositivos.camera_base import FonteCamera, QuadroCamera
from obr_oficial.nucleo.contratos import EstimativaLinha, PontoNormalizado
from obr_oficial.percepcao.linha.detector_neural import (
    ConfiguracaoDetectorNeural,
    DetectorNeuralLinha,
    DiagnosticoGeometria,
    ResultadoDetectorNeural,
)
from obr_oficial.percepcao.linha.rastreamento import RastreadorLinha


@dataclass(frozen=True, slots=True)
class ResultadoQuadroLinha:
    """Quadro pronto para observabilidade, separado do caminho de controle."""

    id_quadro: int
    instante_monotonico_s: float
    imagem_sobreposta: np.ndarray
    mascara: np.ndarray
    estimativa: EstimativaLinha
    diagnostico: DiagnosticoGeometria


@dataclass(frozen=True, slots=True)
class EstadoProcessadorLinha:
    """Saude e desempenho serializaveis do processamento continuo."""

    ativo: bool
    saudavel: bool
    total_processados: int
    total_falhas: int
    quadros_por_segundo: float
    ultimo_id_quadro: int | None
    idade_ultimo_resultado_ms: float | None
    ultimo_erro: str

    def como_dict(self) -> dict[str, object]:
        return asdict(self)


def estimativa_como_dict(estimativa: EstimativaLinha) -> dict[str, object]:
    """Serializa o contrato sem expor tensores ou objetos internos do modelo."""

    def ponto(valor: PontoNormalizado | None) -> dict[str, float] | None:
        return None if valor is None else {"x": valor.x, "y": valor.y}

    return {
        "id_quadro": estimativa.id_quadro,
        "instante_monotonico_s": estimativa.instante_monotonico_s,
        "estado": estimativa.estado.value,
        "confianca": estimativa.confianca,
        "centro_linha": [ponto(item) for item in estimativa.centro_linha],
        "ponto_atual": ponto(estimativa.ponto_atual),
        "ponto_objetivo": ponto(estimativa.ponto_objetivo),
        "erro_lateral_normalizado": estimativa.erro_lateral_normalizado,
        "erro_angular_graus": estimativa.erro_angular_graus,
        "curvatura_normalizada": estimativa.curvatura_normalizada,
        "tipo_curva": estimativa.tipo_curva.value,
        "fonte": estimativa.fonte.value,
        "idade_observacao_ms": estimativa.idade_observacao_ms,
        "motivo": estimativa.motivo,
        "tempos": {
            "pre_processamento_ms": estimativa.tempos.pre_processamento_ms,
            "inferencia_ms": estimativa.tempos.inferencia_ms,
            "geometria_ms": estimativa.tempos.geometria_ms,
            "rastreamento_ms": estimativa.tempos.rastreamento_ms,
            "total_ms": estimativa.tempos.total_ms,
        },
    }


def _criar_mascara_visual(
    mascara: np.ndarray,
    largura: int,
    altura: int,
) -> np.ndarray:
    """Redimensiona a mascara logica sem inventar ou suavizar seus limites."""

    binaria = np.where(mascara > 0, 255, 0).astype(np.uint8)
    return cv2.resize(
        binaria,
        (largura, altura),
        interpolation=cv2.INTER_NEAREST,
    )


def _segmento_na_borda_externa(
    inicio: np.ndarray,
    fim: np.ndarray,
    largura: int,
    altura: int,
) -> bool:
    """Identifica somente arestas criadas pelo recorte nos limites da imagem."""

    x_inicio, y_inicio = (int(valor) for valor in inicio)
    x_fim, y_fim = (int(valor) for valor in fim)
    return (
        (y_inicio == 0 and y_fim == 0)
        or (y_inicio == altura - 1 and y_fim == altura - 1)
        or (x_inicio == 0 and x_fim == 0)
        or (x_inicio == largura - 1 and x_fim == largura - 1)
    )


def _desenhar_contorno_mascara(regiao: np.ndarray, mascara: np.ndarray) -> None:
    """Contorna a linha sem pintar seu interior nem esconder a camera."""

    contornos, _hierarquia = cv2.findContours(
        mascara,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE,
    )
    if not contornos:
        return

    # O corte reproduz a leitura visual das referencias: destino em azul-violeta
    # e trecho mais proximo do robo em ciano, sem gradiente entre as duas regioes.
    corte_proximidade = round(mascara.shape[0] * 0.72)
    cor_distante = (255, 70, 110)
    cor_proxima = (255, 235, 0)
    espessura = 3
    altura, largura = mascara.shape

    for contorno in contornos:
        pontos = contorno.reshape(-1, 2)
        if len(pontos) < 2:
            continue
        pontos_fechados = np.vstack((pontos, pontos[0]))
        for inicio, fim in pairwise(pontos_fechados):
            if _segmento_na_borda_externa(inicio, fim, largura, altura):
                continue
            y_medio = (int(inicio[1]) + int(fim[1])) / 2.0
            cor = cor_proxima if y_medio >= corte_proximidade else cor_distante
            cv2.line(
                regiao,
                tuple(int(valor) for valor in inicio),
                tuple(int(valor) for valor in fim),
                cor,
                espessura,
                cv2.LINE_AA,
            )


def _suavizar_polilinha(pontos: np.ndarray, repeticoes: int = 2) -> np.ndarray:
    """Cria uma curva visual continua sem alterar os pontos usados pelo controle."""

    if len(pontos) < 3:
        return pontos.astype(np.int32)
    suaves = pontos.astype(np.float32)
    for _ in range(repeticoes):
        refinados = [suaves[0]]
        for inicio, fim in pairwise(suaves):
            refinados.extend((0.75 * inicio + 0.25 * fim, 0.25 * inicio + 0.75 * fim))
        refinados.append(suaves[-1])
        suaves = np.asarray(refinados, dtype=np.float32)
    return np.rint(suaves).astype(np.int32)


def _criar_esqueleto_rota(mascara: np.ndarray) -> np.ndarray:
    """Extrai um corredor central estreito e conectado para a rota visual."""

    binaria = np.where(mascara > 0, 255, 0).astype(np.uint8)
    distancia = cv2.distanceTransform(binaria, cv2.DIST_L2, 5)
    maximo_local = cv2.dilate(distancia, np.ones((7, 7), dtype=np.uint8))
    corredor = np.where(
        (binaria > 0) & (distancia >= 0.80 * maximo_local),
        255,
        0,
    ).astype(np.uint8)
    elemento = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    # Fecha apenas falhas subpixel da crista central; nao preenche GAPs reais.
    return cv2.morphologyEx(corredor, cv2.MORPH_CLOSE, elemento)


def _recortar_extremos_rota(
    pontos: np.ndarray,
    margem_px: float,
    *,
    largura: int,
    altura: int,
) -> np.ndarray:
    """Mantem os marcadores inteiros dentro da imagem, sem encurtar rotas pequenas."""

    pontos = np.asarray(pontos, dtype=np.float32)
    if len(pontos) < 2:
        return pontos
    comprimentos = np.linalg.norm(np.diff(pontos, axis=0), axis=1)
    acumulados = np.concatenate(([0.0], np.cumsum(comprimentos)))
    total = float(acumulados[-1])
    if total <= 2.0 * margem_px:
        return pontos

    def amostrar(distancia: float) -> tuple[np.ndarray, int]:
        indice = int(np.searchsorted(acumulados, distancia, side="right") - 1)
        indice = int(np.clip(indice, 0, len(comprimentos) - 1))
        fracao = (distancia - acumulados[indice]) / max(comprimentos[indice], 1e-6)
        ponto = pontos[indice] + fracao * (pontos[indice + 1] - pontos[indice])
        return ponto, indice

    def perto_da_borda(ponto: np.ndarray) -> bool:
        return bool(
            ponto[0] < margem_px
            or ponto[1] < margem_px
            or ponto[0] > largura - 1 - margem_px
            or ponto[1] > altura - 1 - margem_px
        )

    distancia_inicio = margem_px if perto_da_borda(pontos[0]) else 0.0
    distancia_fim = total - margem_px if perto_da_borda(pontos[-1]) else total
    inicio, indice_inicio = amostrar(distancia_inicio)
    fim, indice_fim = amostrar(distancia_fim)
    intermediarios = pontos[indice_inicio + 1 : indice_fim + 1]
    return np.vstack((inicio, intermediarios, fim))


def _cobertura_rota_na_mascara(pontos: np.ndarray, mascara: np.ndarray) -> float:
    """Mede quanto de uma polilinha permanece dentro da linha detectada."""

    amostras: list[np.ndarray] = []
    for inicio, fim in pairwise(np.asarray(pontos, dtype=np.float32)):
        quantidade = max(2, int(np.max(np.abs(fim - inicio))) + 1)
        amostras.append(np.linspace(inicio, fim, quantidade, dtype=np.float32))
    if not amostras:
        return 0.0
    densos = np.rint(np.vstack(amostras)).astype(np.int32)
    densos[:, 0] = np.clip(densos[:, 0], 0, mascara.shape[1] - 1)
    densos[:, 1] = np.clip(densos[:, 1], 0, mascara.shape[0] - 1)
    return float(np.mean(mascara[densos[:, 1], densos[:, 0]] > 0))


def _intervalo_ativo_proximo(
    vetor: np.ndarray,
    referencia: float,
) -> tuple[float, int] | None:
    """Retorna centro e largura do trecho ativo mais proximo da referencia."""

    ativos = np.flatnonzero(vetor > 0)
    if len(ativos) == 0:
        return None
    indice = int(ativos[np.argmin(np.abs(ativos - referencia))])
    zeros_antes = np.flatnonzero(vetor[:indice] == 0)
    inicio_intervalo = int(zeros_antes[-1] + 1) if len(zeros_antes) else 0
    zeros_depois = np.flatnonzero(vetor[indice + 1 :] == 0)
    fim_intervalo = int(indice + zeros_depois[0]) if len(zeros_depois) else len(vetor) - 1
    return 0.5 * (inicio_intervalo + fim_intervalo), fim_intervalo - inicio_intervalo + 1


def _centralizar_rota_monotona(
    pontos: np.ndarray,
    mascara: np.ndarray,
) -> np.ndarray:
    """Segue o centro de cada secao horizontal em retas e curvas comuns."""

    if len(pontos) < 2:
        return pontos
    inicio = np.asarray(pontos[0], dtype=np.float32)
    fim = np.asarray(pontos[-1], dtype=np.float32)
    deslocamento_y = abs(float(fim[1] - inicio[1]))
    if deslocamento_y < 0.20 * mascara.shape[0]:
        return pontos

    quantidade = max(8, min(24, round(deslocamento_y / 24.0)))
    ys = np.linspace(inicio[1], fim[1], quantidade, dtype=np.float32)
    x_referencia = float(inicio[0])
    centralizados: list[tuple[float, float]] = []
    for y in ys:
        y_inteiro = int(np.clip(round(float(y)), 0, mascara.shape[0] - 1))
        intervalo = _intervalo_ativo_proximo(mascara[y_inteiro], x_referencia)
        if intervalo is None:
            continue
        x_central, _largura = intervalo
        centralizados.append((x_central, float(y_inteiro)))
        x_referencia = x_central
    if len(centralizados) < 2:
        return pontos
    return np.asarray(centralizados, dtype=np.float32)


def _centralizar_extremos_em_secoes(
    pontos: np.ndarray,
    mascara: np.ndarray,
) -> np.ndarray:
    """Centraliza as bolinhas sem permitir que um ramo de T desvie a rota."""

    centralizados = np.asarray(pontos, dtype=np.float32).copy()
    if len(centralizados) < 2:
        return centralizados
    for indice in (0, len(centralizados) - 1):
        x, y = centralizados[indice]
        y_inteiro = int(np.clip(round(float(y)), 0, mascara.shape[0] - 1))
        intervalo = _intervalo_ativo_proximo(mascara[y_inteiro], float(x))
        if intervalo is not None:
            centralizados[indice] = (intervalo[0], float(y_inteiro))
    return centralizados


def _ortogonalizar_rota_se_couber(
    pontos: np.ndarray,
    mascara: np.ndarray,
) -> np.ndarray:
    """Preserva o cotovelo de 90 graus somente quando ele cabe inteiro na linha."""

    if len(pontos) < 2:
        return pontos
    inicio = pontos[0]
    fim = pontos[-1]
    deslocamento = np.abs(fim - inicio)
    if deslocamento[0] < 0.08 * mascara.shape[1] or deslocamento[1] < 0.20 * mascara.shape[0]:
        return pontos

    candidatas = (
        np.asarray((inicio, (fim[0], inicio[1]), fim), dtype=np.float32),
        np.asarray((inicio, (inicio[0], fim[1]), fim), dtype=np.float32),
    )
    coberturas = tuple(_cobertura_rota_na_mascara(candidata, mascara) for candidata in candidatas)
    melhor_indice = int(np.argmax(coberturas))
    # Um limiar alto impede que curvas abertas ou linhas diagonais sejam
    # artificialmente convertidas em um angulo reto.
    if coberturas[melhor_indice] < 0.97:
        return pontos

    if melhor_indice == 0:
        # Entrada horizontal, saida vertical. Centralize cada trecho usando as
        # duas bordas reais da mascara em vez da borda mais proxima do robo.
        x_sonda = int(np.clip(round(inicio[0]), 0, mascara.shape[1] - 1))
        intervalo_vertical_inicio = _intervalo_ativo_proximo(
            mascara[:, x_sonda],
            inicio[1],
        )
        if intervalo_vertical_inicio is None:
            return pontos
        y_central, espessura_horizontal = intervalo_vertical_inicio
        intervalo_horizontal_inicio = _intervalo_ativo_proximo(
            mascara[round(y_central)],
            inicio[0],
        )
        if intervalo_horizontal_inicio is None:
            return pontos
        _, comprimento_horizontal = intervalo_horizontal_inicio
        y_sonda = int(np.clip(round(0.5 * (y_central + fim[1])), 0, mascara.shape[0] - 1))
        intervalo_horizontal_saida = _intervalo_ativo_proximo(
            mascara[y_sonda],
            fim[0],
        )
        if intervalo_horizontal_saida is None:
            return pontos
        x_central, espessura_vertical = intervalo_horizontal_saida
        intervalo_vertical_saida = _intervalo_ativo_proximo(
            mascara[:, round(x_central)],
            fim[1],
        )
        if intervalo_vertical_saida is None:
            return pontos
        _, comprimento_vertical = intervalo_vertical_saida
        if (
            comprimento_horizontal < 1.75 * espessura_horizontal
            or comprimento_vertical < 1.75 * espessura_vertical
        ):
            return pontos
        x_robo = mascara.shape[1] // 2
        if mascara[round(y_central), x_robo] == 0:
            x_robo = round(float(inicio[0]))
        refinada = np.asarray(
            ((x_robo, y_central), (x_central, y_central), (x_central, fim[1])),
            dtype=np.float32,
        )
    else:
        # Entrada vertical, saida horizontal: mesma centralizacao transposta.
        y_sonda = int(np.clip(round(inicio[1]), 0, mascara.shape[0] - 1))
        intervalo_horizontal_inicio = _intervalo_ativo_proximo(
            mascara[y_sonda],
            inicio[0],
        )
        if intervalo_horizontal_inicio is None:
            return pontos
        x_central, espessura_vertical = intervalo_horizontal_inicio
        intervalo_vertical_inicio = _intervalo_ativo_proximo(
            mascara[:, round(x_central)],
            inicio[1],
        )
        if intervalo_vertical_inicio is None:
            return pontos
        _, comprimento_vertical = intervalo_vertical_inicio
        x_sonda = int(np.clip(round(0.5 * (x_central + fim[0])), 0, mascara.shape[1] - 1))
        intervalo_vertical_saida = _intervalo_ativo_proximo(
            mascara[:, x_sonda],
            fim[1],
        )
        if intervalo_vertical_saida is None:
            return pontos
        y_central, espessura_horizontal = intervalo_vertical_saida
        intervalo_horizontal_saida = _intervalo_ativo_proximo(
            mascara[round(y_central)],
            fim[0],
        )
        if intervalo_horizontal_saida is None:
            return pontos
        _, comprimento_horizontal = intervalo_horizontal_saida
        if (
            comprimento_vertical < 1.75 * espessura_vertical
            or comprimento_horizontal < 1.75 * espessura_horizontal
        ):
            return pontos
        refinada = np.asarray(
            ((x_central, inicio[1]), (x_central, y_central), (fim[0], y_central)),
            dtype=np.float32,
        )
    if _cobertura_rota_na_mascara(refinada, mascara) >= 0.97:
        return refinada
    return candidatas[melhor_indice]


def _ajustar_pontos_a_mascara(pontos: np.ndarray, mascara: np.ndarray) -> np.ndarray:
    """Evita que arredondamento ou suavizacao deixem uma bolinha fora da linha."""

    ajustados = np.asarray(pontos, dtype=np.int32).copy()
    ys_linha, xs_linha = np.nonzero(mascara)
    if len(xs_linha) == 0:
        return ajustados
    for indice, (x, y) in enumerate(ajustados):
        x = int(np.clip(x, 0, mascara.shape[1] - 1))
        y = int(np.clip(y, 0, mascara.shape[0] - 1))
        if mascara[y, x] > 0:
            ajustados[indice] = (x, y)
            continue
        distancias = (xs_linha - x) ** 2 + (ys_linha - y) ** 2
        mais_proximo = int(np.argmin(distancias))
        ajustados[indice] = (int(xs_linha[mais_proximo]), int(ys_linha[mais_proximo]))
    return ajustados


def _extrair_rota_visual(
    mascara: np.ndarray,
    *,
    intersecao_t: bool,
) -> np.ndarray | None:
    """Encontra uma rota central conectada, inclusive em curvas de 90 graus.

    A rota e deliberadamente visual: a mascara inferior e a estimativa usadas
    pelo futuro controle nao sao alteradas.
    """

    if mascara.ndim != 2 or not np.any(mascara):
        return None
    altura_original, largura_original = mascara.shape
    # A malha de navegacao e apenas uma aproximacao visual. Limita-la a
    # 128x96 reduz bastante o custo da busca no Raspberry Pi, enquanto os
    # pontos finais voltam para a resolucao original antes do desenho.
    escala = min(1.0, 128.0 / largura_original, 96.0 / altura_original)
    largura = max(1, round(largura_original * escala))
    altura = max(1, round(altura_original * escala))
    reduzida = cv2.resize(mascara, (largura, altura), interpolation=cv2.INTER_NEAREST)

    if intersecao_t:
        # O detector de topologia ja confirmou que ha um tronco e uma
        # continuacao frontal. Selecione apenas o componente conectado ao robo
        # e mostre essa decisao como uma reta, sem entrar nos bracos do T.
        quantidade, rotulos = cv2.connectedComponents(
            np.where(reduzida > 0, 255, 0).astype(np.uint8),
            connectivity=8,
        )
        melhor: tuple[float, np.ndarray, np.ndarray] | None = None
        for rotulo in range(1, quantidade):
            ys_componente, xs_componente = np.nonzero(rotulos == rotulo)
            if len(xs_componente) < 2:
                continue
            proximidade = float(
                np.min((xs_componente - largura / 2.0) ** 2 + (ys_componente - altura * 1.18) ** 2)
            )
            if melhor is None or proximidade < melhor[0]:
                melhor = (proximidade, ys_componente, xs_componente)
        if melhor is None:
            return None
        _, ys_componente, xs_componente = melhor
        distancias_robo = (xs_componente - largura / 2.0) ** 2 + (
            ys_componente - altura * 1.18
        ) ** 2
        indice_inicio = int(np.argmin(distancias_robo))
        x_inicio = int(xs_componente[indice_inicio])
        y_inicio = int(ys_componente[indice_inicio])
        pontuacoes = 3.2 * np.maximum(0, y_inicio - ys_componente) - 2.8 * np.abs(
            xs_componente - x_inicio
        )
        indice_destino = int(np.argmax(pontuacoes))
        caminho_t = np.asarray(
            (
                (x_inicio, y_inicio),
                (int(xs_componente[indice_destino]), int(ys_componente[indice_destino])),
            ),
            dtype=np.float32,
        )
        caminho_t = _recortar_extremos_rota(
            caminho_t / escala,
            margem_px=10.0,
            largura=largura_original,
            altura=altura_original,
        )
        caminho_t = _centralizar_extremos_em_secoes(caminho_t, mascara)
        caminho_t = np.rint(caminho_t).astype(np.int32)
        caminho_t = _ajustar_pontos_a_mascara(caminho_t, mascara)
        return caminho_t if len(caminho_t) >= 2 else None

    esqueleto = _criar_esqueleto_rota(reduzida)
    quantidade, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(
        esqueleto,
        connectivity=8,
    )
    if quantidade <= 1:
        return None
    # O afinamento pode deixar pequenos espinhos isolados nas bordas da
    # mascara. Eles nunca devem roubar as bolinhas da rota central principal.
    rotulo_principal = 1 + int(np.argmax(estatisticas[1:, cv2.CC_STAT_AREA]))
    esqueleto = np.where(rotulos == rotulo_principal, 255, 0).astype(np.uint8)
    ys, xs = np.nonzero(esqueleto)
    if len(xs) < 2:
        return None

    # O ponto atual visual e o trecho central mais proximo da posicao virtual
    # do robo, ligeiramente abaixo do centro do quadro.
    distancias_robo = (xs - largura / 2.0) ** 2 + (ys - altura * 1.18) ** 2
    indice_inicio = int(np.argmin(distancias_robo))
    x_inicio = int(xs[indice_inicio])
    y_inicio = int(ys[indice_inicio])
    inicio = y_inicio * largura + x_inicio

    predecessores = np.full(altura * largura, -2, dtype=np.int32)
    distancias = np.full(altura * largura, -1, dtype=np.int32)
    predecessores[inicio] = -1
    distancias[inicio] = 0
    fila: deque[int] = deque((inicio,))
    while fila:
        atual = fila.popleft()
        y, x = divmod(atual, largura)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                novo_y = y + dy
                novo_x = x + dx
                if not (0 <= novo_y < altura and 0 <= novo_x < largura):
                    continue
                novo = novo_y * largura + novo_x
                if esqueleto[novo_y, novo_x] == 0 or distancias[novo] >= 0:
                    continue
                distancias[novo] = distancias[atual] + 1
                predecessores[novo] = atual
                fila.append(novo)

    alcancaveis = np.flatnonzero(distancias >= 0)
    if len(alcancaveis) < 2:
        return None
    ys_alcancaveis = alcancaveis // largura
    progresso_frontal = np.maximum(0, y_inicio - ys_alcancaveis)
    pontuacoes = distancias[alcancaveis] + 1.25 * progresso_frontal
    destino = int(alcancaveis[int(np.argmax(pontuacoes))])

    caminho_reverso: list[tuple[int, int]] = []
    cursor = destino
    while cursor != -1:
        caminho_reverso.append((cursor % largura, cursor // largura))
        cursor = int(predecessores[cursor])
    caminho = np.asarray(list(reversed(caminho_reverso)), dtype=np.float32)
    if len(caminho) < 2:
        return None

    if len(caminho) >= 7:
        preenchido = np.pad(caminho, ((3, 3), (0, 0)), mode="edge")
        nucleo = np.ones(7, dtype=np.float32) / 7.0
        caminho = np.stack(
            [np.convolve(preenchido[:, eixo], nucleo, mode="valid") for eixo in range(2)],
            axis=1,
        ).astype(np.float32)
    caminho = cv2.approxPolyDP(
        caminho.reshape(-1, 1, 2),
        epsilon=2.0,
        closed=False,
    ).reshape(-1, 2)

    caminho = caminho / escala
    caminho = _ortogonalizar_rota_se_couber(caminho, mascara)
    cotovelo_90 = _eh_cotovelo_ortogonal(caminho)
    if not cotovelo_90:
        caminho = _centralizar_rota_monotona(caminho, mascara)
    caminho = _recortar_extremos_rota(
        caminho,
        margem_px=10.0,
        largura=largura_original,
        altura=altura_original,
    )
    if not cotovelo_90:
        caminho = _centralizar_extremos_em_secoes(caminho, mascara)
    caminho = np.rint(caminho).astype(np.int32)
    caminho = _ajustar_pontos_a_mascara(caminho, mascara)
    if len(caminho) < 2:
        return None
    diferentes = np.concatenate(([True], np.any(np.diff(caminho, axis=0) != 0, axis=1)))
    caminho = caminho[diferentes]
    return caminho if len(caminho) >= 2 else None


def _desenhar_marcador(
    imagem: np.ndarray,
    centro: tuple[int, int],
    cor: tuple[int, int, int],
) -> None:
    """Desenha um marcador compacto, legivel e sem halo que esconda a linha."""

    cv2.circle(imagem, centro, 8, (8, 11, 16), -1, cv2.LINE_AA)
    cv2.circle(imagem, centro, 7, (245, 247, 250), -1, cv2.LINE_AA)
    cv2.circle(imagem, centro, 5, cor, -1, cv2.LINE_AA)


def _eh_cotovelo_ortogonal(rota: np.ndarray) -> bool:
    """Distingue uma curva de 90 graus aprovada de uma polilinha comum."""

    if len(rota) != 3:
        return False
    horizontal_vertical = (
        abs(int(rota[0, 1]) - int(rota[1, 1])) <= 2 and abs(int(rota[1, 0]) - int(rota[2, 0])) <= 2
    )
    vertical_horizontal = (
        abs(int(rota[0, 0]) - int(rota[1, 0])) <= 2 and abs(int(rota[1, 1]) - int(rota[2, 1])) <= 2
    )
    return horizontal_vertical or vertical_horizontal


def desenhar_sobreposicao(
    quadro_bgr: np.ndarray,
    resultado: ResultadoDetectorNeural,
    estimativa: EstimativaLinha,
    configuracao: ConfiguracaoDetectorNeural,
) -> np.ndarray:
    """Desenha mascara, centro, posicao atual ciano e objetivo azul-escuro."""

    imagem = quadro_bgr.copy()
    altura, largura = imagem.shape[:2]
    y0 = round(altura * configuracao.roi_y)
    altura_roi = altura - y0
    mascara_quadro = getattr(resultado, "mascara_quadro", None)
    if isinstance(mascara_quadro, np.ndarray) and mascara_quadro.ndim == 2:
        mascara_visual = _criar_mascara_visual(mascara_quadro, largura, altura)
        regiao = imagem
    else:
        mascara_visual = _criar_mascara_visual(resultado.mascara, largura, altura_roi)
        regiao = imagem[y0:]
    _desenhar_contorno_mascara(regiao, mascara_visual)

    def pixel(ponto: PontoNormalizado) -> tuple[int, int]:
        return (
            round(ponto.x * (largura - 1)),
            round(y0 + ponto.y * max(1, altura_roi - 1)),
        )

    if estimativa.ponto_atual is not None and estimativa.ponto_objetivo is not None:
        atual = pixel(estimativa.ponto_atual)
        objetivo = pixel(estimativa.ponto_objetivo)
        rota_visual = _extrair_rota_visual(
            mascara_visual,
            intersecao_t=resultado.diagnostico.intersecao_detectada,
        )
        if rota_visual is None:
            pontos = estimativa.centro_linha
            indice_atual = (
                min(
                    range(len(pontos)),
                    key=lambda indice: abs(pontos[indice].y - estimativa.ponto_atual.y),
                )
                if pontos
                else 0
            )
            indice_objetivo = (
                min(
                    range(len(pontos)),
                    key=lambda indice: abs(pontos[indice].y - estimativa.ponto_objetivo.y),
                )
                if pontos
                else 0
            )
            if len(pontos) >= 2:
                if indice_objetivo <= indice_atual:
                    trecho = list(pontos[indice_objetivo : indice_atual + 1])
                else:
                    trecho = list(reversed(pontos[indice_atual : indice_objetivo + 1]))
                centro_bruto = np.array([pixel(ponto) for ponto in trecho], dtype=np.int32)
                centro_bruto[0] = objetivo
                centro_bruto[-1] = atual
                rota_visual = _suavizar_polilinha(centro_bruto)
        if rota_visual is not None and len(rota_visual) >= 2:
            atual = tuple(int(valor) for valor in rota_visual[0])
            objetivo = tuple(int(valor) for valor in rota_visual[-1])
            rota_desenho = (
                rota_visual
                if _eh_cotovelo_ortogonal(rota_visual)
                else _suavizar_polilinha(rota_visual)
            )
            cv2.polylines(imagem, [rota_desenho], False, (8, 11, 16), 5, cv2.LINE_AA)
            cv2.polylines(imagem, [rota_desenho], False, (35, 45, 245), 2, cv2.LINE_AA)
        _desenhar_marcador(imagem, objetivo, (165, 55, 10))
        _desenhar_marcador(imagem, atual, (255, 230, 0))
    return imagem


class ProcessadorContinuoLinha:
    """Thread independente que descarta quadros antigos e publica o ultimo resultado."""

    def __init__(
        self,
        fonte_camera: FonteCamera,
        detector: DetectorNeuralLinha,
        rastreador: RastreadorLinha,
    ) -> None:
        self._fonte = fonte_camera
        self._detector = detector
        self._rastreador = rastreador
        self._condicao = Condition()
        self._lock_estado = Lock()
        self._parar = Event()
        self._thread: Thread | None = None
        self._ultimo: ResultadoQuadroLinha | None = None
        self._total_processados = 0
        self._total_falhas = 0
        self._ultimo_erro = ""
        self._instantes: deque[float] = deque(maxlen=90)

    def iniciar(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._parar.clear()
        self._rastreador.reiniciar()
        self._thread = Thread(target=self._executar, name="percepcao-linha", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._thread = None

    def obter_ultimo_resultado(
        self,
        *,
        depois_de: int | None = None,
        timeout_s: float = 0.0,
    ) -> ResultadoQuadroLinha | None:
        limite = monotonic() + max(0.0, timeout_s)
        with self._condicao:
            while self._ultimo is None or (
                depois_de is not None and self._ultimo.id_quadro <= depois_de
            ):
                restante = limite - monotonic()
                if restante <= 0.0:
                    return None
                self._condicao.wait(restante)
            return self._ultimo

    def obter_estado(self) -> EstadoProcessadorLinha:
        with self._lock_estado:
            ativo = self._thread is not None and self._thread.is_alive()
            idade = None
            ultimo_id = None
            if self._ultimo is not None:
                idade = (monotonic() - self._ultimo.instante_monotonico_s) * 1000.0
                ultimo_id = self._ultimo.id_quadro
            fps = 0.0
            if len(self._instantes) >= 2:
                duracao = self._instantes[-1] - self._instantes[0]
                if duracao > 0.0:
                    fps = (len(self._instantes) - 1) / duracao
            saudavel = ativo and idade is not None and idade < 1000.0 and not self._ultimo_erro
            return EstadoProcessadorLinha(
                ativo=ativo,
                saudavel=saudavel,
                total_processados=self._total_processados,
                total_falhas=self._total_falhas,
                quadros_por_segundo=fps,
                ultimo_id_quadro=ultimo_id,
                idade_ultimo_resultado_ms=idade,
                ultimo_erro=self._ultimo_erro,
            )

    def _executar(self) -> None:
        ultimo_id: int | None = None
        while not self._parar.is_set():
            quadro = self._fonte.obter_ultimo_quadro(depois_de=ultimo_id, timeout_s=0.5)
            if quadro is None:
                continue
            ultimo_id = quadro.id_quadro
            try:
                self._processar_quadro(quadro)
            except Exception as erro:
                with self._lock_estado:
                    self._total_falhas += 1
                    self._ultimo_erro = str(erro)

    def _processar_quadro(self, quadro: QuadroCamera) -> None:
        resultado = self._detector.processar(
            quadro.imagem_bgr,
            id_quadro=quadro.id_quadro,
            instante_monotonico_s=quadro.instante_monotonico_s,
        )
        estimativa = self._rastreador.atualizar(resultado.estimativa)
        sobreposta = desenhar_sobreposicao(
            quadro.imagem_bgr,
            resultado,
            estimativa,
            self._detector.configuracao,
        )
        publicado = ResultadoQuadroLinha(
            id_quadro=quadro.id_quadro,
            instante_monotonico_s=quadro.instante_monotonico_s,
            imagem_sobreposta=sobreposta,
            mascara=resultado.mascara,
            estimativa=estimativa,
            diagnostico=resultado.diagnostico,
        )
        with self._condicao:
            self._ultimo = publicado
            self._condicao.notify_all()
        with self._lock_estado:
            self._total_processados += 1
            self._ultimo_erro = ""
            self._instantes.append(monotonic())
