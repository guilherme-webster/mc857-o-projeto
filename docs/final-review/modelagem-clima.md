# Revisão Final: Modelagem Climática da Corrida

Este documento consolida a especificação, arquitetura, fórmulas matemáticas e comportamento da **modelagem climática** no simulador de Fórmula 1.

---

## 1. Visão Geral e Princípios

A modelagem climática traduz condições meteorológicas definidas pelo usuário em **efeitos físicos contínuos** sobre a aderência da pista, o comportamento dos pneus, o ritmo dos carros, as decisões estratégicas de box e os incidentes da corrida.

### Princípios do Modelo
* **Origem Honesta (`assumed`):** O dataset histórico principal (Trotman v128) não contém dados de clima/pneus, e o FastF1 fornece apenas ocorrência booleana (`rainfall`). Portanto, a intensidade de chuva é prescrita pelo usuário no cenário, e todos os coeficientes são rotulados como `assumed` (hipóteses plausíveis de ordem de grandeza, versionadas no código).
* **Entrada Discreta, Evolução Contínua:** O usuário define a chuva por blocos de volta, mas o estado da pista (água, temperatura, umidade e borracha) evolui continuamente a cada tick do motor 2D ($\Delta t = 0{,}2\text{ s}$).
* **Física Específica por Pista:** A aderência afeta curvas e frenagens ($\mu$), mas não a reta. O motor calcula o impacto no tempo de volta a partir da geometria real de cada circuito (`GripLapTimes`), de modo que pistas sinuosas (como Mônaco) percam mais tempo na chuva do que pistas de alta velocidade (como Monza).

---

## 2. Pipeline de Funcionamento (Diagrama de Blocos)

```mermaid
flowchart LR
    classDef mainBlock fill:#141a24,stroke:#00d2ff,stroke-width:2px,color:#fff,text-align:left;
    classDef subItem fill:#1a2332,stroke:#2a3b52,stroke-width:1px,color:#c8d6e5,text-align:left;
    classDef noteBlock fill:#1f2937,stroke:#ff9f43,stroke-width:1px,color:#ff9f43,text-align:center;

    subgraph B1 ["1. ENTRADA DO CENÁRIO"]
        direction TB
        E1["• Níveis: Seco / Leve / Intensa"]:::subItem
        E2["• Prescrição por blocos de volta"]:::subItem
        E3["Hipótese assumida<br/>(Sem dados históricos detalhados)"]:::noteBlock
    end
    B1:::mainBlock

    subgraph B2 ["2. EVOLUÇÃO POR TICK"]
        direction TB
        P1["• Água na Pista (acumula / seca)"]:::subItem
        P2["• Umidade do Ar (modula evaporação)"]:::subItem
        P3["• Temperatura da Pista (esfria na chuva)"]:::subItem
        P4["• Borracha (deposição / lavagem)"]:::subItem
    end
    B2:::mainBlock

    subgraph B3 ["3. ADERÊNCIA E PNEUS"]
        direction TB
        A1["• Grip Efetivo (Água × Borracha)"]:::subItem
        A2["• Composto (Slick / Inter / Wet)"]:::subItem
        A3["• Superaquecimento no Seco"]:::subItem
    end
    B3:::mainBlock

    subgraph B4 ["4. IMPACTO NA CORRIDA"]
        direction TB
        I1["• Largada Inteligente na Chuva"]:::subItem
        I2["• Janela e Decisão de Box"]:::subItem
        I3["• Risco de Rodada Solo (Acidente)"]:::subItem
    end
    B4:::mainBlock

    B1 --> B2 --> B3 --> B4
```

---

## 3. Evolução Contínua da Pista (`LiveTrackCondition`)

A cada passo temporal de integração ($\Delta t = 0{,}2\text{ s}$), a classe `LiveTrackCondition` avança o estado do asfalto com base na fração de tempo decorrida:

$$\text{tempo em minutos} = \frac{\Delta t}{60}$$

### 3.1. Água Superficial ($\text{surface\_water} \in [0, 1]$)
* **Aporte de Chuva:**
  * Seco (`dry`): $+0{,}00 / \text{volta de referência}$
  * Chuva leve (`light_rain`): $+0{,}12 / \text{volta de referência}$
  * Chuva intensa (`heavy_rain`): $+0{,}30 / \text{volta de referência}$
* **Drenagem Natural:** $-0{,}03 / \text{volta de referência}$ (constante).
* **Evaporação:** $-0{,}06 / \text{volta de referência}$, modulada pela umidade e temperatura.
* **Dinâmica:** A água sobe progressivamente durante a chuva e seca de forma gradual após a tempestade.

### 3.2. Umidade Relativa do Ar ($\text{humidity\_pct} \in [0, 100]\%$)
Aproxima-se com inércia exponencial de um alvo fixo por nível de chuva:
* Seco: alvo de $50\%$
* Chuva leve: alvo de $75\%$
* Chuva intensa: alvo de $90\%$
* **Efeito:** Ar úmido desacelera a evaporação da água da pista pelo termo $(1 - \text{umidade}/100)$.

### 3.3. Temperatura do Asfalto ($\text{track\_temp\_c}$)
* O asfalto seco tende a $35\text{ °C}$ (`dry_track_temp_c`).
* A água resfria a pista até $23\text{ °C}$ quando saturada ($35 - 12 \times \text{água}$), com constante de tempo de $10\text{ min}$.
* **Efeito na Secagem:** Multiplica a evaporação por $\text{evaporation\_scale} = \text{clamp}(1 + 0{,}03 \times (T - 30), 0{,}3, 2{,}0)$. Pista fria demora mais para secar.

### 3.4. Emborrachamento da Linha Ideal ($\text{rubber} \in [0, 1]$)
* Começa em $0{,}8$ (asfalto já condicionado no início da corrida).
* O tráfego do pelotão deposita borracha, recuperando $8\%$ do que falta por volta.
* A chuva forte lava a camada de borracha (remove até $30\%$ por volta saturada).
* Pista virgem ($\text{rubber} = 0$) perde $3\%$ de aderência em relação à pista totalmente emborrachada ($\text{rubber} = 1{,}0$).


---

## 4. Aderência da Pista e do Carro

### 4.1. Fator de Aderência da Pista (`grip_factor`)
$$\text{grip\_pista} = \text{fator\_água}(\text{água}) \times \text{fator\_borracha}(\text{borracha})$$

* **Fator de Borracha:**
  $$\text{fator\_borracha} = 1{,}0 - 0{,}03 \times (1{,}0 - \text{rubber})$$
* **Fator de Água (com o pneu adequado):**
  * Pista seca ($\text{água} = 0{,}0$): $\text{fator} = 1{,}00$ ($100\%$)
  * Pista úmida ($\text{água} = 0{,}3$): $\text{fator} = 0{,}81$ (âncora de pneu intermediário)
  * Pista saturada ($\text{água} = 1{,}0$): $\text{fator} = 0{,}69$ (âncora de pneu de chuva extrema)

### 4.2. Aderência do Composto e Aderência Efetiva (`relative_grip`)
Cada classe de pneu possui uma curva de atrito absoluto contra a água:

| Nível de Água | Slick (`SLICK`) | Intermediário (`INTERMEDIATE`) | Chuva Extrema (`WET`) | Melhor Composto |
| :---: | :---: | :---: | :---: | :---: |
| **0% (Seco)** | **1,00** | 0,93 | 0,86 | **SLICK** |
| **10%** | **0,86** | 0,905 | 0,85 | **INTERMEDIATE** |
| **30% (Úmido)** | 0,62 | **0,81** | 0,79 | **INTERMEDIATE** |
| **60%** | 0,48 | 0,70 | **0,745** | **WET** |
| **100% (Saturado)** | 0,40 | 0,58 | **0,69** | **WET** |

* **Pontos de Cruzamento (Crossover):**
  * `SLICK` $\rightarrow$ `INTERMEDIATE`: em $\approx 7\%$ de água.
  * `INTERMEDIATE` $\rightarrow$ `WET`: em $\approx 39\%$ de água.
* **Aderência Efetiva no Carro:**
  $$\text{aderência\_efetiva} = \text{grip\_pista} \times \frac{\text{atrito\_absoluto}(\text{pneu atual}, \text{água})}{\text{atrito\_absoluto}(\text{melhor pneu}, \text{água})}$$

### 4.3. Superaquecimento de Pneus de Chuva no Seco
Quando a pista seca ($\text{água} < 0{,}1$), pneus de chuva superaquecem e sofrem um multiplicador na penalidade de tempo:
$$\text{multiplicador} = 1{,}0 + \text{ganho} \times \frac{0{,}1 - \text{água}}{0{,}1}$$
* Intermediário: ganho $3{,}0 \implies$ até **$4\times$** de penalidade no asfalto seco.
* Chuva Extrema: ganho $6{,}0 \implies$ até **$7\times$** de penalidade no asfalto seco.

---

## 5. Dinâmica de Corrida e Estratégia

1. **Largada Inteligente:** Se a previsão da volta 1 apontar pista molhada, todos os carros já largam com o composto de chuva indicado (`INTERMEDIATE` ou `WET`).
2. **Suspensão de Regras:** O uso de qualquer pneu de chuva suspende a obrigatoriedade de utilizar dois compostos secos distintos.
3. **Decisão de Parada nos Boxes (`_weather_switch`):**
   * Avaliada no início de cada volta com horizonte de até $8$ voltas.
   * Compara a perda acumulada por usar o pneu errado contra o custo da parada ($\text{pit\_loss\_ms} \times \text{pit\_loss\_factor} \times \text{viés\_piloto}$).
   * Neutralizações (SC/VSC) reduzem o custo da parada, e Bandeira Vermelha permite troca gratuita instantânea.
4. **Acidente Solo na Chuva (`weather_crash`):**
   * A cada fim de volta com água, sorteia chance de rodada sozinho:
     $$\text{risco} = 0{,}0008 \times \text{água} \times \left(1 + \frac{2 \cdot \text{água}}{\text{compostura}}\right) \times \bigl(1 + 8 \cdot (1 - \text{relative\_grip})\bigr)$$
   * O risco dispara com pneu errado e é atenuado pela **compostura** do piloto. Abandonos solo podem acionar SC, VSC ou Bandeira Vermelha.

---

## 6. Interface e Visualização (Frontend Arcade)

* **Cabeçalho da Pista (Topo Direito):**
  Exibe a condição meteorológica contínua por tick:
  * Exemplo Seco: `Seco · pista 35 °C · umidade 50% · borracha 97%`
  * Exemplo Chuva: `Chuva leve · agua 18% · pista 31 °C · umidade 76% · borracha 74%`
* **Painel de Contexto do Piloto (Rodapé Flutuante):**
  Exibe a aderência efetiva instantânea do carro:
  ```text
  velocidade base       332 km/h
  arquétipo             balanced
  ritmo                   -0.32%
  compostura                0.91
  agressividade             0.93
  consistência              0.96
  gestão de pneu            1.05
  aderência                98.4%
  ```
* **Decomposição de Velocidade:**
  A barra de velocidade decompõe a perda por clima (`clima %`), reponderada suavemente pela curvatura da pista (`WEATHER_STRAIGHT_SHARE = 0.15`).

