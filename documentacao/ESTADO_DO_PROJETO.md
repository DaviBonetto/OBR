# Estado do projeto

Atualizado em: 21 de agosto de 2026.

## Fase atual

**Fase 3 — iniciada; primeiro treinamento neural pendente na T4.**

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

- detector por IA;
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
- [ ] treinar as duas arquiteturas na T4;
- [ ] corrigir a fila de active learning;
- [ ] congelar e exportar o modelo aprovado para ONNX;

Nenhum motor sera usado nesta fase.
