# Plano de desenvolvimento — Simulador de Corrida de Fórmula 1

## 1. Objetivo e recorte do projeto

O sistema permitirá configurar e executar uma corrida de Fórmula 1 simulada e acompanhar sua evolução em um painel 2D. O foco será a estratégia de corrida e o comportamento dos dados, não uma reprodução física ou gráfica 3D.

O simulador deverá considerar, no mínimo:

- circuito, número de voltas, pilotos e equipes;
- ritmo-base de carro e piloto;
- composto, idade e degradação dos pneus;
- consumo de combustível;
- paradas nos boxes;
- clima e condição da pista;
- falhas, acidentes, bandeiras, *Virtual Safety Car* (VSC) e *Safety Car* (SC);
- classificação, intervalos, tempos de volta e histórico de eventos.

O usuário deverá conseguir:

1. selecionar um cenário e ajustar seus parâmetros;
2. iniciar, pausar, avançar e reiniciar a simulação;
3. emitir comandos de estratégia, como uma parada e a escolha do próximo composto;
4. acompanhar a posição dos carros no circuito, a classificação e a telemetria resumida;
5. repetir uma corrida com a mesma semente aleatória e comparar estratégias.

### Fora do escopo inicial

- física veicular de alta fidelidade;
- gráficos 3D;
- reprodução a 60 quadros por segundo;
- dados oficiais em tempo real durante um Grande Prêmio;
- microsserviços, autenticação ou implantação distribuída;
- aprendizado de máquina como requisito para o primeiro protótipo.

Esses itens podem ser extensões, mas não devem bloquear o MVP.

## 2. Decisão sobre a interface: Python com Streamlit

É viável manter praticamente todo o código escrito pela equipe em Python. A recomendação para este projeto é usar **Streamlit** na interface e **Plotly** na visualização do circuito e dos gráficos.

Uma aplicação Streamlit continua tendo cliente e servidor: o código Python executa no servidor e o navegador atua como cliente. Entretanto, a equipe não precisa manter um *frontend* próprio em JavaScript. O Streamlit gera e atualiza a interface do navegador, aceita componentes Plotly produzidos em Python e mantém variáveis entre reexecuções por meio do estado da sessão.

### Por que essa opção é adequada

- todos os integrantes podem trabalhar predominantemente em Python;
- formulários, seletores, tabelas e gráficos exigem pouco código de apresentação;
- Plotly permite desenhar a polilinha da pista e os carros como marcadores interativos;
- o painel pode ser atualizado periodicamente com um fragmento Streamlit, sem criar manualmente uma conexão WebSocket;
- a equipe pode concentrar esforço no domínio, nos dados, na calibração e nos testes;
- a aplicação continua acessível no navegador e é simples de demonstrar em sala.

### Limitação assumida

Streamlit é apropriado para um painel que atualiza algumas vezes por segundo ou a cada setor/volta, mas não para uma animação contínua de jogo. No MVP, a corrida deve avançar em **passos de simulação** e o painel deve atualizar entre 250 ms e 1 s, independentemente do tempo simulado transcorrido.

Se, após o MVP, a animação suave se tornar um requisito prioritário, há duas alternativas:

1. criar apenas um componente visual customizado em JavaScript, mantendo todo o domínio e a aplicação em Python; ou
2. trocar somente a camada de interface por PySide6, caso uma aplicação desktop seja aceitável.

A primeira alternativa preserva a implantação web; a segunda elimina o navegador, mas aumenta o trabalho de interface e distribuição. Nenhuma delas é necessária no escopo inicial.

### Organização sugerida das telas

| Tela | Responsabilidade |
| --- | --- |
| Configuração | Escolher corrida, pilotos, clima, semente e estratégias iniciais. |
| Simulação | Exibir pista 2D, classificação, volta, bandeira, clima, pneus e controles. |
| Análise | Comparar o resultado simulado com dados históricos e outras estratégias. |
| Qualidade dos dados | Mostrar fontes, versão, cobertura, campos ausentes e validações da carga. |

O objeto do motor não deve ser implementado dentro da página. A sessão da interface guarda apenas o identificador ou a instância da simulação ativa e delega comandos ao controlador ou à camada de aplicação, conforme a arquitetura escolhida pelo grupo.

## 3. Estilo arquitetural

### 3.1 Decisão a ser tomada pelo grupo

A organização arquitetural **não está definida por este documento**. O grupo deverá escolher e registrar a alternativa que considerar mais adequada antes de iniciar a implementação estrutural. Duas opções compatíveis com o projeto são apresentadas abaixo: **MVC** e **arquitetura em camadas com portas e adaptadores**.

Independentemente da escolha, o projeto pode ser entregue como um único programa Python — um monólito modular — sem microsserviços. Também devem ser preservadas estas separações mínimas:

- regras da corrida não ficam dentro das páginas Streamlit;
- leitura de Kaggle, CSV, Parquet ou SQLite não fica dentro do motor;
- o estado da interface não é a fonte de verdade da corrida;
- o motor pode ser testado sem abrir o navegador;
- componentes não devem depender de detalhes que não utilizam.

### 3.2 Alternativa A — MVC

No padrão **Model–View–Controller (MVC)**, as responsabilidades podem ser distribuídas assim:

| Elemento | Responsabilidade no simulador |
| --- | --- |
| Model | Entidades, estado da corrida, motor, estratégias, regras, repositórios e dados. |
| View | Páginas Streamlit, tabelas, mensagens e figuras Plotly. |
| Controller | Receber ações da interface, validá-las, chamar o Model e selecionar os dados entregues à View. |

Fluxo típico:

```text
Usuário -> View Streamlit -> Controller -> Model
             ^                            |
             |------- RaceSnapshot -------|
```

MVC tem nomenclatura conhecida, mapeia diretamente as interações da interface e pode ser mais simples para a equipe. É importante, porém, impedir que o Controller concentre todas as regras: cálculo de volta, estratégia, estados de bandeira e eventos pertencem ao Model.

### 3.3 Alternativa B — camadas com portas e adaptadores

Nesta alternativa, a aplicação é organizada em apresentação, casos de uso, domínio e infraestrutura. Portas abstraem as integrações, e adaptadores convertem cada fonte para o modelo interno.

```text
Interface Streamlit -> Casos de uso -> Domínio
                              ^
                              |
                    Portas e adaptadores
                              |
                 Dados e persistência
```

Exemplos de portas possíveis:

- `RaceDataRepository` — consulta corridas, pilotos, resultados e voltas;
- `TelemetryRepository` — consulta amostras de velocidade, acelerador e setores;
- `TyreModelRepository` — fornece parâmetros e estatísticas de *stints*;
- `SimulationResultRepository` — salva cenários, sementes e resultados;
- `RandomSource` — gera eventos aleatórios de maneira substituível e testável.

Essa opção explicita melhor as dependências externas e facilita substituir fontes de dados, mas introduz mais interfaces e arquivos. O grupo deve adotá-la somente se considerar esse custo justificado.

### 3.4 Critérios para a escolha

| Critério | MVC | Camadas com portas e adaptadores |
| --- | --- | --- |
| Curva de aprendizagem | Geralmente menor. | Geralmente maior. |
| Correspondência com a interface | Direta por View e Controller. | Interface tratada como camada de apresentação. |
| Isolamento das fontes de dados | Possível com Repository/Adapter. | Central na organização proposta. |
| Quantidade inicial de abstrações | Menor. | Maior. |
| Facilidade de trocar a interface | Boa se o Model estiver isolado. | Boa por definição das dependências. |
| Adequação ao MVP | Boa. | Boa, se a equipe dominar a abordagem. |

A escolha deve ser registrada em uma decisão arquitetural curta, contendo contexto, alternativa selecionada, justificativa e consequências. MVC não impede o uso dos padrões Repository, Adapter, Strategy ou State; esses padrões resolvem problemas diferentes.

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
| Interface Streamlit | Capturar configuração e comandos; apresentar o estado. | Ações do usuário e `RaceSnapshot`. | Comandos para os casos de uso. |
| Controladores ou casos de uso | Orquestrar criação, avanço, pausa, reinício e comparação, conforme a arquitetura escolhida. | Comandos e identificadores. | Retratos, relatórios e erros de aplicação. |
| Motor de simulação | Avançar o relógio simulado e aplicar regras. | `RaceState`, comandos, parâmetros e fonte aleatória. | Novo estado e eventos de domínio. |
| Modelo de tempo de volta | Calcular ritmo e penalidades de cada carro. | Circuito, piloto, carro, pneu, combustível, clima e tráfego. | Tempo previsto e seus componentes. |
| Gerenciador de estratégia | Decidir ou validar pneus e paradas. | Estado do carro e condições da corrida. | Comando de parada ou permanência. |
| Gerenciador de corrida | Controlar largada, bandeiras, SC/VSC e término. | Eventos e relógio. | Estado global da prova. |
| Ingestão e validação | Ler arquivos brutos, padronizar tipos e validar qualidade. | CSV/Parquet das fontes. | Tabelas canônicas e relatório de qualidade. |
| Calibração | Estimar parâmetros a partir de corridas históricas. | Tabelas canônicas. | Arquivo versionado de parâmetros. |
| Persistência | Salvar dados tratados, cenários e resultados. | Objetos e tabelas internas. | Consultas reprodutíveis. |
| Visualização 2D | Projetar a pista e posicionar marcadores por progresso. | Geometria, progresso e classificação. | Figura Plotly. |

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
- um WebSocket criado pela equipe: o Streamlit já mantém a comunicação com o navegador.

## 6. Dados sugeridos pelo professor

As três bases são complementares e devem ser registradas com versão/data de download e licença. Arquivos brutos nunca devem ser editados manualmente.

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

1. **Aquisição:** baixar manualmente ou por API uma versão identificável de cada base.
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

### 7.2 Esquema canônico mínimo

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

Separar **tempo simulado** de **tempo da interface**. O motor pode avançar por setor no MVP. Cada chamada a `advance()` processa o próximo setor ou evento e retorna um novo `RaceSnapshot`. O Streamlit apenas decide com que frequência chamar o caso de uso.

Esse desenho evita que `sleep`, taxa de atualização do navegador ou desempenho da máquina alterem o resultado da corrida.

### 8.2 Tempo de volta

Uma primeira aproximação auditável é:

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
4. desenhar a pista como linha e cada carro como marcador Plotly.

A classificação deve ser calculada pelo estado do domínio. A posição gráfica não deve ser usada como fonte de verdade.

## 9. Estrutura de diretórios sugerida

Os diretórios comuns às duas alternativas podem ser organizados assim:

```text
.
├── app.py
├── pages/
│   ├── configuracao.py
│   ├── simulacao.py
│   ├── analise.py
│   └── qualidade_dados.py
├── src/f1_simulator/
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

Se o grupo escolher **MVC**, uma possibilidade para `src/f1_simulator/` é:

```text
src/f1_simulator/
├── model/
│   ├── entities.py
│   ├── events.py
│   ├── race_state.py
│   ├── engine.py
│   ├── strategies.py
│   └── repositories.py
├── views/
│   ├── track_plot.py
│   ├── leaderboard.py
│   └── session.py
├── controllers/
│   ├── simulation_controller.py
│   └── analysis_controller.py
└── data/
    ├── datasets/
    ├── persistence/
    └── calibration/
```

Se o grupo escolher **camadas com portas e adaptadores**, uma possibilidade é:

```text
src/f1_simulator/
├── domain/
│   ├── entities.py
│   ├── events.py
│   ├── race_state.py
│   ├── engine.py
│   └── strategies.py
├── application/
│   ├── commands.py
│   ├── use_cases.py
│   └── ports.py
├── infrastructure/
│   ├── datasets/
│   ├── persistence/
│   └── calibration/
└── presentation/
    ├── track_plot.py
    ├── leaderboard.py
    └── session.py
```

Essas árvores são exemplos, não decisões. Depois da escolha, o grupo deve manter uma única organização e evitar misturar nomes de MVC e de arquitetura em camadas sem uma justificativa clara.

Os arquivos grandes de `data/raw` e `data/curated` devem entrar no `.gitignore`. Um arquivo pequeno de exemplo pode ser versionado para os testes.

## 10. Plano incremental de implementação

### Fase 0 — contrato do MVP

- escolher uma corrida e um circuito de referência;
- comparar MVC e camadas com portas/adaptadores e registrar a decisão do grupo;
- definir as telas e métricas obrigatórias;
- registrar versões e licenças das três bases;
- criar critérios de aceitação e uma semente de demonstração.

### Fase 1 — dados e exploração

- implementar os três adaptadores de entrada;
- criar validações e esquema canônico;
- produzir um conjunto pequeno e reproduzível para testes;
- realizar análise exploratória de voltas, stints, clima, pits e abandonos.

### Fase 2 — domínio determinístico

- modelar entidades, estados, comandos e retratos;
- implementar corrida sem eventos aleatórios;
- adicionar pneus, combustível e pit stop;
- testar classificação, término e invariantes.

### Fase 3 — estratégias e eventos

- implementar `Strategy`, `State` e eventos de domínio;
- adicionar clima, DNF, SC e VSC;
- injetar o gerador aleatório com semente;
- comparar ao menos três estratégias de pneus.

### Fase 4 — interface Python

- criar configuração em formulário Streamlit;
- armazenar a simulação ativa no estado da sessão;
- desenhar circuito, marcadores, classificação e histórico com Plotly;
- atualizar apenas o painel da corrida em intervalo controlado;
- incluir iniciar, pausar, avançar, acelerar e reiniciar.

### Fase 5 — calibração e validação

- calibrar parâmetros usando corridas separadas da validação;
- medir MAE/RMSE dos tempos e erro de posição final;
- comparar distribuições de stints, pits e DNF;
- documentar hipóteses, limitações e sensibilidade dos parâmetros.

### Fase 6 — robustez e entrega

- executar testes automatizados e análise estática;
- medir tempo e memória de uma corrida completa;
- preparar cenário de demonstração reproduzível;
- revisar atribuições, licenças e instruções de execução.

## 11. Estratégia de testes

### Testes unitários

- pneus nunca têm idade negativa;
- combustível nunca fica negativo;
- um carro retirado não volta à corrida;
- uma corrida terminada não avança;
- classificação respeita voltas e distância antes do tempo total;
- pit stop troca o composto e reinicia a idade do pneu;
- transições de `RaceState` inválidas são rejeitadas;
- mesma semente produz a mesma sequência de eventos.

### Testes baseados em propriedades

- o tempo e a distância total de um carro ativo são monotônicos;
- o número de carros ativos nunca aumenta após a largada;
- toda volta concluída possui tempo positivo;
- toda posição pertence ao intervalo válido e não se repete no mesmo retrato.

### Testes de integração

- cada adaptador converte uma amostra real para o esquema canônico;
- chaves entre corridas, pilotos, voltas e stints são válidas;
- um cenário salvo pode ser carregado e reproduzido;
- a figura recebe pontos ordenados e posições dentro do comprimento da pista.

### Testes de aceitação

- configurar e concluir uma corrida pela interface;
- pausar, avançar uma etapa e retomar;
- comandar uma parada e observar a troca de composto;
- repetir com a mesma semente e obter o mesmo resultado;
- mudar somente a estratégia e produzir uma comparação legível.

## 12. Tecnologias recomendadas

| Área | Tecnologia |
| --- | --- |
| Linguagem | Python 3.12+ |
| Interface | Streamlit |
| Gráficos e pista 2D | Plotly |
| Transformação tabular | Pandas ou Polars |
| Arquivos analíticos | Parquet com PyArrow |
| Persistência local | SQLite |
| Validação de configuração | dataclasses ou Pydantic |
| Testes | pytest, Hypothesis para propriedades |
| Qualidade | Ruff e Pyright/Mypy |

SimPy é opcional. O MVP pode usar um relógio discreto explícito, mais simples de testar. Adotar SimPy apenas se a fila de eventos concorrentes e suas prioridades justificarem a dependência; o restante do domínio deve continuar independente dele.

## 13. Riscos e decisões a registrar

| Risco | Mitigação |
| --- | --- |
| Escopo excessivo | Um circuito e uma corrida completa antes de generalizar. |
| Modelo aparentemente preciso, mas sem evidência | Exibir decomposição do tempo e parâmetros calibrados. |
| Junções erradas entre bases | IDs internos e tabelas de correspondência auditáveis. |
| Telemetria pesada | Agregação prévia e Parquet; nunca carregar tudo na UI. |
| Animação limitada no Streamlit | Atualização por passos; componente customizado somente como extensão. |
| Resultado não reproduzível | Semente, parâmetros e versão dos dados em cada execução. |
| Licença desconhecida da Base 2 | Confirmar antes de redistribuir os arquivos. |
| Dados históricos incompatíveis entre eras | Calibrar por era/regulamento e validar em corridas recentes. |

## 14. Referências técnicas e de dados

- [Streamlit — arquitetura cliente-servidor](https://docs.streamlit.io/develop/concepts/architecture/architecture)
- [Streamlit — fragmentos e atualizações periódicas](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment)
- [Streamlit — estado da sessão](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)
- [Streamlit — gráficos Plotly](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart)
- [Plotly para Python](https://plotly.com/python/)
- [Base 1 — F1-Tyre-Strategy-Engine Datasets](https://www.kaggle.com/datasets/vanshbatra26/f1-tyre-strategy-engine-datasets)
- [Base 2 — Formula 1: Race Data and Telemetry](https://www.kaggle.com/datasets/alexjr2001/formula-1-dataset-race-data-and-telemetry)
- [Base 3 — Formula 1 Race Data](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data)

---

### Decisões resumidas

- **Interface:** Streamlit + Plotly, sem JavaScript escrito pela equipe no MVP.
- **Arquitetura:** decisão do grupo entre MVC e camadas com portas e adaptadores; ambas podem ser implementadas como monólito modular.
- **Motor:** Python independente da interface e do formato das bases.
- **Comunicação:** chamadas no mesmo processo; sem API e WebSocket próprios no MVP.
- **Persistência:** Parquet para dados analíticos e SQLite para cenários/resultados.
- **Reprodutibilidade:** semente, versão dos dados e parâmetros registrados em toda simulação.
