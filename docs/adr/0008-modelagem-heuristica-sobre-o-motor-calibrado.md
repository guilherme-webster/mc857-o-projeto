# 0008 - Modelagem heurística sobre o motor calibrado

- Status: aceita
- Data: 2026-10-03
- Responsáveis: grupo, pela adoção da abordagem heurística depois da orientação
  do professor; usuário (issue #67), pelas decisões D1 a D7 do PRD
  `docs/prds/modelagem-pilotos-heuristica.md`
- Atualiza: o recorte de "motor de ritmo constante" dos ADRs 0002 e 0006; o
  contexto do ADR 0007 (ver Consequências)
- Relaciona-se com: ADR 0002 (aleatoriedade injetável e reproduzível), ADR 0007
  (não determinismo controlado) e o trabalho da issue #40
  (`40-modelagem-corrida-calibrada`)

## Contexto

O professor indicou que a modelagem de pilotos, pneus e afins **não precisa ser
orientada a dados**: heurísticas são aceitáveis. O grupo preferiu esse caminho a
continuar buscando dados que sustentem cada efeito.

Três trabalhos existiam em paralelo e não se conversavam:

- a `develop`, com atributos de piloto por arquétipo (#90), grid montado a partir
  do catálogo histórico e o `POST /catalog/grid/run`, ainda no motor de ritmo
  constante, com volta fixa de 90 s, sem pista, paradas, disputas ou abandonos;
- a branch do colega da #40, com um motor detalhado calibrado em 2022–2023
  (combustível, pneu por composto, tráfego, paradas, disputas, abandono por
  equipe), que não chegou a ser integrada e conflitava com a `develop` em sete
  arquivos;
- o planejamento do colega (slides "Disputas") para a disputa com o perfil dos
  dois pilotos, ainda não implementado.

Nenhum deles tinha safety car, VSC ou bandeiras, e a documentação dos perfis
(`contrato-perfil-simulacao.md`, `perfilamento-pilotos.md`) define perfil como
desempenho observado e desaconselha notas atribuídas.

## Alternativas consideradas

- **Continuar orientado a dados:** calibrar perfis, ultrapassagem e incidentes
  com o histórico. Rejeitada pelo grupo: custo alto, e os estudos da #63 já
  mostraram efeitos confundidos e poder preditivo fraco.
- **Mecanismo próprio sobre o motor simples** (v1 do plano): seis notas de 0 a
  100 e uma ultrapassagem por janela. Descartada ao encontrar o motor do colega,
  que já resolve bloqueio, exclusão física e contato.
- **Heurísticas como moduladores do motor calibrado:** manter a física
  calibrada do colega e acrescentar perfis, disputa, controle de prova e
  paradas heurísticos, rotulados e neutros por padrão. Escolhida.

## Decisão

1. **Motor único da corrida.** `POST /catalog/grid/run` passa a usar
   `simulate_detailed_race`. O motor simples continua disponível
   (`engine="simple"`) como linha de base.
2. **Física calibrada preservada.** Combustível, pneu por composto, tráfego,
   perda de boxes, dificuldade de ultrapassagem por circuito e confiabilidade
   por equipe continuam vindo de `data/parameters/model-v1.json`.
3. **Perfis heurísticos.** Os atributos por arquétipo ganham `aggression` e
   `composure`. Perfis fictícios nomeados ficam em
   `configs/drivers/perfis-ficticios.json`, declarados como caracterizações
   fictícias e não como afirmações sobre pessoas reais. A entrada da simulação
   passa a ser o perfil heurístico; os estudos orientados a dados permanecem no
   repositório como estudos.
4. **Disputa dos slides.** `p(passar) = P / (P + R)`, com pressão do atacante
   (vantagem, proximidade, agressividade, consistência) e resistência do
   defensor (dificuldade do circuito, firmeza), ancorada para coincidir com a
   fórmula calibrada em perfis neutros. No contato, sorteia-se qual dos dois
   abandona. Retardatários cedem (bandeira azul). A fórmula antiga segue
   disponível (`dispute_model="legacy"`).
5. **Controle de prova heurístico.** SC, VSC, amarela, vermelha e relargada,
   acionados por batidas, acidentes individuais e falhas mecânicas, com
   probabilidades ajustadas para uma frequência plausível de neutralizações.
6. **Paradas heurísticas.** Decisão econômica de parada, parada oportunista sob
   SC/VSC, regra de dois compostos e variação por piloto.
7. **Escala de tempo por pista.** A volta de referência vem de uma tabela por
   circuito (mediana histórica das voltas mais rápidas, 2022–2024), com reserva
   em ms/km e em volta nominal.
8. **Rótulos, versões e neutralidade.** Todo parâmetro novo é heurístico,
   versionado e declarado em `assumptions`. Sem os recursos novos, o motor
   detalhado reproduz exatamente o resultado do motor calibrado.

Os valores atuais e onde mudá-los estão em `docs/modelagem-heuristica.md`.

## Consequências

- A corrida passa a ter ultrapassagens, bloqueios, paradas, abandonos, SC, VSC e
  bandeiras, reproduzíveis por semente.
- **Os resultados não são previsões nem medições.** Qualquer tela que os exiba
  deve deixar clara a origem heurística (as respostas trazem `assumptions`).
- **Ajuste fino necessário.** Os efeitos interagem: as faixas de gestão de pneus
  dos arquétipos precisaram ser amortecidas no motor detalhado para não anular a
  vantagem de ritmo, e a pole ainda vence com frequência alta. Mudanças devem
  incrementar a versão do parâmetro e ser medidas com
  `scripts/race_control_frequency.py`.
- **Vermelha menos frequente que o alvo.** Com o teto de 10% das batidas
  aprovado pelo grupo, ocorre cerca de 1 vermelha a cada 10–11 corridas, contra
  1 a cada 6 na referência de 2024.
- **ADR 0007.** Seu contexto afirma que não havia coeficiente de pneu utilizável
  e que idade e combustível estavam confundidos. A calibração da #40 separou os
  dois efeitos por relógios distintos (volta da corrida e idade do jogo). O 0007
  continua como proposta; antes de aceitá-lo, o grupo deve revisar esse
  contexto ou substituí-lo.
- **Documentos de perfil.** `contrato-perfil-simulacao.md` e
  `perfilamento-pilotos.md` descrevem os estudos orientados a dados; não
  descrevem mais a entrada da simulação.
- **Fora desta decisão:** efeito do clima no tempo de volta e nos incidentes
  (#68/#69), telas do Arcade para disparar e reproduzir a corrida, DRS e vácuo,
  culpa no contato e dano parcial.
