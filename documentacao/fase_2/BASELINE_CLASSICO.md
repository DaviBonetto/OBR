# Baseline classico v1

## Objetivo

Criar uma referencia explicavel e mascaras candidatas para revisao humana. Este detector nao e
o modelo neural final e suas candidatas nunca viram verdade de treino sem revisao.

## Pipeline

1. recorte da regiao de interesse e redimensionamento para 320 x 192;
2. cinza, CLAHE e suavizacao;
3. limiar global de Otsu combinado com limiar adaptativo e contraste local;
4. abertura e fechamento morfologicos;
5. componentes conexos filtrados por area, altura e nitidez da borda;
6. linha central por faixas horizontais;
7. em alargamento de intersecao, manter a continuacao frontal para o T seguir reto.

As operacoes seguem os contratos documentados pelo OpenCV para
[limiarizacao](https://docs.opencv.org/4.x/d7/d4d/tutorial_py_thresholding.html),
[morfologia](https://docs.opencv.org/4.x/d9/d61/tutorial_py_morphological_ops.html) e
[componentes conexos](https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html).

## Resultado de calibracao

Processamento exclusivo das 1.172 amostras de treino e 441 de validacao. As 591 imagens de
teste nao foram abertas.

| Medida indireta | Resultado |
|---|---:|
| Total processado | 1.613 |
| Linha esperada e encontrada | 1.448 |
| Linha esperada sem evidencia | 12 |
| Negativo corretamente vazio | 139 |
| Negativo com falso positivo | 14 |
| Acuracia de presenca por tipo de captura | 98,3881% |
| Latencia mediana na CPU do computador | 9,2797 ms |
| Latencia p95 na CPU do computador | 11,2772 ms |
| Latencia maxima observada | 18,7141 ms |

Essa acuracia nao mede IoU, Dice, erro de centro nem precisao pixel a pixel, pois as mascaras
humanas ainda nao existem. Ela apenas compara presenca de evidencia com o tipo informado na
captura.

## Falhas observadas

O limiar de nitidez eliminou a maior parte das sombras suaves. Os 14 falsos positivos restantes
sao principalmente objetos ou limites pretos reais em quadros negativos. Esse e um limite
esperado do detector classico e uma justificativa direta para a segmentacao neural da Fase 3.

## Reproducibilidade

- configuracao: `configuracoes/detector_classico.toml`;
- geracao: `uv run obr-gerar-mascaras-classicas`;
- revisao: `uv run obr-revisar-mascaras`;
- registro compacto: `dados/manifestos/fase2_baseline_classico_v1.json`;
- candidatas completas: `dados/rotulados/`, ignoradas pelo Git por conter imagens geradas.
