# Pneus: sensibilidade às janelas após retomada de sessão

18/09/2026 · #63 · `63-modelagem-pneus`.

**Resultado:** excluir uma janela de duas voltas após retomadas corrige grandes
distorções locais com custo pequeno de cobertura, mas não transforma tendências
líquidas em coeficientes causais de desgaste. A regra permanece candidata, sem
alterar o estudo anterior ou os parâmetros consumidos pelo core.

## Protocolo

Mesmas 18 sessões de desenvolvimento, filtros, mínimos e métodos do
[estudo anterior](analise-pneus-2024.md). O baseline incorporado no novo JSON
foi comparado e é idêntico ao anterior. Não foram adquiridos dados novos.

Detectamos `Aborted → Started` pela linha temporal canônica de
`session_status_events`, ignorando largada inicial e `Started` repetido. Para
cada piloto, a primeira volta **registrada com início >= instante de retomada**
serve de âncora, antes de qualquer filtro de qualidade. Contam-se diferenças de
número de volta, preservando lacunas e sem reiniciar a janela na troca de pneus.
Uma volta que atravessa o instante da retomada também é marcada separadamente.
Sem observação posterior não se inventa âncora. A primeira volta registrada
não garante ser a primeira física caso o feed esteja incompleto.

Comparamos janelas 0 (baseline), 1, 2, 3 e 5. Uma janela 2 exclui a âncora e a
volta seguinte, inclusive quando a âncora já era excluída pelo filtro original.
A seleção foi feita como análise de sensibilidade, não otimização de coeficiente.
Relógios de status ausentes ou estados simultâneos conflitantes geram erro.

**Limite:** este detector não identifica retorno de SC/VSC à bandeira verde
quando a sessão permanece `Started`; não é um detector universal de relargada.
Também não identifica automaticamente largada parada versus lançada. Essas
situações exigem estudo adicional de track status e mensagens de direção.

## Retomadas encontradas

| Evento | Primeira volta iniciada após retomada nos pilotos observados | Pilotos sem âncora posterior |
| --- | ---: | ---: |
| Japão | 2 | 2 |
| Mônaco | 2 | 4 |
| São Paulo | 33 | 2 |

“Sem âncora” informa ausência de observação posterior, não classifica motivo de
abandono. A análise mantém todos esses registros no baseline.

## Cobertura e tendências

| Janela | Voltas aprovadas restantes | Retiradas adicionais | Ajustes secos |
| --- | ---: | ---: | ---: |
| 0 | 17.069 | 0 | 768 |
| 1 | 17.069 | 0 | 768 |
| 2 | 17.036 | 33 | 768 |
| 3 | 16.986 | 83 | 768 |
| 5 | 16.909 | 160 | 767 |

Janela 1 não muda nada: as primeiras voltas já estavam excluídas. Janela 2
retira seis voltas aprovadas no Japão, 16 em Mônaco e 11 em São Paulo; as 22
primeiras são secas e as de São Paulo não são secas. Custo total: 0,19% das
voltas aprovadas originais. Nenhum mínimo de ajuste seco é perdido nessa janela.

Mediana das inclinações entre stints (ms/volta de idade), baseline → janela 2:
SOFT +32,49 → +32,49; MEDIUM +23,19 → +23,19; HARD +6,42 → +7,07.
HARD passa de 170 para 168 inclinações negativas entre 370 ajustes. O efeito
local forte não exige grande mudança na mediana global, pois poucos stints
são afetados. Nos 20 ajustes secos pareados que perdem voltas na janela 2,
a mediana da mudança absoluta da inclinação é 8,93 ms/volta; há casos extremos.

## Casos que explicam o efeito

Inclinação OLS em ms/volta de idade:

| Piloto / evento / stint | Baseline | Janela 2 | Janela 3 | Janela 5 |
| --- | ---: | ---: | ---: | ---: |
| Gasly / Japão / 2 | −1.074,6 | +201,6 | +205,6 | +152,3 |
| Ocon / Japão / 2 | −807,0 | +85,6 | +75,2 | +95,3 |
| Bottas / Mônaco / 2 | −476,6 | −242,7 | −245,0 | −195,0 |

A volta 3 de Gasly tem 138.362 ms e a de Ocon 140.237 ms, contra voltas
posteriores próximas de 100.000 ms. Ambas passavam pelos filtros originais;
a janela 2 as marca pelo contexto temporal, não por serem tempos extremos.
A inclinação robusta original de Gasly era +168,5 ms/volta, coerente em sinal
com as variantes sem a volta inicial lenta.

MAE linear dentro da amostra, baseline → janela 2: Gasly 5.970 →335 ms;
Ocon 5.405 →210 ms; Bottas 1.051 →206 ms. São amostras diferentes e ajustes
na própria amostra: a redução não é ganho de previsão em teste independente.
Bottas continua melhorando ao longo do stint; a retomada não explica toda
inclinação negativa. Combustível, pista e tráfego permanecem confundidos.

## O que acontece com o diagnóstico de aquecimento

Contraste pós-pit: mediana das posições 2–3 menos 5–8, depois mediana por evento
e entre eventos. Mantidas as posições originais: não substituímos uma volta
retirada pela próxima aprovada.

| Pneu novo | Baseline: stints/eventos, contraste | Janela 2: stints/eventos, contraste |
| --- | --- | --- |
| SOFT | 17/7, −491,5 ms | 17/7, −491,5 ms |
| MEDIUM | 75/14, +3,5 ms | 69/14, −58,625 ms |
| HARD | 244/16, −4,0 ms | 237/15, −20,5 ms |

O contraste fica indisponível quando perde a cobertura exigida nas primeiras
voltas. Portanto parte da mudança é **seleção de stints/eventos**, não efeito
medido sobre o mesmo pareamento. Janelas 3 e 5 mantêm esses mesmos resultados
agregados para pneus novos. Não emerge uma penalidade positiva uniforme de
aquecimento. Não foram feitos testes de hipótese ou calculados intervalos de
confiança; os exemplos foram escolhidos para diagnosticar problemas já vistos.

## Decisão proposta e próximos passos

- Tratar uma janela de **duas voltas após Aborted→Started** como candidata a
  exclusão contextual no próximo protocolo. Ela resolve os casos extremos
  investigados com custo menor que 3/5, mas isso não prova duração universal
  de estabilização nem ótimo estatístico.
- Não adotar cinco voltas automaticamente: perde 160 observações e um ajuste,
  sem benefício universal demonstrado. Diferenças por stint permanecem.
- Não zerar inclinações negativas nem exportar estes slopes ao core como
  desgaste calibrado. A filtragem melhora a qualidade do recorte, não separa
  efeitos físicos.
- Próxima investigação: SC/VSC, mensagens de direção e volta da relargada;
  comparar estimadores robustos e OLS após filtros contextuais; separar eventos
  para avaliar o método antes de fixar coeficientes. O estudo não modifica o
  ranking/perfilamento de pilotos nem o core publicado pelo colega.

## Reprodução e verificação

```bash
pipenv run python -B scripts/analyze_tyre_restarts.py \
  --database data/curated/history-profile-development-2024.sqlite \
  --plan configs/profile-evaluation-2024-expanded.json
```

Publicação atômica em nova pasta `data/curated/tyre-restarts/`: `analysis.json`
com baseline, marcações e variantes; `anchors.csv`, `changes.csv` e dois PNGs.
`--without-plots` dispensa Matplotlib. Nenhum resultado anterior é sobrescrito.

Execução local:
`data/curated/tyre-restarts/restarts-e9b6fa63723c403fa21b3aa5b001a37a/`.
[Casos antes/depois](../data/curated/tyre-restarts/restarts-e9b6fa63723c403fa21b3aa5b001a37a/casos-relargada.png)
e [cobertura/tendências](../data/curated/tyre-restarts/restarts-e9b6fa63723c403fa21b3aa5b001a37a/sensibilidade.png).
Links dependem dos artefatos locais; outro clone deve executar o comando.

Testes cobrem largada inicial, retomadas repetidas/múltiplas, conflitos de status,
voltas atravessando a retomada, lacunas, âncora excluída, ausência de observações
e preservação das variantes sem retomada. Suíte: 177 testes, sem falhas, 13
ignorados. Ruff aprovado; gráfico de casos inspecionado. Sem commits ou push.
