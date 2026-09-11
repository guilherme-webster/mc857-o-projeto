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

O frontend do MVP sera uma aplicacao desktop em Python com Arcade, inspirada na
experiencia de visualizacao do projeto
[IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay). FastAPI 
será o backend, e o motor de simulacao continuara independente dos dois
frameworks. O
[ADR 0002](docs/adr/0002-arquitetura-hexagonal-e-integracao-de-dados.md)
estabelece arquitetura hexagonal, integracao de dados com Adapter + Factory e a
base Formula 1 Race Data, de James Trotman, como fonte inicial unica do MVP.

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

### Geometrias mockadas das pistas

A fixture `tests/fixtures/trotman_v128_tracks_2025/` contém as polilinhas das
24 pistas do calendário de 2025 e seus pit lanes. Cada pit lane inclui um ponto
de serviço representativo. Os dados foram derivados offline do FastF1; cache,
telemetria bruta e scripts de geração não fazem parte do repositório. Consulte
o ADR 0003 e os manifestos em `data/sources/` para proveniência, transformação
e limitações de uso. O visualizador temporário usado para inspecionar os mocks
também não faz parte do repositório.

Para incluir os tracos e pit lanes mockados da issue #51 no mesmo SQLite,
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
Os mocks das 24 pistas continuam disponiveis para outras corridas suportadas.

X/Y sao normalizados e sem unidade; distancia acumulada da pista e em metros.
Os mocks sao de 2025: seu uso com uma corrida de outro ano fica explicito no
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
voltas. O botao de inicio valida o formulario, mas a conexao com Django e com o
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
