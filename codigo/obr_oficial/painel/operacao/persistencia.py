"""Persistencia atomica dos tempos de virada em ``configuracoes/viradas.toml``.

O arquivo e sempre reescrito a partir de um gabarito fixo, com gravacao em
arquivo temporario seguida de ``os.replace``, para nunca deixar um TOML pela
metade. Valores indefinidos sao armazenados como string vazia, decisao do dono
para nao sugerir defaults inventados.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from threading import Lock

from obr_oficial.painel.operacao.viradas import (
    CAMPOS_VIRADAS,
    ErroViradas,
    exigir_campo,
    validar_valor,
)

_GABARITO = """\
# Tempos de manobra do robo OBR, em milissegundos.
# Editavel pelo painel de operacao (obr-painel) ou manualmente.

[viradas.esquerda]
avanco_ms = {esquerda_avanco}
giro_ms = {esquerda_giro}

[viradas.direita]
avanco_ms = {direita_avanco}
giro_ms = {direita_giro}

[viradas.verde]
primeiro_giro_ms = {verde_primeiro_giro}
reverso_ms = {verde_reverso}
segundo_giro_ms = {verde_segundo_giro}

[viradas.verde90]
primeiro_giro_ms = {verde90_primeiro_giro}
reverso_ms = {verde90_reverso}

[viradas.gap]
avanco_ms = {gap_avanco}
confirmacao_ms = {gap_confirmacao}
"""


def _formato_toml(valor: int | None) -> str:
    if valor is None:
        return "0"
    return str(int(valor))


def _texto_para_valor(bruto: object, chave: str) -> int | None:
    if bruto is None or bruto == "":
        return 0
    if isinstance(bruto, bool) or not isinstance(bruto, (int, float)):
        raise ErroViradas(f"Valor invalido no arquivo de configuracao: {chave}")
    campo = exigir_campo(chave)
    numero = round(float(bruto))
    if numero < campo.minimo_ms or numero > campo.maximo_ms:
        raise ErroViradas(
            f"{chave} fora dos limites no arquivo: {numero} ms "
            f"(permitido {campo.minimo_ms} a {campo.maximo_ms})"
        )
    return numero


def valores_iniciais() -> dict[str, int | None]:
    """Mapa completo de chaves para valores, inicia em zero."""

    return {campo.chave: 0 for campo in CAMPOS_VIRADAS}


def carregar(caminho: Path) -> dict[str, int | None]:
    """Le o arquivo existente; ausencia do arquivo retorna tudo indefinido."""

    valores = valores_iniciais()
    if not caminho.is_file():
        return valores
    with caminho.open("rb") as arquivo:
        dados = tomllib.load(arquivo)
    secao = dados.get("viradas")
    if not isinstance(secao, dict):
        return valores
    for campo in CAMPOS_VIRADAS:
        grupo = secao.get(campo.grupo)
        if isinstance(grupo, dict) and campo.campo in grupo:
            valores[campo.chave] = _texto_para_valor(grupo[campo.campo], campo.chave)
    return valores


def gravar(caminho: Path, valores: dict[str, int | None]) -> None:
    """Reescreve o arquivo inteiro de forma atomica."""

    conteudo = _GABARITO.format(
        esquerda_avanco=_formato_toml(valores["esquerda.avanco_ms"]),
        esquerda_giro=_formato_toml(valores["esquerda.giro_ms"]),
        direita_avanco=_formato_toml(valores["direita.avanco_ms"]),
        direita_giro=_formato_toml(valores["direita.giro_ms"]),
        verde_primeiro_giro=_formato_toml(valores["verde.primeiro_giro_ms"]),
        verde_reverso=_formato_toml(valores["verde.reverso_ms"]),
        verde_segundo_giro=_formato_toml(valores["verde.segundo_giro_ms"]),
        verde90_primeiro_giro=_formato_toml(valores["verde90.primeiro_giro_ms"]),
        verde90_reverso=_formato_toml(valores["verde90.reverso_ms"]),
        gap_avanco=_formato_toml(valores["gap.avanco_ms"]),
        gap_confirmacao=_formato_toml(valores["gap.confirmacao_ms"]),
    )
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".toml.tmp")
    temporario.write_text(conteudo, encoding="utf-8")
    os.replace(temporario, caminho)


class GerenciadorViradas:
    """Guarda os valores em memoria e persiste cada alteracao confirmada."""

    def __init__(self, caminho: Path) -> None:
        self._caminho = caminho
        self._lock = Lock()
        self._valores = carregar(caminho)

    @property
    def caminho(self) -> Path:
        return self._caminho

    def definir(self, chave: str, valor: object) -> int:
        """Valida, grava e retorna o valor canonico."""

        campo = exigir_campo(chave)
        numero = validar_valor(campo, valor)
        with self._lock:
            self._valores[chave] = numero
            gravar(self._caminho, self._valores)
        return numero

    def como_dict(self) -> dict[str, int | None]:
        with self._lock:
            return dict(self._valores)
