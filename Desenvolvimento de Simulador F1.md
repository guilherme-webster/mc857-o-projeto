# Plano de desenvolvimento — Simulador de Corrida de Fórmula 1

## 1. Objetivo e recorte do projeto

O sistema permitirá configurar e executar uma corrida de Fórmula 1 simulada e acompanhar sua evolução em um painel 2D. O foco será a estratégia de corrida e o comportamento dos dados, não uma reprodução física ou gráfica 3D.

Na visão evolutiva do produto, o simulador poderá considerar:

- circuito, número de voltas, pilotos e equipes;
- ritmo-base de carro e piloto;
- composto, idade e degradação dos pneus;
- consumo de combustível;
- paradas nos boxes;
- clima e condição da pista;
- falhas, acidentes, bandeiras, *Virtual Safety Car* (VSC) e *Safety Car* (SC);
- classificação, intervalos, tempos de volta e histórico de eventos.

O usuário deverá conseguir:

1. informar os parâmetros disponíveis para o cenário;
2. iniciar a corrida e acompanhar sua execução até o fim;
3. consultar o resultado e a classificação final.

### Escopo acordado para o MVP

O primeiro incremento demonstrável será deliberadamente estreito:

- usar **um único dataset**, com fonte, versão e licença registradas;
- suportar **um único circuito** previamente escolhido pelo grupo;
- implementar o ETL necessário para esse dataset;
- executar uma corrida completa, da largada à classificação final;
- oferecer o fluxo do usuário em três telas: **Parâmetros**, **Corrida** e **Resultados**;
- usar **Django** no backend;
- usar **Arcade** em uma aplicação desktop Python para o frontend.

“Corrida completa” significa concluir todas as voltas previstas e produzir um
resultado consistente. Isso não obriga o primeiro incremento a modelar todos os
fenômenos possíveis da Fórmula 1 nem a suportar mais de uma fonte ou circuito.

As anotações da reunião também mencionam modelagem de combustível e interação
física entre carros dentro da lista do MVP, mas voltam a classificá-las como
assuntos com os quais o grupo não se preocupará agora. Até que o grupo resolva
essa divergência, elas serão tratadas como extensões posteriores e não como
critérios de aceite do núcleo do MVP.

### Fora do escopo inicial

- física veicular de alta fidelidade;
- gráficos 3D;
- reprodução a 60 quadros por segundo;
- dados oficiais em tempo real durante um Grande Prêmio;
- microsserviços, autenticação ou implantação distribuída;
- aprendizado de máquina como requisito para o primeiro protótipo;
- modelagem detalhada da variação de massa causada pelo combustível;
- interação física entre carros, como vácuo aerodinâmico e prevenção de sobreposição.

Esses itens podem ser extensões, mas não devem bloquear o MVP.

## 2. Direção para frontend e backend

O frontend do MVP será uma aplicação desktop em Python construída com a
biblioteca **Arcade**, conforme o
[ADR 0001](docs/adr/0001-frontend-desktop-com-arcade.md). **Django** permanece
como backend e expõe por HTTP/JSON os comandos e as consultas usados pelo
cliente. Essa escolha substitui as orientações anteriores de Streamlit/Plotly e
encerra a investigação da tecnologia de frontend.

A experiência de visualização terá como referência principal o projeto
[IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay): pista
2D, marcadores dos pilotos, leaderboard, informações de volta e controles de
reprodução. A referência demonstra possibilidades do Arcade, mas não define a
arquitetura nem as regras deste produto. O projeto de referência reproduz
telemetria histórica; este projeto gera a evolução de uma corrida simulada.

O backend será responsável por receber e validar parâmetros, iniciar e avançar
a simulação, consultar seu estado e disponibilizar os resultados. As regras da
corrida deverão permanecer em código Python independente do Django e do Arcade;
ambos são adaptadores nas bordas do sistema.

### Diretrizes da interface Arcade

- uma única `arcade.Window` alterna entre `ParametersView`, `RaceView` e
  `ResultsView`;
- `on_update` consulta ou apresenta snapshots, mas não usa o tempo de quadro
  para calcular a corrida;
- chamadas HTTP não bloqueiam o laço de eventos; timeouts e falhas de conexão
  geram mensagens compreensíveis;
- a taxa de desenho pode ser maior que a taxa de consulta, interpolando apenas
  a apresentação quando necessário, sem alterar o estado do domínio;
- regras de classificação, término e posição longitudinal permanecem no motor;
- o protótipo inicial valida OpenGL 3.3 ou superior nos ambientes do grupo e
  mantém os testes do motor executáveis sem janela ou GPU.

### Organização sugerida das telas

| Tela | Responsabilidade |
| --- | --- |
| `ParametersView` | Exibir as opções suportadas para o único cenário do MVP e validar a configuração. |
| `RaceView` | Iniciar a execução e exibir seu progresso, a pista, a classificação e os controles. |
| `ResultsView` | Apresentar classificação final, tempos e eventos relevantes. |

O objeto do motor não deve ser implementado dentro de `arcade.View` nem nas
*views* do Django. O cliente guarda apenas o identificador e a representação
necessária para a tela; comandos e consultas são delegados ao backend.

## 3. Estilo arquitetural

### 3.1 Encaminhamento da reunião e formalização

A reunião de 25 de agosto de 2026 encaminhou a adoção da **arquitetura
hexagonal**, principalmente para isolar o modelo interno das diferenças entre
datasets e permitir a substituição de fontes por adaptadores.

Como a decisão afeta a estrutura e as dependências do projeto, ela somente será
considerada aceita após o registro e a aprovação de um ADR pelo grupo. Até essa
formalização, as árvores de diretórios deste documento são ilustrativas e não
autorizam a criação de uma estrutura definitiva.

### 3.2 Aplicação da arquitetura hexagonal, se aceita

Se o ADR confirmar o encaminhamento da reunião, o núcleo da simulação exporá
portas para os casos de uso e para as dependências externas. Django, Arcade, o
ETL, os datasets e a persistência ficarão nas bordas, implementando ou
consumindo essas portas por meio de adaptadores. O diagrama abaixo é
condicional, não uma decisão já aceita.

```text
Cliente Arcade -> HTTP/JSON -> adaptador Django -> aplicação e domínio
                                                    |
                                             portas de saída
                                                    |
                         adaptadores de datasets, ETL e persistência
```

Possíveis portas, criadas somente quando houver uso concreto, incluem:

- `RaceDataRepository` — consulta os dados canônicos da corrida;
- `SimulationResultRepository` — salva configurações, sementes e resultados;
- `RandomSource` — fornece aleatoriedade substituível e testável;
- casos de uso para configurar, executar, consultar e obter o resultado da corrida.

Cada fonte externa poderá ter seu próprio adaptador para converter nomes,
tipos, unidades e identificadores ao esquema canônico. No MVP haverá somente o
adaptador do dataset escolhido; novos adaptadores serão adicionados quando uma
segunda fonte realmente for incorporada.

### 3.3 Alternativa considerada — MVC

MVC continua sendo uma alternativa tecnicamente possível e deverá constar no
ADR como opção considerada. Sua nomenclatura se alinha diretamente às
interações de interface e pode exigir menos abstrações no início. A arquitetura
hexagonal, porém, foi o encaminhamento da reunião por tornar explícitas as
fronteiras com os diferentes datasets.

O uso de *views* pelo Django não transforma automaticamente todo o sistema em
MVC. Independentemente da arquitetura registrada, cálculos de volta,
estratégias e estados da corrida não devem ser implementados nas *views*.

### 3.4 Fronteiras obrigatórias

- regras da corrida independem de Django, Arcade e dos formatos dos datasets;
- leitura de CSV, Parquet ou banco de dados não fica dentro do motor;
- o estado da interface não é a fonte de verdade da corrida;
- o motor pode ser executado e testado sem janela, GPU ou servidor web;
- dependências externas e aleatoriedade são injetáveis e testáveis;
- não serão criadas portas ou interfaces sem uma variação ou fronteira concreta.

### 3.5 Eventos internos, sem infraestrutura distribuída

O motor pode produzir eventos de domínio, por exemplo:

- `LapCompleted`;
- `PitStopStarted` e `PitStopFinished`;
- `WeatherChanged`;
- `CarRetired`;
- `SafetyCarDeployed` e `SafetyCarEnded`;
- `RaceFinished`.

Esses eventos alimentam o histórico, as estatísticas e a criação de um novo retrato da corrida. Eles devem ser objetos Python processados no mesmo processo. Kafka, filas externas, WebSockets próprios e microsserviços não são necessários.

## 4. Componentes do sistema

| Componente | Responsabilidade | Entradas | Saídas |
| --- | --- | --- | --- |
| Cliente desktop Arcade | Capturar parâmetros e apresentar o progresso e o resultado. | Ações do usuário e respostas HTTP/JSON. | Comandos e consultas ao backend. |
| Adaptador Django | Validar requisições e traduzir dados entre HTTP/JSON e os casos de uso. | Requisições, comandos e identificadores. | Respostas, retratos e erros de aplicação. |
| Casos de uso | Orquestrar configuração, execução, consulta e conclusão da corrida. | Comandos e portas. | Retratos, resultados e eventos. |
| Motor de simulação | Avançar o relógio simulado e aplicar regras. | `RaceState`, comandos, parâmetros e fonte aleatória. | Novo estado e eventos de domínio. |
| Modelo de tempo de volta | Calcular ritmo e penalidades de cada carro. | Circuito, piloto, carro, pneu, combustível, clima e tráfego. | Tempo previsto e seus componentes. |
| Gerenciador de estratégia | Decidir ou validar pneus e paradas. | Estado do carro e condições da corrida. | Comando de parada ou permanência. |
| Gerenciador de corrida | Controlar largada, bandeiras, SC/VSC e término. | Eventos e relógio. | Estado global da prova. |
| Adaptador do dataset e ETL | Ler a fonte escolhida, padronizar tipos e validar qualidade. | Arquivos brutos do dataset do MVP. | Dados canônicos e relatório de qualidade. |
| Calibração | Estimar parâmetros a partir de corridas históricas. | Tabelas canônicas. | Arquivo versionado de parâmetros. |
| Persistência | Salvar dados tratados, cenários e resultados. | Objetos e tabelas internas. | Consultas reprodutíveis. |
| Visualização 2D Arcade | Projetar a pista e posicionar marcadores por progresso. | Geometria, progresso e classificação recebidos. | Desenho da pista, carros e leaderboard. |

### Entidades e objetos de valor do domínio

- `Race`, `Circuit`, `Car`, `Driver`, `Team` e `TyreSet`;
- `RaceState`, `CarState`, `WeatherState` e `TrackState`;
- `RaceSnapshot`, retrato imutável entregue à interface;
- `RaceCommand`, como `Start`, `Pause`, `Advance`, `SchedulePitStop` e `Restart`;
- `LapTimeBreakdown`, contendo tempo-base e penalidades separadas;
- `SimulationConfig`, incluindo a semente aleatória e a versão dos parâmetros.

Os estados devem usar unidades explícitas e consistentes: segundos, quilogramas, metros, quilômetros por hora e graus Celsius. Tempos textuais devem ser convertidos para número na ingestão, não dentro do motor.

## 5. Padrões de projeto recomendados

Os padrões abaixo resolvem variações reais deste sistema; não devem ser aplicados apenas para aumentar o número de classes.

### 5.1 Uso combinado de Adapter e Factory

A reunião encaminhou uma abordagem que combina **Adapter** e **Factory**. Eles
não são alternativas concorrentes: cada padrão resolve uma responsabilidade
diferente.

1. O `Adapter` converte os dados externos para tipos, unidades e identificadores
   conhecidos pela aplicação.
2. A `Factory` recebe dados já normalizados e constrói objetos complexos e
   válidos, como `Race`, `Circuit`, participantes e `SimulationConfig`.
3. Os casos de uso recebem os objetos prontos e não precisam conhecer o formato
   original nem os detalhes de sua montagem.

Esse encadeamento facilita acrescentar datasets sem espalhar condicionais pelo
motor e centraliza a criação consistente dos objetos. A Factory não deve ler
CSV, consultar banco ou decidir qual adaptador usar; essas funções pertencem às
bordas e à composição da aplicação.

### 5.2 Outros padrões aplicáveis

| Padrão | Aplicação no simulador | Benefício |
| --- | --- | --- |
| Strategy | Políticas de pneus, pit stop, ultrapassagem e cálculo de degradação. | Permite comparar estratégias sem alterar o motor. |
| State | Estados da corrida (`GREEN`, `VSC`, `SC`, `RED`, `FINISHED`) e transições válidas. | Evita condicionais espalhadas e torna as regras de bandeira testáveis. |
| Repository | Acesso aos dados históricos e aos resultados simulados. | Isola CSV, Parquet ou SQLite dos casos de uso. |
| Adapter | Converte cada base Kaggle/FastF1 para o esquema canônico. | Impede que nomes e formatos externos vazem para o domínio. |
| Factory | Cria uma corrida completa a partir de `SimulationConfig`. | Centraliza validação, valores padrão e montagem dos objetos. |
| Observer / eventos de domínio | Registra eventos e atualiza projeções de classificação/estatísticas. | Desacopla o avanço do motor de seus consumidores. |
| Dependency Injection | Entrega repositórios, relógio e gerador aleatório ao motor. | Facilita testes e reprodutibilidade. |

Uma interface simples para `TyreStrategy` pode expor `decide(state) -> PitDecision`. As implementações iniciais podem ser `FixedLapStrategy`, `ReactiveWeatherStrategy` e `HistoricalStrategy`. Isso permite executar o mesmo cenário com estratégias diferentes.

A fonte aleatória deve receber uma semente e ser injetada. O mesmo cenário, a mesma versão de dados, os mesmos parâmetros e a mesma semente devem produzir o mesmo resultado.

### Padrões que não são prioridade

- Singleton: cria estado global difícil de testar;
- microsserviços: adicionam rede, implantação e consistência distribuída sem necessidade;
- Active Record no domínio: acopla regras à persistência;
- heranças profundas para carros, equipes ou pneus: prefira composição e estratégias;
- comunicação em tempo real própria antes de comprovar que atualização periódica é insuficiente.

## 6. Dados sugeridos pelo professor

As três bases abaixo são candidatas e complementares. Para o MVP, o grupo deverá
selecionar apenas uma delas e implementar um único ETL. As demais permanecem
como opções para investigação e expansão posterior. Toda fonte adotada deve ter
versão, data de download e licença registradas, e seus arquivos brutos nunca
devem ser editados manualmente.

### 6.1 Base 1 — estratégia de pneus

**Fonte:** [F1-Tyre-Strategy-Engine Datasets](https://www.kaggle.com/datasets/vanshbatra26/f1-tyre-strategy-engine-datasets)

Segundo a descrição pública consultada, a base cobre as temporadas de 2023 e 2024 e agrega informações por *stint*. Os campos declarados são:

- `GP` — Grande Prêmio;
- `Driver` — abreviação do piloto;
- `Stint` — número do *stint*;
- `Compound` — composto utilizado;
- `StintLength` — quantidade de voltas;
- `AirTemp` — temperatura média do ar;
- `TrackTemp` — temperatura média da pista;
- `Season` — temporada.

Uso no projeto:

- obter distribuições de comprimento de *stint* por composto, pista e temperatura;
- criar estratégias históricas plausíveis;
- validar se uma estratégia simulada está dentro da faixa observada;
- estimar a probabilidade de continuar ou parar, sem confundi-la com a degradação de tempo por volta.

Limitação: como os campos declarados são agregados por *stint*, essa base, isoladamente, não identifica a curva volta a volta de degradação. Ela deve ser combinada com tempos de volta da Base 2 ou 3. A licença informada é **CC BY-SA 4.0**, portanto a atribuição e as condições de compartilhamento devem ser preservadas.

### 6.2 Base 2 — corrida e telemetria

**Fonte:** [Formula 1: Race Data and Telemetry (Updatable)](https://www.kaggle.com/datasets/alexjr2001/formula-1-dataset-race-data-and-telemetry)

A descrição informa dados pré-processados provenientes de FastF1 e Ergast, incluindo amostras temporais em décimos de segundo, agregados por volta, setores e minissetores. Entre as métricas declaradas estão tempos de volta e setor, velocidade, RPM, acelerador e frenagem, além de metadados de corrida, clima e pista.

Uso no projeto:

- calibrar o ritmo-base por circuito, piloto e equipe;
- estimar perdas relativas em setores e minissetores;
- relacionar clima e condição da pista ao ritmo;
- validar a progressão dos carros e, se a versão baixada tiver coordenadas espaciais, derivar a geometria do circuito;
- comparar a saída do simulador com uma corrida real.

Limitações: telemetria em alta frequência aumenta custo de memória e processamento e não deve ser lida inteira pela interface. A ingestão deve gerar agregados em Parquet. A página consultada não declara licença; antes de versionar ou redistribuir qualquer arquivo, a equipe deve confirmar as condições da versão baixada.

### 6.3 Base 3 — histórico relacional de corridas

**Fonte:** [Formula 1 Race Data](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data)

A base contém tabelas históricas de pilotos, construtores, circuitos, corridas, resultados, tempos de volta, paradas e situações de término. Os dados anteriores a 2025 derivam do conjunto Ergast e as atualizações posteriores usam a API compatível da Jolpica.

Uso no projeto:

- preencher cadastros e o calendário histórico;
- obter resultados, posições de largada e ritmos observados;
- estimar duração e custo de pit stops por circuito;
- estimar taxas históricas de abandono e categorias de término;
- montar amostras de treino, calibração e validação separadas por corrida.

A licença declarada é **CC0**, o que facilita o uso como espinha dorsal cadastral. A base não substitui os dados de composto, clima ou telemetria detalhada das duas primeiras fontes.

### 6.4 Matriz de uso das fontes

| Necessidade | Base principal | Complemento | Observação |
| --- | --- | --- | --- |
| Pilotos, equipes, circuitos e corridas | Base 3 | Base 2 | Usar identificadores canônicos internos. |
| Tempos de volta e ritmo-base | Base 3 | Base 2 | Filtrar pit laps, SC/VSC e voltas anormais. |
| Estratégia e duração de *stints* | Base 1 | Base 2 | A Base 1 tem o rótulo `StintLength`. |
| Curva de degradação | Base 2 | Bases 1 e 3 | Estimar com voltas limpas dentro do mesmo *stint*. |
| Pit stops | Base 3 | Base 2 | Separar tempo parado de perda total no pit lane. |
| Clima | Base 2 | Base 1 | A Base 1 contém médias por *stint*. |
| Falhas e abandonos | Base 3 | — | Segmentar por era para evitar parâmetros irreais. |
| Pista 2D | coordenadas da Base 2, se presentes | GeoJSON/FastF1 | Não inferir geometria apenas de latitude/longitude do circuito. |

## 7. Pipeline e modelo de dados

### 7.1 Etapas do pipeline

1. **Aquisição:** baixar manualmente ou por API uma versão identificável da fonte adotada.
2. **Raw:** guardar arquivos originais, somente leitura, fora do controle de versão se forem grandes.
3. **Validação:** conferir colunas obrigatórias, tipos, chaves, duplicatas, faixas e unidades.
4. **Padronização:** converter nomes externos em um esquema canônico e gerar identificadores internos.
5. **Curadoria:** criar tabelas voltadas à simulação e à calibração.
6. **Calibração:** produzir um arquivo pequeno e versionado de parâmetros.
7. **Execução:** o simulador lê apenas dados curados e parâmetros, nunca os CSVs brutos diretamente.

Formato sugerido:

- CSV apenas na entrada ou exportação;
- Parquet para telemetria e tabelas analíticas;
- SQLite para metadados, cenários e resultados do MVP;
- JSON ou TOML versionado para parâmetros calibrados.

### 7.2 Esquema canônico de referência

O MVP deverá implementar somente as tabelas e colunas exigidas pelo dataset e
pelo circuito selecionados. O esquema abaixo representa a direção de evolução,
não a obrigação de criar tabelas vazias antecipadamente:

- `circuits(circuit_id, name, country, length_m, default_laps)`;
- `drivers(driver_id, code, name)`;
- `teams(team_id, name)`;
- `races(race_id, circuit_id, season, round, date)`;
- `race_entries(race_id, driver_id, team_id, grid_position, finish_position, status)`;
- `laps(race_id, driver_id, lap_number, lap_time_s, position, is_pit_lap)`;
- `pit_stops(race_id, driver_id, lap_number, stationary_time_s)`;
- `stints(race_id, driver_id, stint_number, compound, start_lap, end_lap, air_temp_c, track_temp_c)`;
- `telemetry(race_id, driver_id, lap_number, sample_time_ms, speed_kph, rpm, throttle_pct, brake)`;
- `track_points(circuit_id, sequence, x, y, cumulative_distance_m)`.

Os adaptadores devem manter uma tabela de correspondência entre os identificadores das fontes. Não usar apenas o nome textual de piloto, equipe ou Grande Prêmio como chave de junção.

### 7.3 Qualidade e prevenção de vazamento

- não misturar temporadas muito diferentes sem considerar mudanças de regulamento;
- calcular parâmetros somente com o conjunto de calibração;
- validar o modelo em corridas inteiras não usadas na calibração;
- remover ou marcar voltas de pit, largada, SC/VSC, bandeira vermelha e chuva quando o objetivo for ritmo em pista livre;
- registrar ausências em vez de preencher silenciosamente com zero;
- guardar unidade, fonte e transformação de cada coluna derivada;
- gerar um relatório com contagem de linhas, nulos, duplicatas e chaves órfãs.

## 8. Modelo de simulação

### 8.1 Relógio e passo

Separar **tempo simulado** de **tempo da interface**. O motor pode avançar por
setor no MVP. Cada chamada a `advance()` processa o próximo setor ou evento e
retorna um novo `RaceSnapshot`. O backend orquestra essa execução, e o cliente
Arcade consulta retratos ou resultados em intervalos controlados.

Esse desenho evita que `sleep`, `arcade.Window.on_update`, taxa de quadros,
latência HTTP ou desempenho da máquina alterem o resultado da corrida.

### 8.2 Tempo de volta

Uma aproximação auditável para a evolução do modelo é:

```text
tempo_volta = ritmo_base
            + efeito_piloto_e_equipe
            + penalidade_pneu
            + penalidade_combustivel
            + penalidade_clima
            + penalidade_trafego
            + ruido_controlado
```

As parcelas devem ser retornadas separadamente em `LapTimeBreakdown`. Valores iniciais são hipóteses; depois devem ser calibrados e validados com as bases.

O núcleo do MVP deverá implementar apenas as parcelas necessárias ao cenário
escolhido. `penalidade_combustivel` e `penalidade_trafego` permanecem na fórmula
como pontos de evolução até a confirmação de seu escopo pelo grupo.

Para pneus, começar com uma função simples por composto, por exemplo:

```text
penalidade_pneu(idade) = a_composto * idade + b_composto * idade²
```

Os coeficientes não devem ser apresentados como universais. Eles dependem de circuito, temperatura, carro e conjunto de dados.

### 8.3 Eventos estocásticos

Falhas, acidentes e mudanças climáticas devem ser gerados por probabilidades condicionais, não por constantes escondidas no código. Os parâmetros precisam ser nomeados, configuráveis, versionados e limitados a faixas plausíveis.

Cuidados importantes:

- taxas históricas de DNF devem ser segmentadas por era;
- um acidente pode alterar o estado global e gerar SC/VSC, não apenas retirar um carro;
- a chuva deve evoluir como estado ao longo do tempo, e não como um multiplicador independente por volta;
- todo evento aleatório deve consumir a fonte aleatória injetada e aparecer no log.

### 8.4 Posicionamento no circuito

Representar a pista por pontos ordenados e distância acumulada. Cada carro mantém a distância total percorrida. Para desenhá-lo:

1. calcular `distancia_na_volta = distancia_total % comprimento_pista`;
2. localizar os dois pontos que delimitam essa distância;
3. interpolar linearmente `x` e `y`;
4. desenhar a pista como linha e cada carro como um marcador na tecnologia de visualização escolhida.

A classificação deve ser calculada pelo estado do domínio. A posição gráfica não deve ser usada como fonte de verdade.

## 9. Estrutura de diretórios sugerida

Esta árvore é apenas uma ilustração das fronteiras discutidas. Ela deverá ser
revista e aprovada no ADR antes de orientar a criação de diretórios:

```text
.
├── backend/
│   ├── manage.py
│   ├── config/
│   └── src/f1_simulator/
│       ├── domain/
│       ├── application/
│       │   └── ports/
│       ├── adapters/
│       │   ├── django/
│       │   ├── datasets/
│       │   └── persistence/
│       └── factories/
├── frontend/
│   └── arcade/                    # views, desenho, controles e cliente HTTP
├── data/
│   ├── raw/
│   ├── curated/
│   └── parameters/
├── scripts/
│   ├── ingest_data.py
│   ├── validate_data.py
│   └── calibrate_model.py
└── tests/
    ├── unit/
    ├── integration/
    └── acceptance/
```

Os nomes exatos dependem da decisão arquitetural formal. O importante é que
Arcade, Django, datasets e persistência permaneçam nas bordas e que o domínio
não dependa deles.

Os arquivos grandes de `data/raw` e `data/curated` devem entrar no `.gitignore`. Um arquivo pequeno de exemplo pode ser versionado para os testes.

## 10. Próximos passos acordados

1. Validar um spike de Arcade com troca entre `arcade.View`, pista simples e
   execução sem janela para os testes que não precisam de renderização.
2. Estudar o `IAmTomShaw/f1-race-replay`, registrando apenas ideias
   aproveitáveis, limitações e licença; não copiar estrutura, código ou recursos
   sem relacioná-los aos requisitos e preservar as atribuições aplicáveis.
3. Buscar datasets além dos sugeridos pelo professor e comparar cobertura,
   granularidade, qualidade, licença e facilidade de integração.
4. Escolher o único dataset e o único circuito do MVP.
5. Escrever e aprovar o ADR que compara MVC com arquitetura hexagonal e registra
   a decisão do grupo, suas consequências e a organização resultante.
6. Confirmar se combustível e interação física entre carros ficam fora do MVP
   ou se alguma aproximação mínima será critério de aceite.
7. Planejar e acompanhar o trabalho nas GitHub Issues, mantendo
   `docs/backlog.md` como espelho gerado para agentes e consulta offline.

## 11. Plano incremental de implementação

### Fase 0 — contrato do MVP

- escolher uma corrida e um circuito de referência;
- decidir e aprovar o ADR de arquitetura, comparando MVC e arquitetura hexagonal;
- selecionar o dataset do MVP e registrar sua versão e licença;
- validar Arcade/OpenGL nos ambientes do grupo;
- definir os contratos HTTP/JSON, as três `arcade.View` e as métricas obrigatórias;
- resolver a divergência de escopo sobre combustível e interação física;
- criar critérios de aceitação e uma semente de demonstração.

### Fase 1 — dados e exploração

- implementar o adaptador e o ETL do único dataset selecionado;
- criar validações e esquema canônico;
- produzir um conjunto pequeno e reproduzível para testes;
- realizar a análise exploratória necessária ao cenário escolhido.

### Fase 2 — domínio determinístico

- modelar entidades, estados, comandos e retratos;
- implementar corrida sem eventos aleatórios;
- adicionar apenas as regras necessárias para concluir a corrida do cenário do MVP;
- testar classificação, término e invariantes.

### Fase 3 — backend Django e aplicação desktop

- integrar o backend Django aos casos de uso por portas de entrada;
- definir e testar o contrato HTTP/JSON entre Django e o cliente;
- implementar `ParametersView`, `RaceView` e `ResultsView` com Arcade;
- desenhar circuito, marcadores e classificação a partir de `RaceSnapshot`;
- consultar snapshots em intervalo controlado sem bloquear o laço de eventos;
- tratar validações e falhas de comunicação sem mover regras para a interface.

### Fase 4 — integração e entrega do MVP

- executar pelo cliente Arcade uma corrida completa no circuito selecionado;
- verificar o resultado contra invariantes e referências do dataset;
- medir tempo e memória de uma corrida completa;
- preparar cenário de demonstração reproduzível;
- executar testes automatizados e análise estática;
- revisar atribuições, licença e instruções de execução.

### Fase 5 — evolução do modelo

- implementar `Strategy`, `State` e eventos de domínio quando exigidos pelos casos de uso;
- adicionar clima, DNF, SC e VSC;
- avaliar e implementar a modelagem de combustível aprovada pelo grupo;
- avaliar interação física entre carros, incluindo vácuo e restrição de sobreposição;
- criar perfis de pilotos a partir de análise e perfilamento dos dados.

### Fase 6 — expansão de dados, calibração e validação

- implementar novos adaptadores somente para datasets incorporados ao projeto;
- calibrar parâmetros usando corridas separadas da validação;
- medir MAE/RMSE dos tempos e erro de posição final;
- comparar distribuições de *stints*, pits e DNF;
- documentar hipóteses, limitações e sensibilidade dos parâmetros.

## 12. Estratégia de testes

### Testes unitários

- um carro retirado não volta à corrida;
- uma corrida terminada não avança;
- classificação respeita voltas e distância antes do tempo total;
- objetos construídos pela Factory respeitam suas invariantes;
- mesma semente produz a mesma sequência de eventos.

Quando as extensões correspondentes forem implementadas, acrescentar testes
para combustível não negativo, idade dos pneus, pit stops, estados de bandeira
e impossibilidade de dois carros ocuparem fisicamente o mesmo espaço.

### Testes baseados em propriedades

- o tempo e a distância total de um carro ativo são monotônicos;
- o número de carros ativos nunca aumenta após a largada;
- toda volta concluída possui tempo positivo;
- toda posição pertence ao intervalo válido e não se repete no mesmo retrato.

### Testes de integração

- o adaptador do MVP converte uma amostra real para o esquema canônico;
- a Factory constrói a corrida a partir dos dados normalizados pelo adaptador;
- chaves entre corridas, pilotos, voltas e stints são válidas;
- um cenário salvo pode ser carregado e reproduzido;
- Django aciona os casos de uso sem importar regras para suas *views*;
- a visualização recebe pontos ordenados e posições dentro do comprimento da pista.
- o cliente HTTP converte respostas em DTOs da apresentação e trata timeout sem bloquear a janela;
- apresentadores e controladores do Arcade podem ser testados sem contexto OpenGL.

### Testes de aceitação

- informar os parâmetros aceitos em `ParametersView`;
- iniciar e acompanhar uma corrida completa em `RaceView`;
- pausar/continuar, ajustar a velocidade visual e reiniciar pelos controles do Arcade;
- consultar a classificação final em `ResultsView`;
- rejeitar uma configuração inválida com mensagem compreensível;
- repetir o cenário de demonstração com a mesma semente e obter o mesmo resultado.

## 13. Tecnologias e decisões atuais

| Área | Tecnologia |
| --- | --- |
| Linguagem do motor e backend | Python 3.12+ |
| Backend web | Django |
| Frontend desktop | Arcade |
| Gráficos e pista 2D | Primitivas, textos, sprites e `arcade.View` |
| Integração frontend/backend | HTTP/JSON com consultas periódicas no MVP |
| Transformação tabular | Pandas ou Polars |
| Arquivos analíticos | Parquet com PyArrow |
| Persistência local | SQLite |
| Validação de configuração | dataclasses ou Pydantic |
| Testes | pytest, Hypothesis para propriedades |
| Qualidade | Ruff e Pyright/Mypy |

SimPy é opcional. O MVP pode usar um relógio discreto explícito, mais simples de testar. Adotar SimPy apenas se a fila de eventos concorrentes e suas prioridades justificarem a dependência; o restante do domínio deve continuar independente dele.

## 14. Ideias para etapas posteriores

Os itens abaixo são relevantes, mas não deverão bloquear o núcleo do MVP até
que o grupo os promova explicitamente a requisitos:

- modelar a quantidade de combustível e seu consumo ao longo da corrida;
- refletir no desempenho a redução de massa causada pelo consumo de combustível;
- analisar os dados para definir perfis de comportamento e desempenho de pilotos;
- modelar o vácuo aerodinâmico aproveitado por um carro que segue outro;
- representar os carros como corpos materiais, impedindo sobreposição e ultrapassagem física impossível.

Cada item precisará de hipótese explícita, dados de calibração, unidade,
parâmetros configuráveis e testes antes de ser incorporado ao motor.

## 15. Riscos e decisões a registrar

| Risco | Mitigação |
| --- | --- |
| Escopo excessivo | Um circuito e uma corrida completa antes de generalizar. |
| Combustível e interação física com escopo contraditório | Resolver na Fase 0 e só então incluí-los nos critérios de aceite. |
| Arquitetura implementada antes da aprovação | Aceitar o ADR antes de criar a estrutura definitiva. |
| Arcade/OpenGL indisponível em algum ambiente | Executar o spike da Fase 0 nos ambientes do grupo e documentar requisitos e falhas. |
| Laço gráfico bloqueado por rede ou simulação | Cliente HTTP não bloqueante e tempo simulado independente de `on_update`. |
| Modelo aparentemente preciso, mas sem evidência | Exibir decomposição do tempo e parâmetros calibrados. |
| Junções erradas entre bases | IDs internos e tabelas de correspondência auditáveis. |
| Telemetria pesada | Agregação prévia e Parquet; nunca carregar tudo na UI. |
| Atualização visual complexa | Começar com retratos periódicos e validar a necessidade de tempo real. |
| Resultado não reproduzível | Semente, parâmetros e versão dos dados em cada execução. |
| Licença desconhecida da Base 2 | Confirmar antes de redistribuir os arquivos. |
| Dados históricos incompatíveis entre eras | Calibrar por era/regulamento e validar em corridas recentes. |

## 16. Referências técnicas e de dados

- [Documentação do Django](https://docs.djangoproject.com/)
- [Documentação do Python Arcade](https://api.arcade.academy/)
- [IAmTomShaw/f1-race-replay — referência visual em Arcade](https://github.com/IAmTomShaw/f1-race-replay)
- [Base 1 — F1-Tyre-Strategy-Engine Datasets](https://www.kaggle.com/datasets/vanshbatra26/f1-tyre-strategy-engine-datasets)
- [Base 2 — Formula 1: Race Data and Telemetry](https://www.kaggle.com/datasets/alexjr2001/formula-1-dataset-race-data-and-telemetry)
- [Base 3 — Formula 1 Race Data](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data)

---

### Decisões resumidas

- **MVP:** um dataset, um ETL, um circuito, uma corrida completa e três telas.
- **Frontend:** aplicação desktop Python com Arcade e três `arcade.View`.
- **Backend:** Django como adaptador web; regras da corrida permanecem independentes do framework.
- **Integração:** HTTP/JSON com consultas periódicas; sem WebSocket no MVP.
- **Arquitetura:** hexagonal encaminhada na reunião e pendente de formalização em ADR; MVC será documentada como alternativa considerada.
- **Padrões:** uso combinado de Adapter para normalização e Factory para construção de objetos complexos.
- **Motor:** Python independente da interface e do formato das bases.
- **Evoluções:** combustível detalhado, perfis de pilotos e interação física entre carros não bloqueiam o núcleo do MVP enquanto o grupo não resolver a divergência de escopo.
- **Reprodutibilidade:** semente, versão dos dados e parâmetros registrados em toda simulação.
