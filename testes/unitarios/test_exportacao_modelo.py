from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest
import torch

from obr_oficial.implantacao.exportacao_modelo import (
    ErroExportacaoModelo,
    carregar_candidato,
    exportar_onnx,
    sha256_arquivo,
)
from obr_oficial.treinamento.segmentacao import ConfiguracaoTreinamento, criar_modelo


def _criar_checkpoint(caminho: Path) -> ConfiguracaoTreinamento:
    configuracao = ConfiguracaoTreinamento(
        largura=64,
        altura=32,
        roi_y=0.3,
        epocas=1,
        lote=1,
        taxa_aprendizado=1e-3,
        decaimento_peso=0.0,
        paciencia=1,
        trabalhadores=0,
        semente=7,
        limiar=0.5,
        peso_bce=0.4,
        peso_dice=0.6,
        aumentos_fortes=False,
    )
    modelo = criar_modelo("linhanet", pretreinado=False)
    torch.save(
        {
            "arquitetura": "linhanet",
            "configuracao": asdict(configuracao),
            "estado_modelo": modelo.state_dict(),
        },
        caminho,
    )
    return configuracao


def test_carrega_checkpoint_e_confere_hash(tmp_path: Path) -> None:
    checkpoint = tmp_path / "modelo.pt"
    configuracao = _criar_checkpoint(checkpoint)

    candidato = carregar_candidato(
        checkpoint,
        sha256_esperado=sha256_arquivo(checkpoint).upper(),
    )

    assert candidato.arquitetura == "linhanet"
    assert candidato.configuracao == configuracao
    assert candidato.modelo.training is False


def test_recusa_checkpoint_com_hash_divergente(tmp_path: Path) -> None:
    checkpoint = tmp_path / "modelo.pt"
    _criar_checkpoint(checkpoint)

    with pytest.raises(ErroExportacaoModelo, match="SHA-256"):
        carregar_candidato(checkpoint, sha256_esperado="0" * 64)


def test_exporta_onnx_autocontido(tmp_path: Path) -> None:
    onnx = pytest.importorskip("onnx")
    checkpoint = tmp_path / "modelo.pt"
    _criar_checkpoint(checkpoint)
    candidato = carregar_candidato(checkpoint)
    destino = tmp_path / "modelo.onnx"

    exportar_onnx(candidato, destino)

    modelo_onnx = onnx.load(destino)
    assert destino.is_file()
    assert modelo_onnx.graph.input[0].name == "imagem"
    assert modelo_onnx.graph.output[0].name == "logits"
