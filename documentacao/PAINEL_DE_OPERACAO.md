# Painel de operação

Dashboard web de observação e ajuste fino do robô. Roda no Raspberry Pi (ou no PC,
em simulação) e abre em qualquer navegador do computador.

## Como abrir

```bash
uv run obr-painel                 # câmera real do perfil camera_usb.toml
uv run obr-painel --simulacao     # pista sintética, sem hardware
```

O endereço aparece no terminal (`http://IP_DO_ROBO:8090`). Para fechar: `Ctrl+C`.

## O que ele faz

- **Vídeo ao vivo duplo**: janela processada (com overlay da IA, quando o modelo
  `modelos/linha/lraspp_v2/modelo.onnx` existe) + janela da câmera crua, ambas MJPEG,
  sempre o quadro mais recente (nunca fila). Sem modelo, a janela processada mostra
  placeholder e o painel segue funcionando.
- **Topo**: logo da equipe, bola de estado do sistema (verde/amarelo/vermelho), FPS,
  idade do quadro e latência, cronômetro de tentativa (clique inicia/pausa, duplo
  clique zera) e botão que recolhe as duas barras laterais.
- **O que está acontecendo**: frase grande centralizada sob os vídeos
  (Seguindo linha, curvas, verde 180°, interseção, gap, resgate, procurando,
  sem linha ou em espera) com bolinha colorida e confiança abaixo. Cada evento
  possui cor funcional própria.
- **Barra esquerda**: tempos de virada verde, estado seguro dos atuadores,
  disponibilidade de bateria, câmera/percepção e informações do sistema. Exibe
  também os slots CAM/DISP 0 e CAM/DISP 1: o primeiro reflete a fonte ativa;
  o segundo permanece não configurado até existir uma segunda fonte. A saúde do
  Raspberry Pi mostra subtensão, tensão de núcleo, temperatura da CPU e RAM livre
  quando essas leituras locais estão disponíveis; isto não substitui um sensor da
  tensão de entrada de 5 V. Bateria fica como “sem leitura” enquanto não houver
  sensor integrado. O botão
  de cópia disponibiliza o comando de simulação sem exibi-lo na interface.
- **Registro de operação**: terminal visual sob os controles manuais, que
  apresenta eventos reais do painel: conexão, mudanças de estado, ajustes,
  capturas e interações de exibição.
- **Viradas** (barras laterais): tempos de manobra editáveis por steppers
  (segure para acelerar) ou digitação, com debounce, confirmação por eco canônico e
  persistência atômica em `configuracoes/viradas.toml`. Grupos: 90° esquerda,
  90° direita, verde 180° e gap (avanço + confirmação). Valores vazios = indefinidos.
- **Captura de imagens**: foto única (PNG), gravação de vídeo (mp4, com fallback
  avi) e sequência de frames com intervalo e quantidade configuráveis. Arquivos em
  `capturas_operacao/AAAA-MM-DD/` (fora do Git). Sempre o quadro bruto, sem overlay.
- **Métricas honestas**: nada de telemetria sintética.

## Segurança

O painel é **somente observador e configurador**: não existe botão de motor e
nenhum comando toca hardware. `atuadores_habilitados` permanece `false`. Os
tempos gravados serão consumidos apenas pelo futuro módulo `controle`.

## Arquitetura

```text
codigo/obr_oficial/painel/operacao/
├── servidor.py      fábrica Flask + CLI (entry point obr-painel)
├── estado.py        retrato thread-safe: câmera + percepção + captura + sistema
├── viradas.py       contrato único de chaves/limites/passos (inclui gap)
├── persistencia.py  TOML atômico (tmp + rename)
├── captura.py       foto, vídeo e sequência de frames (threads próprias)
└── web/             index.html + painel.css + painel.js + logo + fontes/
```

Decisões herdadas da auditoria do dashboard antigo (FusionZero): um único stream
JPEG por vez, SSE em vez de protocolo TCP próprio, debounce de 150 ms nos ajustes,
limites definidos uma única vez no backend (`viradas.py`) e renderização só quando
chega quadro novo.
