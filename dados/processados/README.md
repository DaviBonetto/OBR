# Dados processados

Esta pasta recebe indices e relatorios reproduziveis gerados a partir das sessoes brutas.
Imagens nao sao copiadas nem alteradas pela preparacao. O conteudo gerado permanece fora do
Git comum; apenas este README documenta o formato.

Cada versao contem:

```text
manifesto_dataset.json
auditoria.jsonl
amostras.jsonl
divisoes/treino.txt
divisoes/validacao.txt
divisoes/teste.txt
```

`auditoria.jsonl` registra a decisao sobre cada quadro original. `amostras.jsonl` possui
somente quadros aprovados e inclui o estado da futura anotacao de mascara e linha central.
