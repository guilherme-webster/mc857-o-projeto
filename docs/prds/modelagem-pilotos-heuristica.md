# Integração do motor calibrado com perfis, paradas e bandeiras heurísticos

**Status:** implementado em 2026-10-03 (v3.1). Valores atuais em
[`docs/modelagem-heuristica.md`](../modelagem-heuristica.md); decisão no
[ADR 0008](../adr/0008-modelagem-heuristica-sobre-o-motor-calibrado.md).
**Data:** 2026-10-03
**Issues:** #67 (Modelagem pilotos, filha de #61). Integra o trabalho da #40
(`40-modelagem-corrida-calibrada`, de @DaviGabrielBC), que não chegou à
`develop`.
**Branch de trabalho:** `67-modelagem-pilotos`
**Execução:** agentes Codex (`gpt-5.6-sol`) implementam fatias bem delimitadas;
eu reviso, rodo as verificações e integro. A integração da fatia 0 faço
diretamente, porque exige julgamento sobre código de três autores.

## 1. Contexto

- O professor aceita modelagem **heurística**: não é preciso embasar cada efeito
  em dados. O grupo preferiu esse caminho.
- O colega da #40 construiu um motor de corrida detalhado e calibrado, mas não
  conseguiu integrá-lo ao restante do projeto. Esta fatia faz essa integração.

## 2. Histórico deste plano

| Versão | Mudança |
|---|---|
| v1 (25/09) | Notas 0–100 e um mecanismo próprio de ultrapassagem sobre o `simulate_race` simples. |
| v2 (25/09) | Mecanismo próprio descartado: os perfis passam a modular o motor do colega. |
| v3 (03/10) | Revisto diante da `develop` atual, que ganhou **atributos de piloto por arquétipo** (#90), **grid a partir do catálogo histórico** e **modelo de clima** (#91), e removeu a série livre e o caminho histórico do backend. As seis notas da v2 foram trocadas pela extensão dos atributos que já existem. Acrescentados safety car, bandeiras e paradas heurísticas. A disputa segue a fórmula planejada nos slides do colega. |
| v3.1 (03/10) | Seção 4.4 revista após comparação com o funcionamento real: amarela reduz em vez de proibir ultrapassagem, abandono mecânico frequentemente sem intervenção, vermelha ligada à gravidade da batida, acidentes individuais, relargada com mais disputa, bandeira azul e frequência-alvo de neutralizações. |

## 3. Estado de partida (verificado em 03/10)

### 3.1 `develop` (`b9170b6`, 255 testes OK, 35 ignorados)

- **Atributos de piloto** (`domain/driver_attributes.py`): arquétipos
  `aggressive`, `balanced` e `conservative`, com faixas para `pace_offset_pct`,
  `consistency_factor` e `tyre_management_factor`. Os valores são sorteados com
  semente (`application/generate_attributes.py`), podem ser editados à mão
  (`apply_overrides`) e são rotulados `assumed`.
- **Grid** (`application/build_grid.py`): pares piloto@equipe do histórico,
  escolhidos à mão ou por sorteio.
- **Corrida** (`POST /catalog/grid/run`): usa o `simulate_race` **simples**, com
  volta nominal fixa de 90 s, sem comprimento de pista, combustível, paradas,
  disputas ou abandonos. `track_id` e `weather` são apenas devolvidos na
  resposta.
- **Clima** (`domain/weather.py`, #69): umidade e água na pista por volta,
  isolado, sem efeito no tempo de volta.
- **Removidos:** `POST /simulation/series/simulate`, o caminho histórico
  (`/simulation/load` e `/simulate`), `loader.py` e `models.py`.

### 3.2 `40-modelagem-corrida-calibrada` (`197c361`, 288 testes OK, 13 ignorados)

- `simulate_detailed_race`: grid como atraso inicial, combustível, pneu por
  composto, tráfego, paradas, ruído, disputas (bloqueio, ultrapassagem,
  espaçamento de 700 ms, contato) e abandono mecânico ponderado pela equipe.
- `data/parameters/model-v1.json`: parâmetros calibrados em 2022–2023, por
  circuito (perda de boxes, dificuldade de ultrapassagem) e por equipe
  (confiabilidade).
- Estratégias de parada fixas: `PlannedStopStrategy` (stints iguais) e
  `TyreLifeStrategy` (vida típica do composto).
- **Não há** safety car, VSC, bandeiras nem perfis de piloto no motor.

### 3.3 O que falta do planejamento do colega (slides)

Os slides "Disputas" descrevem um modelo que **ainda não foi implementado**: o
código usa `p = (1 − dificuldade) · v / (v + escala)`, sem perfil. O planejado
era:

```
Pressão     P = Δritmo × proximidade × agressividade      (atacante)
Resistência R = dificuldade da pista × firmeza do defensor (defensor)
P(passar)   = P / (P + R)          sorteio a cada volta
desfecho: ultrapassa · fica bloqueado atrás · contato retira um dos dois
```

"Ritmo e consistência alimentam o ataque; firmeza sob pressão alimenta a
defesa. A distância modula a pressão e a pista escala só a resistência."

### 3.4 Conflitos entre `develop` e a branch do colega (`git merge-tree`)

| Arquivo | Natureza | Resolução proposta |
|---|---|---|
| `domain/random_source.py` | O colega usa `uniform01()` e `standard_normal()` sem rótulo; a `develop` usa `standard_normal(label)`, `spawn`, `uniform_index` e `uniform_float`. | `RandomSource` único com `uniform01(label="")` e `standard_normal(label="")`. As chamadas dos dois lados continuam válidas, e o `FrozenRandomSource` do colega é preservado. |
| `domain/tyres.py` | Dois modelos: `TyreSet`/`tyre_penalty_ms` (colega) e `TyreModelParameters`/`TyreState` (`develop`). | Os dois convivem com nomes distintos. O do colega é o do motor detalhado. |
| `domain/race_simulation.py` | A `develop` estendeu o `simulate_race`; o colega acrescentou `simulate_detailed_race`. | Manter as duas extensões. |
| `backend/app/loaders/loader.py`, `models.py` | Removidos na `develop`, modificados pelo colega. | Aceitar a remoção. O caminho histórico não existe mais. |
| `TOBEDEFINED/service_race_simulation.py` | A `develop` moveu o serviço para cá; o colega o modificou no lugar antigo. | Manter a versão da `develop`. O motor detalhado passa a ser servido pelo `/catalog/grid/run`. |
| `backend/app/routers/simulation.py` | Rotas divergentes. | Versão da `develop`. |

As suítes dos dois lados precisam passar após a integração.

## 4. Desenho

### 4.1 Motor único da corrida

O `/catalog/grid/run` passa a usar `simulate_detailed_race`, com:

- **Referência da volta:** comprimento da pista (geometria do catálogo) ×
  ritmo de referência assumido em ms/km, ajustado pelo `pace_offset_pct` do
  piloto. Substitui os 90 s fixos, que ignoram a pista.
- **Parâmetros de circuito:** `model-v1.json` pelo `track_id`. Circuito sem
  calibração usa o `fallback_track`, já marcado como `assumed`.
- **Ordem de largada:** a ordem do grid montado.
- O `simulate_race` simples continua existindo, como linha de base.

### 4.2 Atributos de piloto (extensão do que já existe)

Os três atributos atuais continuam iguais e passam a atuar no motor detalhado:

| Atributo | Efeito |
|---|---|
| `pace_offset_pct` | Referência da volta |
| `consistency_factor` | Desvio do ruído por volta |
| `tyre_management_factor` | Degradação do pneu e momento da parada |

Dois atributos novos, exigidos pela disputa dos slides, com faixas por
arquétipo:

| Atributo | Papel | `aggressive` | `balanced` | `conservative` |
|---|---|---|---|---|
| `aggression` | Multiplica a pressão do atacante e o risco de contato | 1,20–1,50 | 0,90–1,10 | 0,60–0,85 |
| `composure` (firmeza sob pressão) | Multiplica a resistência do defensor | 0,85–1,05 | 0,90–1,10 | 1,05–1,30 |

Todos são `assumed`, editáveis pelo `PATCH /catalog/grid` e sorteados com
semente, como hoje.

**Perfis fictícios nomeados:** um arquivo
`configs/drivers/perfis-ficticios.json` fixa arquétipo e valores de pilotos
específicos (por exemplo Verstappen: `aggressive`, ritmo alto, agressividade
alta). Esses valores entram com origem `preset`, que se soma a `generated` e
`manual`. O arquivo declara que são **caracterizações fictícias**, não
afirmações sobre pessoas reais, e não usa traços depreciativos.

**Neutralidade:** um piloto sem atributos se comporta exatamente como no motor
do colega. Isso é testado.

### 4.3 Disputa, conforme os slides

```
proximidade = 1 − gap / limiar_disputa                 (0 a 1)
P = (vantagem_ms / escala_ms) × proximidade × aggression_atacante
    × fator_consistencia_atacante
R = dificuldade_circuito × composure_defensor × k_resistencia
p_passar = P / (P + R)
```

- Vantagem nula dá P = 0 e nenhuma passagem. Dificuldade alta nunca leva a 100%.
- `k_resistencia` é ajustado (`heuristic`) para que, com perfis neutros, a taxa
  de trocas entre vizinhos fique perto da medida pelo colega (7,3% por volta).
- **Contato:** a probabilidade calibrada é multiplicada pela agressividade
  média do par. Se houver contato, **sorteia-se qual dos dois abandona**, como
  no slide. O código atual sempre retira o atacante.
- A substituição da fórmula do colega é registrada no ADR 0008. A fórmula
  antiga continua acessível como opção, para o backtest dele seguir
  reproduzível.

### 4.4 Safety car, VSC e bandeiras (novo `domain/race_control.py`)

Revisto em 03/10 depois de comparar com o funcionamento real (seção 4.4.1).

#### 4.4.1 Referência real (resumo)

- **Amarela:** local, vale só no trecho do incidente; proíbe ultrapassar ali e
  custa poucos décimos.
- **Azul:** o retardatário deve ceder ao carro que vai dar volta nele.
- **VSC:** todos 30–40% mais lentos, sem ultrapassagem, intervalos quase
  preservados, 1–3 voltas, parada mais barata.
- **SC:** pelotão agrupado atrás do carro de segurança, intervalos apagados, sem
  ultrapassagem, 3–6 voltas que contam para a corrida, "parada barata",
  relargada lançada com mais disputa e mais risco.
- **Vermelha:** corrida interrompida, troca de pneu grátis, ordem do momento da
  interrupção, relargada atrás do SC ou parada.
- **Frequência de referência** (amostra de 2024 do repositório, estudo da #63):
  10 períodos de SC/VSC em 8 de 18 corridas (cerca de 0,6 por corrida) e
  vermelha com relargada em 3 de 18.

#### 4.4.2 Gatilhos

Um incidente nasce de três fontes:

1. **Contato em disputa** (motor do colega, com a mudança da seção 4.3).
2. **Acidente individual** (novo): chance pequena por carro e por volta, maior
   na primeira volta e na volta da relargada. Antes, só se batia em disputa, e
   um líder isolado nunca rodava.
3. **Abandono mecânico** (motor do colega).

| Incidente | Resposta sorteada (`heuristic`) |
|---|---|
| Batida (contato ou acidente individual) | SC, VSC ou amarela; uma fração pequena (5–10%) é grave e gera vermelha |
| Abandono mecânico | **Nenhuma intervenção** como desfecho mais provável (carro recolhe ou para em área segura); depois amarela e VSC |

As probabilidades são ajustadas para que, em muitas sementes, a simulação gere
**cerca de 0,6 neutralização (SC ou VSC) por corrida** e **vermelha em torno de
1 a cada 6 corridas**. É um alvo verificável por teste de Monte Carlo, não uma
calibração.

#### 4.4.3 Estados e efeitos

| Estado | Efeito no motor |
|---|---|
| Amarela | Uma volta com chance de ultrapassagem reduzida (por exemplo ×0,5) e perda de poucos décimos. Não proíbe a disputa na pista toda, porque na realidade a amarela é local e o motor não tem setores |
| VSC | 1–3 voltas, todos +40% no tempo de volta, intervalos preservados, sem disputa |
| SC | 3–5 voltas que contam para a corrida, pelotão comprimido com espaçamento mínimo, sem disputa |
| Relargada (após SC ou vermelha) | Na volta seguinte, chance de disputa e de contato aumentada |
| Vermelha | Ordem congelada, troca de pneu sem custo, relargada atrás do SC (pelotão agrupado) |

#### 4.4.4 Bandeira azul

O carro com uma volta a menos **sempre cede**: não bloqueia, não disputa e não
gera contato com o carro que vai dar volta nele. Isso corrige o motor do
colega, em que um retardatário podia segurar o líder.

#### 4.4.5 Demais regras

- Parar sob SC ou VSC custa só uma fração da perda de boxes (por exemplo 50%
  e 70%).
- Combustível e pneu continuam envelhecendo nas voltas neutralizadas.
- A resposta lista cada evento: volta, tipo, duração e causa.
- Fora: bandeira laranja, desdobramento de retardatários sob SC, amarela dupla
  como estado separado e efeito da chuva sobre os incidentes.

### 4.5 Paradas heurísticas (nova `HeuristicPitStrategy`)

- Para quando a perda acumulada do pneu velho até o fim da corrida supera a
  perda de boxes mais uma margem. O `tyre_management_factor` adia ou antecipa.
- **Oportunista:** sob SC ou VSC, para se a vida restante do pneu estiver abaixo
  de um limiar.
- Sem paradas nas últimas N voltas, salvo pneu fora do suporte.
- Regra de dois compostos em pista seca.
- Pequena variação sorteada por piloto, para as paradas não ficarem
  sincronizadas.

### 4.6 Fora de escopo

- **Efeito do clima no tempo de volta:** o modelo de clima é da #69 e sua
  integração da #68 (@mauricio-vasconcellos, @Jmvjr). Não mexo sem combinar.
- **Telas do Arcade:** a corrida só é exposta pela API.
- DRS, vácuo, culpa no contato, dano parcial, pit lane congestionado.
- Recalibrar o `model-v1.json`.

## 5. Fatias

Cada fatia deixa a suíte verde e vira um commit `tipo(escopo): resumo`.

| # | Fatia | Quem | Depende de |
|---|---|---|---|
| 0 | Merge da `develop` na `67`; merge da `40-modelagem-corrida-calibrada` com os conflitos da seção 3.4 resolvidos | Eu | — |
| 1 | `aggression` e `composure` nos atributos, arquétipos, geração, `PATCH` e perfis fictícios nomeados | Codex | 0 |
| 2 | Disputa P/(P+R) dos slides, contato que retira um dos dois, ajuste de `k_resistencia` | Codex | 0 |
| 3 | `domain/race_control.py`: SC, VSC, amarela, vermelha, relargada, acidente individual e bandeira azul | Codex | 0 |
| 4 | `HeuristicPitStrategy` | Codex | 0 |
| 5 | Ligação: o motor detalhado aplica atributos, controle de corrida e paradas; o `/catalog/grid/run` passa a usá-lo | Codex, revisão minha | 1–4 |
| 6 | ADR 0008, README, mapa do código e registro na issue #67 | Eu | 5 |

As fatias 1 a 4 mexem em arquivos diferentes e podem rodar em paralelo. A
fatia 5 junta tudo no laço do motor e é sequencial. Cada fatia passa por uma
revisão minha (leitura do diff, testes, verificação de reprodutibilidade) antes
do commit.

## 6. Verificação

- As suítes da `develop` e da branch do colega passam após a integração.
- **Neutralidade:** sem atributos e sem controle de corrida, o motor detalhado
  reproduz o resultado do colega com a mesma semente.
- **Reprodutibilidade:** mesma semente dá a mesma corrida, inclusive os eventos.
- **Probabilidades exatas:** uma fonte falsa com valores conhecidos verifica
  disputas, contatos e acionamento do SC.
- **Monte Carlo** com sementes fixas:
  - o piloto mais rápido vence mais;
  - o agressivo tenta e conclui mais ultrapassagens e se envolve em mais
    contatos;
  - o SC comprime o pelotão e aumenta as paradas oportunistas;
  - Mônaco tem menos ultrapassagens que Spa.
- **Comparação com o histórico** (sanidade, não calibração): trocas por volta,
  paradas e abandonos por corrida em faixas plausíveis.

## 7. Decisões

| # | Decisão | Padrão adotado, salvo objeção |
|---|---|---|
| D1 | Integrar na `67` por merge, preservando a autoria do colega | Sim |
| D2 | Reconciliação da seção 3.4 | Como descrito |
| D3 | Estender os atributos existentes, em vez de criar as seis notas 0–100 da v2 | Sim |
| D4 | Disputa P/(P+R) dos slides substitui a fórmula atual, mantida como opção | Sim |
| D5 | Probabilidades e efeitos de SC, VSC, amarela e vermelha da seção 4.4 | Aprovado (v3.1), ajustável |
| D6 | Clima fora do escopo (pertence à #68/#69) | Sim |
| D7 | Commits na `67`: os dois merges da fatia 0 e um por fatia | Autorizado em 03/10 (sem push) |

## 8. Riscos

- **Integração de código alheio:** o colega deve revisar o merge da fatia 0.
- **Ajuste das heurísticas:** valores ruins geram corridas caóticas ou
  estáticas. Mitigação: neutralidade, testes de Monte Carlo e a comparação de
  sanidade com o histórico.
- **Leitura errada:** perfis e eventos fictícios podem ser tomados como reais.
  Mitigação: origem (`assumed`, `preset`, `heuristic`) em toda resposta.
- **Agentes Codex:** a sessão do Codex já caiu uma vez. Cada fatia é pequena e
  verificada por mim antes do commit.

## 9. Resultado da implementação (2026-10-03)

Commits na `67-modelagem-pilotos`, nesta ordem: integração da `develop` e da
`40-modelagem-corrida-calibrada` (fatia 0); atributos e perfis fictícios
(fatia 1); disputa de pressão e bandeira azul (2); controle de prova (3);
paradas heurísticas (4); ligação no motor (5a); backend no motor detalhado (5b);
dois ajustes de realismo; documentação (6). As fatias 1 a 5b foram implementadas
por agentes Codex (`gpt-5.6-sol`) e revisadas; a fatia 0, os ajustes e a
documentação foram feitos diretamente.

Desvios em relação a este plano, todos aprovados:

- **Fatia 5 dividida** em 5a (motor) e 5b (backend), para reduzir o risco.
- **Bandeira azul corrigida na revisão:** o líder ganhava tempo artificial ao
  dar volta e podia ficar preso atrás do retardatário.
- **Frequência do controle de prova refeita na revisão:** o ajuste do agente
  valia para uma semente só e invertia a proporção SC/VSC nas batidas.
- **Vermelha:** o teto de 10% das batidas (seção 4.4.2) e o alvo de 1 vermelha a
  cada 6 corridas não cabem juntos; o grupo manteve o teto (~1 a cada 10–11).
- **Gestão de pneus amortecida** no motor detalhado (elasticidade 0,4): as
  faixas dos arquétipos faziam os agressivos rápidos terminarem atrás dos
  conservadores lentos. Não estava no plano; decidido após o teste ponta a ponta.
- **Volta de referência por circuito** a partir do histórico: o ritmo único de
  17 s/km dava Mônaco com 56 s. Não estava no plano; decidido após o teste ponta
  a ponta.
- **Abandono na última volta:** com o controle de prova ativo, um carro pode
  abandonar na última volta (no motor calibrado, isso era ignorado).

Pendências: a pole ainda vence com frequência alta; o clima não afeta a corrida;
a interface Arcade não dispara nem reproduz a corrida volta a volta.
