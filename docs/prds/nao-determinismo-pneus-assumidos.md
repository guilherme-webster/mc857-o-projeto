# Não determinismo controlado no core, com pneus e ruído assumidos

**Status:** rascunho para aprovação do grupo. Nada aqui foi implementado.
**Data:** 2026-09-25
**Origem:** pedido do professor de MC857 por mais cenário não determinístico; revisão da
modelagem de pneus (#63) feita em 2026-09-25.
**Issues relacionadas (a confirmar):** #63 (pneus), #70 e #71 (consumir dados da modelagem e
executar a simulação), #8. Nenhuma issue nova foi criada.

## 1. Problema

O core simula toda corrida com ritmo constante por piloto (`domain/race_simulation.py:86`,
`totals[driver_id] += lap_time_ms`). O resultado é sempre o mesmo, e pneus, pit stops e
variação por volta não existem. O professor quer mais cenário não determinístico.

A modelagem de pneus (#63) não fornece coeficientes calibrados: idade do pneu e queima de
combustível estão confundidas, o benchmark fora do evento não supera a constante (intervalos
cruzam zero) e a idade de âncora não é compatível com `PaceContext`. Portanto **nenhum número
empírico de pneu pode ser apresentado como calibrado**.

## 2. Decisão de escopo (já tomada pelo usuário em 2026-09-25)

- Introduzir variância de forma simples, com **parâmetros assumidos e rotulados como tal**.
- Enriquecer a modelagem de pilotos e afins **depois**; fora deste PRD.
- Aproveitar da modelagem de pneus apenas a **estrutura** (estado de pneu, contrato imutável,
  regra ancorada) e a **direção qualitativa** (SOFT desgasta mais que MEDIUM, e este mais que
  HARD). Os valores numéricos são hipóteses, inspiradas na ordem de grandeza da análise
  exploratória (+32,5 / +23,2 / +6,4 ms por volta de idade), e não medidas.

## 3. Solução

Duas fontes de variação, ambas opcionais e desligadas por padrão:

1. **Desgaste de pneu determinístico e assumido:** cada carro corre com um composto e uma idade
   de pneu que cresce a cada volta. O efeito no tempo é
   `efeito = g(idade) − g(idade_âncora)`, com `g` linear.
2. **Ruído por volta com semente:** um deslocamento aleatório de média zero em cada volta,
   sorteado por um `RandomSource` injetável e semeado.

Propriedade central: **mesma semente, mesmos dados e mesmos parâmetros dão exatamente o mesmo
resultado** (`AGENTS.md`). A aleatoriedade é escolhida na **borda**: o backend sorteia a semente
quando o cliente não informa uma, e a devolve na resposta, de modo que qualquer corrida
"aleatória" pode ser reproduzida depois.

Sem modelo de pneu e sem `RandomSource`, o comportamento e a saída de `simulate_race` e
`simulate_series` permanecem **idênticos aos atuais**.

## 4. Requisitos

### 4.1 Contrato de pneus (`domain/tyres.py`)

- Dataclasses `frozen=True, slots=True`, unidades no nome, tuplas em vez de listas.
- `TyreModelParameters`:
  - `compound: str` (`SOFT`, `MEDIUM` ou `HARD`; sem INTER/WET nesta fase)
  - `source_kind: Literal["assumed", "estimated"]`; nesta fase só `"assumed"` é usado
  - `parameter_version: str`
  - `anchor_age_laps: int`, `min_age_laps: int`, `max_age_laps: int` (faixa de suporte)
  - `linear_ms_per_lap: float` (inclinação; pode ser zero, mas nunca é truncada)
  - `rationale: str` (por que o valor foi assumido)
- `TyreState(compound, age_laps_before_lap)`: nossa própria convenção. **Idade = voltas já
  completadas com esse jogo de pneus antes de a volta começar**, então a primeira volta tem
  idade 0. Ela **não** é o `TyreLife` do FastF1, cuja convenção pré/pós-volta ainda não foi
  confirmada; o mapeamento fica fora deste PRD porque nenhum valor vem de dados reais.
- `tyre_effect_ms(parameters, state) -> float`: `linear_ms_per_lap * (idade − idade_âncora)`.
  Efeito exatamente zero na âncora.
- Idade fora de `[min_age_laps, max_age_laps]` ou composto sem parâmetro **levanta
  `ValueError`**. Nunca há clamp, extrapolação silenciosa ou zero por ausência.
- Conjunto padrão assumido `ASSUMED_DRY_TYRES` no mesmo módulo, com docstring que diz
  explicitamente que os valores são hipóteses. Proposta inicial (ver decisão D2):

  | Composto | `linear_ms_per_lap` | `anchor_age_laps` | `max_age_laps` |
  |---|---|---|---|
  | SOFT | 30 | 0 | 80 |
  | MEDIUM | 20 | 0 | 80 |
  | HARD | 6 | 0 | 80 |

### 4.2 Fonte de aleatoriedade (`domain/random_source.py`)

- `RandomSource` como `typing.Protocol`, com `standard_normal(label: str) -> float`. O
  `label` documenta a finalidade do sorteio e entra no registro.
- `SeededRandomSource(seed: int)`, em stdlib pura (`random.Random`), sem I/O. Fica em `domain/`
  porque o `race_simulation.py` não pode importar `application/` (o domínio só importa o
  domínio).
- **Nunca** usar `hash()` do Python para derivar sub-sementes (é salgado por processo). Se
  fluxos independentes por piloto forem necessários, derivar com `hashlib`.
- Registro opcional dos sorteios (`label`, valor) para auditoria, como o plano exige
  (`Desenvolvimento de Simulador F1.md:442`). Desligado por padrão.

### 4.3 Ruído por volta (parâmetro assumido)

- `LapVariabilityAssumption(sigma_pct_of_reference, truncation_sigmas, source_kind,
  parameter_version, rationale)`.
- Valor proposto (decisão D3): `sigma_pct_of_reference = 0.2` (%), `truncation_sigmas = 3.0`,
  `source_kind = "assumed"`. Não é calibrado: o MAD dos perfis é uma medida de dispersão
  observada, e os próprios docs proíbem transformá-lo em ruído.
- O sorteio é truncado em ±`truncation_sigmas` desvios. Essa truncagem é regra **documentada e
  parametrizada**, e não um clamp escondido.
- Ordem dos sorteios determinística e **independente da ordem de entrada** dos competidores:
  voltas em ordem crescente e, dentro de cada volta, competidores por `driver_id`.

### 4.4 Estado por volta e decomposição no motor (`domain/race_simulation.py`)

- Novo `LapTimeBreakdown(reference_ms, tyre_effect_ms, noise_ms)`, com
  `lap_time_ms = reference_ms + tyre_effect_ms + noise_ms`.
- `Competitor.lap_time_ms` passa a significar o **tempo de volta no ponto de ancoragem do
  pneu** quando um modelo de pneu é informado. Isso evita contar duas vezes o efeito de pneu.
- `simulate_race(competitors, total_laps, *, tyre_plan=None, variability=None, rng=None)`,
  todos opcionais e apenas por palavra-chave.
  - `tyre_plan`: mapa `driver_id -> composto`, com **um composto por corrida e sem pit stop**
    (ver seção 5).
  - Se `variability` for informado, `rng` é obrigatório (senão `ValueError`).
- Com os três em `None`, a saída é **byte a byte igual** à atual.
- Com algum ativo, cada carro da `history` ganha `breakdown` e o resultado ganha
  `assumptions` (lista de parâmetros usados com `source_kind`, `parameter_version`,
  `rationale`).
- Tempo de volta resultante deve permanecer positivo; caso contrário, `ValueError`
  explícito.
- Aritmética em `float`, arredondando a 0,1 ms só na saída, como hoje. A divergência com o
  `Decimal` dos perfis é **decisão D1**; ver seção 8.

### 4.5 Série e backend

- `simulate_series(..., *, tyre_plan=None, variability=None, seed=None)`: cada corrida deriva
  seu fluxo aleatório de `(seed, circuit_id)` com `hashlib`, para que reordenar a sequência de
  pistas não mude o resultado de cada corrida.
- `POST /simulation/series/simulate`: campos opcionais novos no corpo, `seed: int | None`,
  `tyres: dict[driver_id, composto] | None` e `variability: bool = False`.
  - Se `variability` for verdadeiro e `seed` estiver ausente, **o router sorteia a semente** e a
    devolve na resposta. O domínio nunca sorteia semente sozinho.
  - A resposta ganha `seed` e `assumptions`. Sem os campos novos, a resposta é a de hoje.
  - Validação Pydantic: composto desconhecido gera 422; `driver_id` em `tyres` fora da lista de
    participantes gera 422.
- `backend/app/loaders/loader.py` **não** é tocado, mas fica fora do caminho novo (ele trunca a
  degradação em zero e converte pit loss ausente em `0.0`; ver bloqueio na revisão).

### 4.6 Registro de decisão e documentação

- ADR 0007, "Não determinismo controlado com parâmetros assumidos": a decisão toca domínio e
  backend e é difícil de reverter, então segue a regra de governança do `CONTRIBUTING.md`.
- Atualizar o texto do `README.MD` que diz que o motor usa ritmo constante e que clima e pit
  não alteram o resultado, sem afirmar que a variância é calibrada.
- Regenerar `docs/CODEBASE_MAP.md` (modo de atualização do Cartographer) depois de integrar.

## 5. Fora de escopo (e por quê)

- **Pit stops e estratégia:** sem troca de pneu, um composto dura a corrida inteira. Isso
  limita o realismo (um SOFT assumido em 30 ms/volta acumula ~2,1 s em 70 voltas), mas evita
  inventar perda de pit, política de troca e safety car sem dados. É a próxima fatia natural.
- **Compostos INTER e WET e clima:** sem estudo que os sustente.
- **Integração com `DriverParametersProvider` e `PaceContext`:** a referência por contexto já
  embute carro, pneu e clima; somar o efeito de pneu duplicaria o efeito até existir referência
  com idade de âncora exata.
- **Frontend Arcade:** ligar "Confirmar torneio" à simulação e expor semente/variância na tela.
- **Calibração empírica de qualquer parâmetro** e ruído dependente do piloto.
- **Refatoração ampla** de `loader.py`, ETL ou perfis.

## 6. Plano de implementação (fatias verticais)

Cada fatia deixa o projeto verde (`python3 -m unittest`, a partir da raiz) e vira **um
commit** com mensagem `tipo(escopo): resumo`. As fatias 1 e 2 são independentes (arquivos
disjuntos) e podem ser feitas em paralelo.

### Fatia 1: contrato de pneus
- **Arquivos:** `src/f1_simulator/domain/tyres.py`, `tests/test_tyre_model.py`.
- **Testes:** efeito zero na âncora; linearidade; idade fora do suporte gera erro; composto sem
  parâmetro gera erro; inclinação zero é aceita e negativa **não** é truncada; ordem
  SOFT > MEDIUM > HARD do conjunto assumido; docstring/`rationale` presentes.
- **Aceite:** nenhum zero silencioso, nenhum clamp, unidades nos nomes.
- **Commit:** `feat(dominio): adicione contrato de pneus com parametros assumidos`

### Fatia 2: fonte de aleatoriedade
- **Arquivos:** `src/f1_simulator/domain/random_source.py`, `tests/test_random_source.py`.
- **Testes:** mesma semente gera a mesma sequência; sementes diferentes divergem; **resultado
  igual em processos com `PYTHONHASHSEED` diferentes**; registro de sorteios opcional e
  ordenado; truncagem respeita o limite.
- **Aceite:** sem `hash()`, sem estado global, sem I/O.
- **Commit:** `feat(dominio): adicione fonte de aleatoriedade injetavel com semente`

### Fatia 3: estado por volta e decomposição no motor
- **Depende de:** 1 e 2.
- **Arquivos:** `src/f1_simulator/domain/race_simulation.py`, `tests/test_race_simulation_core.py`
  (novos casos), possivelmente `tests/test_race_simulation_variability.py`.
- **Testes:** com tudo `None`, saída **idêntica** à atual (os testes existentes passam sem
  alteração); pneu sem ruído é determinístico e cresce a cada volta; mesma semente reproduz o
  resultado inteiro e sementes diferentes o alteram; **resultado independe da ordem de entrada
  dos competidores**; `variability` sem `rng` gera erro; tempo de volta não positivo gera erro;
  `breakdown` soma exatamente o tempo de volta; `assumptions` sempre presente quando ativo.
- **Aceite:** o `RandomSource` é sempre injetado; nenhum `random` global.
- **Commit:** `feat(dominio): incorpore pneu assumido e ruido com semente ao motor`

### Fatia 4: série e endpoint
- **Depende de:** 3.
- **Arquivos:** `src/f1_simulator/domain/race_series.py`, `backend/app/schemas/responses.py`,
  `backend/app/routers/simulation.py`, `tests/test_race_series.py`.
- **Testes:** resposta atual inalterada sem campos novos; mesma semente reproduz a série; a
  ordem das pistas não altera o resultado de cada corrida; semente sorteada pelo router é
  devolvida e reproduz o resultado; composto desconhecido e `driver_id` inexistente dão 422.
- **Aceite:** o domínio nunca sorteia semente; `loader.py` intocado.
- **Commit:** `feat(backend): aceite semente, pneus e variancia na serie de corridas`

### Fatia 5: ADR e documentação
- **Arquivos:** `docs/adr/0007-...md`, `docs/adr/README.md`, `README.MD`, este PRD (marcar como
  implementado) e `docs/CODEBASE_MAP.md`.
- **Aceite:** o texto diz claramente que os parâmetros são **assumidos**, e cita os bloqueios
  da modelagem de pneus.
- **Commit:** `docs(adr): registre nao determinismo controlado com parametros assumidos`

## 7. Critérios de sucesso

- `simulate_race` e `simulate_series` sem parâmetros novos: saída idêntica à de hoje.
- Com semente: duas execuções idênticas produzem JSON idêntico; sementes diferentes produzem
  classificações que podem diferir.
- Nenhum parâmetro assumido é rotulado como calibrado, em código, resposta ou documentação.
- Nenhum `except` silencioso, clamp escondido ou ausência convertida em zero.
- Todos os testes existentes continuam passando; testes novos cobrem cada fatia.

## 8. Decisões que preciso que você aprove antes de implementar

| # | Decisão | Recomendação |
|---|---|---|
| D1 | Precisão numérica: manter `float` no motor (arredondando a 0,1 ms na saída) ou migrar tudo para `Decimal` e ms inteiros | Manter `float` nesta fase e documentar; unificar depois, quando os perfis entrarem no motor |
| D2 | Valores assumidos de pneu: 30, 20 e 6 ms por volta (SOFT, MEDIUM, HARD), suporte até 80 voltas | Aceitar, rotulados como hipótese e revisáveis; a variação por circuito fica para depois |
| D3 | Ruído: σ = 0,2% do tempo de referência, truncado em ±3σ | Aceitar como hipótese; o valor é fácil de mudar por ser parâmetro nomeado |
| D4 | Semente sorteada no backend (e devolvida) quando o cliente não informa | Aceitar; preserva reprodutibilidade sem pôr sorteio no domínio |
| D5 | Sem pit stops nesta fase (um composto por corrida) | Aceitar; pit e estratégia viram o PRD seguinte |
| D6 | Branch de trabalho: nova a partir de `origin/develop`, em worktree próprio, em vez de reaproveitar a `63-modelagem-pneus` | Nova branch, por exemplo `feat/nao-determinismo-core` (o PR vai para `develop`); você indica o número da issue para o nome |

## 9. Execução com agentes Codex

- Modelo: **`gpt-6-sol`** (`-m gpt-6-sol`), raciocínio alto, sandbox `workspace-write`, com
  `--map`. Tarefas simples, como a fatia 5, podem usar `gpt-6-luna`.
- Ordem: fatias 1 e 2 em paralelo; depois 3; depois 4; depois 5. Cada fatia é revisada por um
  agente separado em modo somente leitura antes do commit.
- Os agentes rodam em um worktree dedicado, para não colidir com as outras sessões.
- Commits só com sua autorização, um por fatia, no formato do `CONTRIBUTING.md`.
- Ao final: comentar o andamento na issue correspondente e regenerar o espelho do backlog
  (`python3 scripts/sync_github_backlog.py`), conforme o `AGENTS.md`.

## 10. Riscos

- **Realismo limitado:** sem pit stops, pneus macios acumulam degradação irreal em corridas
  longas. Mitigação: rótulo explícito de hipótese, suporte máximo e a fatia de pit como
  próxima etapa.
- **Falsa impressão de calibração:** números plausíveis podem ser lidos como medidos.
  Mitigação: `source_kind`, `rationale` e `assumptions` em toda resposta que os use.
- **Regressão silenciosa do caminho determinístico:** mitigada pelo critério de saída idêntica
  e pelos testes existentes sem alteração.
- **Ambiente:** o Python local é 3.14, e o projeto mira 3.12+. Testes devem rodar em 3.12
  quando possível (o backend exige `fastapi`, que não está instalado localmente).
