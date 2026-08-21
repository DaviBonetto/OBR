# 006 — Dividir o dataset por ambiente

## Estado

Aceita em 21 de agosto de 2026.

## Decisao

Treino, validacao e teste sao definidos por ambientes completos e versionados em TOML. Nao
usaremos divisao aleatoria de quadros nem moveremos uma sessao entre conjuntos depois que uma
versao for congelada.

## Motivo

Quadros consecutivos sao quase duplicados. Uma separacao aleatoria permitiria que a mesma
cena aparecesse no treino e no teste, escondendo falhas de generalizacao.

## Consequencias

- o teste mede transferencia para um ambiente nao usado na calibracao;
- algumas classes ficam menos balanceadas, mas a medicao permanece honesta;
- novos dados entram em uma nova versao, sem reescrever `fase2_v1`;
- o teste nao pode alimentar pseudo-rotulos, ajuste de limiar ou selecao de modelo.
