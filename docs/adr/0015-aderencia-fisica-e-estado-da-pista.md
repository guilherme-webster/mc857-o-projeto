# 0015 - Aderência física e estado dinâmico da pista

- Status: proposta
- Data: 2026-11-06
- Responsável pela autorização: usuário, ao abrir a issue #119 e autorizar a
  implementação nesta sessão
- Atualiza: [ADR 0010](0010-motor-fisico-de-velocidade-por-trecho.md), que
  derivava a velocidade de curva do ângulo entre pontos com um envelope global
  de 320/90 km/h; o restante do ADR 0010 (o tempo de volta emerge da física e
  substitui a volta de referência) continua valendo
- Relaciona-se com: ADR 0003 (geometria reduzida do FastF1), ADR 0008
  (parâmetros heurísticos rotulados), ADR 0011 (motor 2D, que consome o mesmo
  teto de velocidade) e a issue #120 (pneus de chuva)

## Contexto

O ADR 0010 fez o tempo de volta emergir da geometria: em cada ponto, uma
velocidade-alvo entre 320 km/h (reta) e 90 km/h (curva), interpolada pelo
ângulo entre os segmentos vizinhos e normalizada pela curva mais fechada **da
própria pista**. Três consequências apareceram ao comparar com as voltas de
referência históricas (`reference-laps-v1.json`):

- toda pista tinha a curva mais lenta a 90 km/h: o grampo de Mônaco (real
  ~50 km/h) e a curva mais lenta de Monza ficavam iguais;
- o ângulo dependia do espaçamento dos 240 pontos (~14 m em Mônaco, ~29 m em
  Spa), não do raio;
- a volta física saía em mediana 0,89 da histórica (Mônaco 0,63, Montreal
  0,74; raiz do erro quadrático médio de `log(física/referência)` = 0,169).
  Como o motor detalhado usa a volta física no lugar da referência quando há
  geometria, corridas inteiras saíam 6-15% mais rápidas que as reais.

Além disso, sem aderência explícita, clima, borracha e composto não tinham
onde agir fisicamente: a chuva era só +40% linear no tempo de volta, igual para
qualquer pneu e qualquer traçado, e o 2D repetia o 0,40 no código.

## Alternativas consideradas

1. **Manter o modelo e somar efeitos em milissegundos.** Barato, mas a chuva
   continuaria desacelerando a reta igual à curva, e o erro de calibração
   (Mônaco 37% rápido) ficaria. Rejeitada.
2. **Fator de correção por pista sobre a volta física.** Fecharia o erro por
   construção, mas sem explicar nada: a água, a borracha e o pneu continuariam
   sem ponto físico de entrada. Rejeitada.
3. **Ponto de massa limitado por aderência, com raio em metros.** Modelo
   clássico de simulação de volta quase estacionária: velocidade de curva,
   freada e tração saem do mesmo `mu`. Dois parâmetros do carro são estimados
   contra as 24 voltas de referência. Escolhida.

## Decisão

1. **Curvatura em metros.** As coordenadas normalizadas têm escala uniforme;
   a extensão oficial da volta dividida pelo perímetro da polilinha dá o
   fator. A curvatura de cada ponto é a do círculo pelos dois vizinhos,
   suavizada por média móvel de três pontos e limitada a raio mínimo de 8 m
   (`speed_dynamics.track_curvature_per_m`).
2. **Velocidade de curva** `v² = mu·g / (1/R − mu·k_a)`, em que `k_a` é o
   downforce por massa e por velocidade ao quadrado; sem limite físico, a
   velocidade máxima de reta.
3. **Freada e tração dependem da velocidade:** freada
   `mu·(g + k_a·v²) + k_d·v²`; tração
   `min(0,55·mu·(g + k_a·v²), P/(m·v)) − k_d·v²`. Os dois integradores (por
   distância e o 2D por tempo) usam os mesmos limites.
4. **Parâmetros.** `grip_mu = 1,30` e `downforce_cla_m2 = 4,5` estimados por
   grade (grossa e fina) minimizando o erro de `log(física/referência)` nas
   24 pistas (`scripts/calibrate_car_physics.py` →
   `data/parameters/car-physics-v1.json`). Massa 800 kg, potência 750 kW,
   `C_D·A` 1,1 m², 330 km/h e parcela de tração 0,55 são hipóteses de ordem de
   grandeza. `DEFAULT_CAR_PHYSICS` espelha o artefato; um teste impede que
   divirjam.
5. **Atributos do piloto mantêm o significado do ADR 0010**, agora como uso da
   aderência: ritmo escala a velocidade de reta e o uso de `mu` em curva
   (`p²`), compostura escala o uso de `mu` em curva (`c²`), agressividade o uso
   na freada. Os ganhos (inclusive o ganho de ritmo 7×, exagerado de propósito
   para separar estilos na tela) não mudam.
6. **Estado dinâmico da pista** (`domain/track_condition.py`), calculado
   sempre, inclusive em corrida seca:
   - água: o modelo da #69, agora por minuto (os fluxos valem por volta de
     referência de 1,5 min) e com evaporação acelerada pela temperatura;
   - temperatura do asfalto: tende a 35 °C seca e esfria até 12 °C abaixo com
     a pista saturada (constante de tempo de 10 min);
   - borracha: começa em 0,8, o pelotão recupera 8% do que falta por volta, e
     uma volta saturada lava 30% da camada; pista verde tem 3% menos
     aderência;
   - aderência = `água × borracha`. A água descreve a aderência **com o pneu
     adequado**: 0,81 na pista úmida (água 0,3) e 0,69 saturada, que custam
     ~13% e ~25% na pista mediana, a ordem de grandeza de voltas de
     intermediário e de chuva em corridas molhadas de 2023-2024.
7. **Do fator ao tempo.** Cada carro tem uma tabela de volta lançada por fator
   de aderência (`GripLapTimes`), calculada sob demanda nos pontos de uma grade
   e interpolada. O motor detalhado soma `tempo(fator) − tempo(1)` como
   `weather_ms`; o 2D soma o mesmo valor na conversão para `speed_scale`. Sem
   geometria, usa-se `fator ** −0,6`, a sensibilidade da pista mediana.
8. **Saída.** O resultado traz `track_conditions` por volta (chuva, umidade,
   água, temperatura, borracha e fator) e as premissas `physical_lap_time`
   (agora `estimated`, `car-physics-v1`) e `track_condition` nos dois motores.

## Consequências

- O erro da volta física cai de 0,169 para 0,046 (~4,7%); mediana 0,993;
  Mônaco 1,03. Corridas de distância real ficam com duração próxima da real
  (Spa 44 voltas: ~79 min).
- Água custa mais nas pistas de curvas lentas (saturada: Mônaco ~+27%, Monza
  ~+19%) e quase nada nas retas, como na realidade.
- Resíduos conhecidos, publicados por pista no artefato: curvas inclinadas
  (Zandvoort +11%), traçado rápido de Losail (+12%), altitude (México −5%) e
  chicanes curtas que 240 pontos não resolvem (Monza −7%).
- Frenagens agora chegam a ~4-5 g em alta velocidade. No 2D isso aumenta as
  tentativas de ultrapassagem na freada e, com o modelo de contato atual, os
  abandonos por toque; a taxa de contato do 2D precisa de revisão própria.
- A temperatura ainda não altera a aderência: ela evolui, acelera a secagem e
  fica disponível para a janela de operação dos pneus (#120).
- Todos os resultados mudam: tempos de volta, paradas e posições não são
  comparáveis a corridas simuladas antes desta decisão.
- O efeito linear `weather_penalty_ms` (+40%) foi removido.

## Validação

`tests/test_speed_dynamics.py` (curvatura de círculos amostrados, fórmula da
curva, limites dependentes da velocidade, atributos, recuperação de parâmetros
conhecidos pela calibração, artefato espelhado e erro contra as 24 voltas de
referência) e `tests/test_track_condition.py` (âncoras de água, borracha,
secagem por minuto e por temperatura, interpolação contra a física direta e os
dois motores mais lentos na chuva). A suíte completa roda por `unittest`.
