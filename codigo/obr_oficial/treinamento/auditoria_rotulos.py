"""Gera uma fila de active learning para revisar rotulos vazios suspeitos."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2
import numpy as np
import torch

from obr_oficial.treinamento.segmentacao import (
    ConfiguracaoTreinamento,
    DatasetSegmentacaoLinha,
    criar_modelo,
)


class ErroAuditoriaRotulos(ValueError):
    """Indica que a fila de auditoria nao pode ser gerada com seguranca."""


@dataclass(frozen=True)
class ConfiguracaoAuditoriaRotulos:
    """Criterios de desacordo usados sem consultar o conjunto de teste."""

    limiar_segmentacao: float = 0.50
    confianca_minima: float = 0.90
    area_minima_normalizada: float = 0.01


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _gravar_png(caminho: Path, imagem: np.ndarray) -> None:
    sucesso, codificada = cv2.imencode(".png", imagem)
    if not sucesso:
        raise ErroAuditoriaRotulos(f"Falha ao codificar mascara: {caminho}")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(codificada.tobytes())


def _motivo(manual: bool, desacordo: bool) -> str:
    if manual and desacordo:
        return "rotulo_vazio_manual_e_desacordo_modelo"
    if manual:
        return "rotulo_vazio_manual"
    return "desacordo_modelo_com_negativo"


def gerar_fila_auditoria_rotulos(
    raiz_dataset: Path,
    checkpoint: Path,
    saida: Path,
    configuracao: ConfiguracaoAuditoriaRotulos | None = None,
) -> dict[str, Any]:
    """Seleciona rotulos vazios manuais e negativos contestados pelo modelo."""

    configuracao = configuracao or ConfiguracaoAuditoriaRotulos()
    raiz_dataset = raiz_dataset.resolve()
    checkpoint = checkpoint.resolve()
    saida = saida.resolve()
    if not raiz_dataset.is_dir():
        raise ErroAuditoriaRotulos(f"Dataset nao encontrado: {raiz_dataset}")
    if not checkpoint.is_file():
        raise ErroAuditoriaRotulos(f"Checkpoint nao encontrado: {checkpoint}")
    if saida.exists() and any(saida.iterdir()):
        raise ErroAuditoriaRotulos(f"Saida de auditoria ja existe: {saida}")
    if not 0 < configuracao.limiar_segmentacao < 1:
        raise ErroAuditoriaRotulos("limiar_segmentacao deve estar entre zero e um")
    if not 0 < configuracao.confianca_minima <= 1:
        raise ErroAuditoriaRotulos("confianca_minima deve estar entre zero e um")
    if not 0 <= configuracao.area_minima_normalizada <= 1:
        raise ErroAuditoriaRotulos("area_minima_normalizada deve estar entre zero e um")

    pacote = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if not isinstance(pacote, dict) or "estado_modelo" not in pacote:
        raise ErroAuditoriaRotulos("Checkpoint nao contem um estado de modelo valido")
    configuracao_treino = ConfiguracaoTreinamento(**pacote["configuracao"])
    dispositivo = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    modelo = criar_modelo(str(pacote["arquitetura"]), pretreinado=False).to(dispositivo)
    modelo.load_state_dict(pacote["estado_modelo"])
    modelo.eval()

    candidatas: list[dict[str, Any]] = []
    vazias_analisadas = 0
    contagens_motivo: dict[str, int] = {}
    with torch.inference_mode():
        for divisao in ("treino", "validacao"):
            dataset = DatasetSegmentacaoLinha(raiz_dataset, configuracao_treino, divisao)
            for indice, item in enumerate(dataset.amostras):
                estado_rotulo = str(item.get("estado_rotulo", ""))
                if not estado_rotulo.startswith("aprovada_vazia_"):
                    continue
                vazias_analisadas += 1
                imagem, mascara_esperada = dataset[indice]
                if torch.count_nonzero(mascara_esperada):
                    raise ErroAuditoriaRotulos(
                        f"Rotulo declarado vazio contem pixels: {item['id_amostra']}"
                    )
                inicio = perf_counter()
                logits = modelo(imagem.unsqueeze(0).to(dispositivo))
                if dispositivo.type == "cuda":
                    torch.cuda.synchronize()
                latencia_ms = (perf_counter() - inicio) * 1000
                probabilidade = torch.sigmoid(logits)[0, 0].cpu().numpy()
                prevista = probabilidade >= configuracao.limiar_segmentacao
                area_normalizada = float(np.mean(prevista))
                confianca = float(np.max(probabilidade))
                manual = estado_rotulo == "aprovada_vazia_por_usuario"
                desacordo = (
                    confianca >= configuracao.confianca_minima
                    and area_normalizada >= configuracao.area_minima_normalizada
                )
                if not manual and not desacordo:
                    continue

                motivo = _motivo(manual, desacordo)
                contagens_motivo[motivo] = contagens_motivo.get(motivo, 0) + 1
                relativa_imagem = Path(str(item["imagem"]))
                partes = relativa_imagem.parts[1:] if relativa_imagem.parts else ()
                relativa_mascara = Path("mascaras_modelo", *partes)
                _gravar_png(saida / relativa_mascara, prevista.astype(np.uint8) * 255)
                candidatas.append(
                    {
                        "versao": 1,
                        "id_amostra": str(item["id_amostra"]),
                        "divisao": divisao,
                        "tipo_quadro": str(item["tipo_quadro"]),
                        "trajetoria_desejada": str(item["trajetoria_desejada"]),
                        "origem": relativa_imagem.as_posix(),
                        "mascara_candidata": relativa_mascara.as_posix(),
                        "estado": "auditoria_rotulo_vazio",
                        "estado_rotulo_anterior": estado_rotulo,
                        "motivo_auditoria": motivo,
                        "confianca": round(confianca, 8),
                        "area_normalizada": round(area_normalizada, 8),
                        "latencia_ms": round(latencia_ms, 4),
                        "revisao": "pendente",
                    }
                )

    if not candidatas:
        raise ErroAuditoriaRotulos("Nenhum rotulo suspeito encontrado")
    saida.mkdir(parents=True, exist_ok=True)
    conteudo = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in candidatas
    )
    caminho_candidatas = saida / "candidatas.jsonl"
    caminho_candidatas.write_text(conteudo, encoding="utf-8")
    manifesto: dict[str, Any] = {
        "versao_manifesto": 1,
        "tipo": "auditoria_rotulos_vazios_fase3",
        "divisoes_permitidas": ["treino", "validacao"],
        "teste_aberto": False,
        "arquitetura": str(pacote["arquitetura"]),
        "sha256_checkpoint": _sha256(checkpoint),
        "configuracao": asdict(configuracao),
        "vazias_analisadas": vazias_analisadas,
        "candidatas": len(candidatas),
        "por_motivo": contagens_motivo,
        "sha256_candidatas": hashlib.sha256(conteudo.encode()).hexdigest(),
    }
    (saida / "manifesto.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifesto
