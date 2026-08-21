"""Curadoria deterministica de sessoes brutas sem alterar as imagens originais."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tomllib
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import cv2
import numpy as np
from numpy.typing import NDArray


class ErroPreparacaoDataset(RuntimeError):
    """Indica dado inconsistente ou configuracao insegura da curadoria."""


@dataclass(frozen=True, slots=True)
class FiltrosDataset:
    limiar_diferenca_media: float
    brilho_minimo: float
    brilho_maximo: float
    percentual_escuro_maximo: float
    percentual_claro_maximo: float


@dataclass(frozen=True, slots=True)
class ConfiguracaoDataset:
    nome: str
    versao: int
    largura: int
    altura: int
    tipos_permitidos: tuple[str, ...]
    filtros: FiltrosDataset
    minimo_por_tipo_por_divisao: int
    divisoes: dict[str, tuple[str, ...]]
    hash_configuracao: str

    def divisao_do_ambiente(self, ambiente: str) -> str:
        correspondencias = [
            divisao for divisao, ambientes in self.divisoes.items() if ambiente in ambientes
        ]
        if len(correspondencias) != 1:
            raise ErroPreparacaoDataset(
                f"Ambiente {ambiente!r} precisa pertencer a exatamente uma divisao"
            )
        return correspondencias[0]


def carregar_configuracao_dataset(caminho: Path) -> ConfiguracaoDataset:
    """Carrega e valida a configuracao TOML usada para congelar uma versao."""

    dados = tomllib.loads(caminho.read_text(encoding="utf-8"))
    try:
        dataset = dados["dataset"]
        filtros = dados["filtros"]
        criterios = dados["criterios"]
        divisoes_brutas = dados["divisoes"]
        tipos = tuple(str(tipo) for tipo in dataset["tipos_permitidos"])
        divisoes = {
            nome: tuple(_slug(ambiente) for ambiente in divisoes_brutas[nome])
            for nome in ("treino", "validacao", "teste")
        }
        configuracao = ConfiguracaoDataset(
            nome=_slug(str(dataset["nome"])),
            versao=int(dataset["versao"]),
            largura=int(dataset["largura"]),
            altura=int(dataset["altura"]),
            tipos_permitidos=tipos,
            filtros=FiltrosDataset(
                limiar_diferenca_media=float(filtros["limiar_diferenca_media"]),
                brilho_minimo=float(filtros["brilho_minimo"]),
                brilho_maximo=float(filtros["brilho_maximo"]),
                percentual_escuro_maximo=float(filtros["percentual_escuro_maximo"]),
                percentual_claro_maximo=float(filtros["percentual_claro_maximo"]),
            ),
            minimo_por_tipo_por_divisao=int(criterios["minimo_por_tipo_por_divisao"]),
            divisoes=divisoes,
            hash_configuracao=hashlib.sha256(
                json.dumps(
                    dados,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )
    except (KeyError, TypeError, ValueError) as erro:
        raise ErroPreparacaoDataset(f"Configuracao de dataset invalida: {erro}") from erro

    _validar_configuracao(configuracao)
    return configuracao


class PreparadorDataset:
    """Valida, filtra e divide sessoes completas de forma reproduzivel."""

    VERSAO_MANIFESTO = 1
    VERSAO_AMOSTRA = 1

    def __init__(
        self,
        raiz_bruta: Path,
        pasta_saida: Path,
        configuracao: ConfiguracaoDataset,
    ) -> None:
        self._raiz_bruta = raiz_bruta.resolve()
        self._pasta_saida = pasta_saida.resolve()
        self._configuracao = configuracao

    def preparar(self) -> dict[str, Any]:
        """Gera indices atomicos; nunca remove ou regrava um quadro original."""

        if not self._raiz_bruta.is_dir():
            raise ErroPreparacaoDataset(f"Pasta bruta inexistente: {self._raiz_bruta}")
        if self._pasta_saida.exists():
            raise ErroPreparacaoDataset(f"Saida ja existe: {self._pasta_saida}")

        temporaria = self._pasta_saida.with_name(f".{self._pasta_saida.name}.tmp-{uuid4().hex[:8]}")
        temporaria.mkdir(parents=True, exist_ok=False)
        try:
            resultado = self._processar(temporaria)
            temporaria.replace(self._pasta_saida)
            return resultado
        except Exception:
            shutil.rmtree(temporaria, ignore_errors=True)
            raise

    def _processar(self, saida: Path) -> dict[str, Any]:
        auditoria: list[dict[str, Any]] = []
        selecionadas: list[dict[str, Any]] = []
        hashes_vistos: set[str] = set()
        sessoes_fonte: list[dict[str, Any]] = []
        fonte_hash = hashlib.sha256()

        pastas_sessao = sorted(
            pasta
            for pasta in self._raiz_bruta.iterdir()
            if pasta.is_dir() and (pasta / "manifesto.json").is_file()
        )
        if not pastas_sessao:
            raise ErroPreparacaoDataset("Nenhuma sessao bruta encontrada")

        for pasta_sessao in pastas_sessao:
            manifesto = _ler_json(pasta_sessao / "manifesto.json")
            registros = _ler_jsonl(pasta_sessao / "capturas.jsonl")
            ambiente = _slug(str(manifesto.get("contexto", {}).get("local", "")))
            divisao = self._configuracao.divisao_do_ambiente(ambiente)
            self._validar_sessao(pasta_sessao, manifesto, registros)
            sessoes_fonte.append(
                {
                    "id_sessao": pasta_sessao.name,
                    "ambiente": ambiente,
                    "divisao": divisao,
                    "capturas": len(registros),
                    "estado": manifesto["estado"],
                }
            )

            ultimo_quadro_selecionado: NDArray[np.uint8] | None = None
            for registro in sorted(registros, key=lambda item: int(item["numero"])):
                decisao, quadro_reduzido = self._avaliar_quadro(
                    pasta_sessao,
                    registro,
                    ambiente,
                    divisao,
                    hashes_vistos,
                    ultimo_quadro_selecionado,
                )
                auditoria.append(decisao)
                fonte_hash.update(_linha_canonica_fonte(decisao))
                hashes_vistos.add(decisao["origem"]["sha256"])
                if decisao["selecionada"]:
                    ultimo_quadro_selecionado = quadro_reduzido
                    selecionadas.append(decisao)

        manifesto_dataset = self._gravar_saida(
            saida,
            auditoria,
            selecionadas,
            sessoes_fonte,
            fonte_hash.hexdigest(),
        )
        return manifesto_dataset

    def _validar_sessao(
        self,
        pasta: Path,
        manifesto: dict[str, Any],
        registros: list[dict[str, Any]],
    ) -> None:
        if manifesto.get("estado") != "finalizada":
            raise ErroPreparacaoDataset(f"Sessao nao finalizada: {pasta.name}")
        if int(manifesto.get("capturas", -1)) != len(registros):
            raise ErroPreparacaoDataset(f"Contagem divergente na sessao {pasta.name}")
        numeros = [int(registro.get("numero", -1)) for registro in registros]
        if numeros != list(range(1, len(registros) + 1)):
            raise ErroPreparacaoDataset(f"Numeracao invalida na sessao {pasta.name}")

    def _avaliar_quadro(
        self,
        pasta_sessao: Path,
        registro: dict[str, Any],
        ambiente: str,
        divisao: str,
        hashes_vistos: set[str],
        ultimo_selecionado: NDArray[np.uint8] | None,
    ) -> tuple[dict[str, Any], NDArray[np.uint8]]:
        motivos: list[str] = []
        caminho_relativo = Path(str(registro["arquivo"]))
        caminho = (pasta_sessao / caminho_relativo).resolve()
        if not caminho.is_relative_to(pasta_sessao.resolve()):
            raise ErroPreparacaoDataset(f"Caminho fora da sessao: {caminho_relativo}")
        if not caminho.is_file():
            raise ErroPreparacaoDataset(f"Imagem ausente: {caminho}")

        conteudo = caminho.read_bytes()
        hash_calculado = hashlib.sha256(conteudo).hexdigest()
        hash_registrado = str(registro.get("sha256", ""))
        if hash_calculado != hash_registrado:
            raise ErroPreparacaoDataset(f"Hash divergente: {caminho}")

        imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if imagem is None:
            raise ErroPreparacaoDataset(f"Imagem ilegivel: {caminho}")
        altura, largura = imagem.shape
        if (largura, altura) != (self._configuracao.largura, self._configuracao.altura):
            motivos.append("resolucao_incorreta")

        tipo = str(registro.get("contexto", {}).get("tipo_quadro", ""))
        if tipo not in self._configuracao.tipos_permitidos:
            motivos.append("tipo_nao_permitido")

        metricas = registro.get("metricas", {})
        self._avaliar_metricas(metricas, motivos)
        if hash_calculado in hashes_vistos:
            motivos.append("duplicata_exata")

        reduzida = cv2.resize(imagem, (64, 48), interpolation=cv2.INTER_AREA)
        diferenca_media = None
        if ultimo_selecionado is not None:
            diferenca_media = float(cv2.absdiff(reduzida, ultimo_selecionado).mean())
            if diferenca_media < self._configuracao.filtros.limiar_diferenca_media:
                motivos.append("quase_duplicata_temporal")

        selecionada = not motivos
        id_amostra = f"{pasta_sessao.name}:{int(registro['numero']):06d}"
        decisao = {
            "versao_amostra": self.VERSAO_AMOSTRA,
            "id_amostra": id_amostra,
            "selecionada": selecionada,
            "motivos_rejeicao": motivos,
            "divisao": divisao,
            "ambiente": ambiente,
            "tipo_quadro": tipo,
            "trajetoria_desejada": _trajetoria_desejada(tipo),
            "diferenca_media_anterior": diferenca_media,
            "metricas": metricas,
            "origem": {
                "sessao": pasta_sessao.name,
                "arquivo": caminho_relativo.as_posix(),
                "caminho_relativo_raiz": caminho.relative_to(self._raiz_bruta).as_posix(),
                "sha256": hash_calculado,
                "captura_utc": registro.get("captura_utc"),
            },
            "anotacao": {
                "estado": "pendente" if selecionada else "nao_aplicavel",
                "mascara_linha": None,
                "linha_central_normalizada": None,
                "ponto_objetivo_normalizado": None,
            },
        }
        return decisao, reduzida

    def _avaliar_metricas(self, metricas: dict[str, Any], motivos: list[str]) -> None:
        try:
            brilho = float(metricas["brilho_medio"])
            escuro = float(metricas["percentual_escuro"])
            claro = float(metricas["percentual_claro"])
        except (KeyError, TypeError, ValueError) as erro:
            raise ErroPreparacaoDataset(f"Metricas invalidas: {erro}") from erro
        filtros = self._configuracao.filtros
        if brilho < filtros.brilho_minimo:
            motivos.append("brilho_muito_baixo")
        if brilho > filtros.brilho_maximo:
            motivos.append("brilho_muito_alto")
        if escuro > filtros.percentual_escuro_maximo:
            motivos.append("imagem_predominantemente_escura")
        if claro > filtros.percentual_claro_maximo:
            motivos.append("imagem_predominantemente_clara")

    def _gravar_saida(
        self,
        saida: Path,
        auditoria: list[dict[str, Any]],
        selecionadas: list[dict[str, Any]],
        sessoes_fonte: list[dict[str, Any]],
        hash_fonte: str,
    ) -> dict[str, Any]:
        linhas_auditoria = [_json_canonico(item) for item in auditoria]
        linhas_amostras = [_json_canonico(item) for item in selecionadas]
        (saida / "auditoria.jsonl").write_text("".join(linhas_auditoria), encoding="utf-8")
        (saida / "amostras.jsonl").write_text("".join(linhas_amostras), encoding="utf-8")

        pasta_divisoes = saida / "divisoes"
        pasta_divisoes.mkdir()
        for divisao in ("treino", "validacao", "teste"):
            ids = [item["id_amostra"] for item in selecionadas if item["divisao"] == divisao]
            (pasta_divisoes / f"{divisao}.txt").write_text(
                "".join(f"{identificador}\n" for identificador in ids),
                encoding="utf-8",
            )

        motivos = Counter(motivo for item in auditoria for motivo in item["motivos_rejeicao"])
        contagem_divisao_tipo = Counter(
            (item["divisao"], item["tipo_quadro"]) for item in selecionadas
        )
        por_divisao_e_tipo = {
            divisao: {
                tipo: contagem_divisao_tipo[(divisao, tipo)]
                for tipo in self._configuracao.tipos_permitidos
            }
            for divisao in ("treino", "validacao", "teste")
        }
        tipos_ausentes = {
            divisao: [tipo for tipo, quantidade in tipos.items() if quantidade == 0]
            for divisao, tipos in por_divisao_e_tipo.items()
        }
        tipos_ausentes = {divisao: tipos for divisao, tipos in tipos_ausentes.items() if tipos}
        tipos_insuficientes = {
            divisao: {
                tipo: quantidade
                for tipo, quantidade in tipos.items()
                if quantidade < self._configuracao.minimo_por_tipo_por_divisao
            }
            for divisao, tipos in por_divisao_e_tipo.items()
        }
        tipos_insuficientes = {
            divisao: tipos for divisao, tipos in tipos_insuficientes.items() if tipos
        }
        manifesto = {
            "versao_manifesto_dataset": self.VERSAO_MANIFESTO,
            "nome": self._configuracao.nome,
            "versao": self._configuracao.versao,
            "gerado_utc": datetime.now(UTC).isoformat(),
            "raiz_bruta": str(self._raiz_bruta),
            "hash_configuracao_sha256": self._configuracao.hash_configuracao,
            "hash_fonte_sha256": hash_fonte,
            "hash_amostras_sha256": hashlib.sha256(
                "".join(linhas_amostras).encode("utf-8")
            ).hexdigest(),
            "originais_alterados": False,
            "pronto_para_anotacao": not tipos_insuficientes,
            "tipos_ausentes_por_divisao": tipos_ausentes,
            "tipos_insuficientes_por_divisao": tipos_insuficientes,
            "ferramentas": {
                "opencv": cv2.__version__,
                "numpy": np.__version__,
            },
            "quantidades": {
                "sessoes": len(sessoes_fonte),
                "quadros_brutos": len(auditoria),
                "quadros_selecionados": len(selecionadas),
                "quadros_rejeitados": len(auditoria) - len(selecionadas),
                "por_divisao": dict(Counter(item["divisao"] for item in selecionadas)),
                "por_divisao_e_tipo": por_divisao_e_tipo,
                "por_tipo": dict(Counter(item["tipo_quadro"] for item in selecionadas)),
                "por_ambiente": dict(Counter(item["ambiente"] for item in selecionadas)),
                "rejeicoes_por_motivo": dict(motivos),
            },
            "sessoes_fonte": sessoes_fonte,
        }
        (saida / "manifesto_dataset.json").write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifesto


def _validar_configuracao(configuracao: ConfiguracaoDataset) -> None:
    if configuracao.versao < 1 or configuracao.largura < 1 or configuracao.altura < 1:
        raise ErroPreparacaoDataset("Versao e dimensoes devem ser positivas")
    if configuracao.minimo_por_tipo_por_divisao < 1:
        raise ErroPreparacaoDataset("minimo_por_tipo_por_divisao deve ser positivo")
    if not configuracao.tipos_permitidos or len(set(configuracao.tipos_permitidos)) != len(
        configuracao.tipos_permitidos
    ):
        raise ErroPreparacaoDataset("tipos_permitidos deve ser uma lista unica e nao vazia")
    ambientes = [ambiente for grupo in configuracao.divisoes.values() for ambiente in grupo]
    if not ambientes or len(ambientes) != len(set(ambientes)):
        raise ErroPreparacaoDataset("Ambientes das divisoes devem ser unicos")
    f = configuracao.filtros
    if not 0 <= f.brilho_minimo < f.brilho_maximo <= 255:
        raise ErroPreparacaoDataset("Faixa de brilho invalida")
    if not 0 <= f.percentual_escuro_maximo <= 100:
        raise ErroPreparacaoDataset("percentual_escuro_maximo invalido")
    if not 0 <= f.percentual_claro_maximo <= 100:
        raise ErroPreparacaoDataset("percentual_claro_maximo invalido")
    if f.limiar_diferenca_media < 0:
        raise ErroPreparacaoDataset("limiar_diferenca_media deve ser positivo")


def _trajetoria_desejada(tipo: str) -> str:
    if tipo == "intersecao":
        return "reto"
    if tipo == "sem_linha":
        return "sem_evidencia"
    return "seguir_linha"


def _ler_json(caminho: Path) -> dict[str, Any]:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        raise ErroPreparacaoDataset(f"JSON invalido em {caminho}: {erro}") from erro


def _ler_jsonl(caminho: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(linha)
            for linha in caminho.read_text(encoding="utf-8").splitlines()
            if linha.strip()
        ]
    except (OSError, json.JSONDecodeError) as erro:
        raise ErroPreparacaoDataset(f"JSONL invalido em {caminho}: {erro}") from erro


def _json_canonico(valor: dict[str, Any]) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _linha_canonica_fonte(decisao: dict[str, Any]) -> bytes:
    origem = decisao["origem"]
    partes = (
        decisao["id_amostra"],
        origem["caminho_relativo_raiz"],
        origem["sha256"],
        decisao["tipo_quadro"],
        decisao["ambiente"],
    )
    return ("\t".join(partes) + "\n").encode("utf-8")


def _slug(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    ascii_texto = normalizado.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", ascii_texto).strip("_") or "sem_nome"
