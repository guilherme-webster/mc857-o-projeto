# Handoff — motor 2D de corrida (continue daqui)

Este documento passa o contexto do trabalho do **motor 2D** de uma sessao para
quem continuar (outra conta ou outra pessoa). Ele resume intencao, decisoes,
estado e proximos passos. Nao substitui as fontes de verdade: `AGENTS.md`, os
ADRs em `docs/adr/`, `docs/CODEBASE_MAP.md` e `docs/progresso.md`.

> **Aviso principal:** nada deste trabalho foi commitado e a suite completa do
> projeto **nao foi executada** desde o merge da branch 95. A primeira coisa a
> fazer e consolidar (ver "Proximos passos"). Trate o codigo como nao verificado.

## 1. Objetivo

Ter um motor de corrida **2D**: cada carro tem posicao x,y que evolui por passos
de tempo, e **ultrapassagem e colisao emergem da proximidade espacial** (nao de
um sorteio por volta). O usuario escolheu explicitamente o "2D pleno" — a fisica
espacial decide o resultado da corrida —, nao apenas uma visualizacao 2D sobre o
motor por volta.

## 2. Decisoes registradas (ADRs)

- **ADR 0010** (aceito) — motor fisico de velocidade por trecho: o tempo de volta
  **emerge** da velocidade derivada da curvatura quando ha geometria; cada piloto
  tem um envelope fisico derivado dos atributos. Vive em `speed_dynamics.py`.
- **ADR 0011** (aceito) — motor 2D sub-volta. Muda a resolucao do motor (de "por
  volta" para passos de tempo), traz largura/posicao lateral para a fisica e usa
  o motor de velocidade mantendo posicao no tempo. Atualiza os ADRs 0002, 0003 e
  0010. **O motor detalhado continua sendo o padrao; o 2D e opt-in.**
- O ADR 0009 e o **combustivel** (nao confundir: o ADR de velocidade foi
  renumerado de 0009 para 0010 durante o merge da branch 95).

## 3. Como a fisica funciona (resumo conceitual)

O motor detalhado fala a "moeda" **tempo de volta (ms)**: combustivel, clima,
pneu, bandeiras, etc. todos devolvem ms a mais/menos na volta. O motor 2D fala a
"moeda" **posicao e velocidade a cada passo**; o tempo de volta e consequencia.

Por isso os efeitos que ja existiam **nao foram reescritos**, e sim
**traduzidos**: a penalidade em ms de cada modelo (ex. `fuel.ms_per_kg`,
`tyre_penalty_ms`, agua do clima) e convertida em uma reducao fracionaria da
velocidade do carro (`CarSpaceState.speed_scale`). Assim a volta mais lenta
emerge do movimento. Essa traducao e o grosso do trabalho da "fatia 6".

## 4. Estado atual

### Feito

- `src/f1_simulator/domain/speed_dynamics.py` — envelope fisico, teto por
  curvatura, tempo de volta por distancia (ADR 0010).
- `src/f1_simulator/domain/track_space.py` — motor 2D: pista em faixa com
  largura (`build_track_space`, `TrackSpace`), estado espacial do carro
  (`CarSpaceState`), integrador sub-volta de um carro (`integrate_single_car`),
  integrador multi-carro com exclusao espacial, ultrapassagem emergente por
  troca de faixa e colisao por sobreposicao (`integrate_field`).
- `src/f1_simulator/domain/race_simulation_2d.py` — orquestra o 2D e devolve o
  mesmo `history`/`classification`/`starting_grid` do motor detalhado (lido pelo
  `RacePlayback` do frontend). Pneu, combustivel, clima e abandono mecanico via
  `speed_scale`/sorteio por volta.
- Cadeia de selecao: `run_detailed_grid_simulation(engine="2d")` →
  `backend/app/services/catalog.py::run_grid(engine=...)` → rota
  `POST /catalog/grid/run` (campo `setup.engine` em
  `backend/app/schemas/responses.py::RaceSetupRequest`).
- `tests/test_track_space.py` — 17 testes das fatias espaciais (passando).

### Falta (features que o motor DETALHADO tem e o 2D ainda NAO)

Todas as features abaixo foram **implementadas** (ver secao "Adaptacao das
features que faltavam"), mas **ainda nao foram testadas nem commitadas** (ver o
aviso principal e a secao "Proximos passos"):

- ~~pit stop e troca de pneus~~ adaptado;
- ~~reabastecimento e estrategia de parada por piloto~~ adaptado;
- ~~Safety Car, VSC, bandeiras (amarela/vermelha/relargada), relargada~~ adaptado;
- ~~lift-and-coast (economia de combustivel)~~ adaptado;
- ~~bandeira azul (retardatarios)~~ coberta pela fisica espacial (ver abaixo).

O resultado do 2D continua um cenario hipotetico, nao comparavel ao historico;
a estrategia e as heuristicas reusadas sao as mesmas do motor por volta. Tudo
declarado em `assumptions` (`kind: engine_2d`, `parameter_version: motor-2d-v2`).

### Adaptacao das features que faltavam (feito, nao verificado)

A "moeda" do 2D e posicao/velocidade por passo; o motor por volta cobra tudo em
ms por volta. A traducao reusa os modelos existentes, sem reescreve-los, e os
converte em reducao de velocidade (`speed_scale`) ou atraso na volta:

- **pit stop + pneu + reabastecimento + lift-and-coast**
  (`race_simulation_2d.py`): a `HeuristicPitStrategy` do motor por volta decide a
  parada por piloto no `on_lap_complete`; o pneu reseta (`TyreSet`), a perda de
  boxes entra como ms na volta de entrada (reduzindo `speed_scale`), o
  reabastecimento ajusta a massa, e `fuel_lap` fornece a economia do
  lift-and-coast. Campos `stops_made`, `compound`, `tyre_age_laps`, `fuel_kg`,
  `fuel_saving_laps`, `refuels_made` no retrato por volta.
- **controle de prova (SC/VSC/amarela/vermelha/relargada)**: reusa o automato
  de `race_control` (`step`/`effects`), avancado uma vez por volta da corrida na
  primeira vez que qualquer carro completa a volta N. `LapEffects.lap_time_factor`
  e `lap_time_loss_ms` modulam o `speed_scale` de todos; `race_control_by_lap` e
  `race_control_events` saem no resultado como no motor detalhado. Um gancho
  novo e opt-in em `integrate_field`, `neutralized_lap(lap)`, segura a fila sem
  disputa nem colisao nas voltas neutralizadas (default `None` preserva o
  comportamento anterior).
- **bandeira azul**: no 2D nao ha aproximacao temporal. O retardatario ja esta
  fisicamente atras em `distance_m`, entao a propria fila do integrador o mantem
  atras do carro que vai dar a volta nele.

### Limitacoes conhecidas

- Integrador sem car-following com frenagem antecipada: na entrada de curva a
  folga entre carros em fila pode encolher por um ou dois passos.
- `speed_at` em `speed_dynamics.py` e codigo morto (sem consumidor).
- Controle de prova no 2D e por volta da corrida (do lider), nao por posicao
  fisica na pista: a neutralizacao vale para todos a partir da volta seguinte,
  como no motor por volta. A compressao de pelotao do detalhado
  (`_compress_running_field`) nao foi portada; no 2D o agrupamento sob SC emerge
  da fila em ritmo reduzido, nao de uma reescrita de tempos.
- A ordem de consumo do RNG do 2D NAO e identica a do motor por volta; a
  reproducibilidade e por semente dentro do proprio 2D, nao um espelho bit a bit
  do detalhado. As fatias ja eram assim.
- A perda de boxes vira atraso de ritmo na volta de entrada (reduz
  `speed_scale`), nao uma parada fisica no pit lane: o carro desacelera naquela
  volta em vez de sair da pista. O tempo perdido e o mesmo; a trajetoria 2D da
  parada e aproximada.

## 5. Proximos passos (em ordem)

1. **Rodar a suite completa** (`pytest`, ou `unittest` com `PYTHONPATH=src:.`
   se `pytest` nao estiver instalado) e corrigir regressoes. Nunca foi rodada
   desde o merge da branch 95 (combustivel + velocidade). Pontos de risco:
   `test_run_grid_detailed.py`, `test_fuel.py`, `test_race_playback.py`,
   `test_catalog_grid_run.py`, `test_track_geometry.py`.
2. **Escrever testes permanentes para `race_simulation_2d.py`**. Alem de pneu,
   clima, combustivel, abandono reproduzivel e a cadeia `engine="2d"` lida pelo
   `RacePlayback`, cobrir agora as features recem-adaptadas: pit stop (reset de
   pneu, `stops_made`, perda de boxes), reabastecimento (`refuels_made`,
   `fuel_kg`), lift-and-coast (`fuel_saving_laps`, so com reabastecimento
   desligado), controle de prova (SC/VSC/vermelha/relargada: `race_control_by_lap`,
   `race_control_events`, neutralizacao que segura a fila via `neutralized_lap`
   em `integrate_field`). Validar tambem que `neutralized_lap=None` nao muda os
   17 testes de `track_space.py`.
3. **Fechar um commit** do estado consolidado.
4. So entao decidir: promover o 2D a padrao (exige **novo ADR** e revisao de
   paridade), ou refinar as aproximacoes (compressao de pelotao sob SC,
   car-following, parada fisica no pit lane).

**Nao aposentar o motor detalhado** antes da paridade de features e de uma
decisao de ADR. Hoje ele e o padrao completo e calibrado; o 2D e o novo e
incompleto.

## 6. Como rodar a simulacao 2D

O motor 2D e selecionavel pela API, mas **nao ha botao no frontend** ainda.

1. Suba o backend: `docker compose up -d --build backend`.
2. Monte um grid (pelo frontend ou API) e dispare a corrida com `engine="2d"`:
   ```bash
   curl -X POST http://localhost:8000/catalog/grid/run \
     -H "Content-Type: application/json" \
     -d '{"setup": {"total_laps": 10, "track_id": "circuit:18", "engine": "2d"}}'
   ```
   (O 2D exige geometria da pista; use um `track_id` com geometria.)
3. Abra a corrida salva no Arcade: `uv run python -m frontend.arcade.track_view`.

Sem `engine: "2d"`, roda o motor detalhado (padrao).

## 7. Como o novo perfil usa este handoff

O proximo perfil trabalha no **mesmo repositorio**, entao basta ler, nesta ordem:
`AGENTS.md`, este arquivo, `docs/adr/0010-*` e `docs/adr/0011-*`,
`docs/CODEBASE_MAP.md` (linha "Motor de corrida" e os modulos novos) e a ultima
secao de `docs/progresso.md`. O historico de chat da sessao anterior **nao**
migra entre contas; este documento e o transporte do contexto.
