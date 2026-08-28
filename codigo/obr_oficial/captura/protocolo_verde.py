"""Protocolo versionado dos rotulos brutos da captura de verde."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from obr_oficial.captura.gerenciador_sessoes import ErroCaptura
from obr_oficial.nucleo.contratos import DecisaoVerde


class CategoriaCapturaVerde(StrEnum):
    """Categorias simples apresentadas no painel de captura."""

    ANTES_ESQUERDA = "antes_esquerda"
    ANTES_DIREITA = "antes_direita"
    DOIS_ANTES_180 = "dois_antes_180"
    DEPOIS_IGNORAR = "depois_ignorar"
    SEM_VERDE_NEGATIVO = "sem_verde_negativo"


@dataclass(frozen=True, slots=True)
class DefinicaoCategoriaVerde:
    """Semantica persistida para uma categoria escolhida pelo humano."""

    categoria: CategoriaCapturaVerde
    rotulo: str
    descricao: str
    decisao: DecisaoVerde
    marcador_antes: bool
    marcador_depois: bool
    dois_marcadores_antes: bool
    mascara_marcador_esperada_vazia: bool

    def como_dict(self) -> dict[str, str | bool]:
        return {
            "categoria": self.categoria.value,
            "rotulo": self.rotulo,
            "descricao": self.descricao,
            "decisao_esperada": self.decisao.value,
            "marcador_antes": self.marcador_antes,
            "marcador_depois": self.marcador_depois,
            "dois_marcadores_antes": self.dois_marcadores_antes,
            "mascara_marcador_esperada_vazia": self.mascara_marcador_esperada_vazia,
        }


DEFINICOES_CATEGORIAS_VERDE = (
    DefinicaoCategoriaVerde(
        CategoriaCapturaVerde.ANTES_ESQUERDA,
        "Antes — esquerda",
        "Um marcador válido antes, no lado esquerdo do sentido de chegada.",
        DecisaoVerde.VIRAR_ESQUERDA,
        marcador_antes=True,
        marcador_depois=False,
        dois_marcadores_antes=False,
        mascara_marcador_esperada_vazia=False,
    ),
    DefinicaoCategoriaVerde(
        CategoriaCapturaVerde.ANTES_DIREITA,
        "Antes — direita",
        "Um marcador válido antes, no lado direito do sentido de chegada.",
        DecisaoVerde.VIRAR_DIREITA,
        marcador_antes=True,
        marcador_depois=False,
        dois_marcadores_antes=False,
        mascara_marcador_esperada_vazia=False,
    ),
    DefinicaoCategoriaVerde(
        CategoriaCapturaVerde.DOIS_ANTES_180,
        "Dois antes — 180°",
        "Dois marcadores válidos antes, um de cada lado da linha.",
        DecisaoVerde.RETORNAR_180,
        marcador_antes=True,
        marcador_depois=False,
        dois_marcadores_antes=True,
        mascara_marcador_esperada_vazia=False,
    ),
    DefinicaoCategoriaVerde(
        CategoriaCapturaVerde.DEPOIS_IGNORAR,
        "Depois — ignorar",
        "Marcador oficial depois da interseção; deve ser segmentado e ignorado na decisão.",
        DecisaoVerde.NENHUMA,
        marcador_antes=False,
        marcador_depois=True,
        dois_marcadores_antes=False,
        mascara_marcador_esperada_vazia=False,
    ),
    DefinicaoCategoriaVerde(
        CategoriaCapturaVerde.SEM_VERDE_NEGATIVO,
        "Sem verde / negativo",
        "Sem marcador oficial válido; a linha continua presente e ativa normalmente.",
        DecisaoVerde.NENHUMA,
        marcador_antes=False,
        marcador_depois=False,
        dois_marcadores_antes=False,
        mascara_marcador_esperada_vazia=True,
    ),
)

_DEFINICAO_POR_CATEGORIA = {
    definicao.categoria: definicao for definicao in DEFINICOES_CATEGORIAS_VERDE
}
_CATEGORIAS_COM_ANTES = {
    CategoriaCapturaVerde.ANTES_ESQUERDA,
    CategoriaCapturaVerde.ANTES_DIREITA,
    CategoriaCapturaVerde.DOIS_ANTES_180,
}


def contexto_sessao_verde(contexto: dict[str, Any]) -> dict[str, Any]:
    """Identifica a tarefa sem confiar em valores enviados pelo navegador."""

    resultado = dict(contexto)
    resultado["tarefa"] = "verde"
    resultado["versao_protocolo_verde"] = 1
    return resultado


def contexto_quadro_verde(contexto: dict[str, Any]) -> dict[str, Any]:
    """Valida a escolha humana e materializa a decisao esperada no registro."""

    categoria_bruta = contexto.get("categoria_verde")
    try:
        categoria = CategoriaCapturaVerde(str(categoria_bruta))
    except ValueError as erro:
        permitidas = ", ".join(item.value for item in CategoriaCapturaVerde)
        raise ErroCaptura(f"categoria_verde invalida; use uma de: {permitidas}") from erro

    cruz_mista = contexto.get("cruz_mista", False)
    if not isinstance(cruz_mista, bool):
        raise ErroCaptura("cruz_mista deve ser verdadeiro ou falso")
    if cruz_mista and categoria not in _CATEGORIAS_COM_ANTES:
        raise ErroCaptura("cruz_mista exige ao menos um marcador valido antes")

    definicao = _DEFINICAO_POR_CATEGORIA[categoria]
    resultado = dict(contexto)
    resultado.update(
        {
            "tarefa": "verde",
            "versao_protocolo_verde": 1,
            "categoria_verde": categoria.value,
            "decisao_verde_esperada": definicao.decisao.value,
            "marcador_antes_presente": definicao.marcador_antes,
            "marcador_depois_presente": definicao.marcador_depois or cruz_mista,
            "dois_marcadores_antes": definicao.dois_marcadores_antes,
            "mascara_marcador_verde_esperada_vazia": (definicao.mascara_marcador_esperada_vazia),
            "cruz_mista": cruz_mista,
        }
    )
    return resultado


def esquema_captura_verde() -> dict[str, Any]:
    """Descreve o protocolo para painel, testes e ferramentas futuras."""

    return {
        "tarefa": "verde",
        "versao": 1,
        "categorias": [definicao.como_dict() for definicao in DEFINICOES_CATEGORIAS_VERDE],
        "cruz_mista_permitida_em": sorted(item.value for item in _CATEGORIAS_COM_ANTES),
        "ausencia_verde_interrompe_linha": False,
    }
