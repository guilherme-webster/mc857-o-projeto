# Avaliação das seis corridas reservadas de 2024

Executada em **18/09/2026**, na branch `40-modelagem-dos-dados`, para #66/#67.
Esta é a consulta da reserva autorizada após a
[análise do desenvolvimento](analise-desenvolvimento-pilotos-2024.md).
**A reserva foi examinada e não pode ser tratada novamente como amostra inédita.**

## Protocolo preservado

Conferidos antes da execução: hash do plano expandido, configuração do perfil e
[decisões registradas](../configs/profile-validation-decision-2024.json).
Mantidos agrupamento original, janelas 10/5 voltas, três voltas/três pilotos por
contexto, mínimo de dois eventos, clima até 120.000 ms e bootstrap de 2.000
réplicas, semente 42, nível nominal 95%, aviso abaixo de cinco eventos.

Plano: `c28b469f24beab166b6386dced4fead51d0610864d6c23925e1f6ed8010cbb03`.
A decisão original permanece imutável: seu campo `reserved_metrics_examined=false`
retrata o momento do congelamento, não o estado atual. Este documento registra
que a consulta ocorreu. Não houve ajuste, relaxamento de filtros ou escolha de
outra variante após observar os resultados.

A divisão separa eventos, não o passado do futuro: os 18 eventos de desenvolvimento
estão distribuídos pela temporada, incluindo eventos posteriores a parte da
reserva. A pergunta continua sendo estabilidade descritiva entre recortes,
sem erro preditivo ou aprovação/reprovação automática.

## Cobertura e diferenças agregadas

| Grupo | Eventos selecionados | Voltas observadas | Comparáveis | Cobertura |
| --- | ---: | ---: | ---: | ---: |
| Desenvolvimento | 18 | 20.262 | 12.558 | 61,98% |
| Reserva | 6 | 6.342 | 3.237 | 51,04% |

Há **20 pilotos com estimativas em ambos os grupos**, entre 24 na união.
A mediana do módulo da diferença reserva menos desenvolvimento é **0,129507 pp
no ritmo** e **0,030092 pp no MAD**. Não são MAE de previsão nem limiares de
aprovação; resumem apenas os pares disponíveis, com peso igual por piloto.

| Evento reservado | Observadas | Comparáveis | Cobertura |
| --- | ---: | ---: | ---: |
| Austrália | 998 | 618 | 61,92% |
| Miami | 1.111 | 598 | 53,83% |
| Canadá | 1.272 | 514 | 40,41% |
| Bélgica | 841 | 429 | 51,01% |
| Singapura | 1.177 | 640 | 54,38% |
| Qatar | 943 | 438 | 46,45% |

Liam Lawson e Franco Colapinto têm apenas um evento comparável na reserva;
Oliver Bearman e Jack Doohan estão ausentes dela. Doohan também não atinge o
mínimo no desenvolvimento. Nenhum caso foi imputado como zero.

## Investigação das divergências

As contagens abaixo são de **contextos por piloto**, não de corridas, voltas ou
peso efetivo no estimador. Servem para descrever composição: o perfil dá peso
igual aos eventos após agregar seus contextos.

| Composto | Desenvolvimento (3.023 contextos) | Reserva (816 contextos) |
| --- | ---: | ---: |
| HARD | 58,98% | 42,65% |
| MEDIUM | 29,97% | 43,26% |
| INTERMEDIATE | 5,62% | 13,73% |
| SOFT | 5,43% | 0,37% |

Todos os 112 contextos com intermediários da reserva pertencem ao Canadá.
Nesse evento há 48 contextos com chuva booleana verdadeira e 93 com falsa,
incluindo outros compostos. Pneu intermediário não equivale a chuva no sensor,
e chuva booleana não quantifica intensidade nem aderência da superfície.

As exclusões também mudam: `track_not_clear_or_unknown` aparece em 773 de 6.342
observações reservadas (12,19%), contra 1.236 de 20.262 (6,10%). Na reserva há
999 registros com suporte insuficiente de voltas/contexto, 952 com flag de
precisão rejeitada e 760 sem pilotos comparáveis suficientes. Motivos podem
se sobrepor: não somar para obter uma porcentagem de exclusão.

Os 20 pares disponíveis têm os mesmos conjuntos de equipes nos dois grupos.
Assim, troca de equipe não explica diretamente essas diferenças de grupos.
Isso **não controla desempenho do carro**, evolução durante o ano, estratégia,
tráfego ou adequação a cada circuito. Não foi feito teste causal nem comparação
controlada entre companheiros nesta etapa.

| Piloto | Ritmo desenvolvimento (%) | Ritmo reserva (%) | Diferença (pp) | Eventos com suporte D/R |
| --- | ---: | ---: | ---: | --- |
| Pierre Gasly | +0,151 | +0,650 | +0,500 | 16/6 |
| Max Verstappen | −0,555 | −0,960 | −0,405 | 18/5 |
| Lando Norris | −0,673 | −1,015 | −0,343 | 18/6 |
| Daniel Ricciardo | +0,342 | +0,006 | −0,336 | 12/4 |
| Guanyu Zhou | +0,441 | +0,638 | +0,197 | 17/5 |
| Sergio Pérez | −0,358 | −0,311 | +0,047 | 16/6 |

- **Gasly:** tem ritmo positivo em cinco das seis corridas reservadas; Austrália
  (+0,874%), Bélgica (+0,953%) e Singapura (+0,783%) contribuem para a mediana
  maior. Miami é aproximadamente −0,026%. A mudança não depende apenas do Canadá.
- **Verstappen:** a Austrália tem quatro observações e nenhuma volta comparável,
  portanto não entra na mediana. Canadá (−1,838%), Singapura (−0,960%) e Qatar
  (−1,136%) contribuem para a estimativa mais negativa. O intervalo marginal da
  reserva é amplo, aproximadamente [−1,838%; −0,235%].
- **Norris:** tem suporte nas seis corridas e ritmo negativo em todas. Canadá,
  Singapura e Qatar apresentam estimativas mais negativas; o MAD agregado muda
  somente −0,004 pp, embora o ritmo mude −0,343 pp.
- **Ricciardo:** tem somente quatro eventos comparáveis. A estimativa da Bélgica
  usa sete voltas em dois contextos; Singapura tem observações, mas nenhum contexto
  comparável. A diferença agregada precisa ser lida junto dessa perda de suporte.
- **Zhou:** mantém ritmo positivo nos cinco eventos com suporte, variando de
  +0,049% em Singapura a +1,490% no Canadá. A Bélgica tem cinco observações e
  nenhuma comparável. O sinal persiste, mas a magnitude depende dos eventos.
- **Pérez:** a diferença de ritmo agregado é pequena; o MAD passa de 0,155 para
  0,126 pp. Ainda assim, o Canadá apresenta MAD 0,685 pp. A agregação entre
  eventos não implica ausência de condições locais com dispersão elevada.

Entre as menores mudanças absolutas de ritmo estão Tsunoda (0,002 pp), Ocon
(0,017), Hülkenberg (0,021), Alonso (0,025) e Albon (0,030). Esses números não
são uma classificação de confiabilidade nem eliminam as diferenças de contexto.

**Cuidado com o resumo do MAD:** Hamilton tem MAD 1,617 pp no Canadá, calculado
com 25 voltas em sete contextos, e isso amplia seu intervalo bootstrap. Uma
mediana pequena das mudanças entre pilotos pode esconder eventos e intervalos
individuais muito diferentes. Sobreposição dos intervalos marginais não é teste
de igualdade entre grupos ou pilotos.

## Conclusão e decisões

A avaliação mostra sinais descritivos que persistem para alguns pilotos e
mudanças relevantes para outros. A menor cobertura da reserva e a mudança de
composição impedem interpretar toda diferença como instabilidade intrínseca ou
erro de implementação. O perfil ainda não constitui habilidade isolada ou
coeficiente universal pronto para o motor.

Manter os resultados como avaliação do método congelado. A próxima investigação
pode comparar companheiros em contextos compartilhados e definir uma referência
de tempo de volta para o experimento determinístico. Se essas investigações
alterarem o método, as 24 corridas usadas agora pertencem ao histórico conhecido;
será necessário separar outra amostra independente antes de nova alegação de
validação. Esta entrega não modifica o agrupamento, o ETL ou o motor.

## Artefatos e reprodução

Pasta completa desta execução:
`data/curated/reserved-evaluations/evaluation-7735cb823f9f44de9b10194ac339842d/`.
Contém JSON com proveniência/auditoria, CSVs de suporte e comparações, relatório
e PNG/SVG de cobertura, ritmo, MAD e intervalos. Os dados permanecem fora do Git.

```bash
pipenv run python -B scripts/evaluate_profiles.py \
  --database data/curated/history-profile-full-2024.sqlite \
  --plan configs/profile-evaluation-2024-expanded.json \
  --bootstrap-replicates 2000 --bootstrap-seed 42 \
  --confidence 0.95 --warn-below-events 5 \
  --output-root data/curated/reserved-evaluations
```

Reexecutar esse comando é reprodução de uma avaliação já examinada, não uma
nova validação independente. A CLI publica uma pasta nova, sem apagar resultados.
A interpretação foi construída consultando `coverage`, `comparisons`,
`event_estimates`, `support` e os contextos dos perfis no JSON publicado.

Verificações: duas execuções produziram JSON e os quatro CSVs idênticos; o
perfil completo de desenvolvimento coincide integralmente com o congelado.
33 testes relevantes passaram (avaliação, incerteza, isolamento do desenvolvimento
e protocolo da amostra). Links locais, sintaxe dos comandos e whitespace passaram.
Gráfico de estabilidade com intervalos inspecionado. Não houve alteração de código.
