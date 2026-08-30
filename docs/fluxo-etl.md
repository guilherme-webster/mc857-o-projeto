# Fluxo e responsabilidades do ETL

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
