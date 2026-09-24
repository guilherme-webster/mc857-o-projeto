# Ampliação da amostra de pilotos de 2024

> Atualização em 18/09/2026: a [reserva foi avaliada](avaliacao-reserva-pilotos-2024.md)
> com os parâmetros congelados. O texto abaixo preserva o registro anterior;
> esses eventos agora são conhecidos e não constituem uma reserva inédita.

## Protocolo registrado antes da aquisição

Registro UTC: `2026-09-13T19:58:36.381195+00:00`.
Plano: [profile-evaluation-2024-expanded.json](../configs/profile-evaluation-2024-expanded.json).
SHA-256 canônico do plano: `c28b469f24beab166b6386dced4fead51d0610864d6c23925e1f6ed8010cbb03`.

Escopo: 24 corridas (R) de 2024, por FastF1 3.8.3 e o ETL do ADR 0005,
sem telemetria de carro/posição. Não misturar classificação ao ritmo de corrida.

Reserva: etapas 3, 6, 9, 14, 18 e 23 (Austrália, Miami, Canadá, Bélgica,
Singapura e Qatar). Desenvolvimento: etapas 1, 2, 4, 5, 7, 8, 10, 11, 12,
13, 15, 16, 17, 19, 20, 21, 22 e 24. A seleção usa o calendário e distribuição
ao longo da temporada, sem consultar métricas novas. Não é separação temporal
nem amostragem aleatória estratificada por clima. Os cinco eventos anteriormente
analisados pertencem todos ao desenvolvimento; Itália e Abu Dhabi deixam de
ser reserva neste novo protocolo porque já foram inspecionados.

Antes da aquisição, os manifestos locais confirmaram apenas cinco sessões R
no banco de avaliação anterior; a outra amostra continha São Paulo R/Q.
O registro demonstra a decisão nesta sessão, não comprova desconhecimento
absoluto das corridas por todos os integrantes do grupo.

As configurações permanecem: janelas 10/5 voltas, clima até 120.000 ms,
três voltas e três pilotos por contexto, dois eventos por perfil. Este mínimo
é uma regra de disponibilidade anterior, não garantia de precisão.

Adquirir a reserva permite verificar integridade, presença de feeds e contagens,
mas não autoriza usar ritmo, MAD ou cobertura de perfilamento da reserva para
escolher filtros. Não executar `evaluate_profiles` ou `analyze_contexts` com este
plano expandido antes de congelar as decisões no desenvolvimento. Após consultar
as métricas reservadas, registrar o uso e não tratar a mesma reserva como inédita.

## Artefatos previstos

- `data/curated/history-profile-development-2024.sqlite`: os 18 eventos de
  desenvolvimento; o banco anterior de cinco eventos é preservado.
- `data/curated/history-profile-full-2024.sqlite`: os 24 eventos, inclusive a
  reserva, com manifestos do ETL. Usar somente seleção explícita de sessões.

## Aquisição concluída e verificação técnica

| Artefato | Corridas R | Observações de volta |
| --- | ---: | ---: |
| Amostra anterior preservada | 5 | 5.266 |
| Desenvolvimento expandido | 18 | 20.262 |
| Reserva (diferença entre os bancos novos) | 6 | 6.342 |
| Banco completo expandido | 24 | 26.604 |

Foram adquiridas 19 corridas novas pelo ETL existente. As contagens acima são
observações canônicas, **não voltas comparáveis ou eventos com suporte para
cada piloto**. Não calculamos métricas de perfilamento dos eventos novos.

Nos dois bancos novos, `PRAGMA integrity_check` retornou `ok` e
`foreign_key_check` não encontrou violações. As sessões coincidem exatamente
com o plano; todos os cinco manifestos anteriores e o manifesto histórico
foram preservados integralmente. Contagens de voltas no banco coincidem com
os relatórios de cada sessão.

Nas 24 sessões estão presentes os feeds de voltas, participantes, clima,
estado da sessão/pista e mensagens de direção de prova. Os campos requeridos
nos schemas de voltas/clima/estados/participantes não estão ausentes na origem.
Isso não transforma nulos ou voltas sinalizadas em observações elegíveis:
os filtros anteriores continuam necessários na próxima análise.

Carro/posição têm status `not_requested`, como planejado. `t0_date` está
registrado como `unavailable` nas 24 aquisições sem telemetria; não foi
preenchido por suposição. O perfilamento usa os relógios relativos da sessão.
O FastF1 também emitiu avisos de distância de marcadores sem telemetria e,
em algumas sessões, de divergência entre término registrado e distância de
corrida. Os avisos não foram convertidos em correções manuais de tempos.

Auditoria local: `data/curated/profile-sample-2024-acquisition-audit.json`, com
hash do plano, seleção, contagens, estados de feeds e checksums dos manifestos.
Logs: `profile-development-2024-acquisition.log` e
`profile-reserved-2024-acquisition.log`, em `data/curated/`.

Três testes protegem a separação dos eventos previamente vistos, cobertura das
24 corridas e correspondência entre hash documentado e plano executável.
Suíte completa: 147 testes, sem falhas, 13 ignorados pelas condições gráficas
existentes. Ruff, links locais e sintaxe dos comandos passaram.

## Reprodução da aquisição

Usar Python com `requirements-etl.txt` instalado (FastF1 3.8.3). O ambiente
Pipenv dos gráficos não inclui necessariamente FastF1. Nesta sessão foi usado
`/tmp/mc857-evaluation-venv/bin/python`, um ambiente de aquisição já existente;
na reprodução, substituir `python` pelo interpretador do ambiente do ETL.

Primeiro, acrescentar somente as 13 corridas novas de desenvolvimento:

```bash
python -B scripts/ingest_fastf1.py \
  --base data/curated/history-profile-evaluation-2024.sqlite \
  --season 2024 --rounds 2 4 5 7 8 10 11 13 15 17 19 20 22 \
  --sessions R --without-telemetry \
  --output data/curated/history-profile-development-2024.sqlite \
  --cache-dir data/raw/fastf1-cache
```

Depois, acrescentar as seis reservadas **em outra cópia**:

```bash
python -B scripts/ingest_fastf1.py \
  --base data/curated/history-profile-development-2024.sqlite \
  --season 2024 --rounds 3 6 9 14 18 23 \
  --sessions R --without-telemetry \
  --output data/curated/history-profile-full-2024.sqlite \
  --cache-dir data/raw/fastf1-cache
```

A CLI existente publica cada lote após validação transacional. Destino existente
é recusado: uma execução já concluída deve ser reutilizada ou a nova execução
deve usar outro nome. Não apagar o banco anterior para contornar esse aviso.
O cache permite repetir uma aquisição interrompida sem baixar novamente os
feeds já obtidos. A segunda chamada depende do sucesso da primeira.

Os fatos de Trotman v128/CC0 e suas proveniências são preservados. Cada sessão
FastF1 registra versão, aquisição, origem, transformações, checksums e qualidade
no SQLite. MIT é licença da biblioteca, não autorização unificada para
redistribuir os dados; bancos, caches e logs ficam fora do Git, como no ADR 0005.
Não alterar critérios do ETL ou perfilamento para compensar feeds ausentes.

## Uso posterior sem consultar a reserva

Para experimentar no desenvolvimento, selecionar exclusivamente
`development_sessions` do plano expandido e usar o banco de desenvolvimento.
O banco completo serve à avaliação futura após congelar parâmetros e critérios.
A CLI de avaliação existente executa ambos os grupos; portanto, **não é o comando
para explorar apenas desenvolvimento**. A chamada Python já disponível é:

```python
from pathlib import Path
from scripts.evaluate_profiles import load_plan
from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
from f1_simulator.application.profile_drivers import profile_drivers

plan = load_plan(Path("configs/profile-evaluation-2024-expanded.json"))
result = profile_drivers(
    SQLiteHistoryRepository(Path("data/curated/history-profile-development-2024.sqlite")),
    session_ids=plan.development_sessions,
    config=plan.config,
)
```

Esse exemplo é para a próxima etapa; a presente aquisição não calcula métricas
novas de desenvolvimento nem de reserva. O protocolo antigo e seus gráficos
continuam válidos como registro da exploração dos cinco eventos já conhecidos.
