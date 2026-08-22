# Resultado auditado do treinamento V2

Auditoria concluida em 21 de agosto de 2026, sem abrir o conjunto de teste.

## Proveniencia

- pacote recebido: `OBR_FASE3_V2_RESULTADOS_T4.zip`;
- SHA-256 do pacote: `87bf4db688859fe9b09f95ae9c8f3425c67c0fd22d95203180fce05fd4d9ea57`;
- commit usado no Colab: `b217886bffec1070724f725628ed97eb0f054c0a`;
- SHA-256 do dataset V2: `cd8fc89ddfb151284274998d40c1586df80176a8888e311a1153bf2f1f86eeba`;
- GPU: Tesla T4;
- hashes internos verificados: 10 de 10;
- divisao de teste incluida ou aberta: nao.

## Escolha da arquitetura

O LinhaNet terminou com Dice `0,92546` e FPR significativo `26,09%`, portanto foi rejeitado.
O LR-ASPP terminou com Dice `0,98425` e FPR significativo `15,22%` no limiar de treino `0,50`.
Ele foi selecionado para calibracao porque preservou muito melhor a linha e reduziu o FPR da V1
de `50,00%` para `15,22%`.

O limiar foi calibrado somente nas 426 imagens de validacao:

| Limiar | Dice | Precisao | Recall | FPR significativo |
|---:|---:|---:|---:|---:|
| 0,50 | 0,98425 | 0,98644 | 0,98207 | 15,22% |
| 0,70 | 0,97925 | 0,99248 | 0,96636 | 8,70% |
| **0,80** | **0,97266** | **0,99454** | **0,95173** | **4,35%** |
| 0,90 | 0,95718 | 0,99644 | 0,92089 | 4,35% |

O ponto `0,80` maximiza a pontuacao robusta entre os candidatos avaliados e passa os gates Dice
`>= 0,95` e FPR significativo `<= 0,10`. Permaneceram dois falsos positivos significativos em
46 quadros negativos, ambos do mesmo ambiente com bordas escuras e sombra. Uma tentativa de
elimina-los por geometria zerou o FPR, mas derrubou demais o recall; por isso foi rejeitada.

## Exportacao ONNX

O checkpoint selecionado foi exportado para ONNX FP32, opset 18:

- SHA-256 do checkpoint: `1f14775d85aaec686a9eba69e8fe6ff69c6e484475ada6cca8f3464d699b83a1`;
- SHA-256 do ONNX: `fc01a35bd1415ee1a27ff43d800f1e43f91d36f482ceca4ba179f93df4f2c7cd`;
- maior diferenca absoluta entre logits PyTorch/ONNX: `0,0000495911`;
- concordancia das mascaras em nove entradas: `100%`;
- benchmark ONNX no computador, 50 iteracoes: p50 `15,53 ms`, p95 `23,12 ms`.

Esse benchmark comprova a execucao local, nao o desempenho no Raspberry Pi 5. O teste final,
o benchmark ARM64, a camera oficial e a validacao fisica continuam pendentes. Assim, o artefato
e um candidato aprovado para a Fase 4, ainda nao um modelo final de competicao.
