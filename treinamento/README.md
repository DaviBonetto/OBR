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
e LR-ASPP sem tocar no teste fechado. O fluxo recebe o ZIP do dataset pelo navegador e baixa no
fim um unico `OBR_FASE3_RESULTADOS_T4.zip`, que contem checkpoints, historicos, comparacao,
ambiente e hashes. Resultados completos permanecem fora do Git ate serem auditados e aprovados.

### Auditoria humana antes do V2

O resultado T4 deve ser usado para localizar desacordos, nunca para alterar rotulos sozinho.
Depois de extrair o ZIP de resultados em `artefatos/fase3_resultados_t4`, gere uma fila somente
com mascaras vazias manuais e negativos contestados pelo modelo:

```powershell
uv run --all-extras obr-auditar-rotulos-fase3 `
  --dataset artefatos/fase3_dataset_inicial `
  --checkpoint artefatos/fase3_resultados_t4/resultados/lraspp_v1/melhor.pt

uv run --all-extras obr-revisar-mascaras `
  --brutos artefatos/fase3_dataset_inicial `
  --candidatas dados/rotulados/fase3_v1_auditoria_desacordos `
  --host 127.0.0.1 --porta 8092
```

As tres decisoes significam exatamente:

- `aprovada`: existe linha e a mascara mostrada esta correta;
- `mascara_vazia`: realmente nao existe linha;
- `reprocessar`: existe linha, mas a mascara mostrada precisa ser corrigida.

O comando recusa qualquer divisao de teste e nao sobrescreve uma fila que ja contenha decisoes.

### Dataset e treinamento V2

A auditoria V2 consolidou 54 decisoes humanas:

- 24 sombras confirmadas como hard negatives;
- 23 intersecoes T reconstruidas depois de mascaras vazias acidentais;
- 7 mascaras neurais aprovadas pelo usuario.

O pacote resultante e `artefatos/fase3_dataset_v2.zip`. Seu tamanho e hash ficam registrados em
`dados/manifestos/fase3_dataset_v2.json`. O notebook principal foi atualizado para a V2 e agora:

- aumenta a presenca de negativos nos lotes;
- adiciona uma perda de presenca que pune regioes falsas em quadros sem linha;
- mede falsos positivos significativos, ignorando apenas ruido de poucos pixels;
- escolhe o checkpoint por Dice com penalidade de falso positivo;
- exige como gate inicial Dice >= 0,95 e FPR significativo <= 0,10.

O teste fechado continua fora do pacote e da selecao do modelo. A Fase 4 comeca somente depois
que um checkpoint V2 passar pelos gates e pela auditoria visual. O benchmark no Raspberry Pi 5
pertence a Fase 5 e e obrigatorio antes de promover o candidato a modelo final.
