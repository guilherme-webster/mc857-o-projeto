# Modelagem heurística da corrida: referência

Este é o lugar para consultar **quais heurísticas o simulador usa, com que
valores e onde mudá-las**. O plano e o histórico das decisões estão no
[PRD](prds/modelagem-pilotos-heuristica.md); a decisão arquitetural está no
[ADR 0008](adr/0008-modelagem-heuristica-sobre-o-motor-calibrado.md).

Valores conferidos no código em 2026-10-03 (branch `67-modelagem-pilotos`).
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
| Volta de referência | `application/reference_laps.py`, `data/parameters/reference-laps-v1.json` | `historical-median-fastest-laps-v1` |
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
mesmo multiplicador vai para a estratégia de parada. O motor simples continua
usando o fator integral.

**Perfis nomeados.** 24 pilotos do grid de 2024 em
`configs/drivers/perfis-ficticios.json`, com arquétipo, alguns valores fixados
e uma frase de caracterização. Para mudar um piloto, edite o JSON: valores fora
da faixa do arquétipo são rejeitados.

O `POST /catalog/grid` em modo `random` sorteia pilotos de toda a história
(desde 1950); os perfis nomeados só entram num grid `manual` com os pares de
2024. Pilotos sem perfil nomeado recebem atributos sorteados do arquétipo.

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
| As faixas de um arquétipo | `ASSUMED_ARCHETYPES` em `domain/driver_attributes.py` (afeta também o motor simples) |
| Quanto pesa a gestão de pneus | `DETAILED_TYRE_MANAGEMENT.elasticity` em `domain/attribute_effects.py` |
| Dificuldade de ultrapassar | `resistance_scale` em `domain/disputes.py`, ou a dificuldade por circuito no `model-v1.json` |
| Frequência de SC/VSC/vermelha | `RaceControlParameters` em `domain/race_control.py`; depois meça com `scripts/race_control_frequency.py` |
| Quando os carros param | `HeuristicPitParameters` em `domain/strategy.py` |
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
- Contato não tem culpado nem dano parcial; o carro abandona ou segue.
- O clima existe (`domain/weather.py`, #69) mas ainda não afeta o tempo de volta
  nem os incidentes.
- A interface Arcade ainda não dispara corridas nem as reproduz volta a volta;
  `frontend/arcade/track_view.py` anima com velocidade constante. O
  `scripts/race_report.py --html` do motor calibrado tem um visualizador que
  pode servir de base.
