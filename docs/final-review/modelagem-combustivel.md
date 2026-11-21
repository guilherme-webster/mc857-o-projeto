# Revisão Final: Modelagem de Combustível, Massa e Reabastecimento

Este documento consolida a especificação, arquitetura, formulação matemática, regras desportivas e apresentação visual da **modelagem de combustível** no simulador 2D de Fórmula 1.

---

## 1. Visão Geral e Princípios Arquiteturais

A modelagem de combustível traduz a massa líquida de gasolina embarcada em cada carro em **efeitos inerciais contínuos sobre o tempo de volta e a velocidade**, além de governar o consumo dinâmico na pista, a tática de economia (*lift-and-coast*) e as paradas de reabastecimento.

### Princípios do Modelo
* **Origem Honesta (`calibrated` e `assumed`):** O dataset histórico principal (Trotman v128) não registra a massa de gasolina volta a volta. No entanto, o efeito conjunto de peso e queima no tempo de volta é empiricamente observável. A sensibilidade temporal (`lap_time_fraction_per_fuel_km`) foi calibrada no histórico das temporadas 2022–2023 e validada em 2024–2025. O consumo nominal ($0{,}3443\text{ kg/km}$), a reserva técnica ($1{,}0\text{ kg}$), a vazão de reabastecimento ($9{,}0\text{ kg/s}$) e os fatores de neutralização são hipóteses rotuladas como `assumed` (ADR 0009).
* **Consumo Dinâmico por Movimento (ADR 0014):** No motor 2D, a queima não é uma cota estática por volta. O consumo é integrado a cada subpasso de simulação ($\Delta t = 0{,}05\text{ s}$), sensível à velocidade de reta ao quadrado (arrasto aerodinâmico), à aceleração nas saídas de curva e à desaceleração nas frenagens (*coasting*).
* **Efeito Inverso ao Pneu:** Enquanto o desgaste do pneu piora progressivamente o carro ao longo do stint, o combustível queima e torna o veículo mais leve e rápido a cada volta.
* **Isolamento Hexagonal (ADR 0002):** A integração da massa e as decisões de abastecimento residem estritamente no domínio (`fuel.py`, `dynamic_usage.py`, `strategy.py`, `race_simulation_2d.py`). O frontend Arcade consome esses dados via telemetria contínua sem interferir na física.

---

## 2. Pipeline de Funcionamento

```text
 [ Carga Inicial / Box ]      [ Traçado e Curvatura ]      [ Estilo do Piloto ]
 (start_fuel / refuel)        (extensão / velocidade)      (agressividade / traços)
          │                              │                             │
          ▼                              ▼                             ▼
   ┌─────────────┐               ┌───────────────┐             ┌───────────────┐
   │ Massa Atual │               │ Dynamic Usage │             │  Aceleração/  │
   │  (fuel_kg)  │               │ (cruise/v²/a) │             │  Retomadas 2D │
   └──────┬──────┘               └───────┬───────┘             └───────┬───────┘
          │                              │                             │
          │                              └──────────────┬──────────────┘
          │                                             ▼
          │                                   [ Consumo do Subpasso ]
          │                                   (min: vazão 100 kg/h)
          │                                             │
          ▼                                             ▼
 [ Massa Efetiva ] ◄────────────────────────────────────┘
 (fuel_kg - reserva)
          │
          ▼
 [ Penalidade em Tempo ]
 (fuel_ms = ms_per_kg × massa)
          │
    ┌─────┴─────────────────────┐
    ▼                           ▼
[ speed_scale ]       [ Decisão de Parada ]
(fator de velocidade) (janela de box / pane)
```

---

## 3. Física da Massa e Penalidade no Tempo

O peso da gasolina impõe uma penalidade inercial contínua: acelerar um carro pesado exige mais trabalho do motor e freá-lo exige maior dissipação de energia.

### 3.1. Formulação Matemática
A penalidade temporal adicionada ao tempo de volta base é calculada por:

$$\Delta t_{\text{combustível}} = \text{ms\_per\_kg} \times \max(0{,}0, \; m_{\text{fim}} - m_{\text{reserva}})$$

Onde:
* $m_{\text{fim}}$ é a massa de combustível restante ao término da volta (`car.fuel_kg`);
* $m_{\text{reserva}}$ é a reserva mandatória de segurança da FIA ($1{,}0\text{ kg}$), necessária para permitir a coleta laboratorial de 1 litro de combustível após a corrida;
* $\text{ms\_per\_kg}$ é a sensibilidade temporal específica do circuito:
  $$\text{ms\_per\_kg} = \left(\frac{\text{lap\_time\_fraction\_per\_fuel\_km}}{\text{burn\_kg\_per\_km}}\right) \times t_{\text{referência}}$$

### 3.2. Magnitude Numérica Típica
* Para um circuito com volta de referência de $90\text{ s}$ ($90.000\text{ ms}$):
  $$\text{ms\_per\_kg} \approx \frac{1{,}271 \times 10^{-4}}{0{,}3443} \times 90.000 \approx 33{,}2\text{ ms/kg}$$
* **Início de Prova (Tanque Cheio ~100 kg):** O carro perde cerca de **$3{,}3\text{ segundos}$ por volta** unicamente pelo peso do combustível embarcado.
* **Fim de Prova (Tanque Vazio ~5 kg):** A perda cai para apenas **$0{,}16\text{ segundo}$ por volta**.

---

## 4. Consumo Dinâmico por Movimento 2D (ADR 0014)

O consumo em cada subpasso $\Delta t = 0{,}05\text{ s}$ depende do perfil real de deslocamento executado pelo carro:

### 4.1. Parcelas de Demanda do Motor
O esforço de tração é ponderado por:

$$\text{demanda} = \Delta s \times \left(w_{\text{cruzeiro}} + w_{\text{velocidade}} \cdot \left(\frac{v}{v_{\text{ref}}}\right)^2 + w_{\text{aceleração}} \cdot \frac{\max(0, a)}{a_{\text{ref}}}\right) + v_{\text{lenta}} \cdot \Delta t$$

1. **Arrasto Aerodinâmico em Velocidade ($50\%$):** Em altas velocidades nas retas, vencer a resistência do ar domina o consumo, crescendo quadraticamente com $v^2$.
2. **Potência de Cruzeiro ($20\%$):** Consumo basal de propulsão constante.
3. **Aceleração e Retomadas ($30\%$):** Retomar a aceleração plena ao sair de curvas lentas exige injeção intensa de combustível.
4. **Desaceleração e Freadas (*Coasting*):** Quando o carro desacelera forte ($a < -0{,}10\text{ m/s}^2$), o consumo de deslocamento é reduzido a **$10\%$** do valor normal.
5. **Marcha Lenta nos Boxes (*Idle*):** Mesmo parado trocando pneus na baia de pit stop, o motor ligado consome à taxa de marcha lenta ($v_{\text{lenta}} = 1{,}0\text{ m/s}$ equivalente).

### 4.2. Teto Regulamentar de Vazão da FIA
O simulador impõe o limite físico da FIA para o fluxo de combustível:
$$\text{consumo}_{\Delta t} \le \frac{100{,}0\text{ kg/h}}{3600\text{ s}} \times \Delta t \approx 0{,}0278\text{ kg/s} \times \Delta t$$

### 4.3. Normalização pelo Traçado
Para assegurar paridade com o modelo calibrado, o traçado integra previamente uma volta neutra padrão (`usage_reference`). A demanda instantânea é normalizada pelo índice de consumo do circuito, garantindo que em ritmo verde padrão o carro queime exatamente $\text{burn\_kg\_per\_km} \times \text{extensão}$.

---

## 5. Influência dos Pilotos: Física e Estratégia

O comportamento do piloto afeta o combustível tanto na mecânica do movimento quanto no plano tático da corrida:

### 5.1. Efeito na Física de Pilotagem
* **Sem Multiplicador Artificial:** O simulador não aplica um multiplicador artificial de agressividade sobre o consumo; o próprio estilo do piloto altera o movimento real do carro.
* **Pilotos Agressivos:** Retomam o acelerador com maior antecipação, geram maiores acelerações longitudinais e sustentam velocidades de reta superiores. Por consequência física, **consomem mais kg de combustível por volta**.
* **Pilotos Presos em Tráfego:** Reduzem a velocidade de reta e passam mais tempo em desaceleração, economizando combustível naturalmente.

### 5.2. Efeito na Decisão Estratégica (`FuelStrategyTraits`)
No início da prova, a agressividade do piloto sorteia traços estratégicos individuais (`draw_fuel_traits`):
* **Margem de Segurança no Tanque (`margin_laps`):**
  * Piloto conservador: exige chegar aos boxes com **$1{,}0\text{ a }1{,}5\text{ voltas}$** de folga no tanque.
  * Piloto agressivo: arrisca parar no limite, com apenas **$0{,}2\text{ volta}$** restante de gasolina.
* **Viés de Carga e Paradas (`stop_cost_bias`):**
  * Viés $< 1{,}0$ (agressivo): prefere correr com o carro leve e realizar mais paradas rápidas.
  * Viés $> 1{,}0$ (conservador): prefere carregar mais peso e evitar visitas aos boxes.
* **Deslocamento de Janela (`stint_shift`):** Antecipa (*undercut*) ou estica (*overcut*) o momento da parada.

---

## 6. Condições de Pista e Neutralizações

Quando a corrida é neutralizada pela direção de prova, o ritmo do pelotão diminui, gerando grande economia de combustível:

* **Safety Car (SC):** Fator de queima de **$0{,}5$** ($50\%$ de economia por volta).
* **Virtual Safety Car (VSC):** Fator de queima de **$0{,}6$** ($40\%$ de economia por volta).
* **Bandeira Vermelha (RED):** Fator de queima de **$0{,}5$** durante o retorno lento ao pit lane.


---

## 7. Regras do Cenário: Reabastecimento vs. Era Moderna

O simulador suporta dois regimes regulamentares via `refuelling_allowed`:

### 7.1. Modo com Reabastecimento Ligado (`refuelling_allowed = True`)
Adota a dinâmica da era 1994–2009 da Fórmula 1:
* **Carga de Largada Leve:** As equipes abastecem apenas a quantidade necessária para o primeiro stint planejado (`start_fuel_kg`), tornando os carros extremamente ágeis no início da prova.
* **Operação Simultânea nos Boxes:** A troca de pneus e o reabastecimento ocorrem em paralelo. O tempo parado é determinado pelo processo mais lento:
  $$\Delta t_{\text{estacionário}} = \max(0{,}0, \; t_{\text{abastecer}} - t_{\text{troca\_pneus}})$$
  Com vazão de $9{,}0\text{ kg/s}$ e tempo de troca de pneus de $2{,}5\text{ s}$, colocar até $22{,}5\text{ kg}$ não adiciona tempo extra à parada.
* **Tempo de Box por Equipe (`RefuelStopParameters`):** O deslocamento operacional de cada equipe modula o tempo de serviço.
* **Rede de Segurança (`must_pit`):** O motor verifica se a gasolina restante cobre a distância até a próxima entrada de boxes. Se a reserva não for suficiente, o carro é obrigado a entrar nos boxes imediatamente.

### 7.2. Modo sem Reabastecimento (`refuelling_allowed = False`)
Adota o regulamento moderno (2010+):
* **Tanque Único:** O carro larga com todo o combustível para a corrida inteira (respeitando o teto de $110{,}0\text{ kg}$). É estritamente proibido reabastecer nos boxes.
* **Economia por *Lift and Coast*:** Quando a gasolina não é suficiente para completar a prova, o piloto antecipa a desaceleração antes das frenagens:
  * Pode economizar até **$8\%$** do consumo da volta (`lift_coast_max_saving_fraction = 0.08`);
  * Cada kg economizado custa uma penalidade de tempo de **$1{,}5\text{ s}$** (`lift_coast_ms_per_kg_saved = 1500.0 ms`).
* **Abandono por Pane Seca:** Se o combustível esgotar completamente na pista, o carro abandona por falta de combustível (`ran_dry`).

---

## 8. Comportamento da Régua do Gráfico (Reta vs. Curva)

A decomposição de velocidade (`speed_breakdown`) no frontend calcula frações da velocidade máxima de reta ($v_{\text{max}} \approx 360\text{ km/h}$):

### 8.1. Por que a Porcentagem de Combustível Encolhe nas Curvas?
* **O peso físico da gasolina é o mesmo ao longo da volta:** A massa decresce monotonamente com a queima, sem oscilações bruscas.
* **Na Reta:** Não há limitação de raio de curva (`curva = 0%`). A perda inercial atua sobre o teto pleno de $360\text{ km/h}$, exibindo sua porcentagem integral (ex.: $-4{,}2\%$).
* **Na Curva Lenta:** O limite centrípeta da pista restringe a velocidade a $90\text{ km/h}$ (`curva = -75%`). A perda imposta pelo peso atua sobre o teto remanescente; expressa como fração da régua global de $360\text{ km/h}$, a fatia visual reduz para cerca de $-1{,}0\%$.
* **Evolução ao Longo da Prova:** Diferente do pneu (cuja penalidade só cresce), a fatia de combustível **diminui volta a volta**, refletindo a queima contínua da massa embarcada até a bandeirada.


---

## 9. Interface Gráfica e Apresentação Visual (HUD)

Na janela do Arcade (`TrackView`), o combustível é exibido em múltiplos pontos da interface:

```text
┌──────────────────────────────────────────────┐
│ Ricardo Rodríguez   260 km/h · 78%       [X] │
├──────────────────────────────────────────────┤
│ [██████████████████░░░░░░░░░░░░░░░░░░░░░░░░] │
│ [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] │
│                                              │
│ curva        -28.1%   acel/freio     +10.1%  │
│ pneu          -4.2%   combustível     -2.7%  │
│ clima         -1.3%   controle        -0.0%  │
│ variação      -0.4%   dano            -0.0%  │
├──────────────────────────────────────────────┤
│ ATRIBUTOS DO PILOTO                          │
│   arquétipo                      aggressive  │
│   ritmo                              -0.36%  │
│   compostura                           0.94  │
│   agressividade                        1.39  │
│   consistência                         1.37  │
│   gestão de pneu                       1.17  │
├──────────────────────────────────────────────┤
│ ESTADO DO CARRO                              │
│   velocidade base                  335 km/h  │
│   pneu atual                     MEDIUM (3v) │
│   desgaste do pneu               0.85 v eq.  │
│   aderência                           99.4%  │
│   combustível                       45.2 kg  │
└──────────────────────────────────────────────┘
```

1. **Na Seção `ESTADO DO CARRO`:**
   * A linha **`combustível: 45.2 kg`** reflete a massa líquida em tempo real interpolada a partir do movimento 2D.
2. **Na Barra de Decomposição (`speed_breakdown`):**
   * A fatia **`combustível`** quantifica a perda de velocidade de reta imposta pela inércia da massa atual.
3. **No Medidor de Combustível da Tabela (`_FUEL_GAUGE`):**
   * Uma barra retangular verde de $28\text{ px} \times 7\text{ px}$ é desenhada à esquerda da coluna de kg de cada piloto na tabela de classificação, escalada proporcionalmente ao teto de $110{,}0\text{ kg}$.
4. **No Feed de Mensagens / Logs da Corrida:**
   * Caso o carro precise parar por combustível, o log registra a causa exata em cor âmbar (`"PIT"`):
     * `V20  Box: Piloto X -> HARD (Nível crítico de combustível)`
     * `V28  Box: Piloto Y -> MEDIUM (Reabastecimento e parada planejada)`

---

## 10. Tabela Resumo dos Parâmetros

| Parâmetro | Valor Padrão | Origem | Descrição |
| :--- | :---: | :---: | :--- |
| `lap_time_fraction_per_fuel_km` | $1{,}271 \times 10^{-4}$ | Calibrado (Trotman v128) | Fração do tempo de volta perdida por km de combustível embarcado. |
| `burn_kg_per_km` | $0{,}3443\text{ kg/km}$ | Assumido (`fuel-v1`) | Consumo linear nominal em bandeira verde (~105 kg em 305 km). |
| `finish_reserve_kg` | $1{,}0\text{ kg}$ | Regulamentar FIA | Sobra obrigatória no tanque ao cruzar a linha de chegada. |
| `max_fuel_kg` | $110{,}0\text{ kg}$ | Regulamentar FIA | Capacidade máxima do tanque de combustível. |
| `max_fuel_flow_kg_h` | $100{,}0\text{ kg/h}$ | Regulamentar FIA | Teto de vazão do sensor de fluxo de combustível ($0{,}0278\text{ kg/s}$). |
| `fuel_speed_weight` | $0{,}50$ | Assumido (`dynamic-usage-v1`) | Peso do arrasto aerodinâmico proporcional a $v^2$ no consumo 2D. |
| `fuel_cruise_weight` | $0{,}20$ | Assumido (`dynamic-usage-v1`) | Peso da velocidade de cruzeiro constante no consumo 2D. |
| `fuel_acceleration_weight` | $0{,}30$ | Assumido (`dynamic-usage-v1`) | Peso da aceleração longitudinal positiva no consumo 2D. |
| `fuel_coasting_fraction` | $0{,}10$ | Assumido (`dynamic-usage-v1`) | Redução de consumo durante frenagem e desaceleração severa. |
| `idle_equivalent_speed_ms` | $1{,}0\text{ m/s}$ | Assumido (`dynamic-usage-v1`) | Taxa equivalente de consumo em marcha lenta na baia de pit stop. |
| `refuel_rate_kg_per_s` | $9{,}0\text{ kg/s}$ | Assumido (`fuel-v1`) | Vazão do equipamento de reabastecimento de alta pressão (era 1994–2009). |
| `tyre_change_ms` | $2500{,}0\text{ ms}$ | Assumido (`fuel-v1`) | Duração da troca de pneus realizada em paralelo com reabastecimento. |
| `sc_burn_factor` | $0{,}50$ | Assumido (`fuel-v1`) | Fator de queima sob Safety Car ($50\%$ do consumo verde). |
| `vsc_burn_factor` | $0{,}60$ | Assumido (`fuel-v1`) | Fator de queima sob Virtual Safety Car ($60\%$ do consumo verde). |
| `red_flag_burn_factor` | $0{,}50$ | Assumido (`fuel-v1`) | Fator de queima sob bandeira vermelha no retorno lento aos boxes. |
| `lift_coast_max_saving_fraction` | $0{,}08$ | Assumido (`fuel-v1`) | Máxima economia da volta por *lift-and-coast* ($8\%$). |
| `lift_coast_ms_per_kg_saved` | $1500{,}0\text{ ms/kg}$ | Assumido (`fuel-v1`) | Custo temporal para cada kg economizado por *lift-and-coast*. |

