# Dados brutos

Cada sessao criada pelo painel possui uma pasta exclusiva com:

```text
manifesto.json
capturas.jsonl
quadros/quadro_000001.png
```

O conteudo das sessoes e ignorado pelo Git. Este README permanece versionado para documentar
o formato. Nunca renomeie imagens ou edite manifestos manualmente durante uma sessao.

As sessoes do protocolo verde ficam em `dados/brutos/verde/`. Cada registro inclui
`categoria_verde`, `decisao_verde_esperada`, presenca antes/depois, `cruz_mista` e se a futura
mascara do marcador deve ser vazia. Uma mascara verde vazia nao implica ausencia da linha preta.
