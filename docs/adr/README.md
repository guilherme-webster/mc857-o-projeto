# Registros de decisoes arquiteturais

Use um ADR para decisoes estruturais, dificeis de reverter ou que afetem varios
componentes. Nomeie os arquivos como `NNNN-titulo-curto.md`, em ordem crescente.
Nao altere silenciosamente um ADR aceito: crie outro que o substitua.

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

O primeiro ADR do projeto deve registrar a escolha entre MVC e camadas com
portas e adaptadores, incluindo como as pastas e dependencias refletirao a
decisao.
