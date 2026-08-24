# Estado do projeto

Atualizado em: 24 de agosto de 2026.

## Fase atual

**Fase Verde 0 concluida; proxima etapa: painel e protocolo de captura do verde.**

## Entregas da Fase 0

- [x] definir o repositorio independente `OBR-Oficial`;
- [x] registrar arquitetura e fronteiras dos modulos;
- [x] criar configuracoes iniciais com atuadores desabilitados;
- [x] criar o contrato inicial da estimativa de linha;
- [x] documentar criterios de aceite e seguranca;
- [x] executar qualidade e testes automatizados;
- [x] criar o primeiro commit;
- [x] publicar e verificar `DaviBonetto/OBR`;
- [x] validar qualidade e testes tambem no GitHub Actions.

## Ainda nao implementado

- controle de motores e servos;
- maquina de estados;
- estrategia ou mecanismo de resgate.

## Entregas da Fase 1

- [x] contrato que permite trocar a camera sem alterar consumidores;
- [x] fonte de camera USB com buffer do ultimo quadro;
- [x] camera sintetica para testes sem hardware;
- [x] fotos PNG com hash, manifesto e contexto;
- [x] painel web para foto unica e sequencia automatica;
- [x] executar qualidade e testes automatizados;
- [x] identificar e caracterizar a camera provisoria no Raspberry Pi 5;
- [x] instalar o painel de captura no Raspberry Pi;
- [x] abrir o painel real no computador;
- [x] capturar e verificar sessoes fisicas;
- [x] publicar e validar o codigo da Fase 1 no GitHub.

O ultimo endereco validado do painel foi `10.0.0.61:8080`, sujeito a mudanca pela rede. A
camera provisoria opera em `/dev/video0`, 640 x 480 e aproximadamente 10 FPS.

## Entregas da Fase 2

- [x] copiar as 29 sessoes fisicas para backup local ignorado pelo Git;
- [x] validar 3.583 PNGs, manifestos, resolucoes e hashes;
- [x] implementar curadoria deterministica sem alterar originais;
- [x] filtrar exposicao extrema e quase duplicatas apenas nos indices;
- [x] separar treino, validacao e teste por ambiente completo;
- [x] registrar `intersecao` com trajetoria desejada `reto`;
- [x] definir contrato inicial de mascara, linha central e ponto objetivo;
- [x] congelar o indice `fase2_v1` com 2.204 amostras;
- [x] reproduzir os mesmos fingerprints no Windows e no Raspberry Pi;
- [x] implementar e calibrar o detector classico inicial;
- [x] gerar mascaras iniciais somente para treino e validacao;
- [x] criar painel auditavel de revisao das mascaras;
- [ ] revisar e corrigir as anotacoes;
- [ ] implementar o detector classico de referencia;
- [ ] medir o detector no conjunto de teste intocado.

## Entregas iniciais da Fase 3

- [x] consolidar 1.491 rotulos supervisionados;
- [x] separar 122 linhas dificeis para active learning;
- [x] exportar pacote deterministico para CPU/Colab;
- [x] implementar loader, aumentos, perdas e metricas;
- [x] implementar LinhaNet e LR-ASPP MobileNetV3;
- [x] validar forward e uma etapa de otimizacao na CPU;
- [x] treinar as duas arquiteturas na T4;
- [x] corrigir a fila de active learning;
- [x] auditar o pacote V2 e todos os hashes internos;
- [x] calibrar o limiar somente na validacao;
- [x] congelar e exportar o candidato aprovado para ONNX;
- [x] verificar paridade numerica PyTorch/ONNX;
- [ ] medir FP32 e, se vantajoso, INT8 no Raspberry Pi 5;
- [ ] validar a camera provisoria e a camera oficial;
- [ ] abrir o teste congelado uma unica vez depois de congelar todo o pipeline;

## Entregas iniciais da Fase 4

- [x] executar o ONNX com pre-processamento identico ao treinamento;
- [x] verificar o hash do modelo antes da inferencia;
- [x] extrair linha central, ponto atual, ponto objetivo e erros;
- [x] manter intersecao T com trajetoria reta;
- [x] implementar confirmacao, suavizacao e GAP temporal limitado;
- [x] consumir somente o ultimo quadro da camera;
- [x] criar dashboard preto e somente leitura;
- [x] zerar falsos caminhos de alta confianca na validacao depois da confirmacao temporal;
- [x] criar selecao estratificada e painel independente para a referencia humana;
- [x] implementar erro simetrico contra polilinha humana e gates mediano/P95;
- [x] finalizar mascara visual antialias, trajetoria curta e marcadores atual/objetivo;
- [x] completar a mascara no quadro inteiro com duas janelas sobrepostas e histerese conectada;
- [x] remover fechamentos artificiais do contorno nas bordas do quadro;
- [x] separar T de curvas de 90 graus, com 55/55 T e zero falso T nos outros 371 quadros;
- [x] redesenhar rota visual conectada e marcadores compactos, sem alterar o futuro controle;
- [x] estabilizar jitter pequeno sem atrasar mudancas grandes de direcao;
- [ ] concluir uma referencia humana independente de linha central, se retomada;
- [ ] validar com camera real no Raspberry Pi 5;
- [ ] medir latencia e estabilidade por 30 minutos no Raspberry Pi 5;

Nenhum motor sera usado nesta fase.

## Entregas da Fase Verde 0

- [x] congelar por hash o modelo, a configuracao e a implementacao aprovada da linha;
- [x] definir ausencia de verde como decisao neutra, sem interromper a linha;
- [x] compor linha e verde no mesmo quadro por `EstimativaPista`;
- [x] definir contratos imutaveis para marcador, estado e decisao verde;
- [x] classificar antes/depois e esquerda/direita pelo sentido de chegada;
- [x] ignorar marcadores depois inclusive em cruzes mistas;
- [x] exigir dois marcadores antes, em lados opostos, para retorno de 180 graus;
- [x] versionar configuracao inicial e gates temporais;
- [x] cobrir as regras com testes unitarios sem abrir o teste final;
- [ ] criar o painel e o protocolo de captura da Fase Verde 1;
- [ ] capturar, rotular, treinar e validar o detector visual do verde;
- [ ] integrar o detector visual e medir a percepcao completa no Raspberry Pi 5.

O detalhamento esta em `documentacao/fase_verde/PROGRESSO.md`. Os testes da Fase Verde 0 usam
geometria sintetica; ainda nao provam deteccao por camera, iluminacao ou latencia fisica.
