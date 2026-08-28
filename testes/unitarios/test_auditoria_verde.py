import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest

from obr_oficial.captura.protocolo_verde import contexto_quadro_verde
from obr_oficial.dados import (
    CuradorDatasetVerde,
    ErroAuditoriaVerde,
    carregar_plano_curadoria_verde,
)


def _criar_sessao(
    raiz: Path,
    nome: str,
    estado: str,
    contextos: list[dict[str, object]],
    valor_inicial: int,
) -> None:
    pasta = raiz / nome
    quadros = pasta / "quadros"
    quadros.mkdir(parents=True)
    registros = []
    inicio = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    for indice, contexto in enumerate(contextos):
        numero = indice + 1
        imagem = np.full((48, 64, 3), valor_inicial + indice, dtype=np.uint8)
        sucesso, codificada = cv2.imencode(".png", imagem)
        assert sucesso
        conteudo = codificada.tobytes()
        relativo = Path("quadros") / f"quadro_{numero:06d}.png"
        (pasta / relativo).write_bytes(conteudo)
        registros.append(
            {
                "versao_registro": 1,
                "numero": numero,
                "arquivo": relativo.as_posix(),
                "sha256": hashlib.sha256(conteudo).hexdigest(),
                "captura_utc": (inicio + timedelta(seconds=indice)).isoformat(),
                "quadro": {"largura": 64, "altura": 48},
                "metricas": {"brilho_medio": float(valor_inicial + indice)},
                "contexto": contexto_quadro_verde(contexto),
            }
        )
    manifesto = {
        "versao_manifesto": 1,
        "id_sessao": nome,
        "estado": estado,
        "contexto": {"local": nome},
        "capturas": len(registros),
    }
    (pasta / "manifesto.json").write_text(
        json.dumps(manifesto),
        encoding="utf-8",
    )
    (pasta / "capturas.jsonl").write_text(
        "".join(json.dumps(registro) + "\n" for registro in registros),
        encoding="utf-8",
    )


def _preparar_cenario(tmp_path: Path) -> tuple[Path, Path]:
    raiz = tmp_path / "brutos"
    _criar_sessao(
        raiz,
        "sessao_treino",
        "ativa",
        [
            {"categoria_verde": "antes_esquerda", "cruz_mista": True},
            {"categoria_verde": "antes_esquerda", "cruz_mista": True},
            {"categoria_verde": "antes_esquerda", "cruz_mista": True},
            {"categoria_verde": "sem_verde_negativo"},
        ],
        100,
    )
    _criar_sessao(
        raiz,
        "sessao_validacao",
        "finalizada",
        [{"categoria_verde": "depois_ignorar"}],
        110,
    )
    _criar_sessao(
        raiz,
        "sessao_teste",
        "finalizada",
        [{"categoria_verde": "sem_verde_negativo"}],
        120,
    )
    plano = {
        "nome": "verde_teste_v1",
        "versao": 1,
        "snapshot": {"sha256": "a" * 64},
        "correcoes": [
            {
                "id": "corrigir_mista",
                "sessao": "sessao_treino",
                "numero_inicio": 1,
                "numero_fim": 3,
                "acao": "corrigir_contexto",
                "alteracoes": {"cruz_mista": False},
                "motivo": "erro conhecido",
            },
            {
                "id": "excluir_ambigua",
                "sessao": "sessao_treino",
                "numero_inicio": 4,
                "numero_fim": 4,
                "acao": "excluir",
                "alteracoes": {},
                "motivo": "geometria ambigua",
            },
        ],
        "sessoes_recuperadas": ["sessao_treino"],
        "divisoes": {
            "treino": ["sessao_treino"],
            "validacao": ["sessao_validacao"],
            "teste": ["sessao_teste"],
        },
        "selecao_temporal": {
            "limiar_diferenca_media_64x48": 2.0,
            "intervalo_nova_sequencia_s": 5.0,
            "categorias_sem_reducao": [
                "depois_ignorar",
                "sem_verde_negativo",
            ],
        },
    }
    caminho_plano = tmp_path / "plano.json"
    caminho_plano.write_text(json.dumps(plano), encoding="utf-8")
    return raiz, caminho_plano


def test_cura_sem_alterar_bruto_e_recalcula_semantica(tmp_path: Path) -> None:
    raiz, caminho_plano = _preparar_cenario(tmp_path)
    hashes_antes = {
        caminho: hashlib.sha256(caminho.read_bytes()).hexdigest()
        for caminho in raiz.rglob("*")
        if caminho.is_file()
    }
    saida = tmp_path / "verde_v1"

    manifesto = CuradorDatasetVerde(
        raiz,
        saida,
        carregar_plano_curadoria_verde(caminho_plano),
    ).preparar()

    assert manifesto["originais_alterados"] is False
    assert manifesto["total_bruto"] == 6
    assert manifesto["total_excluido_manualmente"] == 1
    assert manifesto["total_redundante_temporal"] == 1
    assert manifesto["total_selecionado"] == 4
    assert manifesto["correcoes_aplicadas"] == {
        "corrigir_mista": 3,
        "excluir_ambigua": 1,
    }
    assert manifesto["integridade"]["hashes_png_verificados"] == 6
    assert hashes_antes == {
        caminho: hashlib.sha256(caminho.read_bytes()).hexdigest()
        for caminho in raiz.rglob("*")
        if caminho.is_file()
    }

    registros = [
        json.loads(linha)
        for linha in (saida / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    corrigido = next(item for item in registros if item["id_amostra"] == "sessao_treino:000001")
    assert corrigido["contexto_bruto"]["cruz_mista"] is True
    assert corrigido["contexto_efetivo"]["cruz_mista"] is False
    assert corrigido["contexto_efetivo"]["marcador_depois_presente"] is False
    redundante = next(item for item in registros if item["id_amostra"] == "sessao_treino:000002")
    excluido = next(item for item in registros if item["id_amostra"] == "sessao_treino:000004")
    assert redundante["motivos_rejeicao"] == ["quase_duplicata_temporal"]
    assert excluido["motivos_rejeicao"] == ["exclusao_manual"]


def test_hash_divergente_aborta_sem_deixar_saida(tmp_path: Path) -> None:
    raiz, caminho_plano = _preparar_cenario(tmp_path)
    imagem = raiz / "sessao_treino" / "quadros" / "quadro_000001.png"
    imagem.write_bytes(imagem.read_bytes() + b"alterado")
    saida = tmp_path / "verde_v1"

    with pytest.raises(ErroAuditoriaVerde, match="Hash divergente"):
        CuradorDatasetVerde(
            raiz,
            saida,
            carregar_plano_curadoria_verde(caminho_plano),
        ).preparar()

    assert not saida.exists()
    assert not list(tmp_path.glob(".verde_v1.tmp-*"))
