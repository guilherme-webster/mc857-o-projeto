# Instrucoes para agentes de IA

Estas instrucoes valem para todo o repositorio.

## Fontes de verdade

Antes de alterar codigo ou estrutura:

1. leia `CONTRIBUTING.md`;
2. consulte `Desenvolvimento de Simulador F1.md` para escopo, fases e
   restricoes do produto;
3. consulte os ADRs aceitos em `docs/adr/`, quando existirem;
4. examine o codigo, os testes e a configuracao realmente presentes.

Em caso de divergencia, nao tente conciliar decisoes silenciosamente. Informe o
conflito e solicite uma decisao quando ele afetar o resultado.

Se existir `AGENTS.local.md`, leia-o apenas para procedimentos das ferramentas
locais. Ele pode complementar, mas nao substituir, as regras versionadas.

## Estado arquitetural atual

A arquitetura entre MVC e camadas com portas e adaptadores ainda nao foi
decidida. Nao apresente uma das alternativas como se estivesse aprovada e nao
crie uma estrutura hibrida por conveniencia. Uma decisao estrutural deve ser
registrada em um ADR aceito pelo grupo.

Enquanto a decisao estiver pendente, preserve estas fronteiras:

- regras da corrida independem de Streamlit, Plotly e formatos de dados;
- paginas e estado de sessao nao sao a fonte de verdade da simulacao;
- ingestao e persistencia nao fazem parte do motor;
- aleatoriedade e dependencias externas sao injetaveis e testaveis;
- o motor deve poder ser executado e testado sem navegador.

## Forma de trabalhar

- Preserve alteracoes existentes e limite o diff ao pedido atual.
- Nao edite bibliotecas, ambientes virtuais, dados brutos ou artefatos gerados.
- Para trabalho complexo, apresente ou mantenha um plano com etapas verificaveis.
- Divida mudancas grandes em fatias verticais pequenas, funcionais e testaveis.
- Nao adicione abstracoes, dependencias ou padroes sem um problema concreto.
- Mantenha unidades explicitas, parametros configuraveis e simulacoes
  reproduziveis por semente.
- Adicione ou atualize testes para comportamento novo e para correcoes de bugs.
- Execute as verificacoes relevantes disponiveis no repositorio. Se alguma nao
  puder ser executada, explique o motivo no encerramento.

## Commits

So crie commits quando o usuario solicitar ou autorizar. Quando houver
autorizacao:

- cada commit deve representar uma unica intencao e deixar o projeto em estado
  coerente e verificavel;
- nao misture refatoracao ampla, formatacao alheia e mudanca funcional;
- prefira a ordem: preparacao segura, comportamento, integracao e documentacao;
- use mensagens no formato `tipo(escopo): resumo`, conforme `CONTRIBUTING.md`;
- nunca reescreva historico compartilhado sem autorizacao explicita.

## Encerramento

Relate de forma objetiva:

- o comportamento alterado e os arquivos principais;
- as verificacoes executadas e seus resultados;
- riscos, limitacoes ou decisoes ainda pendentes;
- uma sugestao de divisao em commits, caso nao tenha sido autorizado a cria-los.
