"""Contrato dos tempos de manobra ajustaveis pelo painel de operacao.

Fonte unica de verdade para chaves, limites e passos. O painel web le esta
estrutura e monta os controles dinamicamente, evitando duplicar limites entre
camadas (licao registrada das correcoes do dashboard antigo).
"""

from __future__ import annotations

from dataclasses import dataclass


class ErroViradas(RuntimeError):
    """Indica chave desconhecida ou valor fora dos limites permitidos."""


@dataclass(frozen=True, slots=True)
class CampoVirada:
    """Um unico tempo de manobra, em milissegundos."""

    grupo: str
    campo: str
    rotulo: str
    minimo_ms: int
    maximo_ms: int
    passo_ms: int

    @property
    def chave(self) -> str:
        """Identificador canonico no formato ``grupo.campo``."""

        return f"{self.grupo}.{self.campo}"


CAMPOS_VIRADAS: tuple[CampoVirada, ...] = (
    CampoVirada("esquerda", "avanco_ms", "Avanço", 0, 2000, 25),
    CampoVirada("esquerda", "giro_ms", "Giro", 0, 4000, 50),
    CampoVirada("direita", "avanco_ms", "Avanço", 0, 2000, 25),
    CampoVirada("direita", "giro_ms", "Giro", 0, 4000, 50),
    CampoVirada("verde", "primeiro_giro_ms", "Primeiro giro", 0, 4000, 50),
    CampoVirada("verde", "reverso_ms", "Ré", 0, 1500, 25),
    CampoVirada("verde", "segundo_giro_ms", "Segundo giro", 0, 4000, 50),
    CampoVirada("verde90", "primeiro_giro_ms", "Primeiro giro", 0, 4000, 50),
    CampoVirada("verde90", "reverso_ms", "Ré", 0, 1500, 25),
    CampoVirada("gap", "avanco_ms", "Avanço", 0, 5000, 25),
    CampoVirada("gap", "confirmacao_ms", "Confirmação", 0, 3000, 25),
)

ROTULOS_GRUPOS: dict[str, str] = {
    "esquerda": "Curva 90° · esquerda",
    "direita": "Curva 90° · direita",
    "verde": "Verde duplo · 180°",
    "verde90": "Verde · 90°",
    "gap": "Gap",
}

_CAMPOS_POR_CHAVE = {item.chave: item for item in CAMPOS_VIRADAS}


def campo_por_chave(chave: str) -> CampoVirada | None:
    """Retorna o campo correspondente a chave ou ``None`` se inexistente."""

    return _CAMPOS_POR_CHAVE.get(chave)


def exigir_campo(chave: str) -> CampoVirada:
    """Retorna o campo ou levanta ``ErroViradas`` para chave desconhecida."""

    campo = _CAMPOS_POR_CHAVE.get(chave)
    if campo is None:
        raise ErroViradas(f"Parametro desconhecido: {chave}")
    return campo


def validar_valor(campo: CampoVirada, valor: object) -> int:
    """Valida e normaliza um valor informado pelo operador."""

    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroViradas(f"Valor deve ser numerico: {campo.chave}")
    numero = round(float(valor))
    if numero < campo.minimo_ms or numero > campo.maximo_ms:
        raise ErroViradas(
            f"{campo.chave} deve estar entre {campo.minimo_ms} e {campo.maximo_ms} ms"
        )
    return numero


def estrutura_para_web(valores: dict[str, int | None]) -> dict[str, object]:
    """Monta o documento que descreve grupos, campos, limites e valores atuais."""

    grupos: dict[str, dict[str, object]] = {}
    ordem: list[str] = []
    for campo in CAMPOS_VIRADAS:
        if campo.grupo not in grupos:
            grupos[campo.grupo] = {
                "rotulo": ROTULOS_GRUPOS.get(campo.grupo, campo.grupo),
                "campos": [],
            }
            ordem.append(campo.grupo)
        grupos[campo.grupo]["campos"].append(
            {
                "chave": campo.chave,
                "campo": campo.campo,
                "rotulo": campo.rotulo,
                "minimo_ms": campo.minimo_ms,
                "maximo_ms": campo.maximo_ms,
                "passo_ms": campo.passo_ms,
                "valor_ms": valores.get(campo.chave),
                "unidade": "ms",
            }
        )
    return {
        "atuadores_habilitados": False,
        "grupos": [{"id": identificador, **grupos[identificador]} for identificador in ordem],
    }
