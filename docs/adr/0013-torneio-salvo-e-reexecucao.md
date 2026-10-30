# 0013 - Torneio salvo, reabertura e reexecução

- Status: aceita
- Data: 2026-10-30
- Responsável pela autorização: usuário, ao aprovar o PRD
  [controles do usuário](../prds/controles-do-usuario-simulacao.md) (#109)
- Atualiza: [ADR 0006](0006-sequencia-de-corridas-livres.md), registrando o
  mecanismo que substituiu a rota de série removida

## Contexto

O ADR 0006 previa uma rota de backend que executava a sequência inteira. Essa
rota foi removida: hoje o frontend roda cada etapa em `POST /catalog/grid/run`
sobre o grid atual (`current-grid.json`) e pede a pontuação a
`POST /championship/standings`. O torneio só existia na memória do frontend;
cada corrida era salva isoladamente em `saved-races/`, mas nada ligava o plano,
o grid usado, as seeds e os resultados.

O usuário quer salvar um torneio para revê-lo ou rodá-lo de novo sem
reconfigurar nada. A #105 já tornou cada etapa reproduzível: o fluxo aleatório
vem de `(tournament_seed, stage_index)` e o grid é um arquivo explícito.

## Alternativas consideradas

- Rota de backend que executa o torneio salvo inteiro: devolve uma resposta
  longa sem progresso por etapa e duplica o laço que o frontend já tem.
- Salvar só o cenário (inputs): reabrir exigiria simular tudo de novo.
- Salvar só os resultados: não permite reexecutar nem conferir a reprodução.
- Salvar cenário e resultados, com o grid congelado no próprio registro, e
  reexecutar pelo mesmo `POST /catalog/grid/run` de uma simulação nova.

## Decisão

Adotar a última alternativa:

- `POST /tournaments` recebe as etapas já simuladas (plano da tela, `setup`
  enviado e corrida devolvida) e congela o `current-grid.json` daquele momento.
  O núcleo (`application/saved_tournament.py`) recusa o pedido (409) se as
  corridas não foram simuladas com esse grid (seed ou ordem de largada
  diferentes) ou se algum `setup` não reproduziria a corrida guardada.
- O registro é JSON versionado (`schema_version: 1`) em
  `/data/simulation/saved-tournaments/<id>.json`, escrito atomicamente e fora
  do Git, como as corridas salvas.
- `GET /tournaments` lista resumos; `GET /tournaments/{id}` devolve o registro
  completo. **Reabrir** mostra as corridas guardadas sem simular.
- **Reexecutar** é `POST /tournaments/{id}/restore-grid` seguido do reenvio do
  `setup` de cada etapa a `POST /catalog/grid/run`, na ordem. O backend não tem
  rota de reexecução própria.
- `rules` e `plan` são da apresentação (rótulos da tela): o backend os guarda
  sem interpretar; só o frontend os reconstrói.

## Consequências

- Reabrir não depende do motor nem dos parâmetros atuais: o resultado é o que
  foi salvo, inclusive suas `assumptions`.
- Reexecutar reproduz o torneio com a mesma versão de código, Python,
  parâmetros e dados. Mudar um parâmetro (por exemplo, o fator de largada da
  #108) muda a reexecução; a comparação com o resultado salvo mostra o efeito.
- Restaurar o grid sobrescreve o grid atual do backend, como montar um grid
  novo já fazia.
- Salvar precisa acontecer antes de editar ou remontar o grid; depois disso o
  backend recusa com uma mensagem explicando o motivo. Um torneio reaberto
  também só pode ser salvo de novo se o grid atual for o dele.
- Torneios rodados antes da #105 (sem `tournament_seed`) podem ser salvos e
  reexecutados, mas todas as etapas usam o mesmo fluxo aleatório do grid.
