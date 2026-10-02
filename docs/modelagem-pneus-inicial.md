# Modelagem inicial de pneus: estudo e contrato proposto

> Estudo executado: [gráficos, resultados e conclusões de 2024](analise-pneus-2024.md).
> O levantamento abaixo preserva o planejamento inicial.

18/09/2026 · branch `63-modelagem-pneus` · issue #63 (aberta, responsável
@guilherme-webster, filha de #40, ainda sem descrição). Integração futura: #70.
Este documento é uma proposta para discussão e exploração, não um contrato
aceito pelo responsável pelo core nem uma calibração concluída.

## Objetivo desta etapa

Preparar a entrada de parâmetros para evolução determinística dos pneus sem
implementar um segundo motor. A branch parte de `3876dc1`, com o ETL enriquecido,
perfilamento e adaptador de pilotos. Segue CONTRIBUTING e ADRs 0002/0004/0005:
ETL fornece fatos; modelagem estima/configura parâmetros; core mantém estado e
aplica regras. Comunicação local por objetos Python, sem HTTP obrigatório.

## Core encontrado no remoto

Após `git fetch origin`, foi encontrado o commit
[`50c0eed — feat(backend): conecta ao core`](https://github.com/guilherme-webster/mc857-o-projeto/commit/50c0eedc9c71fdfa2a81a6c6222d4a15654a0a17)
em `origin/43-criar-endpoints`. Não foi mesclado nesta branch.

- `src/f1_simulator/domain/race_simulation.py`: `Competitor(driver_id, name,
  lap_time_ms)` e `simulate_race(competitors, total_laps)`. Soma tempo constante
  por piloto, classifica por tempo acumulado e desempata por ID.
- `backend/app/race_store.py`: monta os participantes e chama esse core.
- `backend/app/engine/loader.py`: calcula ritmo pela mediana do quarto mais
  rápido das voltas históricas. Também calcula `degradation_ms_per_lap` por
  regressão de tempo sobre índice de observação, truncando inclinação negativa
  para zero; retorna zero com poucas voltas. Não segmenta composto/stint.
- O campo de degradação não é passado a `Competitor` nessa rota. A existência
  de `CarState.tire_age` no backend não significa evolução de pneus no core.

A tendência provisória mistura trocas de pneu, boxes, combustível e condições;
zero por ausência ou truncamento não identifica desgaste nulo. Proposta: não
promover esse estimador a coeficiente calibrado. A substituição deve ser alinhada
com o colega. O core remoto usa floats e apresenta uma casa decimal de ms;
o microexperimento local usa Decimal e ROUND_HALF_UP em ms inteiros. A política
única de precisão/arredondamento é outra decisão de integração pendente.

## Dados disponíveis e levantamento reproduzível

Leitura pelo `SQLiteHistoryRepository`, sem alterar banco ou dados brutos:
`data/curated/history-profile-development-2024.sqlite`, somente as 18 sessões
`development_sessions` de `configs/profile-evaluation-2024-expanded.json`.

| Campo/medida | Resultado |
| --- | ---: |
| Observações de volta | 20.262 |
| Stints distintos por sessão/piloto/stint | 958 |
| Nulos em composto, idade, stint ou fresh_tyre | 0 em cada campo |
| Tempos de volta ausentes | 188 |
| Stints com mais de um composto registrado | 0 |
| SOFT / MEDIUM / HARD | 1.517 / 6.394 / 10.983 voltas |
| INTERMEDIATE / WET | 1.350 / 18 voltas |
| fresh_tyre verdadeiro / falso | 15.970 / 4.292 observações |

As contagens de `fresh_tyre` são de linhas, não de conjuntos físicos distintos.
O schema fornece `compound`, `tyre_life_laps`, `stint`, `fresh_tyre`, tempo,
pit-in/out, flags de qualidade e situação da pista. Clima e situação da sessão
estão em tabelas canônicas relacionadas. Não fornece diretamente coeficiente
de desgaste, aderência, temperatura interna do pneu ou combustível medido.

Preservando os filtros de qualidade do perfilamento e removendo **somente**
`insufficient_context_laps` e `insufficient_comparison_drivers`, restam 17.193
voltas: 1.162 SOFT, 5.334 MEDIUM, 9.743 HARD, 953 INTERMEDIATE e 1 WET.
Esses filtros foram feitos para pilotos: o estudo de pneus precisa auditar sua
adequação, não assumir que toda volta restante representa pista livre.

Nos compostos secos há 768 grupos sessão/piloto/stint com pelo menos cinco
voltas restantes e amplitude de idade de pelo menos quatro voltas. São
**candidatos a estudo**, não 768 curvas independentes ou já calibradas.
Esse limiar é exploratório; não foi escolhido a partir de resultados de ajuste.

Reprodução das contagens principais, na raiz com `PYTHONPATH=src`:

```python
from collections import Counter, defaultdict
from pathlib import Path
from scripts.evaluate_profiles import load_plan
from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
from f1_simulator.application.profile_drivers import profile_drivers

plan = load_plan(Path('configs/profile-evaluation-2024-expanded.json'))
repo = SQLiteHistoryRepository(Path('data/curated/history-profile-development-2024.sqlite'))
rows = [r for s in plan.development_sessions
        for r in repo.records('lap_observations', session_id=s)]
print(len(rows), Counter(r['compound'] for r in rows))
print({k: sum(r[k] is None for r in rows)
       for k in ('compound', 'tyre_life_laps', 'stint', 'fresh_tyre', 'lap_time_ms')})
print('stints', len({(r['session_id'], r['driver_id'], r['stint']) for r in rows}))
run = profile_drivers(repo, session_ids=plan.development_sessions, config=plan.config)
lookup = {(r['session_id'], r['driver_id'], r['lap_number']): r for r in rows}
comparison_gates = {'insufficient_context_laps', 'insufficient_comparison_drivers'}
quality = [lookup[l.session_id, l.driver_id, l.lap_number] for l in run.laps
           if not (set(l.exclusions) - comparison_gates)]
print('quality', len(quality), Counter(r['compound'] for r in quality))
groups = defaultdict(list)
for r in quality:
    if r['compound'] in ('SOFT', 'MEDIUM', 'HARD'):
        groups[r['session_id'], r['driver_id'], r['stint']].append(r)
print('candidate stints', sum(
    len(g) >= 5 and max(r['tyre_life_laps'] for r in g)
    - min(r['tyre_life_laps'] for r in g) >= 4 for g in groups.values()))
```

## O que estimar primeiro

Primeiro recorte proposto: compostos secos, por evento/circuito, com gráficos de
idade versus tempo por piloto/stint e indicação de voltas excluídas. Auditar
idade crescente, saltos, pneus usados, começo/fim do stint e continuidade das
voltas antes de ajustar qualquer curva. Lacunas não viram voltas consecutivas.

Começar comparando uma referência constante e uma tendência linear descritiva
por stint. A função quadrática sugerida no plano do produto é uma alternativa,
não uma exigência de iniciar com dois coeficientes. Não truncar inclinações
negativas silenciosamente; mostrá-las como evidência de limites/confundimento.

**Identificação:** dentro de um stint sem interrupção, idade do pneu e número da
volta crescem juntos. Adicionar ambos a uma regressão com intercepto por stint
não separa automaticamente desgaste e redução de combustível: há colinearidade.
Precisaremos de diferenças de idades entre participantes na mesma fase da
corrida, repetições e hipóteses explícitas para estudar a separação. Mesmo com
isso, tráfego, estratégia e seleção de pit stops limitam inferências causais.

O perfil atual compara janelas de idade, portanto já absorve parte da condição
dos pneus. Seus resíduos não são uma curva completa de degradação. Também não
se deve tratar SOFT/MEDIUM/HARD como coeficientes universais entre circuitos.

Avaliar MAE em ms por evento/stint, cobertura e estabilidade frente à referência
constante. Fazer partições por evento (não por voltas vizinhas), reamostrar
blocos de eventos para incerteza e registrar previamente as escolhas. A reserva
original já foi examinada no estudo de pilotos: pode apoiar avaliação interna
explicitamente rotulada, mas não é uma nova validação intocada. Não consultar
novos eventos para escolher coeficientes e depois chamá-los de teste independente.

## Contrato conceitual para o core

Nomes abaixo são propostas; nenhuma classe/porta nova foi implementada.

| Objeto | Conteúdo e responsabilidade |
| --- | --- |
| TyreModelParameters | Versão, origem (`assumed` ou `estimated`), circuito/evento e condições válidas, composto, idade de ancoragem, curva relativa em ms, intervalo de idade autorizado, suporte, seleção e hashes de proveniência |
| TyreState | ID do conjunto no cenário, composto, idade em voltas já completadas antes da próxima volta; pertence ao core |
| Saída do modelo | Efeito relativo em ms, idade avaliada, versão e avisos; ausência explícita fora do suporte |
| Comando de troca | Novo conjunto e sua idade inicial; estratégia decide quando, core aplica a transição; trocar por pneu usado não zera sua idade |

Fluxo proposto: `HistoryRepository → estudo/calibração → parâmetros validados
→ adaptador Python → core`. O adaptador não avança idade nem calcula classificação.
O core recebe os parâmetros na preparação; não consulta ETL/banco a cada volta.

O contrato deve fixar se a idade da observação corresponde ao começo ou fim da
volta. O ETL conserva `TyreLife` como `tyre_life_laps`; nesta etapa não foi
confirmada a convenção temporal exata da versão da fonte. Antes da conversão,
verificar documentação/código FastF1 da versão adquirida e uma sequência real.
Não subtrair um automaticamente. No estado proposto, a idade é explicitamente
pré-volta e aumenta uma vez após completar a volta, sem relação com FPS.

## Ancoragem e prevenção de dupla contagem

Para o mesmo composto/escopo, hipótese experimental:

```text
T(volta) = T_ancora + [g(idade_avaliada) - g(idade_ancora)]
g(idade) = a * idade                         # candidato linear
# ou a * idade + b * idade², se justificado
```

`a`: ms/volta de idade; `b`: ms/volta² de idade. A diferença vale zero na
idade de ancoragem. `T_ancora` já inclui o ritmo de piloto/equipe e a condição
observada dos pneus nessa idade; não se soma outra vez a penalidade absoluta.

**Bloqueio atual concreto:** `PaceContext` tem uma janela de idade, não uma
idade exata da mediana que originou a referência. Não escolher o começo ou
meio da janela como se fosse observado. A modelagem precisa produzir uma nova
referência com ancoragem compatível (estimada ou assumida explicitamente).
O adaptador de piloto de uma volta não deve ser reutilizado sem essa extensão.

Comparar/trocar compostos também exige diferença de ritmo entre compostos sob
referência comum. Curvas ancoradas independentemente em zero não identificam
esse deslocamento. Primeira demonstração sugerida: um composto, sem troca,
idade dentro do intervalo de suporte; depois incorporar referência entre
compostos, pneus usados e perda de pit stop separada.

Exemplo **puramente sintético para teste futuro**: T_ancora = 100.000 ms,
idade_ancora = 5, a = 100 ms/volta. Idades avaliadas 5/6/7 produzem
100.000/100.100/100.200 ms. Esses números não são estimativas da base.

## Fatias e decisões para alinhar com o colega

1. **Exploração:** publicar gráficos por stint, auditoria de filtros e cobertura
   por composto/evento; decidir janela de aquecimento e mínimos após examinar
   a qualidade, sem promover automaticamente tendências a desgaste físico.
2. **Modelo isolado:** regra determinística com parâmetros sintéticos explicitados
   e testes de ancoragem, unidades, domínio de validade, ausência, avanço de idade
   e troca por pneu usado. Escolher interface com o responsável pelo core.
3. **Estimativa:** comparar métodos com amostras separadas e referência compatível;
   guardar coeficientes, hipóteses, suporte e incerteza. Não usar bootstrap como ruído.
4. **Integração:** substituir ritmo constante por uma avaliação por volta mantendo
   o comportamento anterior como baseline; produzir decomposição do tempo e estado
   do pneu nos snapshots. Modelo de pneus não implementa relógio/classificação.

Antes da integração: definir convenção de idade, ancoragem do ritmo, precisão,
política fora do suporte (proposta: rejeitar, sem clamp silencioso), proprietário
do estado e ponto exato de aplicação da troca. A perda total de pit lane não
pode ser inferida automaticamente de uma duração histórica de pit stop.

Critérios futuros: mesma entrada gera mesma sequência; alteração da frequência
de renderização não altera idade/tempo; efeito zero na âncora; tempos positivos;
modelo de efeito zero reproduz core constante; ausência não vira zero; limites
são validados antes da execução; não há efeito duplicado de pneus/equipe.

## Verificação e limites desta entrega

Foram inspecionados MDs, ADRs, issue #63, schemas/adaptadores e core remoto;
consulta ao ai-memory trouxe histórico geral, sem decisão específica de contrato
de pneus. Executadas consultas canônicas e snippet acima. Não foram calibrados
coeficientes, adquiridas novas fontes, criados gráficos de curvas ou alterado o
motor. A página pública de referência FastF1 retornou 403 nesta consulta;
a convenção temporal de idade ficou explicitamente pendente, sem inferência.
