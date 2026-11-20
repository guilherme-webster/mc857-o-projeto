# Revisão Final: Modelagem da Pit Lane e Dinâmica dos Boxes

Este documento consolida a especificação, arquitetura geométrica, formulação física, regras desportivas e apresentação visual da **pit lane** (via dos boxes) no simulador 2D de Fórmula 1.

---

## 1. Visão Geral e Princípios Arquiteturais (ADRs 0002, 0011 e 0012)

A funcionalidade de pit lane modela o ciclo completo de uma parada de box — desde o planejamento estratégico e desaceleração na pista principal até a troca de pneus na baia de serviço e o retorno seguro à corrida.

Seguindo a **Arquitetura Hexagonal (ADR 0002)**, o sistema é rigorosamente dividido em duas camadas desacopladas:

1. **Núcleo de Domínio (`src/f1_simulator/domain/`):**
   * `pit_lane.py`: Define o caminho aberto dos boxes (`PitLanePath`), parâmetros regulamentares (`PitLaneParameters`), pedidos de parada (`PitStopRequest`) e estado transitório do carro (`PitLaneState`).
   * `track_space.py`: Implementa o trânsito da via rápida, a aproximação lateral prévia na pista, o controle de filas (*double-stack*) e a verificação de brecha segura para reentrada (*safe gap*).
   * `race_simulation_2d.py`: Conecta a estratégia de pneus/clima/combustível ao agendamento de paradas, executa o sorteio contínuo do tempo de serviço e serializa a trajetória compactada.
   * *O motor independe completamente de janelas gráficas, GPU ou servidores web.*

2. **Borda de Apresentação (`frontend/arcade/`):**
   * `track_view.py`: Renderiza a geometria da pista e da pit lane em camadas, calcula as rampas de acesso tangenciais via curvas cúbicas de Bézier e posiciona as hitboxes orientadas dos carros.
   * `race_playback.py`: Realiza a interpolação contínua da posição física e do progresso interno dos boxes (`pit_distance_m`).

```text
       [ Estratégia de Pneus / Clima ]
                     │
                     ▼
          [ Decisão de Parada ]
                     │
     ┌───────────────┴────────────────┐
     ▼                                ▼
[ Pista Principal (300 km/h) ]   [ Aproximação e Desaceleração ]
                                      │
                                      ▼
                                 [ Off-Ramp Tangencial ]
                                      │
                                      ▼
                          [ Fast Lane dos Boxes (80 km/h) ]
                                      │
                                      ▼
                            [ Baia de Serviço (2,2 a 2,8 s) ]
                                 (Troca de Pneus / Refuel)
                                      │
                                      ▼
                               [ Gap de Segurança ]
                                      │
                                      ▼
                                 [ On-Ramp de Saída ]
                                      │
                                      ▼
                         [ Reenquadramento na Corrida ]
```

---

## 2. Condições para Entrada nos Boxes

A parada nos boxes não é aleatória; ela é acionada por três mecanismos principais:

### 2.1. Regra de Compostos Obrigatória (ADR 0008)
Em corridas disputadas em pista seca, o regulamento desportivo exige o uso de pelo menos **dois compostos secos distintos** (por exemplo, Médio $\to$ Duro). O componente `pit_planning_2d` planeja a janela ideal calculando o desgaste equivalente de cada piloto, preservando o prazo limite da prova.

### 2.2. Degradação Física dos Pneus (ADR 0014)
O desgaste não ocorre por taxa fixa por volta. Ele acumula estresse mecânico real:
* Carga lateral nas curvas (derivada do perfil de curvatura da pista);
* Carga longitudinal (força de tração e frenagem pesada).
Quando a vida útil do composto atinge o ponto de perda severa de ritmo (*cliff*), o modelo tático antecipa a troca.

### 2.3. Dinâmica Climática e Aderência (ADR 0015)
Quando ocorre precipitação e a água na pista eleva a lâmina acima dos limiares dos pneus slick, o fator de aderência efetivo (`grip_factor`) despenca. O piloto programa imediatamente a entrada para calçar pneus Intermediários ou de Chuva Extrema (*Wet*).

### 2.4. Agendamento da Parada
No início da volta prevista, é gerado o objeto imutável:
```python
PitStopRequest(entry_distance_m=entry, service_time_s=duration)
```
Onde `entry_distance_m` representa o marco métrico exato da boca de entrada da rampa dos boxes.

---

## 3. Dinâmica Espacial de Aproximação e Entrada (`integrate_field`)

Quando um carro possui um `pit_request` ativo, o motor espacial adota procedimentos específicos antes do ingresso:

### 3.1. Desaceleração Gradual na Reta
Nos 80 metros que antecedem o marco de entrada ($0 < s_{\text{entry}} - s \le 80\text{ m}$), o teto de velocidade do carro é reduzido linearmente da velocidade de corrida para a velocidade limite do pit lane ($v_{\text{limit}} = 80\text{ km/h} \approx 22{,}22\text{ m/s}$):
$$v_{\text{target}}(s) = \min\left(v_{\text{race}}, \; v_{\text{limit}} + (v_{\text{race}} - v_{\text{limit}}) \cdot \frac{s_{\text{entry}} - s}{80}\right)$$
Isso evita desacelerações instantâneas na pista principal e impede que carros colidam violentamente por trás.

### 3.2. Mudança Prévia de Faixa
Nos 60 metros que antecedem a entrada ($0 < s_{\text{entry}} - s \le 60\text{ m}$), o piloto cancela qualquer tentativa de ultrapassagem e comuta seu alvo lateral para a borda onde fica a entrada dos boxes:
$$d_{\text{target}} = \text{side} \cdot d_{\text{usable}} \cdot 0{,}75$$
Onde $\text{side} \in \{+1{,}0, -1{,}0\}$ indica se a pit lane fica à esquerda ou à direita do circuito. O carro desloca-se a uma taxa lateral máxima de $6{,}0\text{ m/s}$ (`ASSUMED_LANE_CHANGE_MS`), liberando a trajetória ideal para os adversários.

### 3.3. Ingresso nos Boxes
Ao atingir $s \ge s_{\text{entry}}$, o carro transita para o estado `PitLaneState`:
* `car.distance_m` é fixado no marco métrico de entrada;
* `car.pit_state = PitLaneState()` é instanciado com progresso interno zero (`path_distance_m = 0.0`);
* O evento auditável `"entry"` é despachado.

---

## 4. Dinâmica e Fila Dentro da Pit Lane

Dentro dos boxes, o movimento dos veículos deixa as coordenadas Frenet da pista e passa a seguir o caminho unidimensional contínuo da pit lane (`PitLanePath`):

### 4.1. Velocidade Dinâmica Não-Constante
Embora o regulamento imponha um limite de $80\text{ km/h}$, a velocidade real oscila deterministicamente para simular a cautela humana:
* **Velocidade base individual:** Sorteada por hash estável do piloto no intervalo $[66\text{ km/h}, 76\text{ km/h}]$;
* **Gradiente ao longo da via:** Redução gradual de $10\%$ à medida que o carro se aproxima da área dos mecânicos;
* **Oscilação suave de tráfego:** Modulação senoidal de amplitude $4\%$ baseada na posição interna $s_{\text{pit}}$.

### 4.2. Tratamento de Fila e Ultrapassagens (*Fast Lane* vs. *Working Lane*)
Para evitar engarrafamentos irreais na via de rolamento:
* **Carros de equipes diferentes:** Carros de outras escuderias parados em atendimento encontram-se estacionados em sua respectiva baia (*working lane*). Eles **não bloqueiam** o tráfego dos carros em movimento na via rápida (*fast lane*).
* **Double-Stack (Mesma Equipe):** Se dois companheiros de equipe pararem na mesma volta, o segundo carro aguarda em fila segura mantendo folga longitudinal:
  $$\Delta s_{\text{safe}} = \frac{L_{\text{car1}} + L_{\text{car2}}}{2}$$
  O segundo piloto só ingressa na baia após a conclusão do serviço do primeiro, reproduzindo com fidelidade a perda tática de paradas simultâneas.

---

## 5. Duração e Execução do Serviço

Ao atingir o marco métrico da baia de trabalho (`service_distance_m`):

### 5.1. Duração Contínua Sorteada
A duração base da parada é sorteada em um intervalo contínuo determinístico entre **$2{,}2\text{ s}$ e $2{,}8\text{ s}$**:
$$t_{\text{service}} = \max\left(1{,}5, \; \left(t_{\text{base\_params}} + (u - 0{,}5) \cdot 0{,}6\right)\right) \cdot \text{execution}$$
Onde:
* $u \sim \mathcal{U}(0, 1)$ é derivado do fluxo pseudoaleatório determinístico por piloto;
* $\text{execution}$ é o fator de eficiência da equipe (valores menores que $1{,}0$ aceleram a troca; valores maiores penalizam paradas lentas).

### 5.2. Desvios Adicionais por Erro de Troca
Se o cenário incluir variação estocástica (`pit_stop_variation`), um sorteio normal assimétrico pode simular porcas presas ou falhas de levantamento do macaco hidráulico:
$$t_{\text{service}} \leftarrow \max\left(2{,}2 \cdot \text{execution}, \; t_{\text{service}} + \Delta t_{\text{error}}\right)$$

### 5.3. Ações Durante o Atendimento
* Velocidade instantânea mantida em $0\text{ km/h}$;
* Desgaste dos pneus zerado: `tyre_wear_laps = 0.0`;
* Composto comutado para o jogo novo selecionado pela estratégia;
* Combustível injetado (caso a categoria autorize reabastecimento);
* Eventos auditáveis `"service_started"` e `"service_completed"` registrados.


---

## 6. Procedimento de Saída e Reenquadramento (*Rejoining*)

Ao concluir a rampa de aceleração interna dos boxes:

### 6.1. Janela de Segurança na Pista Principal (*Safe Gap*)
Antes de reentrar na pista, o sistema calcula a folga longitudinal em relação aos carros que vêm em velocidade máxima pela reta principal (inclusive retardatários):
$$\Delta s_{\text{gap}} = \text{distância frontal até o carro que se aproxima}$$
Se $\Delta s_{\text{gap}} < 2{,}0 \cdot L_{\text{car}}$, o carro aguarda na via de aceleração até que haja um intervalo seguro, evitando colisões laterais a $300\text{ km/h}$.

### 6.2. Continuidade $C^1$ na Reentrada
Assim que a saída é autorizada:
* `car.pit_state = None` e `car.pit_request = None`;
* A posição lateral é ancorada na borda externa de aceleração:
  $$d_{\text{car}} = \text{side} \cdot d_{\text{usable}} \cdot 0{,}75$$
* A orientação angular coincide perfeitamente com a tangente da pista $\vec{t}_{\text{track}}$;
* O controle lateral é transferido para o algoritmo de decisão de faixa (`_lane_decision`), que conduz o carro suavemente de volta ao traçado de corrida ao longo da reta.

---

## 7. Geometria e Renderização Visual 2D (`TrackView`)

A apresentação visual no frontend Desktop em Arcade resolveu as descontinuidades e os saltos de coordenadas através de modelagem geométrica dedicada:

### 7.1. Proveniência e Dados Reais FastF1 (2025)
A polilinha base provém do dataset FastF1 da temporada 2025 (`pit_lane_points.csv`), contendo 80 pontos por circuito e a localização observada da baia (`is_service_point`).

### 7.2. Eliminação do Ângulo de 90°: Rampas Cúbicas de Bézier
Como a telemetria GPS registra apenas o trecho interno sob o limitador de velocidade, a projeção ortogonal direta no centro da pista gerava uma curva perpendicular em gancho (alça de caneca).

Para criar rampas realistas de $\approx 10^\circ$ a $15^\circ$:
1. **Extensão Longitudinal das Rampas:**
   * A rampa de entrada inicia $60\text{ m}$ antes da linha do limitador;
   * A rampa de saída termina $60\text{ m}$ depois na reta principal.
2. **Vetor Tangente de Concordância:**
   * O vetor tangente forward da pista é obtido a partir da normal:
     $$\vec{t}_{\text{track}} = (\hat{n}_y, \; -\hat{n}_x)$$
3. **Interpolação Bézier Cúbica:**
   A conexão entre a borda da pista $P_0$ e o ponto interno $P_1$ utiliza pontos de controle direcionais:
   $$C_0 = P_0 + \vec{t}_0 \cdot (0{,}4 \cdot D), \quad C_1 = P_1 - \vec{t}_1 \cdot (0{,}4 \cdot D)$$
   $$B(t) = (1-t)^3 P_0 + 3(1-t)^2 t C_0 + 3(1-t) t^2 C_1 + t^3 P_1, \quad t \in [0, 1]$$

### 7.3. Ordem de Desenho por Camadas
No método `on_draw`, a pit lane é desenhada **antes** do traçado principal:
```python
if self._pit_screen:
    arcade.draw_line_strip(self._pit_screen, (190, 146, 52), 4.0 * lane_px)
    arcade.draw_line_strip(self._pit_screen, (64, 68, 74), 3.0 * lane_px)
self._draw_track_2d(screen, track_color)
self._draw_start_finish_line(screen)
self._draw_cars_2d(screen)
```
* **Efeito visual:** O asfalto e as linhas brancas contínuas da pista principal sobrepõem a raiz da junção. O asfalto da pista de corrida permanece $100\%$ limpo, contínuo e sem emendas ou cortes escuros no meio da faixa.

### 7.4. Sincronização 1:1 Sem Teletransporte
* A coordenada métrica de entrada do motor (`pit_lane.entry_distance_m`) e a coordenada visual da rampa (`edge_in`) coincidem rigorosamente no mesmo metro longitudinal;
* O carro atinge o bocal da rampa na pista e ingressa imediatamente no percurso dos boxes, eliminando qualquer ultrapassagem da entrada ou salto para trás.

---

## 8. Tabela Resumo dos Parâmetros

| Parâmetro | Valor Padrão | Origem | Descrição |
| :--- | :---: | :---: | :--- |
| `speed_limit_kmh` | $80{,}0\text{ km/h}$ | Regulamento FIA | Limite de velocidade regulamentar na via dos boxes. |
| `service_time_s` | $[2{,}2\text{ s}, 2{,}8\text{ s}]$ | Heurístico calibrado | Intervalo contínuo sorteado para troca de 4 pneus. |
| `ramp_offset` | $60{,}0\text{ m}$ | Heurístico geométrico | Extensão longitudinal das rampas de acesso tangenciais. |
| `decel_distance` | $80{,}0\text{ m}$ | Dinâmica de frenagem | Extensão na reta para redução gradual de velocidade. |
| `pre_lane_distance` | $60{,}0\text{ m}$ | Tomada de decisão | Distância para migração lateral em direção à borda do box. |
| `merge_gap_m` | $2{,}0 \times L_{\text{car}}$ | Segurança desportiva | Folga mínima exigida para reentrada segura na pista. |

