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

### Avaliação entre eventos — 13/09/2026 (-03:00)

Issues #66/#67 na branch `40-modelagem-dos-dados`, base `0b39f2f`. #66 atribuída
a @guilherme-webster; #67 sem responsável no backlog consultado. Implementados
plano explícito/versionado, validação de sessões/eventos disjuntos, perfis
separados com parâmetros comuns, cobertura e comparação descritiva em pp.
A CLI publica uma pasta nova completa com JSON/CSV/Markdown e gráficos PNG/SVG.

Protocolo definido antes da avaliação: Bahrein/Silverstone/São Paulo como
desenvolvimento; Itália/Abu Dhabi como validação; configuração anterior mantida,
com mínimo de dois eventos em cada grupo. Os dois eventos adicionais foram
ingeridos em cópia da base, sem telemetria de alta frequência. Cronologia não
estritamente futura registrada explicitamente. Nenhum parâmetro ajustado após
examinar métricas de validação.

Verificações: 134 testes sem falhas, 13 ignorados; Ruff aprovado. Testes incluem
isolamento da validação, ausência/insuficiência de dados e falha de publicação
sem apagar resultados anteriores. Duas execuções reais geraram JSON idêntico;
15/24 pilotos com métricas nos dois grupos, mudança absoluta mediana de ritmo
0,255540 pp e MAD 0,042532 pp. Isso não constitui erro de previsão ou aprovação
automática de robustez. Artefatos em `data/curated/evaluations/`, fora do Git.

Próximo passo: revisão dos relatórios e investigação de contexto/tráfego;
qualquer ajuste posterior exige novos eventos reservados para avaliação
confirmatória. Guia e reprodução: `docs/avaliacao-perfis-entre-eventos.md`.
Sem commits, push, comentários ou fechamento de issues; registro local para
posterior atualização da #67 quando o envio for autorizado.

Sugestões de commits: `feat(modelagem): avalie perfis em eventos separados`
(domínio, aplicação, CLI, testes e protocolo) e
`docs(modelagem): documente a avaliação entre eventos`
(guia, README, modelagem inicial e progresso). Espelho gerado em commit separado
somente se houver diff após a sincronização.

### Sensibilidade de contextos e incerteza — 13/09/2026 (-03:00)

Issues #66/#67; branch `40-modelagem-dos-dados`, checkout
`mc857-etl-enriquecimento`. Backlog sincronizado antes do trabalho, sem diff;
#66 atribuída a @guilherme-webster, #67 aberta e sem responsável registrado.
O pedido autorizou comparar contextos e explicitar confiabilidade; não houve
mensagens ao GitHub, commits ou push. Levar este registro à #67 quando autorizado.

Implementadas quatro variantes (original, número do stint, janela de cinco
voltas e combinação), com mesmos filtros de qualidade e suporte recalculado.
Intervalos percentis exploratórios reamostram eventos inteiros, com semente,
réplicas, nível e limiar heurístico de aviso configuráveis. Gráficos mostram
voltas/contextos/eventos, intervalos e indisponibilidade; não classificam outliers.

Execução real: 5.266 observações; 3.096/2.898/2.317/2.194 voltas comparáveis nas
quatro variantes. Pérez/Silverstone: original 8 voltas, MAD 1,386%; janela menor
6 voltas, MAD 0,802%; combinação sem estimativa. Preservado o padrão original,
pois restringir pode eliminar suporte e não demonstra uma correção causal.

Artefatos completos com PNG/SVG em
`data/curated/context-studies/sensitivity-6a4510c6d02d4d279126ced555f4a1c6/`.
Duas execuções produziram os quatro JSONs e os três arquivos de resumo/auditoria
idênticos. Métricas, cobertura e hash da referência coincidem com a avaliação
anterior. Gráficos de estabilidade, mapa de MAD e sensibilidade inspecionados.

Verificações: 144 testes sem falhas, 13 ignorados; 25 testes relevantes repetidos
após ajustes finais; Ruff, whitespace e links locais passaram. Nenhuma dependência
nova. Guia: `docs/sensibilidade-contextos-pilotos.md`.

Limitação: com 2–3 eventos, intervalos são exploratórios, condicionais e discretos;
não representam habilidade isolada nem validação confirmatória. Próximo passo:
novos eventos reservados e investigação de alinhamento temporal/tráfego antes
de promover outra regra padrão. ETL e motor permanecem fora desta alteração.

Sugestão de commits: `feat(modelagem): compare contextos e estime incerteza por evento`
(código, CLI e testes) e `docs(modelagem): registre sensibilidade e limites dos perfis`
(guias, README e progresso).

### Contrato do perfil e aquisição da temporada — 13/09/2026 (-03:00)

Issues #66/#67; branch `40-modelagem-dos-dados`, base `5034dde`. Backlog
sincronizado antes de trabalhar, sem diff; #66 atribuída a @guilherme-webster,
#67 aberta e sem responsável. Implementados os itens 1 e 2 autorizados:
especificação de efeitos de ritmo/variabilidade e ampliação via ETL existente.

`docs/contrato-perfil-simulacao.md` define significado, unidades, fórmula
candidata de ritmo, distinção entre MAD e incerteza, indisponibilidade, riscos
de dupla contagem de equipe e critérios de aceite da integração futura.
O motor não foi integrado nesta fatia; distribuição de ruído, referência por
circuito e separação piloto/equipe permanecem decisões de calibração.

Plano expandido registrado antes da aquisição e de qualquer métrica nova:
18 corridas de desenvolvimento, seis reservadas (etapas 3/6/9/14/18/23).
Os cinco eventos já vistos foram todos incluídos no desenvolvimento. Hash
`c28b469f24beab166b6386dced4fead51d0610864d6c23925e1f6ed8010cbb03`.
A divisão não é estritamente temporal. Nenhum perfil novo foi calculado.

ETL FastF1 3.8.3 executado para as 19 corridas restantes, sem telemetria, no
ambiente existente `/tmp/mc857-evaluation-venv/bin/python`. Criados bancos
separados de desenvolvimento (18 corridas, 20.262 observações) e completo
(24 corridas, 26.604 observações), preservando a base anterior. Reserva tem
6.342 observações; não confundir essas contagens com cobertura comparável.
Manifestos e auditoria local conservam proveniência e qualidade. `t0_date`
indisponível e telemetria não solicitada permanecem explícitos.

Verificações: integridade e chaves SQLite aprovadas nos dois bancos, sessões
exatamente conforme plano, relatórios antigos preservados e contagens conferidas.
147 testes sem falhas, 13 ignorados; Ruff, links e sintaxe dos comandos passaram.
Guia: `docs/amostra-pilotos-2024-expandida.md`; bancos/logs/auditoria fora do Git.

Próximo passo: explorar estabilidade e comparações no desenvolvimento usando
somente o banco de 18 eventos; congelar decisões antes de avaliar a reserva.
Não executar a CLI de avaliação com o plano expandido durante essa exploração,
pois ela calcula ambos os grupos. Exemplo Python seguro está no guia.

Sem commits, push ou mensagens ao GitHub; levar este andamento à #67 quando
a publicação for autorizada. Sugestão de commits:
`docs(modelagem): especifique efeitos de ritmo e variabilidade` e
`feat(dados): configure amostra de 2024 com eventos reservados`.

### Exploração exclusiva do desenvolvimento — 13/09/2026 (-03:00)

Continuação de #66/#67, branch `40-modelagem-dos-dados`. Preservadas as mudanças
pendentes do contrato e da aquisição anterior. Backlog sincronizado sem diff.
Implementados caso de uso `analyze_development` e CLI própria, sem solicitar
registros das sessões reservadas. Quatro agrupamentos, suporte/bootstrap e
influência por retirada de um evento; gráficos PNG/SVG e CSVs publicados em
pasta nova, sem tocar no banco completo com reserva.

Original: 12.558/20.262 voltas comparáveis (61,98%), 23/24 pilotos com perfil.
Cobertura das alternativas: 58,52%/47,70%/45,23%. Jack Doohan mantém apenas um
evento; Bearman tem três. Ritmo original: Pérez −0,358%, Zhou +0,441%,
Verstappen −0,555%, Norris −0,673%. São observações piloto/equipe/contexto,
sem ranking de habilidade. Retirar um evento não é erro de previsão.

Decisões para avaliação futura registradas em
`configs/profile-validation-decision-2024.json`: preservar variante original,
filtros, mínimos e bootstrap; métricas descritivas e ausência sem imputação;
sem aprovação automática. Reserva não avaliada. Próximo passo é consultar a
reserva com essas escolhas fixadas, registrando qualquer revisão posterior.

Artefatos: `data/curated/development-studies/development-1147b746d0c14c22bcff802f2f219c41/`.
Duas execuções produziram JSON e oito CSVs idênticos. Gráfico original inspecionado.
152 testes sem falhas, 13 ignorados; Ruff, whitespace, links e correspondência
entre plano e registro de decisões aprovados. Cinco testes novos cobrem isolamento
da reserva, influência conhecida, mínimo de eventos e falha de publicação.
Guia: `docs/analise-desenvolvimento-pilotos-2024.md`.

Não criados commits, push ou mensagens ao GitHub. Registro local para posterior
publicação na #67 quando autorizada. Para o diff acumulado, agrupar contrato,
plano e aquisição anteriores em `feat(modelagem): defina contrato e reserve amostra de 2024`;
a exploração atual em `feat(modelagem): analise estabilidade no desenvolvimento`.

### Avaliação da reserva — 18/09/2026 (-03:00)

Issues #66/#67; branch `40-modelagem-dos-dados`, base `639a9af`. Backlog
sincronizado sem diff. Executados os itens autorizados: avaliar as seis corridas
reservadas com o método congelado e investigar divergências antes de ajustar.
Hash do plano/configuração conferidos; bootstrap e variante carregados do registro
de decisões. Nenhuma mudança de filtros, mínimos, dados, agrupamento ou motor.

20/24 pilotos com estimativas nos dois grupos. Reserva: 3.237/6.342 voltas
comparáveis (51,04%); desenvolvimento: 12.558/20.262 (61,98%). Mudança absoluta
mediana: ritmo 0,129507 pp, MAD 0,030092 pp. Investigados composição de compostos,
chuva, suporte, exclusões, equipes e valores por evento. Canadá concentra todos
os contextos intermediários da reserva e tem cobertura 40,41%. Mesmas equipes
nos 20 pares não isolam efeitos de carro/circuito/estratégia.

Maiores mudanças de ritmo: Gasly +0,500 pp, Verstappen −0,405 pp, Norris −0,343 pp;
Pérez muda +0,047 pp. Relatório distingue fatos e hipóteses, sem aprovação de
robustez ou causalidade. A reserva agora é conhecida; ajustes posteriores
precisarão de outra amostra independente para nova validação.

Artefatos: `data/curated/reserved-evaluations/evaluation-7735cb823f9f44de9b10194ac339842d/`.
JSON/quatro CSVs idênticos em duas execuções; desenvolvimento idêntico ao anterior.
33 testes relevantes passaram; links, sintaxe e whitespace aprovados; gráfico de
estabilidade inspecionado. Guia: `docs/avaliacao-reserva-pilotos-2024.md`.

Próximo passo: comparações entre companheiros em contextos compartilhados e
especificação de referência de tempo para experimento determinístico; não
confundir essa evolução com a avaliação congelada concluída aqui.
Sem commits, push ou mensagens ao GitHub. Registro para posterior publicação
na #67 quando autorizada. Sugestão: `docs(modelagem): registre avaliação da reserva e divergências`.

### Companheiros e referência determinística — 18/09/2026 (-03:00)

Issues #66/#67; branch `40-modelagem-dos-dados`. Backlog sincronizado sem diff;
#66 atribuída a @guilherme-webster, #67 sem responsável registrado. Implementados
domínio `teammates`, caso de uso `analyze_teammates` e CLI com JSON/CSV/PNG/SVG.
Selecionados somente os 18 eventos de desenvolvimento; estudo exploratório,
pois a reserva anterior já foi examinada. ETL e motor não foram alterados.

Comparação usa mesmos contextos e equipe, medianas de tempos dos dois pilotos,
gap percentual com denominador simétrico, agregação com peso igual por evento
e bootstrap de eventos pareados. Mantidos mínimos e filtros do perfilador.
Dos 15 pares/equipe, 12 têm ao menos dois eventos compartilhados. Pérez–Verstappen
+0,501%; Norris–Piastri −0,187%; Bottas–Zhou −0,163% com intervalo incluindo zero.
Contagens de contextos/voltas e indisponibilidade acompanham as estimativas.

Exportadas 444 referências em ms por contexto exato. O contrato do experimento
usa mediana das medianas do pelotão, sem dupla contagem de efeitos ou ruído.
Exemplo Bahrein: 97.175,5 ms, 18 pilotos/54 voltas; reconstruir medianas do mesmo
contexto é teste estrutural, não previsão. Definidos escopo, ausência, unidade e
arredondamento na futura fronteira do relógio; sem conectar o motor nesta fatia.

Artefatos: `data/curated/teammate-studies/teammates-593cc2a0d9bf4ef9bd11a83888a9de55/`.
JSON/dois CSVs idênticos em duas execuções e gráfico inspecionado. 161 testes
sem falhas, 13 ignorados; Ruff, whitespace, links e sintaxe aprovados.
Guia: `docs/companheiros-e-referencia-deterministica.md`.

Próximo passo: integrar o microexperimento determinístico pelo contrato Python,
escolhendo contexto e referência explícitos, antes de extrapolar a uma corrida
inteira. Causalidade piloto/equipe, ruído e validação independente seguem pendentes.
Sem commits, push ou mensagens ao GitHub; registro para posterior publicação
na #67 quando autorizada. Sugestões: `feat(modelagem): compare companheiros em contextos compartilhados`
(código/testes) e `docs(modelagem): especifique referência determinística por contexto`
(guias/README/progresso).

Na verificação ampla de snippets, identificado comando Docker preexistente no
README com link Markdown dentro de `curl`; não alterado por estar fora do escopo.
A sintaxe do novo comando de análise foi verificada separadamente e passou.
