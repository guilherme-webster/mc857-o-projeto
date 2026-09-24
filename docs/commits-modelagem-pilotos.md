# Comandos dos commits de modelagem

Executar após revisar o diff, no mesmo terminal. Nenhum commit foi criado pelo
agente. A alteração existente em `.gitignore` ignora `Pipfile.lock`; ela foi
preservada e agrupada com a dependência Matplotlib. Bancos, JSON e gráficos
locais não entram nos commits.

```bash
set -e
cd /home/guilherme/Documentos/unicamp/mc857/mc857-etl-enriquecimento
test "$(git branch --show-current)" = '40-modelagem-dos-dados'
git diff --cached --quiet

git add Pipfile .gitignore
git diff --cached --check
git commit -m "chore(deps): configure Matplotlib no ambiente Pipenv"

git add \
  src/f1_simulator/domain/driver_profile.py \
  src/f1_simulator/application/profile_drivers.py \
  scripts/profile_drivers.py \
  tests/test_driver_profile.py \
  tests/test_profile_drivers.py
git diff --cached --check
git commit -m "feat(modelagem): estime ritmo e consistência por contexto"

git add \
  README.MD \
  docs/modelagem-pilotos-inicial.md \
  docs/perfilamento-pilotos.md \
  docs/planejamento-modelagem.md \
  docs/progresso.md \
  docs/commits-modelagem-pilotos.md
git diff --cached --check
git commit -m "docs(modelagem): registre o contrato inicial de pilotos"

git add docs/backlog.md
git diff --cached --check
git commit -m "docs(backlog): atualize o espelho das issues"
```

Publicação quando estiver pronto:

```bash
git push -u origin 40-modelagem-dos-dados
```

## Gerar os gráficos novamente

O banco SQLite é entrada; JSON e gráficos são saídas. Não remover `data/curated`
para repetir uma análise: essa pasta contém o banco. O script recusa uma pasta
de gráficos existente. O bloco abaixo cria uma nova pasta por execução e coloca
o JSON ao lado da subpasta de gráficos. Assim a pasta do redirecionamento `>`
existe antes de o shell abrir o arquivo, e a subpasta de gráficos ainda é nova.

```bash
set -e
cd /home/guilherme/Documentos/unicamp/mc857/mc857-etl-enriquecimento
pipenv install
test -f data/curated/history-fastf1-2024.sqlite
perfil_run_dir=$(mktemp -d data/curated/perfil-pilotos.XXXXXX)
pipenv run python -B scripts/profile_drivers.py \
  --database data/curated/history-fastf1-2024.sqlite \
  --sessions session:1141:R \
  --lap-window 10 --tyre-age-window 5 --weather-max-age-ms 120000 \
  --min-laps-per-context 3 --min-drivers-per-context 3 --min-events 1 \
  --plot-dir "$perfil_run_dir/graficos" \
  > "$perfil_run_dir/perfil.json"
printf 'Resultado em: %s\n' "$perfil_run_dir"
```

Se o `test -f` falhar, restaurar o banco pelo
[ETL enriquecido](etl-enriquecimento.md) antes de executar a modelagem.
