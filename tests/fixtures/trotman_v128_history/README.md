# Amostra completa de esquema Trotman v128

Subconjunto dos 14 CSVs de `jtrotman/formula-1-race-data`, versão 128, licença
CC0-1.0. Extraído do ZIP cujo SHA-256 é verificado por `trotman_source.py`.
Preserva todas as colunas originais, a corrida de São Paulo de 2024 (`1141`),
seus dois primeiros colocados e as entidades relacionadas. As voltas foram
limitadas às três primeiras por piloto. Os registros de sprint, classificação,
standings e resultados de construtores também foram recortados por esses IDs.

Esta amostra testa esquema, relações e persistência. Não serve para calibração
nem pretende representar todo o grid ou histórico de um piloto. Não contém
telemetria FastF1. Os testes de sessões usam exemplos sintéticos explícitos em
Python, sem acesso à rede ou atribuição de parâmetros reais aos pilotos.
