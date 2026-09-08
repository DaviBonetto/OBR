# Treinamento neural verde V1

Atualizado em 8 de setembro de 2026.

## Estado

O treinamento foi concluído na T4 e o resultado foi auditado. Uma inconsistência conhecida de
metadados na validação exigiu a curadoria V2; como o treino não mudou, o checkpoint LR-ASPP foi
reavaliado sem repetir o treinamento. Ele é agora candidato da Fase Verde 4, não modelo final.
Consulte [`AUDITORIA_T4_V1.md`](AUDITORIA_T4_V1.md).

## Dataset transportável

| Campo | Valor |
|---|---:|
| total | 2.085 |
| treino | 1.302 |
| validação | 783 |
| active learning fora do pacote | 271 |
| tamanho | 501.481.335 bytes |
| SHA-256 | `c2d1badc4dd8224c06a186dad7ce5264ccb7b3996917b06bd1c3332e649042ec` |

O arquivo local é `artefatos/fase_verde_3_dataset_v1.zip`. Uma segunda exportação produziu o
mesmo tamanho e o mesmo SHA-256. O ZIP passou pela verificação CRC, contém as cinco categorias e
não contém a divisão de teste.

## Estratégia mínima

O alvo neural é uma única máscara binária: marcador verde oficial ou fundo. Antes/depois,
esquerda/direita, cruz mista e retorno de 180 graus permanecem como metadados e serão decididos
depois pela geometria conjunta com a linha. Treinar um classificador de movimento agora duplicaria
a lógica e aprenderia atalhos de posição da câmera.

O primeiro ciclo compara:

- `LinhaNet`, para medir o limite de velocidade;
- `LR-ASPP MobileNetV3-Large`, para medir o limite de precisão.

As duas recebem o quadro inteiro em `320 x 240`; nenhum corte vertical é aplicado. Os aumentos de
treino simulam luz, sombra, reflexo, ruído e pequenas mudanças geométricas. A validação real não
recebe aumentos. Negativos têm maior probabilidade de amostragem e uma perda de presença específica
para punir falsos marcadores.

## Seleção e gates

Depois do treinamento, cada checkpoint é avaliado nos limiares de `0,30` a `0,95`, somente na
validação. Um par modelo/limiar passa pelo gate inicial quando atende simultaneamente:

- Dice pelo menos `0,95`;
- precisão pelo menos `0,97`;
- recall pelo menos `0,93`;
- falsos positivos significativos em no máximo `5%` dos negativos.

O vencedor ainda é provisório. Depois do ZIP da T4 serão obrigatórias a inspeção visual, a rodada
de active learning e, mais tarde, a medição no Raspberry Pi 5 com a câmera provisória e a oficial.

## Execução

Abra [`treinamento/fase_verde_3/treinar_verde_no_colab.ipynb`](../../treinamento/fase_verde_3/treinar_verde_no_colab.ipynb)
no Colab, selecione uma T4, execute todas as células e envie de volta apenas
`OBR_VERDE_FASE3_RESULTADOS_T4.zip`.

O notebook verifica o hash e o tamanho do dataset, fixa a revisão do código, confirma a GPU,
treina as duas arquiteturas, calibra os limiares e inclui checkpoints, históricos, comparação,
ambiente e hashes no ZIP final.

## Evidência local

O pacote real foi carregado com lotes de treino e validação em `320 x 240`. LinhaNet e LR-ASPP
completaram forward, cálculo de perda e backward na CPU. Isso valida o encadeamento dos dados e do
código, não a precisão neural, a velocidade da T4 ou o desempenho físico do Raspberry Pi.
