# 0006 - Sequência de corridas livres

- Status: aceita
- Data: 2026-09-24
- Responsável pela autorização: usuário, ao confirmar a sequência de corridas
- Atualiza: recorte de circuito único do ADR 0002 e do plano do MVP

> Atualização em 2026-10-16: a rota `POST /simulation/series/simulate` e os
> ritmos informados pelo usuário foram removidos do código (registrado no PRD
> v3 da [modelagem heurística](../prds/modelagem-pilotos-heuristica.md), sem
> ADR próprio). A sequência de corridas livres segue existindo de outra forma:
> o frontend roda cada etapa em `POST /catalog/grid/run` sobre o grid do
> catálogo, e `POST /championship/standings` calcula a pontuação acumulada que
> este ADR deixava para depois. O ritmo vem do motor do
> [ADR 0008](0008-modelagem-heuristica-sobre-o-motor-calibrado.md). O
> [ADR 0013](0013-torneio-salvo-e-reexecucao.md) registra esse mecanismo e o
> torneio salvo.

## Contexto

A interface já lista 24 geometrias, mas o fluxo existente só seleciona uma.
`POST /simulation/simulate` exige uma corrida histórica previamente carregada
para obter pilotos e número de voltas. O usuário definiu que uma simulação
poderá conter mais de uma pista e não precisará reproduzir uma corrida real.

## Alternativas consideradas

- Fazer uma única corrida trocar de pista durante suas voltas: não corresponde
  ao sentido de uma sequência de corridas e embaralha suas classificações.
- Manter o histórico obrigatório e trocar apenas o circuito: acopla a escolha
  livre a um `race_id` e reutiliza tempos de volta de outra pista sem unidade.
- Configurar uma sequência ordenada de corridas independentes com participantes
  e ritmos informados pelo usuário: preserva a separação entre pistas e permite
  executar o motor atual sem ETL histórico.

## Decisão

A tela inicial monta uma sequência ordenada de pistas. Cada pista tem suas
próprias voltas e clima configurado. Uma nova rota recebe a sequência e os
participantes com ritmo em milissegundos por quilômetro. O backend valida os
IDs de pista contra o catálogo disponível, obtém seus comprimentos e executa
o motor determinístico para cada etapa, sem exigir `POST /simulation/load`.
O endpoint histórico existente continua disponível para compatibilidade.

## Consequências

- O histórico pode calibrar parâmetros no futuro, mas não é pré-requisito de
  uma corrida livre. O usuário precisa fornecer participantes e ritmos à nova
  API; nenhum piloto ou tempo real é inventado implicitamente.
- Cada etapa tem classificação independente. Pontuação acumulada, efeito do
  clima, calendário, editor de participantes na interface e tela de reprodução
  da sequência são trabalhos posteriores; a configuração da interface ainda
  requer um consumidor da ação de confirmação para iniciar a API.
- O núcleo continua independente de Arcade, FastAPI e dados históricos.
