# Fluxo e responsabilidades do ETL

## Geometria de pista e pit lane

A extensao da issue #34 consome os CSVs reduzidos da issue #51, conforme o
ADR 0003. Eles ja contem coordenadas X/Y normalizadas. Nao sao um DataFrame
de latitude/longitude e nao exigem Pandas: a leitura tabular fica no adapter.
O ponto geografico de `circuits.csv` continua preservado como localizacao do
circuito, separado de seu contorno.

O fluxo opcional e:

1. `scripts/ingest_trotman.py --geometry-dir ...` compoe
   `MockTrackDatasetAdapter`, com os dois CSVs e os dois manifestos de 2025.
2. `run_race_etl` carrega a corrida como antes e solicita sua geometria pelo
   `circuit_id` canonico; o adapter usa o mapeamento `circuitId` do Trotman
   registrado na issue #51, sem fazer associacao por nome.
3. O adapter verifica SHA-256 dos arquivos, a referencia do pit lane ao
   checksum do tracado, circuito, contagens e comprimento declarado. Converte
   campos numericos e booleanos e ordena as linhas por `sequence`.
4. `TrackGeometryFactory` valida o DTO `NormalizedTrackGeometry`: sequencia
   contigua desde zero, numeros finitos, distancia crescente desde zero,
   fechamento explicito da pista, progresso do pit lane de zero a um e
   exatamente um ponto de servico. Nao ha preenchimento ou reparo silencioso.
5. O caso de uso associa `TrackGeometry` a `RaceData.geometry` somente se o
   circuito coincidir. O writer publica corrida e geometria no mesmo SQLite,
   com chaves estrangeiras e as tabelas abaixo. O relatorio inclui contagens,
   checksums, comprimento e aviso quando o ano do mock difere do ano da corrida.
6. `SQLiteTrackGeometryRepository` implementa `TrackGeometryRepository` e
   devolve as duas polilinhas e suas proveniencias, revalidadas pela Factory.

| Tabela | Conteudo e unidades |
| --- | --- |
| `track_points` | `circuit_id`, `sequence`, `x_normalized`, `y_normalized`, `cumulative_distance_m`. X/Y sem unidade; distancia da volta em metros. |
| `pit_lane_points` | Mesmo circuito e sistema X/Y; `sequence`, `path_fraction` em [0, 1] e `is_service_point` booleano (0/1 no SQLite). |
| `geometry_sources` | Uma linha por caminho: ferramenta/versao, ano, data de geracao, origem, licenca dos dados, checksums do artefato e manifesto, transformacao. |

O comprimento e a distancia declarada no mock, nao uma medida oficial da pista.
Nao se deve calcular metros ou velocidade usando diretamente X/Y nem tratar
`path_fraction` como tempo ou distancia fisica do pit lane. Pista e pit lane
devem receber a mesma escala e translacao na apresentacao; normalizar cada um
separadamente destruiria seu alinhamento. O ponto de servico e representativo,
sem identificar o box individual de uma equipe. O campo `upstream` ausente no
manifesto do pit lane permanece `NULL`; a licenca dos dados e os checksums
continuam obrigatorios.

Exemplo de consumo, com `PYTHONPATH=src`:

```python
from pathlib import Path

from f1_simulator.adapters.persistence.sqlite_track_geometry import (
    SQLiteTrackGeometryRepository,
)
from f1_simulator.application.ports.track_geometry import TrackGeometryRepository

repository: TrackGeometryRepository = SQLiteTrackGeometryRepository(
    Path("data/curated/race-1141-geometry.sqlite")
)
geometry = repository.get_geometry("circuit:18")
track_xy = [(p.x_normalized, p.y_normalized) for p in geometry.track_points]
distances_m = [p.cumulative_distance_m for p in geometry.track_points]
pit_xy = [(p.x_normalized, p.y_normalized) for p in geometry.pit_lane_points]
service = next(p for p in geometry.pit_lane_points if p.is_service_point)
```

O repository abre o banco somente para leitura. Circuito sem geometria, ou
banco historico criado sem ela, gera `TrackGeometryNotFoundError`; arquivo
inexistente, esquema parcial e dados corrompidos geram
`TrackGeometryRepositoryError`. O ID de circuito deve vir da corrida escolhida.

Sem `--geometry-dir`, o comando e o esquema historicos continuam funcionando.
Com essa opcao, ambos os caminhos sao obrigatorios e uma pista ausente falha
explicitamente, sem trocar por outro circuito. A ingestao processa uma corrida
por execucao, usando a pista correspondente entre os 24 mocks disponiveis.
`--geometry-manifests-dir` permite localizar os manifestos fora do diretorio
padrao `data/sources`. A fixture isolada de Interlagos/2024, sem pit lane
correspondente, nao faz parte desse contrato de entrada.

Esta entrega prepara os dados para modelagem e apresentacao; nao implementa
interpolacao de carros, classificacao de curvas/retas ou endpoints de produto.
Os dados de mock, incluindo sua licenca upstream, permanecem distintos do
historico CC0 do Trotman.

## Fluxo historico da corrida

Este documento explica como os dados de uma fonte externa atravessam o ETL ate
se tornarem dados canonicos prontos para persistencia e consumo pelo restante do
sistema.

O objetivo da separacao e permitir que novas fontes de dados sejam adicionadas
sem alterar o dominio, as validacoes compartilhadas ou os consumidores dos
dados. A implementacao segue a arquitetura hexagonal e a combinacao Adapter +
Factory registrada no [ADR 0002](adr/0002-arquitetura-hexagonal-e-integracao-de-dados.md).

## Visao geral

```text
scripts/ingest_trotman.py
    |
    | escolhe os adapters concretos
    v
application/etl.py
    |
    | coordena a execucao
    v
RaceDataIngestionService
    |
    | solicita uma corrida pela RaceDatasetPort
    v
TrotmanDatasetAdapter
    |
    | le CSV/ZIP e converte nomes, tipos, nulos, datas e unidades
    v
NormalizedRaceData
    |
    | transporta os dados normalizados; nao executa processamento
    v
RaceDataFactory
    |
    | valida invariantes, relacionamentos e identificadores
    v
RaceData
    |
    | agregado canonico independente da fonte
    v
application/etl.py
    |
    | gera o relatorio de qualidade e usa a RaceDataWriterPort
    v
SQLiteRaceDataWriter
```

## Responsabilidade de cada componente

### Script de composicao

[`scripts/ingest_trotman.py`](../scripts/ingest_trotman.py) e a entrada de linha
de comando especifica da Base Trotman. Ele escolhe e instancia os componentes
concretos usados naquela execucao:

- `TrotmanDatasetAdapter` como adapter de entrada;
- `SQLiteRaceDataWriter` como adapter de saida;
- `run_race_etl` como caso de uso que coordena os dois.

Esse e o unico ponto do fluxo que precisa conhecer simultaneamente Trotman e
SQLite. A aplicacao recebe essas dependencias prontas.

### Portas da aplicacao

[`application/ports/race_data.py`](../src/f1_simulator/application/ports/race_data.py)
define os contratos controlados pela aplicacao:

- `RaceDatasetPort` exige que um adapter de dataset implemente `load_race()` e
  devolva `NormalizedRaceData`;
- `RaceDataWriterPort` exige que um adapter de saida saiba persistir um
  `RaceData` validado.

As portas nao tratam dados. Elas apenas definem quais operacoes e tipos os
adapters precisam oferecer. Como sao `Protocol`s do Python, um novo adapter nao
precisa herdar explicitamente dessas classes: basta implementar a mesma
interface.

### Adapter da Base Trotman

[`adapters/datasets/trotman.py`](../src/f1_simulator/adapters/datasets/trotman.py)
conhece os detalhes exclusivos da fonte Trotman:

- nomes dos arquivos e das colunas CSV;
- relacionamentos por `raceId`, `driverId`, `constructorId` e `statusId`;
- marcador de valor ausente `\N`;
- formatos externos de data, hora e numeros;
- versao e checksum esperados da fonte.

O adapter le e relaciona os CSVs de uma corrida e converte os valores para o
contrato normalizado. Ele nao cria entidades de dominio, nao grava SQLite e nao
implementa regras do simulador.

### DTO normalizado

[`application/race_data_dto.py`](../src/f1_simulator/application/race_data_dto.py)
define `NormalizedRaceData`, o formato intermediario compartilhado por todos os
adapters de datasets.

O DTO e um recipiente passivo: ele nao le, transforma, valida ou persiste
dados. Sua funcao e transportar valores que ja foram convertidos pelo adapter
para nomes e unidades comuns:

- duracoes em milissegundos;
- coordenadas em graus decimais;
- altitude em metros;
- datas e horarios em tipos do Python;
- valores ausentes representados por `None`.

### Servico de ingestao

[`application/race_data_ingestion.py`](../src/f1_simulator/application/race_data_ingestion.py)
define `RaceDataIngestionService`, o articulador entre qualquer adapter de
dataset e a construcao do dominio.

Seu fluxo central e equivalente a:

```python
normalized = dataset_adapter.load_race(race_external_id)
race_data = RaceDataFactory.create(normalized)
```

O servico conhece a porta generica, mas nao conhece arquivos CSV, Trotman,
Kaggle ou SQLite.

### Factory e dominio canonico

[`factories/race_data_factory.py`](../src/f1_simulator/factories/race_data_factory.py)
recebe o DTO normalizado e aplica as regras compartilhadas entre todas as
fontes. Entre outras verificacoes, a Factory valida:

- metadados e checksum da fonte;
- campos obrigatorios e tipos;
- faixas de latitude e longitude;
- valores positivos ou nao negativos;
- unicidade de identificadores e posicoes;
- referencias entre corrida, circuito, pilotos, equipes, voltas e pit stops.

Depois da validacao, ela produz o agregado `RaceData`, definido em
[`domain/race_data.py`](../src/f1_simulator/domain/race_data.py). Esse agregado
usa identificadores canonicos, como `race:1141` e `driver:830`, e nao depende do
formato de nenhuma fonte externa.

### Orquestracao e persistencia

[`application/etl.py`](../src/f1_simulator/application/etl.py) coordena a
execucao completa. Ele:

1. solicita ao `RaceDataIngestionService` um `RaceData` validado;
2. gera o relatorio de qualidade;
3. entrega os dados ao adapter definido pela `RaceDataWriterPort`;
4. publica o relatorio de forma atomica;
5. remove a saida de dados se a publicacao do relatorio falhar.

O `etl.py` nao normaliza colunas e nao conhece o schema Trotman. O adapter de
saida atual e
[`SQLiteRaceDataWriter`](../src/f1_simulator/adapters/persistence/sqlite_race_data.py),
mas outro adapter pode implementar a porta de escrita futuramente.

## Como adicionar outro dataset

Para integrar outra fonte, crie um adapter que traduza o schema externo para
`NormalizedRaceData`:

```python
class OutraFonteDatasetAdapter:
    def load_race(self, race_external_id: int) -> NormalizedRaceData:
        # Le a fonte e converte suas colunas, nulos e unidades para o DTO comum.
        return NormalizedRaceData(...)
```

Depois, escolha esse adapter no ponto de composicao:

```python
dataset = OutraFonteDatasetAdapter(source)
writer = SQLiteRaceDataWriter()

run_race_etl(
    dataset,
    writer,
    race_external_id,
    database_path,
    report_path,
)
```

Nao deve ser necessario modificar `RaceDataIngestionService`,
`RaceDataFactory`, `RaceData` ou `SQLiteRaceDataWriter`. Uma alteracao nesses
componentes so e justificavel quando a nova fonte revelar uma informacao ou
regra de dominio que o contrato canonico ainda nao representa.

## Resumo das fronteiras

| Componente | Conhece a fonte externa? | Valida o dominio? | Persiste? |
| --- | --- | --- | --- |
| Script de composicao | Escolhe a fonte | Nao | Escolhe o writer |
| Dataset adapter | Sim | Apenas formato e referencias da fonte | Nao |
| `NormalizedRaceData` | Nao | Nao | Nao |
| `RaceDataIngestionService` | Nao | Delega para a Factory | Nao |
| `RaceDataFactory` | Nao | Sim | Nao |
| `RaceData` | Nao | Ja chega validado | Nao |
| `run_race_etl` | Nao | Nao | Delega para o writer |
| Persistence adapter | Nao | Valida integridade da escrita | Sim |
