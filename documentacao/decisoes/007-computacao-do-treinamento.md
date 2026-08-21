# 007 — CPU agora, GPU T4 no treinamento neural

## Estado

Aceita em 21 de agosto de 2026.

## Decisao

A Fase 2 usa a CPU do computador e do Raspberry Pi para curadoria, detector classico,
geracao de mascaras, revisao e benchmarks de OpenCV. Esses trabalhos sao leves, iterativos e
nao justificam transferir o dataset para uma GPU remota.

Na Fase 3, os testes rapidos do carregador e de um lote continuarao locais, mas o treinamento
comparativo das redes de segmentacao usara a T4 do Colab. A GPU sera usada para testar
arquiteturas leves, aumentos de iluminacao e repeticoes com sementes registradas. O modelo
final nao dependera do Colab: sera exportado e medido no Raspberry Pi 5.

## Consequencias

- nenhuma T4 e necessaria para concluir a rotulagem da Fase 2;
- a T4 reduz de forma importante o tempo da busca experimental da Fase 3;
- um resultado de Colab nao prova desempenho em tempo real no Raspberry;
- arquitetura e resolucao serao escolhidas por precisao e latencia medidas, nao apenas pela
  velocidade de treinamento na GPU;
- imagens e mascaras aprovadas serao exportadas por manifesto e hash, sem liberar o teste para
  ajuste.
