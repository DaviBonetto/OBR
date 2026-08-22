from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest


@pytest.fixture
def preparar_dataset_referencia():
    def preparar(tmp_path: Path, *, incluir_teste: bool = False) -> Path:
        dataset = tmp_path / "dataset"
        registros = []
        for tipo in ("reta", "curva_aberta", "curva_fechada", "intersecao"):
            for indice in range(3):
                relativo = Path("imagens") / tipo / f"{indice}.png"
                caminho = dataset / relativo
                caminho.parent.mkdir(parents=True, exist_ok=True)
                imagem = np.full((48, 64, 3), 220, dtype=np.uint8)
                cv2.line(imagem, (32, 47), (32, 0), (10, 10, 10), 8)
                sucesso, conteudo = cv2.imencode(".png", imagem)
                assert sucesso
                caminho.write_bytes(conteudo.tobytes())
                registros.append(
                    {
                        "divisao": "validacao",
                        "id_amostra": f"{tipo}:{indice}",
                        "imagem": relativo.as_posix(),
                        "sha256_imagem": hashlib.sha256(caminho.read_bytes()).hexdigest(),
                        "tipo_quadro": tipo,
                    }
                )
        if incluir_teste:
            registros.append(
                {
                    "divisao": "teste",
                    "id_amostra": "teste:0",
                    "imagem": "segredo.png",
                    "sha256_imagem": "0" * 64,
                    "tipo_quadro": "reta",
                }
            )
        (dataset / "indice.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in registros),
            encoding="utf-8",
        )
        return dataset

    return preparar
