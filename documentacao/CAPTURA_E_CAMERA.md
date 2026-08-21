# Captura e cameras

## Objetivo da Fase 1

Transformar qualquer camera aprovada em uma fonte identificada, calibravel e reproduzivel de
dados. A captura nao detecta a linha e nao acessa atuadores.

## Camera provisoria e camera oficial

A camera provisoria usa o perfil `camera_usb_provisoria`. Quando a camera oficial chegar,
sera criado outro arquivo de perfil com identidade, resolucao, orientacao, exposicao e
calibracao proprias.

O perfil pode ser selecionado com `--configuracao-camera camera_oficial.toml`, sem alterar
classes da camera, captura, painel ou detector.

O detector nao dependera de indice USB, nome de dispositivo ou matriz de calibracao fixa no
codigo. Para manter robustez depois da troca:

1. capturaremos dados com ambas as cameras;
2. calibraremos distorcao e geometria separadamente;
3. incluiremos as duas origens nos conjuntos de treino e validacao;
4. manteremos sessoes inteiras separadas nos conjuntos de avaliacao;
5. repetiremos o benchmark final com a camera oficial no Raspberry Pi 5.

### Caracterizacao da camera provisoria

Medida em 21 de agosto de 2026 no Raspberry Pi 5:

- USB: `058f:3841`;
- nome: `Alcor Micro USB 2.0 PC Camera`;
- dispositivo de captura: `/dev/video0`;
- perfil adotado: MJPEG, 640 x 480, 10 FPS;
- resultado direto do V4L2: aproximadamente 10 FPS, apesar de o descritor anunciar 30 FPS.

Ela e suficiente para coletar fotos entre 1 e 4 amostras por segundo, mas nao esta aprovada
para inferencia final. A camera oficial devera sustentar a meta de pelo menos 25 FPS.

Uma troca pequena de camera nao garante automaticamente a mesma precisao. A arquitetura evita
reescrita, enquanto os testes medidos demonstrarao se a robustez foi preservada.

## Painel

O painel de captura apresenta imagem ao vivo, FPS, brilho, percentual muito escuro, percentual
estourado, nitidez e espaco livre. Ele permite:

- iniciar uma sessao com contexto;
- salvar uma foto PNG sem perdas;
- capturar uma sequencia em intervalo controlado;
- classificar o conteudo do quadro;
- finalizar a sessao e fechar o manifesto.

Atalho de captura: barra de espaco, desde que nenhum campo de texto esteja ativo.

## Execucao simulada

```powershell
uv sync --all-extras
uv run obr-capturar --simulacao --host 127.0.0.1 --porta 8080
```

## Execucao no Raspberry Pi

```bash
uv sync --locked --all-extras
uv run obr-capturar --origem /dev/video0 --host 0.0.0.0 --porta 8080
```

Depois, abrir `http://IP_DO_RASPBERRY:8080` no computador.

## Evidencias para concluir a fase

- identidade e resolucao reais da camera;
- FPS medido por pelo menos alguns minutos;
- exemplo de sessao com fotos e hashes validos;
- medicao de brilho, saturacao e nitidez;
- reproducao posterior dos arquivos;
- confirmacao de que nenhum processo de motor foi iniciado.
