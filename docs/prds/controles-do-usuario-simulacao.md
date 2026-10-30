# Controles do usuário sobre a simulação: largada, grid, voltas, seed e torneio salvo

**Status:** aprovado pelo usuário em 2026-10-30; em implementação.
**Origem:** lista de pendências do usuário (a pit lane já foi entregue no PR #103).
**Issues:** #105, #106, #107, #108 e #109 (ver seção 7).

## 1. Problema

O frontend sempre usa o motor `detailed`. Hoje:

- a penalidade calibrada de largada (`grid_penalty_ms_per_position = 782,4 ms`,
  `data/parameters/model-v1.json`) deixa P20 cerca de 15 s atrás antes da
  primeira volta; `docs/modelagem-heuristica.md` registra a pole vencendo 21 de
  40 corridas em Spa. No 2D, cada carro larga 10 m atrás do anterior, embora o
  código descreva um grid em filas de dois;
- a ordem do grid já chega ao motor, mas a tela não permite reordenar e o
  `PATCH /catalog/grid` só altera atributos;
- toda pista nova começa com 69 voltas fixas no frontend;
- a seed existe só no grid; todas as etapas de um torneio usam a mesma seed e o
  mesmo fluxo `"race"`, a sequência automática de pistas usa
  `random.Random(nome_do_torneio)` e não há campo de seed na interface;
- não existe torneio salvo: o plano, o grid e os resultados vivem só na memória
  do frontend.

## 2. Decisões do usuário (2026-10-30)

1. **Largada:** manter `782,4 ms` como valor calibrado e acrescentar um fator de
   atenuação separado, rotulado `heuristic`, versionado e escolhido por análise
   de sensibilidade com seeds fixas. Alvo: pole vencendo perto de 40–45% das
   corridas (ordem de grandeza histórica, usada como hipótese, não como
   calibração). Corrigir o grid 2D para filas de dois. Não somar a penalidade
   temporal ao 2D (seria contagem dupla).
2. **Ordem do grid:** botões ↑/↓ na tela do grid e `PATCH /catalog/grid` com
   uma ordem que seja permutação exata do grid atual, preservando atributos,
   perfis e seed.
3. **Voltas:** padrão por pista = máximo de voltas completadas na corrida mais
   recente do circuito no Trotman v128 (`latest_observed_race`); sem histórico,
   menor número de voltas completas acima de 305 km (Mônaco: 260 km), rotulado
   `assumed_distance_rule`. O padrão vale só para pista ainda não configurada;
   edição do usuário nunca é sobrescrita.
4. **Seed:** campo de seed digitável; mesma seed + mesmos inputs = mesmo
   resultado; etapas distintas recebem fluxos distintos.
5. **Torneio salvo:** salvar cenário **e** resultados. Reabrir mostra o torneio
   sem recalcular; reexecutar roda as corridas de novo a partir do cenário
   congelado, sem refazer ETL, catálogo ou atributos.

## 3. Contratos compartilhados

### 3.1 Seeds (item 5; consumido pelos itens 1 e 4)

- `grid_seed`: o `seed` já existente de `POST /catalog/grid`; controla seleção
  de pares e atributos.
- `tournament_seed`: inteiro em `[0, 2**53 - 1]`, opcional na configuração do
  torneio; vazio gera uma seed aleatória que é mostrada ao usuário.
- O RNG de cada etapa é derivado **no núcleo** (não no frontend) a partir de
  `(tournament_seed, stage_index)`, de forma documentada e estável.
- `RaceSetupRequest` ganha campos opcionais de seed e índice de etapa. Ausentes,
  o comportamento atual (seed do grid) é preservado.
- A resposta da corrida devolve as seeds efetivamente usadas.
- A ordem automática das pistas passa a depender da `tournament_seed`.
- Garantia: reprodutível com a mesma versão de código, Python, parâmetros e
  dados; não entre versões.

### 3.2 Ordem do grid (item 2)

`PATCH /catalog/grid` aceita `order` opcional (lista de IDs do grid atual) junto
dos `overrides`. Rejeita tamanho diferente, duplicatas, ausências e IDs
desconhecidos (HTTP 422). Escreve `current-grid.json` atomicamente.

### 3.3 Voltas padrão (item 3)

`GET /simulation/tracks` passa a devolver `default_laps`,
`default_laps_source` (`latest_observed_race` | `assumed_distance_rule`) e, no
primeiro caso, a corrida de origem (ID, temporada, rodada).

### 3.4 Torneio salvo (item 4)

Formato JSON versionado (`schema_version`) em diretório de dados do backend,
fora do Git: grid congelado (ordem, atributos, `grid_seed`),
`tournament_seed`, motor, regras, etapas (circuito, voltas, clima, seed
derivada), proveniência (versões de parâmetros, hash de geometria) e resultados
(corridas e classificação). Precisa de ADR novo que revise o ADR 0006.

## 4. Fronteiras

- Regras e derivação de seeds ficam em `src/f1_simulator`; o frontend não
  importa o pacote e fala só HTTP.
- Persistência do torneio é adaptador (port no núcleo, JSON na borda).
- Parâmetros escolhidos (fator de largada, regra dos 305 km) são rotulados
  `heuristic`/`assumed` e aparecem em `assumptions`; nunca como calibrados.

## 5. Ordem de implementação

1. Em paralelo, cada um em sua branch a partir da `develop`: seed (5), ordem do
   grid (2), voltas (3) e largada (1).
2. Depois do merge dos quatro: torneio salvo (4), que congela os contratos acima.

## 6. Critérios de sucesso

- Mesma `tournament_seed` e mesmo cenário reproduzem o torneio inteiro; seeds
  diferentes mudam o resultado; etapas repetidas no mesmo torneio diferem.
- Reordenar no grid muda a largada sem alterar atributos.
- Cada pista abre com voltas plausíveis e a origem do valor é rastreável.
- A taxa de vitória da pole, medida com seeds fixas, fica na faixa escolhida e
  o fator está documentado em `docs/modelagem-heuristica.md`.
- Um torneio salvo reabre sem chamar `/catalog/grid/run` e reexecuta com o
  mesmo resultado.
- Suíte de testes passando em cada commit.

## 7. Issues

- #105 — seed digitável e reprodução determinística (item 5);
- #106 — reordenar o grid de largada (item 2);
- #107 — número de voltas padrão por pista (item 3);
- #108 — impacto da posição de largada (item 1);
- #109 — salvar e reabrir/reexecutar torneio (item 4).
