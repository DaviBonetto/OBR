# Progresso da Fase 4

Atualizado em 22 de agosto de 2026.

## Entrega inicial

O candidato LR-ASPP V2 agora executa em um pipeline completo, ainda sem atuadores:

```text
ultimo quadro da camera
  -> recorte e normalizacao identicos ao treino
  -> ONNX Runtime
  -> mascara com limiar 0,80
  -> linha central e diagnosticos
  -> confirmacao e suavizacao temporal
  -> EstimativaLinha imutavel
  -> dashboard somente leitura
```

Foram implementados:

- verificacao obrigatoria do SHA-256 do ONNX antes da inferencia;
- consumo exclusivo do ultimo quadro, sem fila crescente;
- linha central, ponto atual, ponto objetivo, erro lateral e angular;
- classificacao de reta e curvas suaves/fechadas para esquerda/direita;
- intersecao T com objetivo frontal e tipo de curva `reta`;
- confirmacao de uma rota nova em dois quadros coerentes;
- memoria de GAP limitada a 120 ms, marcada como evidencia temporal;
- suavizacao temporal sem alterar a mascara da IA;
- sobreposicao visual e dashboard preto, sem endpoints de comando;
- telemetria de camera, confianca, fonte, diagnostico e latencia.

## Medicao na validacao

A avaliacao percorreu as 426 imagens de validacao do dataset V2, sem abrir o teste:

- 380 de 380 quadros positivos localizaram a linha;
- 55 de 55 intersecoes foram classificadas com trajetoria reta;
- 1 de 46 negativos gerou caminho de alta confianca por quadro isolado;
- 0 de 46 negativos permaneceu de alta confianca depois da confirmacao temporal;
- ultima execucao completa no PC: mediana `19,13 ms`, P95 `31,04 ms`;
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

## Proximos gates

1. criar e revisar a referencia humana de linha central;
2. medir erro mediano e P95 do centro contra essa referencia;
3. executar o dashboard com a camera provisoria no Raspberry Pi 5;
4. medir FP32 no Raspberry e comparar INT8 somente se necessario;
5. repetir calibracao geometrica com a camera oficial, sem retreinar automaticamente;
6. congelar todo o pipeline antes de abrir o teste final uma unica vez.

Nenhum motor, servo ou mecanismo de resgate foi acionado.
