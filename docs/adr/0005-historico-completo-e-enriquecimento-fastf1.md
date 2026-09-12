# 0005 - Histórico completo e enriquecimento offline com FastF1

- Status: aceita
- Data: 2026-09-12
- Responsável pela autorização: Guilherme, no pedido de ampliação do ETL
- Atualiza: escopo de dados do ADR 0002 e restrição à geometria do ADR 0003

## Contexto

O ETL inicial importa oito CSVs e parte dos campos para construir uma corrida.
O perfilamento requer histórico entre eventos e contexto que esse agregado não
representa. O usuário autorizou importar os 14 CSVs do Trotman e acrescentar os
dados complementares acessíveis pelo FastF1, confirmando corrida e classificação
de 2024 como recorte de validação real. A modelagem permanece uma etapa posterior.

## Alternativas consideradas

- Ampliar apenas o agregado `RaceData`: mistura dados de calibração com os
  requisitos de uma corrida executável; descartaria eventos sem resultados e
  múltiplas inscrições históricas do mesmo piloto.
- Copiar CSVs/DataFrames para o backend sem contrato: transfere normalização,
  validação e resolução de identidades para cada consumidor.
- Adotar um contrato tabular canônico para o histórico e sessões, mantendo a
  projeção existente de corrida quando seus invariantes puderem ser atendidos.

## Decisão

Importar todas as linhas e colunas dos 14 CSVs do **Trotman v128**, preservando
seu checksum e a licença declarada CC0. A importação por corrida continua
disponível e compatível. A nova importação completa também preserva dados que
não podem ser convertidos automaticamente em participantes de uma simulação.

Usar **FastF1 3.8.3** para aquisição offline de sessões selecionadas: contexto
das voltas/pneus, clima, situação da pista e sessão, mensagens de direção de
prova, amostras de carro/posição e marcadores do circuito. Resultados e horários
de sessão ficam separados dos registros Trotman; não há sobrescrita por
precedência implícita. Bibliotecas e rede permanecem no adaptador de aquisição.

Os schemas explícitos, `HistoricalRecord` imutável e a Factory constituem o
contrato de fatos. A ingestão coordena adaptadores e writer por portas Python.
SQLite persiste tabelas, proveniência e relatório de qualidade no mesmo artefato
transacional. O repository expõe registros canônicos, sem SQL ou DataFrames no
consumidor. O novo contrato não define atributos ou regras do modelo de piloto.

As observações do FastF1 são armazenadas localmente em `data/curated/`, fora do
Git. O cache é temporário por padrão; retenção local exige `--cache-dir`.
Telemetria, caches e bancos completos não são versionados. MIT é a licença da
biblioteca, não uma licença unificada dos dados de F1, Jolpica e MultiViewer;
o manifesto registra essa distinção, URLs, versões e transformações. A decisão
de aquisição não implica autorização de redistribuição dessas fontes.

## Consequências

- O pipeline valida tipos, unidades, chaves e referências e publica o lote
  completo somente após validação. Falhas preservam a saída anterior.
- Duplicatas de observações não são resolvidas escolhendo uma linha. No v128,
  1.979 chaves de volta se repetem, com 272 conflitos de tempo/posição.
  Todas as linhas são preservadas; os conflitos aparecem no relatório.
- Nulos, feeds ausentes e feeds não solicitados são distintos. Sentinelas
  inválidas de acelerador permanecem no campo de auditoria, com percentual
  utilizável nulo. Chuva booleana não vira intensidade; não se inferem aderência
  nem política de risco de um piloto.
- Amostras temporais mantêm seus relógios originais, sem interpolação entre
  carro e posição. Marcadores são referências aproximadas de visualização.
- Horários planejados do Trotman e observados no FastF1 podem divergir;
  o relógio de pit stop da fonte não recebe um fuso presumido.
- O catálogo completo pode exceder o cenário único do MVP sem ampliar a
  interface de simulação. Parquet e outras bases continuam opções futuras;
  esta entrega usa SQLite, sem exigir um novo serviço ou stack analítica.
- O consumo posterior está documentado no
  [guia do ETL enriquecido](../etl-enriquecimento.md).
