# Avaliação descritiva de perfis entre eventos

Implementação `profile-stability-v1`, em 13/09/2026, para #66/#67. Reutiliza
`contextual-pace-v1` e os contratos Python do [perfilamento inicial](modelagem-pilotos-inicial.md).
O caso de uso é `evaluate_profiles(repository, plan)`, sem HTTP, Pandas,
FastF1, janela ou banco de dados no domínio.

## Pergunta respondida

Quão diferentes são as estimativas descritivas de ritmo relativo e consistência
quando calculadas em dois conjuntos distintos de eventos? A avaliação também
mostra onde há dados suficientes para comparar e onde não há.

Esta versão **não prevê tempos de volta**, não estima habilidade independente
do carro e não implementa um teste estatístico de robustez. O contexto e o
pelotão de referência podem mudar entre eventos. Comparar os dois perfis não
identifica a causa da mudança nem elimina tráfego, estratégia, pneus ou clima.

## Protocolo explícito e reproduzível

O arquivo [configs/profile-evaluation-2024.json](../configs/profile-evaluation-2024.json)
foi definido antes de consultar as métricas dos eventos reservados. Ele contém
ID da avaliação, versões de avaliação/perfilamento, sessões e todos os limiares:

| Grupo | Eventos | Sessões |
| --- | --- | --- |
| Desenvolvimento | Bahrein, Grã-Bretanha e São Paulo/2024 | `session:1121:R`, `session:1132:R`, `session:1141:R` |
| Validação | Itália e Abu Dhabi/2024 | `session:1136:R`, `session:1144:R` |

Configuração comum: janela de 10 voltas; janela de idade de pneu de 5 voltas;
tolerância de clima de 120.000 ms; mínimo de três voltas e três pilotos por
contexto; **mínimo de dois eventos comparáveis em cada grupo**. Esses números
são escolhas exploratórias herdadas da análise anterior, não limiares calibrados
para aprovação automática.

O protocolo tem SHA-256 canônico
`d86baadadf4b6878f9f7d86b4b711bcdcbb07fb697318512de985915b70f6917`.
A ordem das sessões não altera esse hash. Alterar parâmetros, seleção, ID ou
versão altera a identidade da avaliação; resultados anteriores são preservados.
O hash identifica a configuração, não demonstra que um conjunto nunca foi visto
por um humano. Essa disciplina precisa ser mantida pelo grupo.

**Cronologia:** Itália ocorreu em setembro e São Paulo em novembro. Portanto,
essa divisão é entre eventos e não estritamente temporal. O relatório registra
`validation_after_development=False` e o aviso correspondente. Para alegar
previsão futura será necessário outro protocolo com todos os eventos de
validação posteriores aos de desenvolvimento.

## Separação e métricas

O plano rejeita grupos vazios, sessões repetidas, sobreposição entre os grupos
e versões incompatíveis. Antes de ler voltas, a aplicação resolve sessões e
corridas: somente `R` é aceito e **cada corrida pode ocorrer uma única vez em
toda a avaliação**, impedindo que aliases coloquem o mesmo evento nos dois
lados. Sessão ausente ou sem proveniência do ETL produz erro.

A aplicação chama o perfilador separadamente para cada grupo com a mesma
configuração. Referências contextuais e estimativas de validação são calculadas
apenas naquele grupo; não são usadas para alterar o desenvolvimento ou escolher
parâmetros. Não há ajuste automático de modelo.

Para cada piloto presente na união dos grupos:

- mudança de ritmo = ritmo relativo na validação menos ritmo no desenvolvimento;
- mudança de consistência = MAD na validação menos MAD no desenvolvimento;
- ambas as mudanças são expressas em **pontos percentuais (pp)**. Passar de
  2% para 3% significa +1 pp, não +50%;
- sem métricas disponíveis nos dois lados, a mudança é `None`, com motivos
  como piloto ausente, falta de voltas ou insuficiência de eventos. Não usar zero;
- equipes e compostos observados em cada grupo permanecem no contrato para
  investigar mudanças de contexto.

O resumo calcula a mediana dos módulos dessas mudanças entre os pilotos com
suporte nos dois grupos, com peso igual por piloto. Não é MAE de previsão.
Sem pares disponíveis, as medianas são `None`. A incerteza não é estimada e
nenhuma regra declara o modelo aprovado/reprovado automaticamente.

Por evento, o relatório conserva participantes, voltas observadas/comparáveis,
percentual de cobertura e motivos de exclusão. Motivos podem se sobrepor; sua
soma não equivale à contagem de voltas excluídas. Os gráficos por evento mostram
a mediana contextual de cada piloto naquele evento, mesmo quando ele não
atinge o mínimo de eventos para ter um perfil agregado. Isso não relaxa o
critério do perfil agregado nem preenche pontos ausentes.

## Executar localmente

O banco com os cinco eventos foi gerado como uma cópia enriquecida da amostra
anterior. Para reproduzir a aquisição, usar ambiente com `requirements-etl.txt`:

```bash
python3 -B scripts/ingest_fastf1.py \
  --base data/curated/history-profile-sample-2024.sqlite \
  --season 2024 --rounds 16 24 --sessions R --without-telemetry \
  --output data/curated/history-profile-evaluation-2024.sqlite \
  --cache-dir data/raw/fastf1-cache
```

Saída existente é recusada; acrescentar `--overwrite` somente para substituir
esse banco derivado deliberadamente. A base anterior é preservada. A amostra
mantém as observações necessárias ao perfilamento; telemetria de carro/posição
é registrada como não solicitada e não é usada pela avaliação.

A avaliação não faz downloads. No ambiente Pipenv do projeto, com Matplotlib:

```bash
pipenv run python -B scripts/evaluate_profiles.py \
  --database data/curated/history-profile-evaluation-2024.sqlite \
  --plan configs/profile-evaluation-2024.json
```

Não precisa de `>` nem de criar ou apagar uma pasta de gráficos. A CLI imprime
o caminho da nova pasta em `data/curated/evaluations/evaluation-...`. Ela prepara
todos os artefatos em um diretório temporário e só publica após sucesso. Uma
falha de gráfico/serialização não apaga relatórios anteriores nem deixa um
relatório incompleto como entrega final.

Opções: `--output-root CAMINHO` muda a pasta pai;
`--without-plots` gera JSON/CSV/Markdown sem depender de Matplotlib.

Consumo Python:

```python
from pathlib import Path
from f1_simulator.adapters.persistence.sqlite_history import SQLiteHistoryRepository
from f1_simulator.application.evaluate_profiles import evaluate_profiles
from f1_simulator.domain.driver_profile import ProfileConfig
from f1_simulator.domain.profile_evaluation import EvaluationPlan

plan = EvaluationPlan(
    evaluation_id="f1-2024-cross-event-v1",
    development_sessions=("session:1121:R", "session:1132:R", "session:1141:R"),
    validation_sessions=("session:1136:R", "session:1144:R"),
    config=ProfileConfig(10, 5, 120_000, 3, 3, 2),
)
result = evaluate_profiles(
    SQLiteHistoryRepository(Path("data/curated/history-profile-evaluation-2024.sqlite")),
    plan,
)
print(result.summary)
```

## Artefatos

- `evaluation.json`: protocolo/hash, perfis separados, proveniência/checksums
  do ETL, auditoria de voltas, cobertura, comparações e avisos.
- `report.md`: resumo legível da execução.
- `coverage.csv`: cobertura e exclusões por evento.
- `stability.csv`: métricas dos dois grupos e mudanças por piloto, com IDs e nomes.
- `driver-events.csv`: estimativas e suporte por piloto/evento.
- `coverage.png/.svg`: cobertura por evento e grupo.
- `stability.png/.svg`: estimativas dos dois grupos lado a lado, por nome do piloto.
- `pace-by-event.png/.svg` e `consistency-by-event.png/.svg`: valores por evento,
  mantendo ausências em cinza escuro e identificando o grupo de cada corrida.

Os CSVs usam campos vazios para métricas indisponíveis e JSON nos campos
compostos, como listas de motivos. Os gráficos só apresentam valores já
calculados; não existe uma segunda implementação das fórmulas no Matplotlib.
Todos esses artefatos e bancos permanecem fora do Git. O código e o protocolo
versionados permitem repetir a execução.

## Resultado observado nesta entrega

| Grupo | Evento | Observadas | Comparáveis |
| --- | --- | ---: | ---: |
| Desenvolvimento | Bahrein | 1.129 | 760 |
| Desenvolvimento | Grã-Bretanha | 960 | 504 |
| Desenvolvimento | São Paulo | 1.134 | 580 |
| Validação | Itália | 1.008 | 651 |
| Validação | Abu Dhabi | 1.035 | 601 |

A união tem 24 pilotos; **15 têm estimativas disponíveis nos dois grupos**.
Para esses pares, a mediana da mudança absoluta foi **0,255540 pp no ritmo** e
**0,042532 pp no MAD**. Os demais pilotos permanecem no relatório com motivos
de indisponibilidade. Não extrapolar essas medianas aos pilotos excluídos da
comparação, a outros eventos ou a desempenho futuro.

Os resultados também refletem a diferença de condições e composição da amostra,
não só variabilidade do piloto. Essa execução é uma avaliação descritiva em
eventos reservados; não é validação de uma regra preditiva de tempo de volta.
Nenhum parâmetro foi alterado para melhorar as métricas observadas. Depois de
examinar esses eventos, ajustes futuros devem tratá-los como dados conhecidos
e reservar novos eventos antes da próxima avaliação confirmatória.

## Verificações e próximos passos

A suíte completa terminou com **134 testes, sem falhas e 13 ignorados** por
condições gráficas. Os 15 testes novos cobrem fórmulas em pp, repetição e
sobreposição de eventos, aliases, versões/configuração, cronologia, ausências,
limiares, cobertura e publicação transacional. Um teste altera as voltas da
validação e comprova que o perfil de desenvolvimento permanece igual. Duas
execuções reais produziram JSON idêntico; gráficos PNG/SVG foram inspecionados.

```bash
python3 -B -m unittest tests.test_profile_evaluation -v
python3 -B -m unittest -q
```

Próximos passos: investigar mudanças de contexto com os relatórios; planejar
filtros de tráfego/OpenF1 sob o contrato e as condições da fonte já pesquisados;
e definir uma regra preditiva e uma referência simples se o objetivo passar a
ser erro de tempo de volta. Comparação com companheiros, intervalos de confiança
e conversão em parâmetros do motor continuam decisões próprias. Esta entrega
não muda os efeitos do motor nem incorpora OpenF1 ao ETL de produção.
