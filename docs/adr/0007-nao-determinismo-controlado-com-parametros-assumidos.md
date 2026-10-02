# 0007 - Não determinismo controlado com parâmetros assumidos

- Status: proposta
- Data: 2026-09-25
- Responsável pela autorização: usuário, ao aprovar as decisões D1 a D6 do PRD
  `docs/prds/nao-determinismo-pneus-assumidos.md`
- Atualiza: o endpoint do ADR 0006 (campos opcionais novos) e o recorte de
  "motor determinístico com ritmo constante" dos ADRs 0002 e 0006
- Relaciona-se com: ADR 0002 (aleatoriedade injetável e reprodutível por
  semente) e ADR 0004 (backend FastAPI)

## Contexto

O professor da disciplina pediu que a simulação passe a ter um cenário mais não
determinístico. Hoje o núcleo (`domain/race_simulation.py`) acumula, a cada
volta, um tempo constante por piloto: a mesma entrada produz sempre a mesma
corrida, e pneus, pit stops e variação por volta não existem.

A modelagem de pneus (issue #63) foi revisada em 2026-09-25 para decidir se
poderia alimentar o núcleo. Concluiu-se que **não há coeficiente de pneu
calibrado para exportar**:

- idade do pneu e queima de combustível crescem juntas, e a regressão por stint
  não as separa; uma inclinação positiva não é, portanto, desgaste puro;
- no benchmark fora do evento, os intervalos de OLS e do estimador robusto,
  comparados a uma constante, cruzam zero (10 de 17 eventos melhores);
- a idade de âncora exigida pelo contrato não é compatível com a janela de
  idade de `PaceContext`, e somar o efeito de pneu à referência por contexto
  o contaria duas vezes;
- a convenção pré/pós-volta do `TyreLife` do FastF1 não foi confirmada;
- não há estudo para pneus de chuva, pneus usados nem para o efeito de pit stop.

O `AGENTS.md` exige que a aleatoriedade seja injetável e que as simulações sejam
reproduzíveis por semente, e proíbe apresentar como medido o que não foi.

## Alternativas consideradas

- Esperar a calibração empírica de pneus antes de introduzir qualquer
  variância: não há garantia de que a identificação de desgaste contra
  combustível seja alcançada em prazo útil, e o pedido do professor ficaria
  sem resposta.
- Usar as estimativas exploratórias como coeficientes calibrados: rejeitada. Os
  dados não as sustentam (ver contexto), e o simulador passaria a apresentar
  como medição o que é hipótese.
- Sortear dentro do motor, com o módulo `random` global ou com semente
  escolhida no domínio: rejeitada. Quebra a reprodutibilidade, dificulta os
  testes e viola a fronteira de dependências externas injetáveis.
- Derivar o ruído por volta do MAD dos perfis de pilotos: rejeitada. O MAD mede
  dispersão observada, que já embute carro, pneu e clima, e os documentos da
  modelagem de pilotos proíbem convertê-lo em ruído de simulação.
- Introduzir variância com **parâmetros assumidos e rotulados como tal**, com
  fonte de aleatoriedade injetável e semente escolhida na borda: escolhida.

## Decisão

O núcleo passa a aceitar, de forma opcional e desligada por padrão, duas fontes
de variação: um desgaste linear de pneu e um ruído aleatório por volta.

1. **Parâmetros assumidos e rotulados.** Todo parâmetro carrega `source_kind`
   (`assumed` ou `estimated`), `parameter_version` e `rationale`. Os valores
   iniciais são hipóteses inspiradas apenas na ordem de grandeza de uma análise
   exploratória: pneus SOFT, MEDIUM e HARD com 30, 20 e 6 ms de acréscimo por
   volta de idade, com suporte de 0 a 80 voltas; ruído normal de 0,2 % do tempo
   de referência, truncado em 3 desvios. Nenhum deles foi calibrado.
2. **Aleatoriedade injetável.** `RandomSource` é um protocolo do domínio;
   `SeededRandomSource` é a implementação semeada, sem estado global. Os
   sorteios seguem uma ordem canônica (voltas crescentes e, em cada volta,
   `driver_id` crescente), de modo que o resultado não dependa da ordem de
   entrada dos competidores. Fluxos independentes derivam de `SHA-256` sobre
   `(semente, chave)`, e nunca de `hash()`, que é salgado por processo.
3. **Semente escolhida na borda.** O domínio nunca sorteia a semente. Na série
   de corridas, cada corrida usa o fluxo derivado do seu `circuit_id`, portanto
   reordenar ou remover pistas não altera as demais. Quando o cliente liga a
   variância e não envia semente, o backend a sorteia (53 bits, para sobreviver
   a clientes JSON que tratam números como `double`) e a devolve na resposta.
4. **Modo padrão inalterado.** Sem os parâmetros novos, a saída de
   `simulate_race` e de `simulate_series` é idêntica, byte a byte, à anterior.
5. **Transparência.** Toda resposta com modelo ativo traz `assumptions`, com o
   `source_kind` de cada parâmetro usado. Um componente que a corrida não
   modela aparece como `null` no `breakdown`, e nunca como `0`: ausência não é
   preenchida com zero.
6. **Sem pit stop nesta fase.** Cada carro corre com um único composto, e a
   idade do pneu cresce até o fim. Uma corrida mais longa que o suporte do pneu
   é rejeitada, sem extrapolação.
7. **Aritmética em `float`.** A divergência com o `Decimal` dos perfis de
   pilotos é aceita por ora e será resolvida quando os perfis entrarem no
   motor.

## Consequências

- O simulador produz variância reproduzível: a mesma semente, os mesmos dados e
  os mesmos parâmetros dão o mesmo resultado, e a semente sorteada é devolvida
  para repetir uma corrida.
- Quando houver parâmetros calibrados, eles substituem os assumidos sem mudar o
  contrato: `source_kind: "estimated"` já é aceito, e `assumptions` os
  distingue dos hipotéticos.
- **Realismo limitado.** Sem pit stop, um pneu SOFT acumula cerca de 2,1 s de
  degradação em 70 voltas, o que não representa uma estratégia real. Corridas
  acima de 81 voltas com pneu são rejeitadas (o esquema HTTP aceita até 200).
  Os números só devem ser apresentados como cenário hipotético.
- **Risco de leitura errada.** Valores plausíveis podem ser tomados por
  medidos, caso uma interface omita `assumptions`. Qualquer tela que exiba o
  resultado deve indicar a origem hipotética dos parâmetros.
- **Reprodutibilidade entre versões.** `random.gauss` é estável na prática, mas
  sua sequência não é garantida pela documentação do Python entre versões.
  Se a reprodução entre máquinas ou versões vier a ser exigida, deve-se
  substituí-lo por um gerador próprio (por exemplo, Box-Muller sobre
  `random()`).
- Cada fluxo derivado por `spawn` mantém o seu próprio registro de sorteios;
  uma auditoria completa exigiria reuni-los.
- Não mudam: o ETL, os perfis de pilotos e a modelagem de pneus (que segue
  exploratória). `backend/app/loaders/loader.py` continua truncando a
  degradação em zero e convertendo pit loss ausente em `0.0`; isso contraria o
  `AGENTS.md` e permanece fora do caminho novo, como pendência.
- Trabalhos posteriores, fora deste ADR: pit stops e estratégia; compostos
  INTER e WET e clima; integração com os perfis por referência ancorada;
  calibração empírica separando idade e combustível; unificação de precisão;
  ligar o frontend Arcade às opções de semente e variância.
- Validação: testes unitários e de integração cobrem o contrato de pneus, a
  fonte de aleatoriedade, o motor e o endpoint, inclusive a igualdade byte a
  byte do modo padrão e a reprodução por semente.
