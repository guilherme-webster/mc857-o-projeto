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
