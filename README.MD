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
- [Fluxo e responsabilidades do ETL](docs/fluxo-etl.md)
- [ETL completo: Trotman e FastF1](docs/etl-enriquecimento.md)
- [Proposta de planejamento da modelagem](docs/planejamento-modelagem.md)
- [Modelagem calibrada da corrida e validacao](docs/modelagem-corrida-calibrada.md)
- [Dados e plano de perfilamento dos pilotos](docs/perfilamento-pilotos.md)

O frontend do MVP sera uma aplicacao desktop em Python com Arcade, inspirada na
experiencia de visualizacao do projeto
[IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay). FastAPI 
será o backend, e o motor de simulacao continuara independente dos dois
frameworks. O
[ADR 0002](docs/adr/0002-arquitetura-hexagonal-e-integracao-de-dados.md)
estabelece arquitetura hexagonal, integracao de dados com Adapter + Factory e a
base Formula 1 Race Data, de James Trotman, como fonte inicial. O
[ADR 0005](docs/adr/0005-historico-completo-e-enriquecimento-fastf1.md) amplia o ETL para
o historico completo e observacoes complementares do FastF1.

## 📦 Pré-requisitos e Dependências

Antes de iniciar a execução do projeto, certifique-se de possuir as ferramentas abaixo instaladas no seu ambiente.

---

### 1. Docker & Docker Compose

* **Instalação:**
  * **Windows / macOS:** Baixe e instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/). No Windows, certifique-se de habilitar a integração com o WSL2 durante o assistente.
  * **Linux (Ubuntu/Debian):**
    ```bash
    curl -fsSL [https://get.docker.com](https://get.docker.com) | sh
    sudo usermod -aG docker $USER
    ```

* **Como verificar se está instalado:**
  ```bash
  docker --version
  docker compose version

### 2. uv (Gerenciador de Pacotes e Python)

* **Instalação:**
  * **Windows (PowerShell / WinGet):**
    ```powershell
    winget install astral-sh.uv
    ```
  * **Linux / macOS / WSL:**
    ```bash
    curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
    ```

* **Como verificar se está instalado:**
  ```bash
  uv --version

## ETL da Base Trotman

O fluxo abaixo importa uma corrida. Para os 14 CSVs completos, usar
`python3 scripts/ingest_trotman.py --all-tables --output data/curated/history.sqlite`.
O [guia de enriquecimento](docs/etl-enriquecimento.md) mostra aquisicao FastF1,
contratos Python, relatorios internos e limites de cobertura.

Baixe e verifique o arquivo bruto da versao 128:

```bash
python3 scripts/download_trotman.py
```

Converta uma corrida para o esquema canonico em SQLite. O `raceId` 1141 e usado
apenas como exemplo reproduzivel da corrida de Sao Paulo de 2024; a corrida
oficial do MVP ainda deve ser escolhida pelo grupo.

```bash
python3 scripts/ingest_trotman.py \
  --race-id 1141 \
  --output data/curated/race-1141.sqlite \
  --report data/curated/race-1141-quality.json
```

Arquivos em `data/raw/` e `data/curated/` sao locais e ignorados pelo Git. A
origem, versao, licenca e checksum esperado estao registrados em
`data/sources/trotman-v128.json`.

O SQLite gerado contem `metadata`, `source_ids`, `circuits`, `drivers`, `teams`,
`races`, `race_entries`, `laps` e `pit_stops`. Tempos sao armazenados em
milissegundos e ausencias permanecem `NULL`. O JSON de qualidade registra
contagens, nulos, duplicatas, referencias orfas e pit stops anormalmente longos.

### Geometrias das pistas derivadas do FastF1

O termo historico "mock" identifica aqui uma aproximacao derivada de dados
reais, nao coordenadas inventadas. O ponto de servico e representativo; os
tracados nao fornecem limites oficiais, aderencia ou parametros de pilotos.

A fixture `tests/fixtures/trotman_v128_tracks_2025/` contém as polilinhas das
24 pistas do calendário de 2025 e seus pit lanes. Cada pit lane inclui um ponto
de serviço representativo. Os dados foram derivados offline do FastF1; cache,
telemetria bruta e scripts de geração não fazem parte do repositório. Consulte
o ADR 0003 e os manifestos em `data/sources/` para proveniência, transformação
e limitações de uso. O visualizador temporário usado para inspecionar as geometrias
também não faz parte do repositório.

Para incluir os tracos e pit lanes derivados da issue #51 no mesmo SQLite,
acrescente `--geometry-dir` ao comando de ingestao:

```bash
python3 scripts/ingest_trotman.py \
  --source tests/fixtures/trotman_v128_sample \
  --race-id 1141 \
  --geometry-dir tests/fixtures/trotman_v128_tracks_2025 \
  --output data/curated/race-1141-geometry.sqlite \
  --report data/curated/race-1141-geometry-quality.json
```

Esse exemplo usa a amostra pequena de corrida. Para processar os dados completos,
omita `--source` depois de baixar o Trotman v128. O comando importa apenas a
geometria do circuito da corrida, validando ambos os CSVs e seus manifestos.
As geometrias das 24 pistas continuam disponiveis para outras corridas suportadas.

X/Y sao normalizados e sem unidade; distancia acumulada da pista e em metros.
As geometrias sao de 2025: seu uso com uma corrida de outro ano fica explicito no
relatorio. Consulte o [contrato de consumo](docs/fluxo-etl.md#geometria-de-pista-e-pit-lane)
para ler as novas tabelas com `SQLiteTrackGeometryRepository`.

Execute os testes sem instalar dependencias adicionais:

```bash
python3 -m unittest -v
```

O projeto usa o layout `src`: o pacote `f1_simulator` fica dentro dessa pasta,
mas ainda nao e instalado no ambiente Python. A suite configura esse caminho em
`tests/__init__.py`. Para importar o pacote em um comando Python avulso, informe
o caminho explicitamente:

```bash
PYTHONPATH=src python3 -c "from f1_simulator.domain.race_data import RaceData"
```

## Como Executar a Aplicação

Você pode executar a aplicação completa (comunicação Frontend + Backend) ou rodar as camadas isoladamente dependendo da etapa de desenvolvimento.

---

### Opção 1: Aplicação Completa (Frontend + Backend)

1. **Sincronize o ambiente local:**
   ```powershell
   uv sync
   ```

2. **Execute o inicializador:**
   ```powershell
   uv run python run.py
   ```
   * O backend estará acessível em: `http://localhost:8000`
   * Documentação da API (Swagger): `http://localhost:8000/docs`
   * A janela da interface Arcade abrirá automaticamente assim que os serviços estiverem prontos.

---

### Opção 2: Somente o Frontend (Telas e Simulação Visual)

1. **Sincronize o ambiente local:**
   ```powershell
   uv sync
   ```

2. **Execute a tela desejada:**
   * **Tela principal de parâmetros:**
     ```powershell
     uv run python -m frontend.arcade
     ```
   * **Visualização da corrida (Renderização de Pista):**
     ```powershell
     uv run python -m frontend.arcade.race_view
     ```

---

### Opção 3: Somente o Backend (FastAPI e Banco de Dados)

* **Subir em primeiro plano (com logs interativos):**
  ```bash
  docker compose up --build
  ```

* **Subir em segundo plano (detached mode):**
  ```bash
  docker compose up -d
  ```

* **Parar o backend:**
  ```bash
  docker compose down
  ```

## Telas implementadas com Arcade

### Tela inicial

A `ParametersView` apresenta os dados historicos da corrida de referencia como
somente leitura e permite alterar o numero de voltas. O botao de clima abre uma
segunda `arcade.View`, na qual uma condicao pode ser aplicada a intervalos de
voltas. O botao de inicio valida o formulario, mas a conexao com FastAPI e com o
motor pertence a um incremento posterior.

### Tela de simulação da corrida

Por enquanto, a simulação da corrida consiste de uma pista oval e dois carros
com velocidade constante

## Git Actions

### Sincronizar o backlog

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

### Regras de pull request

Por exemplo, apenas a develop pode ser mergeada na main

## Modelagem inicial de pilotos

O [guia da modelagem inicial](docs/modelagem-pilotos-inicial.md) descreve o caso
de uso Python `profile_drivers`, as métricas de ritmo/consistência, os filtros
explícitos e a CLI com gráficos opcionais. Consome o histórico enriquecido sem
HTTP. O método é exploratório e não representa calibração do motor.

A [avaliação de perfis entre eventos](docs/avaliacao-perfis-entre-eventos.md)
usa o protocolo em `configs/profile-evaluation-2024.json`. Execute
`pipenv run python -B scripts/evaluate_profiles.py --database data/curated/history-profile-evaluation-2024.sqlite --plan configs/profile-evaluation-2024.json`.
A saída é uma pasta nova com relatório, JSON, CSVs e gráficos; não exige
redirecionar o JSON nem remover resultados anteriores.

A [análise de sensibilidade dos contextos](docs/sensibilidade-contextos-pilotos.md)
compara agrupamento por stint e janela de voltas, mostrando cobertura e
intervalos exploratórios por evento nos gráficos:

```bash
pipenv run python -B scripts/analyze_profile_contexts.py \
  --database data/curated/history-profile-evaluation-2024.sqlite \
  --plan configs/profile-evaluation-2024.json
```

O [contrato dos efeitos do perfil](docs/contrato-perfil-simulacao.md) especifica
ritmo, variabilidade, unidades e critérios da futura integração com o motor.
A [amostra expandida de 2024](docs/amostra-pilotos-2024-expandida.md) separa
18 corridas de desenvolvimento e seis reservadas antes de consultar métricas
novas; o guia contém os comandos de aquisição pelo ETL existente.

A [avaliação da reserva de 2024](docs/avaliacao-reserva-pilotos-2024.md) registra
os resultados dos seis eventos e a investigação de contexto, suporte e diferenças
entre grupos. A reserva foi examinada em 18/09/2026; não reutilizá-la como inédita.

A [comparação entre companheiros e referência determinística](docs/companheiros-e-referencia-deterministica.md)
usa contextos compartilhados, apresenta suporte e intervalos e exporta referências
de tempo específicas por circuito/sessão. Execute `scripts/analyze_teammates.py`
conforme os comandos do guia; a integração ao motor permanece posterior.

## Modelo de corrida calibrado

O núcleo da simulação deixou de usar ritmo constante por carro. O tempo de
volta agora é decomposto em referência, combustível, pneu, tráfego, perda de
boxes e ruído, com abandono sorteado por volta. Os coeficientes são estimados
do histórico Trotman e gravados versionados em `data/parameters/`.

```bash
python3 scripts/ingest_trotman.py --all-tables --output data/curated/history.sqlite
python3 scripts/calibrate_model.py --database data/curated/history.sqlite \n  --seasons 2022 2023 --output data/parameters/model-v1.json
```

Valide contra corridas que não entraram na calibração. O script recusa
validar sobre uma temporada calibrada sem `--allow-calibrated-seasons`:

```bash
python3 scripts/backtest_model.py --database data/curated/history.sqlite \n  --parameters data/parameters/model-v1.json --seasons 2024 --repeats 10
```

Cada corrida é comparada com duas linhas de base (ordem de largada e o modelo
antigo de ritmo constante); o modelo só se justifica se vencer as duas. O
[relatório da modelagem](docs/modelagem-corrida-calibrada.md) traz método,
coeficientes, resultados de 2024 e limitações.

`POST /simulation/simulate` aceita `?seed=` e `?stops=`; a mesma semente, os
mesmos parâmetros e os mesmos dados reproduzem exatamente a mesma corrida.

## Ver uma corrida sem frontend

`scripts/race_report.py` roda uma corrida e explica o resultado usando só a
biblioteca padrão do Python: sem instalação, sem ambiente virtual, sem
container. Liste as corridas de uma temporada e depois rode uma delas:

```bash
python3 scripts/race_report.py --season 2024
```

```bash
python3 scripts/race_report.py --race-id 1141 --driver Verstappen
```

O relatório traz a classificação comparada com o resultado oficial, a
evolução das posições, as paradas e a decomposição do tempo de volta
(referência, combustível, pneu, tráfego, boxes e ruído) volta a volta.

Com `--html` o mesmo comando grava um visualizador autocontido, que abre no
navegador com duplo clique e anima a corrida sobre a geometria real do
circuito, com torre de tempos e gráfico de voltas:

```bash
python3 scripts/race_report.py --race-id 1141 --html data/reports/corrida.html
```

O modelo da página fica em `tools/race_viewer_template.html`; os dados são
embutidos no arquivo gerado porque navegadores bloqueiam `fetch` de `file://`.

## Ranking de pilotos e adaptador para simulação

O [guia de ranking e integração Python](docs/ranking-e-adaptador-pilotos.md)
descreve a ordenação por ritmo observado, geração de gráficos e o contrato
para executar o primeiro experimento determinístico de uma volta.
