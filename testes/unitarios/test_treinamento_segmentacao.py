import json
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch

from obr_oficial.treinamento.segmentacao import (
    AcumuladorMetricas,
    AumentadorRobusto,
    ConfiguracaoTreinamento,
    DatasetSegmentacaoLinha,
    ErroTreinamentoSegmentacao,
    LinhaNet,
    PerdaBceDice,
    SegmentadorLRASPP,
    carregar_indice_dataset,
)


def _configuracao() -> ConfiguracaoTreinamento:
    return ConfiguracaoTreinamento(
        largura=96,
        altura=64,
        roi_y=0.25,
        epocas=2,
        lote=2,
        taxa_aprendizado=0.001,
        decaimento_peso=0.0001,
        paciencia=1,
        trabalhadores=0,
        semente=42,
        limiar=0.5,
        peso_bce=0.4,
        peso_dice=0.6,
        aumentos_fortes=True,
    )


def _dataset(tmp_path: Path, divisao: str = "treino") -> Path:
    (tmp_path / "imagens").mkdir()
    (tmp_path / "rotulos").mkdir()
    imagem = np.full((80, 120, 3), 210, dtype=np.uint8)
    cv2.rectangle(imagem, (48, 0), (72, 79), (5, 5, 5), -1)
    mascara = np.zeros((64, 96), dtype=np.uint8)
    mascara[:, 38:58] = 255
    assert cv2.imwrite(str(tmp_path / "imagens" / "quadro.png"), imagem)
    assert cv2.imwrite(str(tmp_path / "rotulos" / "mascara.png"), mascara)
    registro = {
        "id_amostra": "amostra:1",
        "divisao": divisao,
        "tipo_quadro": "reta",
        "imagem": "imagens/quadro.png",
        "mascara": "rotulos/mascara.png",
    }
    (tmp_path / "indice.jsonl").write_text(json.dumps(registro) + "\n", encoding="utf-8")
    return tmp_path


def test_dataset_aplica_roi_e_preserva_mascara_binaria(tmp_path: Path) -> None:
    raiz = _dataset(tmp_path)
    np.random.seed(5)

    imagem, mascara = DatasetSegmentacaoLinha(raiz, _configuracao(), "treino")[0]

    assert imagem.shape == (3, 64, 96)
    assert mascara.shape == (1, 64, 96)
    assert set(torch.unique(mascara).tolist()) <= {0.0, 1.0}
    assert torch.isfinite(imagem).all()


def test_aumentos_extremos_nao_alteram_formato_da_mascara() -> None:
    imagem = np.full((64, 96, 3), 180, dtype=np.uint8)
    mascara = np.zeros((64, 96), dtype=np.uint8)
    mascara[:, 40:56] = 255
    aumentador = AumentadorRobusto(forte=True)

    for semente in range(20):
        np.random.seed(semente)
        aumentada, alvo = aumentador(imagem, mascara)
        assert aumentada.shape == imagem.shape
        assert alvo.shape == mascara.shape
        assert set(np.unique(alvo).tolist()) <= {0, 255}


def test_indice_recusa_teste(tmp_path: Path) -> None:
    raiz = _dataset(tmp_path, divisao="teste")
    with pytest.raises(ErroTreinamentoSegmentacao, match="contaminado"):
        carregar_indice_dataset(raiz, "treino")
    with pytest.raises(ErroTreinamentoSegmentacao, match="proibida"):
        carregar_indice_dataset(raiz, "teste")


@pytest.mark.parametrize(
    "modelo",
    [LinhaNet(), SegmentadorLRASPP(pretreinado=False)],
    ids=["linhanet", "lraspp"],
)
def test_modelos_produzem_um_logit_por_pixel(modelo: torch.nn.Module) -> None:
    modelo.eval()
    entrada = torch.randn(1, 3, 64, 96)
    with torch.inference_mode():
        saida = modelo(entrada)
    assert saida.shape == (1, 1, 64, 96)


def test_linhanet_cabe_no_orcamento_inicial() -> None:
    assert sum(parametro.numel() for parametro in LinhaNet().parameters()) < 50_000


def test_perda_e_metricas_reagem_a_previsao_correta() -> None:
    alvo = torch.tensor([[[[0.0, 1.0], [0.0, 1.0]]]])
    logits_bons = torch.tensor([[[[-8.0, 8.0], [-8.0, 8.0]]]])
    logits_ruins = -logits_bons
    perda = PerdaBceDice(0.4, 0.6)
    assert perda(logits_bons, alvo) < perda(logits_ruins, alvo)

    acumulador = AcumuladorMetricas(0.5)
    acumulador.adicionar(logits_bons, alvo)
    metricas = acumulador.calcular()
    assert metricas["dice"] == pytest.approx(1.0)
    assert metricas["iou"] == pytest.approx(1.0)
