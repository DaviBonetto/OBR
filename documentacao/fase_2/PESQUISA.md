# Pesquisa da Fase 2

## Problema

Quadros consecutivos da camera sao correlacionados. Uma divisao aleatoria colocaria imagens
quase identicas no treino e no teste, produzindo uma metrica artificialmente alta. O dataset
tambem precisa preservar os originais e tornar toda exclusao auditavel.

## Decisao

O conjunto e dividido por ambiente completo, com listas explicitas na configuracao. A
preparacao verifica hashes e decodificacao, rejeita apenas dos indices exposicoes extremas e
quase duplicatas temporais, e grava uma decisao para cada quadro.

Divisao `fase2_v1`:

- treino: robotica, debaixo da mesa, meio da escola e portao da quadra;
- validacao: mesa com sol;
- teste intocado: janela do laboratorio.

Cada divisao precisa conter pelo menos 20 amostras distintas de cada conteudo. O teste nao
participara de escolha de limiares ou arquitetura.

## Contrato de anotacao

- mascara binaria: pixels da linha fisicamente visivel;
- linha central: pontos normalizados derivados da mascara e corrigidos por humano;
- ponto objetivo: ponto normalizado que o controle futuro perseguira;
- intersecao em T: mascara visual completa, mas trajetoria desejada obrigatoriamente `reto`;
- sem linha: mascara vazia, sem ponto objetivo e estado `sem_evidencia`;
- GAP: nao e uma classe visual desta etapa; sera recuperacao temporal na logica futura.

## Detector classico planejado

O detector de referencia usara normalizacao local de iluminacao, limiar adaptativo, morfologia,
componentes conexos e continuidade geometrica. Ele tera duas funcoes: estabelecer um baseline
mensuravel e produzir mascaras iniciais para revisao, nunca promover automaticamente seus
proprios erros a verdade de treino.

## Riscos

- a camera atual e provisoria e limitada a aproximadamente 10 FPS;
- rotulos de conteudo nao substituem mascaras por pixel;
- imagens muito correlacionadas devem permanecer fora dos indices selecionados;
- o teste precisa continuar fechado ate a implementacao estar congelada;
- a camera oficial exigira calibracao e ajuste fino separados.

## Referencias

- [OpenCV: componentes conexos](https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html)
- [PyTorch: datasets e carregamento](https://docs.pytorch.org/docs/stable/data.html)
- [scikit-learn: validacao com grupos](https://scikit-learn.org/stable/modules/cross_validation.html)
