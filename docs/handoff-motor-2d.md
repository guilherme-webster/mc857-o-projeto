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

- pit stop e troca de pneus;
- reabastecimento e estrategia de parada por piloto;
- Safety Car, VSC, bandeiras (amarela/vermelha/relargada), relargada;
- lift-and-coast (economia de combustivel);
- bandeira azul (retardatarios).

Enquanto isso, o 2D e **menos completo** que o detalhado, e seu resultado e
cenario hipotetico, nao comparavel ao historico. Tudo declarado em
`assumptions` (`kind: engine_2d`) no resultado.

### Limitacoes conhecidas

- Integrador sem car-following com frenagem antecipada: na entrada de curva a
  folga entre carros em fila pode encolher por um ou dois passos.
- `speed_at` em `speed_dynamics.py` e codigo morto (sem consumidor).

## 5. Proximos passos (em ordem)

1. **Rodar a suite completa** (`pytest`, ou `unittest` com `PYTHONPATH=src:.`
   se `pytest` nao estiver instalado) e corrigir regressoes. Nunca foi rodada
   desde o merge da branch 95 (combustivel + velocidade). Pontos de risco:
   `test_run_grid_detailed.py`, `test_fuel.py`, `test_race_playback.py`,
   `test_catalog_grid_run.py`, `test_track_geometry.py`.
2. **Escrever testes permanentes para `race_simulation_2d.py`** (pneu, clima,
   combustivel, abandono reproduzivel, cadeia `engine="2d"` lida pelo
   `RacePlayback`). Hoje so ha testes do `track_space.py`.
3. **Fechar um commit** do estado consolidado.
4. So entao decidir: completar as features que faltam no 2D, ou promover o 2D a
   padrao (exige **novo ADR** e paridade de features).

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
