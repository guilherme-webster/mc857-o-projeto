# Companheiros e referência de tempo determinística

Entrega de 18/09/2026 para #66/#67, branch `40-modelagem-dos-dados`.
A análise usa os 18 eventos do banco de desenvolvimento. As 24 corridas de
2024 já são conhecidas; este estudo é exploratório e não constitui uma nova
validação. A [avaliação da reserva](avaliacao-reserva-pilotos-2024.md) permanece
inalterada. Não há mudança de ETL nem integração ao motor nesta entrega.

## Comparação realmente pareada

Os candidatos vêm das inscrições canônicas e da equipe no resultado da corrida.
Um par só existe quando os dois pilotos participaram da mesma sessão pela mesma
equipe. Troca de companheiro/equipe cria outro par; não juntar trajetórias de
substitutos ou transferências. Equipe ausente/ambígua é erro explícito.

Reutilizamos `contextual-pace-v1`, incluindo todos os filtros anteriores e o
mínimo de três voltas e três pilotos no contexto de comparação do pelotão.
Portanto, esta entrega **não relaxa esse mínimo para dois pilotos**. Um contexto
compartilhado precisa existir nos dois perfis com a mesma chave: sessão/corrida,
circuito, composto, chuva booleana, janela de volta e janela de idade do pneu.

Para cada contexto, usamos as medianas observadas dos dois pilotos, em ms:

```text
gap_contexto_pct = 100 × (mediana_A − mediana_B) / ((mediana_A + mediana_B) / 2)
gap_evento_pct = mediana(gaps dos contextos compartilhados naquele evento)
gap_par_pct = mediana(gaps dos eventos compartilhados)
```

A ordem A/B é estável pelo ID canônico, não por desempenho. Negativo significa
A com tempo menor; positivo, B com tempo menor. O denominador é simétrico:
trocar A e B apenas inverte o sinal. **Esse percentual usa a média das duas
medianas como referência**, não o tempo de B nem a referência do pelotão.
Não subtrair os dois perfis agregados para obter esse resultado: eles podem ter
contextos e eventos diferentes. Também não encadear pares para criar ranking
transitivo entre equipes.

Cada evento tem peso igual, independentemente de quantidade de voltas/contextos.
Exigimos pelo menos dois eventos compartilhados para o agregado. A ausência
fica `None`, com motivo, conservando suporte por evento/contexto no JSON.

O intervalo é bootstrap percentil pareado por evento: 2.000 réplicas, semente
42, 95% nominal. Cada sorteio mantém a diferença do par inteira; nunca sorteia
os dois pilotos independentemente ou trata voltas como amostras independentes.
Menos de cinco eventos recebe aviso; intervalo degenerado não significa certeza.
São intervalos marginais exploratórios, sem correção para múltiplas comparações
ou teste causal de habilidade. Um intervalo que não cruza zero, especialmente
com dois eventos, não aprova automaticamente uma conclusão.

## Cobertura e resultados

Foram encontrados 15 pares por equipe; 12 têm pelo menos dois eventos
compartilhados. Existem pares indisponíveis mesmo quando ambos têm perfis gerais:
Albon/Colapinto compartilham apenas um dos sete eventos em que correram juntos.
Gasly/Doohan e Leclerc/Bearman também têm somente um evento compartilhado.

| A − B | Eventos compartilhados/candidatos | Contextos compartilhados/união | Gap (%) | Intervalo nominal 95% |
| --- | ---: | ---: | ---: | --- |
| Pérez − Verstappen | 14/18 | 95/221 | +0,501 | [+0,252; +0,970] |
| Norris − Piastri | 17/18 | 124/229 | −0,187 | [−0,480; −0,042] |
| Bottas − Zhou | 12/18 | 44/229 | −0,163 | [−0,417; +0,156] |
| Hamilton − Russell | 15/18 | 96/233 | +0,053 | [−0,046; +0,268] |
| Sainz − Leclerc | 17/17 | 119/216 | +0,027 | [−0,195; +0,187] |

A união considera contextos elegíveis presentes em pelo menos um piloto nos
eventos em que eram companheiros; não todas as voltas brutas do calendário.
O relatório também registra contextos individuais e voltas de A/B retidas.

Pérez apresenta tempos maiores que Verstappen nos contextos pareados agregados;
Norris apresenta tempos menores que Piastri. Esses sinais são distintos de
comparar cada um contra todo o pelotão. Bottas/Zhou retêm somente 44 contextos
compartilhados de 229 na união; a comparação não sustenta atribuir diretamente
o ritmo geral positivo de Zhou à sua habilidade individual.

Emparelhar equipe e contexto reduz algumas diferenças observáveis, mas não
elimina acerto, atualizações do carro, tráfego, estratégia, ordens de equipe ou
evolução da pista dentro das janelas. A janela não garante voltas simultâneas.
O número do stint continua fora da chave padrão, com sua contagem preservada
na auditoria. Não descartar seletivamente contextos após ver seus resultados.

## Referência concreta para o experimento determinístico

Adotar `observed_context_field_median_v1`: **mediana das medianas observadas de
cada piloto elegível em um único contexto exato**, com peso igual por piloto.
É a referência já usada pelo perfilador; a função `context_reference` verifica
se o pelotão está completo e se todas as estimativas concordam com essa referência.
Contexto inexistente ou referência inconsistente gera erro, sem procurar outro
circuito/composto. A aplicação exporta 444 referências elegíveis no recorte.

Contrato retornado:

- chave completa `PaceContext`, incluindo sessão, circuito, composto, chuva e
  janelas; a referência não é identificada somente pelo nome do circuito;
- `reference_lap_time_ms`, número/IDs de pilotos e número de voltas;
- `reference_kind`, `variability_mode=disabled` e indicação de que não devem
  ser acrescentados efeitos de equipe/pneu/clima já presentes;
- versão/configuração/seleção e manifestos do ETL no relatório que contém a
  referência, para que o parâmetro não circule sem sua proveniência.

Exemplo auditável, primeira chave ordenada da execução: Bahrein/2024,
`session:1121:R`, `circuit:3`, HARD, chuva falsa, janela de corrida 11–20 e idade
de pneu `[0,5)` voltas. São 18 pilotos e 54 voltas; a referência é
**97.175,5 ms (97,1755 s)**. Isso não escolhe o circuito definitivo do MVP.

O microexperimento proposto é uma volta com esse contexto congelado:

```text
tempo_neutro_ms = referencia_contexto_ms
efeito_ritmo_ms = referencia_contexto_ms × deslocamento_contextual_pct / 100
tempo_modelado_ms = referencia_contexto_ms + efeito_ritmo_ms
```

O deslocamento deve vir **do mesmo contexto e da mesma referência**, com seu
ID de piloto/equipe. Não aplicar o gap simétrico entre companheiros nem o perfil
anual agregado diretamente nessa fórmula. O gap do par responde a outra pergunta
com outro denominador e não fornece sozinho os dois tempos absolutos.

No contexto do exemplo, Norris tem deslocamento −0,4111118543% e mediana observada
96.776 ms; Piastri, −0,3905305350% e mediana 96.796 ms. A fórmula reconstrói essas
medianas por definição. Esse é um teste de consistência de unidades e contrato,
**não evidência de capacidade preditiva**. Uma referência externa a esses mesmos
dados será necessária para avaliar previsão de tempo em outro evento.

Não adicionar novamente efeito de equipe, pneu, combustível ou clima à referência
observacional sem primeiro decompor/calibrar esses efeitos. Não inserir ruído de
MAD ou do bootstrap. Sem referência/deslocamento compatível, devolver condição
de indisponibilidade; zero só é válido como cenário neutro escolhido explicitamente.

Preservar valores fracionários em ms nos cálculos. Na futura fronteira do relógio
inteiro, arredondar o tempo final uma única vez para o ms mais próximo, com meio
ms para cima (`ROUND_HALF_UP`); não arredondar parcelas antes da soma. A referência
neutra do exemplo seria 97.176 ms nessa fronteira. A política é especificada aqui;
a integração com o relógio/motor não foi implementada nesta fatia.

A proposta cobre um contexto congelado, não degradação ao longo de uma corrida
inteira. A escolha de referências para sucessivas voltas, efeitos causais separados,
transferência para outro circuito/ano e ruído calibrado permanecem pendentes.

## Reprodução e artefatos

```bash
pipenv run python -B scripts/analyze_teammates.py \
  --database data/curated/history-profile-development-2024.sqlite \
  --plan configs/profile-evaluation-2024-expanded.json
```

A CLI seleciona somente `development_sessions`, publica pasta nova e imprime o
caminho. `--without-plots` dispensa Matplotlib; `--output-root` altera a pasta pai.
Parâmetros de suporte vêm do plano; bootstrap é explícito no caso de uso Python.
São produzidos `analysis.json` com perfis/proveniência/pares/contextos/eventos,
`pairs.csv`, `references.csv`, `report.md` e `teammates.png/.svg` com nomes.
Nada é sobrescrito; falhas de publicação preservam saídas anteriores.

Execução completa com gráficos:
`data/curated/teammate-studies/teammates-593cc2a0d9bf4ef9bd11a83888a9de55/`.
Duas execuções produziram JSON e os dois CSVs idênticos. Gráfico com nomes dos
pilotos e equipes inspecionado. A suíte completa passou com 161 testes, sem
falhas e 13 ignorados pelas condições gráficas existentes. Nove testes novos
cobrem fórmula/sinal, ordem, contextos distintos, mínimos, troca de equipe,
referência completa, ponderação por evento, isolamento de sessões e publicação.
Ruff, whitespace, links locais e sintaxe do comando novo passaram.
