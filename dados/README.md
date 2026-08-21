# Dados

Os dados serao organizados por sessao, tarefa e versao. Videos brutos e rotulos completos
nao serao enviados ao Git comum. Manifestos, divisoes e hashes garantirao rastreabilidade.

A captura bruta da Fase 2 possui 29 sessoes e 3.583 imagens. A preparacao gera indices em
`dados/processados/`, sem copiar ou alterar os PNGs, e a futura anotacao fica em
`dados/rotulados/`. O resumo versionado de cada conjunto fica em `dados/manifestos/`.
