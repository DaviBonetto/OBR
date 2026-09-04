"""Consolidacao conservadora das mascaras verdes candidatas."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


class ErroConsolidacaoVerde(RuntimeError):
    """Indica quebra de integridade ou uso inseguro das candidatas verdes."""


@dataclass(frozen=True, slots=True)
class ConfiguracaoConsolidacaoVerde:
    """Caminhos imutaveis da consolidacao verde."""

    pasta_candidatas: Path
    saida: Path


def _sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _linhas_json(caminho: Path) -> list[dict[str, object]]:
    if not caminho.is_file():
        return []
    return [
        json.loads(linha)
        for linha in caminho.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]


class ConsolidadorRotulosVerdes:
    """Libera rotulos seguros e mantem ambiguidades fora do treinamento."""

    def __init__(self, configuracao: ConfiguracaoConsolidacaoVerde) -> None:
        self.configuracao = configuracao

    def consolidar(self) -> dict[str, object]:
        cfg = self.configuracao
        candidatas_path = cfg.pasta_candidatas / "candidatas.jsonl"
        revisoes_path = cfg.pasta_candidatas / "revisoes.jsonl"
        if cfg.saida.exists():
            raise ErroConsolidacaoVerde(f"Saida ja existe: {cfg.saida}")
        if not candidatas_path.is_file():
            raise ErroConsolidacaoVerde("Candidatas verdes nao encontradas")

        candidatas = _linhas_json(candidatas_path)
        revisoes = _linhas_json(revisoes_path)
        ultimas_revisoes = {str(item["id_amostra"]): item for item in revisoes}
        ids_candidatas = {str(item["id_amostra"]) for item in candidatas}
        ids_orfaos = sorted(set(ultimas_revisoes) - ids_candidatas)
        if ids_orfaos:
            raise ErroConsolidacaoVerde(f"Revisoes sem candidata: {ids_orfaos[:3]}")
        if any(item.get("divisao") == "teste" for item in candidatas):
            raise ErroConsolidacaoVerde("Consolidacao recusou divisao de teste")

        cfg.saida.mkdir(parents=True)
        anotacoes: list[str] = []
        fila: list[str] = []
        contagens: Counter[str] = Counter()
        try:
            for candidata in candidatas:
                id_amostra = str(candidata["id_amostra"])
                divisao = str(candidata["divisao"])
                mascara_verificada = self._ler_mascara_verificada(candidata)
                revisao = ultimas_revisoes.get(id_amostra)
                decisao = None if revisao is None else str(revisao["decisao"])
                incluir, vazia, estado = self._decidir(candidata, decisao)

                mascara_relativa: str | None = None
                hash_mascara: str | None = None
                if incluir:
                    mascara_relativa, hash_mascara = self._gravar_mascara(
                        candidata,
                        mascara_verificada,
                        vazia=vazia,
                    )
                    contagens["rotulos_seguros"] += 1
                    contagens[f"rotulos:{divisao}"] += 1
                    if vazia:
                        contagens["mascaras_vazias"] += 1
                        contagens[f"vazias:{divisao}"] += 1
                    else:
                        contagens["mascaras_positivas"] += 1
                        contagens[f"positivas:{divisao}"] += 1
                else:
                    motivo = "reprocessar_revisao" if decisao == "reprocessar" else "sem_revisao"
                    fila.append(
                        json.dumps(
                            {
                                "id_amostra": id_amostra,
                                "divisao": divisao,
                                "categoria_verde": candidata["categoria_verde"],
                                "cruz_mista": candidata["cruz_mista"],
                                "origem": candidata["origem"],
                                "motivo": motivo,
                                "motivos_prioridade": candidata.get("motivos_prioridade", []),
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                    contagens["fila_active_learning"] += 1

                contagens[f"estado:{estado}"] += 1
                registro = {
                    "versao": 1,
                    "id_amostra": id_amostra,
                    "divisao": divisao,
                    "categoria_verde": candidata["categoria_verde"],
                    "cruz_mista": candidata["cruz_mista"],
                    "decisao_verde_esperada": candidata["decisao_verde_esperada"],
                    "origem": candidata["origem"],
                    "estado_rotulo": estado,
                    "mascara": mascara_relativa,
                    "sha256_mascara": hash_mascara,
                    "revisao_explicita": revisao is not None,
                    "decisao_original": decisao,
                    "observacao": "" if revisao is None else revisao.get("observacao", ""),
                }
                anotacoes.append(json.dumps(registro, ensure_ascii=False, sort_keys=True))

            conteudo_anotacoes = ("\n".join(anotacoes) + "\n").encode()
            conteudo_fila = (("\n".join(fila) + "\n") if fila else "").encode()
            (cfg.saida / "anotacoes.jsonl").write_bytes(conteudo_anotacoes)
            (cfg.saida / "fila_active_learning.jsonl").write_bytes(conteudo_fila)
            manifesto = self._criar_manifesto(
                candidatas_path,
                revisoes_path,
                candidatas,
                ultimas_revisoes,
                contagens,
                conteudo_anotacoes,
                conteudo_fila,
            )
            (cfg.saida / "manifesto.json").write_text(
                json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return manifesto
        except Exception:
            self._limpar_saida_parcial()
            raise

    @staticmethod
    def _decidir(
        candidata: dict[str, object],
        decisao: str | None,
    ) -> tuple[bool, bool, str]:
        prioridade = str(candidata["prioridade"])
        categoria = str(candidata["categoria_verde"])
        if prioridade == "contrato" or categoria == "sem_verde_negativo":
            return True, True, "aprovada_vazia_por_contrato"
        if prioridade == "normal":
            return True, False, "aprovada_por_regra_calibrada"
        if decisao == "aprovada":
            return True, False, "aprovada_por_auditoria_visual"
        if decisao == "mascara_vazia":
            return True, True, "aprovada_vazia_por_auditoria_visual"
        return False, False, "aguardando_active_learning"

    def _ler_mascara_verificada(self, candidata: dict[str, object]) -> bytes:
        relativo = Path(str(candidata["mascara_candidata"]))
        caminho = (self.configuracao.pasta_candidatas / relativo).resolve()
        raiz = self.configuracao.pasta_candidatas.resolve()
        if not caminho.is_relative_to(raiz):
            raise ErroConsolidacaoVerde("Mascara fora da pasta de candidatas")
        try:
            conteudo = caminho.read_bytes()
        except OSError as erro:
            raise ErroConsolidacaoVerde(f"Mascara candidata ausente: {caminho}") from erro
        esperado = str(candidata.get("sha256_mascara", ""))
        if _sha256(conteudo) != esperado:
            raise ErroConsolidacaoVerde(f"Hash de mascara divergente: {candidata['id_amostra']}")
        return conteudo

    def _gravar_mascara(
        self,
        candidata: dict[str, object],
        conteudo: bytes,
        *,
        vazia: bool,
    ) -> tuple[str, str]:
        relativo = Path(str(candidata["mascara_candidata"]))
        if vazia:
            imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if imagem is None:
                raise ErroConsolidacaoVerde(f"Mascara invalida: {candidata['id_amostra']}")
            sucesso, codificada = cv2.imencode(".png", np.zeros_like(imagem))
            if not sucesso:
                raise ErroConsolidacaoVerde("Falha ao codificar mascara vazia")
            conteudo = codificada.tobytes()
        destino = self.configuracao.saida / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        return relativo.as_posix(), _sha256(conteudo)

    @staticmethod
    def _criar_manifesto(
        candidatas_path: Path,
        revisoes_path: Path,
        candidatas: list[dict[str, object]],
        revisoes: dict[str, dict[str, object]],
        contagens: Counter[str],
        conteudo_anotacoes: bytes,
        conteudo_fila: bytes,
    ) -> dict[str, object]:
        revisoes_bytes = revisoes_path.read_bytes() if revisoes_path.is_file() else b""
        pronto_inicial = all(
            contagens[chave] > 0
            for chave in (
                "positivas:treino",
                "positivas:validacao",
                "vazias:treino",
                "vazias:validacao",
            )
        )
        return {
            "versao_manifesto": 1,
            "tipo": "rotulos_verdes_consolidados_conservadores",
            "regra": (
                "contrato_e_normal_calibrada_entram; prioritaria_exige_aprovacao_visual_explicita"
            ),
            "divisao_teste_processada": False,
            "quantidades": {
                "amostras": len(candidatas),
                "revisoes_explicitas_unicas": len(revisoes),
                "rotulos_seguros": contagens["rotulos_seguros"],
                "mascaras_positivas": contagens["mascaras_positivas"],
                "mascaras_vazias": contagens["mascaras_vazias"],
                "fila_active_learning": contagens["fila_active_learning"],
                "treino_seguro": contagens["rotulos:treino"],
                "validacao_segura": contagens["rotulos:validacao"],
                "aprovadas_regra_calibrada": contagens["estado:aprovada_por_regra_calibrada"],
                "aprovadas_contrato": contagens["estado:aprovada_vazia_por_contrato"],
                "aprovadas_auditoria_visual": contagens["estado:aprovada_por_auditoria_visual"],
            },
            "fingerprints": {
                "candidatas": _sha256(candidatas_path.read_bytes()),
                "revisoes": _sha256(revisoes_bytes),
                "anotacoes": _sha256(conteudo_anotacoes),
                "fila_active_learning": _sha256(conteudo_fila),
            },
            "pronto_para_treino_inicial": pronto_inicial,
            "pronto_para_treino_final": pronto_inicial and contagens["fila_active_learning"] == 0,
        }

    def _limpar_saida_parcial(self) -> None:
        if not self.configuracao.saida.exists():
            return
        for caminho in sorted(self.configuracao.saida.rglob("*"), reverse=True):
            if caminho.is_file():
                caminho.unlink()
            elif caminho.is_dir():
                caminho.rmdir()
        self.configuracao.saida.rmdir()
