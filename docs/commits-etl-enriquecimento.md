# Commits do enriquecimento do ETL

Comandos para executar após revisar o diff. Nenhum commit foi criado pelo agente.
A branch já existe em um worktree separado e inclui os commits de planejamento
publicados anteriormente. Os comandos usam caminhos explícitos para excluir
bancos, caches, ambientes virtuais e outros artefatos locais.

Execute os blocos na ordem, no mesmo terminal. A primeira verificação exige
a branch correta e nenhum arquivo previamente preparado no índice.

```bash
set -e
cd /home/guilherme/Documentos/unicamp/mc857/mc857-etl-enriquecimento
test "$(git branch --show-current)" = '24-enriquecimento-etl'
git diff --cached --quiet

git add src/f1_simulator/adapters/persistence/sqlite_race_data_repository.py
git diff --cached --check
git commit -m "fix(etl): corrija a consulta de pilotos no repository"
```

O segundo commit inclui o esquema de sessões porque o repository genérico
já reconhece ambos os contratos. A aquisição FastF1 entra no terceiro.

```bash
git add \
  scripts/ingest_trotman.py \
  src/f1_simulator/domain/history.py \
  src/f1_simulator/domain/session_data.py \
  src/f1_simulator/factories/history_factory.py \
  src/f1_simulator/application/history_etl.py \
  src/f1_simulator/application/ports/history.py \
  src/f1_simulator/adapters/datasets/trotman_history.py \
  src/f1_simulator/adapters/persistence/sqlite_history.py \
  tests/history_support.py \
  tests/test_history_etl.py \
  tests/fixtures/trotman_v128_history/
git diff --cached --check
git commit -m "feat(etl): importe o historico completo do Trotman"

git add \
  requirements-etl.txt \
  scripts/ingest_fastf1.py \
  src/f1_simulator/adapters/datasets/fastf1_sessions.py \
  tests/test_fastf1_etl.py
git diff --cached --check
git commit -m "feat(etl): enriqueça sessoes com dados do FastF1"

git add \
  AGENTS.md CONTRIBUTING.md 'Desenvolvimento de Simulador F1.md' README.MD \
  docs/adr/README.md \
  docs/adr/0002-arquitetura-hexagonal-e-integracao-de-dados.md \
  docs/adr/0003-geometria-mockada-derivada-do-fastf1.md \
  docs/adr/0004-backend-fastapi-e-contratos-python.md \
  docs/adr/0005-historico-completo-e-enriquecimento-fastf1.md \
  docs/fluxo-etl.md docs/etl-enriquecimento.md \
  docs/planejamento-modelagem.md docs/perfilamento-pilotos.md \
  docs/progresso.md docs/commits-etl-enriquecimento.md
git diff --cached --check
git commit -m "docs(etl): documente contratos fontes e validacao"
```

O espelho do backlog é gerado. Se a sincronização produzir alterações,
registre-as separadamente:

```bash
python3 -B scripts/sync_github_backlog.py
if ! git diff --quiet -- docs/backlog.md; then
  git add docs/backlog.md
  git commit -m "docs(backlog): atualize o espelho das issues"
fi
```

Para publicar os commits quando estiver pronto:

```bash
git push -u origin 24-enriquecimento-etl
```
