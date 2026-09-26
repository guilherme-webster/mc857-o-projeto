# Protocolo exploratório: SC/VSC e estimadores de tendência

Registrado em 18/09/2026 antes de calcular os resultados desta comparação.
Somente 18 eventos de desenvolvimento; sem novas fontes ou alteração do core.

1. Detectar episódios de track status SC (4), VSC (6/7), concluídos pelo primeiro
   AllClear (1). Amarelo intermediário não encerra o episódio; vermelho (5)
   cancela sua atribuição e é tratado pela retomada Aborted→Started já existente.
   Episódio sem AllClear permanece aberto e não inventa retomada. Ordem canônica
   de sequence desempata mensagens no mesmo instante, com auditoria explícita.
2. Manter exclusão de duas voltas após Aborted→Started como referência operacional.
   Comparar SC/VSC com janelas 0,1,2,3,5, mantendo âncora anterior aos filtros e
   união das marcações quando episódios se sobrepõem. Comparar cobertura, sinais
   e mudanças pareadas de inclinação. SC/VSC janela 2 é recorte primário fixado
   antes dos resultados; demais janelas são sensibilidade, não seleção pelo erro.
3. Comparar OLS e mediana das inclinações entre pares; intercepto robusto =
   mediana(y − slope*x). Usar os mesmos stints, cinco voltas e amplitude >=4.
   Medir influência pela maior mudança absoluta do slope ao retirar uma volta,
   apenas nos stints em que todos os ajustes reduzidos continuam elegíveis.
4. Avaliação interna por evento deixado de fora: para cada composto, obter slope
   de cada stint nos outros eventos, mediana por evento e mediana entre eventos
   (mínimo dois eventos de treino). No evento alvo, usar primeiras cinco voltas
   aprovadas de cada stint como âncora local do intercepto e prever as seguintes
   (mínimo três). Sem usar as voltas futuras na âncora nem no treinamento.
   Comparar constante, slope OLS transferido e slope robusto transferido nas
   mesmas voltas; mediana de MAE por stint e depois por evento. É avaliação de
   transferência de tendência com adaptação inicial, não previsão sem histórico
   e não estima slope local nas primeiras cinco voltas.
5. Reportar deltas de MAE por evento e intervalos exploratórios por reamostragem
   de eventos inteiros (2.000 replicações, semente 42, percentis 2,5/97,5).
   Sem tratar voltas como independentes. Eventos já explorados: não é validação
   final intocada. Não escolher janela/coeficientes usando esses erros.
6. Não truncar slopes negativos, não exportar coeficientes para o core e não
   promover ganho dentro da amostra a evidência preditiva. Separar ganhos de
   robustez, cobertura e desempenho fora do evento de treinamento.
