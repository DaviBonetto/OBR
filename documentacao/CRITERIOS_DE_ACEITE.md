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

Os gates de erro de centro exigem pontos centrais anotados por humano. Mascaras por pixel, por si
so, nao autorizam derivar uma referencia heuristica e apresenta-la como verdade independente.

## Raspberry Pi 5

- inferencia P95: no maximo 20 ms;
- camera ate estimativa P95: no maximo 40 ms;
- pelo menos 25 quadros por segundo sustentados;
- nenhuma fila crescente de quadros;
- 30 minutos sem travamento, vazamento progressivo ou reducao termica grave.

## Marcadores verdes

- 100% das decisoes corretas no conjunto de teste verde congelado;
- 100% de acerto entre marcadores antes e depois no teste congelado;
- 100% dos casos com dois marcadores antes, um de cada lado, classificados como retorno;
- nenhum comando verde falso em 30 minutos de negativos reais;
- precisao por instancia de pelo menos 99,8% e recall de pelo menos 99,5%;
- confirmacao de uma decisao coerente em ate tres quadros;
- verde ausente, ambiguo ou somente depois sempre produz decisao neutra;
- linha e verde sao medidos simultaneamente, sem fila crescente e dentro do gate total do Pi.

Uma mascara verde vazia nao significa linha ausente. O gate do verde mede sua propria evidencia,
enquanto o gate da linha continua sendo avaliado no mesmo quadro.

## Controle e resgate

Os criterios quantitativos dessas areas serao definidos antes das respectivas implementacoes,
quando hardware, dimensoes e mecanismo final estiverem confirmados.
