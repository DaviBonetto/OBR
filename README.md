# OBR

Projeto oficial do robo de RoboCup Junior Rescue Line da equipe de Davi Bonetto.

Este repositorio reunira, em uma unica base organizada, a percepcao visual, o controle do
robo, as estrategias de percurso e resgate, o painel de acompanhamento, o treinamento dos
modelos e a implantacao no Raspberry Pi 5.

## Estado atual

**Fase 4 iniciada — candidato neural exportado, com teste final ainda fechado.**

A Fase 1 foi concluida com camera USB substituivel, painel de captura e 29 sessoes fisicas.
A Fase 2 foi executada com copia de seguranca, verificacao de hashes, curadoria deterministica e
separacao por ambiente. Na Fase 3, o LR-ASPP V2 foi calibrado em limiar `0,80`, atingiu Dice
`0,97266` e FPR significativo `4,35%` na validacao e foi exportado para ONNX com `100%` de
concordancia das mascaras avaliadas. Motores e mecanismos de resgate continuam sem acionamento.

Consulte [`documentacao/ESTADO_DO_PROJETO.md`](documentacao/ESTADO_DO_PROJETO.md) para o
registro exato do que esta pronto e do que ainda depende de validacao fisica.

Repositorio principal: [DaviBonetto/OBR](https://github.com/DaviBonetto/OBR).

## Objetivo

Construir um sistema rapido, mensuravel e robusto que:

- detecte e acompanhe a linha em ambientes e iluminacoes variadas;
- estime o ponto atual, o ponto objetivo, o erro lateral, a direcao e a curvatura;
- controle locomocao, curvas, obstaculos e o procedimento de resgate;
- apresente video e telemetria em um painel preto, limpo e desacoplado;
- execute em tempo real no Raspberry Pi 5;
- comece sempre com os atuadores desabilitados.

## Organizacao

```text
configuracoes/   Parametros versionados e sem segredos
codigo/          Pacote Python do robo
dados/           Regras e manifestos dos conjuntos de dados
documentacao/    Arquitetura, seguranca, decisoes e estado
ferramentas/     Captura, calibracao, avaliacao e diagnostico
implantacao/     Instalacao e servicos do Raspberry Pi
modelos/         Manifestos e modelos aprovados
testes/          Testes unitarios, integrados, regressao e hardware
treinamento/     Notebooks e rotinas de treinamento
```

A arvore completa planejada e as fronteiras entre modulos estao em
[`documentacao/ARQUITETURA.md`](documentacao/ARQUITETURA.md).

## Preparacao local

Requisitos:

- Python 3.11 ou superior;
- [uv](https://docs.astral.sh/uv/).

No PowerShell:

```powershell
uv sync --extra desenvolvimento
uv run ruff check .
uv run pytest
```

Para abrir o painel com camera sintetica:

```powershell
uv sync --all-extras
uv run obr-capturar --simulacao --host 127.0.0.1 --porta 8080
```

Para preparar a versao congelada do dataset sem alterar os originais:

```powershell
uv sync --extra dados
uv run obr-preparar-dataset
```

Para gerar as mascaras candidatas de treino/validacao e abrir a revisao local:

```powershell
uv run obr-gerar-mascaras-classicas
uv run obr-revisar-mascaras --host 127.0.0.1 --porta 8091
```

A CPU local atende toda a Fase 2. A T4 do Colab sera usada na Fase 3 para comparar e treinar
redes leves de segmentacao; o modelo final continuara sendo medido e executado no Raspberry Pi 5.

Para reproduzir a consolidacao e o pacote inicial da Fase 3:

```powershell
uv run obr-consolidar-rotulos --candidatas dados/rotulados/fase2_v1_classico_candidatas_v4
uv run obr-exportar-fase3
```

O treinamento completo deve usar o notebook
[`treinamento/fase_3/treinar_no_colab.ipynb`](treinamento/fase_3/treinar_no_colab.ipynb).
Um smoke test local pode usar `obr-treinar-segmentacao`, mas nao substitui os experimentos T4
nem o benchmark do Raspberry.

Antes de um treinamento V2, os desacordos entre o modelo e rotulos vazios sao isolados por
`obr-auditar-rotulos-fase3` e revisados no mesmo painel, sem abrir o conjunto de teste. O fluxo e
documentado em [`treinamento/README.md`](treinamento/README.md).

O dataset V2 e gerado por `obr-consolidar-dataset-v2`. O notebook da Fase 3 usa hard negatives e
recusa promover um modelo com falsos positivos significativos acima do gate definido. O resultado
auditado e a justificativa do limiar estao em
[`documentacao/fase_3/RESULTADO_V2.md`](documentacao/fase_3/RESULTADO_V2.md).

## Regras que nao podem ser quebradas

1. A interface nunca participa do caminho critico de controle.
2. Quadros antigos nao formam fila: a percepcao consome sempre o quadro mais recente.
3. Nenhuma previsao temporal pode fingir que existe evidencia visual nova.
4. Dados de treino, validacao e teste sao separados por sessao e ambiente.
5. Motores e servos permanecem desabilitados por padrao.
6. Teste automatizado, simulacao e validacao fisica sao relatados separadamente.
7. Nenhum segredo, video bruto ou peso grande entra no Git acidentalmente.

## Fases

| Fase | Resultado principal |
|---|---|
| 0 | Fundacao, contratos, configuracoes, documentacao, testes e GitHub |
| 1 | Camera USB, calibracao, captura e reproducao deterministica |
| 2 | Dataset inicial, rotulagem e detector classico de referencia |
| 3 | Treinamento e exportacao da segmentacao por IA |
| 4 | Geometria, confianca, rastreamento e painel da linha |
| 5 | Benchmark e implantacao no Raspberry Pi 5 |
| 6 | Controle de locomocao em simulacao e com rodas suspensas |
| 7 | Percepcao completa da pista e maquina de estados |
| 8 | Sistema de resgate e testes integrados |
| 9 | Validacao de campo, endurecimento e preparacao para competicao |

## Seguranca

O projeto nao considera um teste de software como autorizacao para movimento real. O
procedimento obrigatorio esta em [`documentacao/SEGURANCA.md`](documentacao/SEGURANCA.md).
