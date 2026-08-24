# Arquitetura

## Contexto

O projeto executara em um Raspberry Pi 5, recebera video de uma camera USB e, quando as
fases de seguranca forem concluidas, controlara locomocao e resgate. O caminho critico deve
continuar funcional mesmo sem painel, rede ou gravacao de dados.

## Decisao principal

O sistema sera um monolito modular em Python. Os modulos compartilham contratos pequenos,
mas permanecem separados por responsabilidade. Nao usaremos microsservicos, filas externas,
banco de dados ou abstracoes de hardware antes de haver uma necessidade real.

## Fluxo planejado

```text
camera USB
   -> ultimo quadro disponivel
   -> pre-processamento e calibracao
   -> percepcao da linha, pista e resgate
   -> estimativas imutaveis
   -> maquina de estados da missao
   -> controle e camada de seguranca
   -> dispositivos fisicos

estimativas e eventos
   -> telemetria
   -> painel web opcional
```

## Regra de dependencias

- `nucleo` nao depende de camera, interface ou hardware.
- `dispositivos` implementa acesso fisico e nao decide a missao.
- `percepcao` transforma sensores em estimativas; nao comanda motores.
- `controle` transforma objetivos em comandos limitados pela seguranca.
- `missao` escolhe comportamentos sem escrever diretamente no hardware.
- `painel` observa o sistema e envia apenas comandos explicitamente permitidos.
- `aplicacao` monta os componentes e define o modo de execucao.

## Arvore final planejada

```text
OBR-Oficial/
├── configuracoes/
├── codigo/obr_oficial/
│   ├── nucleo/
│   ├── dispositivos/
│   ├── captura/
│   ├── percepcao/
│   │   ├── comum/
│   │   ├── linha/
│   │   ├── pista/
│   │   └── resgate/
│   ├── controle/
│   ├── missao/
│   ├── painel/
│   └── aplicacao/
├── ferramentas/
├── treinamento/
├── dados/
├── modelos/
├── testes/
├── documentacao/
└── implantacao/
```

Pastas e modulos so serao materializados quando tiverem uma responsabilidade implementada
ou documentacao necessaria. Isso evita uma arvore cheia de arquivos vazios.

## Contrato inicial da linha

`EstimativaLinha` e a fronteira entre percepcao, painel e futuro controle. Pontos usam
coordenadas normalizadas entre zero e um, independentes da resolucao. A estimativa inclui
estado, confianca, centro, ponto atual, ponto objetivo, erros, curvatura, origem da evidencia,
idade e tempos de processamento.

O painel jamais le diretamente tensores, mascaras internas ou variaveis do modelo. O futuro
controle tambem consumira somente o contrato validado.

Na Fase 4, `ProcessadorContinuoLinha` concretiza esse fluxo em uma thread independente. Ele
consome sempre o ultimo `QuadroCamera`, publica somente o ultimo `ResultadoQuadroLinha` e entrega
ao painel uma serializacao de `EstimativaLinha`. O dashboard nao possui endpoint de comando e a
inferencia continua funcionando mesmo que nenhum navegador esteja conectado.

## Contrato da pista e do verde

`EstimativaPista` agrega uma `EstimativaLinha` e uma `EstimativaVerde` produzidas para o mesmo
quadro. A agregacao nao cria prioridade implicita: a linha permanece ativa em todos os quadros e
o verde publica apenas uma intencao opcional para a futura maquina de estados.

`DecisaoVerde.NENHUMA` e o resultado normal quando nao ha verde, quando o unico marcador esta
depois da intersecao ou quando a geometria e ambigua. Portanto, um negativo do verde nunca apaga
a linha e nunca comanda motores. A percepcao verde reside em `percepcao/pista/verde` e depende do
contrato da linha somente para formar o referencial da intersecao, sem alterar o detector neural.

## Dados e modelos

- Videos brutos e rotulos completos ficam fora do Git comum.
- Cada sessao recebe manifesto com contexto e hashes.
- O conjunto de teste e separado por sessao e local, nunca por quadros aleatorios vizinhos.
- Cada modelo aprovado possui manifesto, metricas, formato, hash e configuracao de entrada.
- Pesos grandes somente entram no repositorio por decisao explicita e Git LFS.

## Troca de camera

Consumidores dependem de `FonteCamera`, nao de OpenCV, indice USB ou modelo fisico. Camera
USB e simulacao implementam o mesmo contrato. Perfis e calibracoes permanecem fora do codigo,
permitindo que a camera provisoria e a oficial tenham parametros independentes.
