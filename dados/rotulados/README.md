# Dados rotulados

Mascaras e anotacoes corrigidas serao armazenadas por versao do dataset a partir da Fase 2.
Dados rotulados completos permanecem fora do Git comum; manifestos e divisoes serao versionados.

Cada amostra aprovada da linha recebera:

- mascara binaria da linha visivel;
- linha central em coordenadas normalizadas;
- ponto objetivo normalizado;
- revisao humana e estado da anotacao;
- trajetoria `reto` nas intersecoes em T;
- mascara vazia e estado `sem_evidencia` nos negativos.
