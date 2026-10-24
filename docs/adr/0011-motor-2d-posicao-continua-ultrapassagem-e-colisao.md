# 0011 - Motor 2D com posição contínua, ultrapassagem e colisão espaciais

- Status: aceita
- Data: 2026-10-01
- Responsável pela autorização: usuário, nesta sessão, ao escolher o modelo 2D
  pleno (posição x,y evoluída por passos de tempo, ultrapassagem e colisão
  emergentes) em vez do 2D aproximado sobre o motor por volta
- Atualiza: a resolução temporal "o motor avança por volta" dos ADRs 0002 e
  0008; o recorte do ADR 0003 (geometria mockada fora da física de corrida); e
  o uso do ADR 0010, em que a física de velocidade é colapsada num tempo de
  volta escalar
- Relaciona-se com: ADR 0002 (hexagonal, núcleo da corrida), ADR 0003
  (geometria), ADR 0008 (heurísticas sobre o motor calibrado), ADR 0009
  (combustível) e ADR 0010 (motor físico de velocidade por trecho)

## Contexto

Hoje a corrida é unidimensional e temporal. A posição de um carro é um único
escalar, `total_time_ms`, e a pista é tratada como uma linha do tempo: a ordem
é a ordenação por esse escalar. Não existe posição lateral, largura de pista nem
coordenada 2D em nenhuma camada da lógica de corrida. As coordenadas x,y vivem
apenas na geometria de desenho (linha de centro, sem largura) e na curvatura
usada pelo motor de velocidade.

A ultrapassagem e a colisão também não são eventos espaciais. O motor avança uma
volta por passo e, em `domain/disputes.py`, sorteia o *desfecho* de uma briga que
durou a volta inteira: a chance de passar é `P/(P+R)`, e a exclusão física entre
carros é imposta por um espaçamento mínimo medido em milissegundos, não em
metros. Não há instante de roda a roda; não há dois carros lado a lado.

O usuário quer o oposto: carros com posição x,y que evolui ao longo do tempo, de
modo que a ultrapassagem *aconteça* porque um carro tinha velocidade e espaço, e
a colisão *aconteça* porque dois corpos se sobrepuseram no mesmo instante. Isso
exige o motor simular em passos de tempo curtos (sub-volta) em vez de uma volta
por passo, e manter a trajetória de cada carro, não só o seu tempo acumulado.

Essa é a maior mudança de fronteira já proposta no projeto. O `AGENTS.md` declara
que "o motor avança por volta", que "as regras da corrida independem de Arcade,
FastAPI e formatos de dados" e que o laço de renderização não pode ser acoplado
ao relógio da simulação sem um novo ADR aceito. Mudar a resolução do motor de
por-volta para contínua, e trazer largura e posição lateral para dentro da
física, atravessa essas três fronteiras de uma vez. Daí este registro, e a
decisão explícita de não fazê-lo silenciosamente.

## Alternativas consideradas

- **2D aproximado sobre o motor por volta:** manter o avanço por volta e dar à
  disputa uma dimensão lateral (por dentro/por fora, largura modulando a chance
  de passar e de bater). Barato, reversível, reaproveita todo o motor atual.
  Rejeitada pelo usuário: não produz carros genuinamente lado a lado nem colisão
  por sobreposição física; a ultrapassagem continua um sorteio de desfecho.
- **Motor 2D pleno com posição contínua** (esta decisão): o motor passa a avançar
  em passos de tempo pequenos; cada carro tem posição longitudinal e lateral e
  velocidade; ultrapassagem e colisão emergem da proximidade espacial. Caro e de
  fronteira, mas é o único que entrega o comportamento pedido. Escolhida.

## Decisão

Construir um motor 2D de resolução sub-volta, **isolado e opt-in**, que não
substitui o motor por volta enquanto não estiver validado. A adoção é faseada e
cada fase é uma fatia vertical verificável, conforme o `AGENTS.md`.

1. **Representação espacial.** O estado do carro passa a ter posição ao longo da
   pista (distância longitudinal) e posição lateral (deslocamento em relação à
   linha de centro, limitado pela largura), além de velocidade. A geometria
   ganha largura de pista; a linha de centro existente continua sendo o eixo
   longitudinal. Unidades em metros e segundos, explícitas.

2. **Avanço por passo de tempo.** O motor integra o movimento em passos fixos e
   pequenos (ordem de décimos de segundo), não uma volta por iteração. O passo é
   um parâmetro versionado e assumido; a reprodutibilidade por semente é
   preservada fixando passo, ordem de atualização e consumo da fonte aleatória,
   como nos ADRs 0002 e 0010.

3. **Ultrapassagem emergente.** Deixa de haver sorteio de desfecho por volta. Um
   carro ultrapassa quando, passo a passo, tem velocidade e espaço lateral para
   se colocar à frente. `domain/disputes.py` e seus parâmetros
   (`overtake_advantage_scale_ms`, `pass_probability`, `pressure_pass_probability`)
   saem do caminho 2D; a dificuldade por circuito passa a emergir da largura e do
   traçado.

4. **Colisão geométrica.** O contato deixa de ser um sorteio por disputa
   (`collision_probability_per_dispute`). Dois carros colidem quando seus corpos,
   com largura e comprimento assumidos, se sobrepõem no mesmo passo. A divisão de
   culpa e o abandono resultante continuam heurísticos e versionados.

5. **Isolamento e opt-in.** O motor 2D nasce como módulo separado, selecionável,
   sem alterar o motor por volta. `POST /catalog/grid/run` continua no motor
   atual até o 2D ser aceito como padrão. Combustível (ADR 0009), controle de
   prova (ADR 0008) e a reprodução volta a volta do frontend permanecem ligados
   ao motor por volta enquanto o 2D não os reexpressa.

6. **Parâmetros assumidos e rotulados.** Largura de pista, largura e comprimento
   de carro, passo de tempo e limites de agarramento lateral são hipóteses não
   calibradas, declaradas com `source_kind`/`parameter_version`/`rationale`, no
   espírito dos ADRs 0007, 0008 e 0010. Nada aqui é medição.

## Consequências

- A corrida passa a ter carros lado a lado, ultrapassagem por posição e colisão
  por sobreposição, reproduzíveis por semente.
- **Custo e risco altos.** É a maior reescrita do núcleo até hoje. O resultado
  2D não é comparável ao histórico nem aos backtests calibrados; é cenário
  hipotético, como o motor de velocidade do ADR 0010 já é quando há geometria.
- **Reexpressão necessária.** Combustível, pneu, clima e controle de prova hoje
  modulam o tempo por volta. Para valerem no motor 2D precisam ser reexpressos
  como efeitos sobre o movimento contínuo (consumo por distância, aderência por
  água, neutralização por velocidade imposta). Até lá, o 2D roda sem eles ou com
  aproximações declaradas.
- **Resolução e desempenho.** Centenas de passos por volta para dezenas de carros
  é muito mais custoso que uma iteração por volta; o passo de tempo equilibra
  custo e fidelidade e é um parâmetro assumido.
- **Fronteiras.** Esta decisão muda a resolução do motor (ADRs 0002/0008), traz
  largura e lateral para a física (ADR 0003) e exige que o motor de velocidade
  do ADR 0010 mantenha posição no tempo em vez de colapsar num escalar. O motor
  por volta permanece como caminho válido e selecionável; o grupo decide, ao
  aceitar, se e quando o 2D vira padrão.
- **Plano em fatias** (cada uma verificável e isolada):
  1. geometria com largura e um modelo de estado espacial do carro, sem mexer no
     motor por volta;
  2. integrador sub-volta de um único carro na linha de centro, com o mesmo
     tempo de volta emergindo (ponte de validação com o ADR 0010);
  3. vários carros no mesmo eixo longitudinal, com exclusão espacial e posição
     lateral, sem disputa ainda;
  4. ultrapassagem emergente (sem sorteio de desfecho);
  5. colisão por sobreposição e divisão de culpa heurística;
  6. reexpressão de combustível, clima e controle de prova no motor 2D;
  7. decisão de promover o 2D a padrão de `grid/run`.
- Validação: cada fatia entra com testes próprios; a promoção exige revisão de
  quais verificações do motor por volta continuam aplicáveis e de como a
  reprodução do frontend passa a consumir trajetórias em vez de retratos por
  volta.

## Estado de implementacao (2026-10-01)

As sete fatias foram implementadas. O motor 2D vive em
`domain/track_space.py` (mecanica espacial) e `domain/race_simulation_2d.py`
(orquestracao e conversao para o `history` por volta). E selecionavel por
`engine="2d"` em `run_detailed_grid_simulation`, exposto ate a rota
`POST /catalog/grid/run` pelo campo `setup.engine`; o padrao continua o motor
por volta.

Feito:

- fatias 1-5: geometria em faixa com largura, integrador sub-volta validado
  contra o ADR 0010, exclusao espacial, ultrapassagem emergente por troca de
  faixa e colisao por sobreposicao com culpa ponderada pela agressividade;
- fatia 6: pneu (degradacao por idade), combustivel (massa que custa tempo e
  diminui ao queimar), clima (agua penalizando a volta) e abandono mecanico,
  todos reexpressos como reducao fracionaria da velocidade (`speed_scale`) ou
  sorteio por volta; o resultado sai no mesmo formato do motor por volta e e
  lido pelo `RacePlayback` do frontend;
- fatia 7: selecao do motor na cadeia rota -> servico -> caso de uso.

Limitacoes assumidas e declaradas em `assumptions` (`kind: engine_2d`), ainda
nao modeladas no 2D:

- reabastecimento e pit stop (o combustivel so diminui ao queimar; nao ha
  parada nem troca de pneus no 2D);
- SC, VSC, bandeiras e relargada (so o abandono mecanico e o contato existem);
- car-following com frenagem antecipada: na entrada de curva a folga entre
  carros em fila pode encolher por um ou dois passos antes de estabilizar.

Validacao: `tests/test_track_space.py` cobre as fatias 1-5; as fatias 6-7 foram
exercitadas por verificacoes manuais (degradacao de pneu, efeito de combustivel
e clima, abandono reproduzivel, e a cadeia completa com leitura pelo frontend),
ainda sem testes permanentes para `race_simulation_2d.py`.
