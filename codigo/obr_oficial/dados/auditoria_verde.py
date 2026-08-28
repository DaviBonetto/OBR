"""Auditoria e curadoria reproduzivel das capturas brutas de marcadores verdes."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
from numpy.typing import NDArray

from obr_oficial.captura.protocolo_verde import (
    CategoriaCapturaVerde,
    contexto_quadro_verde,
)


class ErroAuditoriaVerde(RuntimeError):
    """Indica inconsistencia no bruto ou no plano versionado de curadoria."""


@dataclass(frozen=True, slots=True)
class RegraCorrecaoVerde:
    """Alteracao humana explicita aplicada como sobreposicao, nunca no bruto."""

    identificador: str
    sessao: str
    numero_inicio: int
    numero_fim: int
    acao: str
    alteracoes: dict[str, Any]
    motivo: str

    def abrange(self, sessao: str, numero: int) -> bool:
        return self.sessao == sessao and self.numero_inicio <= numero <= self.numero_fim


@dataclass(frozen=True, slots=True)
class PlanoCuradoriaVerde:
    """Contrato imutavel para repetir a selecao do mesmo snapshot."""

    nome: str
    versao: int
    snapshot_sha256: str
    regras: tuple[RegraCorrecaoVerde, ...]
    sessoes_recuperadas: frozenset[str]
    divisoes: dict[str, tuple[str, ...]]
    limiar_diferenca_media: float
    intervalo_nova_sequencia_s: float
    categorias_sem_reducao: frozenset[str]
    hash_plano: str

    def divisao_da_sessao(self, sessao: str) -> str:
        correspondencias = [
            divisao for divisao, sessoes in self.divisoes.items() if sessao in sessoes
        ]
        if len(correspondencias) != 1:
            raise ErroAuditoriaVerde(
                f"Sessao {sessao!r} precisa pertencer a exatamente uma divisao"
            )
        return correspondencias[0]


def carregar_plano_curadoria_verde(caminho: Path) -> PlanoCuradoriaVerde:
    """Carrega o plano JSON e rejeita intervalos ambiguos ou campos invalidos."""

    bruto = caminho.read_bytes()
    try:
        dados = json.loads(bruto)
        selecao = dados["selecao_temporal"]
        regras = tuple(
            RegraCorrecaoVerde(
                identificador=str(item["id"]),
                sessao=str(item["sessao"]),
                numero_inicio=int(item["numero_inicio"]),
                numero_fim=int(item["numero_fim"]),
                acao=str(item["acao"]),
                alteracoes=dict(item.get("alteracoes", {})),
                motivo=str(item["motivo"]),
            )
            for item in dados["correcoes"]
        )
        plano = PlanoCuradoriaVerde(
            nome=str(dados["nome"]),
            versao=int(dados["versao"]),
            snapshot_sha256=str(dados["snapshot"]["sha256"]).lower(),
            regras=regras,
            sessoes_recuperadas=frozenset(str(item) for item in dados["sessoes_recuperadas"]),
            divisoes={
                nome: tuple(str(item) for item in dados["divisoes"][nome])
                for nome in ("treino", "validacao", "teste")
            },
            limiar_diferenca_media=float(selecao["limiar_diferenca_media_64x48"]),
            intervalo_nova_sequencia_s=float(selecao["intervalo_nova_sequencia_s"]),
            categorias_sem_reducao=frozenset(
                str(item) for item in selecao["categorias_sem_reducao"]
            ),
            hash_plano=hashlib.sha256(bruto).hexdigest(),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as erro:
        raise ErroAuditoriaVerde(f"Plano de curadoria verde invalido: {erro}") from erro

    _validar_plano(plano)
    return plano


class CuradorDatasetVerde:
    """Valida todos os pixels e gera indices limpos sem regravar imagens brutas."""

    VERSAO_MANIFESTO = 1

    def __init__(self, raiz_bruta: Path, saida: Path, plano: PlanoCuradoriaVerde) -> None:
        self._raiz_bruta = raiz_bruta.resolve()
        self._saida = saida.resolve()
        self._plano = plano

    def preparar(self) -> dict[str, Any]:
        """Executa a auditoria atomica e devolve o manifesto final."""

        if not self._raiz_bruta.is_dir():
            raise ErroAuditoriaVerde(f"Raiz bruta inexistente: {self._raiz_bruta}")
        if self._saida.exists():
            raise ErroAuditoriaVerde(f"Saida ja existe: {self._saida}")

        temporaria = self._saida.with_name(f".{self._saida.name}.tmp-{uuid4().hex[:8]}")
        temporaria.mkdir(parents=True, exist_ok=False)
        try:
            manifesto = self._processar(temporaria)
            temporaria.replace(self._saida)
            return manifesto
        except Exception:
            shutil.rmtree(temporaria, ignore_errors=True)
            raise

    def _processar(self, saida: Path) -> dict[str, Any]:
        pastas = sorted(
            pasta
            for pasta in self._raiz_bruta.iterdir()
            if pasta.is_dir() and (pasta / "manifesto.json").is_file()
        )
        if not pastas:
            raise ErroAuditoriaVerde("Nenhuma sessao verde encontrada")

        sessoes_encontradas = {pasta.name for pasta in pastas}
        sessoes_planejadas = {
            sessao for sessoes in self._plano.divisoes.values() for sessao in sessoes
        }
        if sessoes_encontradas != sessoes_planejadas:
            faltando = sorted(sessoes_planejadas - sessoes_encontradas)
            extras = sorted(sessoes_encontradas - sessoes_planejadas)
            raise ErroAuditoriaVerde(f"Sessoes divergentes; faltando={faltando}, extras={extras}")

        auditoria: list[dict[str, Any]] = []
        fonte_hash = hashlib.sha256()
        hashes_vistos: dict[str, str] = {}
        sessoes_resumo: list[dict[str, Any]] = []

        for pasta in pastas:
            manifesto = _ler_json(pasta / "manifesto.json")
            registros = _ler_jsonl(pasta / "capturas.jsonl")
            self._validar_sessao(pasta, manifesto, registros)
            divisao = self._plano.divisao_da_sessao(pasta.name)
            sessoes_resumo.append(
                {
                    "id_sessao": pasta.name,
                    "divisao": divisao,
                    "local": manifesto.get("contexto", {}).get("local"),
                    "estado_bruto": manifesto.get("estado"),
                    "estado_efetivo": "finalizada",
                    "capturas": len(registros),
                }
            )
            auditoria.extend(
                self._auditar_sessao(
                    pasta,
                    registros,
                    divisao,
                    fonte_hash,
                    hashes_vistos,
                )
            )

        regras_aplicadas = Counter(
            regra_id for item in auditoria for regra_id in item["correcoes_aplicadas"]
        )
        esperadas = {regra.identificador for regra in self._plano.regras}
        if set(regras_aplicadas) != esperadas:
            ausentes = sorted(esperadas - set(regras_aplicadas))
            raise ErroAuditoriaVerde(f"Correcoes sem quadros correspondentes: {ausentes}")

        self._selecionar_temporalmente(auditoria)
        manifesto_saida = self._gravar_saida(
            saida,
            auditoria,
            sessoes_resumo,
            fonte_hash.hexdigest(),
            regras_aplicadas,
        )
        return manifesto_saida

    def _validar_sessao(
        self,
        pasta: Path,
        manifesto: dict[str, Any],
        registros: list[dict[str, Any]],
    ) -> None:
        estado = str(manifesto.get("estado", ""))
        recuperada = pasta.name in self._plano.sessoes_recuperadas
        if estado != "finalizada" and not recuperada:
            raise ErroAuditoriaVerde(f"Sessao nao finalizada: {pasta.name}")
        if recuperada and estado == "finalizada":
            raise ErroAuditoriaVerde(
                f"Sessao marcada como recuperada sem necessidade: {pasta.name}"
            )
        if int(manifesto.get("capturas", -1)) != len(registros):
            raise ErroAuditoriaVerde(f"Contagem divergente: {pasta.name}")
        numeros = [int(registro.get("numero", -1)) for registro in registros]
        if numeros != list(range(1, len(registros) + 1)):
            raise ErroAuditoriaVerde(f"Numeracao invalida: {pasta.name}")
        pngs = list((pasta / "quadros").glob("*.png"))
        if len(pngs) != len(registros):
            raise ErroAuditoriaVerde(f"Quantidade de PNG divergente: {pasta.name}")

    def _auditar_sessao(
        self,
        pasta: Path,
        registros: list[dict[str, Any]],
        divisao: str,
        fonte_hash: Any,
        hashes_vistos: dict[str, str],
    ) -> list[dict[str, Any]]:
        resultado: list[dict[str, Any]] = []
        for registro in registros:
            numero = int(registro["numero"])
            caminho_relativo = Path(str(registro["arquivo"]))
            caminho = (pasta / caminho_relativo).resolve()
            if not caminho.is_relative_to(pasta.resolve()) or not caminho.is_file():
                raise ErroAuditoriaVerde(f"Imagem ausente ou fora da sessao: {caminho_relativo}")

            conteudo = caminho.read_bytes()
            hash_calculado = hashlib.sha256(conteudo).hexdigest()
            if hash_calculado != str(registro.get("sha256", "")):
                raise ErroAuditoriaVerde(f"Hash divergente: {pasta.name}:{numero}")
            id_amostra = f"{pasta.name}:{numero:06d}"
            if hash_calculado in hashes_vistos:
                raise ErroAuditoriaVerde(
                    f"Duplicata exata: {id_amostra} e {hashes_vistos[hash_calculado]}"
                )
            hashes_vistos[hash_calculado] = id_amostra

            imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)
            if imagem is None:
                raise ErroAuditoriaVerde(f"PNG ilegivel: {id_amostra}")
            altura, largura = imagem.shape[:2]
            quadro = registro.get("quadro", {})
            if (largura, altura) != (int(quadro["largura"]), int(quadro["altura"])):
                raise ErroAuditoriaVerde(f"Resolucao divergente: {id_amostra}")

            contexto_bruto = dict(registro.get("contexto", {}))
            contexto_efetivo, regras, exclusao = self._aplicar_regras(
                pasta.name,
                numero,
                contexto_bruto,
            )
            cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
            reduzida = cv2.resize(cinza, (64, 48), interpolation=cv2.INTER_AREA)
            fonte_hash.update(_json_canonico(registro))
            fonte_hash.update(hash_calculado.encode("ascii"))
            resultado.append(
                {
                    "versao_amostra": 1,
                    "id_amostra": id_amostra,
                    "divisao": divisao,
                    "selecionada": False,
                    "motivos_rejeicao": ["exclusao_manual"] if exclusao else [],
                    "correcoes_aplicadas": regras,
                    "contexto_bruto": contexto_bruto,
                    "contexto_efetivo": contexto_efetivo,
                    "metricas": registro.get("metricas", {}),
                    "origem": {
                        "sessao": pasta.name,
                        "numero": numero,
                        "arquivo": caminho_relativo.as_posix(),
                        "caminho_relativo_raiz": caminho.relative_to(self._raiz_bruta).as_posix(),
                        "sha256": hash_calculado,
                        "captura_utc": registro.get("captura_utc"),
                    },
                    "_reduzida": reduzida,
                }
            )
        return resultado

    def _aplicar_regras(
        self,
        sessao: str,
        numero: int,
        contexto_bruto: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str], bool]:
        correspondencias = [regra for regra in self._plano.regras if regra.abrange(sessao, numero)]
        if len(correspondencias) > 1:
            raise ErroAuditoriaVerde(f"Correcoes sobrepostas: {sessao}:{numero}")
        if not correspondencias:
            return contexto_bruto, [], False

        regra = correspondencias[0]
        if regra.acao == "excluir":
            return contexto_bruto, [regra.identificador], True

        base = {
            "categoria_verde": regra.alteracoes.get(
                "categoria_verde", contexto_bruto.get("categoria_verde")
            ),
            "cruz_mista": regra.alteracoes.get(
                "cruz_mista", contexto_bruto.get("cruz_mista", False)
            ),
            "nota": contexto_bruto.get("nota", ""),
        }
        try:
            efetivo = contexto_quadro_verde(base)
        except Exception as erro:
            raise ErroAuditoriaVerde(f"Correcao invalida {regra.identificador}: {erro}") from erro
        return efetivo, [regra.identificador], False

    def _selecionar_temporalmente(self, auditoria: list[dict[str, Any]]) -> None:
        grupos: list[list[dict[str, Any]]] = []
        atual: list[dict[str, Any]] = []
        chave_anterior: tuple[str, bool] | None = None
        instante_anterior: datetime | None = None
        sessao_anterior: str | None = None

        for item in auditoria:
            if item["motivos_rejeicao"]:
                if atual:
                    grupos.append(atual)
                    atual = []
                chave_anterior = None
                instante_anterior = None
                sessao_anterior = None
                continue
            contexto = item["contexto_efetivo"]
            chave = (str(contexto["categoria_verde"]), bool(contexto["cruz_mista"]))
            instante = datetime.fromisoformat(str(item["origem"]["captura_utc"]))
            sessao = str(item["origem"]["sessao"])
            nova = (
                sessao != sessao_anterior
                or chave != chave_anterior
                or (
                    instante_anterior is not None
                    and (instante - instante_anterior).total_seconds()
                    > self._plano.intervalo_nova_sequencia_s
                )
            )
            if nova and atual:
                grupos.append(atual)
                atual = []
            atual.append(item)
            chave_anterior = chave
            instante_anterior = instante
            sessao_anterior = sessao
        if atual:
            grupos.append(atual)

        for grupo in grupos:
            categoria = str(grupo[0]["contexto_efetivo"]["categoria_verde"])
            if categoria in self._plano.categorias_sem_reducao:
                for item in grupo:
                    item["selecionada"] = True
                continue

            ultima: NDArray[np.uint8] | None = None
            for indice, item in enumerate(grupo):
                reduzida = item["_reduzida"]
                diferenca = None if ultima is None else float(cv2.absdiff(reduzida, ultima).mean())
                item["diferenca_media_ultima_selecionada"] = diferenca
                limite = self._plano.limiar_diferenca_media
                selecionar = (
                    indice in {0, len(grupo) - 1} or diferenca is None or diferenca >= limite
                )
                if selecionar:
                    item["selecionada"] = True
                    ultima = reduzida
                else:
                    item["motivos_rejeicao"].append("quase_duplicata_temporal")

        for item in auditoria:
            item.pop("_reduzida", None)

    def _gravar_saida(
        self,
        saida: Path,
        auditoria: list[dict[str, Any]],
        sessoes: list[dict[str, Any]],
        hash_fonte: str,
        regras_aplicadas: Counter[str],
    ) -> dict[str, Any]:
        selecionadas = [item for item in auditoria if item["selecionada"]]
        (saida / "auditoria.jsonl").write_bytes(
            b"".join(_json_canonico(i) + b"\n" for i in auditoria)
        )
        (saida / "amostras.jsonl").write_bytes(
            b"".join(_json_canonico(i) + b"\n" for i in selecionadas)
        )

        contagens_efetivas = Counter(
            (
                item["divisao"],
                str(item["contexto_efetivo"]["categoria_verde"]),
                bool(item["contexto_efetivo"]["cruz_mista"]),
            )
            for item in auditoria
            if "exclusao_manual" not in item["motivos_rejeicao"]
        )
        contagens_selecionadas = Counter(
            (
                item["divisao"],
                str(item["contexto_efetivo"]["categoria_verde"]),
                bool(item["contexto_efetivo"]["cruz_mista"]),
            )
            for item in selecionadas
        )
        motivos = Counter(motivo for item in auditoria for motivo in item["motivos_rejeicao"])
        manifesto = {
            "versao_manifesto": self.VERSAO_MANIFESTO,
            "nome": self._plano.nome,
            "versao": self._plano.versao,
            "snapshot_sha256": self._plano.snapshot_sha256,
            "hash_plano_curadoria": self._plano.hash_plano,
            "hash_fonte_validada": hash_fonte,
            "originais_alterados": False,
            "total_bruto": len(auditoria),
            "total_excluido_manualmente": motivos["exclusao_manual"],
            "total_redundante_temporal": motivos["quase_duplicata_temporal"],
            "total_selecionado": len(selecionadas),
            "correcoes_aplicadas": dict(sorted(regras_aplicadas.items())),
            "sessoes": sessoes,
            "contagens_efetivas": _contagens_aninhadas(contagens_efetivas),
            "contagens_selecionadas": _contagens_aninhadas(contagens_selecionadas),
            "motivos_rejeicao": dict(sorted(motivos.items())),
            "integridade": {
                "hashes_png_verificados": len(auditoria),
                "pngs_ausentes": 0,
                "pngs_ilegíveis": 0,
                "duplicatas_exatas": 0,
                "numeracao_contigua": True,
            },
            "pronto_para_mascaras_verdes": True,
            "pronto_para_treinamento": False,
        }
        (saida / "manifesto.json").write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifesto


def _validar_plano(plano: PlanoCuradoriaVerde) -> None:
    if plano.versao < 1 or len(plano.snapshot_sha256) != 64:
        raise ErroAuditoriaVerde("Versao ou SHA-256 do snapshot invalido")
    if plano.limiar_diferenca_media <= 0 or plano.intervalo_nova_sequencia_s <= 0:
        raise ErroAuditoriaVerde("Parametros de selecao temporal devem ser positivos")
    categorias = {item.value for item in CategoriaCapturaVerde}
    if not plano.categorias_sem_reducao <= categorias:
        raise ErroAuditoriaVerde("Categoria sem reducao desconhecida")
    ids = [regra.identificador for regra in plano.regras]
    if len(ids) != len(set(ids)):
        raise ErroAuditoriaVerde("IDs de correcao duplicados")
    for regra in plano.regras:
        if regra.numero_inicio < 1 or regra.numero_fim < regra.numero_inicio:
            raise ErroAuditoriaVerde(f"Intervalo invalido: {regra.identificador}")
        if regra.acao not in {"corrigir_contexto", "excluir"}:
            raise ErroAuditoriaVerde(f"Acao invalida: {regra.identificador}")


def _ler_json(caminho: Path) -> dict[str, Any]:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        raise ErroAuditoriaVerde(f"JSON invalido: {caminho}") from erro


def _ler_jsonl(caminho: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(linha)
            for linha in caminho.read_text(encoding="utf-8").splitlines()
            if linha.strip()
        ]
    except (OSError, json.JSONDecodeError) as erro:
        raise ErroAuditoriaVerde(f"JSONL invalido: {caminho}") from erro


def _json_canonico(valor: Any) -> bytes:
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _contagens_aninhadas(contagens: Counter[tuple[str, str, bool]]) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    for (divisao, categoria, cruz_mista), quantidade in sorted(contagens.items()):
        chave = f"{categoria}|cruz_mista={str(cruz_mista).lower()}"
        resultado.setdefault(divisao, {})[chave] = quantidade
    return resultado
