"""Leitura centralizada das configuracoes TOML do projeto."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


class ErroConfiguracao(RuntimeError):
    """Indica que uma configuracao nao existe ou nao pode ser interpretada."""


def raiz_projeto() -> Path:
    """Retorna a raiz do checkout a partir da localizacao deste modulo."""

    return Path(__file__).resolve().parents[3]


def carregar_toml(caminho: Path) -> dict[str, Any]:
    """Carrega um TOML e converte erros de leitura em uma excecao do dominio."""

    caminho = caminho.resolve()
    if caminho.suffix.lower() != ".toml":
        raise ErroConfiguracao(f"Arquivo de configuracao deve ser TOML: {caminho}")
    if not caminho.is_file():
        raise ErroConfiguracao(f"Configuracao nao encontrada: {caminho}")

    try:
        with caminho.open("rb") as arquivo:
            dados = tomllib.load(arquivo)
    except (OSError, tomllib.TOMLDecodeError) as erro:
        raise ErroConfiguracao(f"Falha ao carregar configuracao: {caminho}") from erro

    if not dados:
        raise ErroConfiguracao(f"Configuracao vazia: {caminho}")
    return dados


def carregar_configuracao(nome_arquivo: str) -> dict[str, Any]:
    """Carrega um arquivo diretamente da pasta ``configuracoes``.

    O nome deve ser simples, sem componentes de caminho. Isso evita que uma entrada
    externa seja usada para ler arquivos fora da pasta de configuracoes.
    """

    nome = Path(nome_arquivo)
    if nome.name != nome_arquivo or nome.is_absolute():
        raise ErroConfiguracao("Use somente o nome do arquivo de configuracao")
    return carregar_toml(raiz_projeto() / "configuracoes" / nome)


def exigir_secao(configuracao: dict[str, Any], nome: str) -> dict[str, Any]:
    """Retorna uma secao obrigatoria ou informa claramente a ausencia."""

    secao = configuracao.get(nome)
    if not isinstance(secao, dict):
        raise ErroConfiguracao(f"Secao obrigatoria ausente ou invalida: {nome}")
    return secao
