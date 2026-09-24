# Modelagem calibrada da corrida

Relatório da fatia que substituiu o núcleo de ritmo constante por um modelo de
tempo de volta decomposto, calibrado no histórico Trotman v128 e validado contra
corridas reais não usadas na calibração.

Escopo: itens 1 e 4 do plano (`Desenvolvimento de Simulador F1.md`, seções 8.2 e
11, fases 2 e 6) e as frentes de modelagem #60/#61/#63 do backlog. Preserva as
fronteiras do ADR 0002 e não introduz nova fonte de dados além do Trotman v128
já aprovado no ADR 0002/0005.

---

## 1. Resumo do resultado

Validação em **24 corridas de 2024**, 10 sementes por corrida, com parâmetros
calibrados apenas em **2022–2023**. O ano de 2024 nunca entrou na calibração.

O modelo foi validado sob quatro **fontes de ritmo** diferentes, que se
distinguem por quanta informação da própria corrida elas usam:

| Fonte de ritmo | O que usa | pos MAE | Spearman | vencedor | pódio/3 |
| --- | --- | ---: | ---: | ---: | ---: |
| `weekend` | voltas da própria corrida (**vaza**) | 2,508 | 0,804 | 26,4% | 1,69 |
| `profile` | corridas anteriores, método da #40 | 3,007 | 0,716 | 41,7% | 1,67 |
| `qualifying` | classificação, medida antes da largada | 2,755 | 0,743 | 51,4% | 1,86 |
| **`combined`** | **classificação × perfil da #40** | **2,664** | **0,768** | **52,1%** | **1,94** |

Contra as linhas de base, na configuração `combined` — que **não usa nenhuma
informação da corrida sendo prevista**:

| | pos MAE | Spearman | vencedor | paradas sim / real | DNF sim / real |
| --- | ---: | ---: | ---: | ---: | ---: |
| Linha de base `grid` | 2,765 | 0,739 | 45,8% | 0,00 / 1,78 | 0,00 / 1,67 |
| Linha de base `constant` | 2,681 | 0,766 | 50,0% | 0,00 / 1,78 | 0,00 / 1,67 |
| **Modelo, determinístico** | **2,664** | **0,768** | **52,1%** | 2,00 / 1,78 | — |
| Modelo, estocástico completo | 3,385 | 0,595 | 48,3% | 1,84 / 1,78 | 2,91 / 1,67 |

**O modelo determinístico vence as duas linhas de base** em erro de posição,
correlação de ordem e acerto do vencedor. O modo estocástico perde em previsão
pontual pelo motivo estrutural descrito na seção 7.

Efeito visível na aplicação, na corrida de São Paulo de 2024 (69 voltas):

```
modelo antigo (ritmo constante) :  0 voltas com mudança de ordem
modelo novo                     : 40 voltas com mudança de ordem
```

O modelo antigo produzia uma corrida **estática**: com ritmo constante por carro,
a ordem de chegada fica decidida na volta 1 e as diferenças só crescem.

## 2. O modelo

Regra aditiva, com cada parcela devolvida separadamente em `LapTimeBreakdown`
(plano, seção 8.2):

```
tempo_volta = referência(piloto)          # volta limpa: pneu novo, pouco combustível, ar livre
            + penalidade_combustível(voltas restantes)
            + penalidade_pneu(composto, idade)
            + penalidade_tráfego(intervalo p/ o carro à frente)
            + perda_de_boxes(se parar nesta volta)
            + ruído(semente)
```

A posição de largada entra como atraso inicial de relógio, e o abandono é
sorteado por volta contra um risco calibrado.

### A restrição central: não contar o mesmo efeito duas vezes

`reference_lap_time_ms` é a mediana do quartil mais rápido das voltas do próprio
piloto. Essas voltas são tipicamente as de pneu novo, combustível baixo e ar
livre — exatamente a condição que as penalidades assumem como origem. Por isso
elas podem ser somadas a ela.

Somar as mesmas penalidades a uma referência que já contivesse combustível alto
ou pneu velho contaria o efeito duas vezes. É o risco descrito em
`docs/contrato-perfil-simulacao.md`, e ele determinou toda a convenção de sinais:
**a referência é a condição ideal e todas as parcelas são penalidades ≥ 0.**

---

## 3. Como os componentes do repositório se conectam

O pipeline usa apenas peças que já existiam; as novas se encaixam entre elas sem
quebrar nenhuma fronteira do ADR 0002.

```
Kaggle Trotman v128 (CC0, sha256 verificado)
   │
   │  scripts/download_trotman.py            ← já existia
   ▼
data/raw/formula-1-race-data-v128.zip        (fora do Git)
   │
   │  scripts/ingest_trotman.py --all-tables  ← já existia
   │  adapters/datasets/trotman_history.py
   ▼
data/curated/history.sqlite                  (879.870 voltas, 1.172 corridas)
   │
   ├─── CALIBRAÇÃO ────────────────────────────────────────────────┐
   │    adapters/persistence/sqlite_calibration.py   [NOVO]        │
   │      lê e filtra voltas limpas, perdas de boxes, grid, atrito │
   │           ↓ observações canônicas (sem SQL além desta borda)  │
   │    application/calibrate_model.py               [NOVO]        │
   │      regressão within de duas variáveis; só matemática        │
   │           ↓                                                   │
   │    adapters/model_parameters_json.py            [NOVO]        │
   ▼                                                               │
data/parameters/model-v1.json   ← VERSIONADO NO GIT                │
   │                                                               │
   ├─── SIMULAÇÃO ──────────────────┐        └── scripts/calibrate_model.py
   │    domain/model_parameters.py  │ [NOVO]
   │    domain/lap_time.py          │ [NOVO]  decomposição auditável
   │    domain/tyres.py             │ [NOVO]
   │    domain/strategy.py          │ [NOVO]  Strategy (plano §5.2)
   │    domain/random_source.py     │ [NOVO]  aleatoriedade injetada
   │    domain/race_simulation.py   │ [ESTENDIDO] simulate_detailed_race
   │                                │
   ├────────────┬───────────────────┘
   ▼            ▼
BACKEND      VALIDAÇÃO
backend/app/services/race_simulation.py      adapters/persistence/sqlite_race_scenario.py [NOVO]
backend/app/loaders/loader.py                application/backtest_model.py                [NOVO]
  → POST /simulation/simulate                scripts/backtest_model.py                    [NOVO]
  → backend/races/race.json                    → data/reports/backtest-2024-*.json
  → frontend/arcade/track_view.py
```

Pontos de ligação que exigiram cuidado:

| Ligação | Como foi preservada |
| --- | --- |
| **Backtest ↔ backend** | `sqlite_race_scenario.estimate_reference_pace_ms` e `loader._estimate_base_pace` usam a **mesma** definição de ritmo de referência. Se divergissem, as métricas publicadas descreveriam um modelo diferente do que a aplicação executa. |
| **Motor ↔ frontend Arcade** | `_detailed_classification` mantém o campo `lap_time_ms` que `frontend/arcade/track_view.py` usa para interpolar a posição do carro. Agora ele carrega o tempo **médio** por volta, então a animação passa a refletir o modelo novo **sem nenhuma alteração no frontend**. |
| **Parâmetros ↔ container** | `./data:/data` no Compose já monta o repositório, então `data/parameters/model-v1.json` aparece em `/data/parameters`. `backend/app/config.py` cai no caminho do repositório quando `/data` não existe, o que faz o backend funcionar dentro e fora do container sem duplicar arquivo. |
| **Domínio ↔ persistência** | Nenhum módulo de `domain/` importa `sqlite3`, `json` ou `pathlib`. Toda leitura fica em `adapters/`, toda matemática em `application/`. |

---

## 4. Calibração

`scripts/calibrate_model.py --seasons 2022 2023` · 44 corridas · 39.709 voltas limpas

### O problema: combustível e pneu se cancelam

Os dois maiores efeitos de um tempo de volta agem em **sentidos opostos**. O
combustível queima e o carro acelera; o pneu desgasta e o carro desacelera.
Somados ao longo de uma corrida, quase se anulam — a inclinação bruta do tempo
de volta fica perto de zero.

### A identificação: dois relógios diferentes

| Efeito | Relógio |
| --- | --- |
| Combustível | acompanha o **número da volta**, monotônico na corrida |
| Pneu | acompanha a **idade do jogo**, que **reinicia a cada parada** |

Os pit stops registrados no Trotman delimitam os stints, o que permite montar as
duas contagens e regredir o tempo sobre ambas ao mesmo tempo. É uma regressão
linear de duas variáveis, não aprendizado de máquina.

A colinearidade medida entre as duas contagens é **0,536** — alta, porque no
primeiro stint elas coincidem, mas suficientemente abaixo de 1 para separar os
coeficientes. A calibração recusa a amostra se passar de 0,999.

### Coeficientes obtidos

| Parâmetro | Valor | Origem |
| --- | ---: | --- |
| Combustível | **−52,35 ms** por volta de corrida | calibrado |
| Pneu (MEDIUM) | **+30,84 ms** por volta de stint | calibrado |
| Penalidade de largada | **782,4 ms** por posição de grid | calibrado |
| Ruído por volta (σ) | **253,7 ms** | calibrado |
| Assimetria do ruído | 0,000 | calibrado |
| Risco de abandono | **0,00258** por volta | calibrado |
| Escalonamento das paradas | **6,16 voltas** (desvio típico) | calibrado |
| Perda de boxes | **20 circuitos**, 18,9 s (Spa) a 23,4 s (mediana) | calibrado |
| Divisão SOFT/MEDIUM/HARD | ×1,6 / ×1,0 / ×0,6 e ∓450 ms | **hipótese** |
| Tráfego | 400 ms até 1,5 s de intervalo | **hipótese** |

### Verificação externa independente

O valor do combustível **não foi ajustado para bater com nada**: saiu da
regressão sobre as voltas. Comparando com a física publicada da Fórmula 1, que
não entrou em momento algum na calibração:

```
consumo típico            ~1,8 kg por volta
sensibilidade ao peso     ~0,030 s por kg
efeito esperado           ~0,054 s por volta  =  54 ms
efeito calibrado                                 52,35 ms      → 96,9% de acordo
```

A degradação de 0,031 s/volta também cai na faixa publicada (0,03–0,10 s/volta),
na extremidade baixa — coerente com uma média sobre todos os compostos e
circuitos.

Essa concordância é o argumento mais forte de que o método identifica o que diz
identificar, e não um artefato da amostra.

---

## 5. Três defeitos encontrados, com a evidência que os revelou

### 5.1 Perda de boxes inflada 6,1× pela média

`loader.py` usava `statistics.fmean(duration_ms)`. A distribuição tem cauda
extrema: paradas sob bandeira vermelha ficam registradas com o carro imóvel por
minutos.

```
fmean  (o que o código usava) : 145,68 s
median (robusto)             :  23,90 s     → 6,1× inflado
```

Com 145 s de perda, qualquer política de estratégia jamais pararia; com o valor
correto, parar duas vezes é ótimo, como na realidade.

> Correção de uma hipótese anterior: numa análise preliminar eu havia afirmado
> que `duration_ms` seria o tempo **parado** (~2–3 s) e não a perda total. A
> medição desmentiu isso — comparando o atraso real das voltas de entrada e
> saída contra o ritmo limpo do piloto, o resultado foi 23,74 s contra 23,48 s
> de `duration_ms`. O campo **é** a passagem pelo pit lane. O defeito real era a
> média, não a semântica.

### 5.2 Degradação sempre zero

`_estimate_degradation` regredia a corrida inteira e aplicava `max(0.0, slope)`.
Como combustível e pneu se cancelam, a inclinação bruta é frequentemente
**negativa** e o truncamento a zerava. O parâmetro existia, era servido pela API
e nunca significou nada.

### 5.3 Estimador within mal especificado — encontrado por um teste

A primeira versão da calibração centrava o **tempo** dentro de cada par
(corrida, piloto), mas regredia sobre número de volta e idade de pneu **brutos**.
Sobra em cada grupo um deslocamento constante que a reta pela origem não absorve,
e os coeficientes saem atenuados.

`tests/test_calibrate_model.py` gera voltas por uma regra conhecida e exige que a
calibração recupere os coeficientes. O teste falhou:

```
esperado −25,0 ms   obtido −20,57 ms
```

Centrando as três variáveis pela média do grupo (transformação within padrão), o
teste passa. No dado real, o efeito da correção foi grande:

```
combustível  −24,01 ms  →  −52,35 ms   (era o valor que discordava da física)
pneu         +41,97 ms  →  +30,84 ms
colinearidade    0,848  →      0,536
```

Ou seja: **foi a correção deste defeito que trouxe o coeficiente para 96,9% de
acordo com a física conhecida.** A versão anterior parecia plausível e estava
errada.

---

## 6. Validação

`scripts/backtest_model.py --seasons 2024 --repeats 10`

O script **recusa** validar sobre uma temporada usada na calibração, a menos que
receba `--allow-calibrated-seasons`. Validar onde se calibrou mede memorização,
não generalização (plano, seção 7.3).

Cada corrida é executada em três cenários sobre o mesmo grid:

- `grid` — chega na ordem em que largou;
- `constant` — o modelo antigo, ritmo constante por carro;
- `model` — o modelo calibrado.

**Um modelo só se justifica se vencer as duas linhas de base.** Essa regra evita
acrescentar mecanismos que apenas aumentam a contagem de classes.

### O que cada linha de base revelou

A linha `grid` acerta o vencedor em **45,8%** das corridas — muito mais que o
modelo (27,9%). Não é um defeito do modelo: é uma propriedade real da Fórmula 1,
em que a pole position converte com frequência alta. Mas a mesma linha tem a
**pior** correlação de ordem geral (0,739 contra 0,804). Ela acerta a ponta e
erra o meio do grid.

Esse contraste só apareceu porque as linhas de base foram calculadas. Sem elas,
0,804 de Spearman pareceria um bom número isolado, sem referência.

### Ajuste de parâmetros

Os únicos parâmetros ajustados por varredura foram os de tráfego, que **não são
observáveis** no Trotman (a fonte não registra distância entre carros volta a
volta). A varredura rodou **apenas em 2022–2023**.

Ela continuava melhorando até 900 ms com limiar de 2,5 s, e esse ganho foi
**recusado**: menos de 2% de MAE em troca de um coeficiente fisicamente
implausível, que passaria a absorver outros fenômenos não modelados. Foi adotado
400 ms até 1,5 s, ancorado na ordem de grandeza publicada para ar sujo.

---

## 7. O resultado incômodo: o abandono aleatório piora a previsão

| Modo | pos MAE | Spearman | DNF sim / real |
| --- | ---: | ---: | ---: |
| Determinístico (`--reliability-factor 0`) | **2,520** | **0,804** | — |
| Estocástico completo | 3,495 | 0,590 | 2,90 / 1,67 |

Duas causas, e as duas são informativas.

**a) O abandono aleatório é intrinsecamente caro para o erro de posição.** Quando
o modelo aposenta um carro e a corrida real aposentou outro, os dois erros
somam: o carro retirado cai ~10 posições e o que realmente abandonou aparece
~10 posições acima. Um modelo com abandono aleatório **sempre** perderá em
previsão pontual para um sem abandono, a menos que acerte *qual* carro quebra —
o que exigiria confiabilidade por carro, dado que não existe na fonte.

**b) 2024 foi uma temporada mais confiável que a era calibrada.**

```
2022–2023 (calibração) : 13,9% dos carros que largaram abandonaram
2024      (validação)  :  8,6%
```

O modelo retira 2,90 carros por corrida porque foi calibrado em 13,9%. Não
"corrigir" isso é deliberado: ajustar o risco para bater com 2024 seria usar o
conjunto de validação para calibrar. O plano já advertia que taxas de DNF
precisam ser segmentadas por era, e este número é a medida desse efeito.

**Consequência prática.** Os dois modos servem a perguntas diferentes, e a flag
`--reliability-factor` os separa:

- **modo determinístico** para prever o desfecho mais provável;
- **modo estocástico** para explorar a distribuição de desfechos possíveis,
  que é o que um simulador de corrida precisa oferecer ao usuário.

---

## 7-B. Integração com o perfilamento da issue #40, e o que foi além dele

A frente #40 (`40-modelagem-dos-dados`) construiu um estimador de **ritmo de
piloto**: comparação por medianas de peso igual dentro de contextos
comparáveis, agregação por evento, indisponibilidade explícita, intervalos
bootstrap. O que ela não construiu foi uma corrida — `simulate_profile_lap`
calcula **uma volta, para um piloto**, e o próprio docstring diz que não há
tráfego, evolução de pneu, ruído nem relógio de voltas repetidas.

As duas frentes respondem a perguntas diferentes e foram unidas aqui.

### O que foi reaproveitado da #40, sem alterá-lo

`estimate_profiles` não depende da origem dos dados: recebe `LapAssessment` já
avaliadas e faz o resto. O adaptador
[sqlite_trotman_profiles.py](../src/f1_simulator/adapters/persistence/sqlite_trotman_profiles.py)
constrói essas avaliações a partir do **Trotman**, o que permite rodar o método
da #40 sem FastF1 instalado nem acesso à rede.

O preço é um contexto mais pobre, e ele fica declarado no próprio dado:
`compound` vale `"UNKNOWN"` e `rainfall` vale `False` — ausência de observação,
não céu limpo confirmado. Nenhuma corrida é afirmada como seca.

### O que isso resolveu

A crítica mais séria ao backtest original era que cada piloto entrava na
simulação com o ritmo observado **no próprio fim de semana validado**. Agora o
ritmo relativo vem apenas de corridas anteriores (`races_before` corta a
corrida-alvo e tudo depois dela), com **98% de cobertura** — 455 de 465
participantes receberam perfil próprio.

### O que foi além da #40

Quatro parâmetros que o perfilamento de pilotos não toca, todos estimados do
Trotman:

| Parâmetro | Resultado | Verificação externa |
| --- | --- | --- |
| **Severidade de pneu por circuito** | 0,30× a 2,50× | Spa e Bahrain no topo; circuitos curtos no fundo |
| **Dificuldade de ultrapassagem por circuito** | 0,30 a 0,95 | **Mônaco e Ímola os mais difíceis; Spa e Losail os mais fáceis** |
| **Confiabilidade por equipe** | 0,64× a 1,39× | Williams e Alpine as que mais quebram; Mercedes e Red Bull as que menos |
| **Razão classificação → corrida** | 1,0542 | O ritmo de corrida é 5,4% mais lento que uma volta de classificação |

A ordenação de ultrapassagem é a validação externa mais forte do conjunto: o
proxy é apenas "quantas posições mudam por volta", e ele coloca Mônaco no
extremo difícil e Spa no extremo fácil sem que ninguém tenha informado isso.

A confiabilidade por equipe responde à limitação estrutural apontada na seção 7:
com um risco único, o motor acertava *quantos* carros quebravam e nunca *quais*.
O efeito é mensurável — no modo estocástico, o erro de posição caiu de 3,495
para 3,411 e o Spearman subiu de 0,590 para 0,616.

### Classificação não é vazamento

A classificação acontece **antes** da largada. Usá-la para estimar ritmo é
legítimo e é a única medida de velocidade específica daquele fim de semana
disponível sem olhar o resultado — algo que um perfil de temporada, por melhor
que seja, não captura: ele não sabe se o carro foi bem justamente naquele
circuito.

A fonte `combined` toma a **média geométrica** das duas, porque cada uma mede o
que a outra não vê: a classificação mede velocidade em uma volta única, o perfil
mede forma sustentada em corrida. A média geométrica é a natural para grandezas
multiplicativas. O resultado bate as duas isoladamente em todas as métricas.

### O que continua faltando da #40

O perfilamento da #40 é **mais rigoroso** que este trabalho em pontos concretos,
e isso deve constar de qualquer comparação honesta:

- filtra voltas por status de pista, clima e flags de qualidade; aqui só existe
  a heurística de 107%, que descarta voltas anômalas sem saber por quê;
- quantifica incerteza com bootstrap; os parâmetros desta calibração são
  estimativas pontuais sem barra de erro;
- recusa em vez de substituir; aqui o `fallback_track` preenche silenciosamente
  circuitos não calibrados, ainda que marcado como `assumed`;
- compara companheiros de equipe, que é a forma limpa de separar piloto de
  carro; a referência usada aqui continua sendo um bloco piloto+carro.

## 7-C. Disputa de posição: bloqueio, ultrapassagem e contato

Até aqui o tráfego era apenas um **imposto de tempo**: um carro em ar sujo
perdia alguns décimos e passava assim mesmo. Duas medições do próprio histórico
mostram que isso não representa o fenômeno.

| Medição (2022–2023) | Resultado |
| --- | --- |
| Pares adjacentes que trocam de posição de uma volta para a seguinte | **7,3%** — em 92,7% das voltas o carro de trás **não** passa |
| Abandonos causados por colisão, dano de colisão, acidente ou rodada | **41%** — quase metade não é falha mecânica |

O modelo antigo não representava nenhuma das duas: passar era consequência
aritmética de ser mais rápido, e todo abandono vinha do mesmo sorteio plano por
volta, igual para quem liderava sozinho e para quem brigava no pelotão.

### Em que resolução isso é possível

O motor avança por volta, então não existe um instante de roda a roda para
simular. O que existe é o **desfecho de uma briga que durou uma volta**: no
início dois carros estão próximos; no fim, ou a ultrapassagem aconteceu, ou não
aconteceu, ou os dois se tocaram. É nessa resolução que
[disputes.py](../src/f1_simulator/domain/disputes.py) opera, em duas fases:

**Fase A — disputas**, da frente para trás. Se o tempo proposto de um carro o
colocaria à frente do que está imediatamente adiante, houve disputa: sorteia-se
a ultrapassagem e, falhando, o carro fica preso. Processar de frente para trás
faz o bloqueio se propagar — um carro preso segura quem vem atrás, e é assim que
emerge um trem de carros, sem ter sido programado.

**Fase B — exclusão física.** Reordena pelo tempo final e impõe um espaçamento
mínimo entre carros consecutivos. É isso que impede dois carros de ocuparem o
mesmo ponto da pista, no domínio do tempo, que é onde o motor vive.

A probabilidade de passar é saturante:

```text
p = (1 - dificuldade_do_circuito) * vantagem / (vantagem + escala)
```

Ela tem três propriedades que uma constante não teria: vantagem nula dá chance
nula; vantagem enorme satura em `1 - dificuldade` e **não** em 1, de modo que
nem um carro muito mais rápido passa garantidamente em Mônaco; e a escala é o
único parâmetro livre.

### Calibração

| Parâmetro | Valor | Como foi escolhido |
| --- | ---: | --- |
| `contact_dnf_share` | 0,412 | **Medido**: fração dos abandonos por contato |
| `collision_probability_per_dispute` | 0,0035 | **Ajustado** para reproduzir a taxa de abandono observada — 2,70 carros/corrida simulados contra 2,70 observados na era calibrada |
| `overtake_advantage_scale_ms` | 1400 | **Escolhido pela física**, não pelo ótimo da métrica |
| `minimum_gap_ms` | 700 | Hipótese: distância de perseguição plausível |

A escala merece explicação, porque a varredura preferia outro valor. Com
dificuldade mediana, um carro 0,5 s/volta mais rápido passa em:

```
escala  600 ms -> 22,7% por volta  ->  ~4 voltas
escala 1400 ms -> 13,2% por volta  ->  ~8 voltas
escala 3000 ms ->  7,1% por volta  -> ~14 voltas
```

3000 ms minimizava o erro de movimentação, mas exigiria catorze voltas para
resolver meia dúzia de décimos de vantagem — irreal. 1400 ms foi adotado por
ficar na faixa defensável, ao custo de um ajuste ligeiramente pior.

O contato passou a ser **endógeno ao tráfego**: ele só pode ocorrer durante uma
disputa. Um carro em ar livre não bate. Em troca, o risco por volta perdeu a
parcela de contato (`mechanical_hazard_per_lap()`), para o mesmo fenômeno não
ser contado duas vezes.

### O que isso custa, medido em 2024

| Configuração | pos MAE | Spearman | vencedor | trocas/volta (real 3,38) | DNF (real 1,67) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sem disputa, sem abandono | **2,716** | **0,761** | 47,5% | 4,30 | 0,00 |
| Bloqueio + exclusão + contato | 3,084 | 0,669 | 40,4% | **3,85** | 0,99 |
| Completo (+ falha mecânica) | 3,537 | 0,572 | 38,8% | 3,71 | 2,70 |

**O bloqueio aproxima a movimentação da real** — 4,30 trocas por volta caem para
3,85, contra 3,38 observadas — e custa cerca de 3% de erro de posição. O contato
e a falha mecânica custam bem mais, pelo mesmo motivo estrutural da seção 7:
retirar o carro errado soma erro dos dois lados.

A flag `--no-disputes` liga e desliga o mecanismo, de modo que a escolha entre
realismo de movimentação e precisão de previsão fica explícita e mensurável, em
vez de embutida no motor.

### O que continua fora

Sem resolução abaixo da volta, não há como representar onde na pista a disputa
aconteceu, DRS e vácuo (o modelo cobra o ar sujo mas nunca devolve o tow), nem
distinguir quem foi o culpado de um contato — os dois carros correm o mesmo
risco. Também não há dano parcial: o contato ou retira o carro, ou não acontece.

## 8. O que este trabalho NÃO demonstra

- **Não prevê ritmo.** Cada participante entra na simulação com o ritmo de
  referência observado no próprio fim de semana. O backtest avalia se a dinâmica
  de corrida reproduz o desfecho **quando o ritmo é conhecido** — não se o
  projeto prevê uma corrida futura.
- **Não reproduz estratégia de pneus real.** O Trotman v128 não registra
  composto. O cenário escolhe os compostos; o que é comparado com a realidade é o
  **número de paradas** (1,84 simulado contra 1,78 real), que está registrado.
- **A divisão entre compostos é hipótese**, não calibração. Todos os
  `CompoundParameters` carregam `origin="assumed"`, e um teste garante isso.
- **Não há clima, safety car nem bandeira.** O filtro de 107% remove voltas
  anômalas, mas não identifica a causa. Nenhuma volta é rotulada como SC/VSC.
- **Não separa piloto de carro.** O ritmo de referência é do conjunto
  piloto/equipe, como já registrado em `docs/contrato-perfil-simulacao.md`.
- **Peso, potência e aerodinâmica continuam fora.** Não existem na fonte e não
  foram inventados.

---

## 9. Como reproduzir

```bash
python scripts/download_trotman.py
python scripts/ingest_trotman.py --all-tables --output data/curated/history.sqlite
python scripts/calibrate_model.py --database data/curated/history.sqlite --seasons 2022 2023 --output data/parameters/model-v1.json
python scripts/backtest_model.py --database data/curated/history.sqlite --parameters data/parameters/model-v1.json --seasons 2024 --repeats 10
python -m unittest
```

Aplicação completa: `docker compose up --build`, depois
`POST /simulation/load {"race_id": 1141}` e `POST /simulation/simulate`.
A rota aceita `?seed=` e `?stops=`; a mesma semente reproduz exatamente a mesma
corrida.

---

## 10. Próximos passos sugeridos

1. **Confiabilidade por equipe** — o histórico permite estimar taxa de abandono
   por construtor. Acertar *qual* carro quebra é o que tornaria o modo
   estocástico competitivo em previsão pontual.
2. **Composto e stint reais** via FastF1, já autorizado pelo ADR 0005. Tornaria
   `COMPOUND_HYPOTHESIS` calibrado em vez de assumido.
3. **`tyre_severity` por circuito** — hoje vale 1,0 em todos; o histórico
   permite estimá-la por circuito como já é feito com a perda de boxes.
4. **Estratégia reativa** — `TyreLifeStrategy` existe e não é usada pelo
   cenário padrão. Comparar as duas políticas é um experimento pronto.
5. **Recalibrar incluindo 2024** quando outra temporada assumir o papel de
   reserva. A reserva atual está consumida por este relatório.
