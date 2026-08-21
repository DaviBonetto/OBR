# Plano da Fase 3 — segmentacao neural

## Objetivo

Treinar uma mascara binaria robusta a luz, sombra, reflexo e troca de camera, mantendo
inferencia compativel com o Raspberry Pi 5.

## Ciclo 1 — modelo inicial

- treinar somente com 1.065 imagens de treino supervisionadas;
- escolher epoca e limiar somente nas 426 imagens de validacao;
- comparar LinhaNet e LR-ASPP MobileNetV3;
- medir Dice, IoU, precisao, recall e falso positivo nos negativos;
- registrar versoes, semente, configuracao, historico e hashes.

## Ciclo 2 — active learning

- executar os melhores modelos nas 122 linhas rejeitadas pelo usuario;
- priorizar divergencias entre os modelos e baixa confianca;
- corrigir apenas essa fila dificil no painel;
- incorporar as novas mascaras e repetir o treino;
- testar aumentos de baixa luz sem alterar a validacao real.

## Ciclo 3 — congelamento

- congelar arquitetura, limiar e pos-processamento;
- exportar ONNX com o exportador moderno `dynamo=True`;
- comparar PyTorch e ONNX pixel a pixel;
- medir latencia no computador e no Raspberry Pi 5;
- somente entao abrir uma unica vez as 591 imagens do teste.

## Arquiteturas candidatas

| Arquitetura | Parametros | Papel |
|---|---:|---|
| LinhaNet | 32.065 | candidata principal de baixa latencia |
| LR-ASPP MobileNetV3-Large | 3.218.138 | candidata de maior capacidade e professora |

O LR-ASPP e a variante leve de segmentacao do MobileNetV3 disponibilizada pelo
[Torchvision](https://pytorch.org/blog/torchvision-mobilenet-v3-implementation/). O modelo
vencedor sera escolhido pela fronteira precisao/latencia, nao pelo nome da arquitetura.

## Computacao

- CPU local: auditoria, smoke tests, uma etapa de otimizacao e exportacao;
- Colab T4: treinamento completo com mixed precision e comparacao de experimentos;
- Raspberry Pi 5: benchmark final de inferencia, sem treinamento.

O treinamento usa `torch.autocast` e `torch.amp.GradScaler`, conforme a
[documentacao de AMP do PyTorch](https://docs.pytorch.org/docs/stable/notes/amp_examples.html).
As sementes de workers seguem as recomendacoes do
[DataLoader](https://docs.pytorch.org/docs/stable/data.html).
