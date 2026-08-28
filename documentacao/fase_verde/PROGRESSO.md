# Percepcao verde

Atualizado em 28 de agosto de 2026.

## Estado

**Fase Verde 2 em revisão. As máscaras candidatas e a fila essencial foram produzidas.**

O painel foi executado no Raspberry Pi 5 com a câmera USB provisória. Cinco sessões físicas, em
quatro locais, produziram 4.125 imagens. O snapshot bruto foi copiado e verificado por SHA-256;
nenhum PNG está ausente, ilegível, corrompido ou duplicado exatamente. A curadoria V1 selecionou
3.268 quadros sem alterar os originais. Consulte
[`AUDITORIA_DATASET_V1.md`](AUDITORIA_DATASET_V1.md).

O bootstrap V1 processou somente os 2.356 quadros de treino/validação, mantendo o teste fechado.
Foram produzidas 1.674 candidatas normais, 324 máscaras negativas vazias por contrato e 358 casos
prioritários. A revisão inicial foi reduzida a 75 representantes temporais sem aprovar
automaticamente seus vizinhos. Consulte [`MASCARAS_VERDES_V1.md`](MASCARAS_VERDES_V1.md).

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

### Implementacao entregue

- modo `verde` separado do painel antigo de linha;
- pasta padrao `dados/brutos/verde`;
- cinco categorias em botoes grandes com atalhos de `1` a `5`;
- campo de cruz mista disponivel somente quando existe marcador antes;
- decisao esperada visivel antes de cada captura;
- contadores persistentes por categoria no manifesto da sessao;
- validacao da categoria no servidor, nao apenas no navegador;
- metadados explicitos de marcador antes, depois, duplo e mascara vazia;
- imagem PNG original, sem mascara automatica ou IA durante a captura;
- camera, brilho, exposicao, nitidez, local, piso, iluminacao e LEDs registrados;
- motores e demais atuadores fora do processo.

### Captura e auditoria concluídas

- 5 sessões físicas e 4.125 PNGs preservados;
- 4.125 hashes individuais verificados;
- 151 rótulos de cruz mista corrigidos com confirmação humana e visual;
- 8 quadros sem marcador reclassificados como negativos;
- 10 quadros geometricamente ambíguos excluídos do índice;
- 847 quase duplicatas temporais retiradas apenas do índice;
- 3.268 quadros selecionados para a etapa de máscaras;
- treino, validação e teste separados por sessão e ambiente completos;
- teste mantido fora das decisões de máscara e treinamento.

Comando local:

```powershell
uv run obr-capturar --modo verde --simulacao --host 127.0.0.1 --porta 8080
```

Comando no Raspberry Pi:

```bash
uv run --locked --extra captura obr-capturar --modo verde \
  --origem /dev/video0 --host 0.0.0.0 --porta 8080
```

### Protocolo para cada sessao real

1. usar uma sessao para cada combinacao de local, iluminacao, piso, camera e LEDs;
2. escolher a categoria antes de iniciar uma sequencia;
3. mover distancia, angulo e orientacao do robo para evitar quadros quase iguais;
4. ativar `cruz mista` somente quando houver verde valido antes e verde depois;
5. usar `depois - ignorar` quando houver marcador oficial somente depois;
6. usar `sem verde / negativo` quando nao houver marcador oficial valido, mesmo com linha;
7. finalizar a sessao antes de mudar de ambiente ou condicao de luz.

Objetos verdes que nao sao marcadores oficiais pertencem aos negativos dificeis. A futura mascara
de marcador sera vazia nesses casos, enquanto um marcador oficial depois continuara tendo mascara
verde e sera descartado apenas pela geometria.

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

As máscaras atuais são candidatas, não rótulos supervisionados consolidados. Ainda não existe
modelo neural verde, rastreamento temporal ou benchmark do detector verde no Raspberry Pi. A
câmera provisória foi usada na captura, mas essa evidência não prova generalização para a câmera
oficial. A fila essencial precisa ser revisada antes de liberar o primeiro treinamento; essa
fronteira é registrada no manifesto gerado.
