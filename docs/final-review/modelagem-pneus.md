# Revisão Final: Modelagem de Pneus, Desgaste Dinâmico e Estratégia

Este documento consolida a especificação, arquitetura, formulação física, regras desportivas e apresentação visual da **modelagem de pneus** no simulador 2D de Fórmula 1.

---

## 1. Visão Geral e Princípios Arquiteturais

A modelagem de pneus conecta o contato mecânico do carro com o solo, a degradação física de borracha ao longo do tempo, a resposta a variações climáticas e a tomada de decisão estratégica de pit stops.

### Princípios do Modelo
* **Origem Honesta (`calibrated` e `assumed`):** O dataset histórico (Trotman v128) registra as paradas de box, mas não o composto montado em cada volta. A magnitude média da degradação foi calibrada a partir dos stints históricos reais, enquanto a separação dos compostos (`SOFT`, `MEDIUM`, `HARD`) e os pneus de chuva (`INTERMEDIATE`, `WET`) são hipóteses assumidas do grupo (ADR 0008 e ADR 0015).
* **Desgaste por Movimento (ADR 0014):** O pneu não envelhece por mera contagem de voltas fechadas na linha de chegada. O motor 2D acumula desgaste mecânico contínuo a cada subpasso de tempo ($\Delta t = 0{,}05\text{ s}$), sensível à distância, à força centrípeta nas curvas e às frenagens/acelerações.
* **Desacoplamento Hexagonal (ADR 0002):** O cálculo físico do desgaste e a estratégia de troca residem no núcleo de domínio (`tyres.py`, `dynamic_usage.py`, `strategy.py`, `race_simulation_2d.py`). O frontend Desktop em Arcade (`track_view.py`, `speed_breakdown.py`, `race_playback.py`) apenas consome e exibe essas variáveis sem alterar as regras físicas.

---

## 2. Pipeline de Funcionamento

```text
[ Estilo do Piloto ]      [ Traçado e Curvatura ]      [ Água na Pista ]
(gestão de pneus)         (força centrípeta v²·κ)      (surface_water)
        │                            │                        │
        ▼                            ▼                        ▼
 ┌───────────────┐           ┌───────────────┐        ┌───────────────┐
 │ tyre_mgmt     │           │ Dynamic Usage │        │ Wet Tyres     │
 │ factor (0.7x) │           │ (lat/long/dist)│       │ (relative_grip│
 └───────┬───────┘           └───────┬───────┘        │  overheating) │
         │                           │                └───────┬───────┘
         └─────────────┬─────────────┘                        │
                       ▼                                      │
            [ Desgaste Contínuo ]                             │
           (car.tyre_wear_laps)                               │
                       │                                      │
                       ▼                                      ▼
            [ Penalidade em Tempo ] ◄─────────────────────────┘
              (tyre_ms por composto)
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
  [ speed_scale ]            [ Decisão Estratégica ]
  (fator de velocidade 2D)   (janela de box / parada)
```

---

## 3. Os Compostos e Suas Características

O simulador suporta cinco compostos divididos em duas famílias:

### 3.1. Família Slick (Pista Seca)
* **`SOFT` (Macio):** Composto mais veloz quando novo (`pace_offset_ms = -450 ms`), porém com alta taxa de degradação linear e quadrática. Vida útil típica: ~14 voltas.
* **`MEDIUM` (Médio):** Composto de referência da categoria (`pace_offset_ms = 0 ms`). Vida útil típica: ~22 voltas.
* **`HARD` (Duro):** Composto mais lento no início do stint (`pace_offset_ms = +450 ms`), mas extremamente resistente à degradação. Vida útil típica: ~37 voltas.

#### Formulação da Penalidade de Composto Seco
A penalidade em tempo adicionada ao tempo de volta ideal é dada por:

$$\Delta t_{\text{tyre}} = \text{pace\_offset} + (a \cdot w + b \cdot w^2) \cdot \text{tyre\_severity}$$

Onde:
* $w$ é o desgaste contínuo equivalente (`car.tyre_wear_laps`);
* $a$ é o coeficiente de degradação linear (`degradation_ms_per_lap`);
* $b$ é o coeficiente quadrático (`degradation_ms_per_lap2`), que modela a queda abrupta de aderência (*cliff*);
* $\text{tyre\_severity}$ é o índice de severidade abrasiva do circuito.

### 3.2. Família de Chuva (Pista Molhada)
* **`INTERMEDIATE` (Intermediário):** Projetado para asfalto úmido ou chuva leve.
* **`WET` (Chuva Extrema):** Projetado para lâmina de água alta e chuva torrencial.

#### Aderência Absoluta e Cruzamentos (Crossovers)
A aderência varia com a lâmina d'água ($w_{\text{water}} \in [0, 1]$):
* **Pista Seca ($w = 0{,}0$):** Slick = 1,00; Intermediário = 0,93; Chuva = 0,86.
* **Pista Saturada ($w = 1{,}0$):** Slick = 0,40; Intermediário = 0,58; Chuva = 0,69.
* **Ponto de Cruzamento Slick $\to$ Intermediário:** Ocorre com água em torno de $0{,}07$ (7% de saturação).
* **Ponto de Cruzamento Intermediário $\to$ Chuva:** Ocorre com água em torno de $0{,}39$ (39% de saturação).

#### Superaquecimento no Seco
Pneus com sulcos de chuva rodando em asfalto com água abaixo de $0{,}1$ sofrem superaquecimento severo:
$$\text{fator de desgaste} = 1 + \text{ganho} \cdot \frac{0{,}1 - w_{\text{water}}}{0{,}1}$$
O ganho é de **3,0x para Intermediário** e **6,0x para Chuva**, destruindo a borracha rapidamente se a pista secar.

---

## 4. Física do Desgaste por Movimento (ADR 0014)

O desgaste contínuo não é linear com o tempo nem com a volta. Em cada intervalo $\Delta t$, o movimento efetivo gera um incremento de desgaste $\Delta w$:

$$\Delta w = (w_{\text{dist}} + w_{\text{lat}} + w_{\text{long}}) \cdot \text{fator de gestão}$$

### 4.1. Parcelas de Esforço Físico
1. **Desgaste por Distância (Peso 30%):**
   * Esforço base de rolamento contínuo sobre o asfalto:
     $$w_{\text{dist}} = \Delta s \cdot 0{,}30$$
2. **Desgaste por Carga Lateral (Peso 55%):**
   * Aceleração centrípeta real derivada da velocidade instantânea e da curvatura geométrica local da pista $\kappa(s)$:
     $$a_{\text{lat}} = \min(v^2 \cdot \kappa(s), \; 6{,}0\,g)$$
     $$w_{\text{lat}} = \Delta s \cdot 0{,}55 \cdot \frac{a_{\text{lat}}}{a_{\text{ref\_lat}}}$$
   * Curvas de alta velocidade gastam ordens de magnitude mais borracha que retas.
3. **Desgaste Longitudinal (Peso 15%):**
   * Frenagens intensas e tração pesada:
     $$w_{\text{long}} = \Delta s \cdot 0{,}15 \cdot \frac{\min(|a|, a_{\text{max\_long}})}{a_{\text{ref\_long}}}$$
   * Na via dos boxes, as parcelas lateral e longitudinal são zeradas.

### 4.2. Normalização por Volta Limpa
Para não cobrar a severidade do circuito duas vezes, o traçado calcula previamente uma volta estacionária de referência (`usage_reference`). O desgaste bruto é dividido pelo índice médio do circuito, garantindo que um piloto neutro consuma exatamente $1{,}0$ volta equivalente ao completar uma volta limpa padrão.

---

## 5. Atributos do Piloto: Gestão de Pneus

Cada piloto possui o atributo `tyre_management_factor` sorteado a partir de seu arquétipo:
* **Faixas Típicas:** Conservador ($0{,}65$ a $0{,}90$), Equilibrado ($0{,}90$ a $1{,}10$) e Agressivo ($1{,}15$ a $1{,}45$).
* **Elasticidade Amortecida (0,70):** Para evitar que a gestão de pneus anule a vantagem de ritmo nas retas, o simulador aplica amortecimento (`detailed-tyre-management-v2`):
  $$\text{fator efetivo} = 1 + 0{,}70 \cdot (\text{tyre\_management\_factor} - 1)$$
  A faixa efetiva de desgaste varia entre **$0{,}755\times$** (piloto poupador) e **$1{,}315\times$** (piloto gastador).

### Consequências na Prova
* Pilotos conservadores estendem a vida do pneu, evitam a perda precoce de ritmo e podem realizar uma corrida com **uma parada a menos** nos boxes.
* Pilotos agressivos aceleram a degradação, forçando trocas prematuras de pneus.

---

## 6. Impacto no Ritmo e Conversão para Velocidade

A cada subpasso de simulação, as penalidades em tempo são convertidas no fator de velocidade instantânea do veículo (`speed_scale`):

### 6.1. Cálculo do `speed_scale`
$$t_{\text{total}} = t_{\text{base}} + \Delta t_{\text{tyre}} + \Delta t_{\text{combustível}} + \Delta t_{\text{clima}} + \Delta t_{\text{ruído}}$$
$$\text{speed\_scale} = \frac{t_{\text{base}}}{t_{\text{total}}}$$

A velocidade máxima do envelope físico do carro é multiplicada por esse fator ao longo de toda a pista.

### 6.2. Atribuição Correta entre Pneu e Clima
* **Perda da Pista (`weather_ms`):** Perda de tempo decorrente do asfalto molhado supondo o uso do pneu adequado para a lâmina de água.
* **Perda do Pneu (`tyre_ms`):** Inclui o desgaste contínuo e a perda de aderência adicional por escolha incorreta de composto (`relative_grip`).
  * Se um carro utilizar pneus de pista seca na chuva, a perda severa de aderência é atribuída à fatia do **pneu**, evidenciando graficamente a necessidade de parada nos boxes.


---

## 7. Comportamento da Régua do Gráfico (Reta vs. Curva)

Uma característica importante do sistema de decomposição de velocidade (`speed_breakdown`) é como as porcentagens são apresentadas visualmente na interface:

### 7.1. A Régua Global de $v_{\text{max}}$
As fatias da barra de telemetria somam $100\%$ da velocidade máxima de reta do veículo ($v_{\text{max}} \approx 330\text{ a }360\text{ km/h}$):
$$\text{Efetiva} + \text{Acel/Freio} + \text{Curva} + \text{Pneu} + \text{Combustível} + \text{Clima} + \text{Variação} + \text{Dano} = 100\%$$

### 7.2. Por que a Porcentagem do Pneu Oscila na Mesma Volta?
* **O desgaste físico real só aumenta:** O contador contínuo `car.tyre_wear_laps` é estritamente não-decrescente durante todo o stint.
* **Na Reta:** Não há limitação geométrica (`curva = 0%`). O teto disponível é de $100\%$. O pneu retira sua fração integral sobre a velocidade máxima (ex.: $-4{,}2\%$).
* **Na Curva Lenta:** O raio da curva obriga o carro a reduzir para $90\text{ km/h}$, consumindo $75\%$ do teto total (`curva = -75%`). A velocidade restante disponível é de apenas $90\text{ km/h}$. A perda imposta pelo pneu atua sobre o que sobrou; convertida em fração da régua total de $360\text{ km/h}$, a fatia visual reduz para $-1{,}1\%$.
* **Ao retornar à reta:** A curva zera novamente e a porcentagem do pneu retorna ao seu valor integral, ligeiramente maior devido ao desgaste acumulado durante a curva.

O mesmo comportamento ocorre com o combustível (que também reduz nas curvas e cresce nas retas). Por outro lado, o **clima** faz o oposto: expande na curva (onde o atrito $\mu$ mais custa) e reduz nas retas.

---

## 8. Estratégia de Corrida e Regras Desportivas

O módulo de estratégia (`strategy.py`) monitora a integridade dos pneus e as regras do campeonato:

### 8.1. Regra de Dois Compostos Secos Distintos (ADR 0008)
Em corridas secas, o regulamento da FIA exige a utilização de pelo menos **dois compostos secos distintos** (ex.: Médio $\to$ Duro ou Macio $\to$ Médio).
* O agendamento da parada obrigatória é planejado pelo desgaste equivalente (`compulsory_wear_target_laps`), garantindo que o piloto cumpra a regra antes da janela final da prova.

### 8.2. Suspensão da Regra em Pista Molhada
Caso qualquer pneu de chuva (`INTERMEDIATE` ou `WET`) seja utilizado durante a corrida (`wet_compound_used`), a exigência de usar dois compostos secos distintos é automaticamente revogada pela direção de prova.

### 8.3. Ações no Atendimento de Box
Ao atingir a baia de serviço nos boxes:
* O desgaste mecânico é zerado: `car.tyre_wear_laps = 0.0`;
* A idade nominal do jogo é reiniciada: `tyre.age_laps = 0`;
* O composto montado passa a ser o novo jogo selecionado;
* A duração da parada segue o sorteio contínuo no intervalo $[2{,}2\text{ s}, 2{,}8\text{ s}]$, modulado pela eficiência da equipe (`execution`).


---

## 9. Interface Gráfica e Apresentação Visual (HUD)

O painel de decomposição da velocidade (`TrackView`) organiza os dados do veículo em duas seções bem definidas:

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

* **Seção ATRIBUTOS DO PILOTO:** Informa exclusivamente os traços individuais de pilotagem (arquétipo, ritmo, compostura, agressividade, consistência e gestão de pneu).
* **Seção ESTADO DO CARRO:** Informa a telemetria física do veículo:
  * `velocidade base`: Teto de velocidade na reta;
  * `pneu atual`: Composto e voltas completadas (`age_laps`);
  * `desgaste do pneu`: Desgaste contínuo acumulado em voltas equivalentes de carga (`tyre_wear_laps`), permitindo acompanhar a degradação física estritamente crescente;
  * `aderência`: Aderência efetiva instantânea na pista;
  * `combustível`: Massa restante de combustível a bordo.

---

## 10. Tabela Resumo dos Parâmetros

| Parâmetro | Valor Padrão | Origem | Descrição |
| :--- | :---: | :---: | :--- |
| `tyre_distance_weight` | $0{,}30$ | Assumido (`dynamic-usage-v1`) | Peso do rolamento por distância no desgaste contínuo. |
| `tyre_lateral_weight` | $0{,}55$ | Assumido (`dynamic-usage-v1`) | Peso da aceleração centrípeta em curvas no desgaste contínuo. |
| `tyre_longitudinal_weight` | $0{,}15$ | Assumido (`dynamic-usage-v1`) | Peso de frenagem e tração intensa no desgaste contínuo. |
| `max_lateral_g` | $6{,}0\,g$ | Assumido | Teto físico para aceleração lateral na estimativa de desgaste. |
| `tyre_management_elasticity` | $0{,}70$ | Heurístico (`detailed-tyre-management-v2`) | Amortecimento do fator de gestão de pneus do piloto. |
| `overheat_water` | $0{,}10$ | Assumido (`wet-tyres-v1`) | Limiar de lâmina d'água abaixo do qual pneus de chuva superaquecem. |
| `intermediate_overheat_gain`| $3{,}0\times$ | Assumido (`wet-tyres-v1`) | Multiplicador de desgaste do pneu Intermediário em pista secando. |
| `wet_overheat_gain` | $6{,}0\times$ | Assumido (`wet-tyres-v1`) | Multiplicador de desgaste do pneu Wet em pista secando. |
| `service_time_s` | $[2{,}2\text{ s}, 2{,}8\text{ s}]$ | Heurístico calibrado | Intervalo contínuo base para troca de pneus nos boxes. |

