import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch

from obr_oficial.treinamento.auditoria_rotulos import (
    ConfiguracaoAuditoriaRotulos,
    ErroAuditoriaRotulos,
    gerar_fila_auditoria_rotulos,
)
from obr_oficial.treinamento.segmentacao import ConfiguracaoTreinamento, LinhaNet


def _preparar_dataset(raiz: Path) -> None:
    registros = []
    for divisao, estado, indice in (
        ("treino", "aprovada_vazia_por_usuario", 1),
        ("validacao", "aprovada_vazia_por_contrato", 2),
    ):
        imagem_rel = Path("imagens") / divisao / f"{indice}.png"
        mascara_rel = Path("rotulos") / "mascaras" / divisao / f"{indice}.png"
        (raiz / imagem_rel).parent.mkdir(parents=True, exist_ok=True)
        (raiz / mascara_rel).parent.mkdir(parents=True, exist_ok=True)
        imagem = np.full((48, 64, 3), 220, dtype=np.uint8)
        mascara = np.zeros((48, 64), dtype=np.uint8)
        assert cv2.imwrite(str(raiz / imagem_rel), imagem)
        assert cv2.imwrite(str(raiz / mascara_rel), mascara)
        registros.append(
            {
                "versao": 1,
                "id_amostra": f"sessao:{indice}",
                "divisao": divisao,
                "tipo_quadro": "sem_linha",
                "trajetoria_desejada": "sem_linha",
                "imagem": imagem_rel.as_posix(),
                "mascara": mascara_rel.as_posix(),
                "estado_rotulo": estado,
            }
        )
    (raiz / "indice.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in registros), encoding="utf-8"
    )


def _checkpoint(caminho: Path) -> None:
    configuracao = ConfiguracaoTreinamento(
        largura=32,
        altura=24,
        roi_y=0.0,
        epocas=1,
        lote=1,
        taxa_aprendizado=0.001,
        decaimento_peso=0.0,
        paciencia=1,
        trabalhadores=0,
        semente=1,
        limiar=0.5,
        peso_bce=0.4,
        peso_dice=0.6,
        aumentos_fortes=False,
    )
    modelo = LinhaNet()
    with torch.no_grad():
        modelo.saida[-1].bias.fill_(10.0)
    torch.save(
        {
            "arquitetura": "linhanet",
            "estado_modelo": modelo.state_dict(),
            "configuracao": asdict(configuracao),
        },
        caminho,
    )


def test_gera_fila_com_vazias_manuais_e_desacordos(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    _preparar_dataset(dataset)
    checkpoint = tmp_path / "modelo.pt"
    _checkpoint(checkpoint)

    manifesto = gerar_fila_auditoria_rotulos(
        dataset,
        checkpoint,
        tmp_path / "saida",
        ConfiguracaoAuditoriaRotulos(confianca_minima=0.5, area_minima_normalizada=0),
    )

    assert manifesto["teste_aberto"] is False
    assert manifesto["vazias_analisadas"] == 2
    assert manifesto["candidatas"] == 2
    linhas = (tmp_path / "saida" / "candidatas.jsonl").read_text().splitlines()
    assert {json.loads(linha)["divisao"] for linha in linhas} == {"treino", "validacao"}
    assert len(list((tmp_path / "saida" / "mascaras_modelo").rglob("*.png"))) == 2


def test_recusa_sobrescrever_auditoria_existente(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    _preparar_dataset(dataset)
    checkpoint = tmp_path / "modelo.pt"
    _checkpoint(checkpoint)
    saida = tmp_path / "saida"
    saida.mkdir()
    (saida / "revisoes.jsonl").write_text("decisao humana", encoding="utf-8")

    with pytest.raises(ErroAuditoriaRotulos, match="ja existe"):
        gerar_fila_auditoria_rotulos(dataset, checkpoint, saida)
