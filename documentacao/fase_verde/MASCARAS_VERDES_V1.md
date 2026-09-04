# Máscaras verdes V1

Atualizado em 4 de setembro de 2026.

## Resultado atual

A Fase Verde 2 produziu máscaras candidatas em resolução original `640 x 480` para os 2.356
quadros de treino e validação. O conjunto de teste não foi aberto. Depois da correção dos erros
sistemáticos e da auditoria visual em alta resolução, 2.085 rótulos seguros foram liberados para
o primeiro treinamento; 271 casos prioritários continuam isolados para active learning.

| Grupo | Quantidade |
|---|---:|
| treino | 1.458 |
| validação | 898 |
| negativas, vazias por contrato | 324 |
| candidatas positivas normais | 1.689 |
| candidatas prioritárias | 343 |
| representantes auditados na fila essencial | 80 |
| representantes aprovados visualmente | 72 |
| representantes rejeitados para reprocessamento | 8 |
| rótulos seguros para o treino inicial | 2.085 |
| casos mantidos fora do treino | 271 |

O manifesto local está em `dados/rotulados/verde_v1_candidatas/manifesto.json`. A pasta é
ignorada pelo Git por conter dados derivados. Os elementos reprodutíveis foram congelados por
SHA-256:

- configuração: `25b2d8575618cf3d896ed9d063819d63e5983d07f9ff8428dc60a6c07cb3071c`;
- implementação: `2eceef91d6aef7f796e510071b986237552576a7be901f7bf3f3d64f4be8f2eb`;
- índice curado: `7bc650d8075a039eb7e48a0f3c31304df0f1a472c4eacb93a876365aaf3ea377`;
- candidatas: `6ef2358b84672b4bbc6ed9cab9f80c6ac5d0948f46bbc57db3ed5f08e4a46f48`;
- revisões: `051636720e28590967166a0e5f223ee9ff1a0a23459907af70922fad2b20238e`;
- anotações consolidadas: `0bb43192778c0104ceb75e310db3c9937022578026d43d1df0efc596000dcdd0`.

## Como a máscara é construída

O bootstrap combina HSV, excesso de verde e diferença verde-vermelho. A abertura morfológica
remove trilhas finas e reflexos pequenos. Componentes são pontuados por área, retangularidade,
luminância, proporção próxima de quadrado, saturação e contato com a borda. A silhueta convexa
fecha buracos internos causados por brilho, e a ordenação penaliza reflexos inferiores escuros.
A quantidade selecionada vem do contrato da captura: um marcador simples, dois no retorno e um
componente adicional na cruz mista.

A máscara não usa a categoria `antes` ou `depois` para escolher a região. Isso é deliberado. O
detector visual primeiro segmenta o marcador; o papel antes/depois, esquerda/direita e a decisão
de movimento serão calculados pela geometria conjunta da linha e das instâncias verdes.

`Sem verde / negativo` sempre gera máscara vazia por contrato, ainda que a imagem contenha linha
preta, piso, roupa, grama, reflexo ou outro objeto verde que não seja marcador oficial.

## Auditoria e fila essencial

Os 343 casos prioritários contêm marcador parcial, forma irregular, área fora da faixa,
componente extra ambíguo ou baixa confiança. A fila essencial escolheu o quadro de menor confiança
de cada sequência temporal, totalizando 80 representantes.

A auditoria conferiu os 80 representantes em folhas de alta resolução. Foram aprovados 72 e
rejeitados oito casos com marcador muito escuro, oclusão severa, reflexo ou falso positivo no
piso. Aprovar um representante não aprovou automaticamente seus vizinhos: os 271 casos
prioritários sem aprovação explícita permaneceram fora do primeiro treinamento.

O algoritmo foi corrigido e as 2.356 candidatas foram regeneradas. Uma segunda geração produziu
os mesmos 2.356 PNGs e o mesmo `candidatas.jsonl`, com zero divergência de conteúdo.

## Painel de revisão

```powershell
uv run obr-revisar-mascaras-verdes --host 127.0.0.1 --porta 8094
```

O amarelo mostra a máscara candidata. O painel oferece três decisões: aprovar, marcar máscara
vazia ou reprocessar. Ele não treina, não abre o teste e não controla motores.

## Consolidação conservadora

```powershell
uv run obr-consolidar-rotulos-verdes
```

A saída local fica em `dados/rotulados/verde_v1_rotulos_iniciais`. A consolidação verifica o hash
de todas as máscaras antes de copiar qualquer rótulo. Entram as 1.689 candidatas normais da regra
calibrada, as 324 negativas vazias por contrato e as 72 aprovações visuais. Uma candidata
prioritária pendente ou marcada para reprocessamento nunca é promovida implicitamente.

## Gate para seguir ao treinamento

- [x] bruto e índice curado preservados por hash;
- [x] teste não lido pela geração, painel ou consolidação;
- [x] candidatas determinísticas separadas de métricas de tempo;
- [x] negativos estritamente vazios;
- [x] fila essencial revisada;
- [x] erros sistemáticos corrigidos e candidatas regeneradas;
- [x] reprodução independente com 2.356 máscaras idênticas;
- [x] conjunto consolidado e manifesto marcado como pronto para treino inicial;
- [ ] detector neural treinado e validado sem abrir o teste.
