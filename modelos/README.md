# Modelos

Cada candidato possui manifesto versionado com formato, hash, entrada, metricas e dataset de
origem. Pesos e arquivos ONNX sao grandes e continuam ignorados pelo Git; eles so podem ser
reconstruidos ou copiados quando o hash coincidir com o manifesto.

O primeiro candidato neural fica em `linha/lraspp_v2`. Ele passou pelos gates de validacao e
pela equivalencia PyTorch/ONNX, mas ainda nao e o modelo final: faltam benchmark e validacao
fisica no Raspberry Pi 5, troca da camera e abertura unica do conjunto de teste congelado.
