# Planejamento da modelagem do simulador

**Status: proposta de modelagem, sem implementação. A escolha de FastAPI foi
confirmada e registrada no ADR 0004; os demais recortes continuam em discussão.**
Levantamento em 11/09/2026: `develop` em `3ea8a0b` e `origin/main` em
`570b631`, com árvores de arquivos idênticas antes desta alteração documental.
O backlog foi sincronizado do GitHub. As recomendações abaixo não alteram o
estado das issues nem tornam hipóteses do modelo em dados observados.

## 1. Escopo desta etapa e referências

O pedido atual é planejar a modelagem e o perfilamento de pilotos, adiar a
integração da pista até o contrato do colega e usar interfaces Python para a
colaboração entre módulos locais. O detalhamento de dados e etapas está em
[Perfilamento de pilotos](perfilamento-pilotos.md). Nesta etapa
não serão implementados modelos, clientes HTTP, endpoints ou novas fontes.
O usuário esclareceu que o modelo de pista desejado ainda não foi implementado;
a composição por trechos e suas propriedades é trabalho posterior. A existência
de latitude/longitude no cadastro não representa essa modelagem.

Este levantamento se apoia em [CONTRIBUTING.md](../CONTRIBUTING.md), no
[plano do produto](../Desenvolvimento%20de%20Simulador%20F1.md), especialmente
nas seções 1, 3, 4, 7, 8 e 11, e nos ADRs
[0001](adr/0001-frontend-desktop-com-arcade.md),
[0002](adr/0002-arquitetura-hexagonal-e-integracao-de-dados.md),
[0003](adr/0003-geometria-mockada-derivada-do-fastf1.md) e
[0004](adr/0004-backend-fastapi-e-contratos-python.md).
O [fluxo do ETL](fluxo-etl.md) descreve os contratos já implementados.

O plano prioriza uma corrida completa e determinística antes de efeitos
estocásticos e física detalhada. Modelagem de combustível e interação física
entre carros continuam com escopo pendente; a existência de novas ideias nas
issues não resolve essa divergência automaticamente.

## 2. Issues encontradas

O épico [#40 — Modelagem dos dados](https://github.com/guilherme-webster/mc857-o-projeto/issues/40)
está aberto, atribuído a `@DaviGabrielBC`, e descreve a correlação dos atributos
de carro e piloto com o tempo de volta. Suas cinco frentes também estão abertas:

| Frente | Conteúdo encontrado na descrição e nos comentários | Subtarefas |
| --- | --- | --- |
| [#51 — Pistas de corrida](https://github.com/guilherme-webster/mc857-o-projeto/issues/51) | Consumir a interface do backend; compor uma pista com objetos de trechos; disponibilizar informações como curva/reta e atrito. | Sem sub-issues no levantamento. |
| [#60 — Carros](https://github.com/guilherme-webster/mc857-o-projeto/issues/60) | Peso, potência e aerodinâmica, obtidos de dados reais ou parâmetros de modelagem, com impacto no resultado da corrida a ser estudado. | [#64 — Consumo do backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/64), [#65 — Modelagem posterior](https://github.com/guilherme-webster/mc857-o-projeto/issues/65). |
| [#61 — Pilotos](https://github.com/guilherme-webster/mc857-o-projeto/issues/61) | Peso, altura e perfis de pilotos reais ou personas; separar atributos obtidos da fonte e comportamentos definidos pelo modelo. | [#66 — Consumir backend](https://github.com/guilherme-webster/mc857-o-projeto/issues/66), [#67 — Modelagem pilotos](https://github.com/guilherme-webster/mc857-o-projeto/issues/67). |
| [#62 — Clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/62) | Chuva, neblina, atrito, visibilidade e interação com decisões dos pilotos, como insistência em ultrapassagens. | [#68 — Consumir backend para modelar clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/68), [#69 — Modelagem clima](https://github.com/guilherme-webster/mc857-o-projeto/issues/69). |
| [#63 — Pneu](https://github.com/guilherme-webster/mc857-o-projeto/issues/63) | Apenas o título: faltam descrição e critérios de aceitação. | Sem sub-issues no levantamento. |

As cinco frentes estão atribuídas a `@guilherme-webster`. Entre #64–#69,
somente #67 está sem responsável; as demais estão atribuídas a
`@guilherme-webster`. #68 não tem descrição. As descrições de #65, #67 e #69
ainda são genéricas; não definem entradas, saídas, unidades ou comportamento
observável suficiente para implementar seus modelos completos.

Também foram encontradas [#70 — Consumir dados da modelagem](https://github.com/guilherme-webster/mc857-o-projeto/issues/70)
e [#71 — Executar simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/71),
ambas abertas, sem responsável, filhas de
[#8 — Rodar Simulação](https://github.com/guilherme-webster/mc857-o-projeto/issues/8).
Essas issues serão consumidoras dos modelos; convém refinar seus critérios
cedo, para os modelos produzirem algo que a corrida realmente utiliza.

Dependências de integração relacionadas: [#43](https://github.com/guilherme-webster/mc857-o-projeto/issues/43)
(endpoints), [#47](https://github.com/guilherme-webster/mc857-o-projeto/issues/47)
(Trotman no container) e [#54](https://github.com/guilherme-webster/mc857-o-projeto/issues/54)
(dados da pista no container), todas abertas e sem responsável registrado.
Essas relações são dependências técnicas sugeridas por este levantamento, não
novos vínculos de bloqueio cadastrados no GitHub. A issue #51 foi reaberta;
o fechamento de #34/#53, relativas ao ETL, não significa que a modelagem de
trechos ou sua integração esteja pronta.

## 3. Estado do código e disponibilidade dos dados

Há quatro níveis diferentes: o dado existir na fonte, estar normalizado no
ETL, estar materializado em um banco e estar disponível no contrato de consumo.
Um nível não garante automaticamente o próximo.

| Informação | Evidência atual | Até onde permite avançar |
| --- | --- | --- |
| Pilotos e equipes | `Driver`, `Team`, `RaceEntry` e IDs canônicos em [race_data.py](../src/f1_simulator/domain/race_data.py). | Identidade, vínculo do participante com a equipe e dados históricos da inscrição. Não há entidade física de carro nem perfil comportamental de piloto. |
| Tempos de volta, posições, largada, classificação e abandonos | `Lap`, `RaceEntry` e `PitStop`; leitura por `RaceDataRepository`. | Referência de desempenho observado. O tempo mistura efeitos de piloto, carro, pneus, clima e situação de corrida; não identifica cada contribuição separadamente. |
| Geometria | 24 geometrias reduzidas de 2025 com 240 pontos de pista e 80 de pit lane por circuito, [manifestos](../data/sources/fastf1-tracks-2025.json) e [contrato](../src/f1_simulator/domain/track_geometry.py). | Desenho e futuro posicionamento por distância acumulada; segmentação geométrica aproximada, a validar. Não informa atrito, material, largura física, inclinação ou setores oficiais. |
| Clima configurado pelo usuário | `WeatherSchedule` em [configuration_state.py](../frontend/arcade/configuration_state.py): seco, chuva leve e chuva intensa por volta. | Entrada de cenário e apresentação. Não é observação meteorológica nem modelo do efeito da chuva no desempenho. |
| Peso, potência e aerodinâmica do carro | Ausentes dos contratos canônicos e dos cabeçalhos do ZIP Trotman inspecionado. | Só podem entrar inicialmente como hipóteses configuradas e identificadas, se o grupo aprovar esse escopo. Não há suporte para calibrar física veicular com os dados atuais. |
| Peso, altura e perfil de piloto | Não constam do contrato nem do CSV original de pilotos inspecionado. | Cadastro e desempenho observado são possíveis; personas sintéticas exigem regras explícitas. Não atribuir agressividade ou habilidade real com base apenas em resultado, nome ou aparência. |
| Compostos, idade e degradação dos pneus | Não há tabela canônica de stints/compostos, nem esses campos no ZIP Trotman inspecionado. | Pode-se especificar um modelo hipotético de desgaste; não calibrá-lo por composto com a ingestão atual. Registro de pit stop não prova qual pneu foi instalado. |
| Chuva, neblina, temperaturas, aderência e bandeiras ao longo da volta | Ausentes do agregado canônico atual. `status` é a situação de término do participante, não uma série de bandeiras ou clima. | Não há base para estimar efeitos reais por volta ou trecho nem para identificar todas as voltas de pista livre. |

O ZIP v128 local tem 14 CSVs, mas o adapter atual consome oito para uma corrida
por execução. Por exemplo, `dob` e `nationality` existem no CSV de pilotos e
não são expostos no contrato; `qualifying.csv` existe na fonte e não é ingerido.
Logo, dado ausente do contrato nem sempre exige outra fonte. Antes de ampliar
o ETL, é preciso provar sua utilidade para o modelo e distinguir esse caso dos
atributos que realmente não existem na base.

O banco local inspecionado na pasta original `mc857-o-projeto` contém a corrida
1141, circuito 18, temporada 2024 e 1.133 registros de volta, mas não contém
as tabelas de geometria. Não havia SQLite em `data/curated/` no worktree
`mc857-etl-geometria`. Isso descreve somente esses diretórios locais, não o
ambiente do colega ou um container em execução. A geração opcional da geometria
existe no código; sua publicação ao backend ainda precisa ser conferida nas
issues #47/#54. Nenhum artefato foi gerado ou alterado nesta auditoria.

### Observações de integração para o colega do backend

Os itens abaixo descrevem `develop` em `3ea8a0b`. Em leitura posterior, a branch
`origin/43-criar-endpoints` em `0f6255d` apresentou rotas de pilotos e estimativas
de parâmetros. Essa evolução, ainda fora da árvore auditada, está descrita na
[pesquisa de perfilamento](perfilamento-pilotos.md#trabalho-encontrado-na-branch-da-issue-43)
e deve ser coordenada com #67 para evitar cálculos duplicados.

- As portas existentes são [RaceDataRepository](../src/f1_simulator/application/ports/race_data.py)
  (`get_race(race_id)`) e [TrackGeometryRepository](../src/f1_simulator/application/ports/track_geometry.py)
  (`get_geometry(circuit_id)`). São contratos Python, não endpoints HTTP.
- No código atual, `SQLiteRaceDataRepository.get_race()` reconstrói o histórico
  sem preencher `RaceData.geometry`, embora o campo opcional exista. O consumidor
  não pode assumir que essa consulta já traz os caminhos. É necessário definir
  uma composição explícita com o repository de geometria e conferir o mesmo
  `circuit_id`. A issue #32 só justifica `GetSimulationScenario` quando essa
  composição ou outra regra concreta for necessária; não para simplesmente
  repassar uma consulta.
- [backend/app/main.py](../backend/app/main.py) oferece inspeção genérica das
  tabelas com SQL direto e leitura de um JSON de corrida. Não foi encontrado ali
  um contrato semântico de cenário/modelagem que use os repositories. Expor um
  dump de tabelas não deve obrigar cada consumidor a refazer joins e validações.
- [backend/app/engine/simulation.py](../backend/app/engine/simulation.py) é um
  esboço com tempos e desgaste fixados no código. Ele acessa SQLite diretamente,
  consulta `drivers.id` onde o esquema canônico define `driver_id` e usa um
  caminho `/app/data/curated` diferente do volume `/data` do Compose. Essas são
  observações de leitura, não uma validação de execução do backend. Não adotar
  esse esboço como motor ou calibração já concluídos.
- Na árvore auditada, [OvalTrack](../frontend/arcade/oval_track.py) é um oval
  analítico fictício e [RaceSimulationView](../frontend/arcade/race_view.py)
  avança carros de teste com o tempo de quadro. Não foi localizado um modelo
  real de trechos consumindo CSV nessa árvore ou na branch remota
  `40-modelagem-dos-dados` inspecionada. O usuário confirmou nesta sessão que
  esse modelo ainda é trabalho futuro. O planejamento de #51 deve, portanto,
  prever construção do modelo sobre o contrato do backend e substituição do
  protótipo quando houver integração; não pressupor uma implementação de
  trechos existente apenas por haver cadastro e geometria no ETL.

## 4. Ordem recomendada

**Começar pelo recorte mínimo de pilotos e carros (#61/#67 e #60/#65), centrado
no participante da corrida e em um tempo de volta de referência.** É a parte
com dados históricos utilizáveis e que permite exercitar classificação e
término sem esperar parâmetros físicos inexistentes. Os cadastros já estão no
ETL; a contribuição da modelagem deve ser definir comportamento e invariantes,
não duplicar `Driver` e `Team` em uma nova hierarquia.

| Ordem sugerida | Entrega a discutir | Por que / condição para iniciar código |
| --- | --- | --- |
| 1 | Participante com IDs de piloto/equipe, inscrição e ritmo de referência positivo; separar cadastro, parâmetro e estado mutável. | Reutiliza o contrato atual. Começar com efeito conjunto piloto/equipe; não inventar uma separação entre potência do carro e habilidade do piloto. Seleção da amostra e regra do ritmo ainda precisam ser aprovadas. |
| 2 | Pista baseada no contrato canônico e, se necessário para uma regra concreta, composição por intervalos de distância. | A geometria já existe. Aguardar o colega e o contrato de consumo, conforme o pedido. Planejar os objetos é possível agora; implementar a integração permanece adiado. |
| 3 | Primeira corrida determinística completa, como recorte de #70/#71, usando os modelos mínimos anteriores. | Expõe cedo os contratos realmente necessários: avanço, término, classificação e snapshot. Não precisa aguardar todos os efeitos físicos de #60–#63. A sequência é proposta, não alteração do backlog. |
| 4 | Pneus (#63) e estado de clima (#62/#69), primeiro isolados e depois combinados. | Refinar #63. Começar por transições observáveis: idade/troca e agenda climática. Coeficientes de perda de tempo só entram como hipóteses explícitas ou após aquisição/calibração aprovada. |
| 5 | Perfis de decisão, efeitos de chuva/visibilidade sobre estratégia, potência/aerodinâmica e efeitos por trecho. | Dependem de cenário de referência, regras básicas, parâmetros identificáveis e critérios de validação. Evitar somar vários mecanismos que explicam a mesma perda de tempo. |

A implementação de endpoints não é pré-requisito para modelos puros. A frente
produtiva agora é especificar entradas, saídas, invariantes e exemplos de
aceitação, coordenando o contrato Python com o colega. As fatias futuras podem
ser testadas com dados canônicos pequenos e dependências injetadas, sem janela
ou rede. A integração da pista permanece adiada conforme o pedido.

### Referência inicial de ritmo: proposta, não calibração concluída

Um tempo fixo positivo por participante é suficiente para o primeiro teste
determinístico. Uma estimativa por estatística robusta das voltas históricas
pode ser avaliada depois de definir os filtros; nenhuma mediana ou coeficiente
é adotado por este documento. Excluir voltas iniciais e voltas com pit stop
registrado é possível, mas não identifica automaticamente chuva, SC/VSC,
entrada/saída dos boxes ou bandeira vermelha. O plano exige registrar essas
limitações, separar corridas de calibração e validação e não chamar a estimativa
de ritmo de pista livre quando os filtros necessários não podem ser aplicados.

Também não basta repetir as voltas históricas para afirmar que há um simulador:
o modelo deve gerar sua evolução a partir de estado, parâmetros e comandos.
Se o ritmo de referência já contém efeito de carro/piloto/clima/pneu, adicionar
novas parcelas sem redefinir a referência pode contar o mesmo efeito duas vezes.

## 5. Contratos e conceitos a refinar antes de implementar

Separar três responsabilidades: ETL normaliza fatos da fonte; modelagem define
estados/regras e estima ou configura parâmetros; simulação aplica essas regras
ao longo do tempo e gera resultados. Isso não exige três serviços nem um novo
framework. Modelos e regras continuam no núcleo Python, conforme o ADR 0002.

O caso de uso compõe os dados por repositories Python e entrega objetos e
parâmetros ao núcleo. FastAPI é um adaptador de entrada para esses mesmos
casos de uso, não um intermediário HTTP obrigatório entre ETL e modelagem.
O transporte HTTP/JSON entre Arcade e backend continua no plano vigente; uma
entrada local no mesmo processo pode ser estudada separadamente. O
[ADR 0004](adr/0004-backend-fastapi-e-contratos-python.md) resolve a escolha do
framework sem condicionar as regras de modelagem a servidor.

| Contrato/conceito a discutir | Campos ou invariantes úteis | O que não fixar ainda |
| --- | --- | --- |
| Participante e estado da corrida | IDs estáveis; tempo e distância com unidade; voltas concluídas; estado ativo/retirado; referência de ritmo positiva. | Modelo físico do carro, traços comportamentais reais e regras detalhadas de abandono/classificação oficial. |
| Parâmetros do modelo | Versão, unidade, domínio de validade, origem de cada valor (observado, estimado ou assumido) e método/amostra quando estimado. | Coeficientes arbitrários apresentados como medidos; parâmetros que ainda não afetam nenhuma regra. |
| Pista e trechos | Circuito e versão da geometria; intervalos de distância ordenados, sem lacunas ou sobreposição; soma dos comprimentos igual ao comprimento adotado. | Quantidade de trechos, limiares curva/reta, suavização e correspondência com setores oficiais. |
| Geometria versus condição da pista | Forma estática separada de condição mutável (por exemplo, molhada). XY normalizado para apresentação; metros para progresso longitudinal. | Atrito como atributo medido da polilinha: aderência depende também do modelo de superfície, pneu e condição, ausentes dos dados atuais. |
| Pit lane | Mesmo sistema XY da pista, caminho de entrada/saída e um ponto de serviço representativo. | Garagem por equipe, velocidade regulamentar, comprimento físico do caminho e tempos de serviço inferidos de `path_fraction`. |
| Snapshot e entrada HTTP | IDs, unidades, versão do contrato/modelo/fonte, ordenação dos pontos, ausências, erros e limites; configuração distinta do resultado. | Rotas e formato definitivo do colega, frequência de consulta e transferência integral de todos os dados a cada quadro. |

Para obter orientação de curva/reta é possível estudar mudanças de direção
entre pontos, mas a polilinha é reamostrada e tem ruído. A classificação seria
uma derivação aproximada e versionada, não um campo observado. A distância
acumulada não converte automaticamente qualquer distância XY ou raio calculado
em metros; o sistema XY é sem unidade. Nem curva/reta nem latitude/longitude
permitem deduzir atrito real. A perda registrada em `PitStop.duration_ms` também
não deve ser tomada automaticamente como tempo de carro parado ou penalidade
total de passagem pelos boxes.

## 6. Decisões pendentes e evidência necessária

| Decisão a ser tomada | Por que não fechar neste levantamento | Quem precisa participar / evidência para destravar |
| --- | --- | --- |
| Transporte entre Arcade e backend | FastAPI já foi escolhido no ADR 0004; contratos Python internos bastam para o perfilamento. Retirar HTTP também da fronteira do frontend é uma decisão distinta. | Grupo e responsável pelo empacotamento/backend: decidir processos, distribuição e adaptação do trabalho em andamento. Não bloqueia o núcleo. |
| Contrato Python de histórico e responsabilidade pelo perfilamento | Há repositories, mas falta o contrato entre corridas; a branch #43 já calcula parâmetros com SQL direto. | Responsáveis por #43/#66/#67: compor observações canônicas, definir ausências/unidades e compartilhar o cálculo. Não pressupõe novos endpoints. |
| Cenário oficial e compatibilidade de temporadas | São Paulo/2024 é exemplo técnico nos MDs; ter 24 geometrias reduzidas de 2025 não amplia automaticamente o MVP nem comprova que o traçado vale para qualquer ano. | Grupo: circuito/corrida escolhidos, tratamento da divergência de ano e conjunto de demonstração. |
| Volta, setor ou evento como passo inicial | O plano permite setores, mas o contrato atual só tem tempos por volta e geometria sem tempos de setor. | Modelagem e motor: objetivo da primeira demonstração. Avaliar avanço por volta/evento; qualquer repartição de tempo em trechos seria uma hipótese adicional. |
| Como separar efeitos de piloto e carro | Um tempo de volta observado não identifica isoladamente potência, aerodinâmica ou habilidade. Peso/altura/potência nem estão disponíveis. | Grupo: decidir se basta ritmo conjunto para o MVP. Separação posterior exige modelo identificável e dados comparativos adequados, não apenas uma fórmula com várias parcelas. |
| Quais efeitos físicos entram no MVP | Novas issues citam sofisticação; o plano adia combustível e interação física e não exige alta fidelidade. | Grupo e responsáveis por #60–#63: critérios observáveis e orçamento de complexidade; ainda não adotar física por trecho ou ultrapassagem comportamental como obrigação. |
| Origem dos parâmetros de pneus e clima | Falta dado observado; as duas outras bases sugeridas pelo professor não foram ingeridas. O ADR 0003 permite FastF1 somente para geometria. | Grupo: escolher entre hipóteses educacionais explicitadas ou expansão formal de dados, com fonte, versão, data, licença e transformações antes da ingestão. |
| Segmentação, atrito, aderência e limites de pit lane | Geometria reduzida não fornece superfície, grip ou garagem individual. Não há critério de qualidade para segmentação. | Modelagem de pista, pneus e motor: regra que consumirá os trechos, escala, parâmetros e casos de validação. |
| Filtros, métricas e critérios de calibração | Não há anotações suficientes de todas as condições das voltas; a fixture pequena é de integração, não amostra estatística. | Responsável pelos dados e modelos: corridas separadas, registros excluídos/desconhecidos e métrica de validação. Não calibrar e validar na mesma corrida. |
| Perfis de pilotos e sua reação ao clima | A issue descreve comportamento desejado, mas não define regras nem há evidência para atribuí-lo a pilotos reais. | Grupo: decidir entre personas assumidas e perfis estimados; definir quais ações podem mudar, suas faixas e como validar o efeito. |

Nenhuma dessas linhas deve ser convertida em decisão aceita apenas porque
consta deste documento. Divergências de arquitetura ou escopo devem ser
resolvidas antes de implementar os componentes afetados; não impedem a análise
conceitual e o refinamento das issues que não dependem delas.

## 7. Critérios sugeridos para as próximas fatias

Antes de abrir código de cada modelo, registrar na issue: consumidor, entrada
canônica, saída observável, unidades, invariantes, origem dos parâmetros e
limitações. Manter descrições e responsáveis no GitHub, usando
[docs/backlog.md](backlog.md) apenas como espelho gerado.

Exemplos de critérios a aprovar, sem testes implementados nesta etapa:

- Participante: manter vínculo piloto/equipe/corrida; rejeitar ritmo não
  positivo; não inferir característica ausente ou substituir desconhecido por zero.
- Pista: aceitar a representação canônica; tratar geometria ausente com erro
  claro; manter alinhamento de pista/pit lane; preservar fechamento e ordem;
  validar cobertura dos trechos, caso a segmentação seja aprovada.
- Corrida determinística: concluir o total previsto, parar após término,
  produzir classificação consistente e reproduzir o mesmo resultado com as
  mesmas entradas; tempo simulado não depende de FPS ou latência de consulta.
- Pneus/clima: testar transições isoladas antes de interações; tornar claro
  quais valores são hipóteses; não importar `WeatherSchedule` da camada de
  apresentação para o domínio como dependência de produção.
- Integração: provar que os consumidores não precisam ler CSV, inspecionar
  esquema SQLite ou reconstruir joins; validar versão e unidade no contrato.
  A geometria e os resultados devem ser compatíveis com a corrida selecionada.

## 8. Resultado e limites desta revisão

**Há dados suficientes para especificar e, após aprovação do recorte, construir
um núcleo determinístico simples. Não há dados suficientes para calibrar os
modelos físicos e comportamentais completos descritos nas novas issues.**
O contrato Python resolve o acesso, mas não acrescenta campos ausentes. A
[pesquisa de perfilamento](perfilamento-pilotos.md) distingue dados disponíveis
no Trotman, contexto que FastF1 pode fornecer e atributos ainda não estimáveis.
Não há exigência de inventar dados de produção.

Foram conferidos issues/descrições/comentários e hierarquia do backlog, MDs e
ADRs, código das portas/adaptadores e protótipos, cabeçalhos do ZIP Trotman e
esquema do SQLite local em modo somente leitura. Não foram executados motor,
backend, container ou testes gráficos; não há afirmação de validação física
ou operacional desses componentes. As verificações desta entrega são de
documentação, links locais e diff. Código, fontes e dados foram preservados.
