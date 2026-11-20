# Revisão Final: Modelagem da Pista 2D e Dinâmica Espacial

Este documento consolida a especificação, arquitetura geométrica, formulação matemática e comportamento da **pista 2D** no simulador de Fórmula 1.

---

## 1. Visão Geral e Princípios Arquiteturais (ADR 0011)

A modelagem da pista 2D substituiu a antiga resolução unidimensional (onde o motor avançava uma volta por passo e sorteava ultrapassagens por probabilidade) por uma **simulação contínua no espaço e no tempo**.

### Princípios do Modelo
* **Resolução Sub-volta Contínua:** O tempo avança em passos fixos de **$\Delta t = 0{,}1\text{ s}$** (10 passos por segundo), permitindo que trajetórias, acelerações e manobras sejam observadas em tempo real.
* **Comportamento Emergente:** Ultrapassagens, bloqueios na reta, disputas lado a lado e toques de carroceria não são sorteados em tabelas; eles acontecem porque dois corpos físicos com dimensões reais disputam o mesmo espaço de asfalto.
* **Independência de Frameworks:** Toda a física espacial opera exclusivamente em metros e segundos dentro do núcleo de domínio (`src/f1_simulator/domain/track_space.py`), sem acoplamento com o laço gráfico do Arcade ou com o servidor web FastAPI.

---

## 2. Sistema de Coordenadas de Frenet $(s, d)$

Em pistas de corrida em circuito fechado, o cálculo de distâncias relativas entre carros em coordenadas cartesianas puras $(x, y)$ seria computacionalmente ineficiente. Por isso, a física utiliza o sistema curvilíneo de **coordenadas de Frenet $(s, d)$**:

```text
    Borda Esquerda (+usable) -------------------------------------------
                                   ^
                                   | +d (deslocamento lateral para a esquerda)
    Linha de Centro (d = 0)  ------|-------------------------------------> s (distância longitudinal)
                                   | -d (deslocamento lateral para a direita)
                                   v
    Borda Direita (-usable)  -------------------------------------------
```

* **Coordenada Longitudinal $s$:** Distância acumulada em metros percorrida ao longo da linha de centro desde a linha de largada ($s \ge 0$). A volta em curso do piloto é obtida por $s \,//\, \text{lap\_length\_m}$.
* **Coordenada Lateral $d$:** Deslocamento perpendicular em relação à linha de centro em metros:
  * $d = 0$: Carro posicionado exatamente no centro do traçado;
  * $d > 0$: Carro deslocado para o lado **esquerdo**;
  * $d < 0$: Carro deslocado para o lado **direito**.

---

## 3. Geometria da Faixa da Pista (`TrackSpace`)

A classe `TrackSpace` constrói uma esteira contínua com largura sobre a polilinha original de vértices normalizados $(x_i, y_i)$.

### 3.1. Escala Métrica
O fator de conversão entre unidades normalizadas de tela e metros reais é calculado pela razão:
$$\text{xy\_per\_metre} = \frac{\text{Perímetro total da polilinha normalizada}}{\text{Extensão oficial da volta (m)}}$$

### 3.2. Vetores Tangentes e Normais Unitários
Para cada marco do traçado, calculam-se a direção da pista e a sua normal:
1. **Tangente ($\vec{t}$):** Sentido de avanço da corrida entre os pontos vizinhos:
   $$\vec{t} = \left(\frac{x_{i+1} - x_{i-1}}{\|\vec{t}\|}, \; \frac{y_{i+1} - y_{i-1}}{\|\vec{t}\|}\right)$$
2. **Normal ($\vec{n}$):** Giro de $90^\circ$ para a esquerda do sentido de corrida:
   $$\vec{n} = (-\hat{t}_y, \; \hat{t}_x)$$

Cada ponto do circuito é armazenado como um `SpacePoint(distance_m, cx, cy, nx, ny)`.

### 3.3. Conversão de $(s, d)$ para $(x, y)$ na Tela
Para desenhar o carro ou projetar sua posição na visualização gráfica:
1. Realiza-se busca binária rápida no array de distâncias acumuladas;
2. Interpola-se a posição central $(c_x, c_y)$ e a normal $(\hat{n}_x, \hat{n}_y)$ no marco exato $s$;
3. Aplica-se o deslocamento lateral $d$:
   $$(x, y) = (c_x, c_y) + d \cdot \text{xy\_per\_metre} \cdot (\hat{n}_x, \hat{n}_y)$$


---

## 4. Dimensões Físicas e Limites da Pista (`LateralBounds`)

Para que as disputas de posição respeitem os limites espaciais da Fórmula 1, os parâmetros assumidos no modelo são:

* **Largura Total da Pista ($W$):** $12{,}0\text{ metros}$ (`ASSUMED_TRACK_WIDTH_M`).
* **Largura do Carro ($w_{\text{carro}}$):** $2{,}0\text{ metros}$ (`ASSUMED_CAR_WIDTH_M`).
* **Comprimento do Carro ($l_{\text{carro}}$):** $5{,}0\text{ metros}$ (`ASSUMED_CAR_LENGTH_M`).

### 4.1. Faixa Lateral Útil (`usable_m`)
O centro do carro não pode atingir a borda física extrema da pista ($6{,}0\text{ m}$), pois isso colocaria metade do veículo para fora do asfalto. O limite para o centro geométrico é:
$$\text{usable\_m} = \frac{W}{2} - \frac{w_{\text{carro}}}{2} = 6{,}0 - 1{,}0 = \mathbf{5{,}0\text{ metros}}$$

Portanto, qualquer carro é confinado no intervalo:
$$d \in [-5{,}0\text{ m}, \; +5{,}0\text{ m}]$$

Com $10\text{ metros}$ de espaço livre útil e carros de $2\text{ metros}$, o asfalto comporta confortavelmente **dois a três carros emparelhados**.

---

## 5. Dinâmica do Carro e Movimento Lateral (`CarSpaceState`)

O estado de cada veículo a cada instante é representado pela classe `CarSpaceState`:
* `distance_m`: Posição longitudinal acumulada ($s$).
* `lateral_m`: Deslocamento lateral atual ($d$).
* `target_lateral_m`: Posição lateral desejada pelo piloto para ataque ou defesa.
* `speed_ms`: Velocidade escalar ao longo da pista.
* `overtaking`: ID do adversário disputado no momento (garante persistência de manobra até a conclusão, evitando hesitações a cada tick).

### 5.1. Velocidade Lateral Máxima ($\dot{d}_{\max}$)
Mudanças de trajetória respeitam uma taxa de transição física:
$$\dot{d}_{\max} = 6{,}0\text{ m/s} \quad (\text{ASSUMED\_LANE\_CHANGE\_MS})$$

A cada tick ($\Delta t = 0{,}1\text{ s}$), o deslocamento lateral máximo permitido é:
$$\Delta d_{\max} = 6{,}0\text{ m/s} \times 0{,}1\text{ s} = \mathbf{0{,}6\text{ metro por tick}}$$

Para cruzar do centro da pista ($d = 0\text{ m}$) até a linha de tangência externa ($d = 3\text{ m}$), o carro leva aproximadamente **$0{,}5\text{ segundo}$**, garantindo animação contínua e natural.

---

## 6. Ultrapassagens e Bloqueios Emergentes (`integrate_field`)

No motor 2D, ultrapassagens não decorrem de dados estatísticos; elas são consequência direta de velocidade e espaço:

```text
Tick 1: Carro A (mais rápido) se aproxima de Carro B na mesma faixa central (d = 0)
[ Carro A: 300 km/h ] -------- 15 metros --------> [ Carro B: 260 km/h ]

Tick 2: Carro A detecta o bloqueio e aponta para a faixa livre da esquerda (alvo d = +3,0 m)
             \
[ Carro A ] ---\---------------------------------> [ Carro B ]

Tick 3: Carros emparelhados em faixas diferentes (|dA - dB| > 2,0 m) -> Pista livre!
[ Carro A: 300 km/h ] (faixa d = +3,0 m)
--------------------------------------------------
[ Carro B: 260 km/h ] (faixa d = 0,0 m)

Tick 4: Carro A supera o comprimento do Carro B e volta suavemente para o centro da pista
[ Carro A ] ------------------
            \
             \-----------------------------------> [ Carro B ]
```

### Regras do Algoritmo de Pelotão:
1. **Detecção de Mesma Faixa (`_same_lane`):**
   Dois carros ocupam a mesma faixa se a distância lateral entre seus centros for menor que a largura combinada:
   $$|d_A - d_B| < 2{,}0\text{ metros}$$
2. **Gatilho de Perseguição (`ASSUMED_FOLLOW_TRIGGER_M = 20 m`):**
   Quando a folga para o carro à frente na mesma faixa cai abaixo de $20\text{ metros}$, o atacante avalia se há espaço livre à esquerda ou à direita e define seu `target_lateral_m`. Pilotos agressivos abrem para ultrapassagem mais cedo.
3. **Exclusão Longitudinal (Anti-penetração):**
   Enquanto permanecerem na mesma faixa, o avanço do carro seguidor é limitado pelo para-choque traseiro do líder:
   $$s_{\text{proposto}} \le s_{\text{frente}} - \frac{l_{\text{frente}} + l_{\text{trás}}}{2}$$
   O carro de trás é forçado a igualar a velocidade do líder até encontrar espaço lateral.
4. **Conclusão da Ultrapassagem:**
   Assim que a separação lateral atinge $|d_A - d_B| \ge 2{,}0\text{ m}$, a restrição longitudinal deixa de atuar. O carro mais veloz acelera livremente pelo seu teto de velocidade e, ao abrir mais de $5\text{ metros}$ de vantagem à frente, converge suavemente ao centro do traçado.

---

## 7. Contatos e Colisões Espaciais (`spatial_contact.py`)

A física de contato utiliza caixas delimitadoras retangulares orientadas de $5\text{ m} \times 2\text{ m}$:
* **Toque Leve (*Rubbing*, folga lateral $< 0{,}3\text{ m}$):** Em disputas lado a lado de freada ou contorno de curva, toques de carroceria geram dano aerodinâmico cumulativo (`contact_damage`), reduzindo levemente o ritmo de pico sem causar abandono instantâneo.
* **Colisão Severa:** Fechadas bruscas de porta ou colisões em alta velocidade relativa avaliam a severidade do impacto e a compostura dos pilotos, podendo gerar abandono imediato e acionamento de Safety Car, VSC ou bandeiras amarelas pelo controle de prova.

---

## 8. Interface com a Pit Lane

A rua dos boxes conecta-se à pista principal através de coordenadas geométricas de entrada e saída exclusivas. 

*(Nota: Toda a mecânica de tráfego interno, paradas de serviço e desaceleração do pit lane é tratada em documento dedicado em `docs/final-review/modelagem-pit-lane.md`).*

