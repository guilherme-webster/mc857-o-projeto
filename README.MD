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
- [Mapa do codigo](docs/CODEBASE_MAP.md)
- [Modelagem heuristica da corrida (valores atuais)](docs/modelagem-heuristica.md)
- [Modelagem calibrada da corrida e validacao](docs/modelagem-corrida-calibrada.md)
- [Modelo de clima](docs/modelagem-clima.md)
- [Proposta de planejamento da modelagem (historica)](docs/planejamento-modelagem.md)
- [Dados e plano de perfilamento dos pilotos (historico)](docs/perfilamento-pilotos.md)

O frontend do MVP e uma aplicacao desktop em Python com Arcade, inspirada na
experiencia de visualizacao do projeto
[IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay). FastAPI
e o backend, e o motor de simulacao e independente dos dois frameworks. O
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
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    ```

* **Como verificar se está instalado:**
  ```bash
  docker --version
  docker compose version
  ```

### 2. uv (Gerenciador de Pacotes e Python)

* **Instalação:**
  * **Windows (PowerShell / WinGet):**
    ```powershell
    winget install astral-sh.uv
    ```
  * **Linux / macOS / WSL:**
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

* **Como verificar se está instalado:**
  ```bash
  uv --version
  ```

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
de serviço representativo. Os dados foram derivados offline do FastF1; cache e
telemetria bruta não fazem parte do repositório. O gerador reconstruído está em
`scripts/rebuild_fastf1_geometry.py`;
Consulte o ADR 0003 e os manifestos em `data/sources/` para proveniência,
transformação e limitações de uso. O visualizador temporário usado para
inspecionar os mocks também não faz parte do repositório.

Para reconstruir uma etapa sem alterar os CSVs atuais:

```bash
uv run --with fastf1==3.8.3 python scripts/rebuild_fastf1_geometry.py \
  --round 21 \
  --output-dir data/curated/geometry-round-21
```

Sem `--round`, o script processa as 24 etapas de 2025. A saída deve ser um
diretório novo; inclui os dois CSVs e `generation_report.json` com checksums.
O cache é temporário por padrão (`--cache-dir` permite retenção local). A
reconstrução não garante igualdade byte a byte com as fixtures existentes.

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

O fluxo da interface Arcade esta descrito em
[Telas implementadas com Arcade](#telas-implementadas-com-arcade).

Para rodar uma corrida pela API, monte o grid e depois execute-o:

```bash
curl -X POST localhost:8000/catalog/grid -H 'Content-Type: application/json' \
  -d '{"size": 20, "mode": "random", "seed": 7}'
curl -X POST localhost:8000/catalog/grid/run -H 'Content-Type: application/json' \
  -d '{"setup": {"total_laps": 44, "track_id": "circuit:13"}}'
```

O catalogo de pilotos (`GET /catalog`) e o grid dependem do banco historico.
No primeiro uso, construa-o com `curl -X POST localhost:8000/api/history/build`
(cerca de 20 s a partir do ZIP do Trotman em `data/raw/`).

`POST /catalog/grid` tem tres modos: `random` sorteia `size` pares
piloto/equipe de toda a historia (desde 1950); `manual` recebe `pair_ids`
(`driver_id@team_id`, listados em `GET /catalog`); `race` reproduz a largada de
uma corrida historica (`{"mode": "race", "race_id": "race:1141"}`; as corridas
de uma temporada saem de `GET /api/history/races?season=2024`). Os atributos sao
sorteados por arquetipo, os perfis ficticios nomeados de
`configs/drivers/perfis-ficticios.json` sao aplicados por cima (pilotos de
2024) e `PATCH /catalog/grid` edita atributos a mao. A resposta traz a
caracterizacao de cada perfil aplicado e o aviso de que os perfis sao
ficticios.

`POST /catalog/grid/run` roda o motor detalhado (combustivel, pneus, paradas,
disputas, abandonos, safety car, bandeiras e clima) e devolve o historico volta
a volta, a classificacao, a largada (`starting_grid`), os eventos do controle de
prova e, em `assumptions`, todos os parametros heuristicos e assumidos usados.
A mesma semente reproduz a mesma corrida. `POST /championship/standings`
calcula a classificacao de um torneio a partir da chegada de cada etapa.
Detalhes em [Modelagem heuristica da corrida](#modelagem-heurística-da-corrida).

X/Y sao normalizados e sem unidade; distancia acumulada da pista e em metros.
As geometrias sao de 2025: seu uso com uma corrida de outro ano fica explicito no
relatorio. Consulte o [contrato de consumo](docs/fluxo-etl.md#geometria-de-pista-e-pit-lane)
para ler as novas tabelas com `SQLiteTrackGeometryRepository`.

## Testes e verificacoes

Com as dependencias do `pyproject.toml` instaladas (`uv sync`), rode a suite a
partir da raiz:

```bash
uv run python -m unittest -v
```

Sem elas, `python3 -m unittest -v` ainda roda os testes do nucleo; os modulos
que importam FastAPI falham na importacao e os de interface sao pulados. Os
testes de interface grafica abrem janelas Arcade e so rodam com
`ARCADE_GUI_TEST=1` e um display disponivel. Dois testes do servico de catalogo
gravam em `/data/simulation` e so passam dentro do container do backend.
Para lint e formatacao tem sido usado o `ruff` (`ruff check`, `ruff format`),
instalado a parte: ele nao e dependencia declarada e nao ha configuracao
propria; varios arquivos antigos ainda nao seguem o `ruff format`.

O projeto usa o layout `src`: o pacote `f1_simulator` fica dentro dessa pasta,
mas ainda nao e instalado no ambiente Python. A suite configura esse caminho em
`tests/__init__.py`. Para importar o pacote em um comando Python avulso, informe
o caminho explicitamente:

```bash
PYTHONPATH=src python3 -c "from f1_simulator.domain.race_data import RaceData"
```

## Como Executar a Aplicação

O backend FastAPI roda em Docker. O frontend Arcade roda em container ou no
host, conforme o ambiente gráfico. Em todos os casos, o Arcade permanece cliente
HTTP do backend.

### Caminho recomendado: `python run.py`

Depois de clonar o repositório, basta:

```bash
python run.py
```

O inicializador detecta o ambiente, sobe o backend, aguarda o healthcheck e abre
o frontend. O comportamento depende do host:

- **Linux com X11/XWayland:** backend e frontend em container (perfil `linux`),
  com um cookie `xauth` dedicado.
- **Windows ou WSL com WSLg (Docker Desktop):** backend e frontend em container
  (perfil `wslg`).
- **Windows nativo ou WSL sem WSLg:** backend em container e **frontend local**,
  porque a janela Arcade não tem servidor gráfico compatível no host. Nesse
  caso o `run.py` usa `uv`; se o `uv` não estiver instalado, ele mostra a
  instrução de instalação e encerra.

### Execução manual por perfil

Em Linux e WSL/WSLg também é possível subir os serviços diretamente:

```bash
# Linux com X11/XWayland
docker compose --profile linux up --build

# Windows com Docker Desktop e WSLg
docker compose --profile wslg up --build
```

No Windows nativo, rode o backend em container e o frontend localmente:

```powershell
docker compose up -d --build backend
uv run python -m frontend.arcade
```

Sem um perfil, `docker compose up` inicia somente o backend. Os requisitos de
display e autorizacao do frontend em container estao no proprio
`docker-compose.yaml` (variaveis `DISPLAY`, `XAUTHORITY` e
`LIBGL_ALWAYS_SOFTWARE`) e em `run.py`.

### Somente o frontend no host

Depois de `uv sync`, execute a tela desejada:

- Tela principal de parâmetros:

  ```bash
  uv run python -m frontend.arcade
  ```

- Corridas salvas, direto na reprodução (sem passar pela configuração):

  ```bash
  uv run python -m frontend.arcade.track_view
  uv run python -m frontend.arcade.track_view --saved <id-da-corrida>
  ```

Por padrão, o frontend no host consulta `http://localhost:8000`. Para outro
endpoint, defina `F1_API_BASE_URL` antes de iniciar o processo.

### Somente o backend

```bash
docker compose up --build backend
```

Em segundo plano:

```bash
docker compose up -d backend
```

Para encerrar os serviços:

```bash
docker compose down
```

## Telas implementadas com Arcade

O fluxo completo roda sem `curl`: configurar o torneio, ajustar o grid,
simular, assistir a cada etapa e ver o resultado do campeonato.

### Configuração do torneio (`ParametersView`)

A primeira tela (1672 × 900) define nome, pontuação, número de etapas, clima e
desempate do torneio e consulta `GET /simulation/tracks`. Use as setas para
percorrer as pistas, **Adicionar à sequência** para incluí-las na ordem
desejada e arraste as linhas da lista para reordenar; também é possível gerar
uma sequência automática reproduzível a partir do nome do torneio. Clicar na
prévia da pista abre a `RaceConfigurationView`, onde as abas **Sessão** e
**Clima** editam a etapa (o clima é pintado na timeline); **Pista**, **Regras**
e **Carros** ainda são áreas futuras. Toda etapa nova começa com 69 voltas,
qualquer que seja a pista (pendência registrada em `docs/progresso.md`).

**Confirmar torneio** usa o grid atual do backend (ou cria um aleatório de 20
pilotos, se não houver), roda cada etapa em `POST /catalog/grid/run` numa thread
e abre a reprodução da primeira. Intervalo de voltas da sessão e largada lançada
ainda não são suportados pelo motor: viram avisos na tela da corrida.

### Pilotos e grid (`GridView`)

Aberta pelo botão **Pilotos e grid**, monta o grid usado pelo Confirmar
(aleatório ou a largada de qualquer etapa de 2024), mostra arquétipo e os cinco
atributos de cada piloto coloridos pela origem (sorteado, perfil fictício ou
editado) e, para o piloto selecionado, a caracterização fictícia e controles
−/+ gravados via `PATCH /catalog/grid`.

### Reprodução da corrida (`TrackView`)

Reproduz a corrida volta a volta a partir do `history` do motor: ultrapassagens,
paradas, abandonos e o agrupamento sob safety car aparecem na pista. Mostra a
faixa de controle de prova (verde, amarela, VSC, SC, vermelha, relargada), o
registro de eventos, o clima e a classificação ao vivo com intervalo, pneu,
idade do pneu, paradas, "BOX" e posições ganhas. Espaço pausa, ↑/↓ mudam a
velocidade (1x é tempo real), ←/→ invertem o sentido e R reinicia. Num
torneio, **Próxima etapa** avança e, na última, **Resultado do torneio** abre a
`TournamentResultView`, com pontos, vitórias, pódios, média e a posição em cada
etapa (calculados por `POST /championship/standings`).

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
`uv run python -B scripts/evaluate_profiles.py --database data/curated/history-profile-evaluation-2024.sqlite --plan configs/profile-evaluation-2024.json`.
A saída é uma pasta nova com relatório, JSON, CSVs e gráficos; não exige
redirecionar o JSON nem remover resultados anteriores.

A [análise de sensibilidade dos contextos](docs/sensibilidade-contextos-pilotos.md)
compara agrupamento por stint e janela de voltas, mostrando cobertura e
intervalos exploratórios por evento nos gráficos:

```bash
uv run python -B scripts/analyze_profile_contexts.py \
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
python3 scripts/calibrate_model.py --database data/curated/history.sqlite \
  --seasons 2022 2023 --output data/parameters/model-v1.json
```

Valide contra corridas que não entraram na calibração. O script recusa
validar sobre uma temporada calibrada sem `--allow-calibrated-seasons`:

```bash
python3 scripts/backtest_model.py --database data/curated/history.sqlite \
  --parameters data/parameters/model-v1.json --seasons 2024 --repeats 10
```

Cada corrida é comparada com a linha de base da ordem de largada; o modelo só
se justifica se vencê-la. O relatório de 24/09 também comparava com o modelo
antigo de ritmo constante, removido do código depois. O
[relatório da modelagem](docs/modelagem-corrida-calibrada.md) traz método,
coeficientes, resultados de 2024 e limitações.

Esse motor calibrado é o que `POST /catalog/grid/run` executa, com as
heurísticas da seção seguinte por cima; a mesma semente, os mesmos parâmetros e
os mesmos dados reproduzem exatamente a mesma corrida.

## Modelagem heurística da corrida

Por orientação do professor e decisão do grupo, perfis de pilotos, disputas de
posição, safety car, VSC, bandeiras e paradas são **heurísticos**: escolhidos e
rotulados, não medidos. Os perfis nomeados são caracterizações fictícias, não
afirmações sobre pessoas reais. A física de base (combustível, pneu, tráfego,
perda de boxes, dificuldade por circuito) continua vindo do modelo calibrado.

- [Referência das heurísticas](docs/modelagem-heuristica.md): valores atuais,
  onde ficam no código e como reajustar.
- [ADR 0008](docs/adr/0008-modelagem-heuristica-sobre-o-motor-calibrado.md):
  a decisão e suas consequências.
- [Plano e histórico](docs/prds/modelagem-pilotos-heuristica.md).

Para medir a frequência de SC/VSC, vermelhas, paradas e abandonos em muitas
corridas, e para regerar a tabela de voltas de referência por circuito:

```bash
python3 scripts/race_control_frequency.py --races 200 --seed 1
python3 scripts/build_reference_laps.py --database data/curated/history.sqlite \
  --seasons 2022 2023 2024
```

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

## Planejamento da modelagem de pneus

O [estudo inicial de pneus](docs/modelagem-pneus-inicial.md) registra a cobertura
do ETL, o core publicado, a proposta de parâmetros e as decisões de integração.

A [análise de pneus de 2024](docs/analise-pneus-2024.md) apresenta cobertura,
tendências por stint, sensibilidade ao início e instruções para gerar o atlas
de gráficos por piloto.

A [comparação após SC/VSC](docs/pneus-sc-vsc-estimadores.md) inclui cobertura,
robustez à retirada de voltas e avaliação de transferência de tendência por evento.
