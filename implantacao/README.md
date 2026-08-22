# Implantacao

A exportacao FP32 para ONNX ja esta implementada por `obr-exportar-modelo-linha`. O comando:

- verifica o SHA-256 do checkpoint antes de carrega-lo;
- exporta uma entrada fixa `1 x 3 x 192 x 320`;
- valida o grafo ONNX;
- recalcula a validacao sem tocar no teste;
- compara logits e mascaras com o PyTorch;
- executa um benchmark identificado explicitamente como local.

O resultado aprovado e descrito em `modelos/linha/lraspp_v2/manifesto.json`. A instalacao do
ONNX Runtime ARM64 e o benchmark real serao feitos no Raspberry Pi 5 antes de escolher FP32 ou
uma possivel quantizacao INT8. Nenhum servico inicia automaticamente e nenhum atuador e usado.

O runtime da Fase 4 pode ser validado sem hardware por:

```powershell
uv sync --extra percepcao
uv run obr-percepcao-linha --simulacao --host 127.0.0.1 --porta 8081
```

Para a camera USB, remova `--simulacao`. Antes de executar no Raspberry, o endereco, usuario SSH,
`/dev/video0` e perfil da camera devem ser confirmados novamente. O comando nao inicia motores.
