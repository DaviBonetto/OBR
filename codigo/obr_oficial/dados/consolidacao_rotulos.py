"""Consolidacao auditavel das decisoes humanas da rotulagem assistida."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


class ErroConsolidacaoRotulos(RuntimeError):
    """Indica inconsistencia entre candidatas, revisoes e mascaras."""


@dataclass(frozen=True, slots=True)
class ConfiguracaoConsolidacaoRotulos:
    """Caminhos imutaveis da consolidacao de uma versao rotulada."""

    pasta_candidatas: Path
    saida: Path


def _sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _linhas_json(caminho: Path) -> list[dict[str, object]]:
    return [
        json.loads(linha)
        for linha in caminho.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]


class ConsolidadorRotulos:
    """Aplica a regra humana sem transformar rejeicoes em rotulos falsos."""

    def __init__(self, configuracao: ConfiguracaoConsolidacaoRotulos) -> None:
        self.configuracao = configuracao

    def consolidar(self) -> dict[str, object]:
        cfg = self.configuracao
        candidatas_path = cfg.pasta_candidatas / "candidatas.jsonl"
        revisoes_path = cfg.pasta_candidatas / "revisoes.jsonl"
        if cfg.saida.exists():
            raise ErroConsolidacaoRotulos(f"Saida ja existe: {cfg.saida}")
        if not candidatas_path.is_file() or not revisoes_path.is_file():
            raise ErroConsolidacaoRotulos("Candidatas ou revisoes nao encontradas")

        candidatas = _linhas_json(candidatas_path)
        revisoes = _linhas_json(revisoes_path)
        ultimas_revisoes = {str(item["id_amostra"]): item for item in revisoes}
        ids_candidatas = {str(item["id_amostra"]) for item in candidatas}
        ids_orfaos = sorted(set(ultimas_revisoes) - ids_candidatas)
        if ids_orfaos:
            raise ErroConsolidacaoRotulos(f"Revisoes sem candidata: {ids_orfaos[:3]}")

        cfg.saida.mkdir(parents=True)
        anotacoes: list[str] = []
        fila: list[str] = []
        contagens: Counter[str] = Counter()
        try:
            for candidata in candidatas:
                if candidata["divisao"] == "teste":
                    raise ErroConsolidacaoRotulos("Consolidacao recusou divisao de teste")
                id_amostra = str(candidata["id_amostra"])
                tipo = str(candidata["tipo_quadro"])
                revisao = ultimas_revisoes.get(id_amostra)
                decisao = None if revisao is None else str(revisao["decisao"])
                precisa_reprocessar = decisao == "reprocessar" and tipo != "sem_linha"

                if precisa_reprocessar:
                    estado = "aguardando_active_learning"
                    mascara_relativa = None
                    hash_mascara = None
                    fila.append(
                        json.dumps(
                            {
                                "id_amostra": id_amostra,
                                "divisao": candidata["divisao"],
                                "tipo_quadro": tipo,
                                "origem": candidata["origem"],
                                "motivo": "reprocessar_usuario",
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                    contagens["fila_correcao"] += 1
                else:
                    estado = self._estado_aprovacao(tipo, decisao)
                    mascara_relativa, hash_mascara = self._gravar_mascara(
                        candidata,
                        vazia=(tipo == "sem_linha" or decisao == "mascara_vazia"),
                    )
                    contagens["rotulos_supervisionados"] += 1
                    contagens[f"rotulos:{candidata['divisao']}"] += 1
                    if tipo == "sem_linha" or decisao == "mascara_vazia":
                        contagens["mascaras_vazias"] += 1
                    else:
                        contagens["mascaras_positivas"] += 1

                registro = {
                    "versao": 1,
                    "id_amostra": id_amostra,
                    "divisao": candidata["divisao"],
                    "tipo_quadro": tipo,
                    "trajetoria_desejada": candidata["trajetoria_desejada"],
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
            (cfg.saida / "fila_correcao.jsonl").write_bytes(conteudo_fila)
            manifesto: dict[str, object] = {
                "versao_manifesto": 1,
                "tipo": "rotulos_consolidados_parciais",
                "regra_usuario": "pendente_significa_aprovada; marcacoes_exigem_mudanca",
                "divisao_teste_processada": False,
                "quantidades": {
                    "amostras": len(candidatas),
                    "revisoes_explicitas_unicas": len(ultimas_revisoes),
                    "aprovacoes_implicitas": len(candidatas) - len(ultimas_revisoes),
                    "rotulos_supervisionados": contagens["rotulos_supervisionados"],
                    "mascaras_positivas": contagens["mascaras_positivas"],
                    "mascaras_vazias": contagens["mascaras_vazias"],
                    "fila_correcao": contagens["fila_correcao"],
                    "treino_supervisionado": contagens["rotulos:treino"],
                    "validacao_supervisionada": contagens["rotulos:validacao"],
                },
                "fingerprints": {
                    "candidatas": _sha256(candidatas_path.read_bytes()),
                    "revisoes": _sha256(revisoes_path.read_bytes()),
                    "anotacoes": _sha256(conteudo_anotacoes),
                    "fila_correcao": _sha256(conteudo_fila),
                },
                "pronto_para_treino_inicial": contagens["rotulos_supervisionados"] > 0,
                "pronto_para_treino_final": contagens["fila_correcao"] == 0,
            }
            (cfg.saida / "manifesto.json").write_text(
                json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return manifesto
        except Exception:
            self._limpar_saida_parcial()
            raise

    @staticmethod
    def _estado_aprovacao(tipo: str, decisao: str | None) -> str:
        if tipo == "sem_linha":
            return "aprovada_vazia_por_contrato"
        if decisao == "mascara_vazia":
            return "aprovada_vazia_por_usuario"
        if decisao == "aprovada":
            return "aprovada_explicita"
        return "aprovada_por_regra_usuario"

    def _gravar_mascara(
        self,
        candidata: dict[str, object],
        *,
        vazia: bool,
    ) -> tuple[str, str]:
        origem_relativa = Path(str(candidata["mascara_candidata"]))
        origem = self.configuracao.pasta_candidatas / origem_relativa
        try:
            conteudo = origem.read_bytes()
        except OSError as erro:
            raise ErroConsolidacaoRotulos(f"Mascara candidata ausente: {origem}") from erro
        if vazia:
            imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if imagem is None:
                raise ErroConsolidacaoRotulos(f"Mascara invalida: {origem}")
            sucesso, codificada = cv2.imencode(".png", np.zeros_like(imagem))
            if not sucesso:
                raise ErroConsolidacaoRotulos(f"Falha ao codificar mascara vazia: {origem}")
            conteudo = codificada.tobytes()
        destino = self.configuracao.saida / origem_relativa
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        return origem_relativa.as_posix(), _sha256(conteudo)

    def _limpar_saida_parcial(self) -> None:
        # A pasta acabou de ser criada por esta instancia e contem somente sua saida parcial.
        if not self.configuracao.saida.exists():
            return
        for caminho in sorted(self.configuracao.saida.rglob("*"), reverse=True):
            if caminho.is_file():
                caminho.unlink()
            elif caminho.is_dir():
                caminho.rmdir()
        self.configuracao.saida.rmdir()
