"""Avaliacao geometrica somente em treino/validacao, nunca no teste fechado."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from obr_oficial.dados.referencia_centro import RepositorioReferenciaCentro
from obr_oficial.nucleo.contratos import EstadoDeteccao, EstimativaLinha, TipoCurva
from obr_oficial.percepcao.linha.detector_neural import (
    DetectorNeuralLinha,
    ErroDetectorNeural,
    ExtratorGeometriaLinha,
)
from obr_oficial.percepcao.linha.execucao_continua import desenhar_sobreposicao
from obr_oficial.percepcao.linha.rastreamento import RastreadorLinha
from obr_oficial.treinamento.segmentacao import carregar_indice_dataset


def _ler_imagem(caminho: Path, modo: int) -> np.ndarray:
    try:
        conteudo = caminho.read_bytes()
    except OSError as erro:
        raise ErroDetectorNeural(f"Arquivo da avaliacao ausente: {caminho}") from erro
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), modo)
    if imagem is None:
        raise ErroDetectorNeural(f"Arquivo da avaliacao invalido: {caminho}")
    return imagem


def _percentis(valores: list[float]) -> dict[str, float | int | None]:
    if not valores:
        return {"amostras": 0, "mediana": None, "p95": None, "maximo": None}
    return {
        "amostras": len(valores),
        "mediana": float(np.percentile(valores, 50)),
        "p95": float(np.percentile(valores, 95)),
        "maximo": max(valores),
    }


def _erros_centro_pixels(
    prevista: EstimativaLinha,
    referencia: EstimativaLinha,
    largura: int,
) -> list[float]:
    if not prevista.centro_linha or not referencia.centro_linha:
        return []
    erros = []
    for ponto_referencia in referencia.centro_linha:
        ponto_previsto = min(
            prevista.centro_linha,
            key=lambda ponto: abs(ponto.y - ponto_referencia.y),
        )
        if abs(ponto_previsto.y - ponto_referencia.y) <= 0.06:
            erros.append(abs(ponto_previsto.x - ponto_referencia.x) * (largura - 1))
    return erros


def _distancias_pontos_para_polilinha(
    pontos: np.ndarray,
    polilinha: np.ndarray,
) -> np.ndarray:
    if len(pontos) == 0 or len(polilinha) < 2:
        return np.empty(0, dtype=np.float64)
    inicios = polilinha[:-1]
    vetores = polilinha[1:] - inicios
    denominadores = np.sum(vetores * vetores, axis=1)
    resultados = []
    for ponto in pontos:
        deslocamentos = ponto - inicios
        parametros = np.divide(
            np.sum(deslocamentos * vetores, axis=1),
            denominadores,
            out=np.zeros_like(denominadores),
            where=denominadores > 0,
        )
        parametros = np.clip(parametros, 0.0, 1.0)
        projecoes = inicios + parametros[:, None] * vetores
        resultados.append(float(np.min(np.linalg.norm(projecoes - ponto, axis=1))))
    return np.asarray(resultados, dtype=np.float64)


def _amostrar_polilinha(polilinha: np.ndarray, quantidade: int = 24) -> np.ndarray:
    if len(polilinha) < 2:
        return polilinha.copy()
    comprimentos = np.linalg.norm(np.diff(polilinha, axis=0), axis=1)
    acumulados = np.concatenate(([0.0], np.cumsum(comprimentos)))
    total = float(acumulados[-1])
    if total <= 0.0:
        return polilinha[:1].copy()
    alvos = np.linspace(0.0, total, quantidade)
    amostras = []
    for alvo in alvos:
        segmento = min(
            int(np.searchsorted(acumulados, alvo, side="right") - 1),
            len(comprimentos) - 1,
        )
        inicio = acumulados[segmento]
        fracao = (alvo - inicio) / max(comprimentos[segmento], 1e-12)
        amostras.append(
            polilinha[segmento]
            + fracao * (polilinha[segmento + 1] - polilinha[segmento])
        )
    return np.asarray(amostras, dtype=np.float64)


def _erros_centro_humano_pixels(
    prevista: EstimativaLinha,
    pontos_humanos: list[dict[str, float]],
    largura: int,
    altura: int,
) -> list[float]:
    if len(prevista.centro_linha) < 2 or len(pontos_humanos) < 2:
        return []
    escala = np.array([largura - 1, altura - 1], dtype=np.float64)
    prevista_px = np.asarray(
        [[ponto.x, ponto.y] for ponto in prevista.centro_linha],
        dtype=np.float64,
    ) * escala
    humana_px = np.asarray(
        [[ponto["x"], ponto["y"]] for ponto in pontos_humanos],
        dtype=np.float64,
    ) * escala
    humana_amostrada = _amostrar_polilinha(humana_px, quantidade=len(prevista_px))
    ida = _distancias_pontos_para_polilinha(prevista_px, humana_px)
    volta = _distancias_pontos_para_polilinha(humana_amostrada, prevista_px)
    return np.concatenate((ida, volta)).tolist()


def _lado_curva(tipo: TipoCurva) -> str:
    if tipo in {TipoCurva.ESQUERDA_SUAVE, TipoCurva.ESQUERDA_FECHADA}:
        return "esquerda"
    if tipo in {TipoCurva.DIREITA_SUAVE, TipoCurva.DIREITA_FECHADA}:
        return "direita"
    return "reta"


def avaliar_referencia_humana(
    detector: DetectorNeuralLinha,
    raiz_dataset: Path,
    pasta_referencia: Path,
) -> dict[str, Any]:
    """Mede a geometria contra polilinhas desenhadas por humano, sem usar mascaras."""

    repositorio = RepositorioReferenciaCentro(raiz_dataset, pasta_referencia)
    anotacoes = repositorio.anotacoes
    resumo = repositorio.resumo()
    erros: list[float] = []
    erros_por_tipo: dict[str, list[float]] = {}
    erros_por_quadro: list[dict[str, Any]] = []
    curvas_avaliadas = 0
    lados_corretos = 0
    localizadas = 0

    for indice, item in enumerate(repositorio.amostras):
        id_amostra = str(item["id_amostra"])
        anotacao = anotacoes.get(id_amostra)
        if anotacao is None:
            continue
        imagem = _ler_imagem(
            repositorio.caminho_imagem(indice),
            cv2.IMREAD_COLOR,
        )
        estimativa = detector.processar(imagem, id_quadro=indice).estimativa
        if estimativa.estado is not EstadoDeteccao.PERDIDA:
            localizadas += 1
        pontos_humanos = anotacao["pontos"]
        erros_quadro = _erros_centro_humano_pixels(
            estimativa,
            pontos_humanos,
            detector.configuracao.largura,
            detector.configuracao.altura,
        )
        erros.extend(erros_quadro)
        tipo = str(item["tipo_quadro"])
        erros_por_tipo.setdefault(tipo, []).extend(erros_quadro)
        if erros_quadro:
            erros_por_quadro.append(
                {
                    "id_amostra": id_amostra,
                    "tipo_quadro": tipo,
                    "mediana_px": float(np.percentile(erros_quadro, 50)),
                    "p95_px": float(np.percentile(erros_quadro, 95)),
                    "maximo_px": max(erros_quadro),
                }
            )
        if tipo in {"curva_aberta", "curva_fechada"}:
            curvas_avaliadas += 1
            primeiro = pontos_humanos[0]
            ultimo = pontos_humanos[-1]
            deslocamento = float(ultimo["x"]) - float(primeiro["x"])
            lado_humano = "reta"
            if abs(deslocamento) >= 0.03:
                lado_humano = "direita" if deslocamento > 0 else "esquerda"
            if _lado_curva(estimativa.tipo_curva) == lado_humano:
                lados_corretos += 1

    metricas = _percentis(erros)
    referencia_completa = bool(resumo["completa"])
    mediana = metricas["mediana"]
    p95 = metricas["p95"]
    gate_erro = bool(
        referencia_completa
        and mediana is not None
        and p95 is not None
        and mediana <= 3.0
        and p95 <= 8.0
    )
    return {
        "versao_relatorio": 1,
        "divisao": "validacao",
        "teste_aberto": False,
        "origem_referencia": "humana_manual",
        "usa_mascara_como_referencia": False,
        "total_selecionado": int(resumo["total"]),
        "total_anotado": int(resumo["anotadas"]),
        "referencia_completa": referencia_completa,
        "taxa_localizacao": localizadas / max(1, int(resumo["anotadas"])),
        "erro_centro_pixels": metricas,
        "erro_centro_por_tipo_pixels": {
            tipo: _percentis(valores) for tipo, valores in sorted(erros_por_tipo.items())
        },
        "piores_quadros": sorted(
            erros_por_quadro,
            key=lambda item: item["p95_px"],
            reverse=True,
        )[:20],
        "lado_curva": {
            "amostras": curvas_avaliadas,
            "corretas": lados_corretos,
            "taxa": lados_corretos / max(1, curvas_avaliadas),
        },
        "gate": {
            "limite_mediana_px": 3.0,
            "limite_p95_px": 8.0,
            "mediana_aprovada": mediana is not None and mediana <= 3.0,
            "p95_aprovado": p95 is not None and p95 <= 8.0,
            "aprovado": gate_erro,
            "motivo": (
                "gate quantitativo aprovado"
                if gate_erro
                else "conclua todas as anotacoes humanas ou ajuste a geometria"
            ),
        },
    }


def avaliar_geometria_validacao(
    detector: DetectorNeuralLinha,
    raiz_dataset: Path,
) -> dict[str, Any]:
    """Mede centro, trajetoria e latencia na validacao congelada."""

    raiz_dataset = raiz_dataset.resolve()
    amostras = carregar_indice_dataset(raiz_dataset, "validacao")
    extrator_referencia = ExtratorGeometriaLinha(detector.configuracao)
    erros_centro: list[float] = []
    erros_atual: list[float] = []
    erros_objetivo: list[float] = []
    tempos_pre: list[float] = []
    tempos_inferencia: list[float] = []
    tempos_geometria: list[float] = []
    tempos_total: list[float] = []
    positivos = negativos = positivos_localizados = 0
    falsos_caminhos = falsos_alta_confianca = 0
    falsos_alta_confianca_temporais = 0
    intersecoes = intersecoes_retas = 0
    intersecoes_detectadas_por_tipo: dict[str, dict[str, int]] = {}
    ids_falsos_alta_confianca: list[str] = []
    erros_por_tipo: dict[str, list[float]] = {}
    erros_por_quadro: list[dict[str, Any]] = []
    rastreador = RastreadorLinha(detector.configuracao)
    sessao_anterior: str | None = None

    for indice, item in enumerate(amostras):
        imagem = _ler_imagem(raiz_dataset / item["imagem"], cv2.IMREAD_COLOR)
        mascara_referencia = _ler_imagem(
            raiz_dataset / item["mascara"],
            cv2.IMREAD_GRAYSCALE,
        )
        sessao = str(item["id_amostra"]).split(":", maxsplit=1)[0]
        if sessao != sessao_anterior:
            rastreador.reiniciar()
            sessao_anterior = sessao
        resultado = detector.processar(
            imagem,
            id_quadro=indice,
            instante_monotonico_s=indice * 0.1,
        )
        estimativa = resultado.estimativa
        tipo_quadro = str(item["tipo_quadro"])
        contagem_intersecao = intersecoes_detectadas_por_tipo.setdefault(
            tipo_quadro,
            {"quadros": 0, "detectadas": 0},
        )
        contagem_intersecao["quadros"] += 1
        if resultado.diagnostico.intersecao_detectada:
            contagem_intersecao["detectadas"] += 1
        estimativa_temporal = rastreador.atualizar(estimativa)
        tempos_pre.append(estimativa.tempos.pre_processamento_ms)
        tempos_inferencia.append(estimativa.tempos.inferencia_ms)
        tempos_geometria.append(estimativa.tempos.geometria_ms)
        tempos_total.append(estimativa.tempos.total_ms)
        tem_linha = bool(np.any(mascara_referencia >= 128))
        if not tem_linha:
            negativos += 1
            if estimativa.estado is not EstadoDeteccao.PERDIDA:
                falsos_caminhos += 1
            if (
                estimativa.estado is EstadoDeteccao.ENCONTRADA
                and estimativa.confianca >= detector.configuracao.limiar_encontrada
            ):
                falsos_alta_confianca += 1
                ids_falsos_alta_confianca.append(str(item["id_amostra"]))
            if estimativa_temporal.estado is EstadoDeteccao.ENCONTRADA:
                falsos_alta_confianca_temporais += 1
            continue

        positivos += 1
        if estimativa.estado is not EstadoDeteccao.PERDIDA:
            positivos_localizados += 1
        probabilidade_referencia = (mascara_referencia.astype(np.float32) / 255.0).clip(0, 1)
        _mascara, referencia, _diagnostico = extrator_referencia.extrair(
            probabilidade_referencia,
            id_quadro=indice,
            instante_monotonico_s=0.0,
        )
        erros_quadro = _erros_centro_pixels(
            estimativa,
            referencia,
            detector.configuracao.largura,
        )
        erros_centro.extend(erros_quadro)
        erros_por_tipo.setdefault(str(item["tipo_quadro"]), []).extend(erros_quadro)
        if erros_quadro:
            erros_por_quadro.append(
                {
                    "id_amostra": str(item["id_amostra"]),
                    "tipo_quadro": str(item["tipo_quadro"]),
                    "mediana_px": float(np.percentile(erros_quadro, 50)),
                    "p95_px": float(np.percentile(erros_quadro, 95)),
                    "maximo_px": max(erros_quadro),
                }
            )
        if estimativa.ponto_atual is not None and referencia.ponto_atual is not None:
            erros_atual.append(
                abs(estimativa.ponto_atual.x - referencia.ponto_atual.x)
                * (detector.configuracao.largura - 1)
            )
        if estimativa.ponto_objetivo is not None and referencia.centro_linha:
            alvo_referencia = min(
                referencia.centro_linha,
                key=lambda ponto: abs(ponto.y - estimativa.ponto_objetivo.y),
            )
            erros_objetivo.append(
                abs(estimativa.ponto_objetivo.x - alvo_referencia.x)
                * (detector.configuracao.largura - 1)
            )
        if item["tipo_quadro"] == "intersecao":
            intersecoes += 1
            if estimativa.tipo_curva is TipoCurva.RETA:
                intersecoes_retas += 1

    return {
        "versao_relatorio": 2,
        "divisao": "validacao",
        "teste_aberto": False,
        "total_quadros": len(amostras),
        "positivos": positivos,
        "negativos": negativos,
        "taxa_positivos_localizados": positivos_localizados / max(1, positivos),
        "falsos_caminhos_por_quadro": falsos_caminhos,
        "falsos_caminhos_alta_confianca_por_quadro": falsos_alta_confianca,
        "taxa_falsos_alta_confianca_por_quadro": falsos_alta_confianca / max(1, negativos),
        "ids_falsos_alta_confianca_por_quadro": ids_falsos_alta_confianca,
        "falsos_alta_confianca_apos_confirmacao_temporal": falsos_alta_confianca_temporais,
        "taxa_falsos_alta_confianca_apos_confirmacao_temporal": (
            falsos_alta_confianca_temporais / max(1, negativos)
        ),
        "divergencia_centro_derivado_pixels": _percentis(erros_centro),
        "divergencia_centro_por_tipo_pixels": {
            tipo: _percentis(valores) for tipo, valores in sorted(erros_por_tipo.items())
        },
        "piores_quadros_divergencia_centro": sorted(
            erros_por_quadro,
            key=lambda item: item["p95_px"],
            reverse=True,
        )[:20],
        "divergencia_ponto_atual_derivado_pixels": _percentis(erros_atual),
        "divergencia_ponto_objetivo_derivado_pixels": _percentis(erros_objetivo),
        "intersecoes": intersecoes,
        "intersecoes_classificadas_reta": intersecoes_retas,
        "taxa_intersecoes_retas": intersecoes_retas / max(1, intersecoes),
        "intersecoes_detectadas_por_tipo": {
            tipo: {
                **contagem,
                "taxa": contagem["detectadas"] / max(1, contagem["quadros"]),
            }
            for tipo, contagem in sorted(intersecoes_detectadas_por_tipo.items())
        },
        "latencia_pc_ms": {
            "pre_processamento": _percentis(tempos_pre),
            "inferencia": _percentis(tempos_inferencia),
            "geometria": _percentis(tempos_geometria),
            "total": _percentis(tempos_total),
        },
        "validade_referencia_centro": {
            "centro_anotado_por_humano": False,
            "referencia_derivada_da_mascara": True,
            "pode_aprovar_gate_de_erro_centro": False,
            "motivo": "dataset possui mascaras humanas, mas nao linha central humana",
        },
    }


def salvar_relatorio(relatorio: dict[str, Any], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def gerar_montagem_diagnostico(
    detector: DetectorNeuralLinha,
    raiz_dataset: Path,
    relatorio: dict[str, Any],
    destino: Path,
    *,
    quantidade: int = 12,
) -> None:
    """Desenha previsao vermelha e referencia verde nos piores quadros."""

    raiz_dataset = raiz_dataset.resolve()
    amostras = {
        str(item["id_amostra"]): item
        for item in carregar_indice_dataset(raiz_dataset, "validacao")
    }
    extrator_referencia = ExtratorGeometriaLinha(detector.configuracao)
    quadros = []
    for registro in relatorio["piores_quadros_divergencia_centro"][:quantidade]:
        item = amostras[registro["id_amostra"]]
        imagem = _ler_imagem(raiz_dataset / item["imagem"], cv2.IMREAD_COLOR)
        mascara_referencia = _ler_imagem(
            raiz_dataset / item["mascara"],
            cv2.IMREAD_GRAYSCALE,
        )
        resultado = detector.processar(imagem)
        _mascara, referencia, _diagnostico = extrator_referencia.extrair(
            (mascara_referencia.astype(np.float32) / 255.0).clip(0, 1),
            id_quadro=0,
            instante_monotonico_s=0.0,
        )
        visual = desenhar_sobreposicao(
            imagem,
            resultado,
            resultado.estimativa,
            detector.configuracao,
        )
        altura, largura = visual.shape[:2]
        y0 = round(altura * detector.configuracao.roi_y)
        pontos_referencia = np.array(
            [
                (
                    round(ponto.x * (largura - 1)),
                    round(y0 + ponto.y * (altura - y0 - 1)),
                )
                for ponto in referencia.centro_linha
            ],
            dtype=np.int32,
        )
        if len(pontos_referencia) >= 2:
            cv2.polylines(visual, [pontos_referencia], False, (50, 220, 50), 4, cv2.LINE_AA)
        legenda = (
            f"{item['tipo_quadro']}  p95={registro['p95_px']:.1f}px  "
            f"#{str(item['id_amostra']).rsplit(':', maxsplit=1)[-1]}"
        )
        cv2.rectangle(visual, (0, 0), (visual.shape[1], 36), (0, 0, 0), -1)
        cv2.putText(
            visual,
            legenda,
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        quadros.append(cv2.resize(visual, (480, 360), interpolation=cv2.INTER_AREA))
    if not quadros:
        raise ErroDetectorNeural("Nao existem falhas para montar")
    colunas = 3
    while len(quadros) % colunas:
        quadros.append(np.zeros_like(quadros[0]))
    linhas = [np.hstack(quadros[i : i + colunas]) for i in range(0, len(quadros), colunas)]
    montagem = np.vstack(linhas)
    destino.parent.mkdir(parents=True, exist_ok=True)
    sucesso, conteudo = cv2.imencode(".jpg", montagem, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not sucesso:
        raise ErroDetectorNeural("Falha ao codificar montagem de diagnostico")
    conteudo.tofile(destino)
