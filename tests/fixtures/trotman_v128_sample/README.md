# Amostra Trotman v128

Subconjunto da corrida de Sao Paulo de 2024 (`raceId=1141`) extraido de
[Formula 1 Race Data](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data),
versao 128, licenca CC0: Public Domain.

A amostra conserva os dois primeiros colocados, as tres primeiras voltas de
cada um e seus pit stops. As colunas foram limitadas ao contrato lido pelo
adaptador. Ela serve apenas para testes de integracao e nao representa a corrida
completa nem o circuito definitivo do MVP.

`track_points.csv` e uma extensao de geometria, nao uma tabela original do
Trotman. Ela e derivada de uma volta obtida temporariamente pelo FastF1, reduzida a uma
polilinha normalizada e relacionada ao `circuitId=18`. A telemetria e o cache
usados na geracao nao sao retidos. A fonte, a transformacao e o checksum do
artefato ficam registrados em
`data/sources/fastf1-track-interlagos-2024.json`, conforme o ADR 0003.
