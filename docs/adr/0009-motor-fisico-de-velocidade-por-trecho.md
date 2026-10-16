# 0009 - Motor físico de velocidade por trecho

- Status: aceita
- Data: 2026-10-01
- Responsável pela autorização: usuário, nesta sessão, ao escolher o desenho B
  (velocidade física gera o tempo) com envelope global inicial de 320 km/h na
  reta e 90 km/h na curva
- Atualiza: o recorte do ADR 0008, que fixou o motor calibrado como fonte do
  tempo de volta e exigiu que todo recurso novo fosse um modulador neutro por
  padrão
- Relaciona-se com: ADR 0002 (aleatoriedade injetável e reprodutível), ADR 0003
  e 0005 (geometria mockada derivada do FastF1) e ADR 0008 (modelagem
  heurística sobre o motor calibrado)

## Contexto

Hoje a simulação modela o tempo de uma volta como um escalar por carro
(`domain/lap_time.py::compute_lap_time`), e a posição na pista é reconstruída
pela visualização assumindo velocidade constante. Nessa estrutura a velocidade
é um resíduo: ela é derivada do tempo, nunca o contrário. Como consequência, a
geometria do circuito é cosmética — apagar uma curva não muda o resultado da
corrida em nenhum milissegundo.

O usuário quer o oposto: que a velocidade de um piloto varie dentro da volta,
mais alta na reta e mais baixa na curva, que essa velocidade seja observável a
cada quadro, e que ela afete o resultado da corrida. Isso inverte a causalidade
do motor: a velocidade passa a ser a grandeza de primeira classe e o tempo de
volta emerge da integral do movimento.

Essa inversão colide com o ADR 0008 em dois pontos. Primeiro, o 0008 fixou que o
tempo de volta vem da física calibrada em 2022–2024 e que todo recurso novo é um
modulador neutro por padrão, de modo que, sem ele, o motor reproduz exatamente o
resultado calibrado. Um motor que gera o tempo a partir da velocidade não é um
modulador: ele substitui a fonte do tempo. Segundo, o dado disponível não
contém física de curva. A geometria dos ADRs 0003 e 0005 é uma polilinha de
pontos `(x, y, distância)` sem raio, velocidade de ápice ou aderência, e o
Trotman v128 não registra telemetria. Qualquer velocidade por trecho é, portanto,
uma hipótese derivada da curvatura da polilinha, não uma medição.

O `AGENTS.md` proíbe conciliar silenciosamente decisões divergentes e apresentar
como medido o que é hipótese, e exige decisão explícita e ADR para substituir a
combinação de padrões aceita. Daí este registro.

## Alternativas consideradas

- **Manter o motor calibrado e tratar a velocidade só como visualização**
  (desenho A): a velocidade por trecho governa a animação, mas o tempo de volta
  continua vindo da calibração. Barato, preserva a reprodutibilidade dos
  backtests e não exige ADR. Rejeitada pelo usuário: não permite que um carro
  com melhor saída de curva ganhe tempo real, nem modela aceleração como
  dinâmica, apenas como aparência.
- **Velocidade física que preserva o tempo de volta calibrado**: redistribui o
  tempo calibrado pela curvatura, modulando o formato do perfil por atributo.
  Mantém a âncora histórica, mas não deixa a velocidade de reta de um carro ser
  independente do seu tempo de volta — o que o usuário quer. Rejeitada.
- **Motor físico de velocidade por trecho** (desenho B, esta decisão): o carro
  tem estado de velocidade, acelera e freia dentro de limites assumidos, e o
  tempo de volta emerge da integração ao longo da geometria. Permite carros com
  caráter distinto (reta forte, curva fraca) e aceleração como dinâmica real.
  Custa a calibração histórica como fonte do tempo. Escolhida.

## Decisão

Introduzir um motor físico de velocidade por trecho, desligado do caminho de
produção enquanto esta proposta não for aceita, e promovê-lo a fonte do tempo de
volta quando for.

1. **Velocidade como grandeza de primeira classe.** O protótipo
   `domain/speed_dynamics.py` modela o estado de velocidade do carro ao longo da
   linha de centro. A velocidade-alvo de cada ponto vem da curvatura da
   polilinha: virada nula tende à velocidade de reta, a virada mais fechada da
   volta tende à velocidade de curva. O carro acelera em direção ao alvo
   limitado por uma aceleração máxima e freia antes da curva limitado por uma
   frenagem máxima, calculada olhando adiante. O tempo de volta é a soma dos
   tempos de cada trecho.

2. **Parâmetros assumidos e rotulados.** O envelope físico inicial é global e
   não calibrado: 320 km/h na reta, 90 km/h na curva mais fechada, 5 m/s² de
   aceleração e 12 m/s² de frenagem. São hipóteses de ordem de grandeza da F1
   moderna, não medições. Qualquer promoção ao motor deve versionar esses
   valores e declará-los como `assumed`, no mesmo espírito do ADR 0007 e da
   decisão 8 do ADR 0008.

3. **Geometria como entrada da física.** A curvatura é derivada offline dos
   mesmos pontos `(x, y, distância)` dos ADRs 0003 e 0005, sem fonte nova. A
   qualidade do perfil depende da densidade da polilinha; as pistas de 2025 têm
   240 pontos por volta.

4. **Promoção explícita e faseada.** Enquanto esta proposta estiver em aberto, o
   motor físico vive isolado: ele alimenta apenas a exibição de velocidade no
   Arcade, e `POST /catalog/grid/run` continua decidindo a corrida pelo motor
   calibrado do ADR 0008. A substituição da fonte do tempo de volta só ocorre
   quando esta decisão for aceita.

5. **Reprodutibilidade preservada.** Se e quando o motor físico substituir o
   cálculo do tempo, a aleatoriedade continua injetável e semeada na borda, como
   no ADR 0002: a integração do movimento é determinística dada a geometria e o
   envelope, e qualquer variação por piloto entra por parâmetro versionado, não
   por sorteio global.

6. **Caráter por carro, em fase posterior.** O envelope é global nesta decisão.
   Ligar velocidade de reta, aceleração e frenagem aos atributos do piloto, para
   produzir carros de reta e carros de curva, é trabalho subsequente dentro
   deste ADR, não um novo recorte.

## Consequências

- A corrida passa a ter velocidade observável por quadro e a geometria deixa de
  ser cosmética: a saída de curva e a aceleração na reta afetam a posição e,
  depois da promoção, o resultado.
- **Perda da âncora calibrada.** Ao gerar o tempo de volta a partir da física, o
  motor abandona a calibração histórica de 2022–2024 que o ADR 0008 preservava.
  Os tempos passam a valer o que o envelope assumido disser. Até que esses
  parâmetros sejam recalibrados contra os tempos reais, os resultados são
  cenário hipotético, não previsão nem reprodução do histórico.
- **Backtests afetados.** O contrato escalar de `compute_lap_time` e a
  reprodução byte a byte dos resultados calibrados deixam de valer no caminho
  físico. Os backtests que comparam o motor com o histórico precisam ser
  repensados ou restritos ao motor calibrado, que permanece disponível.
- **Risco de leitura errada.** Velocidades plausíveis em km/h podem ser tomadas
  por medidas. Toda tela que as exiba deve indicar a origem assumida do
  envelope, como o ADR 0007 e o 0008 já exigem para seus parâmetros.
- **Física simplificada.** O modelo é unidimensional ao longo da linha de
  centro, sem traçado, downforce, transferência de carga, vácuo ou DRS. A
  curvatura é uma aproximação do ângulo entre segmentos da polilinha. É
  deliberadamente grosseiro e serve ao escopo educacional, não à fidelidade.
- **Decisão sobre o motor calibrado em aberto.** Esta proposta não apaga o motor
  do ADR 0008; ela cria um segundo motor e propõe trocar a fonte do tempo. O
  grupo deve decidir, ao aceitar, se o motor calibrado permanece como linha de
  base selecionável ou é aposentado.
- Trabalhos posteriores, dentro deste ADR: caráter físico por carro ligado aos
  atributos; disputas resolvidas com a velocidade sub-volta, para que a saída de
  curva vire ultrapassagem; eventual recalibração do envelope contra tempos
  históricos; integração com pneus, combustível e clima, que hoje modulam o
  tempo escalar e precisariam ser reexpressos como efeitos sobre a velocidade.
- Validação pendente de promoção: enquanto a proposta não é aceita, o motor
  físico é exercitado apenas pela exibição no Arcade. A promoção deve vir
  acompanhada de testes do tempo emergente, do giro contínuo estável e dos
  limites de velocidade, e de uma revisão de quais verificações do motor
  calibrado continuam aplicáveis.
