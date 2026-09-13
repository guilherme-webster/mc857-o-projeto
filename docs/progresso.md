# Handoffs temporarios

GitHub Issues e a fonte de verdade do andamento. Este arquivo e usado somente
quando uma sessao nao consegue comentar ou atualizar a issue correspondente.
Assim que o acesso voltar, transfira o registro para a issue e remova a linha
temporaria em uma alteracao revisada.

## Como registrar

Informe a issue, responsavel, data/hora com fuso, etapa exata, verificacoes,
proximo passo e bloqueios. Nao marque uma issue como concluida apenas neste
arquivo: o estado oficial continua no GitHub.

| Issue | Responsavel | Atualizado em | Etapa em que ficou | Evidencias | Proximo passo ou bloqueio |
| --- | --- | --- | --- | --- | --- |
| #40, #61, #66 e #67 | #40: @DaviGabrielBC; #61/#66: @guilherme-webster; #67: sem responsavel atribuido | 2026-09-11 21:40 -03:00 | Revisao documental em `40-planejamento-modelagem`: FastAPI confirmado no ADR 0004; planejamento geral e pesquisa de perfilamento. `67-modelagem-pilotos` criada em worktree separado, sem implementacao. | Diff sem erros de whitespace; links locais conferidos; auditoria de contagens do ZIP Trotman/2024; fontes oficiais consultadas; uma consulta limitada OpenF1; leitura da branch #43 em `0f6255d`. Nenhum teste de execucao ou calibracao realizado. | Revisar e commitar documentos, integrar as decisoes na branch #67, coordenar o calculo com #43 e definir recorte/contrato Python. Expansao de FastF1 alem da geometria permanece proposta. Registro local para posterior publicacao nas issues: esta solicitacao autorizou documentacao e branches, sem envio de comentarios ao GitHub. |

## ETL enriquecido — 2026-09-12 (-03:00)

Issue #24, responsável @guilherme-webster; consumidores #66/#67 e integração
#43. Trabalho local em `24-enriquecimento-etl`, baseado em
`40-planejamento-modelagem` (`ef1859c`). Este registro sucede a proposta de
expansão FastF1 da entrada de 11/09; a expansão foi autorizada e implementada.

- Implementados os 14 CSVs completos do Trotman v128 e dez famílias de
  observações FastF1, com contratos Python, validação e publicação atômica.
- Validados o ZIP completo e São Paulo/2024, corrida e classificação, com
  telemetria e modo estrito. Isso não equivale a validar toda a temporada.
- Suíte: 99 testes, sem falhas, 13 ignorados por condições de interface gráfica.
  Verificações estáticas e evidências detalhadas no guia do ETL enriquecido.
- Preservadas duplicatas históricas e sentinelas de telemetria com sinalização
  de qualidade; corrigida a sintaxe da consulta antiga de pilotos.
- Próximo passo: revisão e commits conforme `commits-etl-enriquecimento.md`;
  depois definir amostra, filtros e alinhamento temporal para #66/#67 e
  compartilhar os contratos com #43. Perfilamento não foi implementado.
- Sem commits, push ou comentários enviados ao GitHub nesta entrega. O usuário
  solicitou os comandos para publicar; este registro precisa ser levado à #24
  quando houver autorização para enviar a atualização.

## Modelagem inicial de pilotos — 2026-09-12T18:58-03:00

Issues #61/#66/#67, na branch `40-modelagem-dos-dados`, worktree
`mc857-etl-enriquecimento`, após os merges do ETL em `d8ae3d8`. #61/#66 estão
atribuídas a @guilherme-webster; #67 permanece sem responsável no backlog
consultado. A sincronização também confirmou #74 (enriquecimento) fechada.

- Implementado `contextual-pace-v1`: perfil imutável, seleção conservadora de
  voltas e comparação por contexto, ritmo relativo e MAD; caso de uso pela
  porta `HistoryRepository`, CLI JSON e gráficos opcionais.
- Preservados os contratos do ETL, banco de entrada, cadastro de piloto e
  fronteiras Python; sem novo endpoint ou dependência no núcleo.
- Verificações: 117 testes sem falhas, 13 ignorados por condições gráficas;
  Ruff, whitespace e links locais passaram. Execução real em São Paulo/2024:
  580 de 1.134 voltas comparáveis, 18 de 20 inscritos com estimativa, para os
  limiares explícitos do guia. Gráficos PNG/SVG gerados e inspecionados.
- Análise de sensibilidade: 240 a 694 voltas nas cinco configurações verificadas.
  Não houve calibração preditiva ou validação em eventos reservados. Incerteza
  não foi estimada; os resultados continuam descritivos de piloto/equipe.
- Próximo passo #66/#67: ampliar eventos, reservar validação e definir métodos/
  limiares; #43/#70/#71: compartilhar o caso de uso e acordar conversão explícita
  em parâmetros do motor, evitando contar efeitos duas vezes.
- Guia: `docs/modelagem-pilotos-inicial.md`. Artefatos locais ignorados pelo Git:
  `data/curated/driver-profile-2024.json` e `driver-profile-v1-plots/`.
- Nenhum commit, push, comentário ou mudança de estado enviado ao GitHub.
  Registro local para posterior atualização da #67, pois o pedido autorizou
  implementação, não envio de mensagens. Não declarar a issue inteira concluída
  com base neste primeiro recorte experimental.

Sugestão de commits: comportamento, aplicação, CLI e testes juntos em
`feat(modelagem): estime ritmo e consistência por contexto`; documentação em
`docs(modelagem): registre o contrato inicial de pilotos`; espelho gerado em
`docs(backlog): atualize o espelho das issues`.

### Recuperação da geração local de gráficos

Matplotlib 3.11.2 instalado pelo Pipenv; `pip check` sem conflitos e 18 testes
da modelagem passaram nesse ambiente. Como `data/curated` e o cache haviam
sido removidos, o histórico Trotman completo e São Paulo/2024 R/Q foram
reingeridos em modo estrito. Gráficos PNG/SVG e JSON gerados com sucesso em
`data/curated/perfil-pilotos.S3ZHHn/`; JSON validado e gráfico inspecionado.
O comando repetível usa uma pasta nova por execução; não é necessário excluir
o banco nem criar o JSON de saída antecipadamente. Comandos de commits e
execução em `docs/commits-modelagem-pilotos.md`. Nenhum commit foi executado.

### Pesquisa de fontes, ampliação da amostra e nomes — 13/09/2026 (-03:00)

Continuação das issues #61/#66/#67, na branch `40-modelagem-dos-dados`.
Amostra ampliada via FastF1 existente para Bahrein, Silverstone e São Paulo/2024:
3.223 observações, 1.844 voltas comparáveis; 20 de 23 pilotos com estimativa
agregada ao exigir dois eventos. Banco anterior preservado; novo recorte sem
telemetria de alta frequência, explicitamente registrada como não solicitada.

Investigados OpenF1, Jolpica e as bases AlexJR/Vansh sugeridas pelo professor.
Foram consultados metadados, adquirido e auditado o ZIP Vansh v1 (11 CSVs) e
comparadas 57 voltas OpenF1/FastF1: 56 iguais e primeira volta com diferença de
475 ms. Janela OpenF1 do carro 11 retornou 18 intervalos, candidatos para
modelagem posterior de tráfego. Nenhuma fonte nova foi mesclada automaticamente
com os fatos canônicos. Evidências e condições estão em
`docs/fontes-e-amostra-pilotos.md`; downloads/manifestos fora do Git.

Gráficos passam a usar nomes do cadastro canônico, conservando IDs estáveis,
desambiguando homônimos e preservando fallback para ausência de nome. Gerados
JSON, PNG e SVG em `data/curated/perfil-ampliado.aPAUuF/`; imagens inspecionadas.
Verificações: 119 testes sem falhas, 13 ignorados por condições gráficas; Ruff,
whitespace, links locais e sintaxe dos comandos passaram.

Próximo passo: reservar eventos não usados para validação e especificar a
adoção de intervalos OpenF1 (proveniência, condições de dados, mapeamento de
sessão/piloto e alinhamento temporal), conforme o guia. Ampliar amostra ainda
não comprova robustez preditiva. Sem commits, push ou mensagens ao GitHub;
este registro deve ser levado à #67 quando o envio for autorizado.

Sugestões de commits desta fatia:
`fix(graficos): exiba nomes dos pilotos preservando os IDs` (aplicação, CLI e
testes) e `docs(modelagem): registre fontes e ampliação da amostra` (guia de
fontes, atualização da modelagem e progresso). O espelho gerado só precisa de
commit separado se a sincronização produzir diff.
