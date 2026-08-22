# Progresso da Fase 4

Atualizado em 22 de agosto de 2026.

## Entrega inicial

O candidato LR-ASPP V2 agora executa em um pipeline completo, ainda sem atuadores:

```text
ultimo quadro da camera
  -> duas janelas sobrepostas, com a mesma escala fisica do treino
  -> ONNX Runtime sequencial: janela superior + janela inferior
  -> mascara inferior 0,80 para controle
  -> mascara full-frame 0,55 conectada a semente inferior 0,80
  -> linha central inferior + topologia full-frame
  -> confirmacao e suavizacao temporal
  -> EstimativaLinha imutavel
  -> dashboard somente leitura
```

Foram implementados:

- verificacao obrigatoria do SHA-256 do ONNX antes da inferencia;
- consumo exclusivo do ultimo quadro, sem fila crescente;
- linha central, ponto atual, ponto objetivo, erro lateral e angular;
- classificacao de reta e curvas suaves/fechadas para esquerda/direita;
- intersecao T confirmada somente quando ha ramo e continuacao frontal;
- curvas de 90 graus sem continuacao frontal preservadas como curvas fechadas;
- confirmacao de uma rota nova em dois quadros coerentes;
- memoria de GAP limitada a 120 ms, marcada como evidencia temporal;
- suavizacao temporal sem alterar a mascara da IA;
- sobreposicao visual e dashboard preto, sem endpoints de comando;
- telemetria de camera, confianca, fonte, diagnostico e latencia.

## Medicao na validacao

A avaliacao percorreu as 426 imagens de validacao do dataset V2, sem abrir o teste:

- 380 de 380 quadros positivos localizaram a linha;
- 55 de 55 intersecoes foram detectadas e classificadas com trajetoria reta;
- 0 de 202 curvas abertas, 0 de 57 curvas fechadas, 0 de 66 retas e 0 de 46
  negativos foram confundidos com T;
- 1 de 46 negativos gerou caminho de alta confianca por quadro isolado;
- 0 de 46 negativos permaneceu de alta confianca depois da confirmacao temporal;
- ultima execucao completa com duas inferencias no PC: mediana `59,27 ms`, P95
  `330,50 ms`;
- execucao ao vivo simulada: nenhuma falha observada e cerca de 10 FPS, limitada pela camera
  simulada configurada em 10 FPS.

Esses tempos pertencem ao computador Windows e nao comprovam o desempenho do Raspberry Pi 5.

## Limite de avaliacao encontrado

O dataset possui mascaras por pixel revisadas por humano, mas nao possui uma linha central humana.
Derivar uma segunda linha central da propria mascara e compara-la com o detector produz uma
divergencia util para diagnostico, principalmente em curvas de 90 graus, mas nao e uma verdade
independente e nao pode aprovar o gate de erro de centro.

O experimento com caminho geodesico/esqueleto foi testado e removido: aumentou latencia e piorou
as divergencias. O codigo publicado contem somente o extrator leve aprovado nesta etapa.

Antes de declarar o centro perfeito, criaremos um pequeno conjunto de referencia com pontos
centrais humanos em retas, curvas abertas, curvas fechadas e T. O teste final continua fechado.

## Gate humano implementado

O painel `obr-referenciar-centro-fase4` seleciona deterministicamente 48 quadros reais de
validacao: 12 retas, 12 curvas abertas, 12 curvas fechadas e 12 intersecoes T. O humano desenha a
polilinha do centro desde o robo ate o destino. A previsao da IA permanece escondida por padrao e
nenhum ponto e derivado da mascara.

A avaliacao mede distancia simetrica entre a trajetoria prevista e a polilinha humana em
`320 x 192`, por tipo e no total. O gate exige mediana de no maximo 3 pixels e P95 de no maximo
8 pixels. Ele so pode ser aprovado depois das 48 anotacoes. O teste fechado e recusado em todas
as etapas.

O usuario encerrou a anotacao manual depois de cinco tentativas. Esses pontos alternavam entre a
base e o topo da imagem e, por isso, foram preservados apenas no historico local e excluidos da
avaliacao. Nenhuma referencia gerada pela propria IA foi registrada como humana. Assim, o gate de
3/8 pixels permanece **nao medido**, e nao foi usado para alegar perfeicao.

## Mascara full-frame e acabamento final local

A rede foi mantida na escala em que foi treinada. Em vez de esticar a ROI ou executar o modelo
fora da distribuicao conhecida, o quadro e lido em duas janelas de 70% da altura, sobrepostas
entre 30% e 70%. O passe inferior continua sendo a fonte da linha central e do futuro controle.
O passe superior completa somente a mascara do quadro e fornece contexto para confirmar a
topologia do T.

A fusao usa histerese conectada: `0,80` forma a semente forte no passe inferior e `0,55` recupera
a borda completa apenas no componente ligado a essa semente. Manchas superiores desconectadas
sao descartadas. A camada visual agora:

- nenhum preenchimento ou transparencia sobre a linha e a imagem da camera;
- contorno azul-violeta no horizonte e ciano perto do robo, cobrindo o quadro inteiro;
- nenhum `blur`, fechamento morfologico ou simplificacao poligonal no desenho;
- componentes que saem do quadro permanecem abertos, sem as tampas horizontais artificiais no
  topo, na antiga fronteira da ROI ou no rodape;
- horizontais internas verdadeiras, incluindo o ramo de uma intersecao T, permanecem visiveis;
- trajeto vermelho limitado ao trecho entre posicao atual e ponto objetivo;
- marcadores ciano e azul-escuro com centro branco, anel e halo;
- suavizacao temporal adaptativa: forte contra jitter pequeno e responsiva a curvas grandes.

Antes da nova topologia, 91 de 371 quadros que nao eram T recebiam o diagnostico de intersecao.
Depois da mudanca, a avaliacao das 426 imagens ficou com 100% dos 380 positivos localizados,
55 de 55 T detectados, zero falso T nas outras quatro classes e zero falso caminho de alta
confianca depois da confirmacao temporal. O teste final permaneceu fechado.

Essa validacao usa capturas reais ja registradas, mas a parte superior nao possui rotulos humanos
full-frame independentes. A cobertura visual superior e a latencia ainda precisam ser confirmadas
ao vivo com a camera provisoria no Raspberry Pi 5 e, depois, repetidas com a camera oficial.

## Proximos gates

1. executar o dashboard com a camera provisoria no Raspberry Pi 5;
2. testar iluminacao, sombra, Sol, reta, curva aberta, curva de 90 graus, T e negativos;
3. registrar os casos que falharem e separar erro de segmentacao de erro geometrico;
4. medir estabilidade e latencia FP32 por 30 minutos, comparando INT8 somente se necessario;
5. repetir a calibracao com a camera oficial, sem retreinar automaticamente;
6. retomar o gate humano se necessario e congelar tudo antes de abrir o teste final uma vez.

Nenhum motor, servo ou mecanismo de resgate foi acionado.
