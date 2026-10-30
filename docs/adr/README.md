# Registros de decisoes arquiteturais

ADR significa *Architecture Decision Record*, ou registro de decisao
arquitetural. E um documento curto que guarda o contexto, as alternativas, a
decisao tomada e suas consequencias, para que o grupo nao precise rediscutir ou
adivinhar depois por que uma escolha estrutural foi feita.

Use um ADR para decisoes estruturais, dificeis de reverter ou que afetem varios
componentes. Nomeie os arquivos como `NNNN-titulo-curto.md`, em ordem crescente.
Nao altere silenciosamente um ADR aceito: crie outro que o substitua.

## Decisoes registradas

| ADR | Status | Decisao |
| --- | --- | --- |
| [0001](0001-frontend-desktop-com-arcade.md) | aceita; backend atualizado pelo 0004 | Frontend desktop em Python com Arcade. |
| [0002](0002-arquitetura-hexagonal-e-integracao-de-dados.md) | aceita; backend atualizado pelo 0004 | Arquitetura hexagonal, integracao com Adapter + Factory e dataset Trotman para o MVP. |
| [0003](0003-geometria-mockada-derivada-do-fastf1.md) | aceita; escopo de dados ampliado pelo 0005 | Geometria reduzida derivada offline. |
| [0004](0004-backend-fastapi-e-contratos-python.md) | aceita | FastAPI substitui Django; integracao interna por contratos Python. |
| [0005](0005-historico-completo-e-enriquecimento-fastf1.md) | aceita | Historico Trotman completo e observacoes complementares FastF1 offline. |
| [0006](0006-sequencia-de-corridas-livres.md) | aceita; mecanismo atualizado pelo 0013 | Sequencia de corridas livres em varias pistas, sem evento historico obrigatorio. |
| [0007](0007-nao-determinismo-controlado-com-parametros-assumidos.md) | proposta, nao implementada; contexto a revisar pelo 0008 | Variancia reproduzivel por semente, com pneus e ruido assumidos e rotulados. |
| [0008](0008-modelagem-heuristica-sobre-o-motor-calibrado.md) | aceita | Perfis, disputa, SC/VSC/bandeiras e paradas heuristicos sobre o motor calibrado da #40. |
| [0009](0009-combustivel-por-massa-e-reabastecimento.md) | proposta | Combustivel por massa por carro e reabastecimento como regra do cenario, com paradas estrategicas por piloto. |
| [0010](0010-motor-fisico-de-velocidade-por-trecho.md) | aceita; atualiza o 0008 | Motor fisico de velocidade por trecho: o tempo de volta emerge da velocidade derivada da curvatura. |
| [0011](0011-motor-2d-posicao-continua-ultrapassagem-e-colisao.md) | aceita; atualiza o 0002, 0003 e 0010 | Motor 2D sub-volta: posicao x,y continua; ultrapassagem e colisao emergem da proximidade espacial. |
| [0012](0012-percurso-espacial-de-pit-lane.md) | aceita; atualiza o 0011 | Pit lane espacial no 2D: entrada, fila, serviço e saída; tempo efetivo sem duplicar a perda de boxes. |
| [0013](0013-torneio-salvo-e-reexecucao.md) | aceita; atualiza o 0006 | Torneio salvo com grid congelado e resultados: reabrir sem simular ou reexecutar pelo `POST /catalog/grid/run`. |

## Modelo

```markdown
# NNNN - Titulo da decisao

- Status: proposta | aceita | rejeitada | substituida
- Data: AAAA-MM-DD
- Responsaveis: nomes dos participantes

## Contexto

Qual problema precisa ser resolvido? Quais restricoes e criterios importam?

## Alternativas consideradas

- Alternativa A: beneficios e custos.
- Alternativa B: beneficios e custos.

## Decisao

Qual alternativa foi escolhida e por que ela atende melhor aos criterios?

## Consequencias

- Beneficios esperados.
- Custos, riscos e limitacoes aceitos.
- Acoes de implementacao ou validacao necessarias.
```

O [ADR 0002](0002-arquitetura-hexagonal-e-integracao-de-dados.md) encerra a
escolha entre MVC e camadas com portas e adaptadores. Alteracoes futuras dessas
fronteiras devem ser registradas em um novo ADR que substitua a decisao aceita.
