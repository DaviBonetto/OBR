# Estado do projeto

Atualizado em: 21 de agosto de 2026.

## Fase atual

**Fase 1 — em execucao.**

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

- detector classico ou por IA;
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
- [ ] capturar e verificar a primeira sessao fisica;
- [x] publicar e validar o codigo da Fase 1 no GitHub.

O painel real esta ativo em `10.136.42.116:8080` com a camera provisoria USB em
`/dev/video0`, a 640 x 480 e aproximadamente 10 FPS. A imagem observada na
instalacao estava muito escura e sem nitidez; o painel agora apresenta esses
avisos explicitamente. A primeira sessao fisica somente deve ser capturada depois
de descobrir e posicionar a lente sobre uma pista iluminada.

Nenhum motor sera usado nesta fase.
