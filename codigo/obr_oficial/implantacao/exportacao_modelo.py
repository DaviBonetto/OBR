"""Exporta a segmentacao para ONNX e verifica equivalencia numerica."""

from __future__ import annotations

import hashlib
import io
import json
import platform
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

import numpy as np
import torch

from obr_oficial.treinamento.segmentacao import (
    AcumuladorMetricas,
    ConfiguracaoTreinamento,
    DatasetSegmentacaoLinha,
    ErroTreinamentoSegmentacao,
    criar_modelo,
)


class ErroExportacaoModelo(RuntimeError):
    """Indica um artefato invalido ou uma exportacao nao equivalente."""


@dataclass(frozen=True, slots=True)
class CandidatoCarregado:
    """Checkpoint validado e pronto para avaliacao ou exportacao."""

    modelo: torch.nn.Module
    arquitetura: str
    configuracao: ConfiguracaoTreinamento
    sha256: str


def sha256_arquivo(caminho: Path) -> str:
    """Calcula o SHA-256 sem carregar arquivos grandes inteiros na memoria."""

    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def carregar_candidato(
    checkpoint: Path,
    *,
    sha256_esperado: str | None = None,
) -> CandidatoCarregado:
    """Carrega somente pesos locais confiaveis e valida seus metadados."""

    checkpoint = checkpoint.resolve()
    if not checkpoint.is_file():
        raise ErroExportacaoModelo(f"Checkpoint ausente: {checkpoint}")
    sha256 = sha256_arquivo(checkpoint)
    if sha256_esperado is not None and sha256.lower() != sha256_esperado.lower():
        raise ErroExportacaoModelo(
            f"SHA-256 do checkpoint diverge: esperado {sha256_esperado}, obtido {sha256}"
        )
    try:
        pacote = torch.load(checkpoint, map_location="cpu", weights_only=True)
        arquitetura = str(pacote["arquitetura"])
        configuracao = ConfiguracaoTreinamento(**pacote["configuracao"])
        modelo = criar_modelo(arquitetura, pretreinado=False)
        modelo.load_state_dict(pacote["estado_modelo"], strict=True)
    except (KeyError, TypeError, RuntimeError, ErroTreinamentoSegmentacao) as erro:
        raise ErroExportacaoModelo("Checkpoint incompativel com o codigo atual") from erro
    modelo.eval()
    return CandidatoCarregado(modelo, arquitetura, configuracao, sha256)


def avaliar_validacao(
    candidato: CandidatoCarregado,
    raiz_dataset: Path,
    *,
    limiar: float,
    lote: int = 16,
) -> dict[str, float]:
    """Recalcula as metricas usando exclusivamente a divisao de validacao."""

    dataset = DatasetSegmentacaoLinha(raiz_dataset.resolve(), candidato.configuracao, "validacao")
    acumulador = AcumuladorMetricas(
        limiar,
        candidato.configuracao.area_minima_negativo,
    )
    carregador = torch.utils.data.DataLoader(dataset, batch_size=lote, shuffle=False)
    with torch.inference_mode():
        for imagens, mascaras in carregador:
            acumulador.adicionar(candidato.modelo(imagens), mascaras)
    return acumulador.calcular()


def _entradas_paridade(
    candidato: CandidatoCarregado,
    raiz_dataset: Path,
    quantidade_reais: int,
) -> list[np.ndarray]:
    configuracao = candidato.configuracao
    gerador = np.random.default_rng(configuracao.semente)
    entradas = [
        gerador.normal(
            0.0,
            1.0,
            size=(1, 3, configuracao.altura, configuracao.largura),
        ).astype(np.float32)
    ]
    dataset = DatasetSegmentacaoLinha(raiz_dataset.resolve(), configuracao, "validacao")
    quantidade = min(max(1, quantidade_reais), len(dataset))
    indices = np.linspace(0, len(dataset) - 1, quantidade, dtype=int)
    entradas.extend(dataset[int(indice)][0].numpy()[None] for indice in indices)
    return entradas


def exportar_onnx(
    candidato: CandidatoCarregado,
    destino: Path,
    *,
    opset: int = 18,
) -> None:
    """Exporta uma entrada fixa, adequada ao caminho de tempo real do robo."""

    destino = destino.resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)
    configuracao = candidato.configuracao
    exemplo = torch.zeros(1, 3, configuracao.altura, configuracao.largura)
    try:
        # O exportador imprime simbolos Unicode mesmo com verbose=False. O log interno e
        # capturado para a CLI funcionar tambem em consoles Windows com encoding CP1252.
        with redirect_stdout(io.StringIO()):
            torch.onnx.export(
                candidato.modelo,
                (exemplo,),
                destino,
                input_names=["imagem"],
                output_names=["logits"],
                opset_version=opset,
                dynamo=True,
                external_data=False,
            )
        import onnx

        onnx.checker.check_model(onnx.load(destino))
    except (ImportError, ModuleNotFoundError) as erro:
        raise ErroExportacaoModelo(
            "Dependencias ONNX ausentes; instale o extra 'implantacao'"
        ) from erro
    except Exception as erro:
        raise ErroExportacaoModelo(f"Falha ao exportar ou validar ONNX: {erro}") from erro


def comparar_onnx(
    candidato: CandidatoCarregado,
    modelo_onnx: Path,
    raiz_dataset: Path,
    *,
    limiar: float,
    quantidade_reais: int = 8,
) -> dict[str, float | int | bool]:
    """Compara logits e mascaras do PyTorch com o ONNX Runtime."""

    try:
        import onnxruntime as ort
    except (ImportError, ModuleNotFoundError) as erro:
        raise ErroExportacaoModelo("ONNX Runtime ausente; instale o extra 'implantacao'") from erro
    sessao = ort.InferenceSession(
        str(modelo_onnx.resolve()),
        providers=["CPUExecutionProvider"],
    )
    diferencas_maximas: list[float] = []
    diferencas_medias: list[float] = []
    pixels_iguais = 0
    pixels_totais = 0
    entradas = _entradas_paridade(candidato, raiz_dataset, quantidade_reais)
    with torch.inference_mode():
        for entrada in entradas:
            pytorch = candidato.modelo(torch.from_numpy(entrada)).numpy()
            resultado_onnx = sessao.run(["logits"], {"imagem": entrada})[0]
            diferenca = np.abs(pytorch - resultado_onnx)
            diferencas_maximas.append(float(np.max(diferenca)))
            diferencas_medias.append(float(np.mean(diferenca)))
            mascara_pytorch = pytorch >= np.log(limiar / (1.0 - limiar))
            mascara_onnx = resultado_onnx >= np.log(limiar / (1.0 - limiar))
            pixels_iguais += int(np.count_nonzero(mascara_pytorch == mascara_onnx))
            pixels_totais += int(mascara_pytorch.size)
    diferenca_maxima = max(diferencas_maximas)
    concordancia = pixels_iguais / pixels_totais
    return {
        "amostras": len(entradas),
        "diferenca_absoluta_maxima_logits": diferenca_maxima,
        "diferenca_absoluta_media_logits": mean(diferencas_medias),
        "concordancia_mascaras": concordancia,
        "gate_diferenca_maxima": 1e-3,
        "gate_concordancia_mascaras": 0.999,
        "aprovado": diferenca_maxima <= 1e-3 and concordancia >= 0.999,
    }


def benchmark_onnx(
    modelo_onnx: Path,
    configuracao: ConfiguracaoTreinamento,
    *,
    aquecimentos: int = 10,
    iteracoes: int = 50,
) -> dict[str, float | int | str]:
    """Mede somente inferencia ONNX local; nao representa o Raspberry Pi."""

    try:
        import onnxruntime as ort
    except (ImportError, ModuleNotFoundError) as erro:
        raise ErroExportacaoModelo("ONNX Runtime ausente; instale o extra 'implantacao'") from erro
    sessao = ort.InferenceSession(
        str(modelo_onnx.resolve()),
        providers=["CPUExecutionProvider"],
    )
    entrada = np.zeros((1, 3, configuracao.altura, configuracao.largura), dtype=np.float32)
    for _ in range(aquecimentos):
        sessao.run(["logits"], {"imagem": entrada})
    tempos_ms = []
    for _ in range(iteracoes):
        inicio = perf_counter()
        sessao.run(["logits"], {"imagem": entrada})
        tempos_ms.append((perf_counter() - inicio) * 1000.0)
    return {
        "escopo": "computador_local; nao_e_benchmark_do_raspberry_pi_5",
        "iteracoes": iteracoes,
        "media_ms": mean(tempos_ms),
        "p50_ms": float(np.percentile(tempos_ms, 50)),
        "p95_ms": float(np.percentile(tempos_ms, 95)),
    }


def preparar_pacote(
    checkpoint: Path,
    destino_onnx: Path,
    raiz_dataset: Path,
    *,
    limiar: float,
    sha256_checkpoint_esperado: str | None = None,
    sha256_dataset: str | None = None,
    sha256_pacote_resultados: str | None = None,
) -> dict[str, Any]:
    """Executa a trilha auditavel completa sem consultar a divisao de teste."""

    candidato = carregar_candidato(checkpoint, sha256_esperado=sha256_checkpoint_esperado)
    exportar_onnx(candidato, destino_onnx)
    validacao = avaliar_validacao(candidato, raiz_dataset, limiar=limiar)
    paridade = comparar_onnx(candidato, destino_onnx, raiz_dataset, limiar=limiar)
    if not paridade["aprovado"]:
        raise ErroExportacaoModelo(f"ONNX divergiu do PyTorch: {paridade}")
    benchmark = benchmark_onnx(destino_onnx, candidato.configuracao)
    dice_aprovado = validacao["dice"] >= 0.95
    fpr_aprovado = validacao["taxa_falso_positivo_negativos_significativos"] <= 0.10
    return {
        "versao_manifesto": 1,
        "estado": "candidato_fase4; benchmark_raspberry_pendente",
        "arquitetura": candidato.arquitetura,
        "entrada": {
            "formato": "NCHW_RGB_normalizado_imagenet",
            "dimensoes": [1, 3, candidato.configuracao.altura, candidato.configuracao.largura],
            "roi_y": candidato.configuracao.roi_y,
        },
        "pos_processamento": {"sigmoid": True, "limiar": limiar},
        "origem": {
            "checkpoint": checkpoint.name,
            "sha256_checkpoint": candidato.sha256,
            "sha256_dataset_v2": sha256_dataset,
            "sha256_pacote_resultados_t4": sha256_pacote_resultados,
        },
        "onnx": {
            "arquivo": destino_onnx.name,
            "sha256": sha256_arquivo(destino_onnx),
            "opset": 18,
            "paridade": paridade,
        },
        "validacao_limiar_calibrado": validacao,
        "gates_validacao": {
            "dice_minimo": 0.95,
            "fpr_significativo_maximo": 0.10,
            "dice_aprovado": dice_aprovado,
            "fpr_aprovado": fpr_aprovado,
            "aprovado": dice_aprovado and fpr_aprovado,
        },
        "benchmark_onnx": benchmark,
        "ambiente_exportacao": {
            "python": platform.python_version(),
            "plataforma": platform.platform(),
            "torch": torch.__version__,
        },
        "auditoria": {
            "teste_aberto": False,
            "motores_acionados": False,
            "benchmark_raspberry_pi_5_executado": False,
        },
    }


def salvar_manifesto(manifesto: dict[str, Any], destino: Path) -> None:
    """Salva o manifesto legivel e estavel para revisao no Git."""

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
