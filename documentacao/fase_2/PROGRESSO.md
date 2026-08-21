# Progresso da Fase 2

## Estado

**Etapa 1 concluida. Etapa 2 implementada e aguardando revisao humana.**

## Concluido em 21 de agosto de 2026

- backup local das 29 sessoes e 3.583 imagens;
- 3.583 hashes e decodificacoes validados;
- `obr-preparar-dataset` implementado;
- 2.204 amostras selecionadas sem alterar os originais;
- treino 1.172, validacao 441 e teste 591;
- todos os cinco conteudos presentes em todas as divisoes;
- T registrado com trajetoria `reto`;
- contrato inicial de anotacao registrado;
- Windows e Raspberry Pi produziram os mesmos tres fingerprints;
- 31 testes automatizados aprovados no computador e no Raspberry Pi;
- dashboard permaneceu ativo durante a preparacao no Raspberry Pi.

## Concluido na Etapa 2

- detector classico explicavel implementado e parametrizado por TOML;
- regra geometrica `intersecao T -> seguir reto` coberta por teste;
- 1.613 mascaras candidatas geradas somente para treino e validacao;
- conjunto de 591 imagens de teste permaneceu sem leitura;
- acuracia indireta de presenca de 98,3881% na calibracao;
- latencia mediana de 9,2797 ms e p95 de 11,2772 ms na CPU do computador;
- painel local de revisao com filtros, sobreposicao e decisoes auditaveis;
- 39 testes automatizados aprovados no computador.

## Proxima etapa

Revisar as mascaras candidatas, corrigir os casos marcados e congelar os rotulos humanos.
Somente depois sera executado o benchmark unico no teste de 591 quadros.

## Bloqueios

Nenhum bloqueio de software. A camera oficial ainda nao esta disponivel e sera tratada por um
perfil e uma rodada de ajuste fino proprios.
