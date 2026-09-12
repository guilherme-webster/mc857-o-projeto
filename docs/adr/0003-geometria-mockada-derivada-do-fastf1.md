# 0003 - Geometria mockada derivada do FastF1

- Status: aceita
- Data: 2026-09-08
- Responsaveis: grupo do projeto

> Esclarecimento de terminologia em 2026-09-11: "mock" designa neste registro
> uma geometria reduzida derivada de observacoes reais, com aproximacoes; nao
> significa dados inventados. Preserva-se o texto historico e o escopo aceito.
> A reducao dos dados nao altera por si so as condicoes de uso da fonte.

## Contexto

O dataset Trotman v128 registra apenas latitude e longitude de cada circuito,
portanto nao permite construir seu contorno. A simulacao precisa de pontos
ordenados e distancia acumulada para representar uma pista e, futuramente,
interpolar a posicao visual dos carros. O repositorio de referencia
`IAmTomShaw/f1-race-replay` deriva essa forma da telemetria posicional acessada
por FastF1.

O FastF1 e distribuido sob MIT, mas essa licenca cobre o software e nao concede
direitos adicionais sobre os dados upstream da Formula 1. Assim, telemetria
bruta ou cache nao devem ser incorporados ao repositorio.

## Alternativas consideradas

- Inferir o contorno da latitude/longitude do Trotman: impossivel, pois existe
  somente um ponto geografico por circuito.
- Manter a pista oval ficticia: suficiente para o spike visual, mas nao
  representa o circuito selecionado.
- Usar GeoJSON ou OpenStreetMap: fornece geometria, mas introduz outra fonte e
  exige identificar corretamente relacoes e licencas por circuito.
- Derivar uma polilinha reduzida com FastF1: segue a referencia visual ja
  estudada e fornece X/Y ordenados junto da distancia da volta.

## Decisao

Usar FastF1 3.8.3 somente como ferramenta de geracao offline. Uma primeira
amostra de Interlagos usa a corrida de Sao Paulo de 2024. Para cobrir a selecao
de pistas, as 24 etapas do calendario de 2025 usam uma volta representativa da
corrida correspondente, associada ao `circuitId` do Trotman v128. Cada volta e
reamostrada em intervalos iguais de distancia. As coordenadas X/Y serao
centralizadas e escaladas uniformemente para um espaco sem unidade, preservando
a proporcao do desenho. O artefato final guardara `circuitId`, sequencia, X, Y e
distancia acumulada em metros.

Para cada circuito, uma parada completa observada na corrida tambem fornece a
polilinha entre `PitInTime` e `PitOutTime`. Ela usa a mesma transformacao da
pista. Um unico ponto de servico representativo e marcado no centro das
posicoes de menor velocidade; ele nao pretende localizar a garagem real de
cada equipe.

Esta decisao introduz uma excecao explicita e restrita a regra de fonte unica
do ADR 0002; ela nao autoriza usar FastF1 para ritmo, clima, pneus ou qualquer
outro dado do simulador.

O cache do FastF1 foi criado em diretorio temporario exclusivo da execucao e
apagado automaticamente. Apenas as polilinhas reduzidas e os manifestos com
fonte, versao, data, transformacao e checksum sao versionados. Os scripts e o
codigo auxiliar de geracao foram removidos depois da validacao. A geometria e
um mock educacional derivado, nao uma fonte oficial nem telemetria redistribuida.

## Consequencias

- O Trotman permanece a fonte dos dados historicos do MVP; o FastF1 e uma
  segunda fonte limitada exclusivamente a geracao da geometria.
- A aplicacao e o motor nao dependem de FastF1 em tempo de execucao.
- O calendario de 2025 resulta em 24 polilinhas independentes, todas ligadas
  aos IDs de circuito ja existentes no Trotman v128.
- Cada pista tem ainda um caminho de pit lane e um ponto de servico mockado;
  posicoes individuais dos boxes continuam fora do escopo.
- Regenerar ou acrescentar pistas exigira reintroduzir uma ferramenta offline,
  revisar a transformacao e produzir novos manifestos sem versionar telemetria
  bruta.
- A visualizacao da pista permanece fora desta decisao e da issue de geracao.
