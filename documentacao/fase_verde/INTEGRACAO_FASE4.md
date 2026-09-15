# Integração verde e linha — Fase Verde 4

## Estado atual

O candidato ONNX verde e o detector de linha processam o mesmo quadro da câmera no dashboard de
percepção. A linha continua ativa em todos os quadros. A máscara verde aparece somente como
contorno amarelo, sem esconder a imagem nem alterar a máscara, trajetória ou pontos da linha.

O painel permanece somente leitura e publica:

- estado, decisão candidata, confiança e quantidade de marcadores verdes;
- contorno amarelo dos marcadores detectados;
- latência própria da inferência verde;
- telemetria da linha preservada.

Nenhum endpoint de motor foi adicionado. `atuadores_habilitados` continua `false`.

## Calibração inicial com capturas reais

Foi executada a inferência do ONNX verde nas 787 imagens de validação V2, sem abrir o teste. Os
cartões válidos ocuparam de aproximadamente `6%` a `26%` do quadro da câmera USB, enquanto os 142
negativos permaneceram sem componente. Por isso, o teto de área geométrica foi ajustado de `8%`
provisórios para `30%`.

Em reprodução real, um quadro com marcador antes à esquerda e marcador depois publicou
`VIRAR_ESQUERDA`, mantendo o marcador depois como `DEPOIS_IGNORADO`.

## Limite deliberado desta entrega

Uma imagem isolada antes de a cruz entrar no enquadramento não permite saber se o marcador será
antes ou depois da próxima interseção. Publicar giro nessa situação seria inseguro. Assim, fora de
uma interseção T confirmada, o sistema mostra a evidência verde e publica decisão neutra com o
motivo `marcadores_verdes_aguardando_intersecao`.

A decisão no T agora exige três leituras consecutivas iguais dentro de `120 ms`. Troca de lado,
atraso ou leitura neutra descarta a memória; portanto uma intenção jamais permanece publicada
depois do T. Essa confirmação ainda é observabilidade, não comando de motor.

O próximo gate é medir as sequências reais de aproximação e saída de cada configuração verde,
incluindo cartões fundidos ou partidos. Depois serão validados Raspberry Pi 5 e câmera oficial.
O teste final permanece fechado.

## Execução local com capturas reais

```powershell
uv sync --all-extras
uv run obr-percepcao-linha `
  --reproduzir-capturas artefatos/fase_verde_3_dataset_v2 `
  --divisao-reproducao validacao `
  --host 127.0.0.1 --porta 8082
```

Abra `http://127.0.0.1:8082`. Essa execução reproduz somente treino ou validação; a divisão de
teste não é aceita pelo leitor de capturas.
