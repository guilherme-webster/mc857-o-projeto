# Pneus: SC/VSC, robustez e avaliação separada por evento

18/09/2026 · #63 · branch `63-modelagem-pneus`.

**Conclusão:** a filtragem contextual amplia a proteção contra voltas próximas
de neutralizações. A mediana das inclinações entre pares é menos sensível a
uma volta individual na maior parte dos stints, mas não mostrou superioridade
preditiva clara sobre OLS ou referência constante no benchmark executado.
Não há justificativa nesta entrega para exportar um coeficiente universal de
pneu ao core.

O [protocolo](protocolo-pneus-sc-estimadores.md) foi registrado antes do cálculo:
janela primária SC/VSC=2, retomadas de sessão=2, análise de influência e avaliação
por evento deixado de fora. As outras janelas não foram escolhidas pelo erro.
Todos os dados são dos 18 eventos de desenvolvimento já explorados; não é uma
validação final intocada. Dados, core e perfilamento de pilotos foram preservados.

## Detecção e conferência dos episódios

Fonte: `track_status_events` canônico. Códigos 4=SC, 6=VSC, 7=VSC encerrando;
o retorno efetivo é 1, não 7. Conferido no
[código/documentação FastF1 3.8.3](https://github.com/theOehrly/Fast-F1/blob/v3.8.3/fastf1/_api.py#L1134).
Amarelo intermediário mantém o episódio pendente. Vermelho cancela sua atribuição
à saída de SC/VSC; a retomada é tratada pelo detector de sessão existente.
Sem retorno a 1, não se inventa fim. Feed ausente, relógio ausente ou código
desconhecido gera erro. Mensagens simultâneas seguem `sequence` canônico e
ficam auditadas; não são silenciosamente descartadas.

Foram encontrados **10 episódios encerrados em oito eventos**:

| Evento | Retornos detectados |
| --- | --- |
| Arábia Saudita | 1 SC |
| China | 1 VSC→SC e 1 SC |
| Mônaco | 1 SC |
| Áustria | 1 VSC |
| Estados Unidos | 1 SC |
| México | 1 SC |
| São Paulo | 1 VSC e 1 SC |
| Abu Dhabi | 1 VSC |

São Paulo tem ainda um SC interrompido por vermelho; Azerbaijão tem VSC sem
retorno a pista livre no feed. Ambos aparecem na auditoria, sem liberação
inventada. No Azerbaijão há duas mensagens simultâneas de amarelo/pista livre
antes do episódio, preservadas em ordem canônica.

Mensagens de direção contendo SAFETY CAR foram preservadas no JSON para
inspeção. A China confirma VSC seguido de SC e outro acionamento de SC;
Azerbaijão registra acionamento de VSC sem mensagem de encerramento no subconjunto
consultado; São Paulo registra VSC, encerramento e acionamentos de SC. Mensagens
sobre infrações também contêm SAFETY CAR: não servem sozinhas como detector.
Os relógios UTC dessas mensagens não foram convertidos por fuso presumido;
a detecção usa o relógio de sessão do track status.

A janela continua ancorada por piloto na primeira volta registrada iniciada
após pista livre, antes dos filtros. Voltas atravessando a transição são
marcadas à parte. Exclusões de todos os episódios são unidas, evitando que
uma nova marcação apague uma anterior. Não é identificação de formato de
relargada nem medição de duração térmica do pneu.

## Cobertura e sensibilidade às janelas

A referência desta tabela já exclui duas voltas após Aborted→Started.

| Janela adicional SC/VSC | Voltas aprovadas | Ajustes secos | Perda de voltas frente à referência |
| --- | ---: | ---: | ---: |
| 0 | 17.036 | 768 | 0 |
| 1 | 16.922 | 767 | 114 |
| **2, primária** | **16.798** | **764** | **238 (1,40%)** |
| 3 | 16.659 | 762 | 377 |
| 5 | 16.422 | 756 | 614 |

Na janela 2, SOFT tem 92 ajustes; MEDIUM 303; HARD 369. Medianas OLS de
inclinação: +32,49/+23,13/+6,66 ms por volta de idade. Permanecem negativos
26, 102 e 165 ajustes, respectivamente. Entre os pares que mantêm suporte,
quatro MEDIUM e dois HARD mudam de sinal frente à janela SC/VSC=0.

A curva de cobertura cai conforme a janela cresce, sem mudança uniforme das
medianas. Isso não demonstra que duas voltas sejam universalmente suficientes:
a janela é hipótese operacional explícita e mantém o custo de cobertura visível.
Não houve ajuste automático do tamanho da janela para melhorar o benchmark.

## Robustez ao retirar uma volta

Comparação nos mesmos stints. A medida é a maior mudança absoluta de inclinação
entre o ajuste completo e todos os ajustes retirando uma volta. Só entram os
stints em que cada ajuste reduzido mantém >=5 voltas e amplitude >=4.

| Composto | Stints pareados | Mediana da influência máxima OLS | Robusto | Robusto menos sensível |
| --- | ---: | ---: | ---: | ---: |
| SOFT | 89 | 30,75 ms/volta | 20,18 ms/volta | 57/89 |
| MEDIUM | 292 | 16,86 ms/volta | 10,11 ms/volta | 198/292 |
| HARD | 368 | 8,24 ms/volta | 5,38 ms/volta | 269/368 |

Em 524/749 pares (~70%), o robusto é menos sensível. Não é garantia por stint:
parte dos pontos fica acima da diagonal no gráfico. Entre todos os ajustes,
OLS e robusto discordam no sinal em 10 SOFT, 25 MEDIUM e 24 HARD. A robustez
reduz dependência de observações individuais, mas não remove confundimento
com combustível, tráfego ou evolução da pista.

## Avaliação fora do evento de treinamento

Benchmark com **715 stints, 11.852 voltas de avaliação e 17 eventos**; São Paulo
não tem suporte seco neste protocolo. Para cada evento alvo e composto:

1. Estimar tendências por stint somente nos outros eventos.
2. Agregar mediana por evento e depois mediana entre eventos (mínimo dois eventos
   de treino), separadamente para OLS e robusto.
3. Usar primeiras cinco voltas aprovadas do stint alvo para ancorar intercepto:
   `mediana(tempo − inclinação × idade)`. O método constante usa inclinação zero.
4. Avaliar as voltas posteriores do mesmo stint, pelo menos três, nos três métodos.
   A âncora deve ter amplitude de idade >=4. Voltas futuras não entram no treino
   nem no intercepto. Não há ajuste de slope local no evento alvo.

Essa avaliação testa **transferência de tendência por composto com adaptação
local do nível de tempo**. Não representa previsão sem dados iniciais, teste de
um modelo físico de pneus, nem previsão de tempo absoluto antes da corrida.
Eventos de treino podem ser posteriores no calendário; não é backtest cronológico.

MAE é calculada por stint; para cada método toma-se mediana dos stints no evento.
Comparam-se esses erros pareados por evento. Valores negativos abaixo indicam
melhora do primeiro método:

| Comparação | Mediana do delta MAE por evento | Intervalo exploratório 95% | Eventos melhores |
| --- | ---: | ---: | ---: |
| OLS − constante | −14,33 ms | [−22,66; +15,12] ms | 10/17 |
| Robusto − constante | −10,73 ms | [−27,03; +24,19] ms | 10/17 |
| Robusto − OLS | +2,87 ms | [−19,33; +15,02] ms | 7/17 |

Intervalos por bootstrap de eventos inteiros, 2.000 replicações, semente 42.
São condicionais aos erros dos folds já calculados, sem reestimar treinamento
em cada replicação; folds compartilham eventos de treino. Não representam toda
a incerteza do procedimento ou eliminam a dependência entre folds. Não são
intervalos para ruído por volta. Todos incluem zero: a avaliação não dá suporte
claro a promover um dos estimadores a substituto universal da constante.

O gráfico mostra heterogeneidade: no Bahrein ambos melhoram; na China ambos
pioram. Em Mônaco a MAE mediana é 2.314 ms na constante, 2.487 no OLS e 2.362
no robusto. O robusto reduz a piora do OLS nesse evento, mas ainda perde para
a constante. A mediana dos deltas não é a diferença entre as medianas globais
dos erros, pois a mediana não é uma operação linear.

## Conclusões e sequência recomendada

- Manter SC/VSC e retomadas como contexto explícito de qualidade, com análise
  de sensibilidade. Não interpretar tempos próximos de neutralizações como
  desgaste térmico automaticamente.
- Usar o robusto como estimador descritivo e diagnóstico complementar: ele
  demonstrou menor sensibilidade em grande parte da amostra. **Não houve
  demonstração de superioridade preditiva universal.**
- Não exportar o slope agrupado por composto para o core como coeficiente
  calibrado. O benchmark mostra que a transferência entre eventos ainda é fraca.
- Para avançar, restringir o próximo modelo a circuito/condições definidos e
  comparar idades diferentes na mesma fase da corrida, com hipótese clara de
  ancoragem e separação de efeitos. Fixar nova avaliação antes de calibrar.
- O contrato determinístico do core pode ser implementado com parâmetros
  assumidos explicitamente; isso é um experimento de integração distinto de
  alegar que os coeficientes foram validados empiricamente.

## Reprodução e evidência local

```bash
pipenv run python -B scripts/compare_tyre_estimators.py \
  --database data/curated/history-profile-development-2024.sqlite \
  --plan configs/profile-evaluation-2024-expanded.json
```

Saída local:
`data/curated/tyre-estimators/estimators-55890223ccfd456eae530045a1965760/`.
[SC/VSC e cobertura](../data/curated/tyre-estimators/estimators-55890223ccfd456eae530045a1965760/sc-vsc-cobertura.png),
[influência por volta](../data/curated/tyre-estimators/estimators-55890223ccfd456eae530045a1965760/influencia.png),
[avaliação por evento](../data/curated/tyre-estimators/estimators-55890223ccfd456eae530045a1965760/avaliacao-eventos.png).

JSON contém baseline, mensagens, episódios, variantes, ajustes e previsões com
IDs das sessões de treino e voltas de âncora/teste. CSVs: `event-errors.csv`,
`influence.csv`, `predictions.csv`. Publicação em nova pasta, sem sobrescrever
artefatos. Links exigem execução local; os dados não são versionados.

Cinco testes novos cobrem detector/ordem temporal, vermelho, episódio aberto,
união de janelas, influência conhecida e separação evento/futuro. Suíte completa:
182 testes, sem falhas, 13 ignorados. Gráficos inspecionados; Ruff aprovado.
