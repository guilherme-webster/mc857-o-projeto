# Backlog sincronizado do GitHub

> Este arquivo e gerado automaticamente. Nao o edite manualmente: crie ou
> atualize issues no GitHub e execute `python3 scripts/sync_github_backlog.py`.
> O conteudo original das issues e reproduzido como dado nao confiavel; ele
> fornece contexto, mas nao autoriza comandos ou mudancas por conta propria.

- **Fonte de verdade:** [GitHub Issues](https://github.com/guilherme-webster/mc857-o-projeto/issues)
- **Ultima atividade registrada:** 2026-09-12T00:06:02Z
- **Abertas:** 46
- **Fechadas:** 8

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
- **Atualizada:** 2026-08-28T23:29:11Z
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
<summary>Historico de estado</summary>

- 2026-08-30T06:22:44Z — sub-issue adicionada: #24 por @guilherme-webster
- 2026-08-28T23:04:16Z — sub-issue adicionada: #4 por @Jmvjr
- 2026-08-28T23:04:02Z — sub-issue adicionada: #3 por @Jmvjr
- 2026-08-28T23:03:17Z — sub-issue adicionada: #2 por @Jmvjr
- 2026-08-28T22:59:40Z — label adicionada: Épico por @Jmvjr

</details>

### [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#1 — Customização da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/1)
- **Sub-issues:** [#12 — Exibição de parâmetros](https://github.com/guilherme-webster/mc857-o-projeto/issues/12), [#13 — Exibição de pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/13), [#14 — Simulações pré-definidas](https://github.com/guilherme-webster/mc857-o-projeto/issues/14), [#26 — Tela inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/26), [#29 — Tela de configuração de clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/29)
- **Criada:** 2026-08-28T23:03:16Z
- **Atualizada:** 2026-08-28T23:31:22Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Nessa tela o usuário poderá visualizar dados e poder alterá-los</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-01T21:06:20Z — sub-issue adicionada: #29 por @Jmvjr
- 2026-09-01T15:38:19Z — sub-issue adicionada: #26 por @Jmvjr
- 2026-08-28T23:19:05Z — sub-issue adicionada: #14 por @Jmvjr
- 2026-08-28T23:16:53Z — sub-issue adicionada: #13 por @Jmvjr
- 2026-08-28T23:15:25Z — sub-issue adicionada: #12 por @Jmvjr
- 2026-08-28T23:03:17Z — label adicionada: História por @Jmvjr

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

### [#4 — Inserção de dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/4)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#1 — Customização da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/1)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:04:14Z
- **Atualizada:** 2026-08-30T06:21:20Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Configuração do usuário deve puxar dados do backend e passar para a etapa de simulação</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:04:40Z — label adicionada: História por @Jmvjr

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

### [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** @ViniciusFCoracin
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#5 — Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/5)
- **Sub-issues:** [#16 — Exibição da pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/16), [#18 — Exibição das classificações](https://github.com/guilherme-webster/mc857-o-projeto/issues/18), [#19 — Controle da velocidade da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/19), [#21 — Exibição de condições da corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/21)
- **Criada:** 2026-08-28T23:06:03Z
- **Atualizada:** 2026-08-28T23:39:04Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O usuário deve conseguir visualizar a pista, os carros e as posições. </pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:39:04Z — atribuida: @ViniciusFCoracin por @ViniciusFCoracin
- 2026-08-28T23:36:19Z — sub-issue adicionada: #21 por @ViniciusFCoracin
- 2026-08-28T23:34:45Z — sub-issue adicionada: #19 por @ViniciusFCoracin
- 2026-08-28T23:34:10Z — sub-issue adicionada: #18 por @ViniciusFCoracin
- 2026-08-28T23:33:20Z — sub-issue adicionada: #16 por @ViniciusFCoracin
- 2026-08-28T23:06:44Z — label adicionada: História por @Jmvjr

</details>

### [#7 — Tela de loading](https://github.com/guilherme-webster/mc857-o-projeto/issues/7)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#5 — Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/5)
- **Sub-issues:** [#17 — Processamento da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/17), [#20 — Exibição do progresso da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/20)
- **Criada:** 2026-08-28T23:06:16Z
- **Atualizada:** 2026-08-28T23:22:16Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Usuário deve ser capaz de ver tela de loading enquanto simulação é computada.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:35:58Z — sub-issue adicionada: #20 por @DaviGabrielBC
- 2026-08-28T23:34:04Z — sub-issue adicionada: #17 por @DaviGabrielBC
- 2026-08-28T23:06:17Z — label adicionada: História por @Jmvjr

</details>

### [#8 — Rodar Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/8)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#5 — Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/5)
- **Sub-issues:** [#70 — Consumir dados da modelagem](https://github.com/guilherme-webster/mc857-o-projeto/issues/70), [#71 — Executar simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/71)
- **Criada:** 2026-08-28T23:06:39Z
- **Atualizada:** 2026-08-28T23:25:14Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>A simulação em si deve ser computada de maneira a exibir algo para o usuário. Isto deve ser feito antes de qualquer exibição em si para o usuário, de maneira a evitar problemas de performance.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T23:54:52Z — sub-issue adicionada: #71 por @guilherme-webster
- 2026-09-11T23:54:09Z — sub-issue adicionada: #70 por @guilherme-webster
- 2026-08-28T23:06:41Z — label adicionada: História por @Jmvjr

</details>

### [#9 — Resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/9)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#10 — Tela de resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/10), [#11 — Armazenamento de dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/11)
- **Criada:** 2026-08-28T23:07:00Z
- **Atualizada:** 2026-08-28T23:32:58Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O usuário deve conseguir ver a tela com os resultados finais da simulação.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:08:16Z — sub-issue adicionada: #11 por @Jmvjr
- 2026-08-28T23:07:16Z — sub-issue adicionada: #10 por @Jmvjr
- 2026-08-28T23:07:01Z — label adicionada: Épico por @Jmvjr

</details>

### [#10 — Tela de resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/10)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#9 — Resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/9)
- **Sub-issues:** [#23 — Resultado final da corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/23)
- **Criada:** 2026-08-28T23:07:15Z
- **Atualizada:** 2026-08-28T23:15:26Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O usuário deve conseguir visualizar os resultados da simulação requisitada</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:48:15Z — sub-issue adicionada: #23 por @DaviGabrielBC
- 2026-08-28T23:07:17Z — label adicionada: História por @Jmvjr

</details>

### [#11 — Armazenamento de dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/11)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#9 — Resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/9)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:08:15Z
- **Atualizada:** 2026-08-28T23:28:43Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>É necessário armazenar internamente os resultados e processá-los para que os resultados possam chegar ao usuário.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:08:29Z — label adicionada: História por @Jmvjr

</details>

### [#12 — Exibição de parâmetros](https://github.com/guilherme-webster/mc857-o-projeto/issues/12)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:15:24Z
- **Atualizada:** 2026-08-28T23:38:49Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O usuário deve conseguir visualizar e alterar aos parâmetros configuráveis da corrida.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:38:49Z — atribuida: @Jmvjr por @Jmvjr
- 2026-08-28T23:15:25Z — label adicionada: Task por @Jmvjr

</details>

### [#13 — Exibição de pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/13)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:16:51Z
- **Atualizada:** 2026-08-28T23:38:43Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O usuário deve poder visualizar a pista selecionada</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:38:43Z — atribuida: @Jmvjr por @Jmvjr
- 2026-08-28T23:16:53Z — label adicionada: Task por @Jmvjr

</details>

### [#14 — Simulações pré-definidas](https://github.com/guilherme-webster/mc857-o-projeto/issues/14)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Jmvjr
- **Responsaveis:** @Jmvjr
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#2 — Tela de configuração](https://github.com/guilherme-webster/mc857-o-projeto/issues/2)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:19:03Z
- **Atualizada:** 2026-08-28T23:38:53Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O usuário deve poder escolher simulações já existentes como base</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:38:53Z — atribuida: @Jmvjr por @Jmvjr
- 2026-08-28T23:19:04Z — label adicionada: Task por @Jmvjr

</details>

### [#15 — Simulação puxa dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/15)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#5 — Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/5)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:24:35Z
- **Atualizada:** 2026-08-28T23:32:08Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Antes de rodar, a simulação deve puxar dados do backend de maneira coerente com a configuração setada para o usuário. Então, estes dados são consumidos pelo motor do sistema que irá executar a simulação.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:32:08Z — label adicionada: História por @guilherme-webster

</details>

### [#17 — Processamento da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/17)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @DaviGabrielBC
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#7 — Tela de loading](https://github.com/guilherme-webster/mc857-o-projeto/issues/7)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:34:03Z
- **Atualizada:** 2026-08-28T23:36:11Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>A simulação deve ser processada do seu início ao fim no back-end.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:36:11Z — label adicionada: Task por @DaviGabrielBC

</details>

### [#18 — Exibição das classificações](https://github.com/guilherme-webster/mc857-o-projeto/issues/18)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:34:08Z
- **Atualizada:** 2026-08-28T23:43:44Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>A tela de simulação deve exibir a classificação dos pilotos de forma dinâmica ao longo da corrida.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:36:48Z — label adicionada: Task por @ViniciusFCoracin

</details>

### [#19 — Controle da velocidade da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/19)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:34:43Z
- **Atualizada:** 2026-08-28T23:40:23Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O usuário deve ser capaz de controlar a velocidade com que a simulação é exibida na tela (exemplo: exibir a corrida em tempo real, exibir em 10x, 50x etc).</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:36:55Z — label adicionada: Task por @ViniciusFCoracin

</details>

### [#20 — Exibição do progresso da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/20)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @DaviGabrielBC
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#7 — Tela de loading](https://github.com/guilherme-webster/mc857-o-projeto/issues/7)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:35:56Z
- **Atualizada:** 2026-08-28T23:35:56Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>O usuário será informado do progresso da simulação, sabendo quão próxima está de concluida.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:35:57Z — label adicionada: Task por @DaviGabrielBC

</details>

### [#21 — Exibição de condições da corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/21)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @ViniciusFCoracin
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#6 — Tela de simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/6)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:36:18Z
- **Atualizada:** 2026-08-28T23:41:19Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>A tela de simulação deve exibir as condições da corrida, como por exemplo o clima, o tempo de corrida, se há bandeira amarela/vermelha etc).</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:37:02Z — label adicionada: Task por @ViniciusFCoracin

</details>

### [#22 — teste](https://github.com/guilherme-webster/mc857-o-projeto/issues/22)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:45:38Z
- **Atualizada:** 2026-09-04T22:15:18Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-04T22:15:18Z — responsavel removido: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji
- 2026-09-03T23:50:41Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji

</details>

### [#23 — Resultado final da corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/23)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @DaviGabrielBC
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#10 — Tela de resultados](https://github.com/guilherme-webster/mc857-o-projeto/issues/10)
- **Sub-issues:** —
- **Criada:** 2026-08-28T23:48:14Z
- **Atualizada:** 2026-08-28T23:48:14Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Na tela de resultados, o usuário poderá visualizar uma tabela contendo o ranque e os tempos finais de todos os jogadores</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-08-28T23:48:16Z — label adicionada: Task por @DaviGabrielBC

</details>

### [#24 — ETL inicial](https://github.com/guilherme-webster/mc857-o-projeto/issues/24)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#1 — Customização da simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/1)
- **Sub-issues:** [#30 — implementar race data repository](https://github.com/guilherme-webster/mc857-o-projeto/issues/30), [#31 — implementar SQLiteRaceDataRepository](https://github.com/guilherme-webster/mc857-o-projeto/issues/31), [#32 — implementar GetSimulationScenario](https://github.com/guilherme-webster/mc857-o-projeto/issues/32), [#34 — Implementar ETL para criação da pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/34), [#53 — implementar etl para dados de pista](https://github.com/guilherme-webster/mc857-o-projeto/issues/53)
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

### [#36 — Setup de Infraestrutura &amp; DevOps](https://github.com/guilherme-webster/mc857-o-projeto/issues/36)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#37 — Docker - conteinerizar a aplicação](https://github.com/guilherme-webster/mc857-o-projeto/issues/37), [#38 — Configurar CI](https://github.com/guilherme-webster/mc857-o-projeto/issues/38), [#39 — Padronização e Qualidade de Código](https://github.com/guilherme-webster/mc857-o-projeto/issues/39)
- **Criada:** 2026-09-04T00:07:17Z
- **Atualizada:** 2026-09-04T00:10:50Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Configurar a infraestrutura do projeto, garantindo um ambiente de desenvolvimento padronizado entre os integrantes do grupo e a automação de validações de código.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-04T00:16:18Z — sub-issue adicionada: #39 por @Gustavo-Jun-Tsuji
- 2026-09-04T00:15:03Z — sub-issue adicionada: #38 por @Gustavo-Jun-Tsuji
- 2026-09-04T00:12:30Z — sub-issue adicionada: #37 por @Gustavo-Jun-Tsuji
- 2026-09-04T00:07:17Z — label adicionada: Épico por @Gustavo-Jun-Tsuji

</details>

### [#37 — Docker - conteinerizar a aplicação](https://github.com/guilherme-webster/mc857-o-projeto/issues/37)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#36 — Setup de Infraestrutura &amp; DevOps](https://github.com/guilherme-webster/mc857-o-projeto/issues/36)
- **Sub-issues:** —
- **Criada:** 2026-09-04T00:12:28Z
- **Atualizada:** 2026-09-04T22:14:50Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>conteinerizar o backend e o frontend com Docker para padronizar o ambiente de desenvolvimento e execução.</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-04T22:14:50Z — label adicionada: História por @Gustavo-Jun-Tsuji
- 2026-09-04T00:39:57Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji

</details>

### [#38 — Configurar CI](https://github.com/guilherme-webster/mc857-o-projeto/issues/38)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** @Gustavo-Jun-Tsuji
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#36 — Setup de Infraestrutura &amp; DevOps](https://github.com/guilherme-webster/mc857-o-projeto/issues/36)
- **Sub-issues:** —
- **Criada:** 2026-09-04T00:15:02Z
- **Atualizada:** 2026-09-04T22:14:57Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>configurar um pipeline de Integração Contínua (CI) para validar builds, linters e testes 

Esse ticket será um constante lembrete de implementar boas práticas de CI</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-04T22:14:57Z — label adicionada: História por @Gustavo-Jun-Tsuji
- 2026-09-04T00:42:15Z — marcada como duplicada por @Gustavo-Jun-Tsuji
- 2026-09-04T00:17:34Z — atribuida: @Gustavo-Jun-Tsuji por @Gustavo-Jun-Tsuji

</details>

### [#39 — Padronização e Qualidade de Código](https://github.com/guilherme-webster/mc857-o-projeto/issues/39)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#36 — Setup de Infraestrutura &amp; DevOps](https://github.com/guilherme-webster/mc857-o-projeto/issues/36)
- **Sub-issues:** —
- **Criada:** 2026-09-04T00:16:17Z
- **Atualizada:** 2026-09-04T22:15:04Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>padronizar o estilo de código e validações pré-commit para evitar inconsistências e erros de sintaxe no repositório</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-04T22:15:04Z — label adicionada: História por @Gustavo-Jun-Tsuji

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

### [#41 — Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/41)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** Épico
- **Milestone:** —
- **Issue-pai:** —
- **Sub-issues:** [#43 — Criar endpoints](https://github.com/guilherme-webster/mc857-o-projeto/issues/43), [#47 — Carregar trotman no container](https://github.com/guilherme-webster/mc857-o-projeto/issues/47), [#54 — Carregar dados de pista no container](https://github.com/guilherme-webster/mc857-o-projeto/issues/54)
- **Criada:** 2026-09-04T23:02:55Z
- **Atualizada:** 2026-09-04T23:03:36Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Endpoints, integração com o front, fornecer arquivo de reprodução da simulação</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T20:24:01Z — sub-issue adicionada: #54 por @guilherme-webster
- 2026-09-05T19:56:27Z — sub-issue adicionada: #47 por @Gustavo-Jun-Tsuji
- 2026-09-05T16:38:00Z — sub-issue adicionada: #43 por @Gustavo-Jun-Tsuji
- 2026-09-04T23:02:57Z — label adicionada: Épico por @Gustavo-Jun-Tsuji

</details>

### [#43 — Criar endpoints](https://github.com/guilherme-webster/mc857-o-projeto/issues/43)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#41 — Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/41)
- **Sub-issues:** —
- **Criada:** 2026-09-05T16:37:59Z
- **Atualizada:** 2026-09-05T16:38:09Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-05T16:38:09Z — label adicionada: História por @Gustavo-Jun-Tsuji

</details>

### [#47 — Carregar trotman no container](https://github.com/guilherme-webster/mc857-o-projeto/issues/47)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @Gustavo-Jun-Tsuji
- **Responsaveis:** —
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#41 — Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/41)
- **Sub-issues:** —
- **Criada:** 2026-09-05T19:56:26Z
- **Atualizada:** 2026-09-05T19:56:38Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-05T19:56:38Z — label adicionada: Task por @Gustavo-Jun-Tsuji

</details>

### [#51 — Pistas de corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/51)

- **Estado:** aberta
- **Motivo do estado:** reopened
- **Autor:** @Jmvjr
- **Responsaveis:** @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#40 — Modelagem dos dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/40)
- **Sub-issues:** —
- **Criada:** 2026-09-08T22:18:07Z
- **Atualizada:** 2026-09-11T22:35:07Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Mockagem de dados para representação de pistas</pre>

</details>

<details>
<summary>Comentarios (11)</summary>

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

</details>

<details>
<summary>Historico de estado</summary>

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

### [#54 — Carregar dados de pista no container](https://github.com/guilherme-webster/mc857-o-projeto/issues/54)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** —
- **Milestone:** —
- **Issue-pai:** [#41 — Backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/41)
- **Sub-issues:** —
- **Criada:** 2026-09-11T20:24:00Z
- **Atualizada:** 2026-09-11T20:24:00Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

### [#60 — Carros](https://github.com/guilherme-webster/mc857-o-projeto/issues/60)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#40 — Modelagem dos dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/40)
- **Sub-issues:** [#64 — Consumo do backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/64), [#65 — Modelagem posterior](https://github.com/guilherme-webster/mc857-o-projeto/issues/65)
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
- **Sub-issues:** [#68 — Consumir backend para modelar clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/68), [#69 — Modelagem clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/69)
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
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:22:10Z
- **Atualizada:** 2026-09-11T22:33:26Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:33:26Z — atribuida: @guilherme-webster por @guilherme-webster
- 2026-09-11T22:33:26Z — label adicionada: Task por @guilherme-webster

</details>

### [#64 — Consumo do backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/64)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#60 — Carros](https://github.com/guilherme-webster/mc857-o-projeto/issues/60)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:26:45Z
- **Atualizada:** 2026-09-11T22:26:45Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>consumir interface do backend para modelagem posterior dos carros</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:26:46Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:26:45Z — atribuida: @guilherme-webster por @guilherme-webster

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

### [#66 — Consumir backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/66)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#61 — Pilotos](https://github.com/guilherme-webster/mc857-o-projeto/issues/61)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:28:39Z
- **Atualizada:** 2026-09-11T22:32:45Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Consumir dados do backend para termos dados de pilotos</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:32:45Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:32:40Z — atribuida: @guilherme-webster por @guilherme-webster

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
- **Atualizada:** 2026-09-11T22:33:16Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>modelagem posterior para os pilotos</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:33:16Z — label adicionada: Task por @guilherme-webster

</details>

### [#68 — Consumir backend para modelar clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/68)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#62 — Clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/62)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:31:03Z
- **Atualizada:** 2026-09-11T22:31:03Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>(sem descricao)</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:31:05Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:31:04Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#69 — Modelagem clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/69)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** @guilherme-webster
- **Labels:** Task
- **Milestone:** —
- **Issue-pai:** [#62 — Clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/62)
- **Sub-issues:** —
- **Criada:** 2026-09-11T22:31:25Z
- **Atualizada:** 2026-09-11T22:33:46Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>modelagem posterior para os clima</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T22:33:46Z — label adicionada: Task por @guilherme-webster
- 2026-09-11T22:33:42Z — atribuida: @guilherme-webster por @guilherme-webster

</details>

### [#70 — Consumir dados da modelagem](https://github.com/guilherme-webster/mc857-o-projeto/issues/70)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#8 — Rodar Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/8)
- **Sub-issues:** —
- **Criada:** 2026-09-11T23:54:08Z
- **Atualizada:** 2026-09-11T23:54:57Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Consome dados da etapa de modelagem para rodar a simulação em si</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T23:54:57Z — label adicionada: História por @guilherme-webster

</details>

### [#71 — Executar simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/71)

- **Estado:** aberta
- **Motivo do estado:** —
- **Autor:** @guilherme-webster
- **Responsaveis:** —
- **Labels:** História
- **Milestone:** —
- **Issue-pai:** [#8 — Rodar Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/8)
- **Sub-issues:** —
- **Criada:** 2026-09-11T23:54:51Z
- **Atualizada:** 2026-09-11T23:54:51Z
- **Fechada:** —

<details>
<summary>Descricao original</summary>

<pre>Roda a simulação da corrida em geral, que usufrui da modelagem da etapa anterior e modela a corrida em geral</pre>

</details>

<details>
<summary>Historico de estado</summary>

- 2026-09-11T23:54:52Z — label adicionada: História por @guilherme-webster

</details>

## Issues fechadas

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
