# Análise dos 18 eventos de desenvolvimento de 2024

Continuação de #66/#67 na branch `40-modelagem-dos-dados`. Consome somente o
banco de desenvolvimento da [amostra expandida](amostra-pilotos-2024-expandida.md).
A aplicação `analyze_development` recebe o plano completo, mas passa somente
`development_sessions` ao perfilador. Os IDs reservados ficam como metadados do
protocolo; nenhum registro de sessão reservada é solicitado para calcular perfis.

## Comportamento implementado

- Quatro variantes, com os mesmos filtros e mínimos: original, separação por
  stint, janela de cinco voltas e combinação. Reutiliza o estimador existente.
- Suporte e intervalos bootstrap por evento (2.000 réplicas, semente 42, 95%
  nominal, aviso heurístico abaixo de cinco eventos), conforme a
  [documentação da incerteza](sensibilidade-contextos-pilotos.md).
- Retirada de um evento por vez: recalcula a mediana das estimativas dos eventos
  restantes e registra a mudança em pp. Preserva o mínimo de dois eventos;
  se a retirada deixa suporte insuficiente, registra `None` com motivo.
- Relatórios por piloto com diferenças entre variantes, intervalos, suporte e
  influência dos eventos; gráficos PNG/SVG com nomes e contagens.

A influência é exata para a regra de agregação vigente: retirar uma corrida não
altera referências contextuais das outras. Não é teste de previsão futura,
validação cruzada de um modelo ajustado ou nova estimativa de erro estatístico.
Com número par de eventos, a mediana depende dos valores centrais; uma mudança
pequena ao remover um evento pode coexistir com um intervalo bootstrap amplo.
Não interpretar influência pequena como prova de estabilidade geral.

## Resultados observados

| Variante | Voltas comparáveis | Cobertura | Pilotos com perfil | Contextos com mistura |
| --- | ---: | ---: | ---: | ---: |
| Original | 12.558 | 61,98% | 23/24 | 3 |
| Stints | 11.858 | 58,52% | 23/24 | 0 |
| Janela menor | 9.665 | 47,70% | 23/24 | 0 |
| Ambas | 9.165 | 45,23% | 23/24 | 0 |

Todas as variantes partem de 20.262 observações. Em relação ao original, a
mudança absoluta mediana de ritmo **agregado por piloto** é 0,031 pp para
stints, 0,062 pp para janela menor e 0,063 pp para ambas. Os máximos são
0,143/0,500/0,266 pp. Esses números não têm a mesma unidade amostral do estudo
anterior, que resumia diferenças por par piloto/evento.

Jack Doohan tem apenas um evento com suporte e permanece sem perfil agregado.
Oliver Bearman possui três e recebe aviso de poucos eventos. Todos os demais
atingem pelo menos cinco eventos, sem que isso constitua aprovação estatística.

Exemplos no agrupamento original:

| Piloto | Eventos | Voltas | Ritmo (%) | MAD (pp) | Máxima mudança de ritmo ao retirar um evento (pp) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sergio Pérez | 16 | 572 | −0,358 | 0,155 | 0,128 |
| Guanyu Zhou | 17 | 564 | +0,441 | 0,172 | 0,105 |
| Max Verstappen | 18 | 730 | −0,555 | 0,110 | 0,006 |
| Lando Norris | 18 | 746 | −0,673 | 0,132 | 0,011 |

O destaque de Pérez em uma corrida não se traduz em dispersão agregada extrema
neste recorte maior. Zhou mantém ritmo relativo positivo, com diferença menor
que nos primeiros recortes. Verstappen e Norris apresentam tempos relativos
negativos, mas essas estimativas não isolam habilidade e usam referências
contextuais que podem diferir. Não inferir superioridade entre eles apenas
pela ordem dos pontos ou pela sobreposição dos intervalos.

A maior influência de um evento no ritmo agregado aparece para Logan Sargeant
(0,292 pp), Liam Lawson (0,254 pp) e Oliver Bearman (0,191 pp). Esses casos
merecem inspeção; não são classificados automaticamente como outliers.

## Decisões registradas antes de consultar a reserva

O registro legível por máquina está em
[profile-validation-decision-2024.json](../configs/profile-validation-decision-2024.json).
Contém hash do plano, hash da análise de desenvolvimento, variante, configuração,
bootstrap, métricas e política de ausência. Não altera o plano de seleção anterior.

1. Manter o agrupamento **original**. A separação por stint reduz suporte e muda
   o pelotão de comparação para resolver somente três contextos mistos; a janela
   menor perde cerca de 14,28 pontos percentuais de cobertura. Não temos evidência
   de melhor previsão que justifique promover essas alternativas.
2. Manter os mínimos e filtros, sem relaxá-los para incluir todos os pilotos.
3. Na futura avaliação reservada, reportar cobertura, pares disponíveis,
   diferenças de ritmo/MAD em pp e suas medianas absolutas, junto dos motivos de
   indisponibilidade e intervalos marginais. Não converter ausências em zero.
4. Não estabelecer aprovação/reprovação automática nem afirmar erro preditivo:
   a pergunta permanece descritiva. Distribuição de ruído e referência de tempo
   para o motor continuam pendentes no [contrato do perfil](contrato-perfil-simulacao.md).

**A reserva não foi avaliada nesta entrega.** Esse registro fixa as escolhas para
sua consulta posterior. Qualquer ajuste após ver a reserva deverá ser identificado
como nova exploração; a mesma reserva não continuará sendo evidência inédita.

## Executar

```bash
pipenv run python -B scripts/analyze_profile_development.py \
  --database data/curated/history-profile-development-2024.sqlite \
  --plan configs/profile-evaluation-2024-expanded.json
```

A saída é uma pasta nova em `data/curated/development-studies/development-...`.
`--without-plots` dispensa Matplotlib e `--output-root` muda a pasta pai.
Configuração do perfil vem do plano; parâmetros do bootstrap e janela alternativa
são explícitos no caso de uso Python e registrados no JSON/hash da execução.
A CLI usa os valores documentados acima. A publicação é atômica e preserva
relatórios existentes; não exige criar/apagar pastas nem um JSON de perfil prévio.

Resultados desta execução:
`data/curated/development-studies/development-1147b746d0c14c22bcff802f2f219c41/`.
A pasta inclui `analysis.json`, `report.md`, CSVs por variante e gráficos.
Os testes verificam ausência de consultas à reserva, invariância ao remover
seus feeds, influência conhecida com e sem suporte e publicação transacional.
