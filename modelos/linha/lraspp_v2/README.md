# LR-ASPP V2

Candidato selecionado para iniciar a Fase 4. A arquitetura e
`lraspp_mobilenet_v3_large`, com entrada RGB normalizada em `1 x 3 x 192 x 320`, recorte dos
30% superiores da imagem e limiar de mascara `0,80`.

Arquivos locais grandes, ignorados pelo Git:

- `melhor.pt`: checkpoint T4, SHA-256
  `1f14775d85aaec686a9eba69e8fe6ff69c6e484475ada6cca8f3464d699b83a1`;
- `modelo.onnx`: exportacao FP32 autocontida, SHA-256
  `fc01a35bd1415ee1a27ff43d800f1e43f91d36f482ceca4ba179f93df4f2c7cd`.

O arquivo `manifesto.json` e versionado e registra metricas, proveniencia, paridade e benchmark
local. O estado ainda e `candidato_fase4`: nao houve benchmark no Raspberry Pi 5, troca da
camera, validacao fisica nem abertura do teste final.

Reproducao local:

```powershell
uv sync --extra implantacao
uv run obr-exportar-modelo-linha `
  --sha256-checkpoint-esperado 1f14775d85aaec686a9eba69e8fe6ff69c6e484475ada6cca8f3464d699b83a1 `
  --sha256-dataset cd8fc89ddfb151284274998d40c1586df80176a8888e311a1153bf2f1f86eeba `
  --sha256-pacote-resultados 87bf4db688859fe9b09f95ae9c8f3425c67c0fd22d95203180fce05fd4d9ea57
```
