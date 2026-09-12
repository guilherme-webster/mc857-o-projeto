# 0004 - Backend FastAPI e contratos Python internos

- Status: aceita
- Data: 2026-09-11
- Responsaveis: grupo do projeto; decisao comunicada por Guilherme nesta revisao
- Substitui: escolha de Django nos ADRs 0001 e 0002; demais decisoes preservadas

## Contexto

O usuario confirmou que o grupo escolheu FastAPI em lugar de Django e pediu
coerencia na documentacao. O codigo do backend ja usa FastAPI, mas as fontes
de verdade ainda indicavam Django. Tambem surgiu a duvida sobre exigir HTTP
para a modelagem consumir os dados em uma aplicacao executada localmente.

## Alternativas consideradas

- Manter Django: contraria a escolha explicitada pelo grupo e o backend atual.
- Adotar FastAPI como adaptador de entrada, mantendo dominio e aplicacao Python.
- Criar um servico HTTP separado para cada modelagem: nao ha fronteira de
  processo ou necessidade concreta que justifique essa complexidade.

## Decisao

FastAPI e o framework do backend. Rotas validam e traduzem requisicoes e
respostas e chamam os casos de uso; nao concentram estatisticas de perfilamento,
regras da corrida ou acesso a formatos externos dentro do dominio.

A integracao interna segue o ADR 0002: casos de uso coordenam repositories e
objetos canonicos por contratos Python. Modelagem de piloto, pista, carro,
pneu e clima nao precisa de endpoint ou cliente HTTP para funcionar. A
composicao injeta adaptadores; o mesmo nucleo pode ser chamado por testes ou
por uma entrada local sem servidor. Criar portas apenas para dependencias
concretas; nao uma interface por entidade ou um microservico por modelo.

O contrato HTTP/JSON previsto entre Arcade e backend permanece na arquitetura
vigente. Este registro nao decide remover essa fronteira: juntar ambos no mesmo
processo e uma alternativa a avaliar separadamente, inclusive quanto ao
empacotamento e ao trabalho em andamento do backend. "Rodar localmente" nao
determina sozinho a quantidade de processos. Nenhuma regra do nucleo depende
da escolha futura de transporte.

## Consequencias

- CONTRIBUTING, instrucoes dos agentes, proposta e plano passam a citar FastAPI.
- Os ADRs anteriores preservam sua justificativa historica com aviso de
  substituicao parcial; mencoes antigas no backlog continuam sendo historico.
- A issue #66 deve ser refinada como consumo do contrato canonico Python para
  perfilamento; nao implica buscar um dump HTTP do banco. Essa e uma sugestao
  de refinamento, nao uma alteracao da issue feita por este ADR.
- A branch da issue #43 tem calculos de parametros em `backend/app/engine`;
  sua futura integracao deve compartilhar os casos de uso com #67 e evitar
  duas formulas independentes para o mesmo parametro.
- Este registro alinha documentacao. Nao migra codigo nem altera a politica
  de fontes do ADR 0003. Expandir FastF1 para perfis continua uma proposta.
