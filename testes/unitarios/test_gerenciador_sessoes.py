import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from obr_oficial.captura import ErroCaptura, GerenciadorSessoesCaptura
from obr_oficial.dispositivos.camera_base import MetricasImagem, QuadroCamera


def _quadro() -> QuadroCamera:
    return QuadroCamera(
        id_quadro=42,
        instante_monotonico_s=10.5,
        instante_utc="2026-08-18T12:00:00+00:00",
        imagem_bgr=np.full((48, 64, 3), 180, dtype=np.uint8),
        metricas=MetricasImagem(180.0, 0.0, 0.0, 15.0),
    )


def test_sessao_salva_png_manifesto_registro_e_hash(tmp_path: Path) -> None:
    gerenciador = GerenciadorSessoesCaptura(tmp_path)
    iniciado = gerenciador.iniciar(
        {"nome": "Pátio com Sol", "local": "escola"},
        {"nome_perfil": "camera_provisoria"},
    )

    registro = gerenciador.capturar(_quadro(), {"tipo_quadro": "curva_fechada"})

    pasta = Path(iniciado["pasta"])
    imagem = pasta / registro["arquivo"]
    assert imagem.is_file()
    assert registro["sha256"] == hashlib.sha256(imagem.read_bytes()).hexdigest()

    manifesto = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    assert manifesto["capturas"] == 1
    assert manifesto["camera"]["nome_perfil"] == "camera_provisoria"

    linhas = (pasta / "capturas.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 1
    assert json.loads(linhas[0])["contexto"]["tipo_quadro"] == "curva_fechada"

    finalizado = gerenciador.finalizar()
    assert finalizado["ultima_sessao"]["estado"] == "finalizada"


def test_nao_captura_sem_sessao(tmp_path: Path) -> None:
    gerenciador = GerenciadorSessoesCaptura(tmp_path)

    with pytest.raises(ErroCaptura, match="Inicie uma sessao"):
        gerenciador.capturar(_quadro())


def test_nao_inicia_duas_sessoes_ao_mesmo_tempo(tmp_path: Path) -> None:
    gerenciador = GerenciadorSessoesCaptura(tmp_path)
    gerenciador.iniciar({"nome": "primeira"}, {})

    with pytest.raises(ErroCaptura, match="Ja existe"):
        gerenciador.iniciar({"nome": "segunda"}, {})


def test_conta_categorias_verdes_no_manifesto(tmp_path: Path) -> None:
    gerenciador = GerenciadorSessoesCaptura(tmp_path)
    gerenciador.iniciar({"nome": "verde"}, {})

    gerenciador.capturar(_quadro(), {"categoria_verde": "antes_esquerda"})
    gerenciador.capturar(_quadro(), {"categoria_verde": "antes_esquerda"})
    gerenciador.capturar(_quadro(), {"categoria_verde": "depois_ignorar"})

    contagens = gerenciador.obter_estado()["sessao"]["contagens_por_categoria"]
    assert contagens == {"antes_esquerda": 2, "depois_ignorar": 1}
