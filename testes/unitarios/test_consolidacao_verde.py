import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from obr_oficial.dados.consolidacao_verde import (
    ConfiguracaoConsolidacaoVerde,
    ConsolidadorRotulosVerdes,
    ErroConsolidacaoVerde,
)


def _preparar_candidatas(tmp_path: Path, *, incluir_teste: bool = False) -> Path:
    pasta = tmp_path / "candidatas"
    mascaras = pasta / "mascaras"
    mascaras.mkdir(parents=True)
    especificacoes = [
        ("normal_treino", "treino", "normal", "antes_esquerda"),
        ("normal_validacao", "validacao", "normal", "antes_direita"),
        ("contrato_treino", "treino", "contrato", "sem_verde_negativo"),
        ("contrato_validacao", "validacao", "contrato", "sem_verde_negativo"),
        ("aprovada", "treino", "prioritaria", "depois_ignorar"),
        ("pendente", "validacao", "prioritaria", "antes_esquerda"),
        ("reprocessar", "treino", "prioritaria", "dois_antes_180"),
    ]
    if incluir_teste:
        especificacoes.append(("teste", "teste", "normal", "antes_esquerda"))
    registros = []
    for indice, (identificador, divisao, prioridade, categoria) in enumerate(especificacoes):
        mascara = np.zeros((24, 32), dtype=np.uint8)
        mascara[:, 10:22] = 255
        sucesso, codificada = cv2.imencode(".png", mascara)
        assert sucesso
        conteudo = codificada.tobytes()
        nome = f"{indice}.png"
        (mascaras / nome).write_bytes(conteudo)
        registros.append(
            {
                "id_amostra": identificador,
                "divisao": divisao,
                "prioridade": prioridade,
                "categoria_verde": categoria,
                "cruz_mista": False,
                "decisao_verde_esperada": "nenhuma",
                "origem": f"origem/{nome}",
                "mascara_candidata": f"mascaras/{nome}",
                "sha256_mascara": hashlib.sha256(conteudo).hexdigest(),
                "motivos_prioridade": [],
            }
        )
    (pasta / "candidatas.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in registros),
        encoding="utf-8",
    )
    revisoes = [
        {"id_amostra": "aprovada", "decisao": "aprovada", "observacao": "ok"},
        {
            "id_amostra": "reprocessar",
            "decisao": "reprocessar",
            "observacao": "ambigua",
        },
    ]
    (pasta / "revisoes.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in revisoes),
        encoding="utf-8",
    )
    return pasta


def test_consolida_verde_sem_promover_prioritaria_pendente(tmp_path: Path) -> None:
    candidatas = _preparar_candidatas(tmp_path)
    saida = tmp_path / "saida"

    manifesto = ConsolidadorRotulosVerdes(
        ConfiguracaoConsolidacaoVerde(candidatas, saida)
    ).consolidar()

    assert manifesto["pronto_para_treino_inicial"] is True
    assert manifesto["pronto_para_treino_final"] is False
    assert manifesto["quantidades"] == {
        "amostras": 7,
        "revisoes_explicitas_unicas": 2,
        "rotulos_seguros": 5,
        "mascaras_positivas": 3,
        "mascaras_vazias": 2,
        "fila_active_learning": 2,
        "treino_seguro": 3,
        "validacao_segura": 2,
        "aprovadas_regra_calibrada": 2,
        "aprovadas_contrato": 2,
        "aprovadas_auditoria_visual": 1,
    }
    anotacoes = {
        item["id_amostra"]: item
        for item in (
            json.loads(linha)
            for linha in (saida / "anotacoes.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    assert anotacoes["pendente"]["mascara"] is None
    assert anotacoes["reprocessar"]["mascara"] is None
    assert anotacoes["aprovada"]["estado_rotulo"] == "aprovada_por_auditoria_visual"
    assert (saida / "fila_active_learning.jsonl").read_text().count("\n") == 2


def test_recusa_teste_e_remove_saida_parcial(tmp_path: Path) -> None:
    candidatas = _preparar_candidatas(tmp_path, incluir_teste=True)
    (candidatas / "mascaras" / "7.png").unlink()
    saida = tmp_path / "saida"

    with pytest.raises(ErroConsolidacaoVerde, match="divisao de teste"):
        ConsolidadorRotulosVerdes(ConfiguracaoConsolidacaoVerde(candidatas, saida)).consolidar()

    assert not saida.exists()


def test_recusa_mascara_adulterada(tmp_path: Path) -> None:
    candidatas = _preparar_candidatas(tmp_path)
    (candidatas / "mascaras" / "0.png").write_bytes(b"adulterada")
    saida = tmp_path / "saida"

    with pytest.raises(ErroConsolidacaoVerde, match="Hash de mascara divergente"):
        ConsolidadorRotulosVerdes(ConfiguracaoConsolidacaoVerde(candidatas, saida)).consolidar()

    assert not saida.exists()
