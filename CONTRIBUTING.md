# Guia de contribuicao

Este documento e a referencia comum para contribuicoes humanas e assistidas por
IA. As regras devem ser aplicadas em conjunto com o plano de desenvolvimento e
com as decisoes arquiteturais aceitas pelo grupo.

## Compatibilidade com assistentes de IA

`AGENTS.md` fornece instrucoes automaticas para ferramentas compativeis, mas
nenhum arquivo de prompt garante sozinho que todas as ferramentas aplicarao as
mesmas regras. `CONTRIBUTING.md` e, portanto, a fonte de verdade independente de
fornecedor.

Quando o grupo definir quais assistentes serao usados, criar apenas adaptadores
curtos para os formatos exigidos por eles, apontando para este documento, em vez
de copiar todas as regras. Regras duplicadas em `CLAUDE.md`, configuracoes do
Cursor, instrucoes do Copilot ou arquivos semelhantes tendem a divergir.

As regras objetivas devem ser reforcadas por automacao assim que houver codigo:
formatador, linter, verificacao de tipos e testes executados localmente e no CI.
Instrucoes orientam o processo; essas verificacoes sao a barreira reproduzivel.

## Principios do projeto

- Entregar o MVP de forma incremental, mantendo cada incremento executavel.
- Priorizar codigo simples, legivel, testavel e justificavel pelos requisitos.
- Preservar a reproducibilidade: dados, parametros, versoes e sementes precisam
  ser identificaveis.
- Separar regras de dominio, interface, dados e infraestrutura.
- Evitar escopo acidental, generalizacoes prematuras e tecnologia sem uso real.
- Tratar codigo gerado por IA com o mesmo nivel de revisao que codigo humano.

## Decisoes vigentes

O plano atual estabelece:

- Python 3.12 ou superior;
- Streamlit e Plotly para a interface do MVP;
- um monolito modular, sem microsservicos ou WebSocket proprio;
- motor de simulacao independente da interface e das fontes de dados;
- execucao reproduzivel com fonte aleatoria injetada e semente registrada;
- arquivos brutos e grandes fora do Git, com pequenas amostras versionadas para
  testes quando necessario.

A escolha entre MVC e camadas com portas e adaptadores permanece pendente. Ela
deve ser aprovada pelo grupo e registrada em `docs/adr/` antes de orientar a
estrutura definitiva de `src/`.

## Fluxo de desenvolvimento

1. **Entender:** ler o pedido, o plano, os ADRs relevantes e o codigo afetado.
2. **Delimitar:** registrar comportamento esperado, fora de escopo e criterios
   de aceitacao observaveis.
3. **Planejar:** para mudancas complexas, decompor o trabalho em fatias que
   entreguem comportamento verificavel. Quantidade de linhas, isoladamente, nao
   define complexidade.
4. **Implementar:** fazer a menor alteracao coesa que satisfaca cada criterio.
5. **Verificar:** executar testes, analise estatica e formatacao aplicaveis.
6. **Revisar:** inspecionar o diff, remover alteracoes acidentais e documentar
   decisoes ou limitacoes relevantes.

Considere uma mudanca complexa quando ela altera contratos, persistencia,
estrutura arquitetural, varias fronteiras do sistema ou mais de um
comportamento independente. Nesses casos, nao concentrar toda a entrega em um
unico diff dificulta revisao e reversao.

## Fatias e commits

Uma boa fatia atravessa apenas as camadas necessarias e termina com um resultado
util e testavel. Exemplos:

- definir um objeto de dominio com invariantes e seus testes;
- implementar um caso de uso sobre esse objeto e seus testes;
- conectar o caso de uso a uma tela sem mover regras para a interface;
- adicionar um adaptador de uma fonte usando uma amostra pequena e validada.

Quando houver commits:

- manter uma unica intencao por commit;
- deixar testes relevantes passando ao final de cada commit;
- separar refatoracao mecanica de alteracao de comportamento;
- nao misturar formatacao de arquivos alheios ao pedido;
- incluir mudancas de contrato junto de seus consumidores ou manter
  compatibilidade durante a transicao;
- nao versionar segredos, ambientes virtuais, bibliotecas instaladas, dados
  brutos grandes ou resultados gerados.

Usar mensagens curtas no formato:

```text
tipo(escopo): resumo no imperativo
```

Tipos usuais: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`. O escopo pode
ser omitido quando nao acrescentar informacao.

Assistentes de IA nao devem criar commits sem solicitacao ou autorizacao
explicita. Sem essa autorizacao, devem entregar o diff verificado e sugerir uma
divisao de commits para revisao humana.

## Arquitetura e design

- Registrar em ADR toda decisao dificil de reverter ou que afete mais de um
  componente.
- Usar interfaces em fronteiras externas ou quando houver variacao real; nao
  criar uma interface para cada classe.
- Aplicar Strategy, State, Repository, Adapter ou outros padroes apenas quando o
  problema correspondente estiver presente.
- Preferir composicao a herancas profundas.
- Manter dependencias apontando para o dominio, nunca do dominio para Streamlit,
  Plotly, Pandas, arquivos ou banco de dados.
- Tratar `RaceSnapshot` como representacao de saida; a visualizacao nao calcula
  classificacao nem altera o estado diretamente.
- Representar unidades nos nomes ou em tipos consistentes e converter formatos
  externos durante a ingestao.
- Nomear e versionar parametros de simulacao; nao esconder constantes de modelo
  em condicionais.

## Codigo e testes

- Escrever nomes que expressem a linguagem do dominio e funcoes com uma
  responsabilidade clara.
- Adicionar anotacoes de tipo nas interfaces publicas do projeto.
- Documentar o motivo de regras e decisoes nao obvias; evitar comentarios que
  apenas repetem o codigo.
- Tratar erros de maneira explicita, sem ignorar excecoes silenciosamente.
- Nao adicionar dependencia sem justificar o problema resolvido e verificar se
  uma dependencia existente ja o resolve.
- Cobrir novas regras com testes unitarios deterministas.
- Adicionar teste de regressao antes ou junto da correcao de um bug.
- Usar testes de integracao para adaptadores, persistencia e conexoes entre
  componentes.
- Manter amostras de teste pequenas, anonimizadas quando necessario e com
  origem/licenca registradas.
- Verificar invariantes do simulador e reprodutibilidade com a mesma semente.

Os comandos oficiais de instalacao, teste, lint e formatacao devem ser
registrados no `README.MD` assim que a configuracao do projeto for criada.

## Dados e seguranca do repositorio

- Nao editar manualmente arquivos em `data/raw/`.
- Nao acessar telemetria bruta diretamente a partir da interface ou do motor.
- Nao preencher dados ausentes silenciosamente com zero.
- Registrar fonte, versao, licenca, unidade e transformacao dos dados derivados.
- Nunca incluir credenciais, tokens, dados pessoais ou arquivos de configuracao
  locais no Git.
- Antes de alterar `.gitignore`, confirmar que a regra nao protege arquivos
  locais ou dados grandes de outros integrantes.

## Revisao e definicao de pronto

Uma mudanca esta pronta quando:

- os criterios de aceitacao foram atendidos;
- o diff esta limitado ao objetivo declarado;
- testes relevantes passam e verificacoes de qualidade foram executadas;
- documentacao e ADRs foram atualizados quando a mudanca altera uso ou design;
- riscos, hipoteses e verificacoes nao executadas estao explicitos;
- outro integrante consegue compreender e reproduzir o resultado.

Na revisao, priorizar corretude, limites arquiteturais, cobertura de casos de
erro, legibilidade, reprodutibilidade e facilidade de reversao.
