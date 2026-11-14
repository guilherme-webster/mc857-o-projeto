# Modelagem heurística da corrida: referência

Este é o lugar para consultar **quais heurísticas o simulador usa, com que
valores e onde mudá-las**. O plano e o histórico das decisões estão no
[PRD](prds/modelagem-pilotos-heuristica.md); a decisão arquitetural está no
[ADR 0008](adr/0008-modelagem-heuristica-sobre-o-motor-calibrado.md).

Valores conferidos no código em 2026-10-30. A modelagem original foi integrada
na branch `67-modelagem-pilotos`, de 2026-10-03.
Combustível e reabastecimento (§6 e tabelas) conferidos em 2026-10-23, branch
`97-modelagem-combustivel`; decisão no
[ADR 0009](adr/0009-combustivel-por-massa-e-reabastecimento.md).
Se um número aqui divergir do código, **vale o código**: atualize este arquivo.

> **Nota de estado (2026-11-12, #154).** O motor por volta (`simulate_detailed_race`,
> `run_detailed_grid_simulation`, `disputes.py`, `lap_time.py`) foi removido de
> `src/`; o único motor é o 2D (`simulate_2d_race`, ADR 0011), montado por
> `run_grid_simulation`. As seções abaixo que falam em "motor detalhado" ou
> "motor por volta" descrevem o comportamento anterior e valem como registro:
> o que continua vigente no 2D está dito nas seções 6, 9 e no ADR 0014. O
> impacto da posição de largada (`grid_start`, §7.2) está arquivado em
> [`TOBEDEFINED/`](../TOBEDEFINED/README.md) (#152); a #108 pode reaproveitá-lo.
> Limitações conhecidas do 2D em §9.

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

### 1.1 Seeds de grid e torneio

`grid_seed` controla apenas a seleção do grid aleatório e a geração dos
atributos. `tournament_seed`, quando informada, controla as corridas: cada
etapa recebe uma seed derivada no núcleo por SHA-256 versionado
(`tournament-stage-v1`) sobre `(tournament_seed, stage_index)`. O índice começa
em zero, portanto repetir a mesma pista em etapas diferentes não reutiliza o
mesmo fluxo. A ordem automática das pistas usa a própria `tournament_seed`.

Seeds digitáveis ficam em `[0, 2**53 - 1]`, intervalo preservado exatamente
por clientes JSON que representam números como `double`. A resposta de
`POST /catalog/grid/run` registra `grid_seed`, `tournament_seed`, `stage_index`,
`race_seed` (texto decimal para também representar o fluxo legado de 256 bits)
e `race_stream_id`. Sem `tournament_seed`, permanece o comportamento anterior:
`SeededRandomSource(grid_seed).spawn("race")`. A reprodução é garantida com a
mesma versão de código, Python, parâmetros e dados, não entre versões.

## 2. Onde está cada coisa

| Tema | Código | Parâmetros (versão) |
|---|---|---|
| Atributos e arquétipos | `domain/driver_attributes.py`, `application/generate_attributes.py` | `ASSUMED_ARCHETYPES` (`assumed-driver-attributes-v2`) |
| Perfis fictícios nomeados | `configs/drivers/perfis-ficticios.json`, `adapters/driver_presets_json.py` | `fictional-driver-presets-v1` |
| Efeito dos atributos no tempo | `domain/attribute_effects.py` | `DETAILED_TYRE_MANAGEMENT` (`detailed-tyre-management-v1`) |
| Disputa de posição | `domain/disputes.py` (arquivado em `TOBEDEFINED/disputes.py`; no 2D a disputa emerge da proximidade espacial) | `DEFAULT_DISPUTE_HEURISTICS` (`dispute-pressure-v1`) |
| SC, VSC e bandeiras | `domain/race_control.py` | `HEURISTIC_RACE_CONTROL` (`heuristic-race-control-v2`) |
| Paradas | `domain/strategy.py` (`HeuristicPitStrategy`) | `DEFAULT_HEURISTIC_PIT_PARAMETERS` (`heuristic-pit-v1`) |
| Combustível por massa | `domain/fuel.py` (`FuelModelParameters`, `FuelPlan`, `fuel_lap`), `data/parameters/fuel-v1.json` | `fuel-trotman-v128-2022-2023` (coeficiente calibrado; consumo, reserva e fatores `assumed`) |
| Reabastecimento estratégico | `domain/strategy.py` (`HeuristicPitStrategy` com `FuelStatus`, `FuelStrategyTraits`, `draw_fuel_traits`) | `heuristic-fuel-strategy-v1`; `DEFAULT_FUEL_TRAIT_HEURISTICS` (`heuristic-fuel-traits-v1`) |
| Tempo de parada por carro | `domain/fuel.py` (`RefuelStopParameters`, `sample_refuel_stops`), bloco `refuel_stops` do `fuel-v1.json` | calibrado nas paradas do Trotman 2023–2024 |
| Entrada dos boxes | `domain/track_geometry.py` (`pit_entry_lap_fraction`) | geometria FastF1 (só a posição na volta) |
| Volta de referência | `application/reference_laps.py`, `data/parameters/reference-laps-v1.json` | `historical-median-fastest-laps-v1` |
| Voltas padrão por pista | `application/default_laps.py` | corrida mais recente ou `assumed-distance-rule-v1` |
| Clima e estado da pista | `domain/weather.py` (`step_weather`, `simulate_weather`), `domain/track_condition.py` (`simulate_track_conditions`) | `ASSUMED_WEATHER_PARAMETERS` (`assumed-weather-per-lap-v1`, por volta de referência de 1,5 min), `ASSUMED_TRACK_CONDITION` (`assumed-track-condition-v1`) |
| Tempo de volta físico | `domain/speed_dynamics.py` (`CarPhysics`, `physics_for`, `GripLapTimes`), `application/calibrate_car_physics.py` | `data/parameters/car-physics-v1.json` (`mu` e `C_L·A` estimados; demais campos `assumed`), ADR 0015 |
| Composto de largada | `application/run_grid_simulation.py` | `assumed-grid-starting-compound-v1` (MEDIUM para todos) |
| Impacto temporal do grid (**arquivado**, sem consumidor; #152) | `TOBEDEFINED/grid_start.py` (antes `domain/grid_start.py`, aplicado por `domain/race_simulation.py`) | `TOBEDEFINED/grid-start-v1.json` (antes `data/parameters/grid-start-v1.json`; `heuristic-grid-start-v1`) |
| Ligação ao grid | `application/run_grid_simulation.py` (`run_grid_simulation`; antes `run_detailed_grid_simulation`) | ritmo de reserva `ASSUMED_REFERENCE_PACE_MS_PER_KM` |
| Motor | `domain/race_simulation_2d.py` (`simulate_2d_race`); o `simulate_detailed_race` está arquivado em `TOBEDEFINED/race_simulation.py` | — |
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

**Efeito no tempo de volta do motor 2D (issue #139).** A tabela acima descreve
o papel de cada atributo; no motor 2D, três deles também mudam o envelope físico
do carro (`physics_for`, em `domain/speed_dynamics.py`), por ganhos heurísticos
versionados em `DRIVER_PHYSICS_GAINS_VERSION` (`driver-physics-gains-v2`):

| Atributo | Atua em | Ganho | Faixa dos arquétipos → tempo de volta (Mônaco) |
|---|---|---|---|
| `pace_offset_pct` | velocidade de reta e de curva | 2,0 | −0,60 a +0,40 → −1,0% a +0,7% |
| `composure` | velocidade de curva | 0,08 | 0,85 a 1,30 → +1,0% a −2,0% |
| `aggression` | uso de aderência na freada | 0,25 | 0,60 a 1,50 → +0,6% a −0,6% |

Os ganhos foram escolhidos, não medidos, para que nenhum atributo domine. Na
versão anterior (compostura 0,5 e freada 0,5) a compostura 1,30 valia −10,9% de
volta, dez vezes o ritmo, e o arquétipo conservador vencia todas as corridas
curtas. Em 18 corridas de distância completa (Bahrein, Mônaco e Zandvoort, 4
pilotos por arquétipo, atributos sorteados nas faixas) a posição média ficou em
6,6 (agressivo), 6,3 (equilibrado) e 6,6 (conservador). Esses números carregam
muito ruído de abandonos por contato (issue #174), então valem como indicação.

**Ruído de ritmo por volta.** `consistency_factor` atua no motor 2D desde a
issue #139: cada carro sorteia, uma vez por volta, um desvio de ritmo com
`sigma = lap_noise_ms × consistency_factor`, em que `lap_noise_ms` (253,7 ms) e
`lap_noise_skew` vêm de `model-v1.json`. O sorteio usa um fluxo próprio por
piloto (`lap-noise:<piloto>`), não ocorre em voltas neutralizadas e não existe
sem `model_parameters`. A escala é calibrada; multiplicá-la pelo atributo
fictício é hipótese, declarada em `assumptions` como `lap_pace_noise_2d`
(`lap-pace-noise-2d-v1`, origem `heuristic`). No painel de decomposição o
desvio aparece como a fatia "variação".

**Pneu: sem multiplicador.** A degradação de `model-v1.json` não foi escalada.
Em distância completa o pneu já pesa 2,4% a 2,6% do tempo de volta no fim do
stint em Mônaco e no Bahrein (0,85% em Zandvoort, de severidade 0,3), com uma a
duas paradas. Multiplicar a degradação por 2,5 levou a três paradas em Mônaco e
a quase seis no Bahrein. A elasticidade de `tyre_management_factor` (0,4)
também ficou como está: 0,7 e 1,0 não melhoraram o equilíbrio entre arquétipos.

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

No 2D, o [ADR 0014](adr/0014-consumo-e-desgaste-por-movimento.md) integra
combustível e desgaste por movimento. A estratégia recebe o desgaste
equivalente acumulado, separado da idade real. Não há segunda queima nem
desgaste adicional ao fechar a volta. Os fatores de consumo SC/VSC da tabela
abaixo continuam exclusivos do motor por volta; no 2D o esforço menor produz
a economia. Fórmulas e limites em [consumo-desgaste-dinamicos.md](consumo-desgaste-dinamicos.md).

A primeira troca obrigatória no 2D usa um orçamento de desgaste, com preferência
individual semeada de ±2 voltas equivalentes (`spatial-pit-planning-v1`). Assim,
o grid não precisa inteiro aguardar o último prazo comum para usar o segundo
composto. O prazo de segurança permanece, e decisões coincidentes continuam
possíveis. O motor por volta conserva sua política anterior.

No motor 2D, o [ADR 0012](adr/0012-percurso-espacial-de-pit-lane.md) substitui
a perda diluída por um percurso físico hipotético dos boxes. O carro entra
na próxima passagem pela entrada, percorre a polilinha a até 80 km/h, para
2,5 s no ponto de serviço e aguarda folga para retornar. Limite, serviço e
folga são injetáveis em `PitLaneParameters` e declarados como `assumed` no
resultado. A extensão em metros vem da escala do mock, não de uma medição
oficial da pit lane. `pit_loss_ms` só orienta a estratégia nesse modo: o
relógio cobra o deslocamento e o serviço, sem somar outra perda nem aplicar
desconto artificial de SC/VSC. Com combustível e `refuelling_allowed`, a
estratégia 2D também recebe a massa e a queima nominal por volta. No ponto de
serviço, pneus e combustível são tratados simultaneamente: a duração é o
máximo entre o serviço de pneus e a massa solicitada dividida pela vazão
assumida, limitada à capacidade disponível na chegada. Há marcha lenta durante
o serviço. A trajetória registra a variação de massa e o evento informa massa
inicial, massa adicionada e instante de conclusão. Uma troca gratuita sob
bandeira vermelha não abastece. Sem o modelo de pneus e parâmetros de boxes,
não há paradas no 2D.

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

As regras detalhadas a seguir descrevem o planejador por volta. No 2D, a
estratégia usa a queima nominal como estimativa, embora o consumo real seja
contínuo e limitado pela vazão de 2025 (ADR 0014). A carga inicial permanece
a do cenário, sem planejamento por piloto; os traços de combustível usam o
padrão neutro e estratégias explícitas não recebem uma parada de segurança.
A estimativa pode falhar e resultar em pane seca; não é uma previsão calibrada.

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

### Pista molhada: pneus de chuva (#120)

Código em `domain/wet_tyres.py` (`ASSUMED_WET_TYRES`,
`assumed-wet-tyres-v1`); decisão em `HeuristicPitStrategy._weather_switch`.

- **Aderência por composto.** Cada classe de pneu tem uma curva de aderência
  contra a água (slick 1,00 → 0,40; intermediário 0,93 → 0,58 com pico 0,81 na
  água 0,3; chuva 0,86 → 0,69). O carro paga a aderência da pista (ADR 0015)
  vezes a do seu pneu dividida pela do melhor composto para aquela água: com o
  pneu certo, nada a mais; slick em pista saturada tem 58% da aderência do
  pneu de chuva. Cruzamentos que emergem: slick → intermediário com água
  ~0,07; intermediário → chuva com ~0,4.
- **Decisão.** A cada volta o muro vê a água prevista para a volta que começa
  (radar). Se o pneu montado não é o melhor, a perda por volta
  (`volta de referência × (aderência relativa ** -0,6 − 1)`) vezes 8 voltas
  (ou o que resta) é comparada com a perda de boxes, barateada por SC/VSC e
  multiplicada pelo **viés do piloto** (`draw_weather_switch_bias`: 1 +
  0,6 × (agressividade − 1) + 0,2 × ruído, entre 0,5 e 2,0; o agressivo aposta
  mais tempo no pneu atual). Troca gratuita sob vermelha sempre vai para o
  pneu certo. Paradas por desgaste ou combustível com pista molhada montam o
  pneu de chuva indicado; com pneu de chuva montado não há parada por
  desgaste.
- **Regra de dois compostos** suspensa para todo o pelotão quando qualquer
  carro usou intermediário ou chuva. Uma troca solicitada só conta após o
  serviço nos boxes; uma troca gratuita conta quando realizada.
- **Largada.** MEDIUM no seco; se a água prevista ao fim da volta 1 pede pneu
  de chuva, todos largam com ele.
- **Desgaste.** Intermediário (20 ms/volta, vida 30) e chuva (15 ms/volta, vida
  35) são hipóteses no código (`ASSUMED_WET_COMPOUNDS`), fora do artefato
  calibrado da #40. Abaixo de água 0,1 superaquecem: desgaste até 4× (inter) e
  7× (chuva) com a pista seca.
- **Risco.** Acidente individual × (1 + 2 × água ÷ compostura) × (1 + 8 ×
  (1 − aderência relativa)); contato em disputa × (1 + água). A compostura do
  piloto serve como habilidade na chuva. Com 20 carros e 8 sementes em Mônaco,
  40 voltas: 1,6 abandonos por corrida no seco, 1,8 com chuva forte (voltas
  8-18) e 2,1 com garoa longa; paradas por carro sobem de 0,9 para 1,9.
- **No 2D** valem a mesma aderência, o mesmo desgaste e a mesma decisão; o
  contato espacial ainda não depende da água.

## 7. Volta de referência por circuito

`data/parameters/reference-laps-v1.json`: por corrida, a mediana das voltas
mais rápidas de cada piloto; por circuito, a mediana entre as corridas de 2022
a 2024. Exemplos: Mônaco 77,2 s; Spa 110,5 s; Monza 85,9 s. É histórico, não
heurístico, mas só fixa a escala de tempo da pista: não descreve pilotos.

Ordem de uso: tabela → comprimento da pista × 17.000 ms/km (reserva) → 90 s
(sem pista). A origem usada aparece em `assumptions`.

### 7.1 Voltas padrão da interface

O catálogo usa o máximo de voltas completadas na corrida mais recente do
circuito (`latest_observed_race`). Sem observação disponível, a regra
`assumed-distance-rule-v1` escolhe o menor inteiro de voltas cuja distância
excede 305 km, ou 260 km para o circuito Trotman `circuit:6` (Mônaco). Essa
origem é exposta como `assumed_distance_rule`; não é um valor calibrado.

Uma corrida recente encurtada por bandeira vermelha continua sendo a observação
escolhida. No fallback, o comprimento aproximado da geometria FastF1 também
pode deslocar o resultado em uma ou duas voltas.

### 7.2 Impacto da posição de largada (#108)

> **Arquivado em 2026-11-12 (#152).** `grid_start.py`, o adaptador
> `grid_start_parameters_json.py` e `grid-start-v1.json` estão em
> [`TOBEDEFINED/`](../TOBEDEFINED/README.md), sem consumidor desde a remoção do
> motor por volta; o 2D larga em filas de dois por física. O texto abaixo
> descreve o comportamento do motor por volta.

O coeficiente `grid_penalty_ms_per_position = 782,4 ms` continua sendo o valor
**calibrado** de `model-v1.json`. O motor detalhado multiplica esse coeficiente
uma única vez pelo fator **heurístico** 0,10 de `grid-start-v1.json`: o efeito
usado é 78,24 ms por posição (P20 começa 1.486,56 ms atrás da pole). A resposta
publica os três valores em `assumptions`; fator 1,0 reproduz os tempos e os
sorteios anteriores. O motor 2D não recebe a penalidade temporal: mantém o
grid escalonado (cada posição 10 m atrás da anterior, lados alternados), como
no grid real da F1. Filas lado a lado foram testadas e descartadas: geravam
contato artificial na largada (34 abandonos em 15 corridas de 2 voltas, contra
0 no escalonado).

Análise reproduzível:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  scripts/analyze_grid_start_sensitivity.py --races-per-track 40
```

Protocolo `grid-start-sensitivity-v1`: mesmas sementes (`1082026` em diante)
para cada fator; Spa (44 voltas), Interlagos (71) e Mônaco (78); três grids
sintéticos fixos de 20 carros (ritmo na ordem, top 5 misturado e P8 mais rápido).
São 360 corridas por fator. A média de P8 usa as 120 corridas do terceiro grid,
em que ele é exatamente 500 ms/volta mais rápido que a pole. “Ganha/igual/perde”
compara posição de largada e posição final para os 7.200 carros, inclusive
abandonos. É sensibilidade de uma hipótese, não calibração histórica.

| Fator | ms/posição | Vitória da pole | P8 médio final | Ganha | Igual | Perde |
|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 782,40 | 73,89% | 7,74 | 56,61% | 30,85% | 12,54% |
| 0,750 | 586,80 | 71,11% | 7,31 | 57,15% | 29,38% | 13,47% |
| 0,500 | 391,20 | 66,94% | 7,30 | 55,33% | 25,08% | 19,58% |
| 0,350 | 273,84 | 67,22% | 6,93 | 53,24% | 20,96% | 25,81% |
| 0,250 | 195,60 | 59,44% | 6,45 | 52,24% | 18,33% | 29,43% |
| 0,150 | 117,36 | 55,56% | 7,27 | 51,74% | 14,97% | 33,29% |
| **0,100** | **78,24** | **50,83%** | **5,86** | **50,54%** | **14,64%** | **34,82%** |
| 0,075 | 58,68 | 53,33% | 5,81 | 50,72% | 13,72% | 35,56% |
| 0,050 | 39,12 | 51,39% | 6,28 | 50,82% | 12,79% | 36,39% |
| 0,025 | 19,56 | 46,67% | 5,86 | 50,68% | 12,42% | 36,90% |
| 0,015 | 11,74 | 43,33% | 5,96 | 51,00% | 11,46% | 37,54% |
| 0,000 | 0,00 | 46,39% | 5,33 | 50,13% | 11,60% | 38,28% |

O alvo hipotético inicial era a pole vencer 40–45%. A tabela mostra que ele só
é atingido praticamente zerando a penalidade: com 360 corridas por fator, o erro
padrão é de cerca de 2,6 p.p., e os fatores de 0 a 0,10 ficam no mesmo patamar
(43–53%). O fator 0,10 foi escolhido pelo usuário em 2026-10-30 por manter um
efeito de largada perceptível (P20 a ~1,5 s) e já tirar a pole de 74% para ~51%;
a vantagem restante vem do modelo de ultrapassagem, tratado na issue #110. A
não monotonicidade é esperada: mudanças de ordem alteram disputas, contatos e
neutralizações apesar das sementes pareadas. O resultado caracteriza este
protocolo sintético e não transforma o fator em coeficiente calibrado.

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
| Impacto temporal da posição de largada (arquivado) | `grid_start_penalty_factor` em `TOBEDEFINED/grid-start-v1.json`; depois rode `scripts/analyze_grid_start_sensitivity.py` |

Ao mudar um valor: incremente o `parameter_version`, atualize o `rationale` e
esta página, e rode a suíte. Testes que dependem de valores exatos usam os
próprios parâmetros, não números fixos.

## 9. Limitações conhecidas

- **A pole ainda vence muito.** Depois da atenuação da #108 (fator 0,10), venceu
  ~51% da amostra sintética (§7.2); mesmo sem penalidade venceria ~46%. A causa
  restante é a ultrapassagem (bloqueio, disputas, `resistance_scale`), a revisar
  na issue #110. Nada disso é calibração histórica.
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
- **Limitações conhecidas do motor 2D** (registradas em 2026-11-12, sem decisão
  tomada): não reabastece nem faz lift-and-coast, e todos largam com a mesma
  carga de combustível; a assumption de gestão de pneus não é declarada em
  `assumptions`; abandono sem disputa vira `mechanical`; em `speed_breakdown`
  a troca de pneu aparece defasada uma volta em relação à parada.
- **Clima só no tempo de volta.** Água e borracha viram um fator de
  aderência (`domain/track_condition.py`, ADR 0015) que o motor físico
  converte em tempo pela geometria: pista saturada custa ~27% em Mônaco e
  ~19% em Monza com o pneu certo. Pneus de chuva, troca por clima e risco na
  chuva estão na seção 6 (#120). A temperatura do asfalto evolui e acelera a
  secagem, mas ainda não altera a aderência nem o desgaste (janela de
  operação a combinar com a #104); o contato espacial do 2D não depende da
  água.
- **Volta física com erro de ~4,7% por pista.** O carro de referência
  (`car-physics-v1.json`) reproduz a mediana das voltas de referência, mas
  Zandvoort (curvas inclinadas) e Losail saem ~11-12% lentas e Monza (chicanes
  que 240 pontos não resolvem) ~7% rápida.
- **Consequência de contato no 2D é assumida.** A versão
  `spatial-contact-severity-assumed-v2` exige encontro dos corpos projetados e
  avalia cada episódio uma vez. Até 2 m/s de aproximação normal relativa há
  apenas toque; dano e risco de abandono crescem com a gravidade. A margem de
  planejamento não causa abandono. Parâmetros, eventos e limitações estão em
  [contato e reprodução espacial](contato-e-reproducao-espacial.md); os limiares
  não foram calibrados contra acidentes reais. Resultados não são invariantes
  ao passo de integração.
- **Composto de largada fixo e médio quase sem volta.** Todos largam de MEDIUM
  no seco (hipótese; com chuva na volta 1, o pneu de chuva indicado). Enquanto a regra de dois compostos não foi cumprida, o médio fica
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
