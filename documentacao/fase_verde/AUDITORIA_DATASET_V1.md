# Auditoria do dataset verde V1

Atualizado em 28 de agosto de 2026.

## Resultado

O conjunto bruto foi congelado, copiado do Raspberry Pi e validado sem modificar nenhuma imagem.
O índice curado `verde_v1` está **pronto para gerar e revisar máscaras verdes**, mas ainda não
está liberado para treinamento.

| Verificação | Resultado |
|---|---:|
| sessões físicas | 5 |
| PNGs brutos | 4.125 |
| hashes PNG conferidos | 4.125 |
| ausentes, ilegíveis ou com hash divergente | 0 |
| duplicatas exatas | 0 |
| quadros ambíguos excluídos | 10 |
| quase duplicatas temporais retiradas apenas do índice | 847 |
| quadros selecionados | 3.268 |

O snapshot bruto está em `OBR_BACKUP_VERDE_BRUTO_20260828T1430.tar`, fora do Git, com SHA-256:

```text
72a5bd2728742c083fb4e50e8b2dce21879942d53cc24061b1c4a3b2a0d5c249
```

## Correções confirmadas

As correções vivem em `dados/manifestos/curadoria_verde_v1.json` e são aplicadas como uma camada
sobre o registro bruto. Arquivos PNG, manifestos e JSONL originais permanecem intactos.

1. Lugar 3, quadros 1 a 151: `cruz_mista` estava ligada por engano. Há somente o marcador antes;
   o valor efetivo passou para `false`.
2. Lugar 4, quadros 1.078 a 1.085: já não existe marcador visível. Foram reclassificados de
   `depois_ignorar` para `sem_verde_negativo`.
3. Lugar 3, quadros 1.148 a 1.157: um marcador entra e sai durante uma sequência negativa, sem
   geometria confiável. Foram excluídos do índice em vez de receber um rótulo inventado.

Os quadros 152 a 157 do Lugar 3 permanecem como cruz mista: a revisão visual confirma um marcador
antes e outro depois. As demais transições de categoria, cruz mista, dois marcadores/180 graus,
marcador depois e negativos difíceis foram mantidas.

## Divisões sem vazamento

As divisões usam sessões e ambientes completos:

- treino: duas sessões do Laboratório e Lugar 2;
- validação: Lugar 3;
- teste: Lugar 4.

O teste continua fechado para decisões de treino. A redução temporal usa quadros em escala de
cinza `64 x 48`, limiar médio `2,0` e preserva o primeiro e o último quadro de cada sequência.
Todos os quadros `depois_ignorar` e `sem_verde_negativo` foram preservados por serem evidências
críticas contra decisões erradas.

## Distribuição efetiva antes da redução temporal

| Evidência | Quantidade |
|---|---:|
| antes — esquerda, simples | 816 |
| antes — esquerda, cruz mista | 343 |
| antes — direita, simples | 624 |
| antes — direita, cruz mista | 540 |
| dois antes — retorno 180 graus | 741 |
| depois — detectar e ignorar | 567 |
| sem verde / negativo | 484 |
| total efetivo | 4.115 |

## Próximo gate

A próxima etapa é gerar máscaras candidatas de **todos os pixels dos marcadores oficiais**, abrir
um painel de revisão e corrigir casos difíceis. A posição antes/depois não será aprendida como uma
classe de imagem: será calculada pela geometria conjunta da linha e das instâncias verdes.

Só depois de fechar a qualidade das máscaras será produzido o pacote T4, treinado um segmentador
leve e medidos falsos positivos em sombras, reflexos, piso, roupas, grama e objetos verdes. Linha e
verde continuarão executando no mesmo quadro, sem qualquer acionamento de motores.

## Reprodução

```powershell
uv sync --extra dados
uv run obr-curar-dataset-verde
uv run pytest -q testes/unitarios/test_auditoria_verde.py
```

Saídas locais, ignoradas pelo Git:

- `dados/processados/verde_v1/manifesto.json`;
- `dados/processados/verde_v1/auditoria.jsonl`;
- `dados/processados/verde_v1/amostras.jsonl`.
