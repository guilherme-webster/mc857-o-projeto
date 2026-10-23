# 0009 - Combustível por massa e reabastecimento como regra de cenário

- Status: proposta
- Data: 2026-10-23
- Responsáveis: issue de modelagem do combustível (branch
  `97-modelagem-combustivel`)
- Relaciona-se com: ADR 0002 (Trotman como fonte e aleatoriedade injetável),
  ADR 0003 (geometria FastF1 restrita ao traçado), ADR 0008 (heurísticas
  rotuladas sobre o motor calibrado) e a calibração da #40

## Contexto

O motor calibrado da #40 tratava o combustível como uma penalidade linear por
volta restante: 52,3 ms por volta, igual em todos os circuitos e sem estado por
carro. Isso impedia três coisas pedidas para o simulador:

- saber quanto combustível cada carro carrega e exibi-lo na corrida;
- diferenciar circuitos: uma volta em Spa queima o dobro de uma em Mônaco;
- representar paradas de reabastecimento.

Restrições:

- o regulamento de 2010 em diante proíbe reabastecer e limita a carga a 110 kg;
  a API aceita corridas de até 200 voltas, bem além do alcance de um tanque;
- o Trotman não registra combustível; só o efeito no tempo de volta é
  observável;
- o caminho legado do motor (hashes da #40) não pode mudar.

## Alternativas consideradas

- **A. Manter a penalidade linear.** Sem custo, mas sem estado por carro, sem
  kg e sem diferença entre circuitos.
- **B. Massa por carro com a regra 2010+.** Fiel ao regulamento atual: carga
  até 110 kg, economia (lift-and-coast) e pane seca. Corridas além do alcance
  terminam com abandonos por falta de combustível.
- **C. Massa por carro com reabastecimento como regra do cenário**, mantendo B
  disponível por chave.

## Decisão

Adotar C.

- O combustível é massa embarcada por carro (`domain/fuel.py`), integrada volta
  a volta: a volta é o passo do motor, e a interface interpola dentro dela.
  O consumo é por km vezes a extensão da pista, reduzido sob SC, VSC e
  vermelha; o custo no tempo é proporcional à massa e à duração da volta.
- O coeficiente de tempo é calibrado no Trotman 2022–2023 e validado fora da
  amostra em 2024–2025. Consumo em kg/km, reserva, fatores de neutralização,
  vazão e troca de pneus são hipóteses rotuladas `assumed`.
- Com `refuelling_allowed` (padrão do cenário), toda parada troca pneus e
  reabastece, como na era 1994–2009. Quando parar e quanto colocar é decisão de
  `HeuristicPitStrategy`, que pesa desgaste, peso do combustível e custo da
  parada; o único limite físico é chegar à entrada dos boxes. Cada piloto tem
  preferências próprias (`FuelStrategyTraits`), sorteadas por semente a partir
  da agressividade.
- O tempo de parada de cada carro é a perda de boxes medida do circuito mais o
  deslocamento real da equipe (paradas do Trotman 2023–2024) e uma variação por
  parada, mais o tempo de abastecer além da troca de pneus.
- A geometria FastF1 fornece só a extensão da volta e a posição da entrada dos
  boxes, o que é traçado (ADR 0003). Ela não define o tempo de pit lane: o
  caminho mockado não prediz a perda medida (correlação 0,24 em 20 circuitos).
- Sem `FuelPlan`, o motor segue o caminho legado intacto.

## Consequências

- **Validação registrada em `data/parameters/fuel-v1.json`.** Erro da
  inclinação de combustível por corrida: 16,1 ms/volta com a massa contra 22,3
  com o linear, em 47 corridas de 2024–2025 (mediana 6,1 contra 11,1).
  Nenhuma corrida de distância real de 2022–2025 passa de 110 kg, e o fluxo
  médio fica entre 53 e 87 kg/h, abaixo do limite de 100 kg/h. Uma checagem
  exploratória em voltas FastF1 de 2024 com composto conhecido reestimou o
  coeficiente em 1,22–1,29 × 10⁻⁴, contra 1,271 × 10⁻⁴ do Trotman (export CSV
  de terceiros, não versionado, proveniência a confirmar).
- **Tempo de parada por equipe.** A variação por parada cobre 80,0% das paradas
  reais de 2025 entre os percentis 10 e 90. O deslocamento por equipe previu
  2025 pior que "todas iguais" (131 contra 118 ms), porque o campo convergiu.
- **Desvio do regulamento atual.** Com o reabastecimento ligado, corridas de
  distância real passam a ter 2–3 paradas combinadas, como em 2009, e não como
  em 2024. A regra 2010+ continua disponível (`refuelling_allowed = false`, ou
  `--no-refuelling` em `scripts/calibrate_fuel.py`).
- **Estratégia sem validação histórica.** O Trotman só registra paradas a
  partir de 2011, então a estratégia de reabastecimento não foi confrontada com
  1994–2009. Paradas dessa era podem ser inferidas dos tempos de volta em
  trabalho futuro.
- **Hipóteses a revisar:** 0,344 kg/km igual em todos os traçados, 9 kg/s,
  2,5 s de troca de pneus e fatores 0,5/0,6 de SC/VSC. Valores e onde mudá-los
  estão em `docs/modelagem-heuristica.md`.
- **Pneus não mudam nesta decisão.** Uma tentativa de calibrar os compostos em
  voltas FastF1 corrigidas pelo combustível não superou os compostos do
  `model-v1.json` na reserva de 2024 nem em 2023, e ficou para o backlog da
  issue #63.
