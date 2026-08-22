# Referencia humana do centro da linha

Esta pasta contem o gate independente da geometria da Fase 4.

- `selecao.jsonl`: 48 imagens de validacao selecionadas deterministicamente, 12 por tipo;
- `anotacoes.jsonl`: log anexado criado pelo painel conforme a revisao humana avanca.

As imagens permanecem no dataset local e nao sao duplicadas aqui. O conjunto de teste e recusado
pelo seletor, pelo repositorio, pelo painel e pela avaliacao.

No painel, os pontos devem ser marcados em ordem: do centro da linha mais proximo do robo ate o
destino. Em uma intersecao T, a referencia segue reto. A previsao da IA fica escondida por padrao
para nao influenciar a anotacao humana.
