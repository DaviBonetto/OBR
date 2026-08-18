# Criterios de aceite

Este documento registra metas. Um valor so sera marcado como atingido depois de medicao
reproduzivel no ambiente indicado.

## Percepcao da linha

- recall da linha visivel por grupo de iluminacao: pelo menos 99%;
- precisao contra falsos caminhos: pelo menos 99,5%;
- nenhum falso caminho de alta confianca em 30 minutos de cenarios negativos;
- erro mediano do centro em 320 x 192: no maximo 3 pixels;
- erro P95 do centro em 320 x 192: no maximo 8 pixels;
- estimativa sem evidencia nova mantida por no maximo 120 ms.

## Raspberry Pi 5

- inferencia P95: no maximo 20 ms;
- camera ate estimativa P95: no maximo 40 ms;
- pelo menos 25 quadros por segundo sustentados;
- nenhuma fila crescente de quadros;
- 30 minutos sem travamento, vazamento progressivo ou reducao termica grave.

## Controle e resgate

Os criterios quantitativos dessas areas serao definidos antes das respectivas implementacoes,
quando hardware, dimensoes e mecanismo final estiverem confirmados.
