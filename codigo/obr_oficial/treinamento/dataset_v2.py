"""Consolida a auditoria humana no dataset da Fase 3 V2."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np


class ErroDatasetV2(ValueError):
    """Indica uma consolidacao incompleta ou contaminada."""


def _sha256_bytes(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _sha256_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _ler_jsonl(caminho: Path) -> list[dict[str, Any]]:
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    return [json.loads(linha) for linha in linhas if linha]


def _ler_imagem(caminho: Path, modo: int) -> np.ndarray:
    imagem = cv2.imdecode(np.frombuffer(caminho.read_bytes(), dtype=np.uint8), modo)
    if imagem is None:
        raise ErroDatasetV2(f"Imagem invalida: {caminho}")
    return imagem


def _gravar_png(caminho: Path, imagem: np.ndarray) -> None:
    sucesso, codificada = cv2.imencode(".png", imagem)
    if not sucesso:
        raise ErroDatasetV2(f"Falha ao codificar mascara: {caminho}")
    caminho.write_bytes(codificada.tobytes())


def _reconstruir_intersecao(imagem: np.ndarray, tamanho: tuple[int, int]) -> np.ndarray:
    """Recupera a faixa preta extrema de intersecoes T revisadas como incorretas."""

    y0 = round(imagem.shape[0] * 0.30)
    roi = cv2.resize(imagem[y0:], tamanho, interpolation=cv2.INTER_AREA)
    cinza = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    suavizada = cv2.GaussianBlur(cinza, (5, 5), 0)
    _, mascara = cv2.threshold(
        suavizada,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    mascara = cv2.morphologyEx(
        mascara,
        cv2.MORPH_CLOSE,
        np.ones((5, 5), dtype=np.uint8),
    )
    quantidade, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(mascara, 8)
    limpa = np.zeros_like(mascara)
    area_minima = max(64, round(mascara.size * 0.002))
    for rotulo in range(1, quantidade):
        if estatisticas[rotulo, cv2.CC_STAT_AREA] >= area_minima:
            limpa[rotulos == rotulo] = 255
    area = float(np.mean(limpa > 0))
    if not 0.20 <= area <= 0.90:
        raise ErroDatasetV2(f"Mascara reconstruida fora do limite seguro: area={area:.4f}")
    return limpa


def _empacotar(raiz: Path, destino: Path) -> None:
    if destino.exists():
        raise ErroDatasetV2(f"Arquivo V2 ja existe: {destino}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipado:
        for caminho in sorted(item for item in raiz.rglob("*") if item.is_file()):
            relativa = caminho.relative_to(raiz).as_posix()
            info = zipfile.ZipInfo(relativa, date_time=(2026, 8, 22, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zipado.writestr(info, caminho.read_bytes(), compresslevel=6)


def consolidar_dataset_v2(
    dataset_v1: Path,
    auditoria: Path,
    saida: Path,
    arquivo_zip: Path,
    manifesto_publico: Path,
) -> dict[str, Any]:
    """Aplica decisoes humanas, preserva negativos e gera um ZIP reproduzivel."""

    dataset_v1 = dataset_v1.resolve()
    auditoria = auditoria.resolve()
    saida = saida.resolve()
    arquivo_zip = arquivo_zip.resolve()
    manifesto_publico = manifesto_publico.resolve()
    if saida.exists():
        raise ErroDatasetV2(f"Saida V2 ja existe: {saida}")
    if arquivo_zip.exists():
        raise ErroDatasetV2(f"ZIP V2 ja existe: {arquivo_zip}")
    indice = _ler_jsonl(dataset_v1 / "indice.jsonl")
    if any(item["divisao"] == "teste" for item in indice):
        raise ErroDatasetV2("Dataset V1 contaminado pela divisao de teste")
    candidatas = _ler_jsonl(auditoria / "candidatas.jsonl")
    eventos = _ler_jsonl(auditoria / "revisoes.jsonl")
    revisoes = {str(item["id_amostra"]): item for item in eventos}
    if len(revisoes) != len(candidatas):
        raise ErroDatasetV2("Auditoria humana ainda possui pendencias")
    candidatas_por_id = {str(item["id_amostra"]): item for item in candidatas}
    indice_por_id = {str(item["id_amostra"]): item for item in indice}
    if not candidatas_por_id.keys() <= indice_por_id.keys():
        raise ErroDatasetV2("Auditoria contem amostra desconhecida")

    shutil.copytree(dataset_v1, saida)
    contagens: Counter[str] = Counter()
    for id_amostra, candidata in candidatas_por_id.items():
        item = indice_por_id[id_amostra]
        decisao = str(revisoes[id_amostra]["decisao"])
        caminho_mascara = saida / str(item["mascara"])
        mascara_atual = _ler_imagem(caminho_mascara, cv2.IMREAD_GRAYSCALE)
        if candidata["tipo_quadro"] == "sem_linha" or decisao == "mascara_vazia":
            mascara_nova = np.zeros_like(mascara_atual)
            item["estado_rotulo"] = "hard_negative_sombra_confirmado"
            contagens["hard_negatives_sombra"] += 1
        elif decisao == "aprovada":
            mascara_nova = _ler_imagem(
                auditoria / str(candidata["mascara_candidata"]),
                cv2.IMREAD_GRAYSCALE,
            )
            item["estado_rotulo"] = "corrigida_modelo_aprovada_por_usuario"
            contagens["mascaras_modelo_aprovadas"] += 1
        elif decisao == "reprocessar" and candidata["tipo_quadro"] == "intersecao":
            imagem = _ler_imagem(dataset_v1 / str(item["imagem"]), cv2.IMREAD_COLOR)
            mascara_nova = _reconstruir_intersecao(
                imagem,
                (mascara_atual.shape[1], mascara_atual.shape[0]),
            )
            item["estado_rotulo"] = "corrigida_intersecao_otsu_auditada"
            contagens["intersecoes_reconstruidas"] += 1
        else:
            raise ErroDatasetV2(
                f"Decisao sem consolidacao segura: {id_amostra} ({decisao})"
            )
        _gravar_png(caminho_mascara, mascara_nova)
        item["sha256_mascara"] = _sha256_arquivo(caminho_mascara)
        item["auditoria_fase3_v2"] = {
            "decisao": decisao,
            "motivo": str(candidata["motivo_auditoria"]),
        }

    conteudo_indice = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in indice
    ).encode()
    (saida / "indice.jsonl").write_bytes(conteudo_indice)
    quantidades = Counter(str(item["divisao"]) for item in indice)
    manifesto_dataset = {
        "versao_manifesto": 2,
        "tipo": "dataset_segmentacao_fase3_v2",
        "dataset_pai": "fase3_dataset_inicial",
        "quantidades": {
            "total": len(indice),
            "treino": quantidades["treino"],
            "validacao": quantidades["validacao"],
        },
        "correcoes": dict(sorted(contagens.items())),
        "sha256_indice": _sha256_bytes(conteudo_indice),
        "sha256_candidatas_auditoria": _sha256_arquivo(auditoria / "candidatas.jsonl"),
        "sha256_revisoes_auditoria": _sha256_arquivo(auditoria / "revisoes.jsonl"),
        "divisao_teste_incluida": False,
        "uso": "treinamento_fase3_v2_com_hard_negatives; nao_e_treino_final",
    }
    (saida / "manifesto.json").write_text(
        json.dumps(manifesto_dataset, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _empacotar(saida, arquivo_zip)
    manifesto = {
        **manifesto_dataset,
        "arquivo_local_ignorado": "artefatos/fase3_dataset_v2.zip",
        "bytes": arquivo_zip.stat().st_size,
        "sha256_arquivo": _sha256_arquivo(arquivo_zip),
    }
    manifesto_publico.parent.mkdir(parents=True, exist_ok=True)
    manifesto_publico.write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifesto
