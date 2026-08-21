# Treinamento

Os notebooks de linha e resgate serao criados quando existirem datasets versionados. Cada
treinamento devera registrar sementes, divisoes, dependencias, metricas, exportacao e hashes.

O primeiro conjunto aprovado e `fase2_v1`. Seus quadros sao separados por ambiente:

- treino: laboratorio, debaixo da mesa, meio da escola e portao da quadra;
- validacao: mesa com sol;
- teste intocado: janela do laboratorio.

O teste nao pode ser usado para escolher limiares, arquitetura, pesos ou aumentos de dados.

## Fase 3

O pacote inicial local e `artefatos/fase3_dataset_inicial.zip` e possui 1.491 pares
supervisionados. Ele e ignorado pelo Git; seu hash versionado esta em
`dados/manifestos/fase3_dataset_inicial.json`.

O notebook do Colab esta em `treinamento/fase_3/treinar_no_colab.ipynb`. Ele compara LinhaNet
e LR-ASPP sem tocar no teste fechado. Resultados completos tambem permanecem fora do Git ate
serem auditados e aprovados.
