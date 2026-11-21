# Revisão Final: Modelagem de Pilotos, Carros e Dinâmica de Corrida 2D

Este documento consolida a especificação, arquitetura, formulação matemática, regras desportivas e apresentação visual da **modelagem de atributos de pilotos e carros** no simulador de Fórmula 1.

---

## 1. Visão Geral e Princípios Arquiteturais

A modelagem de desempenho no simulador 2D combina dois pilares fundamentais: o **envelope físico do veículo** (potência, arrasto, aderência, teto de reta e aceleração longitudinal) e os **atributos de pilotagem e estilo** (ritmo, consistência, agressividade, firmeza sob pressão e gestão de pneus).

```text
 ┌────────────────────────────────┐         ┌────────────────────────────────┐
 │       ATRIBUTOS DO CARRO       │         │      ATRIBUTOS DO PILOTO       │
 │  v_max_kmh  (334 a 342 km/h)   │         │  pace_offset_pct  (-0.6 a +0.4)│
 │  a_max_ms2  (13.7 a 14.5 m/s²) │         │  consistency_factor (0.7 a 1.3)│
 │  grip_mu, power_kw, drag, mass │         │  aggression, composure, pneu  │
 └───────────────┬────────────────┘         └───────────────┬────────────────┘
                 │                                          │
                 └────────────────────┬─────────────────────┘
                                      ▼
                        ┌───────────────────────────┐
                        │      physics_for(...)     │
                        │ (Envelope Físico Efetivo) │
                        └─────────────┬─────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            ▼                                                   ▼
┌───────────────────────┐                           ┌───────────────────────┐
│     Dinâmica 2D       │                           │  Estratégia de Pit    │
│  accel_limit_ms2(v)   │                           │  stint_horizon_laps   │
│  corner_speed_ms(κ)   │                           │  strategy_offset_laps │
│  brake_limit_ms2(v)   │                           │  weather_switch_bias  │
└───────────────────────┘                           └───────────────────────┘
```

### Princípios do Modelo
* **Separação entre Carro e Piloto (ADR 0008 e ADR 0015):** Na Fórmula 1, o carro define o teto do que é fisicamente possível na pista; o piloto define quanto desse teto é extraído em frenagens, tangências, consistência e preservação de compostos.
* **Rotulagem Honesta (`assumed` e `heuristic`):** Os atributos não pretendem medir telemetria de indivíduos reais (o que violaria a honestidade metodológica). São perfis e parâmetros assumidos, rotulados com proveniência explícita e versões auditáveis (`assumed-driver-attributes-v3`, `driver-physics-gains-v3`).
* **Preservação de Determinismo e Reprodutibilidade:** Sementes aleatórias (`SeededRandomSource`) utilizam fluxos isolados e chaveados por ID de piloto (`attributes:car_perf:{driver_id}`, `strategy:offset:{driver_id}`). O sorteio de um piloto não altera o sorteio de outro.
* **Isolamento Hexagonal:** Os motores e modelos matemáticos (`driver_attributes.py`, `speed_dynamics.py`, `strategy.py`, `race_simulation_2d.py`) operam sem dependência de FastAPI ou Arcade.

---

## 2. Atributos do Piloto e seus Impactos Físicos

Cada piloto possui cinco atributos fundamentais, sorteados dentro das faixas do seu arquétipo (`aggressive`, `balanced` ou `conservative`) ou editados manualmente pelo usuário:

### 2.1. Formulação dos Efeitos

| Atributo | Significado | Faixa Típica | Onde Atua na Física |
| :--- | :--- | :---: | :--- |
| `pace_offset_pct` | Desvio percentual de ritmo | $[-0{,}60\%, +0{,}40\%]$ | Modula $v_{\max}$ e aderência em reta e curva via ganho $\text{PACE\_GAIN} = 2{,}0$. |
| `composure` | Firmeza / Compostura | $[0{,}85, 1{,}30]$ | Eleva a velocidade de contorno em curvas: $\text{corner\_grip\_use} \propto (\text{pace} \cdot \text{composure})^2$. |
| `aggression` | Agressividade ofensiva | $[0{,}60, 1{,}50]$ | Modula capacidade de frenagem tardia ($\text{brake\_grip\_use}$) e propensão a disputas/contatos. |
| `consistency_factor` | Regularidade volta a volta | $[0{,}70, 1{,}30]$ | Escala o ruído estocástico gaussiano ($\sigma = \text{lap\_noise\_ms} \times \text{consistency}$). |
| `tyre_management_factor` | Preservação de borracha | $[0{,}70, 1{,}35]$ | Multiplica o desgaste gerado a cada metro: $w_{\text{eff}} = w \cdot \text{factor}$. |

### 2.2. Efeito no Envelope Físico (`physics_for`)

A função `physics_for(attributes, base)` compõe o carro base com os multiplicadores do piloto:

$$\text{pace} = 1{,}0 - \left(\frac{\text{pace\_offset\_pct}}{100} \cdot 2{,}0\right)$$
$$\text{corner} = 1{,}0 + (\text{composure} - 1{,}0) \cdot 0{,}04$$
$$\text{brake} = 1{,}0 + (\text{aggression} - 1{,}0) \cdot 0{,}25$$

Resultando nas capacidades físicas:
$$v_{\text{straight}} = v_{\text{base}} \cdot \text{pace}$$
$$\text{corner\_grip\_use} = \text{base.corner\_grip\_use} \cdot (\text{pace} \cdot \text{corner})^2$$
$$\text{brake\_grip\_use} = \text{base.brake\_grip\_use} \cdot \text{brake}$$

---


## 3. Atributos Físicos do Carro: Velocidade Máxima e Aceleração

Anteriormente, todos os carros do grid utilizavam valores base idênticos ($v_{\max} = 330\text{ km/h}$, aceleração estática limitada a $\approx 7\text{ m/s}^2$). Para criar diferenciação realista de equipamento entre equipes e carros, introduziu-se a modelagem de limites contínuos por veículo:

### 3.1. Faixas de Desempenho

Os parâmetros base são sorteados de forma contínua e aleatória dentro das faixas limites:

* **Velocidade Máxima Base ($v_{\max}$):**
  $$v_{\text{max}} \in [334{,}0\text{ km/h}, 342{,}0\text{ km/h}]$$
  Representa o teto de reta em condições ideais sem arrasto induzido por asa extra.
* **Aceleração Máxima Base ($a_{\max}$):**
  $$a_{\text{max}} \in [13{,}70\text{ m/s}^2, 14{,}50\text{ m/s}^2] \quad (\approx 1{,}40\text{G a } 1{,}48\text{G})$$
  Representa a aceleração longitudinal máxima nas retomadas de baixa e média velocidade com aderência plena.

### 3.2. Curva de Aceleração Dinâmica (`accel_limit_ms2`)

A aceleração longitudinal do carro a uma velocidade instantânea $v$ é governada pela transição física entre **aderência dos pneus** (baixa velocidade), **potência do motor** (média e alta velocidade) e **arrasto aerodinâmico** ($v^2$):

$$a_{\text{eff}} = a_{\max} \cdot \left(\frac{\mu_{\text{pista}}}{1{,}3}\right)$$
$$a_{\text{potência}}(v) = \frac{P_{\text{motor}}}{\text{massa} \cdot \max(v, 1{,}0)}$$
$$a_{\text{arrasto}}(v) = \frac{1}{2} \rho_{\text{ar}} \frac{C_D \cdot A}{\text{massa}} \cdot v^2$$

$$\text{Aceleração Líquida}(v) = \max\Big(0{,}0, \, \min(a_{\text{eff}}, \, a_{\text{potência}}(v)) - a_{\text{arrasto}}(v)\Big)$$

* **Em pista molhada:** Se $\mu$ cai $50\%$, $a_{\text{eff}}$ é reduzida proporcionalmente para evitar destracionamento irreal.
* **Em alta velocidade:** O arrasto equilibra a potência quando $v \to v_{\max}$, zerando a aceleração de forma suave e contínua.

---

## 4. Estratégia de Paradas e Dispersão do Efeito Manada

Para evitar que múltiplos carros entrem na pit lane na mesma volta (o "efeito manada"), três correções e dinâmicas foram integradas:

### 4.1. Horizonte de Stint Realista (`_stint_horizon_laps`)
Anteriormente, o cálculo econômico de paradas comparava continuar no pneu atual versus parar projetando todas as voltas restantes até o final da prova (ex.: 70 voltas). Como o desgaste tem componente quadrático ($b \cdot \text{idade}^2$), essa fórmula previa perdas astronômicas e mandava todos pararem na volta 1 ou 3 por "cliff".

A decisão econômica agora calcula o custo sobre o **horizonte do stint** do composto:
$$\text{horizonte} = \max\big(1, \min(\text{voltas\_restantes}, \, \text{vida\_típica\_do\_composto})\big)$$

* Na Volta 1, ficar na pista custa $\approx 14\text{ s}$ de degradação, enquanto parar nos boxes custa $\approx 41\text{ s}$ (perda de box $+$ ritmo do pneu novo). **Ninguém para nas primeiras voltas.**

### 4.2. Offsets Estratégicos por Arquétipo (`_strategy_offset`)
A idade efetiva do pneu na decisão de box é deslocada pelo viés estratégico do piloto:
$$\text{idade\_decisão} = \max\big(0, \, \text{idade\_real} - \text{offset\_laps}\big)$$

* **Pilotos Agressivos (`aggressive`):** Recebem viés de antecipação ($\text{offset} \le -1$). Buscam a parada mais cedo para tentar o *undercut*.
* **Pilotos Equilibrados (`balanced`):** Seguem a janela nominal ($\text{offset} = 0$).
* **Pilotos Conservadores (`conservative`):** Recebem viés de extensão ($\text{offset} \ge +1$). Prolongam o stint para tentar o *overcut* com pneus conservados.
* O valor final é estritamente limitado dentro de $[-\text{amplitude}, +\text{amplitude}]$ para respeitar as invariantes de estratégia.

### 4.3. Viés Climático na Chuva (`weather_switch_bias`)
Na transição para chuva, o custo da parada é ponderado pelo viés de aposta do piloto:
* Pilotos agressivos possuem viés mais alto (apostam mais tempo em slicks esperando a pista secar).
* Pilotos conservadores possuem viés mais baixo (priorizam a segurança e entram nos boxes logo no início da precipitação).

---

## 5. Exibição e Interação no Frontend

### 5.1. Editor de Grid (`grid_editor.py` e `grid_view.py`)
A tabela de pilotos e o painel lateral de edição foram expandidos:
* Novas colunas na tabela:
  * `VMAX`: Velocidade máxima base em $\text{km/h}$ (ex.: `339`).
  * `AMAX`: Aceleração base em $\text{m/s}^2$ (ex.: `14.3`).
* No painel lateral, os botões `−` e `+` permitem incrementar ou decrementar esses valores em passos de $1\text{ km/h}$ e $0{,}1\text{ m/s}^2$.
* As edições são enviadas ao backend de forma atômica via requisição `PATCH /catalog/grid`.

### 5.2. Janela de Decomposição de Velocidade (`track_view.py`)
Ao clicar sobre um carro na visualização da pista, a janela flutuante exibe a telemetria ao vivo com duas seções limpas:
* **ATRIBUTOS DO PILOTO:** arquétipo, ritmo, compostura, agressividade, consistência e gestão de pneu.
* **ESTADO DO CARRO:** velocidade base ($v_{\max}$), aceleração base ($a_{\max}$), pneu atual, desgaste acumulado, aderência de superfície e combustível.

---

## 6. Endpoints da API

* `GET /catalog/grid`: Retorna as entradas do grid com os objetos `attributes` contendo `v_max_kmh` e `a_max_ms2`.
* `PATCH /catalog/grid`: Aceita modificações manuais de `v_max_kmh` e `a_max_ms2` através do schema `AttributeOverride`:
  ```json
  {
    "overrides": [
      {
        "driver_id": "driver:830",
        "v_max_kmh": 341.0,
        "a_max_ms2": 14.4
      }
    ]
  }
  ```
* `POST /catalog/grid/run`: Executa a simulação 2D alimentando o motor com os limites específicos de cada carro, publicando a telemetria completa em `speed_breakdown`.
