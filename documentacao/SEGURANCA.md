# Seguranca

## Estado seguro padrao

- `atuadores_habilitados = false`.
- `modo_simulacao = true`.
- O painel nao aceita comandos por padrao.
- Inicializacao automatica no Raspberry Pi permanece desabilitada.
- Perda de telemetria, excecao ou estimativa vencida deve resultar em parada segura.

## Separacao das validacoes

Os relatorios sempre distinguirao:

1. testes automatizados;
2. reproducao de video e simulacao;
3. execucao no Raspberry Pi sem atuadores;
4. teste eletrico com rodas suspensas;
5. movimento fisico controlado no chao.

Uma etapa nao prova a etapa seguinte.

## Condicoes antes do primeiro PWM real

Antes de qualquer ativacao fisica futura sera necessario:

- confirmar novamente o mapeamento de canais e o neutro;
- robot apoiado de modo que nenhuma roda toque o chao;
- area livre e mecanismo de resgate imobilizado;
- fonte dos motores correta e corte de energia acessivel;
- parada de emergencia testada;
- limites conservadores de potencia e tempo;
- confirmacao nova e explicita: `CONFIRMO RODAS SUSPENSAS`.

Nenhuma autorizacao dada para criar codigo ou executar simulacoes substitui essa confirmacao.
