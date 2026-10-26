# Modelagem heurística da corrida: referência

Este é o lugar para consultar **quais heurísticas o simulador usa, com que
valores e onde mudá-las**. O plano e o histórico das decisões estão no
[PRD](prds/modelagem-pilotos-heuristica.md); a decisão arquitetural está no
[ADR 0008](adr/0008-modelagem-heuristica-sobre-o-motor-calibrado.md).

Valores conferidos no código em 2026-10-16 (branch `6-reproducao-volta-a-volta`;
os valores não mudaram desde a branch `67-modelagem-pilotos`, de 2026-10-03).
Combustível e reabastecimento (§6 e tabelas) conferidos em 2026-10-23, branch
`97-modelagem-combustivel`; decisão no
[ADR 0009](adr/0009-combustivel-por-massa-e-reabastecimento.md).
Se um número aqui divergir do código, **vale o código**: atualize este arquivo.

## 1. Princípios

- **Heurístico, não medido.** O professor aceitou modelagem por heurísticas e o
  grupo optou por ela. Nenhum valor desta página descreve pilotos reais; os
  perfis nomeados são caracterizações fictícias.
- **Rotulado.** Todo parâmetro tem origem (`heuristic`, `assumed`,
  `calibrated`, `historical-median`), versão e justificativa, e toda resposta da
  corrida lista em `assumptions` o que foi usado.
- **Reproduzível.** Mesma semente, mesmos dados e mesmos parâmetros dão a mesma
  corrida. Toda aleatoriedade passa pelo `RandomSource` injetado.
- **Neutro por padrão.** Sem os recursos novos, o motor detalhado reproduz
  exatamente o motor calibrado da issue #40 (há teste com hashes de referência).
- **Sem zero silencioso.** Ausência vira erro explícito ou valor de reserva
  declarado, nunca zero.

## 2. Onde está cada coisa

| Tema | Código | Parâmetros (versão) |
|---|---|---|
| Atributos e arquétipos | `domain/driver_attributes.py`, `application/generate_attributes.py` | `ASSUMED_ARCHETYPES` (`assumed-driver-attributes-v2`) |
| Perfis fictícios nomeados | `configs/drivers/perfis-ficticios.json`, `adapters/driver_presets_json.py` | `fictional-driver-presets-v1` |
| Efeito dos atributos no tempo | `domain/attribute_effects.py` | `DETAILED_TYRE_MANAGEMENT` (`detailed-tyre-management-v1`) |
| Disputa de posição | `domain/disputes.py` | `DEFAULT_DISPUTE_HEURISTICS` (`dispute-pressure-v1`) |
| SC, VSC e bandeiras | `domain/race_control.py` | `HEURISTIC_RACE_CONTROL` (`heuristic-race-control-v2`) |
| Paradas | `domain/strategy.py` (`HeuristicPitStrategy`) | `DEFAULT_HEURISTIC_PIT_PARAMETERS` (`heuristic-pit-v1`) |
| Combustível por massa | `domain/fuel.py` (`FuelModelParameters`, `FuelPlan`, `fuel_lap`), `data/parameters/fuel-v1.json` | `fuel-trotman-v128-2022-2023` (coeficiente calibrado; consumo, reserva e fatores `assumed`) |
| Reabastecimento estratégico | `domain/strategy.py` (`HeuristicPitStrategy` com `FuelStatus`, `FuelStrategyTraits`, `draw_fuel_traits`) | `heuristic-fuel-strategy-v1`; `DEFAULT_FUEL_TRAIT_HEURISTICS` (`heuristic-fuel-traits-v1`) |
| Tempo de parada por carro | `domain/fuel.py` (`RefuelStopParameters`, `sample_refuel_stops`), bloco `refuel_stops` do `fuel-v1.json` | calibrado nas paradas do Trotman 2023–2024 |
| Entrada dos boxes | `domain/track_geometry.py` (`pit_entry_lap_fraction`) | geometria FastF1 (só a posição na volta) |
| Volta de referência | `application/reference_laps.py`, `data/parameters/reference-laps-v1.json` | `historical-median-fastest-laps-v1` |
| Clima no tempo de volta | `domain/weather.py` (`simulate_weather`, `weather_penalty_ms`) | `ASSUMED_WEATHER_PARAMETERS` (`assumed-weather-per-lap-v1`), `ASSUMED_WEATHER_EFFECT` (`assumed-weather-effect-v1`) |
| Composto de largada | `application/run_grid_simulation.py` | `assumed-grid-starting-compound-v1` (MEDIUM para todos) |
| Ligação ao grid | `application/run_grid_simulation.py` (`run_detailed_grid_simulation`) | ritmo de reserva `ASSUMED_REFERENCE_PACE_MS_PER_KM` |
| Motor | `domain/race_simulation.py` (`simulate_detailed_race`) | — |
| Física calibrada (colega, #40) | `data/parameters/model-v1.json` | `trotman-v128-2022-2023` |

## 3. Atributos de piloto

Cinco atributos, sorteados com semente dentro da faixa do arquétipo. Os fatores
multiplicativos têm 1,0 como neutro.

| Atributo | Efeito | aggressive | balanced | conservative |
|---|---|---|---|---|
| `pace_offset_pct` | Referência da volta × (1 + pct/100) | −0,60 a −0,20 | −0,15 a +0,15 | +0,10 a +0,40 |
| `consistency_factor` | Desvio do ruído por volta | 1,10 a 1,40 | 0,90 a 1,10 | 0,70 a 0,95 |
| `tyre_management_factor` | Degradação do pneu (amortecida, ver abaixo) | 1,15 a 1,45 | 0,90 a 1,10 | 0,65 a 0,90 |
| `aggression` | Pressão do atacante e risco de contato | 1,20 a 1,50 | 0,90 a 1,10 | 0,60 a 0,85 |
| `composure` | Firmeza do defensor sob pressão | 0,85 a 1,05 | 0,90 a 1,10 | 1,05 a 1,30 |

**Precedência de origem por campo:** `manual` (PATCH) > `preset` (perfil
nomeado) > `generated` (sorteio).

**Gestão de pneus amortecida.** No motor detalhado, a degradação usa
`1 + 0,4 × (tyre_management_factor − 1)`, ou seja, 0,86× a 1,18× em vez de
0,65× a 1,45×. Com o fator integral, os agressivos faziam 2,4 paradas contra
1,1 dos conservadores em pistas de desgaste alto e terminavam atrás deles. O
mesmo multiplicador vai para a estratégia de parada.

**Perfis nomeados.** 24 pilotos do grid de 2024 em
`configs/drivers/perfis-ficticios.json`, com arquétipo, alguns valores fixados
e uma frase de caracterização. Para mudar um piloto, edite o JSON: valores fora
da faixa do arquétipo são rejeitados.

O `POST /catalog/grid` em modo `random` sorteia pilotos de toda a história
(desde 1950); os perfis nomeados entram num grid `manual` com os pares de 2024
ou no modo `race`, que reproduz a largada de uma corrida histórica
(`race_id`, por exemplo uma etapa de 2024). Pilotos sem perfil nomeado recebem
atributos sorteados do arquétipo. A resposta do grid traz, para quem tem campo
de origem `preset`, a caracterização do perfil, e no topo o aviso de que os
perfis são fictícios; a tela "Pilotos e grid" do Arcade mostra ambos.

## 4. Disputa de posição (slides da #40)

Quando um carro alcança o da frente durante a volta:

```
proximidade = 1 − intervalo_no_inicio_da_volta / 1500 ms        (0 a 1)
P = (vantagem_ms / 1400 ms) × proximidade × aggression_atacante
    × consistency_factor_atacante^(−0,25)
R = dificuldade_do_circuito × composure_defensor × 33/7
p(passar) = P / (P + R) × fator_de_ultrapassagem (amarela, relargada)
```

- `33/7` faz um carro 0,5 s mais rápido passar com 13,16% por volta em pista de
  dificuldade 0,5, a mesma chance da fórmula calibrada do colega.
- Sem vantagem de ritmo, p = 0. A dificuldade vem de `model-v1.json` por
  circuito (Mônaco 0,95; Spa 0,32).
- Quem não passa fica preso atrás, com espaçamento mínimo de 700 ms.
- **Contato:** 0,35% por disputa × média da agressividade do par × fator de
  contato. Havendo contato, sorteia-se 50/50 qual dos dois abandona.
- **Bandeira azul:** um carro com volta a menos cede sem disputa nem contato; o
  líder mantém o próprio tempo e o retardatário termina atrás dele.

## 5. Safety car, VSC e bandeiras

**Incidentes:** contato em disputa, acidente individual (0,005% por carro por
volta; ×3 na primeira volta, ×2 na relargada, ×0,25 neutralizado) e abandono
mecânico (risco calibrado do colega × confiabilidade da equipe).

| Incidente | Resposta |
|---|---|
| Batida (contato ou acidente individual) | 10% grave → vermelha; nas demais: SC 33%, VSC 17%, amarela 50% |
| Abandono mecânico | Nenhuma intervenção 65%, amarela 25%, VSC 10% |

| Estado | Duração | Efeito |
|---|---|---|
| Amarela | 1 volta | Ultrapassagem ×0,5, perda de 300 ms. É global porque o motor não tem setores |
| VSC | 1–3 voltas | Tempo de volta ×1,4, sem disputa, intervalos preservados, parada custa 70% |
| SC | 3–5 voltas | Tempo de volta ×1,6, sem disputa, pelotão comprimido ao fim de cada volta, parada custa 50% |
| Relargada | 1 volta | Ultrapassagem ×1,35, contato ×1,5 |
| Vermelha | 1 volta | Ordem congelada, troca de pneu grátis, relargada com o pelotão agrupado |

Um incidente durante uma neutralização só a substitui se pedir resposta mais
grave, ou estende a atual.

**Frequência medida** (`scripts/race_control_frequency.py`, 3 sementes × 200
corridas de 58 voltas): 0,60–0,70 SC+VSC e 0,09–0,10 vermelha por corrida.
Referência real de 2024: ~0,6 SC/VSC e vermelha em 3 de 18 corridas. A vermelha
fica abaixo de 1 a cada 6 porque o grupo manteve o teto de 10% das batidas.

**Simplificações:** amarela não é por setor; vermelha não tem período de SC
antes da relargada; não há bandeira laranja nem desdobramento formal de
retardatários (a compressão do SC já os traz para perto do pelotão).

## 6. Paradas

No motor 2D, o [ADR 0012](adr/0012-percurso-espacial-de-pit-lane.md) substitui
a perda diluída por um percurso físico hipotético dos boxes. O carro entra
na próxima passagem pela entrada, percorre a polilinha a até 80 km/h, para
2,5 s no ponto de serviço e aguarda folga para retornar. Limite, serviço e
folga são injetáveis em `PitLaneParameters` e declarados como `assumed` no
resultado. A extensão em metros vem da escala do mock, não de uma medição
oficial da pit lane. `pit_loss_ms` só orienta a estratégia nesse modo: o
relógio cobra o deslocamento e o serviço, sem somar outra perda nem aplicar
desconto artificial de SC/VSC. A estratégia do 2D continua só de pneus;
o reabastecimento descrito abaixo pertence ao motor por volta.

`HeuristicPitStrategy` decide no início de cada volta:

1. **Regra econômica:** para se o custo de continuar no jogo atual até o fim
   superar o custo de um jogo novo + perda de boxes (× fator do SC/VSC) +
   margem de 1,5 s.
2. **Oportunista:** sob SC ou VSC, para se restar menos de 25% da vida típica
   do pneu.
3. **Sem parada nas últimas 3 voltas**, salvo pneu muito além da vida típica.
4. **Dois compostos** em pista seca: força a parada antes da janela final.
5. **Variação por piloto** de ±2 voltas, sorteada fora da estratégia.

Composto inicial: MEDIUM para todos (hipótese). Próximo composto: o mais macio
cuja vida típica cobre o restante da corrida.

### Com reabastecimento ligado (combustível por massa)

Quando a corrida usa o modelo de massa (`fuel-v1.json`) com
`refuelling_allowed`, toda parada troca pneus **e** reabastece, e a mesma
`HeuristicPitStrategy` decide as duas coisas juntas. A cada volta o piloto
conhece a massa a bordo, a queima da volta, quanto cada kg custa e a perda
média da sua parada:

1. **Tanque cobre o fim:** valem só as regras de pneus acima; uma parada, se
   houver, não abastece.
2. **Limite físico:** se não chegaria à próxima entrada dos boxes com a sua
   folga, para agora. A posição da entrada vem da geometria (89–99,6% da
   volta), e a volta de entrada só queima até ela.
3. **Regra econômica:** compara parar agora com parar na última volta
   possível. Cada cenário soma, até o fim, o desgaste do pneu atual, o peso do
   combustível, a parada (perda do carro × fator do SC/VSC, mais o tempo de
   abastecer além da troca de pneus) e um plano do resto da corrida. Para se
   agora for mais barato pela margem de 1,5 s. Sob SC/VSC a parada fica mais
   barata e tende a ser antecipada, sem regra separada.
4. **Plano do resto (`_plan_rest`):** escolhe entre o mínimo de stints que o
   tanque permite e até duas paradas a mais, com stints quase iguais; daí
   saem o composto e quanto abastecer. A carga de largada é a do primeiro
   stint desse mesmo plano.
5. **Rede de segurança do motor:** estratégias que não olham o combustível
   são chamadas aos boxes antes de não alcançarem a entrada; enchem para
   terminar e repetem o composto.

Preferências por piloto (`FuelStrategyTraits`), sorteadas no fluxo
`strategy:fuel:<piloto>` a partir de `aggression`, com z₁, z₂, z₃ normais
padrão (`heuristic-fuel-traits-v1`):

| Preferência | Fórmula | Faixa | Efeito |
|---|---|---|---|
| `margin_laps` | 0,5 − 0,5 × (agressividade − 1) + 0,2 × z₁ | 0,2 a 1,5 volta | Folga ao chegar aos boxes; maior = para antes |
| `stop_cost_bias` | 1 − 0,5 × (agressividade − 1) + 0,15 × z₂ | 0,5 a 1,5 | Peso das paradas futuras; menor = carro leve e mais paradas |
| `stint_shift` | −0,2 × (agressividade − 1) + 0,12 × z₃ | −30% a +30% | Encurta (undercut) ou alonga (overcut) o próximo stint |

Parâmetros do combustível (`fuel-v1.json`):

| Parâmetro | Valor | Origem |
|---|---|---|
| Fração do tempo de volta por km de combustível | 1,271 × 10⁻⁴ (≈ 33 ms/kg numa volta de 90 s) | calibrado (Trotman 2022–2023) |
| Carga máxima | 110 kg | regulamento 2022–2025 |
| Consumo em bandeira verde | 0,3443 kg/km (105 kg em 305 km) | assumido |
| Reserva na bandeirada | 1,0 kg (amostra de 1 L da FIA) | assumido |
| Queima relativa sob VSC / SC / vermelha | 0,6 / 0,5 / 0,5 | assumido |
| Vazão do reabastecimento | 9 kg/s (~12 L/s) | assumido |
| Troca de pneus parada | 2,5 s (já contida na perda medida) | assumido |
| Lift-and-coast (só com reabastecimento desligado) | até 8% da queima, 1,5 s por kg economizado | assumido |
| Tempo de parada por equipe | perda do circuito + deslocamento × 0,754; variação σ 1,73 s, assimetria 0,697 | calibrado (paradas Trotman 2023–2024) |

## 7. Volta de referência por circuito

`data/parameters/reference-laps-v1.json`: por corrida, a mediana das voltas
mais rápidas de cada piloto; por circuito, a mediana entre as corridas de 2022
a 2024. Exemplos: Mônaco 77,2 s; Spa 110,5 s; Monza 85,9 s. É histórico, não
heurístico, mas só fixa a escala de tempo da pista: não descreve pilotos.

Ordem de uso: tabela → comprimento da pista × 17.000 ms/km (reserva) → 90 s
(sem pista). A origem usada aparece em `assumptions`.

## 8. Como reajustar

| Quero mudar... | Onde |
|---|---|
| Um piloto específico | `configs/drivers/perfis-ficticios.json` |
| As faixas de um arquétipo | `ASSUMED_ARCHETYPES` em `domain/driver_attributes.py` |
| O efeito da chuva no tempo de volta | `ASSUMED_WEATHER_EFFECT.wet_penalty_pct_max` em `domain/weather.py` |
| Quanto pesa a gestão de pneus | `DETAILED_TYRE_MANAGEMENT.elasticity` em `domain/attribute_effects.py` |
| Dificuldade de ultrapassar | `resistance_scale` em `domain/disputes.py`, ou a dificuldade por circuito no `model-v1.json` |
| Frequência de SC/VSC/vermelha | `RaceControlParameters` em `domain/race_control.py`; depois meça com `scripts/race_control_frequency.py` |
| Quando os carros param | `HeuristicPitParameters` em `domain/strategy.py` |
| Se os carros podem reabastecer | `scenario.refuelling_allowed` no `fuel-v1.json` (ou `--no-refuelling` em `scripts/calibrate_fuel.py`) |
| Consumo, reserva, vazão e troca de pneus | bloco `assumed` do `fuel-v1.json` (padrões em `FuelModelParameters`, `domain/fuel.py`) |
| Como os pilotos tratam o combustível | `FuelTraitHeuristics` em `domain/strategy.py` |
| O efeito do combustível no tempo de volta | `scripts/calibrate_fuel.py --database ... --seasons 2022 2023 --validate-seasons 2024 2025` |
| Tempos de volta das pistas | `scripts/build_reference_laps.py --database ... --seasons ...` |

Ao mudar um valor: incremente o `parameter_version`, atualize o `rationale` e
esta página, e rode a suíte. Testes que dependem de valores exatos usam os
próprios parâmetros, não números fixos.

## 9. Limitações conhecidas

- **A pole vence muito.** Em Spa, quem larga em 1º venceu 21 de 40 corridas de
  teste, e um carro 0,5 s/volta mais rápido largando em 8º raramente vence
  (mas termina em média em 5,7º). Candidatos a ajuste: a penalidade calibrada
  de grid (782 ms por posição) e `resistance_scale`.
- A ultrapassagem é decidida por volta, não em um ponto da pista.
- **Reabastecimento não é o regulamento atual.** Fica ligado por padrão como
  regra do cenário (ADR 0009): corridas de distância real têm 2–3 paradas
  combinadas, como em 2009. `refuelling_allowed = false` volta à regra 2010+
  (lift-and-coast e pane seca).
- **Estratégia de reabastecimento sem validação histórica.** O Trotman só
  registra paradas a partir de 2011; a era 1994–2009 não foi confrontada.
- **Consumo igual por km em todos os traçados.** O consumo real depende do
  tempo em aceleração plena (Monza gasta mais por km que Mônaco); aqui só a
  extensão da volta muda a queima.
- **Mônaco para pouco.** A perda de boxes calibrada (41,9 s) está
  contaminada por corridas atípicas, então a estratégia prefere uma parada.
- **Deslocamento por equipe fraco em 2025.** Previu as paradas de 2025 pior
  que tratar todas as equipes iguais (131 contra 118 ms).
- Contato não tem culpado nem dano parcial; o carro abandona ou segue.
- **Clima só no tempo de volta.** A água na pista ao fim de cada volta
  (`domain/weather.py`, #69) acrescenta até 40% ao tempo de referência
  (`assumed-weather-effect-v1`, proporcional à água). O clima não altera
  disputas, incidentes nem paradas, e não há pneus intermediários ou de chuva:
  todos seguem nos compostos secos.
- **Composto de largada fixo e médio quase sem volta.** Todos largam de MEDIUM
  (hipótese). Enquanto a regra de dois compostos não foi cumprida, o médio fica
  fora da escolha; depois vence o mais macio cuja vida típica (macio 14, médio
  22, duro 37 voltas) cobre o restante. Por isso as paradas vão quase sempre
  para HARD, ou para SOFT nas últimas 14 voltas.
- **Severidade de pneu por circuito pouco confiável.** `tyre_severity` vem de
  `scripts/calibrate_model.py` (regressão por circuito dividida pela do campo,
  encolhida para 1,0 com peso `n/(n+1500)` e cortada em 0,30–2,50). Zandvoort
  bate no piso (0,30) apesar de 87 paradas observadas; Spa e Bahrein batem no
  teto. Efeito observado em 2026-10-16: em Zandvoort ninguém para por desgaste
  (a parada vira obrigação da regra de dois compostos, perto do fim); em Suzuka
  (2,46) os carros fazem 3–4 paradas. `observed_stops` não entra na
  calibração. Revisão a combinar com a #40.
- A interface Arcade lê trajetórias no modo 2D, inclusive o caminho dos boxes
  e o serviço parado. Para corridas por volta ou antigas, mantém a interpolação
  de `history`, com paradas diluídas na volta. Não há carro de segurança
  físico desenhado.
