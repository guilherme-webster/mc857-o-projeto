"""Camada de servicos do backend: orquestra ETL, simulacao e geometria.

Cada modulo agrupa uma responsabilidade unica entre os routers (HTTP) e o nucleo
(src/f1_simulator). E aqui que o backend abre SQLite, roda o ETL e grava
arquivos, mantendo o nucleo independente de HTTP e persistencia.
"""
