# Máscaras verdes V1

Atualizado em 28 de agosto de 2026.

## Resultado atual

A Fase Verde 2 produziu máscaras candidatas em resolução original `640 x 480` para os 2.356
quadros de treino e validação. O conjunto de teste não foi aberto. Esta saída é uma
pré-anotação auditável e ainda não é um conjunto liberado para treinamento.

| Grupo | Quantidade |
|---|---:|
| treino | 1.458 |
| validação | 898 |
| negativas, vazias por contrato | 324 |
| candidatas positivas normais | 1.674 |
| candidatas prioritárias | 358 |
| representantes na fila essencial | 75 |

O manifesto local está em `dados/rotulados/verde_v1_candidatas/manifesto.json`. A pasta é
ignorada pelo Git por conter dados derivados. Os elementos reprodutíveis foram congelados por
SHA-256:

- configuração: `25b2d8575618cf3d896ed9d063819d63e5983d07f9ff8428dc60a6c07cb3071c`;
- implementação: `2c02dca79b6c863170741c36e855b3555f2eb7e790dccd3158b7c773d99a19d0`;
- índice curado: `7bc650d8075a039eb7e48a0f3c31304df0f1a472c4eacb93a876365aaf3ea377`;
- candidatas: `f1ff1af41e560b1581fb0964d1529b7f69bba5c3b239e624d7ce2704090508aa`.

## Como a máscara é construída

O bootstrap combina HSV, excesso de verde e diferença verde-vermelho. A abertura morfológica
remove trilhas finas e reflexos pequenos. Componentes são pontuados por área, retangularidade,
proporção próxima de quadrado, saturação e contato com a borda. A quantidade selecionada vem do
contrato da captura: um marcador simples, dois no retorno e um componente adicional na cruz
mista.

A máscara não usa a categoria `antes` ou `depois` para escolher a região. Isso é deliberado. Em
piso brilhante existe uma cópia escura do marcador por reflexão; usar a posição esperada para
forçar a seleção fez o protótipo escolher reflexos. O detector visual deve primeiro segmentar o
marcador. O papel antes/depois, esquerda/direita e a decisão de movimento serão calculados depois,
pela geometria conjunta da linha e das instâncias verdes.

`Sem verde / negativo` sempre gera máscara vazia por contrato, ainda que a imagem contenha linha
preta, piso, roupa, grama, reflexo ou outro objeto verde que não seja marcador oficial.

## Auditoria e fila essencial

Os 358 casos prioritários contêm marcador parcial, forma irregular, área fora da faixa,
componente extra ambíguo ou baixa confiança. Quadros próximos da mesma sessão normalmente são
quase a mesma situação. Para evitar revisão repetitiva, a fila essencial escolhe o quadro de
menor confiança de cada sequência temporal, totalizando 75 representantes.

Aprovar um representante não aprova automaticamente os vizinhos. A fila serve para validar a
calibração e localizar padrões de falha antes da consolidação. Se ela revelar um erro sistemático,
o algoritmo é corrigido e todas as candidatas são regeneradas. Na V1, casos prioritários não
validados podem ficar fora do primeiro treinamento e retornar por active learning.

## Painel de revisão

```powershell
uv run obr-revisar-mascaras-verdes --host 127.0.0.1 --porta 8094
```

Abra `http://127.0.0.1:8094`. O amarelo mostra a máscara candidata. A tela começa na fila
essencial e oferece três decisões:

- `A`: a máscara do marcador está correta;
- `V`: a máscara deveria estar vazia;
- `R`: existe marcador, mas a máscara precisa ser corrigida ou excluída desta versão.

O painel não treina, não abre o teste e não controla motores. A T4 só será necessária depois da
consolidação das máscaras, na comparação e no treinamento do detector neural verde.

## Gate para seguir ao treinamento

- [x] bruto e índice curado preservados por hash;
- [x] teste não lido pela geração nem pelo painel;
- [x] candidatas determinísticas separadas de métricas de tempo;
- [x] negativos estritamente vazios;
- [x] reflexos e casos difíceis destacados para auditoria;
- [x] painel de revisão somente leitura sobre imagens e máscaras;
- [ ] fila essencial revisada;
- [ ] erros sistemáticos corrigidos e candidatas regeneradas, se necessário;
- [ ] conjunto consolidado e manifesto marcado como pronto para treino inicial.
