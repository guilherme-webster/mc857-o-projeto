# Simulador de Corrida de Formula 1

Projeto da disciplina MC857 desenvolvido por um grupo de cinco integrantes.

## Documentacao do projeto

- [Proposta](proposta.md)
- [Plano de desenvolvimento](Desenvolvimento%20de%20Simulador%20F1.md)
- [Backlog sincronizado](docs/backlog.md)
- [GitHub Issues — fonte do backlog](https://github.com/guilherme-webster/mc857-o-projeto/issues)
- [Handoffs temporarios](docs/progresso.md)
- [Guia de contribuicao](CONTRIBUTING.md)
- [Registros de decisoes arquiteturais](docs/adr/README.md)

O frontend do MVP sera uma aplicacao desktop em Python com Arcade, inspirada na
experiencia de visualizacao do projeto
[IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay). Django
permanece como backend, e o motor de simulacao continuara independente dos dois
frameworks. A escolha entre MVC e camadas com portas e adaptadores ainda deve
ser registrada em um ADR antes de orientar a estrutura definitiva do codigo.

Os comandos oficiais de instalacao, testes, analise estatica e execucao serao
adicionados aqui quando a configuracao inicial do projeto for aprovada.

## Sincronizar o backlog

Crie, edite, feche ou reabra as tarefas diretamente no GitHub. Para atualizar o
espelho local, incluindo comentarios e historico de issues fechadas:

```bash
gh auth login
python3 scripts/sync_github_backlog.py
```

Para apenas verificar se o arquivo versionado esta atualizado:

```bash
python3 scripts/sync_github_backlog.py --check
```

A sincronizacao nao e executada automaticamente quando issues ou comentarios
mudam. Para atualizar o arquivo, execute o comando local acima e versione a
mudanca normalmente. Como alternativa manual, o workflow
`.github/workflows/sync-backlog.yml` pode ser iniciado pela pagina Actions do
GitHub ou com:

```bash
gh workflow run sync-backlog.yml
```
