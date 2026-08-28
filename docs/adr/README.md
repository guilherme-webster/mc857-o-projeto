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
| [0001](0001-frontend-desktop-com-arcade.md) | aceita | Frontend desktop em Python com Arcade. |

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

O ADR da escolha entre MVC e camadas com portas e adaptadores continua
obrigatorio e deve incluir como as pastas e dependencias refletirao a decisao.
Enquanto ele nao for aceito, nenhum outro ADR autoriza implicitamente uma
estrutura definitiva para `src/`.
