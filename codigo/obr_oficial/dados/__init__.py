"""Preparacao, versionamento e contratos dos conjuntos de dados."""

from obr_oficial.dados.consolidacao_rotulos import (
    ConfiguracaoConsolidacaoRotulos,
    ConsolidadorRotulos,
    ErroConsolidacaoRotulos,
)
from obr_oficial.dados.mascaras_classicas import (
    ConfiguracaoGeracaoMascaras,
    ErroGeracaoMascaras,
    GeradorMascarasClassicas,
)
from obr_oficial.dados.preparacao_dataset import (
    ConfiguracaoDataset,
    ErroPreparacaoDataset,
    PreparadorDataset,
    carregar_configuracao_dataset,
)
from obr_oficial.dados.referencia_centro import (
    ErroReferenciaCentro,
    RepositorioReferenciaCentro,
    preparar_selecao_referencia,
)

__all__ = [
    "ConfiguracaoConsolidacaoRotulos",
    "ConfiguracaoDataset",
    "ConfiguracaoGeracaoMascaras",
    "ConsolidadorRotulos",
    "ErroConsolidacaoRotulos",
    "ErroGeracaoMascaras",
    "ErroPreparacaoDataset",
    "ErroReferenciaCentro",
    "GeradorMascarasClassicas",
    "PreparadorDataset",
    "RepositorioReferenciaCentro",
    "carregar_configuracao_dataset",
    "preparar_selecao_referencia",
]
