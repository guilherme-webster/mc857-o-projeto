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

Na interface Arcade, a primeira tela (1672 × 900) configura as regras do
torneio e consulta `GET /simulation/tracks`. Use as setas para percorrer as
pistas, **Adicionar à sequência** para inclui-las na ordem desejada e arraste
as linhas da lista para reordenar. Tambem e possivel gerar uma sequencia
automatica reproduzivel a partir do nome do torneio. Clique na previa da
pista para abrir a segunda tela, de configuracao da corrida. Nela, a aba
**Clima** edita os intervalos na propria tela, por campos ou pintando a timeline;
**Pista**, **Regras** e
**Carros** permanecem apenas como areas futuras. A geometria da previa vem de
`GET /simulation/track/{circuit_id}`. A configuracao padrao e **Corrida livre**:
nao exige escolher um GP historico. **Confirmar torneio** produz um plano
validado; a interface ainda nao contem o editor de participantes nem a tela
de reproducao dessa sequencia.

Para executar a sequencia pela API, envie as pistas em ordem a
`POST /simulation/series/simulate` com `circuit_id`, `total_laps` (1 a 200) e
participantes com `driver_id`, `name` e `pace_ms_per_km` (ritmo em ms/km). Exemplo:

```json
{
  "tracks": [
    {"circuit_id": "circuit:18", "total_laps": 69},
    {"circuit_id": "circuit:6", "total_laps": 78}
  ],
  "competitors": [
    {"driver_id": "piloto-1", "name": "Piloto 1", "pace_ms_per_km": 21000}
  ]
}
```

A resposta inclui cada corrida, seu historico volta a volta e classificacao
final independente. A API usa o comprimento das pistas do catalogo, sem
consultar `race_id` nem exigir `POST /simulation/load`. O motor atual usa ritmo
constante; clima, pit stops e pontuacao acumulada ainda nao alteram o resultado.

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

A `ParametersView` monta o torneio a partir do catálogo de pistas. A
`RaceConfigurationView` permite ajustar sessão e clima para cada etapa; a aba
Clima pinta intervalos de voltas na timeline sem sair dessa tela. A confirmação
valida o plano, mas o início da simulação pela interface pertence a um
incremento posterior.

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

## Ranking de pilotos e adaptador para simulação

O [guia de ranking e integração Python](docs/ranking-e-adaptador-pilotos.md)
descreve a ordenação por ritmo observado, geração de gráficos e o contrato
para executar o primeiro experimento determinístico de uma volta.

## Planejamento da modelagem de pneus

O [estudo inicial de pneus](docs/modelagem-pneus-inicial.md) registra a cobertura
do ETL, o core publicado, a proposta de parâmetros e as decisões de integração.

A [análise de pneus de 2024](docs/analise-pneus-2024.md) apresenta cobertura,
tendências por stint, sensibilidade ao início e instruções para gerar o atlas
de gráficos por piloto.

A [comparação após SC/VSC](docs/pneus-sc-vsc-estimadores.md) inclui cobertura,
robustez à retirada de voltas e avaliação de transferência de tendência por evento.
