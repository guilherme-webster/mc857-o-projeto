# 0016 - Elenco do grid e geração de atributos por piloto

- Status: aceita
- Data: 2026-11-07
- Responsáveis: usuário (decisões de produto e de regra de geração); agente
  de implementação (backend e frontend)
- Atualiza: a regra de reprodutibilidade por semente descrita na
  [ADR 0007](0007-nao-determinismo-controlado-com-parametros-assumidos.md) e
  o contrato de `PATCH /catalog/grid`, antes limitado a atributos e ordem

## Contexto

O grid era montado com um número fixo de pilotos (a tela pedia 20) e só podia
ser editado em atributos e na ordem. Para adicionar ou remover pilotos sem
perder as edições dos demais, o backend precisava de uma operação de elenco.

Havia dois problemas na geração de atributos:

- o sorteio do arquétipo usava um único fluxo aleatório que avançava piloto a
  piloto, na ordem da lista. O arquétipo define as faixas dos demais atributos.
  Assim, o valor de um piloto dependia de quem mais estava no grid;
- o limite de 40 pilotos estava no schema de `BuildGridRequest` e em
  `EditGridAttributesRequest`, mas não em `race` mode. Uma largada historica com
  mais de 40 inscritos montaria um grid que o `PATCH` não conseguia mais editar.

## Alternativas consideradas

- **Refazer o grid com `POST /catalog/grid` (modo manual) a cada mudança de
  elenco.** Funciona com a API atual, mas regenera os atributos e perde as
  edições dos pilotos que continuam no grid.
- **Operação de elenco atômica no `PATCH`** (`add`, `remove`, com `overrides`
  e `order` na mesma gravação). Preserva os pilotos que continuam e falha antes
  de gravar se qualquer parte for inválida.
- **Manter a geração sequencial** e aceitar que o arquétipo de um piloto depende
  do elenco. Preserva os valores de sementes antigas, mas um piloto adicionado
  não tem valores estáveis: o mesmo piloto pode receber atributos diferentes
  conforme quem está no grid.
- **Geração por piloto**, com fluxos de arquétipo e de campos derivados de
  `(semente, driver_id)`. Os valores passam a depender só da semente e do ID.

## Decisão

- `PATCH /catalog/grid` aceita `add` (pares `piloto@equipe`) e `remove`
  (`driver_id`), aplicados nesta ordem: remover, acrescentar ao fim,
  reordenar, editar atributos. Tudo é validado antes da gravação, que é única.
- O elenco resultante tem de 1 a 40 pilotos. `add` e `remove` com o mesmo piloto
  são permitidos e representam troca de equipe. Se `order` vier junto, deve ser
  a permutação exata do elenco resultante.
- Pilotos acrescentados entram ao fim do grid. A ordem final é enviada pelo
  frontend sempre que o elenco muda.
- Pilotos que continuam mantêm atributos e origens. Só os novos são gerados,
  com a semente do grid.
- A geração usa fluxos derivados por piloto, tanto para o arquétipo quanto para
  os campos. O valor de um piloto depende só da semente e do ID.
- Uma largada historica com mais de 40 pilotos é recusada com 422 em
  `POST /catalog/grid` (modo `race`).
- Escolher o piloto pelo par `piloto@equipe` evita ambiguidade: o histórico tem
  pilotos com mais de uma equipe.

## Consequências

- **Quebra de reprodutibilidade para sementes antigas.** Uma montagem nova com
  a mesma semente gera valores diferentes dos gerados antes desta decisão. O
  teste `test_v1_fields_keep_exact_values_for_the_same_seed` foi atualizado com
  os valores novos, e sua docstring registra a mudança.
- **Grids e torneios já salvos não mudam.** Os atributos ficam gravados no
  `current-grid.json` e no registro do torneio. Reexecutar um torneio salvo usa
  o grid congelado no registro (ADR 0013), não uma nova geração.
- O frontend precisa mostrar pilotos recém-adicionados sem atributos locais
  até o salvamento, porque é o backend que os sorteia.
- O limite de 40 é de produto. Uma largada real com mais pilotos não é aceita
  por esta rota.
- A pontuação do campeonato não muda: continua a mesma para qualquer número de
  pilotos.

## Pontos não verificados

- A tabela de classificação ao vivo desenha uma linha por piloto. Com 40
  carros, não foi verificado se ela cabe na janela ou se precisa de rolagem.
- O motor 2D com 40 carros não foi testado de ponta a ponta. A posição inicial
  do último carro fica 400 m atrás da linha (`GRID_ROW_SPACING_M` = 10 m).
