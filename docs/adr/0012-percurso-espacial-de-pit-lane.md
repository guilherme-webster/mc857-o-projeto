# 0012 - Percurso espacial da pit lane no motor 2D

- Status: aceita
- Data: 2026-10-26
- Autorização: usuário, ao solicitar a implementação da issue #101
- Atualiza: aproximação temporal dos boxes no motor 2D do ADR 0011
- Relaciona-se: ADRs 0003 (mock da geometria), 0008 (estratégia heurística)
  e 0009 (combustível e tempo de boxes do motor por volta, ainda proposta)

## Contexto

O 2D já decide paradas e troca pneus, mas dilui `pit_loss_ms` numa redução
de velocidade na volta inteira. O carro não entra no caminho de pit lane
existente nem permanece no ponto de serviço. O usuário pediu o percurso
completo, com limite de velocidade, parada e retorno à pista, evitando a
duplicação da perda temporal.

## Decisão

Usar o caminho reduzido já existente como geometria **hipotética** de movimento.
A escala uniforme da pista converte seu comprimento em metros estimados.
Entrada e saída são projetadas em segmentos da pista, com pequenas conexões
à polilinha. A extensão mockada não prediz a perda histórica de boxes: o
resultado 2D permanece um cenário não calibrado, conforme o ADR 0011.

- O integrador separa distância no caminho dos boxes e progresso de corrida.
  O progresso interpola monotonamente entre as projeções de entrada e saída,
  desenrolando a volta quando o caminho cruza a linha. Durante o serviço,
  nenhum dos dois avança.
- O pedido reserva a próxima entrada. A mudança de pneus ocorre ao concluir
  o serviço, não ao pedir a parada nem ao cruzar a linha de volta.
- Limite padrão: 80 km/h; serviço de pneus: 2,5 s; folga de reinserção: 2 m
  além dos corpos. Todos são parâmetros injetáveis, assumidos e versionados
  em `spatial-pit-lane-v1`.
- Carros fazem fila no caminho dos boxes e não participam das disputas da
  pista principal. A saída aguarda folga também em relação a retardatários.
- O relógio do integrador contabiliza deslocamento, serviço e espera. Não se
  soma `pit_loss_ms` nem se aplica o desconto SC/VSC a esse relógio: sob
  neutralização, o menor ritmo da pista já muda a perda relativa. A perda
  histórica e seus fatores continuam apenas como estimativa na estratégia.
- A resposta HTTP acrescenta o caminho aberto em `pit_lane_2d`, eventos em
  `pit_stop_events` e um quinto campo opcional nas trajetórias 2D: distância
  nos boxes, ou `null` na pista. O frontend interpola esses dados sem importar
  o domínio. O formato antigo de quatro campos permanece legível.

## Consequências e limites

O carro percorre a pit lane e fica parado no ponto de serviço, enquanto desenho,
indicador de boxes e classificação usam a mesma trajetória. O motor por volta
preserva a perda calibrada e seu comportamento existente.

O serviço é um único ponto representativo para todos os carros, com fila,
não garagens individuais. O limite é imposto ao entrar, sem uma zona de
frenagem detalhada, e a saída é uma aproximação por folga, sem disputa entre
um carro saindo e outro na pista. Este incremento troca só pneus: não porta
o reabastecimento do motor por volta para o 2D. Não há fonte nova, telemetria
bruta ou alteração das fixtures.

Validação: `tests/test_pit_lane.py` cobre percurso, serviço, limite, fila,
reinserção, contagem de voltas, reprodutibilidade, ausência de cobrança
duplicada e leitura do resultado pelo frontend sem janela.
