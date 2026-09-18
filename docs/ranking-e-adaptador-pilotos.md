# Ranking de ritmo e integração Python com o núcleo

Implementação de 18/09/2026, relacionada às issues #67 e #70.

## Ranking observacional

`application.rank_drivers.rank_drivers(ProfileRun)` ordena o ritmo agregado
`pace_delta_pct` crescente: menor percentual significa ritmo mais rápido na
amostra. Preserva o estimador existente (mediana por contexto, depois por evento,
depois entre eventos); não usa MAD para desempatar nem altera a seleção de voltas.
Empates exatos compartilham posição, no padrão 1, 1, 3. IDs ordenam apenas a
apresentação de empates. Perfis indisponíveis ficam no fim, sem posição.

O ranking representa o conjunto piloto/equipe nos contextos observados. Não
identifica habilidade isolada. Os intervalos marginais por bootstrap de eventos
não testam superioridade entre posições. Cobertura, avisos, nomes e proveniência
acompanham os valores. Pilotos que mudaram de equipe mantêm no ranking o agregado
exploratório existente; o adaptador exige a equipe do contexto escolhido.

```bash
pipenv run python -B scripts/rank_drivers.py \
  --database data/curated/history-profile-development-2024.sqlite \
  --plan configs/profile-evaluation-2024-expanded.json
```

A execução lê somente `development_sessions` do plano. Publica JSON, CSV,
relatório Markdown e gráficos PNG/SVG em uma nova subpasta de
`data/curated/driver-rankings/`, sem sobrescrever resultados anteriores.
`--without-plots` dispensa Matplotlib. Artefatos permanecem fora do Git.

Na amostra de 18 eventos, 23 pilotos têm posição; Jack Doohan fica indisponível.
Os cinco primeiros são Norris (−0,6726%), Verstappen (−0,5549%), Sainz
(−0,4902%), Russell (−0,4110%) e Leclerc (−0,3769%). Esta ordem descritiva não
certifica diferenças estatísticas ou capacidade de prever outras corridas.

## Adaptador e consumidor do núcleo

Fluxo: `HistoryRepository → profile_drivers → ProfileRun →
ProfileParametersAdapter → DriverParametersProvider → simulate_profile_lap`.

A porta Python `DriverParametersProvider` pertence à aplicação. O adaptador
traduz o resultado do perfilamento para `DriverPaceParameters`, objeto imutável
do domínio. O consumidor depende somente da porta e do contrato, sem SQLite,
DataFrames, FastF1, HTTP ou interface gráfica.

A primeira implementação segue a
[referência por contexto exato](companheiros-e-referencia-deterministica.md):
referência em ms e deslocamento percentual devem vir do mesmo contexto. Não usa
a posição no ranking como coeficiente, nem aplica o ritmo anual a uma referência
arbitrária. A referência já incorpora carro, pneus e condições observadas;
não se somam novamente esses efeitos. Variabilidade fica explicitamente
`disabled`; MAD e bootstrap não viram ruído.

Exemplo executável na raiz do repositório, com `PYTHONPATH=src`:

```python
from pathlib import Path
from scripts.evaluate_profiles import load_plan
from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
from f1_simulator.adapters.profile_parameters import ProfileParametersAdapter
from f1_simulator.application.profile_drivers import profile_drivers
from f1_simulator.application.simulate_profile_lap import simulate_profile_lap
from f1_simulator.domain.driver_profile import PaceContext

plan = load_plan(Path("configs/profile-evaluation-2024-expanded.json"))
run = profile_drivers(
    SQLiteHistoryRepository(Path("data/curated/history-profile-development-2024.sqlite")),
    session_ids=plan.development_sessions,
    config=plan.config,
)
provider = ProfileParametersAdapter(run, allowed_sessions=plan.development_sessions)
context = PaceContext("session:1121:R", "race:1121", 2024, "circuit:3", "HARD", False, 11, 0)
parameters = provider.parameters("driver:846", "team:1", context)
result = simulate_profile_lap(
    provider, driver_id="driver:846", team_id="team:1", context=context
)
print(parameters)
print(result)
```

O chamador explicita as sessões permitidas; o adaptador rejeita seleção fora
delas. Não há um cadastro global de partições: cabe à composição passar o plano
correto. Os parâmetros registram seleção, hashes dos manifestos, hash do run,
versões, equipe, contexto e suporte. O run original contém os manifestos completos
e deve ser preservado para auditoria.

Ausência, equipe/contexto incompatíveis, perfil insuficiente e método desconhecido
resultam em `ValueError`, sem fallback zero. A regra do domínio calcula
`referência × (1 + offset / 100)` uma vez, com Decimal e arredondamento final
ROUND_HALF_UP para milissegundos inteiros. O resultado expõe referência, efeito,
tempo fracionário e tempo do relógio.

## Limites e continuidade

O consumidor executável cobre uma volta com contexto congelado, reconstruindo
uma mediana observada. Isso valida a integração estrutural, não uma previsão.
O demonstrador `backend/app/engine/simulation.py` ainda não consome esta porta:
substituí-lo exige definir referências ao longo da corrida, evolução dos pneus,
política para contextos ausentes e classificação/relógio completos. A interface
já permite essa composição sem inserir dependências externas no núcleo.

Continuam pendentes extrapolação para outros eventos/equipes, separação causal
piloto/carro e calibração de ruído. Nenhum dado novo foi adquirido nesta entrega.
