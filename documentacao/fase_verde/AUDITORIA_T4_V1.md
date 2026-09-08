# Auditoria do treinamento verde na T4

Atualizado em 8 de setembro de 2026.

## Conclusao

O LR-ASPP treinado na T4 foi promovido a **candidato da Fase Verde 4**, com limiar `0,75`.
Ele passou os gates globais na validacao corrigida e foi exportado para ONNX com paridade numerica.
Ainda nao e o modelo final: faltam a geometria conjunta com a linha, a validacao ao vivo no
Raspberry Pi 5, a camera oficial e a abertura unica do teste congelado.

Nenhum motor foi acionado e a divisao de teste nao foi aberta.

## Pacote recebido

| Campo | Valor |
|---|---|
| arquivo | `OBR_VERDE_FASE3_RESULTADOS_T4.zip` |
| tamanho | 12.229.332 bytes |
| SHA-256 | `8030558bb818f184bb2d7dbaa883993abba1e09b94e171740a568258695f2c8c` |
| integridade | 16 arquivos, caminhos seguros, CRC e hashes internos aprovados |
| GPU | NVIDIA Tesla T4 |
| ambiente | Python 3.13.15, PyTorch 2.11.0+cu128, CUDA 12.8 |
| revisao treinada | `05dedb72` |

O LinhaNet completou 80 epocas e obteve Dice `0,93654`. O LR-ASPP selecionou a epoca 9 de 27 e
obteve Dice `0,93945` no pacote V1. Nenhum dos dois passou originalmente por todos os gates.

## Inconsistencia encontrada e correcao V2

A auditoria relacionou a sequencia visual, os metadados brutos e a informacao dada durante a
captura. Na sessao `20260828T164709Z_verde_sessao_02_e0a67f`, os quadros 158 a 327 possuem uma
cruz mista real, mas foram capturados com `cruz_mista=false`. A curadoria V1 ja corrigia o lote
inverso, quadros 1 a 151, e nao continha essa segunda correcao.

A sobreposicao rastreavel foi adicionada em
`dados/manifestos/curadoria_verde_v2.json`. Imagens e manifestos brutos nao foram alterados. O
dataset V2 resultante possui:

| Divisao | Amostras |
|---|---:|
| treino | 1.302 |
| validacao | 787 |
| total | 2.089 |
| active learning fora do pacote | 267 |

O treino V2 e byte a byte identico ao treino usado na T4. Por isso, repetir o treinamento nao
mudaria os pesos: o checkpoint existente foi reavaliado somente na validacao corrigida. O ZIP V2
tem SHA-256 `473ae40feb5614dd686893d584c3f47df4c570aff391759180d098162d18877a` e continua sem
a divisao de teste.

## Resultado calibrado

No LR-ASPP, `0,75` foi o unico limiar da grade avaliada que passou simultaneamente pelos quatro
gates:

| Metrica | Resultado | Gate |
|---|---:|---:|
| Dice | 0,95067 | >= 0,95 |
| IoU | 0,90598 | informativa |
| precisao | 0,97078 | >= 0,97 |
| recall | 0,93138 | >= 0,93 |
| FP significativo nos negativos | 0,00% | <= 5,00% |

Por categoria, o Dice foi `0,91679` em antes/esquerda, `0,95786` em antes/direita, `0,96437`
em retorno de 180 graus e `0,95841` em depois/ignorar. Os 142 negativos ficaram sem falsos
positivos.

## Leitura operacional por marcador

A metrica por pixel penaliza partes escuras ou cobertas do cartao que o bootstrap classico nao
rotulou, embora a rede reconheca corretamente o objeto completo. Como a decisao do robo depende
do numero e da posicao dos marcadores, foi feita tambem uma auditoria de componentes com limiar
`0,50` e area minima de `0,5%` do quadro:

- 784 de 787 quadros com contagem exata (`99,62%`);
- 196 de 196 antes/esquerda;
- 129 de 130 antes/direita;
- 139 de 140 retorno de 180 graus;
- 178 de 179 depois/ignorar;
- 142 de 142 negativos.

Os tres erros restantes sao geometricos: um fragmento espurio pequeno, dois marcadores encostados
fundidos e um marcador cortado pela linha preta em dois componentes. A Fase Verde 4 deve resolver
esses casos combinando a mascara verde com a mascara e o referencial da linha; nao ha evidencia de
que um novo treinamento seja necessario agora.

## Exportacao ONNX

O candidato esta descrito em `modelos/verde/lraspp_v1/manifesto.json`:

- checkpoint SHA-256 `c76a6cc67180cd4753d5d52b48868c7f94b62ff3513427cf5e647d8699f04ae4`;
- ONNX SHA-256 `3970535c47d9b599bdf730bd00559e4b91a6394ca66c7764c6c47017fdcbd451`;
- concordancia de mascaras PyTorch/ONNX `100%` em nove entradas;
- maior diferenca absoluta entre logits `0,00002527`;
- P95 local de inferencia `10,83 ms` em CPU Windows.

O tempo local mede apenas a inferencia ONNX e nao estima o FPS final nem substitui o benchmark no
Raspberry Pi 5.

## Proximo gate

1. integrar o ONNX verde em modo somente leitura ao mesmo quadro da linha;
2. separar e agrupar instancias usando a geometria da linha;
3. classificar antes/depois e esquerda/direita pelo sentido de chegada;
4. mostrar mascara, instancias, decisao e confianca no dashboard;
5. validar com video gravado e depois ao vivo no Raspberry Pi 5, ainda sem motores;
6. repetir com a camera oficial antes de congelar o pipeline e abrir o teste final uma unica vez.
