# LR-ASPP verde V1

Candidato neural da Fase Verde 4. A arquitetura é `lraspp_mobilenet_v3_large`, com entrada RGB
normalizada em `1 x 3 x 240 x 320`, quadro inteiro e limiar de máscara `0,75`.

Arquivos locais grandes, ignorados pelo Git:

- `melhor.pt`: checkpoint T4, SHA-256
  `c76a6cc67180cd4753d5d52b48868c7f94b62ff3513427cf5e647d8699f04ae4`;
- `modelo.onnx`: exportação FP32 autocontida, SHA-256
  `3970535c47d9b599bdf730bd00559e4b91a6394ca66c7764c6c47017fdcbd451`.

O `manifesto.json` versionado registra métricas, proveniência, paridade e benchmark local. O
estado continua candidato: geometria conjunta com a linha, Raspberry Pi 5, câmera oficial e teste
final permanecem pendentes.

Reprodução local:

```powershell
uv sync --extra implantacao
uv run obr-exportar-modelo-verde `
  --sha256-checkpoint-esperado c76a6cc67180cd4753d5d52b48868c7f94b62ff3513427cf5e647d8699f04ae4 `
  --sha256-dataset 473ae40feb5614dd686893d584c3f47df4c570aff391759180d098162d18877a `
  --sha256-pacote-resultados 8030558bb818f184bb2d7dbaa883993abba1e09b94e171740a568258695f2c8c
```

Detalhes da seleção estão em `documentacao/fase_verde/AUDITORIA_T4_V1.md`.
