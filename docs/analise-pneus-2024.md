# Pneus em 2024: evolução por stint, início e cobertura

Estudo exploratório de 18/09/2026, issue #63, branch `63-modelagem-pneus`.
**Conclusão principal:** os dados permitem estudar evolução líquida de tempo,
mas ainda não justificam coeficientes universais de desgaste ou uma penalidade
fixa de aquecimento. Há forte dependência de evento, seleção e início do stint.

## Reprodução e artefatos

```bash
pipenv run python -B scripts/analyze_tyres.py \
  --database data/curated/history-profile-development-2024.sqlite \
  --plan configs/profile-evaluation-2024-expanded.json
```

Somente as 18 sessões de desenvolvimento são consultadas; a reserva não entra.
A publicação cria uma pasta única em `data/curated/tyre-studies/` com:

- `analysis.json`: configuração, versão, manifestos, pontos, exclusões e ajustes;
- `stints.csv`: suporte, inclinações, MAEs e contrastes por piloto/stint;
- `coverage.csv`: cobertura e mediana de inclinações por evento/composto;
- `pilotos-stints.pdf`: atlas dos 18 eventos, com painel por piloto e identificação
  de cada stint; páginas completas e zoom nas voltas aprovadas;
- `session-<race>-R.png` e `session-<race>-R-zoom.png`: mesmas vistas em PNG;
- `cobertura-tendencias.png/.svg` e `inicio-sensibilidade.png/.svg`: sínteses;
- `graficos.md`: índice navegável dos eventos.

Nomes dos pilotos vêm do catálogo canônico. Cruz cinza significa volta excluída;
pontos coloridos, aprovados. A linha tracejada é uma tendência linear descritiva.
O zoom inclui **todas** as voltas aprovadas e conta as excluídas fora da escala;
a vista completa preserva também essas observações. Falta de tempo não é zero.
Os artefatos locais não são versionados. `--without-plots` permite reproduzir
JSON/CSV sem Matplotlib; não cria imagens nessa execução.

## Método e denominadores

Unidade de análise: sessão/piloto/stint, sem juntar stints do mesmo composto.
Preservados os filtros de qualidade do perfilamento; removidos somente os dois
mínimos específicos da comparação entre pilotos. Acrescentada exigência de
rainfall conhecido e falso para estudar compostos secos. Idade e stint ausentes
não são imputados. Compósitos INTERMEDIATE/WET aparecem na cobertura e no atlas,
mas não recebem ajuste de desgaste seco.

A auditoria verifica composto/fresh_tyre estáveis e incrementos de idade iguais
aos incrementos da volta da corrida. Não encontrou inconsistências nos 958
stints deste recorte. Isso não demonstra integridade física de um conjunto nem
resolve a convenção de idade pré/pós-volta para o futuro core.

Ajustes exigem cinco voltas aprovadas e amplitude de idade >=4. Calculados OLS
(mínimos quadrados) e mediana das inclinações de todos os pares de idades
diferentes como diagnóstico robusto. Não se trunca resultado negativo.
As MAEs são **dentro da própria amostra**, contra constante mediana e reta OLS;
não medem previsão. A reta minimiza erro quadrático, não MAE.

Para o início, posição no stint = volta da corrida menos primeira volta
registrada do stint +1, **não posição entre voltas filtradas**. Exigimos início
identificável por volta 1 ou registro de pit-out. No contraste pós-pit, comparamos
mediana das posições 2–3 (ambas aprovadas) com mediana das posições 5–8 (>=3
aprovadas), separando pneu novo/usado. Stints que começam na largada ficam fora
dessa síntese. Pit-out também ocorre no contexto de relargadas: não prova uma
parada convencional. Esse contraste não mede temperatura nem duração térmica.

## Cobertura: boa para secos, desigual entre compostos

| Composto | Voltas observadas | Aprovadas | Stints observados | Stints ajustados |
| --- | ---: | ---: | ---: | ---: |
| SOFT | 1.517 | 1.158 | 131 | 92 |
| MEDIUM | 6.394 | 5.214 | 357 | 306 |
| HARD | 10.983 | 9.743 | 395 | 370 |

Total: 20.262 observações/958 stints incluindo chuva; 17.069 voltas aprovadas
incluindo 953 INTERMEDIATE e uma WET. Os 768 ajustes são de compostos secos.
A exigência adicional de chuva falsa retirou 124 voltas antes aceitas no
levantamento inicial (17.193 → 17.069), sem reduzir o número de stints que
atingem os mínimos de ajuste. Exclusões no JSON podem se sobrepor.

SOFT tem ajuste em 11 eventos, MEDIUM em 16 e HARD em 17. São Paulo não fornece
ajuste seco neste protocolo. A maior idade observada nos ajustes é 27 para
SOFT, 76 para MEDIUM e 77 para HARD; isso não é vida útil autorizada universal.
Amplitude mediana por stint ajustado: 11, 15 e 24 voltas, respectivamente.

**Leitura dos gráficos:** a cobertura não é uniforme e misturar todos os pontos
favorece eventos com mais stints/voltas. O painel de cobertura deve acompanhar
qualquer comparação entre compostos. Pneus de chuva exigem outro estudo; uma
única volta WET aprovada é insuficiente para uma curva neste recorte.

## Evolução: inclinação líquida não equivale a desgaste

| Composto | Mediana entre stints (ms/volta de idade) | Inclinações negativas | Mediana das medianas por evento |
| --- | ---: | ---: | ---: |
| SOFT | +32,5 | 26/92 (28,3%) | +17,7 |
| MEDIUM | +23,2 | 103/306 (33,7%) | +24,7 |
| HARD | +6,4 | 170/370 (45,9%) | −7,3 |

Cada evento recebe peso igual na última coluna; na primeira cada stint recebe
peso igual. A mudança de sinal de HARD entre agregações mostra por que não
converter uma mediana agrupada em parâmetro universal.

No gráfico por evento, por exemplo, HARD tem mediana +39,4 ms/volta no Bahrein,
−76,9 na Arábia Saudita e −7,3 na Itália. MEDIUM varia de −92,9 em Mônaco a
+125,3 em Las Vegas. SOFT tem pouca cobertura em alguns eventos: medianas de um
ou dois stints são descritivas e não sustentam comparação firme.

Medianas de MAE constante → linear, em ms, entre stints:
SOFT 299 →260; MEDIUM 344 →265; HARD 385 →321.
A reta reduz MAE em 62/92, 212/306 e 269/370 stints, respectivamente. Há estrutura
temporal em parte da amostra, mas ganhos de ajuste não são validação preditiva
nem isolamento do efeito físico dos pneus.

### Caso concreto: Japão, Gasly, stint 2

A figura do Japão mostra um ponto aprovado de 138.362 ms na volta 3 (idade 2),
seguido de 99.925 ms na volta 4. O stint produz OLS **−1.074,6 ms/volta**, mas
mediana de inclinações entre pares **+168,5 ms/volta**. MAE da constante:
3.476 ms; da reta: 5.970 ms. Um início lento pode dominar o ajuste linear.

O dado canônico registra `Aborted` e depois `Started` nessa sessão; a primeira
volta do stint é a volta 2, com pit-out e tempo ausente. A volta 3 já tem
`accurate=True` e pista `1`, passando pelos filtros atuais. Ocon e outros
pilotos mostram comportamento semelhante. Isso aponta a necessidade de
investigar a janela após relargadas, não prova que o pneu tenha melhorado
fisicamente mais de um segundo por volta. Os dados não foram apagados nem
reclassificados ad hoc para melhorar os resultados deste estudo.

## Início e aquecimento: evidência heterogênea

Valor positivo significa posições 2–3 mais lentas que 5–8. A tabela usa
mediana por evento e depois mediana entre eventos, evitando dar peso maior a
corridas com mais stints elegíveis.

| Composto | Conjunto | Stints pareados | Eventos | Contraste (ms) |
| --- | --- | ---: | ---: | ---: |
| SOFT | novo | 17 | 7 | −491,5 |
| SOFT | usado | 11 | 4 | −186,5 |
| MEDIUM | novo | 75 | 14 | +3,5 |
| MEDIUM | usado | 29 | 11 | −91,5 |
| HARD | novo | 244 | 16 | −4,0 |
| HARD | usado | 54 | 12 | +48,5 |

Para HARD novo, oito dos 16 eventos têm contraste positivo; para MEDIUM novo,
sete dos 14. Não há sinal uniforme. No SOFT novo, seis de sete eventos têm
contraste negativo: neste recorte, o começo observado é frequentemente mais
rápido que o trecho posterior. Isso **não prova ausência de aquecimento**;
as voltas excluídas podem conter justamente o fenômeno, e só stints suficientemente
longos/completos entram no pareamento.

No gráfico de início, Mônaco se destaca com +3.148 ms para MEDIUM novo
(seis stints) e +3.221 ms para HARD novo (quatro stints). A sessão também contém
interrupção e retomada. Na sensibilidade exploratória que retira inteiramente
Japão e Mônaco, o contraste de MEDIUM novo muda de +3,5 para −37,25 ms (12
eventos); HARD novo permanece −4 ms (14 eventos). Essa retirada é diagnóstico
posterior, não um novo filtro validado ou estimativa causal de aquecimento.

Não há teste de hipótese ou intervalo de confiança nesta síntese; a dispersão
dos pontos representa medianas observadas dos eventos, não incerteza estimada.
Não tratar extremos visuais como outliers estatísticos.

## Sensibilidade a cortar o início do stint

Comparação pareada apenas dos stints que têm ajuste antes e depois do corte:

| Composto | Ajustes após retirar posições 1–3 | Mudanças de sinal | Mediana da mudança de inclinação (ms/volta) |
| --- | ---: | ---: | ---: |
| SOFT | 86/92 | 13/86 | +5,76 |
| MEDIUM | 291/306 | 22/291 | +1,46 |
| HARD | 368/370 | 33/368 | +0,15 |

Ao retirar posições 1–5, ficam 76/92, 270/306 e 364/370 ajustes; mudam de sinal
18, 34 e 46, respectivamente. A mediana da mudança é pequena, mas alguns
stints são muito sensíveis, como aparece longe da diagonal no gráfico. Logo,
não se deve decidir um corte universal só pela pequena mudança da mediana.
O corte custa proporcionalmente mais cobertura em SOFT.

## Conclusões para a modelagem e o core

1. **Não exportar estes slopes como desgaste calibrado.** A idade acompanha a
   volta da corrida dentro do stint; combustível, tráfego e pista permanecem
   confundidos. Zero forçado em slopes negativos esconderia essa evidência.
2. **Não implementar agora uma penalidade universal de aquecimento.** Os
   contrastes têm sinais diferentes, seleção importante e relargadas misturadas.
   Precisamos identificar a primeira sequência após interrupções e estudar
   início operacional separado de efeito térmico.
3. **Começar com um evento/composto e referência ancorada explícita.** HARD tem
   mais cobertura, mas não é automaticamente mais identificável: quase metade
   dos slopes é negativa. Escolher o recorte pela cobertura e qualidade, não
   apenas pelo sinal desejado. A referência de piloto por janela ainda precisa
   de uma idade de ancoragem compatível.
4. **Próxima fatia recomendada:** marcar relargadas e voltas adjacentes;
   comparar regressão robusta e OLS em stints pareados; investigar comparação
   entre participantes na mesma fase da corrida e idades diferentes. Definir
   partições por evento e métricas antes de calibrar parâmetros para o core.
5. **O contrato pode evoluir independentemente:** implementar e testar a regra
   determinística ancorada com valores explicitamente assumidos, mantendo sua
   origem distinta dos estimados. Este estudo não altera o core do colega.

Nenhuma fonte nova foi adquirida; bancos e dados brutos foram preservados.
As conclusões derivam dos registros canônicos e dos artefatos reproduzíveis acima.
