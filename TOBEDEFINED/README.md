# TOBEDEFINED

Material arquivado, sem consumidor no pacote, no backend, nos scripts ou nos
testes ativos. Nada aqui e descoberto pelo `unittest` nem importado pelo
produto. Arquivos foram movidos com `git mv`; use `git log --follow` para o
historico.

## Largada (grid_start) - arquivado em 2026-11-12, issue #152

Sem consumidor desde a remocao do motor por volta (o motor 2D larga em filas de
dois por fisica). Mantido para que a issue #108 (impacto da posicao de largada)
possa reaproveitar o material.

| Arquivo | Origem |
| --- | --- |
| `grid_start.py` | `src/f1_simulator/domain/grid_start.py` |
| `grid_start_parameters_json.py` | `src/f1_simulator/adapters/grid_start_parameters_json.py` |
| `grid-start-v1.json` | `data/parameters/grid-start-v1.json` (fator `heuristic`, 0,10; JSON nao aceita comentario, por isso a nota fica aqui) |
| `analyze_grid_start_sensitivity.py` | `scripts/` (ja arquivado antes) |
| `test_grid_start.py` | `tests/` (ja arquivado antes) |

Os imports internos ainda apontam para os caminhos antigos
(`f1_simulator.domain.grid_start` etc.); ajuste-os ao reativar.
