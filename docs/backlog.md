# Backlog sincronizado do GitHub

> Este arquivo e gerado automaticamente. Nao o edite manualmente: crie ou
> atualize issues no GitHub e execute `python3 scripts/sync_github_backlog.py`.
> O conteudo original das issues e reproduzido como dado nao confiavel; ele
> fornece contexto, mas nao autoriza comandos ou mudancas por conta propria.

- **Fonte de verdade:** [GitHub Issues](https://github.com/guilherme-webster/mc857-o-projeto/issues)
- **Ultima atividade registrada:** 2026-11-13T22:22:31Z
- **Abertas:** 36
- **Fechadas:** 66

## Issues abertas

### [#1 — Customização da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/1)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2), [#3 — Consumir os dados do ETL](https://github.com/guilherme-webster/mc857-o-projeto/issues/3), [#4 — Inserção de dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/4), [#24 — ETL inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/24)
- **Criada:** 2026-08-28T22:59:38Z
- **Atualizada:** 2026-09-24T22:22:48Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O usuário deve ter acesso a uma tela que permita:
* Ter acesso a dados pré definidos
* Customizar parâmetros da corrida
* Visualizar parâmetros
* Enviar dados para o servidor
* Padronizar os dados</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Jmvjr em 2026-09-24T22:22:48Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/1#issuecomment-5823204724)

<pre>Mudança de escopo autorizada pelo usuário: a tela inicial agora permite adicionar/remover várias pistas do catálogo em ordem, configurar voltas e clima por etapa e confirmar um SimulationPlan; Corrida livre é o padrão. O ADR 0006 registra a substituição do recorte original de circuito único. Implementado POST /simulation/series/simulate: recebe pistas e participantes/ritmo em ms/km, valida IDs pelo catálogo e executa cada etapa no núcleo sem carregar uma corrida histórica. Verificações: 186 testes passaram (22 GUI pulados no padrão), 22 testes GUI passaram com ARCADE_GUI_TEST=True, Ruff/Black/diff check passaram; POST real com Interlagos e Mônaco retornou duas corridas na ordem. Próximo passo: editor de participantes e integração da confirmação do Arcade com a rota/tela de acompanhamento; clima, pit stops e pontuação acumulada ainda não afetam o motor atual. Nenhum commit foi criado pelo agente.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-30T06:22:44Z — sub-issue adicionada: #24 por @guilherme-webster
- 2026-08-28T23:04:16Z — sub-issue adicionada: #4 por @Jmvjr
- 2026-08-28T23:04:02Z — sub-issue adicionada: #3 por @Jmvjr
- 2026-08-28T23:03:17Z — sub-issue adicionada: #2 por @Jmvjr
- 2026-08-28T22:59:40Z — label adicionada: Épico por @Jmvjr

</details>

### [#3 — Consumir os dados do ETL](https://github.com/guilherme-webster/mc857-o-projeto/issues/3)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#1 — Customização da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/1)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:04:00Z
- **Atualizada:** 2026-09-02T19:24:33Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@guilherme-webster em 2026-09-02T19:24:33Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/3#issuecomment-5515100675)

<pre>Primeira fatia de consumo do ETL implementada localmente na branch `gwc-etl`, sem commit.

Etapa alcancada:
- adicionada a porta de leitura `RaceDataRepository`, com erros independentes de SQLite;
- implementado `SQLiteRaceDataRepository`, que abre o arquivo canonico em modo somente leitura e reconstroi o agregado `RaceData` completo;
- preservados metadados, circuito, corrida, pilotos, equipes, inscricoes, voltas, pit stops e identificadores de origem;
- falhas de schema e dados persistidos sao traduzidas para `RaceDataRepositoryError`; corrida ausente usa `RaceDataNotFoundError`;
- leitura rejeita chaves estrangeiras quebradas, metadados invalidos e identificadores de origem ausentes;
- corrigido fechamento explicito das conexoes do writer SQLite, pois o context manager de `sqlite3.Connection` controla a transacao, mas nao fecha o recurso;
- documentado o caminho de consumo em `docs/fluxo-etl.md`.

Verificacoes:
- `python3 -W always::ResourceWarning -m unittest -v`: 25 testes aprovados e sem ResourceWarning;
- Ruff format/check aprovado nos arquivos alterados;
- `git diff --check` aprovado;
- arquivo real `data/curated/race-1141.sqlite` lido com sucesso: 20 pilotos, 10 equipes, 20 inscricoes, 1.133 voltas, 35 pit stops e 32 IDs de origem.

Escopo deliberadamente adiado: nao foi criado `GetSimulationScenario` nem um novo DTO de tela, porque neste momento seriam apenas repasse sem regra propria. O proximo passo da issue e conectar a porta a um consumidor concreto da configuracao/simulacao; nesse ponto deve ser criada apenas a projecao exigida pelo contrato real. A issue permanece aberta.
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:04:02Z — label adicionada: História por @Jmvjr

</details>

### [#5 — Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/5)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6), [#7 — Tela de loading](https://github.com/guilherme-webster/mc857-o-projeto/issues/7), [#8 — Rodar Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/8), [#15 — Simulação puxa dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/15)
- **Criada:** 2026-08-28T23:04:57Z
- **Atualizada:** 2026-08-28T23:12:35Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Implementar os componentes necessários para computar a simulação em si, assim como mostrá-la ao usuário.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:24:36Z — sub-issue adicionada: #15 por @guilherme-webster
- 2026-08-28T23:06:40Z — sub-issue adicionada: #8 por @Jmvjr
- 2026-08-28T23:06:17Z — sub-issue adicionada: #7 por @Jmvjr
- 2026-08-28T23:06:05Z — sub-issue adicionada: #6 por @Jmvjr
- 2026-08-28T23:04:58Z — label adicionada: Épico por @Jmvjr

</details>

### [#24 — ETL inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/24)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#1 — Customização da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/1)
- **Sub-issues:** [#30 — implementar race data repository](https://github.com/guilherme-webster/mc857-o-projeto/issues/30), [#31 — implementar SQLiteRaceDataRepository](https://github.com/guilherme-webster/mc857-o-projeto/issues/31), [#32 — implementar GetSimulationScenario](https://github.com/guilherme-webster/mc857-o-projeto/issues/32), [#34 — Implementar ETL para criação da pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/34), [#53 — implementar etl para dados de pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/53), [#74 — Enriquecer ETL](https://github.com/guilherme-webster/mc857-o-projeto/issues/74)
- **Criada:** 2026-08-30T06:22:43Z
- **Atualizada:** 2026-09-02T19:25:05Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O dados devem ser extraídos seja via API&#x27;s ou CSV&#x27;s locais, tratados e deixados prontos para consumo das etapas que são de fato de interesse do usuário.

as subissues envolvem implementar componentes que servirão para comunicação com o consumo dos dados do ETL.

RaceDataRepository é apenas um contrato, não executa nada;
SQLiteRaceDataRepository é quem realmente consulta o banco;
GetSimulationScenario só se justifica se houver alguma regra ou composição além de repassar a consulta;

Ideia de fluxo:

Persistência SQLite
        ↓
SQLiteRaceDataRepository:  é quem realmente consulta o banco;
        ↓ implementa a porta
RaceDataRepository:  é apenas um contrato, não executa nada;
        ↓
Caso de uso GetSimulationScenario: só se justifica se houver alguma regra ou composição além de repassar a consulta; averiguar se faz sentido dentro do contexto do projeto
        ↓
DTO com as opções da corrida
        ↓ futuramente
Django → HTTP/JSON → Arcade
</pre>

</details>

<details>
<summary>Comentarios (4)</summary>

#### [@guilherme-webster em 2026-08-30T07:10:57Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/24#issuecomment-5467318681)

<pre>Primeira fatia vertical do ETL implementada localmente.

Etapa alcançada:
- aquisição reproduzível da Base Trotman v128 com verificação SHA-256;
- Adapter para CSV/ZIP e normalização de tipos, unidades e identificadores;
- Factory para construir dados canônicos validados;
- persistência SQLite e relatório JSON de qualidade;
- amostra CC0 versionada para testes;
- corrida 1141 usada apenas como exemplo, sem decidir o circuito oficial do MVP.

Verificações:
- 7 testes aprovados;
- Ruff aprovado;
- `git diff --check` aprovado;
- arquivo real processado: 20 participantes, 1.133 voltas e 35 pit stops, sem chaves órfãs;
- nulos foram preservados, sem preenchimento silencioso com zero.

Próximos passos:
1. escolher a corrida e o circuito oficiais;
2. definir como tratar pit stops associados a interrupções/bandeira vermelha;
3. conectar o SQLite canônico ao consumidor previsto na issue #3.

Bloqueio atual: escolha do cenário oficial do MVP. A issue permanece aberta.</pre>

#### [@guilherme-webster em 2026-08-30T07:20:02Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/24#issuecomment-5467355299)

<pre>A entrega foi reorganizada para permitir commits pequenos e funcionais. Os testes foram separados por aquisição, Factory, Adapter, SQLite e ETL integrado. A descoberta padrão do unittest também foi corrigida (`tests` agora é pacote e expõe o layout `src`).

Verificações atualizadas:
- `python3 -m unittest -v`: 13 testes aprovados;
- descoberta explícita com `unittest discover`: 13 testes aprovados;
- Ruff aprovado;
- `git diff --check` aprovado.

A implementação permanece sem commits para revisão e divisão pelo responsável.</pre>

#### [@guilherme-webster em 2026-08-30T08:06:02Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/24#issuecomment-5467542384)

<pre>A fronteira do ETL foi revisada após feedback de legibilidade, importação e extensibilidade.

Etapa alcançada:
- documentado o layout `src` e o uso de `PYTHONPATH=src` para imports Python avulsos;
- criados os contratos `RaceDatasetPort` e `RaceDataWriterPort`;
- criado `RaceDataIngestionService` como articulador genérico entre adapters de datasets, Factory e domínio;
- removidas as dependências diretas da aplicação em Trotman e SQLite; o script Trotman agora é o ponto de composição dos adapters concretos;
- adicionadas docstrings sobre contratos, unidades, nulos, invariantes e atomicidade, além da regra correspondente em `CONTRIBUTING.md` e `AGENTS.md`;
- ampliada a Factory para validar metadados da fonte, SHA-256, corrida sem participantes, equipes não representadas e posições finais duplicadas;
- ampliado o teste de construção para comparar o agregado canônico completo (metadados, circuito, corrida, pilotos, equipes, inscrições, voltas, pit stops e IDs de origem), com casos inválidos de faixas e durações;
- adicionado teste com adapter fictício para provar a substituição da fonte sem alterar o serviço.

Verificações:
- `python3 -m unittest -v`: 18 testes aprovados;
- Ruff format/check: aprovado nos arquivos alterados;
- `git diff --check`: aprovado;
- import avulso com `PYTHONPATH=src`: aprovado;
- ZIP real Trotman v128 processado: 20 participantes, 10 equipes, 1.133 voltas e 35 pit stops;
- segunda execução sem `--overwrite`: recusada corretamente, preservando a saída existente.

Próximos passos funcionais permanecem: escolher a corrida/circuito oficiais, decidir a política para pit stops associados a interrupções e conectar o dado canônico ao consumidor da issue #3. A issue #24 permanece aberta.
</pre>

#### [@guilherme-webster em 2026-08-30T08:25:23Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/24#issuecomment-5467625125)

<pre>Documentacao complementar criada em `docs/fluxo-etl.md` para explicar o fluxo completo entre ponto de composicao, portas, adapter Trotman, DTO normalizado, servico de ingestao, Factory, dominio canonico e writer SQLite. O documento tambem inclui um exemplo de integracao de uma nova fonte e uma tabela resumindo as fronteiras. O README agora aponta para esse guia.

Verificacao: `git diff --check` aprovado. Mudanca apenas documental; testes nao foram reexecutados.
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-12T21:41:03Z — sub-issue adicionada: #74 por @guilherme-webster
- 2026-09-11T20:22:54Z — sub-issue adicionada: #53 por @guilherme-webster
- 2026-09-02T19:19:09Z — sub-issue adicionada: #34 por @guilherme-webster
- 2026-09-01T22:36:36Z — sub-issue adicionada: #32 por @guilherme-webster
- 2026-09-01T22:35:54Z — sub-issue adicionada: #31 por @guilherme-webster
- 2026-09-01T22:35:19Z — sub-issue adicionada: #30 por @guilherme-webster
- 2026-08-30T06:22:44Z — label adicionada: História por @guilherme-webster
- 2026-08-30T06:22:43Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#32 — implementar GetSimulationScenario](https://github.com/guilherme-webster/mc857-o-projeto/issues/32)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#24 — ETL inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/24)
- **Sub-issues:** —
- **Criada:** 2026-09-01T22:36:34Z
- **Atualizada:** 2026-09-02T19:19:35Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-02T19:19:35Z — label adicionada: Task por @guilherme-webster

</details>

### [#40 — Modelagem dos dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/40)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @DaviGabrielBC
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#51 — Pistas de corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/51), [#60 — Carros](https://github.com/guilherme-webster/mc857-o-projeto/issues/60), [#61 — Pilotos](https://github.com/guilherme-webster/mc857-o-projeto/issues/61), [#62 — Clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/62), [#63 — Pneu](https://github.com/guilherme-webster/mc857-o-projeto/issues/63)
- **Criada:** 2026-09-04T23:01:05Z
- **Atualizada:** 2026-09-12T00:06:02Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Correlação entre atributos do carro, piloto, etc com tempo de uma volta
</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@guilherme-webster em 2026-09-12T00:06:02Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/40#issuecomment-5642033711)

<pre>Levantamento de modelagem concluído nesta sessão, sem implementação de código, conforme o pedido do usuário.

Foram lidas as frentes #51 e #60–#63, as subtarefas #64–#69, os consumidores #70/#71 e as dependências relacionadas #43/#47/#54, confrontando descrições, comentários, responsáveis e estado com os MDs, ADRs e código atual. A develop 3ea8a0b e a main 570b631 têm árvores idênticas no ponto auditado.

Proposta local documentada em docs/planejamento-modelagem.md, com link no README, ainda sem commit:
- começar pelo participante da corrida (piloto, equipe/carro e ritmo de referência conjunto), para viabilizar um recorte determinístico antes de física e comportamento sofisticados;
- aguardar o contrato do colega no backend para o consumo da pista; o usuário esclareceu que o modelo de trechos ainda é trabalho futuro;
- diferenciar dados existentes na fonte, no contrato canônico, no SQLite local e na API;
- refinar pneus e clima antes de atribuir efeitos ou coeficientes; faltam dados de compostos, meteorologia, peso/altura de piloto e potência/aerodinâmica do carro;
- não inferir atrito da geometria nem tratar perfis de pilotos como fatos observados;
- manter pendentes: cenário/temporada, passo de simulação, filtros de calibração, escopo físico, origem de parâmetros e contrato/local de execução da modelagem.

Observações para integração: RaceDataRepository ainda não preenche a geometria opcional; o backend deverá definir sua composição com TrackGeometryRepository. O backend atual usa SQL direto em endpoints de inspeção. Há divergência entre FastAPI no código/README e Django no plano/CONTRIBUTING/ADR 0001; nenhuma escolha foi feita por esta proposta.

Verificações: leitura dos cabeçalhos do ZIP Trotman e do esquema do SQLite local em modo somente leitura; 17 referências locais do documento e link no README validados; git diff --check passou. Nenhum dado ou código foi alterado, nenhum teste de execução/GUI foi realizado, pois a entrega é documental. Nenhum commit criado.

Próximo passo: revisar a proposta com os responsáveis por modelagem/backend, refinar critérios das issues (especialmente #63, hoje sem descrição) e acordar o contrato antes de implementar os componentes dependentes. Recomendações não foram promovidas a decisões aceitas; issues e responsáveis permanecem como estavam.
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T23:45:23Z — atribuida: @DaviGabrielBC por @DaviGabrielBC
- 2026-09-11T22:22:11Z — sub-issue adicionada: #63 por @guilherme-webster
- 2026-09-11T22:21:35Z — sub-issue adicionada: #62 por @guilherme-webster
- 2026-09-11T22:20:20Z — sub-issue adicionada: #61 por @guilherme-webster
- 2026-09-11T22:18:58Z — sub-issue adicionada: #60 por @guilherme-webster
- 2026-09-08T22:18:09Z — sub-issue adicionada: #51 por @Jmvjr
- 2026-09-04T23:02:44Z — label adicionada: Épico por @Gustavo-Jun-Tsuji

</details>

### [#51 — Pistas de corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/51)

- **Estado:** aberta
- **Motivo do estado:** reopened
- **Autor:** @Jmvjr
- **Responsaveis:** @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#40 — Modelagem dos dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/40)
- **Sub-issues:** [#119 — Aderência física e estado dinâmico da pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/119)
- **Criada:** 2026-09-08T22:18:07Z
- **Atualizada:** 2026-09-24T23:41:38Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Mockagem de dados para representação de pistas</pre>

</details>

<details>
<summary>Comentarios (12)</summary>

#### [@Jmvjr em 2026-09-08T22:25:28Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5592701537)

<pre>Início da implementação da geração de geometria mockada de pistas. Escopo confirmado: usar FastF1 apenas como fonte temporária, derivar uma polilinha normalizada para a amostra de dados, registrar proveniência e remover automaticamente cache/telemetria temporários; nenhuma alteração de visualização nesta issue e nenhum dado preexistente será apagado.</pre>

#### [@Jmvjr em 2026-09-08T22:38:26Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5592838768)

<pre>Geração de pistas concluída para o circuito do MVP (Interlagos, circuitId 18), sem integração visual. Entregue: gerador FastF1 parametrizável; transformação pura para polilinha fechada/normalizada; fixture track_points.csv com 240 pontos e distância acumulada; manifesto de proveniência/checksum; ADR 0003; documentação e testes. A aquisição usou FastF1 3.8.3, GP de São Paulo 2024, corrida, volta 67 de VER. Cache e telemetria ficaram em diretório temporário e foram removidos automaticamente; dados preexistentes não foram apagados e a saída recusa sobrescrita por padrão. Verificações: 56 testes OK, 13 testes Arcade ignorados por exigirem ARCADE_GUI_TEST=True; teste específico do artefato/checksum OK; git diff --check passa nas mudanças da implementação, com whitespace preexistente apenas no backlog gerado a partir de uma issue. Próximo passo, fora desta issue: consumir a polilinha na visualização da issue 13. Limitação registrada: a licença MIT cobre o software FastF1, não concede direitos adicionais sobre os dados upstream.</pre>

#### [@Jmvjr em 2026-09-08T22:38:27Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5592838925)

<pre>Critérios atendidos para a geração mockada do circuito do MVP; visualização permanece na issue 13.</pre>

#### [@Jmvjr em 2026-09-08T22:49:32Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5592950139)

<pre>Validação complementar concluída após o fechamento: foi adicionado `scripts/preview_track_geometry.py`, um visualizador Arcade de desenvolvimento que lê o `track_points.csv` versionado, preserva a proporção da geometria e marca o início/fim da volta. O comando `--check` valida o arquivo sem abrir janela.

Verificações: `python3 -m unittest -v` (59 testes, 13 pulados por dependerem da configuração gráfica), `uv run python scripts/preview_track_geometry.py --check` (240 pontos válidos) e inicialização real da janela/render loop Arcade sem erros. Este utilitário é apenas diagnóstico da geometria gerada e não implementa o fluxo de produto da issue #13.</pre>

#### [@Jmvjr em 2026-09-08T22:57:30Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5593019022)

<pre>Escopo reaberto por solicitação do usuário: ampliar a geração mockada de Interlagos para as 24 etapas do calendário de 2025. A implementação continuará restrita à geometria reduzida, sem reter cache ou telemetria bruta, com IDs associados ao Trotman v128 e validação individual dos artefatos. A issue #13 permanece fora do escopo; o visualizador será usado apenas como diagnóstico.</pre>

#### [@Jmvjr em 2026-09-08T23:12:46Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5593145842)

<pre>Ampliação para o calendário completo de 2025 concluída. Foram geradas 24 geometrias vinculadas aos `circuitId` do Trotman v128 em `tests/fixtures/trotman_v128_tracks_2025/track_points.csv`: 5.760 linhas de dados, 240 pontos por pista, polilinhas fechadas e escala uniforme. O manifesto agregado `data/sources/fastf1-tracks-2025.json` registra FastF1 3.8.3, sessão/piloto/volta/comprimento de cada etapa, transformação, retenção e checksum. O cache e a telemetria permaneceram em diretório temporário e foram removidos; a fixture anterior de Interlagos e os demais dados existentes foram preservados.

Também foram entregues gerador atômico em lote, escritor multi-circuito, seleção por `--circuit-id`/listagem no visualizador, testes e documentação/ADR atualizados. Verificações: 62 testes OK (13 GUI pulados pela configuração existente), 24 IDs e 5.760 pontos conferidos, checksum válido, proteção contra sobrescrita OK, `git diff --check` OK fora do backlog gerado e renderização real de uma pista agregada iniciada sem erro. A issue #13 continua fora deste escopo.</pre>

#### [@Jmvjr em 2026-09-08T23:18:56Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5593200341)

<pre>Escopo reaberto para completar a geometria necessária à simulação: derivar também o caminho do pit lane e um ponto de serviço representativo para cada uma das 24 pistas, mantendo as mesmas coordenadas normalizadas do traçado principal. A classificação posterior de curvas e retas é viável a partir da curvatura da polilinha, mas não faz parte desta etapa.</pre>

#### [@Jmvjr em 2026-09-08T23:32:19Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5593353177)

<pre>Complemento de pit lane concluído. A fixture `tests/fixtures/trotman_v128_tracks_2025/pit_lane_points.csv` contém 24 caminhos entrada→saída, 80 pontos por circuito (1.920 no total) e exatamente um `isServicePoint=true` por pista. As coordenadas usam a mesma transformação do traçado principal. O ponto de serviço é representativo, inferido de uma parada observada, e não identifica a garagem exata de cada equipe. Proveniência e checksum estão em `data/sources/fastf1-pit-lanes-2025.json`.

O visualizador agora sobrepõe automaticamente pit lane e ponto de serviço. Conforme solicitado, os três scripts FastF1 e o módulo auxiliar de geração foram removidos após a geração; ficaram apenas mocks, manifestos, visualizador e testes de integridade. Cache e telemetria temporários foram removidos. Verificações: 60 testes OK (13 GUI condicionais pulados), 24/1.920/24 contagens conferidas, checksum válido, `git diff --check` OK fora do backlog gerado e renderização Arcade real sem erro. Curvas e retas poderão ser classificadas posteriormente pela curvatura da polilinha, fora desta etapa.</pre>

#### [@Jmvjr em 2026-09-09T23:19:04Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5610073659)

<pre>Limpeza final solicitada: o visualizador temporário `scripts/preview_track_geometry.py` e seus testes específicos foram removidos. Os mocks de pista/pit lane, manifestos e testes de integridade permaneceram. `scripts/__init__.py` foi mantido porque também evita colisão com um pacote externo homônimo e é necessário ao teste de sincronização do backlog. Verificação: 55 testes OK, 13 GUI condicionais pulados; nenhuma referência ao visualizador permanece fora do histórico gerado.</pre>

#### [@guilherme-webster em 2026-09-11T22:17:09Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5641258700)

<pre>Refatorar para não consumir mais dados brutos, mas sim a interface do backend</pre>

#### [@guilherme-webster em 2026-09-11T22:35:07Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5641405159)

<pre>Tornar possível uma construção de partes da pista como objetos os quais são compostos de maneira a gerar uma pista final. Ademais, fazer com que seja viável saber o atrito na parte da pista, se é curva ou retam, etc para outras partes do simulador</pre>

#### [@Jmvjr em 2026-09-24T23:36:48Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/51#issuecomment-5824054131)

<pre>Atendendo ao pedido posterior do usuário, foi reconstruído um gerador offline versionável para as geometrias das 24 pistas de 2025: scripts/rebuild_fastf1_geometry.py. O código original não consta no histórico Git, então a reconstrução segue os eventos/proveniência dos manifestos e não promete checksums idênticos; por padrão usa cache temporário e exige diretório novo, sem alterar fixtures versionadas. ADR 0003, README e README da fixture foram atualizados; testes determinísticos cobrem resampling, escala compartilhada, serviço e proteção contra sobrescrita. Verificações: 201 testes OK (31 GUI pulados), Ruff/Black/diff check OK. Execução real da etapa 21 com FastF1 3.8.3 produziu 240 pontos de pista e 80 de pit lane; os 240 pontos de pista coincidiram linha a linha com a fixture, enquanto o pit lane diferiu levemente e o ponto de serviço ficou um índice adiante. Saída de verificação preservada em data/curated/geometry-rebuild-check-20260924 (ignorada pelo Git); CSVs versionados mantêm seus checksums. Próximo passo: revisar a diferença no pit lane antes de usar o gerador para substituir qualquer fixture. Issue mantida aberta; nenhum commit criado pelo agente.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-06T20:20:47Z — sub-issue adicionada: #119 por @DaviGabrielBC
- 2026-09-24T23:41:38Z — reaberta por @Jmvjr
- 2026-09-24T23:41:19Z — fechada por @Jmvjr
- 2026-09-11T22:17:46Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-09-11T22:17:46Z — responsavel removido: @Jmvjr por @Jmvjr
- 2026-09-11T22:16:30Z — reaberta por @guilherme-webster
- 2026-09-08T23:32:20Z — fechada por @Jmvjr
- 2026-09-08T23:18:55Z — reaberta por @Jmvjr
- 2026-09-08T23:12:47Z — fechada por @Jmvjr
- 2026-09-08T22:57:29Z — reaberta por @Jmvjr
- 2026-09-08T22:38:28Z — fechada por @Jmvjr
- 2026-09-08T22:18:09Z — label adicionada: História por @Jmvjr
- 2026-09-08T22:18:08Z — atribuida: @Jmvjr por @Jmvjr

</details>

### [#60 — Carros](https://github.com/guilherme-webster/mc857-o-projeto/issues/60)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#40 — Modelagem dos dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/40)
- **Sub-issues:** [#64 — Consumo do backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/64), [#65 — Modelagem posterior](https://github.com/guilherme-webster/mc857-o-projeto/issues/65), [#97 — Modelagem do combustível](https://github.com/guilherme-webster/mc857-o-projeto/issues/97)
- **Criada:** 2026-09-11T22:18:57Z
- **Atualizada:** 2026-09-11T22:36:33Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Fazer modelagem do carro</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@guilherme-webster em 2026-09-11T22:36:33Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/60#issuecomment-5641418011)

<pre>Levar em conta um modelo que leve em conta parâmetros como peso, cavalos, aerodinâmica do carro. Pode ser consumido via dados reais ou gerado via modelagem. Pensar em como levar isto em conta de maneira a gerar uma modelagem geral da corrida mais sofisticada. Documentar.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-22T23:41:51Z — sub-issue adicionada: #97 por @DaviGabrielBC
- 2026-09-11T22:27:12Z — sub-issue adicionada: #65 por @guilherme-webster
- 2026-09-11T22:26:46Z — sub-issue adicionada: #64 por @guilherme-webster
- 2026-09-11T22:25:05Z — label adicionada: História por @guilherme-webster
- 2026-09-11T22:25:01Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#61 — Pilotos](https://github.com/guilherme-webster/mc857-o-projeto/issues/61)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#40 — Modelagem dos dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/40)
- **Sub-issues:** [#66 — Consumir backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/66), [#67 — Modelagem pilotos](https://github.com/guilherme-webster/mc857-o-projeto/issues/67)
- **Criada:** 2026-09-11T22:20:19Z
- **Atualizada:** 2026-09-11T22:37:34Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@guilherme-webster em 2026-09-11T22:37:34Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/61#issuecomment-5641425322)

<pre>Levar em conta um modelo que leve em conta parâmetros como peso, altura, e ter perfilamento de pilotos, sejam pilotos reais ou personas. Pode ser consumido via dados reais (altura, peso, etc) ou gerado via modelagem (perfilamento). Pensar em como levar isto em conta de maneira a gerar uma modelagem geral da corrida mais sofisticada. Documentar.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:33:04Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:32:51Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-09-11T22:30:20Z — sub-issue adicionada: #67 por @guilherme-webster
- 2026-09-11T22:28:40Z — sub-issue adicionada: #66 por @guilherme-webster

</details>

### [#62 — Clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/62)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#40 — Modelagem dos dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/40)
- **Sub-issues:** [#68 — Consumir backend e frontend para modelar clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/68), [#69 — Modelagem clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/69)
- **Criada:** 2026-09-11T22:21:34Z
- **Atualizada:** 2026-09-11T22:39:11Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@guilherme-webster em 2026-09-11T22:39:11Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/62#issuecomment-5641437211)

<pre>Levar em conta um modelo que leve em conta parâmetros como chuva, neblina, etc. Pode ser consumido via dados reais ou gerado via modelagem. Pensar em como levar isto em conta de maneira a gerar uma modelagem geral da corrida mais sofisticada; por exemplo, como isto impactaria o atrito da pista, a visibilidade dos pilotos, isto afeta o perfil do piloto? Por exemplo, um piloto agressivo tende a ser mais conservador em chuvas ou vice versa? Um piloto que tende a  realizar ultrapassagens em curvas tende a ser menos insistente nisto quando temos chuva ou baixa visibilidade? Documentar.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:31:51Z — label adicionada: História por @guilherme-webster
- 2026-09-11T22:31:37Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-09-11T22:31:27Z — sub-issue adicionada: #69 por @guilherme-webster
- 2026-09-11T22:31:05Z — sub-issue adicionada: #68 por @guilherme-webster

</details>

### [#63 — Pneu](https://github.com/guilherme-webster/mc857-o-projeto/issues/63)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#40 — Modelagem dos dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/40)
- **Sub-issues:** [#104 — Desgate e combústivel dinâmicos](https://github.com/guilherme-webster/mc857-o-projeto/issues/104)
- **Criada:** 2026-09-11T22:22:10Z
- **Atualizada:** 2026-09-11T22:33:26Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-26T23:08:01Z — sub-issue adicionada: #104 por @Jmvjr
- 2026-09-11T22:33:26Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-09-11T22:33:26Z — label adicionada: Task por @guilherme-webster

</details>

### [#65 — Modelagem posterior](https://github.com/guilherme-webster/mc857-o-projeto/issues/65)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#60 — Carros](https://github.com/guilherme-webster/mc857-o-projeto/issues/60)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:27:10Z
- **Atualizada:** 2026-09-11T22:32:25Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>modelagem posterior dos dados com os dados pré tratados do backend</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:32:25Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:32:18Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#67 — Modelagem pilotos](https://github.com/guilherme-webster/mc857-o-projeto/issues/67)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#61 — Pilotos](https://github.com/guilherme-webster/mc857-o-projeto/issues/61)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:30:19Z
- **Atualizada:** 2026-10-03T20:35:50Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>modelagem posterior para os pilotos</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@guilherme-webster em 2026-10-03T20:35:31Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/67#issuecomment-5973245886)

<pre>## Andamento — modelagem heurística de pilotos e corrida (2026-10-03)

**Etapa:** implementação concluída na branch `67-modelagem-pilotos` (12 commits sobre a `develop`, ainda **não publicados** — o merge será feito pelo responsável). Plano em `docs/prds/modelagem-pilotos-heuristica.md`, decisão no ADR 0008 e valores atuais de todas as heurísticas em **`docs/modelagem-heuristica.md`**.

**Contexto:** por orientação do professor e decisão do grupo, perfis de pilotos, disputas, safety car/VSC/bandeiras e paradas passam a ser **heurísticos** (escolhidos e rotulados, não medidos). Os perfis nomeados são caracterizações fictícias, não afirmações sobre pessoas reais.

### O que foi feito
- **Integração** do motor calibrado da #40 (`40-modelagem-corrida-calibrada`, que não havia chegado à `develop`), com 7 conflitos resolvidos. Sem os recursos novos, o motor reproduz exatamente os resultados da branch original (verificado por hashes).
- **Atributos de piloto:** `aggression` e `composure` acrescentados aos arquétipos; 24 perfis fictícios nomeados do grid de 2024 em `configs/drivers/perfis-ficticios.json`.
- **Disputa** conforme os slides da #40: `p(passar) = P/(P+R)`, contato que retira um dos dois e bandeira azul.
- **Controle de prova:** SC, VSC, amarela, vermelha, relargada e acidente individual.
- **Paradas heurísticas:** decisão econômica, parada oportunista sob SC/VSC, regra de dois compostos.
- **`POST /catalog/grid/run`** passa a usar o motor detalhado (o motor simples continua com `engine=&quot;simple&quot;`).
- **Ajustes de realismo:** gestão de pneus amortecida no motor detalhado e volta de referência por circuito a partir do histórico (ex.: Mônaco 77,2 s em vez de 56 s).

### Verificações
- Suíte completa passando (eram 255 testes na `develop`; agora 490, 35 ignorados de GUI).
- Neutralidade do motor calibrado fixada por teste.
- Fluxo `POST /catalog/grid` → `POST /catalog/grid/run` testado pela API real: perfis aplicados, eventos de controle de prova e reprodutibilidade por semente.
- Frequência medida em 3 sementes × 200 corridas: 0,60–0,70 SC+VSC e 0,09–0,10 vermelha por corrida (referência de 2024: ~0,6 e ~1 a cada 6).
- Implementação das fatias 1 a 5 por agentes Codex, com revisão. Na revisão foram corrigidos um defeito da bandeira azul e um ajuste de frequência que valia para uma única semente.

### Próximos passos
- Merge da branch na `develop`. O colega da #40 deve revisar o merge da integração (commit `53c071e`), porque resolvi conflitos no código dele.
- Revisar ou substituir o ADR 0007, cujo contexto ficou desatualizado com a calibração da #40.
- Ajuste opcional: a pole ainda vence com frequência alta.

### Bloqueios e dependências
- A interface Arcade ainda não dispara nem reproduz a corrida volta a volta. O `track_view.py` anima em velocidade constante e não mostra ultrapassagens. O `scripts/race_report.py --html` da #40 pode servir de base para a tela.
- O clima (#68/#69) ainda não afeta o tempo de volta nem os incidentes.
- O modo `random` do grid sorteia pilotos de toda a história, então os perfis de 2024 só aparecem num grid `manual`.
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:33:16Z — label adicionada: Task por @guilherme-webster

</details>

### [#97 — Modelagem do combustível](https://github.com/guilherme-webster/mc857-o-projeto/issues/97)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @DaviGabrielBC
- **Responsaveis:** —
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** [#60 — Carros](https://github.com/guilherme-webster/mc857-o-projeto/issues/60)
- **Sub-issues:** —
- **Criada:** 2026-10-22T23:41:50Z
- **Atualizada:** 2026-11-13T22:22:30Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Fazer modelagem do consumo de combustível e implementar o reabastecimento (junto com troca de pneus)</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Jmvjr em 2026-11-13T22:22:30Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/97#issuecomment-6866381998)

<pre>Implementação de reabastecimento durante o serviço de pneus no motor 2D concluída em branch isolada e em revisão. Os 15 testes direcionados e o Ruff passaram; a suíte completa apresenta as mesmas cinco falhas existentes na develop. Permanecem limitações de planejamento inicial de carga e garantia de chegada aos boxes, que estão sendo avaliadas antes do fechamento.</pre>

</details>

### [#105 — Seed digitável e reprodução determinística do torneio](https://github.com/guilherme-webster/mc857-o-projeto/issues/105)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** enhancement
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-10-30T20:33:02Z
- **Atualizada:** 2026-10-30T21:55:48Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Permitir que o usuário informe uma seed para reproduzir deterministicamente uma simulação.

Hoje a seed existe só no grid: todas as etapas de um torneio usam a mesma seed e o mesmo fluxo `race`, a sequência automática de pistas usa `random.Random(nome_do_torneio)` e a interface não tem campo de seed.

Critérios:
- campo de seed do torneio e do grid na interface; vazio gera seed mostrada ao usuário;
- RNG por etapa derivado no núcleo a partir de `(tournament_seed, stage_index)`;
- `RaceSetupRequest` aceita seed e índice de etapa opcionais; ausentes, preserva o comportamento atual; a resposta devolve as seeds usadas;
- ordem automática das pistas depende da seed;
- testes: mesma seed reproduz, seeds diferentes mudam, etapas repetidas diferem.

Contrato: `docs/prds/controles-do-usuario-simulacao.md`, seção 3.1.</pre>

</details>

<details>
<summary>Comentarios (4)</summary>

#### [@guilherme-webster em 2026-10-30T20:35:17Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/105#issuecomment-6532927697)

<pre>Iniciado em 2026-10-30. Implementacao delegada a um agente Codex (gpt-5.6-sol) na branch `105-seed-deterministica`, a partir da `develop` (1200f6e, com o PRD `docs/prds/controles-do-usuario-simulacao.md`). Linha de base da suite na develop: 614 passam, 3 falhas pre-existentes em `tests/test_catalog_grid_run.py`.</pre>

#### [@guilherme-webster em 2026-10-30T20:47:22Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/105#issuecomment-6533136617)

<pre>Implementado na branch `105-seed-deterministica` (5 commits: correcao dos 3 testes quebrados de `test_catalog_grid_run.py`, derivacao SHA-256 versionada `tournament-stage-v1` de `(tournament_seed, stage_index)` no nucleo, `RaceSetupRequest.tournament_seed/stage_index` com seeds efetivas na resposta, campos de seed na configuracao do torneio e no grid, ordem automatica das pistas pela seed). Integrado na `develop` local (merge, sem push). Verificacao: suite completa 650 passed / 0 failed na develop integrada. Pendente: push/PR e inspecao visual dos campos novos (testes GUI de `test_parameters_view.py` tem 3 falhas pre-existentes, iguais na base 1200f6e).</pre>

#### [@guilherme-webster em 2026-10-30T21:31:43Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/105#issuecomment-6533890853)

<pre>Correção do registro anterior: a integração na `develop` local foi desfeita a pedido do usuário, que preferiu PRs. A entrega está no PR #111 (base `develop`). Ordem de merge: #111 (105) → #112 (106) → #113 (107) → #114 (108) → #115 (109); cada PR tem como base a branch anterior. Próximo passo: revisão e merge.</pre>

#### [@guilherme-webster em 2026-10-30T21:55:48Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/105#issuecomment-6534336495)

<pre>Mergeado na `develop` em 2026-10-30 (PRs #111–#115, na ordem). Suite na develop resultante (0668268): 672 passed, 0 failed. Pendente apenas a conferencia visual das telas no app rodando; a issue fica aberta ate essa conferencia e o merge na `main`.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-30T20:33:03Z — label adicionada: enhancement por @guilherme-webster

</details>

### [#108 — Ajustar o impacto da posição de largada (pole)](https://github.com/guilherme-webster/mc857-o-projeto/issues/108)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** enhancement
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-10-30T20:33:06Z
- **Atualizada:** 2026-11-12T21:18:24Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>A penalidade calibrada de 782,4 ms por posição deixa P20 ~15 s atrás antes da primeira volta; a pole venceu 21 de 40 corridas em Spa (`docs/modelagem-heuristica.md`). No motor 2D cada carro larga 10 m atrás do anterior, em vez de filas de dois.

Critérios:
- manter 782,4 ms como valor calibrado; acrescentar fator de atenuação rotulado `heuristic`, versionado e publicado em `assumptions`;
- escolher o fator por análise de sensibilidade com seeds fixas (alvo: pole vence ~40–45%);
- grid 2D em filas de dois, sem somar a penalidade temporal;
- documentar em `docs/modelagem-heuristica.md`.

Contrato: `docs/prds/controles-do-usuario-simulacao.md`, item 1 da seção 2.</pre>

</details>

<details>
<summary>Comentarios (5)</summary>

#### [@guilherme-webster em 2026-10-30T20:35:21Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/108#issuecomment-6532928838)

<pre>Iniciado em 2026-10-30. Implementacao delegada a um agente Codex (gpt-5.6-sol) na branch `108-impacto-largada`, a partir da `develop` (1200f6e, com o PRD `docs/prds/controles-do-usuario-simulacao.md`). Linha de base da suite na develop: 614 passam, 3 falhas pre-existentes em `tests/test_catalog_grid_run.py`.</pre>

#### [@guilherme-webster em 2026-10-30T20:47:26Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/108#issuecomment-6533137655)

<pre>Implementado na branch `108-impacto-largada` (3 commits), ainda NAO integrado. 782,4 ms segue calibrado; novo `grid_start_penalty_factor` heuristico em `data/parameters/grid-start-v1.json`; grid 2D em filas de dois. Analise (`scripts/analyze_grid_start_sensitivity.py`, 360 corridas/fator): fator 1,0 -&gt; pole vence 73,9%; 0,25 -&gt; 59,4%; 0,10 -&gt; 50,8%; 0,015 -&gt; 43,3%; 0 -&gt; 46,4%. Ponto em aberto: abaixo de ~0,1 as diferencas ficam dentro do ruido (EP ~2,6 p.p.), entao o alvo 40-45% so e atingido praticamente zerando a penalidade; o restante da vantagem da pole vem do modelo de ultrapassagem. Aguardando decisao do valor do fator.</pre>

#### [@guilherme-webster em 2026-10-30T21:31:47Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/108#issuecomment-6533891831)

<pre>Decisão do usuário: fator 0,10 (78,24 ms/posição, pole vence ~51% na análise); a causa restante foi para a #110. O grid 2D em filas de dois foi testado e revertido (`0072e31`): causava 34 abandonos por contato em 15 corridas de 2 voltas, contra 0 no grid escalonado. Entrega no PR #114. Ordem de merge: #111 (105) → #112 (106) → #113 (107) → #114 (108) → #115 (109); cada PR tem como base a branch anterior. Suíte: 657 passed, 0 failed.</pre>

#### [@guilherme-webster em 2026-10-30T21:55:51Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/108#issuecomment-6534337429)

<pre>Mergeado na `develop` em 2026-10-30 (PRs #111–#115, na ordem). Suite na develop resultante (0668268): 672 passed, 0 failed. Pendente apenas a conferencia visual das telas no app rodando; a issue fica aberta ate essa conferencia e o merge na `main`.</pre>

#### [@guilherme-webster em 2026-11-12T21:18:24Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/108#issuecomment-6836213430)

<pre>Material de largada arquivado na #152 (branch local 152-arquivar-grid-start, ainda sem push): TOBEDEFINED/grid_start.py, grid_start_parameters_json.py, grid-start-v1.json, analyze_grid_start_sensitivity.py, test_grid_start.py. Indice em TOBEDEFINED/README.md. Pode ser reaproveitado aqui.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-30T20:33:07Z — label adicionada: enhancement por @guilherme-webster

</details>

### [#109 — Salvar e reabrir/reexecutar torneio](https://github.com/guilherme-webster/mc857-o-projeto/issues/109)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** enhancement
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-10-30T20:33:07Z
- **Atualizada:** 2026-10-30T21:55:53Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Permitir salvar uma simulação para reabrir ou rodar o torneio de novo sem reprocessar tudo.

Critérios:
- formato JSON versionado fora do Git com grid congelado, seeds, motor, regras, etapas, proveniência e resultados;
- reabrir não chama `/catalog/grid/run`; reexecutar reproduz o resultado com o mesmo cenário;
- port no núcleo, adaptador JSON na borda, endpoints e tela de listar/abrir/reexecutar;
- ADR novo revisando o ADR 0006.

Depende das issues de seed, ordem do grid, voltas e largada. Contrato: `docs/prds/controles-do-usuario-simulacao.md`, seção 3.4.</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-10-30T21:31:48Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/109#issuecomment-6533892156)

<pre>Implementado na branch `109-salvar-torneio` (PR #115, empilhado sobre o #114): núcleo `application/saved_tournament.py`; rotas `/tournaments` (salvar, listar, abrir, `restore-grid`); botão Salvar torneio na tela de resultado e tela Torneios salvos com Abrir e Reexecutar; ADR 0013 atualizando o 0006. Verificação: pytest 672 passed, 0 failed; GUI 711 passed, com 3 falhas pré-existentes em `test_parameters_view.py`; teste de ponta a ponta de reexecução reproduzindo as classificações. Pendente: revisão, merge e conferência visual das telas novas no app rodando.</pre>

#### [@guilherme-webster em 2026-10-30T21:55:52Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/109#issuecomment-6534337763)

<pre>Mergeado na `develop` em 2026-10-30 (PRs #111–#115, na ordem). Suite na develop resultante (0668268): 672 passed, 0 failed. Pendente apenas a conferencia visual das telas no app rodando; a issue fica aberta ate essa conferencia e o merge na `main`.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-30T20:33:09Z — label adicionada: enhancement por @guilherme-webster

</details>

### [#110 — Revisar a dificuldade de ultrapassagem no motor detalhado](https://github.com/guilherme-webster/mc857-o-projeto/issues/110)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** enhancement
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-10-30T21:18:57Z
- **Atualizada:** 2026-10-30T21:18:57Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Achado da analise de sensibilidade da #108 (`scripts/analyze_grid_start_sensitivity.py`, 360 corridas por fator, 3 pistas, 3 grids sinteticos): mesmo zerando a penalidade temporal de largada, a pole ainda vence ~46% e um carro 500 ms/volta mais rapido saindo de P8 termina em media em ~5,3-5,9. Abaixo de um fator ~0,1 as diferencas ficam dentro do ruido (EP ~2,6 p.p.).

Decisao do usuario (2026-10-30): usar fator 0,10 na #108 e atacar a causa restante aqui.

Investigar: `resistance_scale`, limiares de disputa e bloqueio por volta em `domain/race_simulation.py` (ADR 0008, `docs/modelagem-heuristica.md`). Parametros sao heuristicos: rotular, versionar e medir com o mesmo script/sementes.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-30T21:18:58Z — label adicionada: enhancement por @guilherme-webster

</details>

### [#119 — Aderência física e estado dinâmico da pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/119)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @DaviGabrielBC
- **Responsaveis:** @DaviGabrielBC
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#51 — Pistas de corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/51)
- **Sub-issues:** —
- **Criada:** 2026-11-06T20:20:28Z
- **Atualizada:** 2026-11-06T20:30:28Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>## Contexto

A velocidade de curva do motor físico (ADR 0010, `speed_dynamics._target_speeds`) interpola entre 320 e 90 km/h pelo ângulo entre pontos consecutivos, normalizado pela curva mais fechada da própria pista. Não usa raio nem aderência:

- a curva mais fechada de qualquer pista vale 90 km/h (o grampo de Mônaco e a curva mais lenta de Monza ficam iguais);
- o ângulo depende do espaçamento dos 240 pontos (~14 m em Mônaco, ~29 m em Spa), não do raio;
- a volta física sai, em mediana, 0,89 da histórica (Mônaco 0,63, Montreal 0,74), e o motor detalhado a usa no lugar da referência quando há geometria;
- água, temperatura, borracha e pneu não têm onde atuar além de uma porcentagem no tempo de volta.

## Proposta

Velocidade de curva limitada pela aderência, `v = min(v_max, √(μ_ef · g · R))`, com `R` em metros e `μ_ef` incluindo um termo aerodinâmico (downforce cresce com a velocidade). O estado da pista entra como multiplicador de `μ`, que também é o ponto de entrada dos compostos na #120.

## Critérios

- [ ] raio em metros a partir da geometria (escala já calculada em `track_space`), suavizado, com raio mínimo para curvas sub-amostradas;
- [ ] `speed_ceiling` limitado por `μ` nos dois motores (detalhado e 2D), sem duplicar a curvatura;
- [ ] `μ` e termo aerodinâmico calibrados contra `reference-laps-v1.json`, com script reproduzível e parâmetros versionados; meta: mediana da razão física/histórica ≈ 1,00 e Mônaco dentro de ±10%;
- [ ] `physics_for` traduz a compostura em aproveitamento de `μ`, não mais em velocidade mínima de curva;
- [ ] estado da pista por volta: água (já existe em `weather.py`), temperatura de pista (padrão por circuito) e borracha acumulada (cresce com o tráfego, lavada pela chuva), rotulados `assumed`/`estimated`;
- [ ] secagem por tempo decorrido e temperatura, não por volta;
- [ ] o 2D usa o mesmo efeito de clima do detalhado (remover o `0.40` fixo em `race_simulation_2d.py`);
- [ ] testes de curvatura, calibração, estado da pista e reprodutibilidade por seed;
- [ ] ADR novo revisando o ADR 0010; atualizar `docs/modelagem-heuristica.md` e `docs/modelagem-clima.md`.

## Fora do escopo

Compostos de chuva, efeito da temperatura no pneu, estratégia de troca e efeitos em disputas (#120); desgaste dinâmico (#104).</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-06T20:20:29Z — label adicionada: Task por @DaviGabrielBC
- 2026-11-06T20:20:28Z — atribuida: @DaviGabrielBC por @DaviGabrielBC

</details>

### [#120 — Pneus de chuva e efeitos do clima na corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/120)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @DaviGabrielBC
- **Responsaveis:** @DaviGabrielBC
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-06T20:31:18Z
- **Atualizada:** 2026-11-06T20:31:18Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>## Contexto

Hoje a água na pista só soma até 40% ao tempo de volta (`assumed-weather-effect-v1`), igual para qualquer pneu, e todos seguem em compostos secos (`docs/modelagem-heuristica.md`, §9). O clima não afeta disputa, incidente, controle de prova nem estratégia.

Referência real (voltas FastF1 de 2023–2024; mediana da metade mais rápida das voltas com pneu de chuva ÷ voltas rápidas com slick na mesma corrida):

| Corrida | Intermediário | Chuva |
|---|---|---|
| Holanda 2023 | +11% | – |
| Mônaco 2023 | +16% | +25% |
| Inglaterra 2024 | +13% | – |
| Canadá 2024 | +14% | – |

Depende de #119 (aderência física e estado da pista). Coordenar com #104 (desgaste dinâmico).

## Critérios

- [ ] compostos INTERMEDIATE e WET com aderência em função da água; slick em pista molhada e pneu de chuva em pista seca penalizados; o ponto de troca slick ↔ intermediário ↔ chuva emerge do modelo, não de um limiar fixo;
- [ ] janela de temperatura por composto e aquecimento lento na volta de saída (efeito no desgaste combinado com #104);
- [ ] pneu de chuva superaquece e degrada rápido em pista secando;
- [ ] estratégia: cada piloto troca com limiar próprio, sorteado por seed a partir do perfil (como `FuelStrategyTraits`); regra dos dois compostos suspensa quando há pneus de chuva na corrida;
- [ ] risco de incidente, SC/VSC e disputa sensíveis à água e ao pneu; habilidade na chuva por piloto (comentário da #62);
- [ ] mesmo comportamento nos motores detalhado e 2D;
- [ ] interface: condição inicial da pista (molhada na largada), cores dos compostos INTERMEDIATE/WET, água e temperatura na tela da corrida;
- [ ] parâmetros versionados e rotulados: `estimated` só onde houver âncora com proveniência registrada, o resto `assumed`/`heuristic`;
- [ ] testes e documentação em `docs/modelagem-heuristica.md` e `docs/modelagem-clima.md`.

## Pendência

Registrar origem, versão e licença do export FastF1 de 2023–2024 usado como âncora (AGENTS.md, ADR 0005) antes de rotular qualquer parâmetro como `estimated`.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-06T20:31:20Z — label adicionada: Task por @DaviGabrielBC
- 2026-11-06T20:31:19Z — atribuida: @DaviGabrielBC por @DaviGabrielBC

</details>

### [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#137 — Melhorar Tela de corrida salvas](https://github.com/guilherme-webster/mc857-o-projeto/issues/137), [#135 — Carregar corridas salvas na tela inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/135), [#138 — Tela inicial geral](https://github.com/guilherme-webster/mc857-o-projeto/issues/138), [#142 — Botão resultado do torneio](https://github.com/guilherme-webster/mc857-o-projeto/issues/142), [#167 — Melhorar tela de atributos](https://github.com/guilherme-webster/mc857-o-projeto/issues/167), [#168 — Tela Pilotos e Grid: Não tem como selecionar o número de corredores](https://github.com/guilherme-webster/mc857-o-projeto/issues/168), [#169 — Tela de Simulação: Texto de contato](https://github.com/guilherme-webster/mc857-o-projeto/issues/169), [#172 — Tela Inicial: Caminho para telas de Clima e etc sumiu](https://github.com/guilherme-webster/mc857-o-projeto/issues/172), [#173 — Janela decomposição de velocidade: sobreposição de texto quando o nome é extenso](https://github.com/guilherme-webster/mc857-o-projeto/issues/173)
- **Criada:** 2026-11-08T20:23:47Z
- **Atualizada:** 2026-11-08T20:23:47Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T17:59:24Z — sub-issue adicionada: #173 por @Gustavo-Jun-Tsuji
- 2026-11-13T17:39:12Z — sub-issue adicionada: #172 por @Gustavo-Jun-Tsuji
- 2026-11-13T17:18:37Z — sub-issue adicionada: #169 por @Gustavo-Jun-Tsuji
- 2026-11-13T17:03:12Z — sub-issue adicionada: #168 por @Gustavo-Jun-Tsuji
- 2026-11-13T16:58:28Z — sub-issue adicionada: #167 por @Gustavo-Jun-Tsuji
- 2026-11-08T20:49:31Z — sub-issue adicionada: #142 por @Gustavo-Jun-Tsuji
- 2026-11-08T20:41:05Z — sub-issue adicionada: #138 por @Gustavo-Jun-Tsuji
- 2026-11-08T20:34:24Z — sub-issue adicionada: #135 por @Gustavo-Jun-Tsuji
- 2026-11-08T20:24:33Z — sub-issue adicionada: #137 por @Gustavo-Jun-Tsuji
- 2026-11-08T20:23:48Z — label adicionada: Épico por @Gustavo-Jun-Tsuji

</details>

### [#138 — Tela inicial geral](https://github.com/guilherme-webster/mc857-o-projeto/issues/138)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)
- **Sub-issues:** —
- **Criada:** 2026-11-08T20:41:03Z
- **Atualizada:** 2026-11-13T18:00:18Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>- Textos não alinhados
- Textos ultrapassando blocos
- Botão de &quot;voltar&quot; não funcional
- Botão de &quot;ajuda&quot;


&lt;img width=&quot;614&quot; height=&quot;113&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/0df17698-192b-4d40-b4e3-b21c399c7c43&quot; /&gt;

&lt;img width=&quot;665&quot; height=&quot;489&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/fc9c5ea5-4709-458d-925c-8bc5e9cd3a58&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T18:00:18Z — label adicionada: bug por @Gustavo-Jun-Tsuji
- 2026-11-13T18:00:18Z — label removida: Task por @Gustavo-Jun-Tsuji
- 2026-11-08T20:41:20Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#139 — Balanceamento das features](https://github.com/guilherme-webster/mc857-o-projeto/issues/139)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#170 — Bugs no Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/170)
- **Sub-issues:** [#140 — Combustível: Influência na % da velocidade aumenta e diminui sem o piloto passar por pitstop](https://github.com/guilherme-webster/mc857-o-projeto/issues/140), [#141 — Pneu: Influência na % da velocidade aumenta e diminui sem o piloto passar por pitstop](https://github.com/guilherme-webster/mc857-o-projeto/issues/141)
- **Criada:** 2026-11-08T20:41:54Z
- **Atualizada:** 2026-11-13T17:35:21Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>&lt;img width=&quot;164&quot; height=&quot;209&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/88799557-4ac8-44a9-b4f4-868b8204adf3&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T17:35:21Z — label adicionada: História por @Gustavo-Jun-Tsuji
- 2026-11-13T17:35:21Z — label removida: Épico por @Gustavo-Jun-Tsuji
- 2026-11-08T20:48:34Z — sub-issue adicionada: #141 por @Gustavo-Jun-Tsuji
- 2026-11-08T20:48:13Z — sub-issue adicionada: #140 por @Gustavo-Jun-Tsuji
- 2026-11-08T20:41:54Z — label adicionada: Épico por @Gustavo-Jun-Tsuji

</details>

### [#140 — Combustível: Influência na % da velocidade aumenta e diminui sem o piloto passar por pitstop](https://github.com/guilherme-webster/mc857-o-projeto/issues/140)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#139 — Balanceamento das features](https://github.com/guilherme-webster/mc857-o-projeto/issues/139)
- **Sub-issues:** —
- **Criada:** 2026-11-08T20:48:12Z
- **Atualizada:** 2026-11-13T22:22:30Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Obs: Não tenho certeza se esse era o comportamento desejado</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Jmvjr em 2026-11-13T22:22:30Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/140#issuecomment-6866381990)

<pre>Investigação: a porcentagem exibida representa a contribuição na velocidade local e varia com o limite do trecho e outras penalidades, mesmo quando a massa de combustível só diminui. Foram adicionados testes e documentação; vou submetê-los para revisão. A suíte completa apresenta cinco falhas preexistentes na develop.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:51:38Z — label removida: Task por @Gustavo-Jun-Tsuji
- 2026-11-08T20:51:16Z — label adicionada: bug por @Gustavo-Jun-Tsuji
- 2026-11-08T20:48:19Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#141 — Pneu: Influência na % da velocidade aumenta e diminui sem o piloto passar por pitstop](https://github.com/guilherme-webster/mc857-o-projeto/issues/141)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#139 — Balanceamento das features](https://github.com/guilherme-webster/mc857-o-projeto/issues/139)
- **Sub-issues:** —
- **Criada:** 2026-11-08T20:48:33Z
- **Atualizada:** 2026-11-08T20:51:28Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:51:28Z — label adicionada: bug por @Gustavo-Jun-Tsuji
- 2026-11-08T20:51:28Z — label removida: Task por @Gustavo-Jun-Tsuji
- 2026-11-08T20:48:45Z — label adicionada: Task por @Gustavo-Jun-Tsuji
- 2026-11-08T20:48:42Z — responsavel removido: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-11-08T20:48:37Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji

</details>

### [#142 — Botão resultado do torneio](https://github.com/guilherme-webster/mc857-o-projeto/issues/142)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)
- **Sub-issues:** —
- **Criada:** 2026-11-08T20:49:29Z
- **Atualizada:** 2026-11-13T18:00:22Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>&lt;img width=&quot;291&quot; height=&quot;35&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/7cd18454-3464-4b54-a982-62d60f69b8e2&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T18:00:22Z — label adicionada: bug por @Gustavo-Jun-Tsuji
- 2026-11-13T18:00:21Z — label removida: Task por @Gustavo-Jun-Tsuji
- 2026-11-10T20:43:23Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#155 — Saneamento pos-motor 2D: suite verde, CI e limpeza](https://github.com/guilherme-webster/mc857-o-projeto/issues/155)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:34Z
- **Atualizada:** 2026-11-12T21:58:13Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

Levantamento de 2026-11-12 sobre `develop` (`94e52ab`): a suite termina com 5
falhas e 21 erros em 637 testes, quase todos restos da remocao do motor por
volta, e nao ha CI de testes. Este epico ordena o saneamento em fatias pequenas.

## Ordem sugerida

**Suite verde**

- [x] #144
- [x] #145
- [x] #146
- [x] #147

**Barreira automatica**

- [x] #148
- [x] #149
- [x] #150

**Bugs (depois do teste de ponta a ponta)**

- [ ] #140 (confirmar antes se o comportamento e o desejado)
- [ ] #141

**Limpeza e interface**

- [x] #151
- [x] #152
- [x] #153
- [ ] #138
- [ ] #142
- [x] #154

## Fora deste epico

Dependem de decisao de modelagem do grupo: reabastecimento no 2D e
`pit_loss_ms` calibrado (`TODO(motor-2d)` em `race_simulation_2d.py:393`), peso
da pole (#108) e balanceamento (#139). Tambem nao esta previsto quebrar as
views grandes sem um problema concreto.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@guilherme-webster em 2026-11-12T21:35:40Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/155#issuecomment-6836581010)

<pre>## Andamento do epico (2026-11-12)

Todas as issues do epico criadas nesta rodada (#144-#154) tem branch local com commits e comentario de encerramento na propria issue. **Ainda sem push nem PR**, por isso nenhuma issue foi fechada.

| Issue | Branch | Base |
|---|---|---|
| #144 | `144-fuel-parameters-support` | develop |
| #145 | `145-portar-testes-motor-2d` | empilhada sobre a 144 |
| #146 | `146-remover-seletor-motor` | develop |
| #147 | `147-pit-lane-amostras-paradas` | develop |
| #148 | `148-ci-testes` | develop |
| #149 | `149-ruff` | integracao-saneamento |
| #150 | `150-teste-ponta-a-ponta-2d` | develop |
| #151 | `151-apagar-weather-view` | develop |
| #152 | `152-arquivar-grid-start` | 94e52ab |
| #153 | `153-progresso-reexecucao-torneio` | develop |
| #154 | `154-docs-alinhamento` | integracao-saneamento |

### Verificacao na branch local `integracao-saneamento` (todas mescladas)

- `uv run python -m unittest`: **732 testes, OK** (skipped=42, expected failures=2). Baseline em develop: 637 testes, 5 falhas, 21 erros.
- `uv run ruff check .`: limpo.
- Conflito #146 x #153 em `saved_tournaments.py` resolvido na integracao: a reexecucao usa o SSE e reenvia o `setup` salvo sem o `engine` legado.
- Com `ARCADE_GUI_TEST=1`: 4 falhas e 1 erro em `tests.test_parameters_view` (`test_visible_controls_add_track_and_confirm_sequence`, `test_large_window_draws_full_panels_and_maps_clicks`, `test_preview_click_still_opens_the_configurator`, `test_resizing_keeps_size_and_refits_both_configuration_screens`, `test_selects_another_backend_track_and_preserves_it_after_return`). Ja existiam em develop antes desta rodada; precisam de issue propria.

### Pendencias que dependem do grupo

- Status dos ADRs 0009 e 0015 (proposta na #154).
- `ruff format`: 76 arquivos seriam reformatados; adiado por causa de branches abertas (ver #149).
- Limitacoes do 2D registradas na #145/#154: nao reabastece nem faz lift-and-coast (2 `expectedFailure` em `test_race_playback`), nao declara a assumption de gestao de pneus, abandono solo vira `mechanical`, troca de pneu defasada uma volta em `speed_breakdown`.
- #140 e #141 nao se reproduziram no cenario do teste de ponta a ponta (#150) sem clima nem controle de prova; os helpers de `tests/race_invariants.py` estao prontos para os regressivos.
- Conferencia visual: painel de regras sem o seletor de motor (#146), aba Clima e tela de carregamento (#151), reexecucao com progresso (#153).
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:08:36Z — label adicionada: Épico por @guilherme-webster

</details>

### [#167 — Melhorar tela de atributos](https://github.com/guilherme-webster/mc857-o-projeto/issues/167)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)
- **Sub-issues:** —
- **Criada:** 2026-11-13T16:58:27Z
- **Atualizada:** 2026-11-13T18:00:26Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>&lt;img width=&quot;219&quot; height=&quot;667&quot; alt=&quot;image&quot; src=&quot;https://github.com/user-attachments/assets/7d49dc1b-5fc7-4e3e-839a-8fb9b6c36386&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T18:00:26Z — label adicionada: bug por @Gustavo-Jun-Tsuji
- 2026-11-13T18:00:26Z — label removida: Task por @Gustavo-Jun-Tsuji
- 2026-11-13T16:58:39Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#168 — Tela Pilotos e Grid: Não tem como selecionar o número de corredores](https://github.com/guilherme-webster/mc857-o-projeto/issues/168)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)
- **Sub-issues:** —
- **Criada:** 2026-11-13T17:03:11Z
- **Atualizada:** 2026-11-13T17:59:47Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T17:59:47Z — label adicionada: bug por @Gustavo-Jun-Tsuji
- 2026-11-13T17:59:47Z — label removida: Task por @Gustavo-Jun-Tsuji
- 2026-11-13T17:03:26Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#169 — Tela de Simulação: Texto de contato](https://github.com/guilherme-webster/mc857-o-projeto/issues/169)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)
- **Sub-issues:** —
- **Criada:** 2026-11-13T17:18:36Z
- **Atualizada:** 2026-11-13T17:59:56Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>- Texto Contato
- Sobreposição Time e Intervalo

&lt;img width=&quot;146&quot; height=&quot;30&quot; alt=&quot;image&quot; src=&quot;https://github.com/user-attachments/assets/86458486-2c96-4762-976f-9f257947aec4&quot; /&gt;

&lt;img width=&quot;294&quot; height=&quot;26&quot; alt=&quot;image&quot; src=&quot;https://github.com/user-attachments/assets/2286265a-f6ab-41ce-8041-780faeacdcca&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T17:59:56Z — label adicionada: bug por @Gustavo-Jun-Tsuji

</details>

### [#170 — Bugs no Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/170)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#139 — Balanceamento das features](https://github.com/guilherme-webster/mc857-o-projeto/issues/139), [#171 — Botão &quot;abortar simulação&quot; não aborta a simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/171), [#174 — Corrida atual com muitas colisões](https://github.com/guilherme-webster/mc857-o-projeto/issues/174), [#175 — Efeito &quot;sanfona&quot; nos carros durante a simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/175)
- **Criada:** 2026-11-13T17:34:34Z
- **Atualizada:** 2026-11-13T22:22:31Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Jmvjr em 2026-11-13T22:22:31Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/170#issuecomment-6866382308)

<pre>Investigação: foram reproduzidos e corrigidos três casos de validação (overrides duplicados, corrida salva inválida e etapa vazia). Os testes direcionados passaram; a suíte completa apresenta cinco falhas já existentes na develop. Vou abrir um PR para revisão. A issue principal permanece aberta enquanto suas subissues não estiverem concluídas.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T18:01:50Z — sub-issue adicionada: #175 por @Gustavo-Jun-Tsuji
- 2026-11-13T18:01:21Z — sub-issue adicionada: #174 por @Gustavo-Jun-Tsuji
- 2026-11-13T17:37:29Z — sub-issue adicionada: #171 por @Gustavo-Jun-Tsuji
- 2026-11-13T17:35:41Z — sub-issue adicionada: #139 por @Gustavo-Jun-Tsuji
- 2026-11-13T17:35:07Z — renomeada: “Bugs Backend” → “Bugs no Backend” por @Gustavo-Jun-Tsuji
- 2026-11-13T17:34:40Z — label adicionada: Épico por @Gustavo-Jun-Tsuji

</details>

### [#171 — Botão &quot;abortar simulação&quot; não aborta a simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/171)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug, Task
- **Milestone:** —
- **Issue-pai:** [#170 — Bugs no Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/170)
- **Sub-issues:** —
- **Criada:** 2026-11-13T17:37:27Z
- **Atualizada:** 2026-11-13T18:00:39Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Mesmo &quot;abortando a simulação&quot; ela aparece em corridas salvas após um tempo

&lt;img width=&quot;136&quot; height=&quot;46&quot; alt=&quot;image&quot; src=&quot;https://github.com/user-attachments/assets/bff4e4b1-3a8f-4979-9527-6fe398a50e51&quot; /&gt;

</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T18:00:39Z — label adicionada: bug por @Gustavo-Jun-Tsuji
- 2026-11-13T17:37:38Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#172 — Tela Inicial: Caminho para telas de Clima e etc sumiu](https://github.com/guilherme-webster/mc857-o-projeto/issues/172)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)
- **Sub-issues:** —
- **Criada:** 2026-11-13T17:39:11Z
- **Atualizada:** 2026-11-13T18:00:07Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>&lt;img width=&quot;1280&quot; height=&quot;800&quot; alt=&quot;image&quot; src=&quot;https://github.com/user-attachments/assets/62e3cf36-1464-4312-b1e0-29e5d37d3193&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T18:00:07Z — label adicionada: bug por @Gustavo-Jun-Tsuji
- 2026-11-13T18:00:07Z — label removida: Task por @Gustavo-Jun-Tsuji
- 2026-11-13T17:39:13Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#173 — Janela decomposição de velocidade: sobreposição de texto quando o nome é extenso](https://github.com/guilherme-webster/mc857-o-projeto/issues/173)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)
- **Sub-issues:** —
- **Criada:** 2026-11-13T17:59:22Z
- **Atualizada:** 2026-11-13T18:00:12Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>&lt;img width=&quot;156&quot; height=&quot;130&quot; alt=&quot;image&quot; src=&quot;https://github.com/user-attachments/assets/8fa10a45-46e2-45d8-b503-0fcf1faae80c&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T18:00:12Z — label adicionada: bug por @Gustavo-Jun-Tsuji

</details>

### [#174 — Corrida atual com muitas colisões](https://github.com/guilherme-webster/mc857-o-projeto/issues/174)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#170 — Bugs no Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/170)
- **Sub-issues:** —
- **Criada:** 2026-11-13T18:01:19Z
- **Atualizada:** 2026-11-13T18:54:43Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T18:54:43Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-11-13T18:01:20Z — label adicionada: bug por @Gustavo-Jun-Tsuji

</details>

### [#175 — Efeito &quot;sanfona&quot; nos carros durante a simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/175)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** [#170 — Bugs no Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/170)
- **Sub-issues:** —
- **Criada:** 2026-11-13T18:01:48Z
- **Atualizada:** 2026-11-13T18:01:48Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T18:01:50Z — label adicionada: bug por @Gustavo-Jun-Tsuji

</details>

## Issues fechadas

### [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#1 — Customização da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/1)
- **Sub-issues:** [#12 — Exibição de parâmetros](https://github.com/guilherme-webster/mc857-o-projeto/issues/12), [#13 — Exibição de pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/13), [#14 — Simulações pré-definidas](https://github.com/guilherme-webster/mc857-o-projeto/issues/14), [#26 — Tela inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/26), [#29 — Tela de configuração de clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/29), [#86 — Otimização de UI\\UX](https://github.com/guilherme-webster/mc857-o-projeto/issues/86)
- **Criada:** 2026-08-28T23:03:16Z
- **Atualizada:** 2026-11-13T17:34:08Z
- **Fechada:** 2026-11-13T17:34:08Z

<details>
<summary>Descricao original</summary>

<pre>Nessa tela o usuário poderá visualizar dados e poder alterá-los</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@Jmvjr em 2026-09-24T22:57:04Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/2#issuecomment-5823587802)

<pre>Etapa da interface: tela inicial de torneio ampliada para 1672x900, com texto renderizado em resolução nativa; segunda tela de configuração por corrida criada conforme referência, com aba Sessão funcional, resumo de pista/clima, navegação para o editor de Clima existente e sem Assistências. Pista, Regras e Carros permanecem placeholders por pedido do usuário. Sessão e clima são incluídos no plano salvo. Verificações: 192 testes passaram na suíte padrão (28 GUI pulados), 28 testes GUI passaram com ARCADE_GUI_TEST=True, Ruff e git diff --check passaram. Próximos passos: implementar as abas adiadas e integrar confirmação do Arcade à execução/acompanhamento da simulação. Limitação atual: configurações de etapas com pista repetida ainda são compartilhadas por ID de circuito. Nenhum commit criado pelo agente.</pre>

#### [@Jmvjr em 2026-09-24T23:05:46Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/2#issuecomment-5823695300)

<pre>Correção do fluxo da segunda tela: a aba Clima agora edita a programação por volta dentro da própria RaceConfigurationView, sem abrir WeatherConfigurationView nem redimensionar a janela. Preservados seleção de condição, pintura inclusiva por arraste, campos de intervalo, aplicação e resumo paginado; salvar/avançar persiste o clima e cancelar descarta alterações não salvas. README atualizado. Verificações: suíte geral 194 testes OK (30 GUI pulados), 31 testes GUI OK, Ruff/Black/diff check OK; captura da aba em 1672x900 inspecionada. Próximo passo: abas Pista/Regras/Carros e integração da confirmação com a simulação. Nenhum commit criado pelo agente.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T17:34:09Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-26T00:29:21Z — sub-issue adicionada: #86 por @Jmvjr
- 2026-09-01T21:06:20Z — sub-issue adicionada: #29 por @Jmvjr
- 2026-09-01T15:38:19Z — sub-issue adicionada: #26 por @Jmvjr
- 2026-08-28T23:19:05Z — sub-issue adicionada: #14 por @Jmvjr
- 2026-08-28T23:16:53Z — sub-issue adicionada: #13 por @Jmvjr
- 2026-08-28T23:15:25Z — sub-issue adicionada: #12 por @Jmvjr
- 2026-08-28T23:03:17Z — label adicionada: História por @Jmvjr

</details>

### [#4 — Inserção de dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/4)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#1 — Customização da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/1)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:04:14Z
- **Atualizada:** 2026-11-08T20:27:37Z
- **Fechada:** 2026-11-08T20:27:18Z

<details>
<summary>Descricao original</summary>

<pre>Configuração do usuário deve puxar dados do backend e passar para a etapa de simulação</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:27:38Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-11-08T20:27:18Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:04:40Z — label adicionada: História por @Jmvjr

</details>

### [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @ViniciusFCoracin, @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#5 — Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/5)
- **Sub-issues:** [#16 — Exibição da pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/16), [#18 — Exibição das classificações](https://github.com/guilherme-webster/mc857-o-projeto/issues/18), [#19 — Controle da velocidade da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/19), [#21 — Exibição de condições da corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/21), [#101 — Simular entrada, parada e saída dos carros pela pit lane no motor 2D](https://github.com/guilherme-webster/mc857-o-projeto/issues/101)
- **Criada:** 2026-08-28T23:06:03Z
- **Atualizada:** 2026-11-13T22:09:50Z
- **Fechada:** 2026-11-13T22:09:50Z

<details>
<summary>Descricao original</summary>

<pre>O usuário deve conseguir visualizar a pista, os carros e as posições. </pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-13T22:09:50Z — fechada por @Gustavo-Jun-Tsuji
- 2026-10-26T22:30:35Z — sub-issue adicionada: #101 por @Jmvjr
- 2026-10-16T20:24:01Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-08-28T23:39:04Z — atribuida: @ViniciusFCoracin por @ViniciusFCoracin
- 2026-08-28T23:36:19Z — sub-issue adicionada: #21 por @ViniciusFCoracin
- 2026-08-28T23:34:45Z — sub-issue adicionada: #19 por @ViniciusFCoracin
- 2026-08-28T23:34:10Z — sub-issue adicionada: #18 por @ViniciusFCoracin
- 2026-08-28T23:33:20Z — sub-issue adicionada: #16 por @ViniciusFCoracin
- 2026-08-28T23:06:44Z — label adicionada: História por @Jmvjr

</details>

### [#7 — Tela de loading](https://github.com/guilherme-webster/mc857-o-projeto/issues/7)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#5 — Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/5)
- **Sub-issues:** [#17 — Processamento da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/17), [#20 — Exibição do progresso da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/20)
- **Criada:** 2026-08-28T23:06:16Z
- **Atualizada:** 2026-11-08T20:17:35Z
- **Fechada:** 2026-11-08T20:17:35Z

<details>
<summary>Descricao original</summary>

<pre>Usuário deve ser capaz de ver tela de loading enquanto simulação é computada.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:17:35Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:35:58Z — sub-issue adicionada: #20 por @DaviGabrielBC
- 2026-08-28T23:34:04Z — sub-issue adicionada: #17 por @DaviGabrielBC
- 2026-08-28T23:06:17Z — label adicionada: História por @Jmvjr

</details>

### [#8 — Rodar Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/8)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#5 — Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/5)
- **Sub-issues:** [#70 — Consumir dados da modelagem](https://github.com/guilherme-webster/mc857-o-projeto/issues/70), [#71 — Executar simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/71), [#102 — Simular entrada, parada e saída dos carros pela pit lane no motor 2D](https://github.com/guilherme-webster/mc857-o-projeto/issues/102)
- **Criada:** 2026-08-28T23:06:39Z
- **Atualizada:** 2026-11-08T20:50:50Z
- **Fechada:** 2026-11-08T20:50:50Z

<details>
<summary>Descricao original</summary>

<pre>A simulação em si deve ser computada de maneira a exibir algo para o usuário. Isto deve ser feito antes de qualquer exibição em si para o usuário, de maneira a evitar problemas de performance.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:50:50Z — fechada por @Gustavo-Jun-Tsuji
- 2026-10-26T22:56:43Z — sub-issue adicionada: #102 por @Jmvjr
- 2026-09-11T23:54:52Z — sub-issue adicionada: #71 por @guilherme-webster
- 2026-09-11T23:54:09Z — sub-issue adicionada: #70 por @guilherme-webster
- 2026-08-28T23:06:41Z — label adicionada: História por @Jmvjr

</details>

### [#9 — Resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/9)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#10 — Tela de resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/10), [#11 — Armazenamento de dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/11)
- **Criada:** 2026-08-28T23:07:00Z
- **Atualizada:** 2026-11-08T20:26:42Z
- **Fechada:** 2026-11-08T20:26:42Z

<details>
<summary>Descricao original</summary>

<pre>O usuário deve conseguir ver a tela com os resultados finais da simulação.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:26:44Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:08:16Z — sub-issue adicionada: #11 por @Jmvjr
- 2026-08-28T23:07:16Z — sub-issue adicionada: #10 por @Jmvjr
- 2026-08-28T23:07:01Z — label adicionada: Épico por @Jmvjr

</details>

### [#10 — Tela de resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/10)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#9 — Resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/9)
- **Sub-issues:** [#23 — Resultado final da corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/23)
- **Criada:** 2026-08-28T23:07:15Z
- **Atualizada:** 2026-11-08T20:26:53Z
- **Fechada:** 2026-11-08T20:26:53Z

<details>
<summary>Descricao original</summary>

<pre>O usuário deve conseguir visualizar os resultados da simulação requisitada</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:26:53Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:48:15Z — sub-issue adicionada: #23 por @DaviGabrielBC
- 2026-08-28T23:07:17Z — label adicionada: História por @Jmvjr

</details>

### [#11 — Armazenamento de dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/11)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#9 — Resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/9)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:08:15Z
- **Atualizada:** 2026-11-08T20:26:38Z
- **Fechada:** 2026-11-08T20:26:38Z

<details>
<summary>Descricao original</summary>

<pre>É necessário armazenar internamente os resultados e processá-los para que os resultados possam chegar ao usuário.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:26:38Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:08:29Z — label adicionada: História por @Jmvjr

</details>

### [#12 — Exibição de parâmetros](https://github.com/guilherme-webster/mc857-o-projeto/issues/12)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:15:24Z
- **Atualizada:** 2026-11-08T20:21:08Z
- **Fechada:** 2026-11-08T20:21:08Z

<details>
<summary>Descricao original</summary>

<pre>O usuário deve conseguir visualizar e alterar aos parâmetros configuráveis da corrida.</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Gustavo-Jun-Tsuji em 2026-11-08T20:21:01Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/12#issuecomment-6726620937)

<pre>Versão inicial implementada, fechando por agora

&lt;img width=&quot;1280&quot; height=&quot;800&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/1962075d-9ed4-4c87-9a52-d3c26d7781d1&quot; /&gt;

&lt;img width=&quot;187&quot; height=&quot;248&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/e367ef79-34bf-4fa6-8b8c-cdc535aa0319&quot; /&gt;
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:21:08Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:38:49Z — atribuida: @Jmvjr por @Jmvjr
- 2026-08-28T23:15:25Z — label adicionada: Task por @Jmvjr

</details>

### [#13 — Exibição de pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/13)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:16:51Z
- **Atualizada:** 2026-09-24T23:42:03Z
- **Fechada:** 2026-09-24T23:42:03Z

<details>
<summary>Descricao original</summary>

<pre>O usuário deve poder visualizar a pista selecionada</pre>

</details>

<details>
<summary>Comentarios (8)</summary>

#### [@Jmvjr em 2026-09-18T22:14:07Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/13#issuecomment-5736826058)

<pre>Andamento: a branch `43-criar-endpoints` foi integrada por fast-forward na branch local `13-exibição-de-pista`, trazendo os endpoints do backend, incluindo `GET /simulation/tracks` e `GET /simulation/track/{circuit_id}`. Verificação executada: `uv run python -m unittest -v` — 164 testes aprovados e 13 ignorados (configurações de GUI Arcade). Próximo passo: consumir o endpoint de geometria na visualização da pista. A branch local ainda precisa ser publicada com push.</pre>

#### [@Jmvjr em 2026-09-18T22:28:41Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/13#issuecomment-5736949407)

<pre>Implementação concluída localmente na branch `13-exibição-de-pista`: `GET /simulation/track/{circuit_id}` agora inclui `pit_lane_points` com `path_fraction` e `is_service_point`; a seção **Pista** da tela de configuração carrega a geometria em segundo plano e desenha traçado, pit lane e ponto de serviço com uma transformação conjunta que preserva alinhamento e proporção. Também há estados de carregamento/erro quando o backend não responde. Verificações: `uv run python -m unittest -v` — 168 testes aprovados, 14 testes Arcade ignorados por padrão; `ARCADE_GUI_TEST=True uv run python -m unittest -v tests.test_parameters_view` — 14 testes gráficos aprovados; `ruff check` e `git diff --check` aprovados. Foi feita revisão visual com a geometria real de Interlagos. Próximo passo: revisão humana, commit e push; nenhum commit foi criado pelo agente.</pre>

#### [@Jmvjr em 2026-09-18T22:33:21Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/13#issuecomment-5736988506)

<pre>Correção adicional de execução no Fedora: os bind mounts do `docker-compose.yaml` receberam rótulo SELinux `:Z`, eliminando `cannot open /app/entrypoint.sh: Permission denied`. A fixture versionada de geometria foi montada como `/data/geometry:ro,Z`, pois o backend procurava esse diretório mas apenas `./data` estava montado. Validação real em container: `/` respondeu `online`; `GET /simulation/track/18` retornou `circuit:18`, 240 pontos de pista, 80 pontos de pit lane e 1 ponto de serviço. O container foi deixado ativo para uso pelo frontend.</pre>

#### [@Jmvjr em 2026-09-18T22:35:43Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/13#issuecomment-5737007587)

<pre>Corrigida a corrida de inicialização mostrada na tela: `run.py` não usa mais `sleep(1)`; agora consulta `http://localhost:8000/` e só abre o Arcade depois de receber HTTP 200, com timeout e encerramento limpo em caso de falha. Foram adicionados testes para retry e esgotamento das tentativas. Verificações: suíte completa com 170 testes aprovados (14 gráficos ignorados por padrão), Ruff/Black/diff check aprovados e validação real após `docker compose up`: a espera confirmou o backend pronto e `/simulation/track/18` retornou 240 pontos de pista e 80 de pit lane.</pre>

#### [@Jmvjr em 2026-09-18T22:38:28Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/13#issuecomment-5737028569)

<pre>Diagnóstico final da falha exibida no Arcade: após criar a janela, o `urllib.request.urlopen` inicializava seu opener e um contexto HTTPS dentro da thread de carregamento, causando `ssl.SSLError` no ambiente Fedora/Pyglet mesmo para `http://localhost`. `frontend/arcade/track_client.py` agora constrói o opener na thread principal; a mensagem de erro também informa a classe da exceção. Validação ponta a ponta: backend Docker ativo + janela Arcade invisível + carregamento assíncrono real resultaram em `Geometria da pista carregada`, sem erro. Suíte: 170 testes aprovados; 14/14 testes gráficos aprovados; Ruff, Black e diff check aprovados. É necessário reiniciar o processo Arcade para carregar o cliente corrigido.</pre>

#### [@Jmvjr em 2026-09-18T22:45:13Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/13#issuecomment-5737077983)

<pre>Visualizador enriquecido apenas com dados existentes, sem nova aquisição: pista em camadas (sombra/borda/asfalto), setas derivadas da ordem dos pontos, linha de largada/chegada perpendicular ao primeiro segmento, entrada e saída derivadas dos extremos do pit lane, ponto de serviço, legenda completa, distância da amostra e contagem de pontos. A interface distingue ID canônico Trotman v128 de geometria reduzida FastF1 2025 e não apresenta a distância observada como extensão oficial. Zebras, largura variável e áreas de escape não foram inferidas. Revisão visual feita com Interlagos real. Verificações: 171 testes aprovados (14 gráficos ignorados por padrão), 14/14 testes Arcade aprovados, Ruff/Black/diff check aprovados.</pre>

#### [@Jmvjr em 2026-09-18T22:48:13Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/13#issuecomment-5737099621)

<pre>Ajuste visual após revisão: as camadas da pista foram afinadas (contorno total 23→18 px), a pit lane foi reduzida (11→8 px), o risco interno do asfalto foi removido e a linha de largada acompanhou a nova largura. Isso aumenta a separação visual na reta dos boxes sem alterar coordenadas. Nova captura revisada; 14/14 testes Arcade, testes de transformação, Ruff e diff check aprovados.</pre>

#### [@Jmvjr em 2026-09-24T22:12:58Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/13#issuecomment-5823094639)

<pre>Implementação local da seleção de pistas: a tela inicial consulta GET /simulation/tracks, permite percorrer o catálogo e abre a configuração com o circuito escolhido; o tópico Pista carrega sua geometria via GET /simulation/track/{circuit_id}. Tratados carregamento e erro da API. Verificações: 175 testes unitários passaram (18 testes de GUI omitidos por padrão); 18 testes de GUI passaram com ARCADE_GUI_TEST=True; Ruff e git diff --check passaram; integração manual com backend confirmou 24 pistas e prévia de Monaco. Próximo passo: revisão/commit pelo responsável e integração da branch. Limitação: a seleção de geometria não amplia o suporte do motor de simulação a todos os circuitos.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-24T23:42:03Z — fechada por @Jmvjr
- 2026-08-28T23:38:43Z — atribuida: @Jmvjr por @Jmvjr
- 2026-08-28T23:16:53Z — label adicionada: Task por @Jmvjr

</details>

### [#14 — Simulações pré-definidas](https://github.com/guilherme-webster/mc857-o-projeto/issues/14)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:19:03Z
- **Atualizada:** 2026-11-08T20:21:26Z
- **Fechada:** 2026-11-08T20:21:26Z

<details>
<summary>Descricao original</summary>

<pre>O usuário deve poder escolher simulações já existentes como base</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:21:26Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:38:53Z — atribuida: @Jmvjr por @Jmvjr
- 2026-08-28T23:19:04Z — label adicionada: Task por @Jmvjr

</details>

### [#15 — Simulação puxa dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/15)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#5 — Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/5)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:24:35Z
- **Atualizada:** 2026-11-08T20:21:44Z
- **Fechada:** 2026-11-08T20:21:44Z

<details>
<summary>Descricao original</summary>

<pre>Antes de rodar, a simulação deve puxar dados do backend de maneira coerente com a configuração setada para o usuário. Então, estes dados são consumidos pelo motor do sistema que irá executar a simulação.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:21:44Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:32:08Z — label adicionada: História por @guilherme-webster

</details>

### [#16 — Exibição da pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/16)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:33:19Z
- **Atualizada:** 2026-09-05T00:04:58Z
- **Fechada:** 2026-09-05T00:04:58Z

<details>
<summary>Descricao original</summary>

<pre>A tela de simulação deve exibir uma visão aérea em duas dimensões da pista, assim como a posição dos carros.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-05T00:04:59Z — fechada por @ViniciusFCoracin
- 2026-08-28T23:36:37Z — label adicionada: Task por @ViniciusFCoracin

</details>

### [#17 — Processamento da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/17)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @DaviGabrielBC
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#7 — Tela de loading](https://github.com/guilherme-webster/mc857-o-projeto/issues/7)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:34:03Z
- **Atualizada:** 2026-11-08T20:17:23Z
- **Fechada:** 2026-11-08T20:17:23Z

<details>
<summary>Descricao original</summary>

<pre>A simulação deve ser processada do seu início ao fim no back-end.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:17:24Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:36:11Z — label adicionada: Task por @DaviGabrielBC

</details>

### [#18 — Exibição das classificações](https://github.com/guilherme-webster/mc857-o-projeto/issues/18)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:34:08Z
- **Atualizada:** 2026-11-08T20:29:56Z
- **Fechada:** 2026-11-08T20:29:56Z

<details>
<summary>Descricao original</summary>

<pre>A tela de simulação deve exibir a classificação dos pilotos de forma dinâmica ao longo da corrida.</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Gustavo-Jun-Tsuji em 2026-11-08T20:29:56Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/18#issuecomment-6726720060)

<pre>&lt;img width=&quot;304&quot; height=&quot;247&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/c5181fca-c6ac-4705-9d8b-b400590c2619&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:29:56Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:36:48Z — label adicionada: Task por @ViniciusFCoracin

</details>

### [#19 — Controle da velocidade da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/19)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:34:43Z
- **Atualizada:** 2026-11-08T20:30:21Z
- **Fechada:** 2026-11-08T20:30:21Z

<details>
<summary>Descricao original</summary>

<pre>O usuário deve ser capaz de controlar a velocidade com que a simulação é exibida na tela (exemplo: exibir a corrida em tempo real, exibir em 10x, 50x etc).</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Gustavo-Jun-Tsuji em 2026-11-08T20:30:21Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/19#issuecomment-6726724724)

<pre>&lt;img width=&quot;258&quot; height=&quot;24&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/19bdf41b-cdd2-4ba4-96b2-81df808a1283&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:30:22Z — fechada por @Gustavo-Jun-Tsuji
- 2026-11-08T20:30:07Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-08-28T23:36:55Z — label adicionada: Task por @ViniciusFCoracin

</details>

### [#20 — Exibição do progresso da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/20)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @DaviGabrielBC
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#7 — Tela de loading](https://github.com/guilherme-webster/mc857-o-projeto/issues/7)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:35:56Z
- **Atualizada:** 2026-11-08T20:16:57Z
- **Fechada:** 2026-11-08T20:16:36Z

<details>
<summary>Descricao original</summary>

<pre>O usuário será informado do progresso da simulação, sabendo quão próxima está de concluida.</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Gustavo-Jun-Tsuji em 2026-11-08T20:16:36Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/20#issuecomment-6726571098)

<pre>&lt;img width=&quot;365&quot; height=&quot;63&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/b28234ae-d2d6-4af2-8c76-2628d78a539d&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:16:57Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-11-08T20:16:37Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:35:57Z — label adicionada: Task por @DaviGabrielBC

</details>

### [#21 — Exibição de condições da corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/21)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:36:18Z
- **Atualizada:** 2026-11-08T20:33:33Z
- **Fechada:** 2026-11-08T20:33:33Z

<details>
<summary>Descricao original</summary>

<pre>A tela de simulação deve exibir as condições da corrida, como por exemplo o clima, o tempo de corrida, se há bandeira amarela/vermelha etc).</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Gustavo-Jun-Tsuji em 2026-11-08T20:33:33Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/21#issuecomment-6726761203)

<pre>&lt;img width=&quot;798&quot; height=&quot;776&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/af2f7cf6-7566-413c-9b87-cc9ce5ae6f00&quot; /&gt;

Bandeiras verde, vermelha, amarela, saafety, etc</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:33:33Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:37:02Z — label adicionada: Task por @ViniciusFCoracin

</details>

### [#22 — teste](https://github.com/guilherme-webster/mc857-o-projeto/issues/22)

- **Estado:** fechada
- **Motivo do estado:** not_planned
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:45:38Z
- **Atualizada:** 2026-10-23T21:58:53Z
- **Fechada:** 2026-10-23T21:58:53Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-23T21:58:53Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-04T22:15:18Z — responsavel removido: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-09-03T23:50:41Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji

</details>

### [#23 — Resultado final da corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/23)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @DaviGabrielBC
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#10 — Tela de resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/10)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:48:14Z
- **Atualizada:** 2026-11-08T20:22:53Z
- **Fechada:** 2026-11-08T20:22:53Z

<details>
<summary>Descricao original</summary>

<pre>Na tela de resultados, o usuário poderá visualizar uma tabela contendo o ranque e os tempos finais de todos os jogadores</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Gustavo-Jun-Tsuji em 2026-11-08T20:22:53Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/23#issuecomment-6726641829)

<pre>&lt;img width=&quot;572&quot; height=&quot;343&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/11fd4770-02e7-4d39-b2d0-56c6f926f71d&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:22:53Z — fechada por @Gustavo-Jun-Tsuji
- 2026-08-28T23:48:16Z — label adicionada: Task por @DaviGabrielBC

</details>

### [#25 — Implementar CI](https://github.com/guilherme-webster/mc857-o-projeto/issues/25)

- **Estado:** fechada
- **Motivo do estado:** duplicate
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-08-30T07:58:27Z
- **Atualizada:** 2026-09-04T00:42:15Z
- **Fechada:** 2026-09-04T00:42:15Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-04T00:42:15Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-01T22:12:34Z — label adicionada: Task por @guilherme-webster

</details>

### [#26 — Tela inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/26)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)
- **Sub-issues:** —
- **Criada:** 2026-09-01T15:38:17Z
- **Atualizada:** 2026-09-01T19:32:45Z
- **Fechada:** 2026-09-01T19:32:45Z

<details>
<summary>Descricao original</summary>

<pre>Implementação de um layout básico para a tela de configuração</pre>

</details>

<details>
<summary>Comentarios (4)</summary>

#### [@Jmvjr em 2026-09-01T15:49:21Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/26#issuecomment-5496598985)

<pre>Etapa concluida: implementado o wireframe Python da tela inicial de configuracao, independente de Arcade, com paineis para dados de referencia, parametros de cenario e acoes. Os dados historicos da corrida 1141 permanecem somente leitura; voltas, clima e semente sao editaveis. Verificacoes: python3 -m unittest -v tests.test_configuration_layout (3 testes aprovados); python3 -m compileall -q frontend/arcade; git diff --check. A suite completa executou 21 testes, com 1 erro preexistente: tests.test_sync_github_backlog importa o pacote scripts de /home/jmvjr/Documentos/unicamp/GeoBench/spada. Proximo passo: uma ParametersView em Arcade deve renderizar este layout e conectar os controles ao contrato HTTP/JSON quando o backend existir.</pre>

#### [@Jmvjr em 2026-09-01T17:44:30Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/26#issuecomment-5498000115)

<pre>Implementacao atualizada para Arcade 3.3.3: criada uma ParametersView executavel com uma unica arcade.Window, campos UIInputText, seletores UIDropdown e botoes UIFlatButton. A geometria e o estado/validacao permanecem separados da View, permitindo testes sem colocar regras de simulacao na interface. Dados historicos do ETL sao somente leitura; voltas, clima e semente sao editaveis. O ponto de entrada e python -m frontend.arcade. Verificacoes: suite completa em ambiente temporario com Arcade 3.3.3 e ARCADE_GUI_TEST=True, 26 testes aprovados; compileall aprovado; git diff --check aprovado; janela 1280x720 renderizada e inspecionada. Proximo passo: revisar, criar commit e conectar o callback de inicio ao contrato HTTP/JSON quando o backend estiver disponivel. A issue permanece aberta ate a mudanca ser revisada e versionada.</pre>

#### [@Jmvjr em 2026-09-01T17:57:47Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/26#issuecomment-5498151771)

<pre>Adicionado requirements.txt com arcade==3.3.3 e atualizado o README para instalacao com python -m venv e pip, sem depender de Pipenv. Verificacoes: pip install --dry-run -r requirements.txt e git diff --check aprovados.</pre>

#### [@Jmvjr em 2026-09-01T18:07:05Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/26#issuecomment-5498261871)

<pre>Layout ajustado sem commit: os campos de clima inicial e semente foram removidos da ParametersView e substituidos por Configurar clima por volta. O botao abre uma segunda Arcade View, onde o usuario aplica Seco, Chuva leve ou Chuva intensa a intervalos inclusivos de voltas, visualiza o cronograma consolidado e salva ou cancela. O estado armazena uma condicao por volta e preserva/trunca o cronograma quando a quantidade de voltas muda. Verificacoes: 31 testes aprovados com Arcade 3.3.3 e ARCADE_GUI_TEST=True; compileall e git diff --check aprovados; as duas telas 1280x720 foram renderizadas e inspecionadas. Nenhum commit, git add ou push foi executado.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-01T19:32:46Z — fechada por @Jmvjr
- 2026-09-01T15:38:27Z — atribuida: @Jmvjr por @Jmvjr

</details>

### [#29 — Tela de configuração de clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/29)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)
- **Sub-issues:** —
- **Criada:** 2026-09-01T21:06:18Z
- **Atualizada:** 2026-09-02T15:13:07Z
- **Fechada:** 2026-09-02T15:13:07Z

<details>
<summary>Descricao original</summary>

<pre>O usuário deve poder escolher o clima da pista em cada uma das voltas</pre>

</details>

<details>
<summary>Comentarios (10)</summary>

#### [@Jmvjr em 2026-09-01T21:10:18Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5500479689)

<pre>Etapa concluida localmente, sem commit: adicionada uma timeline colorida na WeatherConfigurationView. Seco usa amarelo, chuva leve azul claro e chuva intensa azul escuro; cada faixa ocupa largura proporcional ao numero inclusivo de voltas configuradas. A barra atualiza imediatamente ao aplicar um intervalo e inclui legenda e marcacoes de volta inicial, intermediaria e final. Verificacoes: 32 testes aprovados com Arcade 3.3.3 e ARCADE_GUI_TEST=True; compileall e git diff --check aprovados; tela 1280x720 renderizada e inspecionada. Proximo passo: revisao e commit pelo responsavel. Nenhum git add, commit ou push foi executado.</pre>

#### [@Jmvjr em 2026-09-01T21:15:30Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5500537398)

<pre>Andamento da tela de configuração de clima:

- adicionada seleção da condição por uma paleta de cores;
- adicionada pintura de um intervalo diretamente na timeline por clique e arraste, com prévia durante o gesto;
- o intervalo é inclusivo, aceita arraste nos dois sentidos e limita solturas além das extremidades à primeira/última volta;
- os campos numéricos continuam disponíveis e são sincronizados com a seleção feita pelo mouse;
- adicionados testes da seleção da paleta, pintura reversa e limite da timeline.

Verificações executadas: `ARCADE_GUI_TEST=True .venv/bin/python -m unittest -v` (35 testes, todos passando), `compileall` e `git diff --check`. Também foi feita inspeção visual da tela Arcade.

Próximo passo: revisão manual da interação e decisão sobre eventuais ajustes visuais. Nenhum commit, push ou staging foi realizado pelo agente.</pre>

#### [@Jmvjr em 2026-09-01T21:32:09Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5500718784)

<pre>Atualização da implementação:

- reformulado o visual da tela de clima conforme o mockup enviado;
- adicionados cabeçalho, menu lateral, cards escuros, timeline com divisores, legenda e resumo por intervalo;
- adicionada a logo fornecida em `frontend/arcade/assets/f1-logo.png`, com o arquivo original preservado como `f1-original.png`;
- removida a opção Nublado, pois ela não faz parte das condições suportadas atualmente pelo projeto;
- mantida a configuração rápida por clique na condição e arraste na timeline.

Verificações: 35 testes passando, `compileall`, `git diff --check` e inspeção visual headless no Arcade. Nenhum commit, push ou staging foi realizado pelo agente.</pre>

#### [@Jmvjr em 2026-09-01T21:36:24Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5500765119)

<pre>Refinamento visual concluído:

- botões de ação agora possuem borda permanente e estados próprios para normal, hover e pressionado;
- campos numéricos receberam fundo e bordas coerentes com o dashboard;
- botões da paleta ganharam borda, realce superior e destaque mais claro da condição selecionada;
- timeline recebeu moldura externa, realce interno e divisores com contorno, marca central e número da volta.

Verificações: 35 testes passando, `compileall`, `git diff --check` e inspeção visual headless no Arcade. Nenhum commit, push ou staging foi realizado pelo agente.</pre>

#### [@Jmvjr em 2026-09-01T21:40:18Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5500805608)

<pre>Correção visual das bordas concluída:

- substituídos os botões quadrados do `UIFlatButton` por botões desenhados com cantos realmente arredondados e áreas clicáveis equivalentes;
- adicionados estados hover e pressionado aos novos botões;
- paleta climática, campos, painéis e cards de resumo agora usam cantos arredondados;
- timeline recebeu extremidades arredondadas e moldura curva, preservando segmentos e divisores.

Verificações: 35 testes passando, `compileall`, `git diff --check` e inspeção visual no Arcade. Nenhum commit, push ou staging foi realizado pelo agente.</pre>

#### [@Jmvjr em 2026-09-01T21:43:13Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5500836227)

<pre>Ajustes finais de alinhamento concluídos:

- timeline ampliada para ocupar toda a largura interna do card;
- adicionada borda arredondada contínua e mais visível ao redor da barra;
- valores dos campos de volta inicial/final centralizados horizontal e verticalmente;
- rótulos desses campos centralizados sobre os respectivos inputs;
- marcações e divisores foram reposicionados proporcionalmente à nova largura.

Verificações: 35 testes passando, `compileall`, `git diff --check` e inspeção visual no Arcade. Nenhum commit, push ou staging foi realizado pelo agente.</pre>

#### [@Jmvjr em 2026-09-01T21:45:36Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5500860145)

<pre>Correção adicional da timeline concluída:

- removidas as abas/quinas causadas pelo preenchimento retangular atravessando as extremidades arredondadas;
- moldura e conteúdo agora são desenhados em camadas separadas;
- segmentos inicial e final recebem pontas arredondadas próprias dentro da borda;
- divisores continuam alinhados proporcionalmente ao espaço interno da barra;
- validado visualmente também o caso de intervalo único (voltas 1–69: Seco).

Verificações: 35 testes passando, `compileall`, `git diff --check` e inspeção visual no Arcade. Nenhum commit, push ou staging foi realizado pelo agente.</pre>

#### [@Jmvjr em 2026-09-01T22:00:57Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5501016952)

<pre>Ícones climáticos integrados:

- adicionados ícones Lucide para Seco (`sun`), Chuva leve (`cloud-drizzle`) e Chuva intensa (`cloud-rain-wind`);
- SVGs-fonte e PNGs transparentes 64x64 armazenados em `frontend/arcade/assets/icons/`;
- ícones aplicados à paleta, legenda da timeline e cards de resumo;
- licença ISC e origem registradas em `LUCIDE_LICENSE.txt`;
- adicionado teste garantindo que todas as condições suportadas possuem asset.

Verificações: 36 testes passando, `compileall`, `git diff --check` e inspeção visual no Arcade. Nenhum commit, push ou staging foi realizado pelo agente.</pre>

#### [@Jmvjr em 2026-09-01T22:04:02Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5501048818)

<pre>Resumo por intervalo sem corte concluído:

- removido o limite fixo de quatro intervalos (`ranges()[:4]`);
- até oito intervalos são exibidos em uma grade compacta de duas linhas;
- cenários com mais de oito intervalos recebem paginação anterior/próxima, mantendo todos acessíveis;
- validado visualmente com os sete intervalos do exemplo enviado;
- adicionado teste cobrindo dez intervalos e a navegação para a segunda página.

Verificações: 37 testes passando, `compileall`, `git diff --check` e inspeção visual no Arcade. Nenhum commit, push ou staging foi realizado pelo agente.</pre>

#### [@Jmvjr em 2026-09-02T15:08:26Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/29#issuecomment-5511748928)

<pre>Fluxo de configuração reorganizado conforme nova direção:

- a tela inicial agora seleciona a pista da simulação;
- como o ADR 0002 limita o MVP a um circuito, a seleção apresenta apenas o Autódromo José Carlos Pace com os dados atuais;
- o antigo editor climático passou a ser `TrackConfigurationView`, uma tela geral de configuração da pista;
- o menu lateral alterna entre Sessão, Pista, Clima, Assistências, Regras e Carros;
- Clima mantém toda a edição funcional existente; Pista exibe os dados disponíveis; tópicos ainda fora do MVP mostram seu estado sem inventar parâmetros;
- o nome `WeatherConfigurationView` foi preservado como alias temporário para compatibilidade;
- adicionados testes para abrir a pista selecionada e navegar pelos tópicos.

Verificações: 39 testes passando, `compileall`, inspeção visual das telas e `git diff --check` nos arquivos-fonte. O espelho gerado `docs/backlog.md` contém um espaço final proveniente do texto de uma issue e não foi editado manualmente. Nenhum commit, push ou staging foi realizado pelo agente.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-02T15:13:07Z — fechada por @Jmvjr
- 2026-09-01T21:06:20Z — label adicionada: Task por @Jmvjr
- 2026-09-01T21:06:18Z — atribuida: @Jmvjr por @Jmvjr

</details>

### [#30 — implementar race data repository](https://github.com/guilherme-webster/mc857-o-projeto/issues/30)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#24 — ETL inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/24)
- **Sub-issues:** —
- **Criada:** 2026-09-01T22:35:17Z
- **Atualizada:** 2026-09-11T22:14:41Z
- **Fechada:** 2026-09-11T22:14:41Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@guilherme-webster em 2026-09-02T19:25:45Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/30#issuecomment-5515116567)

<pre>Implementacao local concluida, ainda sem commit: adicionada a porta `RaceDataRepository` com `get_race(race_id) -&gt; RaceData`, acompanhada de `RaceDataRepositoryError` e `RaceDataNotFoundError`. O contrato usa apenas identificadores e entidades canonicas e nao expoe SQLite aos consumidores. A implementacao concreta e seus testes estao descritos na issue #31. A issue permanece aberta ate revisao e versionamento.
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:14:41Z — fechada por @guilherme-webster
- 2026-09-02T19:30:08Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-09-02T19:19:25Z — label adicionada: Task por @guilherme-webster

</details>

### [#31 — implementar SQLiteRaceDataRepository](https://github.com/guilherme-webster/mc857-o-projeto/issues/31)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#24 — ETL inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/24)
- **Sub-issues:** —
- **Criada:** 2026-09-01T22:35:52Z
- **Atualizada:** 2026-09-11T22:14:54Z
- **Fechada:** 2026-09-11T22:14:54Z

<details>
<summary>Descricao original</summary>

<pre>componente que serve apenas para leitura</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@guilherme-webster em 2026-09-02T19:25:46Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/31#issuecomment-5515116877)

<pre>Implementacao local concluida, ainda sem commit: criado `SQLiteRaceDataRepository` para reconstruir o agregado `RaceData` completo a partir do SQLite curado.

Comportamentos cobertos:
- conexao em modo somente leitura, sem criar banco ausente;
- leitura de metadados, circuito, corrida, pilotos, equipes, inscricoes, voltas, pit stops e IDs de origem;
- ordem deterministica de participantes, voltas e paradas;
- erros de SQLite traduzidos para a porta da aplicacao;
- distincao entre corrida inexistente e falha de armazenamento;
- rejeicao de schema invalido, chaves estrangeiras quebradas e rastreabilidade ausente;
- fechamento explicito das conexoes do reader e do writer.

Verificacoes: 25 testes aprovados com `ResourceWarning` habilitado, Ruff aprovado, `git diff --check` aprovado e leitura do SQLite real confirmada com 20 pilotos, 10 equipes, 20 inscricoes, 1.133 voltas, 35 pit stops e 32 IDs de origem. A issue permanece aberta ate revisao e versionamento.
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:14:54Z — fechada por @guilherme-webster
- 2026-09-02T19:30:03Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-09-02T19:19:30Z — label adicionada: Task por @guilherme-webster

</details>

### [#34 — Implementar ETL para criação da pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/34)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#24 — ETL inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/24)
- **Sub-issues:** —
- **Criada:** 2026-09-02T19:19:08Z
- **Atualizada:** 2026-09-11T22:14:03Z
- **Fechada:** 2026-09-11T22:14:03Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-09-11T20:24:10Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/34#issuecomment-5640207905)

<pre>Etapa implementada localmente: ETL de geometria usando os CSVs de pista e pit lane da issue #51, conforme o ADR 0003 e a escolha confirmada nesta sessão.

Entrega:
- Adapter para os CSVs reduzidos, validando checksums, manifestos, vínculo entre os caminhos, circuito, contagens e comprimento;
- DTO, Factory e domínio canônicos com coordenadas X/Y sem unidade, distância acumulada em metros, progresso do pit lane e ponto de serviço representativo;
- ingestão opcional por --geometry-dir no ETL da corrida, unindo pelo circuit_id e persistindo track_points, pit_lane_points e geometry_sources no mesmo SQLite;
- SQLiteTrackGeometryRepository para consumo das duas polilinhas e proveniência, com leitura somente leitura e revalidação;
- relatório com contagens e aviso para diferença entre o ano do mock (2025) e o da corrida;
- documentação de execução e contrato de consumo em README.MD e docs/fluxo-etl.md.

Verificações:
- 74 testes executados: 61 passaram, 13 testes gráficos pulados pela configuração existente; 19 testes novos;
- validação dos 24 circuitos da fixture;
- ZIP real Trotman v128, corrida 1141: 20 pilotos, 1.133 voltas, 35 pit stops, 240 pontos de pista, 80 de pit lane; leitura canônica pelo repository OK;
- Ruff check/format e git diff --check OK;
- execução com Python 3.14; sintaxe dos arquivos alterados validada para Python 3.12, mas esse runtime não está disponível no ambiente. A suíte ainda emite um ResourceWarning de conexão SQLite não fechada em testes preexistentes.

Localização: branch local gwc-etl-geometria, worktree ../mc857-etl-geometria, baseada em 95b63e4 (origin/51-pistas-de-corrida), que contém a main 338f38f. A gwc-etl original foi preservada. Nenhum commit ou push foi realizado.

Próximo passo: revisar e versionar o diff, integrar com o trabalho da issue #51 via develop e conectar os consumidores de modelagem/apresentação. Os commits de RaceDataRepository da gwc-etl original continuam separados; esta entrega fornece o repository específico de geometria. A issue permanece aberta enquanto a entrega está local.

Limites: ingestão de uma corrida/circuito por execução, mock de 2025 sem interpolação de carros, classificação de curvas/retas ou novos endpoints. O pit lane mantém a escala da pista; X/Y não são geolocalização nem metros. FastF1/Pandas não são dependências de execução. A divergência preexistente FastAPI na main versus Django no plano/ADR não foi alterada por esta entrega.
</pre>

#### [@guilherme-webster em 2026-09-11T21:02:05Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/34#issuecomment-5640593651)

<pre>Preparação do diff da branch local gwc-etl-geometria para revisão: .gitignore agora ignora *.egg-info/ e /build/. Os dois arquivos .pyc anteriormente versionados foram retirados apenas do índice; arquivos locais preservados e conferidos por SHA-256.

Verificações: git check-ignore confirma as exclusões; git diff --check e git diff --cached --check passaram. Testes não foram reexecutados porque esta etapa altera somente o rastreamento de artefatos gerados. Nenhum commit criado. Próximo passo: separar o commit de higiene do commit funcional de geometria e da documentação. A implementação segue local, com revisão e integração pendentes.
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:14:03Z — fechada por @guilherme-webster
- 2026-09-02T19:30:12Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-09-02T19:19:47Z — label adicionada: Task por @guilherme-webster

</details>

### [#36 — Setup de Infraestrutura &amp; DevOps](https://github.com/guilherme-webster/mc857-o-projeto/issues/36)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#37 — Docker - conteinerizar a aplicação](https://github.com/guilherme-webster/mc857-o-projeto/issues/37), [#38 — Configurar CI](https://github.com/guilherme-webster/mc857-o-projeto/issues/38), [#39 — Padronização e Qualidade de Código](https://github.com/guilherme-webster/mc857-o-projeto/issues/39)
- **Criada:** 2026-09-04T00:07:17Z
- **Atualizada:** 2026-11-08T20:44:32Z
- **Fechada:** 2026-11-08T20:44:32Z

<details>
<summary>Descricao original</summary>

<pre>Configurar a infraestrutura do projeto, garantindo um ambiente de desenvolvimento padronizado entre os integrantes do grupo e a automação de validações de código.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:44:33Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-04T00:16:18Z — sub-issue adicionada: #39 por @Gustavo-Jun-Tsuji
- 2026-09-04T00:15:03Z — sub-issue adicionada: #38 por @Gustavo-Jun-Tsuji
- 2026-09-04T00:12:30Z — sub-issue adicionada: #37 por @Gustavo-Jun-Tsuji
- 2026-09-04T00:07:17Z — label adicionada: Épico por @Gustavo-Jun-Tsuji

</details>

### [#37 — Docker - conteinerizar a aplicação](https://github.com/guilherme-webster/mc857-o-projeto/issues/37)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#36 — Setup de Infraestrutura &amp; DevOps](https://github.com/guilherme-webster/mc857-o-projeto/issues/36)
- **Sub-issues:** —
- **Criada:** 2026-09-04T00:12:28Z
- **Atualizada:** 2026-11-08T20:43:43Z
- **Fechada:** 2026-11-08T20:43:43Z

<details>
<summary>Descricao original</summary>

<pre>conteinerizar o backend e o frontend com Docker para padronizar o ambiente de desenvolvimento e execução.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:43:44Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-04T22:14:50Z — label adicionada: História por @Gustavo-Jun-Tsuji
- 2026-09-04T00:39:57Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji

</details>

### [#38 — Configurar CI](https://github.com/guilherme-webster/mc857-o-projeto/issues/38)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#36 — Setup de Infraestrutura &amp; DevOps](https://github.com/guilherme-webster/mc857-o-projeto/issues/36)
- **Sub-issues:** —
- **Criada:** 2026-09-04T00:15:02Z
- **Atualizada:** 2026-11-08T20:43:52Z
- **Fechada:** 2026-11-08T20:43:52Z

<details>
<summary>Descricao original</summary>

<pre>configurar um pipeline de Integração Contínua (CI) para validar builds, linters e testes 

Esse ticket será um constante lembrete de implementar boas práticas de CI</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:43:53Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-04T22:14:57Z — label adicionada: História por @Gustavo-Jun-Tsuji
- 2026-09-04T00:42:15Z — marcada como duplicada por @Gustavo-Jun-Tsuji
- 2026-09-04T00:17:34Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji

</details>

### [#39 — Padronização e Qualidade de Código](https://github.com/guilherme-webster/mc857-o-projeto/issues/39)

- **Estado:** fechada
- **Motivo do estado:** not_planned
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#36 — Setup de Infraestrutura &amp; DevOps](https://github.com/guilherme-webster/mc857-o-projeto/issues/36)
- **Sub-issues:** —
- **Criada:** 2026-09-04T00:16:17Z
- **Atualizada:** 2026-11-08T20:44:06Z
- **Fechada:** 2026-11-08T20:44:06Z

<details>
<summary>Descricao original</summary>

<pre>padronizar o estilo de código e validações pré-commit para evitar inconsistências e erros de sintaxe no repositório</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:44:06Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-04T22:15:04Z — label adicionada: História por @Gustavo-Jun-Tsuji

</details>

### [#41 — Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/41)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#43 — Criar endpoints](https://github.com/guilherme-webster/mc857-o-projeto/issues/43), [#47 — Carregar trotman no container](https://github.com/guilherme-webster/mc857-o-projeto/issues/47), [#54 — Carregar dados de pista no container](https://github.com/guilherme-webster/mc857-o-projeto/issues/54)
- **Criada:** 2026-09-04T23:02:55Z
- **Atualizada:** 2026-11-08T20:50:09Z
- **Fechada:** 2026-11-08T20:50:09Z

<details>
<summary>Descricao original</summary>

<pre>Endpoints, integração com o front, fornecer arquivo de reprodução da simulação</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:50:09Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-11T20:24:01Z — sub-issue adicionada: #54 por @guilherme-webster
- 2026-09-05T19:56:27Z — sub-issue adicionada: #47 por @Gustavo-Jun-Tsuji
- 2026-09-05T16:38:00Z — sub-issue adicionada: #43 por @Gustavo-Jun-Tsuji
- 2026-09-04T23:02:57Z — label adicionada: Épico por @Gustavo-Jun-Tsuji

</details>

### [#43 — Criar endpoints](https://github.com/guilherme-webster/mc857-o-projeto/issues/43)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#41 — Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/41)
- **Sub-issues:** —
- **Criada:** 2026-09-05T16:37:59Z
- **Atualizada:** 2026-11-08T20:28:55Z
- **Fechada:** 2026-09-24T18:52:46Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:28:55Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-09-24T18:52:46Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-05T16:38:09Z — label adicionada: História por @Gustavo-Jun-Tsuji

</details>

### [#47 — Carregar trotman no container](https://github.com/guilherme-webster/mc857-o-projeto/issues/47)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#41 — Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/41)
- **Sub-issues:** —
- **Criada:** 2026-09-05T19:56:26Z
- **Atualizada:** 2026-11-08T20:28:52Z
- **Fechada:** 2026-10-08T16:22:58Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:28:52Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-10-08T16:22:58Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-05T19:56:38Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#53 — implementar etl para dados de pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/53)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#24 — ETL inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/24)
- **Sub-issues:** —
- **Criada:** 2026-09-11T20:22:52Z
- **Atualizada:** 2026-09-11T22:13:36Z
- **Fechada:** 2026-09-11T22:13:36Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:13:36Z — fechada por @guilherme-webster
- 2026-09-11T20:22:54Z — label adicionada: História por @guilherme-webster
- 2026-09-11T20:22:52Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#54 — Carregar dados de pista no container](https://github.com/guilherme-webster/mc857-o-projeto/issues/54)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** [#41 — Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/41)
- **Sub-issues:** —
- **Criada:** 2026-09-11T20:24:00Z
- **Atualizada:** 2026-11-08T20:28:43Z
- **Fechada:** 2026-10-08T16:23:01Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:28:43Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-10-08T16:23:02Z — fechada por @Gustavo-Jun-Tsuji

</details>

### [#64 — Consumo do backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/64)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#60 — Carros](https://github.com/guilherme-webster/mc857-o-projeto/issues/60)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:26:45Z
- **Atualizada:** 2026-11-08T20:51:51Z
- **Fechada:** 2026-11-08T20:51:51Z

<details>
<summary>Descricao original</summary>

<pre>consumir interface do backend para modelagem posterior dos carros</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:51:51Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-11T22:26:46Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:26:45Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#66 — Consumir backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/66)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#61 — Pilotos](https://github.com/guilherme-webster/mc857-o-projeto/issues/61)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:28:39Z
- **Atualizada:** 2026-11-08T20:37:32Z
- **Fechada:** 2026-11-08T20:37:32Z

<details>
<summary>Descricao original</summary>

<pre>Consumir dados do backend para termos dados de pilotos</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:37:32Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-11T22:32:45Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:32:40Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#68 — Consumir backend e frontend para modelar clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/68)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @Jmvjr, @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#62 — Clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/62)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:31:03Z
- **Atualizada:** 2026-10-26T23:07:15Z
- **Fechada:** 2026-10-26T23:07:15Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-26T23:07:15Z — fechada por @Jmvjr
- 2026-10-02T22:38:41Z — atribuida: @Jmvjr por @Jmvjr
- 2026-10-02T22:38:33Z — renomeada: “Consumir backend para modelar clima” → “Consumir backend e frontend para modelar clima” por @Jmvjr
- 2026-09-11T22:31:05Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:31:04Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#69 — Modelagem clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/69)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @Jmvjr, @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#62 — Clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/62)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:31:25Z
- **Atualizada:** 2026-10-02T22:36:38Z
- **Fechada:** 2026-10-02T22:36:38Z

<details>
<summary>Descricao original</summary>

<pre>modelagem posterior para os clima</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-02T22:36:39Z — fechada por @Jmvjr
- 2026-10-02T22:13:51Z — atribuida: @Jmvjr por @Jmvjr
- 2026-09-11T22:33:46Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:33:42Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#70 — Consumir dados da modelagem](https://github.com/guilherme-webster/mc857-o-projeto/issues/70)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#8 — Rodar Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/8)
- **Sub-issues:** —
- **Criada:** 2026-09-11T23:54:08Z
- **Atualizada:** 2026-11-08T20:50:47Z
- **Fechada:** 2026-11-08T20:50:47Z

<details>
<summary>Descricao original</summary>

<pre>Consome dados da etapa de modelagem para rodar a simulação em si</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:50:47Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-11T23:54:57Z — label adicionada: História por @guilherme-webster

</details>

### [#71 — Executar simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/71)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#8 — Rodar Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/8)
- **Sub-issues:** —
- **Criada:** 2026-09-11T23:54:51Z
- **Atualizada:** 2026-11-08T20:50:41Z
- **Fechada:** 2026-11-08T20:50:41Z

<details>
<summary>Descricao original</summary>

<pre>Roda a simulação da corrida em geral, que usufrui da modelagem da etapa anterior e modela a corrida em geral</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:50:41Z — fechada por @Gustavo-Jun-Tsuji
- 2026-09-11T23:54:52Z — label adicionada: História por @guilherme-webster

</details>

### [#74 — Enriquecer ETL](https://github.com/guilherme-webster/mc857-o-projeto/issues/74)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#24 — ETL inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/24)
- **Sub-issues:** —
- **Criada:** 2026-09-12T21:41:02Z
- **Atualizada:** 2026-09-12T21:41:15Z
- **Fechada:** 2026-09-12T21:41:15Z

<details>
<summary>Descricao original</summary>

<pre>Trazer demais campos dos DF&#x27;s recomendados pelo professor de maneira a termos mais dados para modelagem posterior</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-12T21:41:15Z — fechada por @guilherme-webster
- 2026-09-12T21:41:02Z — label adicionada: História por @guilherme-webster
- 2026-09-12T21:41:02Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#86 — Otimização de UI\\UX](https://github.com/guilherme-webster/mc857-o-projeto/issues/86)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)
- **Sub-issues:** —
- **Criada:** 2026-09-26T00:29:20Z
- **Atualizada:** 2026-09-26T00:40:20Z
- **Fechada:** 2026-09-26T00:40:20Z

<details>
<summary>Descricao original</summary>

<pre>Limpeza da UI e UX</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@Jmvjr em 2026-09-26T00:36:36Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/86#issuecomment-5841574785)

<pre>Tela de torneio: sequência agora rola uma etapa por vez com indicador de posição; retirados do painel esquerdo o seletor de geração e o resumo, e da apresentação da pista os textos de proveniência/“geometria reduzida”. O botão de geração automática do scheduler foi preservado. Verificações locais: 33 testes gráficos de parameters_view passaram; suíte geral 308 testes OK (32 GUI pulados no padrão); Ruff, Black e git diff --check OK. Próximo passo: revisão visual pelo responsável e commit/PR; nenhuma alteração foi commitada pelo agente.</pre>

#### [@Jmvjr em 2026-09-26T00:39:16Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/86#issuecomment-5841596247)

<pre>Ajustes adicionais na configuração de corrida: controles −/+ das voltas redesenhados como botões internos aos campos, com cliques individuais; opção visual de largada removida sem alterar o contrato SessionConfiguration; ID canônico removido do cabeçalho compartilhado por Sessão/Clima; textos de geometria reduzida e quantidade de pontos removidos do resumo da pista. Testes atualizados. Verificações: 35 testes GUI de parameters_view passaram, suíte geral 311 testes OK (35 GUI pulados no padrão), Ruff/Black/diff check OK. Próximo passo: revisão visual do layout pelo responsável e commit/PR; nenhum commit criado pelo agente.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-26T00:40:21Z — fechada por @Jmvjr
- 2026-09-26T00:29:35Z — atribuida: @Jmvjr por @Jmvjr
- 2026-09-26T00:29:33Z — label adicionada: Task por @Jmvjr

</details>

### [#95 — Modelagem da pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/95)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-10-16T19:57:22Z
- **Atualizada:** 2026-11-08T20:28:37Z
- **Fechada:** 2026-11-07T19:01:07Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:28:37Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-11-07T19:01:07Z — fechada por @Gustavo-Jun-Tsuji

</details>

### [#101 — Simular entrada, parada e saída dos carros pela pit lane no motor 2D](https://github.com/guilherme-webster/mc857-o-projeto/issues/101)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)
- **Sub-issues:** —
- **Criada:** 2026-10-26T22:30:33Z
- **Atualizada:** 2026-10-26T22:55:37Z
- **Fechada:** 2026-10-26T22:55:37Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-26T22:55:37Z — fechada por @Jmvjr
- 2026-10-26T22:30:41Z — atribuida: @Jmvjr por @Jmvjr

</details>

### [#102 — Simular entrada, parada e saída dos carros pela pit lane no motor 2D](https://github.com/guilherme-webster/mc857-o-projeto/issues/102)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** [#8 — Rodar Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/8)
- **Sub-issues:** —
- **Criada:** 2026-10-26T22:56:42Z
- **Atualizada:** 2026-10-26T22:56:49Z
- **Fechada:** 2026-10-26T22:56:49Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-10-26T22:56:49Z — fechada por @Jmvjr
- 2026-10-26T22:56:48Z — atribuida: @Jmvjr por @Jmvjr

</details>

### [#104 — Desgate e combústivel dinâmicos](https://github.com/guilherme-webster/mc857-o-projeto/issues/104)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** [#63 — Pneu](https://github.com/guilherme-webster/mc857-o-projeto/issues/63)
- **Sub-issues:** —
- **Criada:** 2026-10-26T23:08:00Z
- **Atualizada:** 2026-11-06T21:35:40Z
- **Fechada:** 2026-11-06T21:35:39Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@Jmvjr em 2026-11-06T21:19:21Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/104#issuecomment-6695878335)

<pre>Retomada em 06/11/2026: alterações locais de consumo e desgaste dinâmicos recuperadas na develop atualizada, com stash preservado como cópia de segurança. Revisão inclui as paradas sincronizadas na regra de segundo composto e a preservação das funcionalidades recentes de torneios e sementes. O ADR novo passa a ser 0014, pois 0013 já pertence aos torneios salvos. Próximos passos: concluir os ajustes, executar os testes e registrar o commit antes de encerrar a issue.</pre>

#### [@Jmvjr em 2026-11-06T21:35:38Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/104#issuecomment-6696268042)

<pre>Concluído e integrado à develop pelo PR #121: https://github.com/guilherme-webster/mc857-o-projeto/pull/121

Commit da implementação: 8531d60f80341aa89320dc2a9f08cd1470a80222. Merge: e30b79497c98aabf065649964e6e274a04561666.

O 2D agora integra queima e desgaste por movimento, considerando distância, velocidade, esforço longitudinal e carga lateral estimada das curvas. O frontend lê os recursos das trajetórias; pane seca pode ocorrer entre linhas sem creditar uma volta fictícia. A troca obrigatória é planejada por desgaste e preferência individual semeada, preservando o prazo de dois compostos, estratégias explícitas e o motor por volta. O ADR 0014 registra a integração sem substituir o ADR 0013 dos torneios.

Verificações: suíte completa com `uv run --with httpx2 python -m unittest` — 756 testes, zero falhas/erros, 45 ignorados por condições gráficas; Ruff e whitespace passaram. No cenário de regressão de dez voltas/seed 42, o grid entra nas voltas 6 e 7. Reprodutibilidade, conservação de massa, curvas rápidas, convergência do passo, serviço parado, formatos legados e torneios estão cobertos.

Limites registrados: pesos heurísticos/assumidos, curvatura derivada do mock com contribuição limitada a 6 g, sem calibração de consumo/desgaste medidos nem reabastecimento no 2D. Próximo trabalho possível: calibrar esses fatores e revisar o envelope físico; não há bloqueio para esta entrega. Datasets e arquivos calibrados foram preservados.
</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-06T21:35:40Z — fechada por @Jmvjr
- 2026-10-26T23:12:04Z — atribuida: @Jmvjr por @Jmvjr

</details>

### [#106 — Reordenar livremente o grid de largada](https://github.com/guilherme-webster/mc857-o-projeto/issues/106)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** enhancement
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-10-30T20:33:03Z
- **Atualizada:** 2026-11-08T20:36:33Z
- **Fechada:** 2026-11-08T20:36:33Z

<details>
<summary>Descricao original</summary>

<pre>Permitir que o usuário mude a ordem de largada como quiser.

A ordem já chega ao motor, mas a tela só seleciona linhas e o `PATCH /catalog/grid` altera apenas atributos.

Critérios:
- botões ↑/↓ na tela do grid; ordem pendente no `GridDraft` (descartar, payload);
- `PATCH /catalog/grid` aceita `order`, permutação exata do grid atual; 422 para duplicata, ausência ou ID desconhecido;
- atributos, perfis e seed preservados; escrita atômica.

Contrato: `docs/prds/controles-do-usuario-simulacao.md`, seção 3.2.</pre>

</details>

<details>
<summary>Comentarios (4)</summary>

#### [@guilherme-webster em 2026-10-30T20:35:19Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/106#issuecomment-6532928102)

<pre>Iniciado em 2026-10-30. Implementacao delegada a um agente Codex (gpt-5.6-sol) na branch `106-reordenar-grid`, a partir da `develop` (1200f6e, com o PRD `docs/prds/controles-do-usuario-simulacao.md`). Linha de base da suite na develop: 614 passam, 3 falhas pre-existentes em `tests/test_catalog_grid_run.py`.</pre>

#### [@guilherme-webster em 2026-10-30T20:47:23Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/106#issuecomment-6533137003)

<pre>Implementado na branch `106-reordenar-grid` (2 commits: `reorder_grid` valida permutacao exata por `driver_id` e `PATCH /catalog/grid` aceita `order` preservando atributos e seed; botoes Subir/Descer e ordem pendente no `GridDraft`). Integrado na `develop` local (merge, sem push). Suite: 650 passed / 0 failed na develop integrada. Pendente: push/PR e conferencia visual dos botoes.</pre>

#### [@guilherme-webster em 2026-10-30T21:31:45Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/106#issuecomment-6533891164)

<pre>Entrega no PR #112 (empilhado sobre o #111, com a branch 105 já mesclada). Ordem de merge: #111 (105) → #112 (106) → #113 (107) → #114 (108) → #115 (109); cada PR tem como base a branch anterior. Próximo passo: revisão e merge; conferir visualmente os botões Subir/Descer.</pre>

#### [@guilherme-webster em 2026-10-30T21:55:49Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/106#issuecomment-6534336804)

<pre>Mergeado na `develop` em 2026-10-30 (PRs #111–#115, na ordem). Suite na develop resultante (0668268): 672 passed, 0 failed. Pendente apenas a conferencia visual das telas no app rodando; a issue fica aberta ate essa conferencia e o merge na `main`.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:36:33Z — fechada por @Gustavo-Jun-Tsuji
- 2026-11-08T20:36:30Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-11-08T20:36:29Z — responsavel removido: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-11-08T20:36:25Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-10-30T20:33:04Z — label adicionada: enhancement por @guilherme-webster

</details>

### [#107 — Número de voltas padrão por pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/107)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-10-30T20:33:05Z
- **Atualizada:** 2026-11-08T20:36:16Z
- **Fechada:** 2026-11-08T20:36:16Z

<details>
<summary>Descricao original</summary>

<pre>Toda pista nova começa com 69 voltas fixas no frontend (`configuration_state.py`, `parameters_view.py`).

Critérios:
- padrão = máximo de voltas completadas na corrida mais recente do circuito (Trotman v128), com proveniência;
- sem histórico: menor número de voltas completas acima de 305 km (Mônaco 260 km), rotulado `assumed_distance_rule`;
- `GET /simulation/tracks` devolve `default_laps` e origem;
- padrão só para pista não configurada; edição do usuário preservada; clima padrão cobre o novo total.

Contrato: `docs/prds/controles-do-usuario-simulacao.md`, seção 3.3. Proposta original em `docs/progresso.md`.</pre>

</details>

<details>
<summary>Comentarios (4)</summary>

#### [@guilherme-webster em 2026-10-30T20:35:20Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/107#issuecomment-6532928474)

<pre>Iniciado em 2026-10-30. Implementacao delegada a um agente Codex (gpt-5.6-sol) na branch `107-voltas-padrao`, a partir da `develop` (1200f6e, com o PRD `docs/prds/controles-do-usuario-simulacao.md`). Linha de base da suite na develop: 614 passam, 3 falhas pre-existentes em `tests/test_catalog_grid_run.py`.</pre>

#### [@guilherme-webster em 2026-10-30T20:47:25Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/107#issuecomment-6533137326)

<pre>Implementado na branch `107-voltas-padrao` (2 commits: caso de uso `default_laps_for_circuit` com historico Trotman e reserva `assumed-distance-rule-v1`; `GET /simulation/tracks` com `default_laps`, origem e corrida; frontend aplica o padrao so em pista nao configurada e ajusta o clima). Conferido com o Trotman v128 bruto: Albert Park 58, Monaco 78, Spa 44, Interlagos 71, Yas Marina 58 (corrida mais recente). Integrado na `develop` local (merge com conflito resolvido em `parameters_view.py`/teste, sem push). Suite: 650 passed / 0 failed.</pre>

#### [@guilherme-webster em 2026-10-30T21:31:46Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/107#issuecomment-6533891529)

<pre>Entrega no PR #113 (empilhado sobre o #112, conflito com a #105 resolvido no merge da branch). Ordem de merge: #111 (105) → #112 (106) → #113 (107) → #114 (108) → #115 (109); cada PR tem como base a branch anterior. Próximo passo: revisão e merge.</pre>

#### [@guilherme-webster em 2026-10-30T21:55:50Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/107#issuecomment-6534337125)

<pre>Mergeado na `develop` em 2026-10-30 (PRs #111–#115, na ordem). Suite na develop resultante (0668268): 672 passed, 0 failed. Pendente apenas a conferencia visual das telas no app rodando; a issue fica aberta ate essa conferencia e o merge na `main`.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:36:16Z — fechada por @Gustavo-Jun-Tsuji
- 2026-10-30T20:33:06Z — label adicionada: bug por @guilherme-webster

</details>

### [#125 — Feature: Decomposicao de velocidade](https://github.com/guilherme-webster/mc857-o-projeto/issues/125)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-07T19:03:31Z
- **Atualizada:** 2026-11-08T20:34:53Z
- **Fechada:** 2026-11-08T20:34:53Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Comentarios (1)</summary>

#### [@Gustavo-Jun-Tsuji em 2026-11-08T20:34:53Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/125#issuecomment-6726776427)

<pre>&lt;img width=&quot;267&quot; height=&quot;234&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/de975f96-e2fa-4543-bbe3-f5e2400feaff&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:34:53Z — fechada por @Gustavo-Jun-Tsuji
- 2026-11-08T20:34:52Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji

</details>

### [#128 — Desempenho de equipes no pit-stop](https://github.com/guilherme-webster/mc857-o-projeto/issues/128)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** @ViniciusFCoracin
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-08T01:07:46Z
- **Atualizada:** 2026-11-08T20:28:26Z
- **Fechada:** 2026-11-08T19:13:45Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:28:26Z — atribuida: @ViniciusFCoracin por @ViniciusFCoracin
- 2026-11-08T19:13:45Z — fechada por @ViniciusFCoracin

</details>

### [#130 — Correções de bugs no frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/130)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** @ViniciusFCoracin
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-08T16:23:18Z
- **Atualizada:** 2026-11-08T20:28:05Z
- **Fechada:** 2026-11-08T19:13:37Z

<details>
<summary>Descricao original</summary>

<pre>Alguns bugs foram identificados no frontend:
1) Na tela de configuração, a seta para a esquerda para visualizar a pista anterior não está funcionando.
2) Na tela de grid, não estão sendo exibidos todos os pilotos
3) Está havendo sobreposição dos pilotos com a caixa de configuração das estatísticas
Necessário corrigir esses bugs</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:28:05Z — atribuida: @ViniciusFCoracin por @ViniciusFCoracin
- 2026-11-08T19:13:37Z — fechada por @ViniciusFCoracin

</details>

### [#132 — Simulação leva em conta o número de voltas definido pelo usuário](https://github.com/guilherme-webster/mc857-o-projeto/issues/132)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** @ViniciusFCoracin
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-08T17:10:21Z
- **Atualizada:** 2026-11-08T20:27:55Z
- **Fechada:** 2026-11-08T19:13:30Z

<details>
<summary>Descricao original</summary>

<pre>Até então, o usuário tem a possibilidade de customizar a volta inicial e o número de voltas, mas nem a simulação e nem a exibição levam em conta esse número customizado (continuam utilizando o padrão definido na pista)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-08T20:27:55Z — atribuida: @ViniciusFCoracin por @ViniciusFCoracin
- 2026-11-08T19:13:30Z — fechada por @ViniciusFCoracin

</details>

### [#135 — Carregar corridas salvas na tela inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/135)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @ViniciusFCoracin
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)
- **Sub-issues:** —
- **Criada:** 2026-11-08T20:20:26Z
- **Atualizada:** 2026-11-09T22:36:53Z
- **Fechada:** 2026-11-09T22:36:53Z

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-09T22:36:53Z — fechada por @ViniciusFCoracin
- 2026-11-09T21:46:29Z — atribuida: @ViniciusFCoracin por @ViniciusFCoracin
- 2026-11-08T20:20:27Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#137 — Melhorar Tela de corrida salvas](https://github.com/guilherme-webster/mc857-o-projeto/issues/137)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @ViniciusFCoracin
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#136 — Bugs no Frontend](https://github.com/guilherme-webster/mc857-o-projeto/issues/136)
- **Sub-issues:** —
- **Criada:** 2026-11-08T20:24:31Z
- **Atualizada:** 2026-11-09T22:36:41Z
- **Fechada:** 2026-11-09T22:36:41Z

<details>
<summary>Descricao original</summary>

<pre>Escritas sobrepostas e não existe botão de retorno

&lt;img width=&quot;779&quot; height=&quot;588&quot; alt=&quot;Image&quot; src=&quot;https://github.com/user-attachments/assets/3145cd1a-37be-4232-8c3f-bb495eefd5a5&quot; /&gt;</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-09T22:36:42Z — fechada por @ViniciusFCoracin
- 2026-11-09T21:46:34Z — atribuida: @ViniciusFCoracin por @ViniciusFCoracin
- 2026-11-08T20:24:40Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#144 — Testes: extrair fuel_parameters para modulo de suporte e destravar test_fuel](https://github.com/guilherme-webster/mc857-o-projeto/issues/144)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:19Z
- **Atualizada:** 2026-11-12T21:57:58Z
- **Fechada:** 2026-11-12T21:57:58Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

Em `develop` (commit `94e52ab`), `uv run python -m unittest` termina com 5 falhas
e 21 erros. Parte deles e erro de importacao em cascata:

- `tests/test_fuel.py:39` importa `f1_simulator.domain.lap_time`, removido junto
  com o motor por volta (hoje em `TOBEDEFINED/`);
- `tests/test_dynamic_usage.py:26` e `tests/test_race_playback.py:17` importam o
  helper `fuel_parameters` de `tests.test_fuel` e caem junto.

Resultado: tres modulos de teste inteiros nao executam.

## Escopo

- Mover `fuel_parameters` (e helpers puros que ele usa) para um modulo de suporte
  em `tests/`, no molde de `tests/history_support.py`, e apontar os tres modulos
  para ele.
- Em `test_fuel.py`, remover apenas os testes que dependem de `lap_time`
  (`fuel_penalty_ms`). Os testes de `domain/fuel.py` continuam.

## Criterios de aceitacao

- `uv run python -m unittest tests.test_fuel tests.test_dynamic_usage tests.test_race_playback`
  importa e passa.
- Nenhum teste de `domain/fuel.py` ainda valido foi apagado; liste no comentario
  de encerramento os testes removidos e o motivo.

## Fora de escopo

`tests/test_fuel_strategy.py` (tratado em outra issue) e qualquer mudanca em `src/`.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:27:36Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/144#issuecomment-6836408292)

<pre>Branch local `144-fuel-parameters-support` (sem push), commit `d0a6ef0` sobre develop (59bef6a).

**O que mudou (so `tests/` e `TOBEDEFINED/`)**
- Novo `tests/fuel_support.py` com `fuel_parameters` e `REFERENCE_MS`; `test_dynamic_usage` e `test_race_playback` importam dele.
- Novo `tests/geometry_support.py` (geometria do fixture Trotman + `attribute`).
- `test_fuel.py`: removidos os testes que dependiam do motor por volta, arquivados em `TOBEDEFINED/test_fuel_motor_por_volta.py`.
- `test_race_playback.py`: `run_engine_race` agora usa o 2D (geometria de Monaco, 4 carros, 6 voltas).

**Testes removidos de `test_fuel.py` (motivo)**
- `EngineFuelTest` (7 testes: `test_clean_race_reproduces_the_linear_model` usa `fuel_penalty_ms`/`lap_time`; os demais usam `simulate_detailed_race`).
- `RefuelStopEngineTest` (7 testes) e helpers `entrants`/`quiet_model`: `simulate_detailed_race`/`Entrant`.
- `GridFuelTest` (2) e `GridRefuelTest` (1): rodavam `run_grid_simulation` sem geometria (o 2D recusa) e usavam `attribute` do modulo detalhado.
- Nenhum teste de `domain/fuel.py`, calibracao ou artefato foi apagado (20 testes permanecem).

**Achados do motor 2D (motor nao alterado)** — em `test_race_playback`, dois testes ficaram `expectedFailure`:
- `test_lift_and_coast_laps_match_the_engine_count`: no 2D o consumo real em Monaco (~1,6 kg/volta) fica bem abaixo do `burn_kg_per_lap` do plano (5,5) por causa do fluxo limitado pela dinamica de uso; o carro seca sem fazer lift-and-coast.
- `test_scenario_forces_a_refuel_stop`: com a estrategia padrao o 2D nao reabastece; os demais testes da classe passam vacuamente (sem eventos).
- Tolerancias: `laps_at` com delta 0,01 (passos de tempo discretos) e combustivel com delta 0,01 (snapshot arredondado a 2 casas).

**Verificacoes**: `tests.test_fuel tests.test_dynamic_usage tests.test_race_playback`: 86 testes OK (2 expected failures). Suite completa nesta branch: 712 testes, 3 falhas, 19 erros (restos das issues #145/#146), nenhuma nova.

Proximo passo: decidir se o 2D deve ter lift-and-coast/reabastecimento coerentes com o plano (fora do escopo desta issue).
</pre>

#### [@guilherme-webster em 2026-11-12T21:57:57Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/144#issuecomment-6837051010)

<pre>Mesclado em `develop` pelo PR #160. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:57:58Z — fechada por @guilherme-webster
- 2026-11-12T21:08:19Z — label adicionada: Task por @guilherme-webster

</details>

### [#145 — Testes: portar para o motor 2D os contratos vivos e arquivar os do motor por volta](https://github.com/guilherme-webster/mc857-o-projeto/issues/145)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:20Z
- **Atualizada:** 2026-11-12T21:58:00Z
- **Fechada:** 2026-11-12T21:58:00Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

O motor por volta foi removido de `src/` (ADR 0011; arquivo morto em
`TOBEDEFINED/`), mas os testes dele ficaram em `tests/` e quebram a suite:

| Modulo | Sintoma |
|---|---|
| `test_run_grid_detailed.py` (11 erros) | `engine=`, patch de `simulate_detailed_race`, execucao sem geometria |
| `test_detailed_tyre_management.py` | `ValueError: o motor 2D exige geometria da pista` |
| `test_reference_laps.py` (2 erros, `DetailedGridReferenceTest`) | idem |
| `test_fuel_strategy.py` | importa `f1_simulator.domain.race_simulation` |
| `test_catalog_grid_run.py`, `test_tournament_seed_api.py` | patch de `run_detailed_grid_simulation` |
| `test_saved_tournament.py::test_rerun_after_restore_reproduces_saved_races` | reexecucao sem geometria |

## Decisao do responsavel (2026-11-12)

**Portar para o motor 2D** os testes cujo contrato continua vivo. Arquivar em
`TOBEDEFINED/` somente o que testa comportamento exclusivo do motor removido.

## Escopo

Reescrever contra `run_grid_simulation` / `simulate_2d_race`, com a geometria de
`tests/fixtures/trotman_v128_tracks_2025` e poucas voltas, os contratos:

- ordem do grid e atributos chegam ao motor como posicoes de largada;
- mesma semente reproduz a corrida, inclusive eventos de controle de prova;
- semente de torneio reproduz a etapa e separa etapas distintas
  (`derive_tournament_stage_random_source`);
- atributo de ritmo altera o resultado;
- volta de referencia historica prevalece sobre o ritmo por km;
- pista sem calibracao usa o fallback `assumed` e o declara em `assumptions`;
- metadados de semente devolvidos pela API batem com a derivacao do nucleo;
- reexecucao de torneio salvo apos `restore-grid` reproduz as corridas salvas;
- decisoes de `HeuristicPitStrategy` com combustivel que nao dependam do motor
  antigo (`test_fuel_strategy.py`).

Renomear os modulos que perderem o sentido de &quot;detailed&quot;. Mover para
`TOBEDEFINED/` o que sobrar, com uma linha no topo dizendo de onde veio.

## Criterios de aceitacao

- `grep -rn &quot;detailed\|lap_time\|race_simulation\b&quot; tests/` nao encontra
  referencia ao motor removido.
- Os contratos listados acima tem teste passando contra o 2D.
- O comentario de encerramento lista o que foi portado e o que foi arquivado.

## Dependencias

Depois de #144. O campo `engine` nas asserts de rota e tratado em outra issue.

## Fora de escopo

Alterar regra de simulacao. Se um contrato portado falhar por comportamento real
do 2D, registre aqui e nao ajuste o motor.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:27:37Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/145#issuecomment-6836408821)

<pre>Branch local `145-portar-testes-motor-2d` (pilha sobre `144-fuel-parameters-support`; sem push). Commits: `b88c4d6`, `7426d6f`, `4698005`, `d6069ce`.

**Portado para o 2D (geometria de `tests/fixtures/trotman_v128_tracks_2025`, 1 a 4 voltas)**
- `test_run_grid_detailed.py` -&gt; `test_run_grid_simulation.py` (9 testes): ordem do grid e atributos chegam ao motor como posicoes de largada (patch de `simulate_2d_race`); mesma semente reproduz corrida e eventos de controle; semente de torneio reproduz e separa etapas; atributo de ritmo altera resultado; pista sem calibracao usa fallback `assumed`; sem pista usa volta nominal declarada em `assumptions`; referencia por geometria.
- `test_reference_laps.py::GridReferenceTest`: volta historica prevalece sobre ritmo por km, fallback por km, referencia de outro circuito rejeitada.
- `test_detailed_tyre_management.py` -&gt; `test_tyre_management_factor.py`: efeito do fator de gestao de pneus no tempo de corrida.
- `test_catalog_grid_run.py`, `test_tournament_seed_api.py`: patch de `run_detailed_grid_simulation` -&gt; `run_grid_simulation` (metadados de semente batem com a derivacao do nucleo). Nao toquei nos asserts `engine=` (issue #146).
- `test_saved_tournament.py::test_rerun_after_restore_reproduces_saved_races`: injeta a geometria do fixture; reexecucao reproduz as corridas salvas.
- `test_fuel_strategy.py`: decisoes de `HeuristicPitStrategy` com combustivel (unitarias) continuam; import do motor antigo removido.
- Helpers `attribute` e `small_geometry` foram para `tests/geometry_support.py`; importadores atualizados.

**Arquivado em `TOBEDEFINED/`**: `test_fuel_motor_por_volta.py` (da #144) e `test_fuel_strategy_motor_por_volta.py` (teste de grid com cargas iniciais distintas, paradas de reabastecimento decididas pela estrategia e assumption `fuel_strategy`; teste de queima ate a entrada dos boxes).

**Divergencias do 2D (motor nao alterado)**
1. Abandono sem disputa e `mechanical` (nao `solo_crash`), e so vira evento de controle de prova se outro carro completar a volta; teste ajustado para esse contrato.
2. O 2D aplica o fator de gestao de pneus mas nao declara a assumption `detailed_tyre_management`; removi essa asserção.
3. No 2D, todos os carros largam com a mesma carga, nao ha `refuel_stops` decididos pela estrategia nem assumption `fuel_strategy` (contrato arquivado acima).

**Verificacoes**: suite completa: 727 testes, 4 falhas, 0 erros, 51 skipped, 2 expected failures. Falhas restantes: `test_route_forwards_*` (2) e subteste `[motor]` de saved_tournament (issue #146, campo `engine`) e `test_pit_lane::test_movement_stops_at_service_and_finishes_two_laps` (ja falhava, fora desta issue). `grep detailed` ainda acha: `engine=&quot;detailed&quot;` (#146) e nomes de `src` (`DETAILED_TYRE_MANAGEMENT`), que sao fora do escopo de testes. Rodei `uv pip install httpx2` so no ambiente local, sem alterar pyproject/uv.lock.
</pre>

#### [@guilherme-webster em 2026-11-12T21:57:59Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/145#issuecomment-6837051650)

<pre>Mesclado em `develop` pelo PR #161. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:58:00Z — fechada por @guilherme-webster
- 2026-11-12T21:08:21Z — label adicionada: Task por @guilherme-webster

</details>

### [#146 — Remover o seletor de motor do frontend e a checagem de motor do torneio salvo](https://github.com/guilherme-webster/mc857-o-projeto/issues/146)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:21Z
- **Atualizada:** 2026-11-12T21:58:03Z
- **Fechada:** 2026-11-12T21:58:03Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

So existe o motor 2D, e `RaceSetupRequest` nao declara `engine`. Mesmo assim:

- `frontend/arcade/configuration_state.py:198` oferece
  `ENGINE_OPTIONS = (&quot;Detalhado (calibrado)&quot;, &quot;2D com pit lane&quot;)`, com
  &quot;Detalhado&quot; como padrao; a tela promete um motor que nao roda;
- `frontend/arcade/race_launcher.py:139-143` e `parameters_view.py` (linhas
  ~516, ~1002, ~1348) ainda montam e desenham a regra;
- `tests/test_catalog_grid_run.py::test_route_forwards_setup_to_service` e
  `tests/test_tournament_seed_api.py::test_route_forwards_explicit_seed_and_stage_index`
  esperam `engine=&#x27;detailed&#x27;` na chamada do servico;
- `tests/test_saved_tournament.py::test_rejects_setup_that_would_rerun_a_different_race`
  tem o subteste `[motor]`, que espera `SavedTournamentError` para motor
  divergente; `check_saved_tournament` nao faz mais essa checagem.

## Decisao do responsavel (2026-11-12)

Remover a escolha e a checagem, mantendo apenas o motor 2D.

## Escopo

- Tirar `ENGINE_OPTIONS`, `ENGINE_API_VALUES`, o campo `engine` de
  `TournamentRules` e o controle correspondente da tela; `setup` deixa de
  enviar `engine`.
- Ajustar os tres testes acima e os testes de frontend que citem a regra.
- Torneios ja salvos podem conter `rules.engine` ou `setup.engine`: reabrir e
  reexecutar devem continuar funcionando, ignorando o campo. Cubra com teste.

## Criterios de aceitacao

- `grep -rn &quot;engine&quot; frontend/arcade backend/app` nao encontra a regra de motor.
- Um torneio salvo antigo com `engine` reabre sem erro.
- O layout de `ParametersView` nao fica com um buraco onde estava o controle.

## Fora de escopo

Reintroduzir escolha de motor ou alterar o ADR 0011.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:23:08Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/146#issuecomment-6836314243)

<pre>Implementado localmente na branch `146-remover-seletor-motor` (commit 0243479, sem push).

- Removidos `ENGINE_OPTIONS`, `ENGINE_API_VALUES`, `TournamentRules.engine`, o controle/rotulo/clique em `parameters_view.py`, o envio de `setup.engine` em `race_launcher.py` e a linha &quot;Motor&quot; da tela de carregamento.
- `saved_tournaments.py`: `reopen`/`rerun` ignoram `rules.engine` e `setup.engine` de registros antigos (e nao reenviam ao backend). Testes novos cobrem reabrir, reexecutar e `check_saved_tournament`.
- Layout: `RULES_PANEL_BOUNDS` encolhido de (28,184,544,392) para (28,214,544,362), para nao sobrar painel vazio abaixo do campo de semente (conferido pelo codigo; conferencia visual fica para o usuario).
- Testes ajustados: test_catalog_grid_run, test_tournament_seed_api (sem `engine=`), test_saved_tournament (sem subteste &quot;motor&quot;), test_race_launcher, test_parameters_view, test_saved_tournaments_frontend.
- `grep -rn engine frontend/arcade backend/app` so acha o tratamento de legado.

Suite (com httpx2 so na .venv): 635 testes, 2 falhas, 21 erros (baseline 637/5/21). Restantes sao do motor removido (#145: geometria exigida, patch de run_detailed_grid_simulation) e test_pit_lane. test_parameters_view com ARCADE_GUI_TEST=1 tem as mesmas 4 falhas + 1 erro de antes da mudanca (display/tamanho de janela), nao relacionadas.
</pre>

#### [@guilherme-webster em 2026-11-12T21:58:01Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/146#issuecomment-6837052551)

<pre>Mesclado em `develop` pelo PR #162. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:58:03Z — fechada por @guilherme-webster
- 2026-11-12T21:08:22Z — label adicionada: Task por @guilherme-webster

</details>

### [#147 — Investigar a falha de test_pit_lane (25 amostras paradas, esperado mais de 40)](https://github.com/guilherme-webster/mc857-o-projeto/issues/147)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** bug
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:23Z
- **Atualizada:** 2026-11-12T21:57:50Z
- **Fechada:** 2026-11-12T21:57:50Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

`tests/test_pit_lane.py::PitLaneMotionTest::test_movement_stops_at_service_and_finishes_two_laps`
falha em `develop` (`94e52ab`):

```
self.assertGreater(len(stationary), 40)
AssertionError: 25 not greater than 40
```

O teste pede um servico de 2,5 s (`PitStopRequest(360, 2.5)`); com `dt_s=0.05`
seriam cerca de 50 amostras paradas. A duracao entre `service_started` e
`service_completed` continua correta (a assert anterior passa), entao a
diferenca pode estar na amostragem de `integrate_field` e nao no servico. A
causa **nao foi investigada**.

## Escopo

- Descobrir desde qual commit o teste falha (`git bisect` ou `git log` em
  `domain/track_space.py` e `domain/pit_lane.py`).
- Decidir, com a causa em maos, se o erro esta no motor ou no teste, e corrigir
  o lado errado.

## Criterios de aceitacao

- O teste passa e o comentario de encerramento explica a causa.
- Se o motor mudou, ha teste de regressao; se o teste mudou, a nova assert
  continua verificando que o carro fica parado durante todo o servico.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:16:47Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/147#issuecomment-6836177730)

<pre>## Causa e correcao (branch local `147-pit-lane-amostras-paradas`, commit 413b10b, sem push)

**Causa:** o erro estava no teste, nao no motor. O commit 9c94abd (&quot;feat: visualizacao impacto dos parametros no frontend&quot;, 07/11) mudou `ASSUMED_TIME_STEP_S` de 0,05 s para 0,1 s em `domain/track_space.py`. O teste usava o passo padrao e fixava &quot;&gt; 40 amostras&quot;, valido so para 0,05 s (2,5 / 0,05 = 50). Com 0,1 s o servico gera ~25 amostras, o que e correto: a duracao service_started -&gt; service_completed continua 2,5 s. Identificado por `git log -S` no valor da constante (mudanca de uma linha; bisect desnecessario).

**Correcao:** o teste passa `dt_s=0.05` explicito e a assert passa a ser `len(stationary) &gt;= round(service_s / dt_s) - 1`; as asserts de velocidade zero e posicao constante durante o servico foram mantidas. Corrigi tambem o comentario obsoleto de `ASSUMED_TIME_STEP_S` (dizia 50 ms). Nenhuma regra de simulacao mudou.

**Verificacao:** `tests.test_pit_lane` 12/12 OK; suite completa: 629 testes, 2 falhas, 22 erros, 51 skipped (restos de outras issues; nenhum de test_pit_lane).
</pre>

#### [@guilherme-webster em 2026-11-12T21:57:49Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/147#issuecomment-6837048276)

<pre>Mesclado em `develop` pelo PR #156. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:57:50Z — fechada por @guilherme-webster
- 2026-11-12T21:08:23Z — label adicionada: bug por @guilherme-webster

</details>

### [#148 — CI: rodar a suite de testes em pull requests](https://github.com/guilherme-webster/mc857-o-projeto/issues/148)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:24Z
- **Atualizada:** 2026-11-12T21:58:08Z
- **Fechada:** 2026-11-12T21:58:08Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

Nao ha CI de testes; `.github/workflows/` tem apenas `pull-request-rules.yml` e
`sync-backlog.yml`. A suite quebrou em `develop` sem ninguem notar. O
`CONTRIBUTING.md` pede que as regras objetivas sejam reforcadas por automacao.

## Escopo

- Workflow do GitHub Actions que, em PRs para `develop` e `main` e em push para
  `develop`, instala com `uv sync` (Python 3.12) e roda
  `uv run python -m unittest`.
- Os testes de GUI seguem pulados (`ARCADE_GUI_TEST` ausente); o job nao precisa
  de display.
- Se o `TestClient` pedir `httpx2`, resolver de forma declarada (ver a secao
  &quot;Testes e verificacoes&quot; do `README.MD`), sem dependencia implicita.
- Remover de `pyproject.toml` o bloco `[tool.pytest.ini_options]`, ou trocar
  por algo coerente: pytest nao e dependencia e a suite usa unittest.
- Atualizar o `README.MD` e a frase do `CONTRIBUTING.md` que diz nao haver CI.

## Criterios de aceitacao

- Um PR com teste quebrado fica com o check vermelho.
- O job nao acessa a rede alem da instalacao de dependencias.

## Dependencias

A suite precisa estar verde antes: #144, #145, #146 e #147.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:19:42Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/148#issuecomment-6836241339)

<pre>Branch local `148-ci-testes` (sem push), a partir de develop 59bef6a.

Commits:
- 6e526f2 build(deps): declara httpx2 no grupo dev para o TestClient
- 0766a27 ci(tests): roda a suite unittest em pull requests

O que mudou:
- `.github/workflows/tests.yml`: PRs para develop/main e push para develop; `permissions: contents: read`; `concurrency` cancela runs antigos; actions/checkout@v7, astral-sh/setup-uv@v10.3.3 com uv 0.13.6 e Python 3.12; `uv sync --locked` e `uv run python -m unittest`. Sem ARCADE_GUI_TEST, GUI fica pulada; sem rede apos a instalacao.
- `pyproject.toml`: grupo `dev` com `httpx2` (o starlette 1.7.0 travado exige httpx2 em `starlette.testclient`; numa venv limpa `tests.test_saved_tournament` nao importava). `uv.lock` atualizado. Removido `[tool.pytest.ini_options]`.
- README.MD (secao Testes e verificacoes) e CONTRIBUTING.md atualizados (CI existe; nao ha mais `--with httpx2`).

Verificacao local (env -u ARCADE_GUI_TEST -u DISPLAY -u WAYLAND_DISPLAY, apos `uv sync --locked`): 637 testes, 5 falhas, 21 erros, 51 pulados - as mesmas do baseline de develop. Importar arcade sem display nao quebra a descoberta. actionlint indisponivel; YAML validado com python.

Importante: o check so ficara verde apos o merge de #144-#147 (falhas conhecidas). Sugestao: ao ficar verde, marcar o check como obrigatorio na protecao de branch.
</pre>

#### [@guilherme-webster em 2026-11-12T21:58:07Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/148#issuecomment-6837054370)

<pre>Mesclado em `develop` pelo PR #164. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:58:08Z — fechada por @guilherme-webster
- 2026-11-12T21:08:25Z — label adicionada: Task por @guilherme-webster

</details>

### [#149 — CI: adotar ruff como linter e formatador](https://github.com/guilherme-webster/mc857-o-projeto/issues/149)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:25Z
- **Atualizada:** 2026-11-12T21:58:10Z
- **Fechada:** 2026-11-12T21:58:10Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

O `CONTRIBUTING.md` preve formatador e linter locais e no CI; nao ha nenhum.
Decisao do responsavel em 2026-11-12: adotar.

## Escopo

- Adicionar `ruff` como dependencia de desenvolvimento (grupo `dev` do
  `pyproject.toml`), com configuracao minima: regras padrao mais ordenacao de
  imports, `target-version = &quot;py312&quot;`, e `TOBEDEFINED/` excluido.
- Passo de `ruff check` no workflow de CI.
- Formatacao: **nao** reformatar o repositorio inteiro junto com outra mudanca.
  Se `ruff format --check` exigir um diff grande, faca-o em commit proprio,
  mecanico, e registre o hash em `.git-blame-ignore-revs`; se o diff for
  invasivo demais, deixe o `format` fora do CI e registre a decisao aqui.
- Corrigir os achados do `ruff check` sem mudar comportamento; o que exigir
  mudanca de comportamento vira issue separada.
- Documentar os comandos no `README.MD` e no `CONTRIBUTING.md`.

## Criterios de aceitacao

- `uv run ruff check .` passa localmente e no CI.
- Nenhum commit mistura reformatacao com mudanca funcional.

## Dependencias

Depois de #148.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:31:47Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/149#issuecomment-6836497166)

<pre>Implementado localmente na branch `149-ruff` (base `integracao-saneamento`; sem push/PR).

**Mudancas**
- `ruff&gt;=0.15` no grupo `dev` do `pyproject.toml`, `uv.lock` atualizado (resolve ruff 0.17.5).
- `[tool.ruff]`: `target-version = &quot;py312&quot;`, `line-length = 88`, `extend-exclude = [&quot;TOBEDEFINED&quot;]`; lint com `select = [&quot;E4&quot;,&quot;E7&quot;,&quot;E9&quot;,&quot;F&quot;,&quot;I&quot;]` (conjunto padrao classico + isort, fixado explicitamente porque o ruff 0.17 ampliou os padroes e geraria 439 achados, muitos de estilo).
- Correcoes automaticas seguras (`--fix`, sem `--unsafe-fixes`): 102 achados em 88 arquivos (imports ordenados + F401 triviais), commit mecanico proprio.
- Manuais: `per-file-ignores` de E402 em 3 testes que inserem `backend/` em `sys.path` antes de importar `app` (intencional); `# noqa: F401` na sonda de disponibilidade do `arcade` em `tests/test_grid_view_scroll.py`. Nenhum achado exigiu mudar comportamento (nada a abrir como issue).
- `.github/workflows/tests.yml`: passo `uv run ruff check .` antes da suite. README.MD e CONTRIBUTING.md atualizados.

**Commits**: 9a438d3 (config+dependencia), segundo commit (line-length 88), commit mecanico de `--fix`, commit final (ci/docs/ignores); ver `git log 149-ruff`.

**Verificacao**: `uv run ruff check .` limpo; `uv run python -m unittest` = 732 testes, OK (skipped=42, expected failures=2), igual ao baseline.

**Formatador (decisao do grupo)**: `ruff format --check` com line-length 88: 76 de 295 arquivos seriam reformatados (~1234 linhas alteradas); com 100: 188 arquivos (~4264 linhas), por isso fixei 88. NAO reformatei nem pus `ruff format` no CI, para evitar conflito com #119, #120 e outras branches em andamento. Recomendacao: quando nao houver branches abertas grandes, fazer um unico commit `style: ruff format` em main/develop, registrar o hash em `.git-blame-ignore-revs` (e `git config blame.ignoreRevsFile .git-blame-ignore-revs`), e so entao adicionar `ruff format --check` ao CI. Os colegas devem rodar `ruff format` nas suas branches antes de rebasear.
</pre>

#### [@guilherme-webster em 2026-11-12T21:58:09Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/149#issuecomment-6837055146)

<pre>Mesclado em `develop` pelo PR #165. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:58:10Z — fechada por @guilherme-webster
- 2026-11-12T21:08:27Z — label adicionada: Task por @guilherme-webster

</details>

### [#150 — Teste de ponta a ponta do motor 2D (simulate_2d_race)](https://github.com/guilherme-webster/mc857-o-projeto/issues/150)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:27Z
- **Atualizada:** 2026-11-12T21:57:54Z
- **Fechada:** 2026-11-12T21:57:54Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

`domain/race_simulation_2d.py` e o unico motor e a fonte de verdade da
classificacao, mas nao tem teste dedicado de ponta a ponta; os testes atuais
cobrem pecas (`test_track_space`, `test_speed_dynamics`, `test_pit_lane`,
`test_dynamic_usage`).

## Escopo

Novo modulo de teste que roda `simulate_2d_race` com a geometria de
`tests/fixtures/trotman_v128_tracks_2025`, poucos carros e poucas voltas, e
verifica:

- **reprodutibilidade**: mesma semente e mesmos insumos dao `history`,
  `classification` e `race_control_events` identicos; sementes diferentes dao
  resultados diferentes;
- **invariantes**: cada piloto aparece uma vez na classificacao; posicoes sao
  1..N sem buracos; quem termina completou `total_laps`; voltas e tempos
  acumulados por carro nao decrescem; abandono tem motivo e volta;
- **efeitos opcionais**: sem `model_parameters` + `track_params` + `compounds`
  nao ha paradas; com eles ha ao menos uma troca numa corrida longa o bastante;
  com `FuelPlan` a massa de combustivel so diminui;
- **`on_progress`** e chamado uma vez por volta, em ordem.

## Criterios de aceitacao

- O modulo roda em poucos segundos e sem rede.
- As invariantes estao em helpers reutilizaveis pelos testes de regressao dos
  bugs #140 e #141.

## Fora de escopo

Mudar o motor. Uma invariante que falhe por comportamento real vira issue de bug.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:19:17Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/150#issuecomment-6836232203)

<pre>Implementado na branch local `150-teste-ponta-a-ponta-2d` (sem push), commit 599243b, a partir de develop 59bef6a.

- `tests/test_race_simulation_2d.py`: 11 testes sobre `simulate_2d_race` na geometria real do fixture `trotman_v128_tracks_2025` (circuito 1, 4 carros, 5 e 12 voltas, ~6 s, sem rede; corridas simuladas uma vez em setUpClass). Cobre reproducibilidade (history/classification/race_control_events; sementes diferentes via falha mecanica sorteada), invariantes de classificacao e history, abandono com causa e volta, ausencia de paradas sem model_parameters+track_params+compounds, parada na corrida longa, massa de combustivel nao crescente, efeitos de combustivel/pneu so em um sentido entre paradas, e on_progress uma vez por volta em ordem.
- `tests/race_invariants.py`: helpers reutilizaveis (geometria real, entrantes, FuelPlan de teste, assert_same_race, assert_classification_invariants, assert_history_invariants, stop_laps, breakdown_series, assert_effect_moves_only_with_stops, assert_fuel_never_increases) para os regressivos de #140 e #141.

Verificacao: suite completa sem httpx2 = 640 testes, 3 falhas, 22 erros (baseline 629 + 11 novos, mesmas falhas/erros pre-existentes); modulo novo passa 11/11.

Decisoes: o FuelPlan de teste e definido no helper porque `tests/test_fuel.py` esta quebrado no baseline (importa modulo removido) e test_dynamic_usage depende dele. Nenhuma invariante falhou, entao nao ha expectedFailure; as invariantes de #140/#141 passam com os parametros usados (nao reproduzem os bugs neste cenario), portanto os bugs podem depender de clima/controle de prova ou de outros parametros.
</pre>

#### [@guilherme-webster em 2026-11-12T21:57:53Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/150#issuecomment-6837049597)

<pre>Mesclado em `develop` pelo PR #158. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:57:54Z — fechada por @guilherme-webster
- 2026-11-12T21:08:28Z — label adicionada: Task por @guilherme-webster

</details>

### [#151 — Frontend: apagar a tela legada weather_view.py](https://github.com/guilherme-webster/mc857-o-projeto/issues/151)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:28Z
- **Atualizada:** 2026-11-12T21:57:56Z
- **Fechada:** 2026-11-12T21:57:56Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

`frontend/arcade/weather_view.py` (1291 linhas) contem `TrackConfigurationView`,
tela legada inalcancavel no fluxo atual. Ela so sobrevive porque outros modulos
reaproveitam pecas dela:

- `race_configuration_view.py:29` e `:915` usam `WEATHER_ICON_PATHS`,
  `WEATHER_TIMELINE_COLORS` e `TrackConfigurationView._draw_rounded_panel`;
- `simulation_loading_view.py:30` e `:573` usam `_draw_rounded_panel` e
  `WEATHER_TIMELINE_COLORS`;
- `tests/test_parameters_view.py` tem testes `test_weather_view_*` da tela legada.

## Escopo

- Mover `_draw_rounded_panel` para um modulo compartilhado de desenho e as
  constantes de clima para onde ja vive o estado de clima (ou `theme.py`).
- Apagar `weather_view.py` e os testes de GUI que exercitam apenas a tela legada.
- Antes de apagar, confirmar que nenhum comportamento da aba **Clima** de
  `race_configuration_view.py` depende de codigo que so existe na tela legada.

## Criterios de aceitacao

- `grep -rn &quot;weather_view&quot; frontend tests` vazio.
- A aba Clima e a tela de carregamento continuam com a mesma aparencia
  (conferir abrindo a aplicacao).

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (3)</summary>

#### [@guilherme-webster em 2026-11-12T21:16:51Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/151#issuecomment-6836179418)

<pre>Implementado na branch local `151-apagar-weather-view` (sem push).

Commits: ver `git log` da branch (2 commits: refactor de extracao e remocao).
- Extracao: `draw_rounded_panel` (+ `draw_rounded_rectangle`) em `frontend/arcade/drawing.py`; `WEATHER_TIMELINE_COLORS` e `WEATHER_ICON_PATHS` em `frontend/arcade/theme.py`; `race_configuration_view.py` atualizado. Mesma logica de desenho (codigo movido sem alteracao).
- Remocao: `frontend/arcade/weather_view.py` apagado e 8 testes que so exercitavam a tela legada removidos (o teste dos icones foi mantido). Nenhuma outra referencia no codigo.

Verificacoes: `uv run python -m unittest` -&gt; 247 testes, OK (27 skipped). Com `ARCADE_GUI_TEST=1`, test_parameters_view: 3 falhas/erros, identicos ao estado anterior as mudancas (test_visible_controls_add_track_and_confirm_sequence, test_large_window_draws_full_panels_and_maps_clicks, test_selects_another_backend_track_and_preserves_it_after_return), nao introduzidos aqui.

Notas: `simulation_loading_view.py` nao existe nesta base; a conferencia visual da aba Clima (pixels do painel) fica pendente para o usuario. `docs/CODEBASE_MAP.md` ainda cita weather_view.py (nao editado por instrucao).
</pre>

#### [@guilherme-webster em 2026-11-12T21:20:30Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/151#issuecomment-6836258372)

<pre>Correcao: meu comentario anterior foi feito sobre uma base errada e antiga (b9170b6); desconsidere os hashes dele. Refeito sobre develop (59bef6a), branch local `151-apagar-weather-view` (sem push):

- a4fbb2c refactor(frontend): extrai desenho de painel e constantes de clima da tela legada
  (`draw_rounded_panel` em `frontend/arcade/drawing.py`; `WEATHER_TIMELINE_COLORS`/`WEATHER_ICON_PATHS` em `theme.py`; consumidores migrados: `race_configuration_view.py` e `simulation_loading_view.py`)
- 2158d0d refactor(frontend): remove a tela legada weather_view
  (apaga `weather_view.py`, 8 testes so da tela legada e a linha do CODEBASE_MAP; mantido o teste dos icones)

Verificacao: grep sem referencias restantes a weather_view/TrackConfigurationView/WeatherConfigurationView em frontend/ e tests/.
Suite `uv run python -m unittest`: antes 629 testes (3 falhas, 22 erros, 51 skipped); depois 621 (3 falhas, 22 erros, 43 skipped) -- os 8 a menos sao os testes removidos; falhas/erros inalterados. Com ARCADE_GUI_TEST=1, tests.test_parameters_view: develop tem 4 falhas + 1 erro e a branch os mesmos 5 (preexistentes).
Pendente: conferencia visual da aba Clima e da tela de carregamento fica para o usuario.
</pre>

#### [@guilherme-webster em 2026-11-12T21:57:55Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/151#issuecomment-6837050374)

<pre>Mesclado em `develop` pelo PR #159. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:57:56Z — fechada por @guilherme-webster
- 2026-11-12T21:08:30Z — label adicionada: Task por @guilherme-webster

</details>

### [#152 — Arquivar os modulos orfaos de grid_start em TOBEDEFINED/](https://github.com/guilherme-webster/mc857-o-projeto/issues/152)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:30Z
- **Atualizada:** 2026-11-12T21:57:52Z
- **Fechada:** 2026-11-12T21:57:52Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

Desde a remocao do motor por volta, nao tem consumidor:

- `src/f1_simulator/domain/grid_start.py`;
- `src/f1_simulator/adapters/grid_start_parameters_json.py`;
- `data/parameters/grid-start-v1.json`;
- os testes correspondentes, se existirem.

O motor 2D larga em filas de dois por fisica.

## Decisao do responsavel (2026-11-12)

**Arquivar** (nao apagar) e **deixar indicado** que foi arquivado: a #108
(impacto da posicao de largada) pode querer reaproveitar o material.

## Escopo

- Mover os arquivos para `TOBEDEFINED/` com `git mv`, preservando o historico.
- Indicar o arquivamento: nota no topo de cada arquivo movido (data, motivo e
  esta issue), entrada no indice ou README de `TOBEDEFINED/` (criar se nao
  houver) e comentario na #108 apontando onde o material esta.
- Atualizar `docs/CODEBASE_MAP.md` (secoes 4.1, 4.4 e 7), que os lista como orfaos.

## Criterios de aceitacao

- `grep -rn &quot;grid_start&quot; src backend scripts tests` vazio.
- Suite verde.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:18:23Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/152#issuecomment-6836213049)

<pre>Arquivamento feito na branch local `152-arquivar-grid-start` (commit 8d0c2ff, sem push).

- Movidos com `git mv` para `TOBEDEFINED/` (layout plano, como os demais): `grid_start.py`, `grid_start_parameters_json.py`, `grid-start-v1.json`. O script de sensibilidade e `test_grid_start.py` ja estavam la.
- Nota de arquivamento (2026-11-12, motivo, #152, #108 pode reaproveitar) no topo dos dois .py. O JSON nao aceita comentario: a nota esta no novo `TOBEDEFINED/README.md` (indice com a origem de cada arquivo).
- `grep -rn grid_start src backend scripts tests frontend` vazio.
- `uv run python -m unittest`: 629 testes, 3 falhas, 22 erros, 51 skipped; nenhum relacionado a grid_start (restos do motor por volta e outras issues da rodada).
- NAO editei `docs/CODEBASE_MAP.md` (sera ajustado na #154). `docs/modelagem-heuristica.md` ainda cita os caminhos antigos; nao tocado.
- Imports dentro dos arquivos arquivados ainda apontam para os caminhos antigos; ajustar ao reativar.
</pre>

#### [@guilherme-webster em 2026-11-12T21:57:51Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/152#issuecomment-6837048943)

<pre>Mesclado em `develop` pelo PR #157. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:57:52Z — fechada por @guilherme-webster
- 2026-11-12T21:08:31Z — label adicionada: Task por @guilherme-webster

</details>

### [#153 — Progresso por volta na reexecucao de torneio salvo](https://github.com/guilherme-webster/mc857-o-projeto/issues/153)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** enhancement
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:31Z
- **Atualizada:** 2026-11-12T21:58:05Z
- **Fechada:** 2026-11-12T21:58:05Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

`frontend/arcade/saved_tournaments.py::rerun` usa o `POST /catalog/grid/run`
sincrono, entao a reexecucao de um torneio salvo nao mostra progresso. A
execucao normal ja usa o SSE `POST /catalog/grid/run/stream` atraves de
`race_launcher.HttpRaceClient.run_grid` e da `SimulationLoadingView`.

## Escopo

- Reexecutar um torneio salvo pelo mesmo caminho da execucao normal:
  `restore-grid` e, em seguida, as etapas pelo SSE, com a tela de carregamento
  (grid, etapa em foco, progresso por volta, abortar).
- Manter o fallback sincrono quando a rota de stream responder 404.
- Regras de apresentacao em modulo puro, testadas sem janela.

## Criterios de aceitacao

- Reexecutar mostra o progresso por volta e permite abortar entre etapas.
- A reexecucao continua reproduzindo os resultados salvos (mesmas sementes).
- Erro vindo como evento SSE `error` aparece para o usuario.

## Fora de escopo

Criar rota de reexecucao no backend (o ADR 0013 deixa a orquestracao no cliente).

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:21:06Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/153#issuecomment-6836271431)

<pre>Implementado localmente (sem push) na branch `153-progresso-reexecucao-torneio`, commit abaixo.

- `frontend/arcade/saved_tournaments.py`: `rerun` ganhou `stage_progress` (LaunchProgress por etapa e volta) e `cancelled` (LaunchCancelled entre etapas); novos `plan_from_record` e `rerun_runner`; `HttpTournamentClient.run_grid` usa `track_client.run_grid_stream` (SSE, com fallback sincrono em 404; evento `error` vira BackendError).
- `frontend/arcade/saved_tournaments_view.py`: Reexecutar carrega o registro e abre a `SimulationLoadingView` (grid salvo do registro, etapa em foco, progresso por volta, abortar); erro aparece na tela de carregamento e ao voltar na lista (`show_message`).
- Sem rota nova no backend. O `setup` salvo e reenviado intacto (mesmas sementes/indices); testado.
- Testes: 4 novos em tests/test_saved_tournaments_frontend.py (progresso, abortar, setups reenviados, plano) e teste de GUI atualizado (ARCADE_GUI_TEST=1, 3 OK).
- Suite sem httpx2: 633 testes, 3 falhas, 22 erros (baseline 629/3/22 + 4 novos); falhas restantes sao de outras issues. Nao consegui instalar httpx2 (bloqueado), entao test_saved_tournament ficou sem rodar.
- Pendente: conferencia visual real da tela.
</pre>

#### [@guilherme-webster em 2026-11-12T21:58:05Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/153#issuecomment-6837053658)

<pre>Mesclado em `develop` pelo PR #163. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:58:05Z — fechada por @guilherme-webster
- 2026-11-12T21:08:32Z — label adicionada: enhancement por @guilherme-webster

</details>

### [#154 — Docs: alinhar ADRs, handoffs e mapa ao estado atual do codigo](https://github.com/guilherme-webster/mc857-o-projeto/issues/154)

- **Estado:** fechada
- **Motivo do estado:** completed
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** documentation
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-11-12T21:08:32Z
- **Atualizada:** 2026-11-12T21:58:12Z
- **Fechada:** 2026-11-12T21:58:12Z

<details>
<summary>Descricao original</summary>

<pre>
## Contexto

Divergencias entre documentacao e codigo encontradas em 2026-11-12:

- `docs/adr/README.md` lista os ADRs 0009 e 0015 como &quot;proposta&quot;, embora
  estejam implementados. **Mudar status de ADR e decisao do grupo**: proponha a
  mudanca e peca confirmacao antes de aplicar.
- `docs/handoff-motor-2d.md` diz que o motor detalhado era o padrao.
- `docs/progresso.md` ainda tem handoffs das #119 e #120, ja mergeadas.
- `docs/prds/modelagem-pilotos-heuristica.md` cita caminhos de `TOBEDEFINED/`.
- `docs/CODEBASE_MAP.md`, secao 4.7, lista `test_fuel`, `test_fuel_strategy` e
  `test_dynamic_usage` como cobertura nova, mas eles nao importavam em
  `94e52ab`; revisar depois de #144 e #145.
- As issues #119 e #120 seguem abertas com o trabalho mergeado: conferir os
  criterios e sugerir o fechamento ao responsavel.

## Escopo

Corrigir os pontos acima; documentos historicos ganham nota de estado em vez de
serem reescritos. Nao editar `docs/backlog.md` a mao (espelho gerado).

## Criterios de aceitacao

- Nenhum documento vigente descreve o motor por volta como ativo.
- `docs/progresso.md` contem apenas handoffs pendentes.

## Dependencias

Por ultimo, depois de #145, #146 e #152.

## Como trabalhar

Leia `AGENTS.md` e `CONTRIBUTING.md` antes de comecar. Limite o diff a esta
issue, rode `uv run python -m unittest` ao final e registre aqui o resultado.
Commits so com autorizacao do usuario.
</pre>

</details>

<details>
<summary>Comentarios (2)</summary>

#### [@guilherme-webster em 2026-11-12T21:33:33Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/154#issuecomment-6836535264)

<pre>Implementado localmente (sem push) na branch `154-docs-alinhamento`, sobre `integracao-saneamento` (pos #144-#148 e #150-#153). So documentacao.

Commits:
- 0e3e8f4 docs(progresso): remove handoffs de issues ja mergeadas ou fechadas
- d306b5c docs(mapa): atualiza o CODEBASE_MAP ao estado pos-saneamento
- 6481426 docs(modelagem): aponta grid_start para TOBEDEFINED e registra limitacoes do 2D
- 9ec9994 docs: notas de estado sobre a remocao do motor por volta
- 7a46b6e docs(mapa): corrige a nota de gestao de pneus amortecida

O que mudou
- `docs/progresso.md`: removidos os handoffs das #119 e #120 (PRs #122 e #123 mergeados), #69, #101, #107 (fechadas) e o registro do motor 2D de 2026-10-01 (ADR 0011 aceito, motor unico). Restam so handoffs de issues abertas.
- `docs/CODEBASE_MAP.md`: grid_start em `TOBEDEFINED/`; secao 4.7 (testes novos, `fuel_support`, `geometry_support`, `race_invariants`, sem pytest); CI `tests.yml`; `drawing.py` no lugar de `weather_view.py`; sem seletor de motor; reexecucao de torneio salvo com SSE; limitacoes do 2D.
- `docs/modelagem-heuristica.md`: nota de estado, `grid_start`/adaptador/JSON apontando para `TOBEDEFINED/` com nota de arquivado, motor 2D e `run_grid_simulation` na tabela, limitacoes conhecidas do 2D em §9.
- Notas de estado curtas (2026-11-12) em `handoff-motor-2d.md`, `prds/modelagem-pilotos-heuristica.md`, `prds/controles-do-usuario-simulacao.md`, `contrato-perfil-simulacao.md`, `planejamento-modelagem.md`, `ranking-e-adaptador-pilotos.md`, `perfilamento-pilotos.md`, `modelagem-corrida-calibrada.md`, `consumo-desgaste-dinamicos.md`, `modelagem-clima.md`; `README.MD` deixa de descrever o seletor de motor.
- ADRs aceitos e `AGENTS.md` nao foram tocados.

Limitacoes conhecidas do 2D (registradas, sem decisao): nao reabastece nem faz lift-and-coast e todos largam com a mesma carga; assumption de gestao de pneus nao declarada; abandono sem disputa vira `mechanical`; em `speed_breakdown` a troca de pneu aparece defasada uma volta em relacao a parada.

Verificacao: `uv run python -m unittest` = 732 testes, OK (42 skipped, 2 expected failures).

## Proposta para o grupo (nao aplicada): status dos ADRs
- ADR 0009 (combustivel por massa): implementado (`domain/fuel.py`, `fuel-v1.json`, `HeuristicPitStrategy` com `FuelStatus`). Ressalva: o reabastecimento nao roda no 2D (`refuel_mode = False`); so a massa atua. Proposta: `aceita`, anotando essa ressalva (ou `aceita parcialmente`), conforme o grupo preferir.
- ADR 0015 (aderencia e estado da pista): implementado (`track_condition.py`, `speed_dynamics.py`, `car-physics-v1.json`, `calibrate_car_physics.py`, testes). Proposta: `aceita`.
- Peco confirmacao antes de alterar `docs/adr/README.md` e os cabecalhos dos ADRs (e a linha correspondente do CODEBASE_MAP, hoje marcada &quot;proposta no README; implementado&quot;).
- Ainda aberto, fora desta issue: ADR 0007 segue &quot;proposta, nao implementada; contexto a revisar&quot;.

## AGENTS.md (proposta, nao editado)
Descreve o estado correto (nao cita o motor por volta). Sem mudanca necessaria.

## #119 e #120
Trabalho mergeado (PRs #122 e #123). Conferencia de criterios feita no relatorio ao orquestrador; fechamento fica com os responsaveis.

Pendencias: `docs/progresso.md` ainda guarda handoffs de setembro/outubro (#40/#61/#66/#67, #24, #63, #97, #6) cujas issues estao abertas; nao removi sem confirmacao dos responsaveis.
</pre>

#### [@guilherme-webster em 2026-11-12T21:58:12Z](https://github.com/guilherme-webster/mc857-o-projeto/issues/154#issuecomment-6837056068)

<pre>Mesclado em `develop` pelo PR #166. Na integracao de todas as issues do epico #155: `uv run python -m unittest` com 732 testes OK (skipped=42, expected failures=2) e `ruff check` limpo; o workflow de testes passou no GitHub Actions nos PRs #165 e #166.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-11-12T21:58:12Z — fechada por @guilherme-webster
- 2026-11-12T21:08:34Z — label adicionada: documentation por @guilherme-webster

</details>
