"""Preparacao, versionamento e contratos dos conjuntos de dados."""

from obr_oficial.dados.auditoria_verde import (
    CuradorDatasetVerde,
    ErroAuditoriaVerde,
    PlanoCuradoriaVerde,
    carregar_plano_curadoria_verde,
)
from obr_oficial.dados.consolidacao_rotulos import (
    ConfiguracaoConsolidacaoRotulos,
    ConsolidadorRotulos,
    ErroConsolidacaoRotulos,
)
from obr_oficial.dados.consolidacao_verde import (
    ConfiguracaoConsolidacaoVerde,
    ConsolidadorRotulosVerdes,
    ErroConsolidacaoVerde,
)
from obr_oficial.dados.mascaras_classicas import (
    ConfiguracaoGeracaoMascaras,
    ErroGeracaoMascaras,
    GeradorMascarasClassicas,
)
from obr_oficial.dados.mascaras_verdes import (
    ConfiguracaoGeracaoMascarasVerdes,
    ConfiguracaoMascarasVerdes,
    DetectorCromaticoVerde,
    ErroMascarasVerdes,
    GeradorMascarasVerdes,
    ResultadoMascaraVerde,
    carregar_configuracao_mascaras_verdes,
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
    "ConfiguracaoConsolidacaoVerde",
    "ConfiguracaoDataset",
    "ConfiguracaoGeracaoMascaras",
    "ConfiguracaoGeracaoMascarasVerdes",
    "ConfiguracaoMascarasVerdes",
    "ConsolidadorRotulos",
    "ConsolidadorRotulosVerdes",
    "CuradorDatasetVerde",
    "DetectorCromaticoVerde",
    "ErroAuditoriaVerde",
    "ErroConsolidacaoRotulos",
    "ErroConsolidacaoVerde",
    "ErroGeracaoMascaras",
    "ErroMascarasVerdes",
    "ErroPreparacaoDataset",
    "ErroReferenciaCentro",
    "GeradorMascarasClassicas",
    "GeradorMascarasVerdes",
    "PlanoCuradoriaVerde",
    "PreparadorDataset",
    "RepositorioReferenciaCentro",
    "ResultadoMascaraVerde",
    "carregar_configuracao_dataset",
    "carregar_configuracao_mascaras_verdes",
    "carregar_plano_curadoria_verde",
    "preparar_selecao_referencia",
]
