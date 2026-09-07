# AGENTS.md

Instrucoes obrigatórias para qualquer agente de IA (ou humano) trabalhando neste repositorio.
Leia este arquivo inteiro antes de escrever ou executar qualquer coisa.

## Manutencao deste arquivo

Este documento deve evoluir junto com o projeto. Sempre que uma tarefa alterar estrutura,
contratos, configuracoes, comandos, regras de seguranca ou o estado do projeto, o mesmo
commit (ou o proximo) deve atualizar este arquivo e os documentos em `documentacao/`.
Um AGENTS.md desatualizado e considerado um defeito.

## O projeto

Software oficial do robo OBR de RoboCup Junior Rescue Line (equipe Davi Bonetto).
Monolito modular em Python 3.11, alvo Raspberry Pi 5, camera USB trocavel.
Fase atual e entregas exatas: `documentacao/ESTADO_DO_PROJETO.md`.

Modulos existentes hoje: `nucleo`, `dispositivos`, `captura`, `painel` e `aplicacao`
(dentro de `codigo/obr_oficial/`). Modulos futuros planejados (`percepcao`, `controle`,
`missao`) so sao criados quando tiverem responsabilidade real implementada.

## Regras inegociaveis de seguranca

1. Nunca habilite atuadores: `atuadores_habilitados = false` e `modo_simulacao = true`
   devem permanecer em `configuracoes/controle.toml`. Ha teste automatizado que falha se
   isso mudar sem decisao explicita do dono.
2. Nunca execute motores, servos, relés ou qualquer atuador, nem em simulacao fisica.
3. Nunca acesse SSH, serial ou rede do Raspberry Pi sem autorizacao explicita do dono.
4. Nao altere configuracoes da camera, IA ou controle sem pedido explicito.
5. Nao capture imagens nem inicie sessoes de dataset sem pedido explicito.
6. Se houver um painel/dashboards rodando no robo, nao mexa nele.
7. Teste de software nunca autoriza movimento fisico. A cadeia de validacao esta em
   `documentacao/SEGURANCA.md` e cada etapa so e provada pela etapa seguinte.

## Regras de arquitetura

- `nucleo` nao depende de camera, interface ou hardware.
- `dispositivos` acessa fisica e nunca decide a missao.
- `percepcao` transforma sensores em estimativas; `controle` transforma objetivos em
  comandos limitados por seguranca; `missao` escolhe comportamentos.
- O painel apenas observa e envia comandos explicitamente permitidos; nunca participa
  do caminho critico de controle.
- Quadros antigos nao formam fila: percepcao consome sempre o quadro mais recente.
- Consumidores dependem do contrato `FonteCamera` e de estimativas imutaveis
  (`EstimativaLinha`), nunca de OpenCV, indice USB ou detalhes internos.
- Nenhuma previsao temporal pode fingir que existe evidencia visual nova.

Detalhes completos: `documentacao/ARQUITETURA.md`. Decisoes registradas em
`documentacao/decisoes/`.

## Comandos padrao

Use sempre uv com o lockfile. Python 3.11 e gerenciado pelo uv via `.python-version`.

```powershell
uv sync --locked --all-extras        # instalar exatamente pelo lockfile
uv run pytest -q                     # testes (26 na Fase 1)
uv run ruff check .                  # lint
uv run ruff format --check .         # formato
uv run python -m compileall -q codigo testes   # sintaxe
uv build                             # pacote sdist + wheel
git diff --check                     # espacos em branco
```

Rode a bateria completa antes de considerar qualquer tarefa concluida. CI (GitHub
Actions `.github/workflows/verificacoes.yml`) executa sync locked, ruff check e pytest;
se falhar localmente, falhara no CI.

Painel com camera sintetica (sem hardware, seguro):

```powershell
uv run obr-capturar --simulacao --host 127.0.0.1 --porta 8080
```

## Convencoes de codigo

- Portugues em identificadores, docstrings, mensagens e documentacao, sem acentos
  (padrao adotado nos arquivos `.md`; mensagens de commit podem usar acentos).
- Ruff: linha maxima 100, regras B, E, F, I, RUF, SIM, UP; alvo py311.
- Contratos em `codigo/obr_oficial/nucleo/contratos.py` sao `dataclass(frozen=True,
  slots=True)` com validacao em `__post_init__`. Nunca quebre imutabilidade ou validez
  dos contratos existentes sem discutir antes.
- Coordenadas normalizadas entre 0.0 e 1.0, independentes de resolucao.
- Sem segredos, videos brutos ou pesos grandes no Git. Pesos so com Git LFS e decisao
  explicita (ver `.gitignore`).

## Git e fluxo de trabalho

- Branches de agente: prefixo `codex/` (exemplo: `codex/agente-secundario-base`),
  criadas a partir de `main` atualizada.
- Commits: curtos, imperativos, em portugues (ex.: "Adiciona painel e captura da Fase 1").
- Nao faca push, PR ou issues sem autorizacao explicita do dono.
- Nao commite artefatos gerados (`dist/`, `build/`, `.venv/`, caches) - ja estao no
  `.gitignore`; confirme com `git status` antes de commitar.
- Antes de commitar: rode a bateria completa de comandos e garanta `git status` limpo
  do que nao pertence ao commit.

## Documentacao viva

Ao concluir uma tarefa, verifique se precisam ser atualizados:

- `documentacao/ESTADO_DO_PROJETO.md` - estado real das entregas;
- `documentacao/ARQUITETURA.md` - fronteiras e arvore de modulos;
- `documentacao/CAPTURA_E_CAMERA.md` - perfis e procedimentos de captura;
- `documentacao/CRITERIOS_DE_ACEITE.md` - metas mensuradas;
- `README.md` e este arquivo.

## Como decidir em duvida

Seguranca primeiro, depois arquitetura, depois simplicidade. Em caso de ambiguidade
entre implementar mais ou menos, implemente menos e pergunte ao dono. Nada aqui
substitui autorizacao explicita do dono para operacoes com risco fisico.
