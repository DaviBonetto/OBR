# Plano de implementacao da Fase 2

## Objetivo

Produzir um conjunto rotulado, reproduzivel e sem vazamento, seguido por um detector classico
de referencia medido antes do treinamento da IA.

## Etapa 1 — Congelamento e curadoria

- validar sessoes, hashes, imagens e resolucao;
- filtrar indices sem alterar originais;
- dividir por ambiente;
- gerar manifesto, fingerprints e auditoria;
- comprovar reproducibilidade em duas execucoes.

Criterio: cada divisao possui os cinco conteudos e fingerprints identicos entre execucoes.

## Etapa 2 — Rotulagem assistida

- implementar o detector classico inicial;
- gerar mascaras candidatas somente para treino e validacao;
- criar revisao visual de mascara, linha central e ponto objetivo;
- codificar `intersecao -> reto` e `sem_linha -> sem_evidencia`.

Criterio: anotacoes validadas e sem uso do teste na calibracao.

## Etapa 3 — Detector classico de referencia

- congelar parametros usando treino e validacao;
- medir precisao, recall, erro de centro e latencia;
- executar avaliacao uma unica vez no teste fechado;
- registrar falhas por ambiente e iluminacao.

Criterio: benchmark reproduzivel; resultado nao sera confundido com aceitacao no Raspberry.

## Etapa 4 — Entrega para a Fase 3

- exportar imagens, mascaras e indices para Colab;
- validar o carregador do dataset;
- registrar sementes e aumentos permitidos;
- preservar o teste externo sem aumento nem ajuste.

Criterio: notebook recebe exatamente os hashes aprovados e consegue reproduzir a divisao.
