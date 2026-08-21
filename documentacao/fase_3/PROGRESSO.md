# Progresso da Fase 3

## Concluido em 21 de agosto de 2026

- 1.491 rotulos confiaveis consolidados sem abrir o teste;
- 122 linhas rejeitadas isoladas para active learning;
- pacote transportavel deterministico de 284.233.469 bytes;
- loader com ROI 320 x 192 e validacao sem aumentos;
- aumentos de gamma, ganho, sombra, reflexo, ruido, cor, blur e geometria;
- LinhaNet e LR-ASPP implementadas com saida binaria por pixel;
- perda BCE + Dice, metricas e early stopping implementados;
- mixed precision habilitada automaticamente em CUDA;
- smoke test de forward, loss, backward e atualizacao de pesos aprovado na CPU;
- teste preliminar aquecido no PC: LinhaNet 25,5 ms; LR-ASPP 56,5 ms.

Esses tempos sao do PyTorch no computador e nao substituem ONNX nem Raspberry Pi.

## Proximo passo

Executar o notebook no Colab com T4, primeiro para LinhaNet e depois LR-ASPP. Nenhum resultado
de teste sera usado nessa comparacao.
