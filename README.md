# OBR

Projeto oficial do robo de RoboCup Junior Rescue Line da equipe de Davi Bonetto.

Este repositorio reunira, em uma unica base organizada, a percepcao visual, o controle do
robo, as estrategias de percurso e resgate, o painel de acompanhamento, o treinamento dos
modelos e a implantacao no Raspberry Pi 5.

## Estado atual

**Fase 0 concluida em 18 de agosto de 2026 — Fundacao do projeto.**

Nesta fase existem somente a arquitetura, os contratos centrais, configuracoes seguras,
documentacao e verificacoes automatizadas. Camera, motores e mecanismos de resgate ainda
nao sao acionados.

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
