# Percepcao verde

Atualizado em 24 de agosto de 2026.

## Estado

**Fase Verde 0 concluida. A proxima etapa e a Fase Verde 1: captura.**

Esta frente amplia a percepcao da pista sem substituir, pausar ou retreinar o detector de linha.
O modelo e a configuracao aprovados da linha foram congelados no manifesto
`dados/manifestos/fase_verde_0.json` para permitir regressao objetiva.

## Regra funcional congelada

O verde publica apenas uma intencao de intersecao:

| Evidencia relativa ao sentido de chegada | Decisao verde |
|---|---|
| um marcador antes e a esquerda | `virar_esquerda` |
| um marcador antes e a direita | `virar_direita` |
| marcador depois da intersecao | `nenhuma` |
| dois marcadores antes, um de cada lado | `retornar_180` |
| nenhum marcador valido | `nenhuma` |

Em uma cruz mista, todos os marcadores depois sao preservados no diagnostico como
`depois_ignorado`, mas somente os marcadores antes participam da decisao. Dois componentes do
mesmo lado nao autorizam retorno.

As regras internacionais de 2026 registram marcadores verdes de `25 mm x 25 mm`, posicionados
imediatamente antes da intersecao. Dois marcadores antes, um em cada lado da linha, indicam um
beco sem saida e exigem retorno:
<https://junior.robocup.org/wp-content/uploads/2026/02/RCJRescueLine2026-final.pdf>, secao 3.6.

## Integracao simultanea com a linha

`EstimativaPista` carrega `EstimativaLinha` e `EstimativaVerde` do mesmo quadro:

```text
quadro mais recente
   |-- percepcao da linha  -> EstimativaLinha  -> seguimento normal
   `-- percepcao do verde  -> EstimativaVerde  -> intencao opcional
                                      |
                         AUSENTE/NENHUMA nao altera a linha
```

`SEM VERDE` nao e uma ordem para seguir reto e nao e uma imagem sem linha. E uma mascara verde
vazia. A imagem ainda pode e normalmente deve conter a linha preta, que continua sendo processada
pelo detector de linha.

Na futura base de treinamento, cada quadro tera evidencias separadas:

- imagem RGB original;
- mascara da linha, quando aplicavel ao conjunto de linha;
- mascara de todos os pixels verdes, inclusive marcadores depois;
- papel geometrico por instancia: antes esquerda, antes direita ou depois;
- decisao humana esperada: nenhuma, esquerda, direita ou retorno.

Negativos importantes incluem linha sem verde, intersecao sem verde, objetos verdes longe da
linha, reflexos, piso, roupa, grama e verde somente depois. Nos negativos sem marcador a mascara
verde e vazia; isso nao apaga nem enfraquece a mascara de linha.

## Contratos implementados

- `EstadoVerde`: ausente, candidata, confirmada ou ambigua;
- `DecisaoVerde`: nenhuma, esquerda, direita ou retorno de 180 graus;
- `PosicaoMarcadorVerde`: antes esquerda, antes direita, depois ignorado ou ambigua;
- `EstimativaVerde`: resultado imutavel, com confianca, marcadores, fonte, motivo e latencia;
- `EstimativaPista`: composicao imutavel da linha e do verde no mesmo quadro;
- `ReferencialIntersecao`: centro e sentido de avanco independentes da rotacao da camera;
- `InterpretadorGeometricoVerde`: antes/depois e esquerda/direita sem comandar atuadores.

A saida da Fase 0 e instantanea e recebe estado `candidata`. A confirmacao de tres em cinco
quadros esta contratada na configuracao, mas so sera implementada depois de existir evidencia
visual real. Nenhum teste geometrico finge ser deteccao por camera.

## Fase Verde 1 - captura

O painel de captura tera cinco categorias, pois o treinamento precisa separar verde invalido de
ausencia real:

1. antes - esquerda;
2. antes - direita;
3. dois antes - retorno de 180 graus;
4. depois - ignorar, incluindo cruz mista;
5. sem verde / negativo.

A tela continuara mostrando a camera inteira. As categorias classificam o papel do verde, nao o
comportamento da linha. Sessoes, ambientes e camera permanecerao registrados em manifestos, e as
divisoes de treino, validacao e teste serao feitas por sessao completa.

## Gates da Fase 0

- [x] linha e verde coexistem no mesmo contrato de quadro;
- [x] ausencia de verde e estritamente neutra;
- [x] verde depois e detectavel, mas nao gera comando;
- [x] cruz mista obedece somente ao verde antes;
- [x] esquerda e direita dependem do sentido de chegada, nao da tela;
- [x] retorno exige dois lados opostos;
- [x] modelo, configuracao e implementacao da linha possuem hashes congelados;
- [x] atuadores permanecem desabilitados;
- [x] teste final permanece fechado.

## Limites atuais

Ainda nao existem detector cromatico, modelo neural, mascara verde real, painel de captura verde,
rastreamento temporal ou benchmark no Raspberry Pi. Os testes desta fase validam apenas contrato
e geometria sintetica. Luz, camera, latencia e imagens reais pertencem as fases seguintes.
