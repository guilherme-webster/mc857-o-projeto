# Sensibilidade dos contextos e incerteza dos perfis

Entrega exploratória para #66/#67, em 13/09/2026, na branch
`40-modelagem-dos-dados`. Complementa a [avaliação entre eventos](avaliacao-perfis-entre-eventos.md).
Não muda o ETL, a regra padrão `contextual-pace-v1`, os parâmetros do motor ou
as fontes autorizadas. Domínio e aplicação continuam consumindo contratos Python.

## Perguntas e protocolo

O estudo compara quatro variantes nos mesmos cinco eventos já inspecionados:

| Variante | Janela de voltas | Número do stint na chave |
| --- | ---: | --- |
| `baseline` | 10 | não |
| `stints` | 10 | sim |
| `narrow` | 5 | não |
| `narrow-stints` | 5 | sim |

Idade do pneu, composto, chuva booleana, filtros de qualidade e mínimos de
suporte são mantidos. A janela menor aproxima voltas no andamento da corrida,
mas não mede intensidade da chuva, umidade da pista, tráfego ou aderência.
O número ordinal de um stint tampouco garante estratégia equivalente entre
carros; sua inclusão é uma hipótese de sensibilidade, não uma correção adotada.

A separação ocorre antes de recalcular os mínimos de voltas/pilotos e a
referência de cada contexto. Somente exclusões de suporte são reconsideradas;
voltas inválidas, pits, bandeiras e clima sem cobertura continuam excluídos.
Uma estimativa que desaparece não se transforma em zero.

O método padrão permanece intacto. A extensão experimental `StintContext`
acrescenta o número do stint à chave, e seus perfis recebem a identificação
`contextual-pace-stint-v1`. A versão da análise é `context-reliability-v1`.
O `plan_sha256` continua identificando o plano de avaliação efetivo; o novo
`analysis_sha256` inclui versão, plano, variante e configuração do bootstrap.
Proveniência dos dados continua nos manifestos de cada execução.

**Os grupos D/V preservam apenas a divisão anterior.** Como seus resultados já
foram vistos, este estudo não é nova validação confirmatória e não escolhe a
melhor variante automaticamente. Uma futura decisão exige novos eventos reservados.

## Incerteza por evento

Para cada piloto/grupo, calculamos as medianas contextuais por evento, como no
perfil original. Reamostramos com reposição o mesmo número de eventos disponíveis
e calculamos novamente a mediana entre eventos. A cada réplica, ritmo e MAD usam
os mesmos eventos sorteados. Como a estatística só depende dessas medianas,
reamostrar seus pares equivale a conservar cada evento inteiro para esse cálculo.
Não sorteamos voltas individualmente nem tratamos mais voltas como mais eventos.

Padrão: **2.000 réplicas, semente 42 e nível nominal de 95%**. Os extremos são
os percentis 2,5 e 97,5, com interpolação linear entre posições ordenadas.
Os parâmetros são configuráveis e constam no JSON e no hash da análise.

A escolha de reamostrar grupos inteiros preserva sua dependência interna,
conforme a descrição de *clustered bootstrap* nas
[notas STAT 9610, seção 15.3.4](https://katsevich-teaching.github.io/stat-9610-notes/bootstrap.html#clustered-bootstrap).
A aplicação aos eventos deste projeto é uma escolha exploratória nossa.

Limitações e decisões explícitas:

- Intervalos são **marginais e condicionais aos eventos com suporte**, mantendo
  fixas as referências contextuais dentro de cada evento. Não quantificam viés
  por eventos ausentes, incerteza da seleção de filtros ou habilidade isolada.
- O bootstrap supõe eventos intercambiáveis para essa distribuição empírica;
  diferenças de circuito, condições e evolução do carro fragilizam a hipótese.
  Não modela dependência entre corridas nem sustenta previsão temporal.
- Com dois ou três eventos, a distribuição é discreta e pouco informativa.
  O nível nominal não demonstra cobertura estatística real de 95% nesta amostra.
- Menos de cinco eventos gera o aviso `few_events_exploratory_interval`.
  Cinco é um limiar heurístico configurável de apresentação, não um critério
  validado de suficiência; superá-lo não aprova o perfil.
- Um único evento ou perfil agregado indisponível não recebe intervalo.
  Intervalo degenerado é explicitamente marcado; largura zero não é certeza.
- Não há intervalo para a diferença D/V, teste entre pilotos, ranking de
  habilidade ou detecção estatística de outliers. Sobreposição de intervalos
  marginais não substitui esses testes.

## Gráficos e auditoria

`stability.png/.svg` mostra nomes, pontos, intervalos e contagens por grupo:
`v` = voltas comparáveis, `c` = contextos e `e` = eventos. Marcadores vazios
indicam aviso de suporte; `[insuf.]` identifica estimativa indisponível.
As barras representam incerteza entre eventos, não o MAD dentro de um contexto.

Os mapas por evento exibem valor e contagens em cada célula. Cinza diferencia
textualmente ausência e insuficiência; um evento não recebe intervalo entre
eventos. As cores indicam magnitude, sem rotular pilotos como outliers.

Cada variante possui JSON, CSVs e gráficos completos. `support.csv` acrescenta
contagens, contextos com mistura de stints, extremos dos intervalos e avisos.
`driver-events.csv` agora inclui quantidade de contextos e mistura de stints.
O campo `ProfileRun.uncertainty` continua descrevendo o perfilador isolado, que
não calcula intervalos; os novos intervalos estão em `ProfileEvaluation.support`.

O estudo acrescenta:

- `summary.json` e `report.md`: cobertura, pares disponíveis, mudanças medianas
  e máximas, além de quantos pares tiveram alguma mudança acima de 1e-9 pp;
- `context-changes.csv`: diferenças por piloto/evento, suporte e voltas comuns
  às variantes. A mediana resume somente pares disponíveis em ambos os lados;
- `context-audit.csv`: chave, números das voltas, stints e amplitude dos tempos
  de cada contexto contribuinte, permitindo investigar mistura/evolução;
- `sensitivity.png/.svg`: comparação da cobertura e mudanças medianas.

As mudanças incluem alterações do pelotão de referência e das voltas retidas,
não apenas da fórmula sobre uma amostra fixa. Mediana zero pode esconder
mudanças importantes em poucos pares; consultar máximos e detalhes.

## Resultado nos cinco eventos de 2024

Todas as variantes partem das mesmas **5.266 observações**:

| Variante | Voltas comparáveis | Cobertura | Contextos com mistura | Pares piloto/evento com referência |
| --- | ---: | ---: | ---: | ---: |
| Original | 3.096 | 58,79% | 3 | 95 |
| Stints | 2.898 | 55,03% | 0 | 92 |
| Janela de 5 voltas | 2.317 | 44,00% | 0 | 92 |
| Ambas | 2.194 | 41,66% | 0 | 88 |

A ausência de mistura na janela menor é observada nesta amostra, não uma
garantia do algoritmo. Separar stints perde 198 voltas; diminuir a janela perde
779; combinar perde 902. Não reduzir mínimos para compensar silenciosamente.

Pérez em Silverstone ilustra o compromisso:

| Variante | Voltas/contextos | Ritmo (%) | MAD (%) |
| --- | --- | ---: | ---: |
| Original | 8/2 | +0,161 | 1,386 |
| Stints | 3/1 | +1,582 | 1,237 |
| Janela de 5 voltas | 6/2 | +0,092 | 0,802 |
| Ambas | 0/0 | indisponível | indisponível |

O contexto original reúne voltas 21, 22, 23 e 30 em dois stints, com amplitude
6.193 ms. Separar stints não elimina toda dispersão; combinar restrições elimina
a estimativa. Esses resultados não identificam inconsistência intrínseca.
A decisão nesta entrega é **manter o agrupamento original como referência** e
expor a sensibilidade, sem promover uma alternativa com base nesses eventos.

## Reprodução

No ambiente Pipenv já usado para os gráficos:

```bash
pipenv run python -B scripts/analyze_profile_contexts.py \
  --database data/curated/history-profile-evaluation-2024.sqlite \
  --plan configs/profile-evaluation-2024.json
```

A CLI cria uma pasta nova em `data/curated/context-studies/sensitivity-...` e
imprime seu caminho. Não requer um JSON de perfil prévio nem que se apague uma
pasta. Publica as quatro variantes somente após sucesso completo; falhas deixam
intactas as saídas anteriores. Dados e artefatos permanecem fora do Git.

Opções: `--narrow-window`, `--bootstrap-replicates`, `--bootstrap-seed`,
`--confidence`, `--warn-below-events`, `--output-root`, `--without-plots`.
A CLI anterior `scripts/evaluate_profiles.py` também gera suporte e intervalos,
aceitando as mesmas opções de bootstrap.

## Verificação e continuidade

Testes deterministas cobrem limites conhecidos dos intervalos, reprodução,
ordenação, contagem por evento independente da quantidade de voltas, suporte
insuficiente, degeneração, preservação de filtros, mudanças de hash, comparação
entre variantes e publicação sem sobrescrever saídas. A suíte completa passou
com 144 testes, 13 ignorados pelas condições gráficas existentes; Ruff passou.

Próximo passo: avaliar as hipóteses com mais eventos antes de mudar o agrupamento
padrão, investigar alinhamento temporal mais preciso e quantificar o efeito de
tráfego/equipe. A análise atual não depende dessas extensões para funcionar.
