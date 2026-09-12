# Perfilamento de pilotos: dados, limites e plano de implementação

**Status: proposta, sem modelo implementado ou nova ingestão.** Pesquisa em
11/09/2026 para [#61](https://github.com/guilherme-webster/mc857-o-projeto/issues/61),
[#66](https://github.com/guilherme-webster/mc857-o-projeto/issues/66) e
[#67](https://github.com/guilherme-webster/mc857-o-projeto/issues/67).
Complementa o [planejamento geral](planejamento-modelagem.md). A escolha de
FastAPI foi confirmada e registrada no
[ADR 0004](adr/0004-backend-fastapi-e-contratos-python.md); a ampliação de fontes
e os métodos estatísticos abaixo continuam propostas.

## 1. Por onde começar e o que significa um perfil

Recomendo começar por **ritmo e consistência contextualizados**, separando
cadastro de piloto, estimativas de desempenho e estado mutável na simulação.
Isso oferece parâmetros observáveis para a corrida sem exigir peso, altura,
telemetria de alta frequência ou um modelo psicológico.

O primeiro perfil deve dizer em quais corridas e condições o desempenho foi
observado. Não deve prometer uma medida universal de habilidade independente
do carro. Comparar companheiros ajuda a controlar parte do contexto, mas não
elimina diferenças de configuração, estratégia, tráfego e execução da equipe.

Não é necessário inventar dados de produção. Há três conceitos distintos:

- **Geometria reduzida:** os CSVs da #51 derivam de observações reais do FastF1.
  O termo histórico "mock" não significa coordenadas fabricadas. Reamostragem,
  normalização e o ponto de serviço representativo são aproximações conhecidas.
- **Amostras e dublês de teste:** conjuntos pequenos e controlados permitem
  verificar ausência de dados, unidades e reprodução sem depender de rede.
  Podem ser sintéticos; nunca servem para calibrar um piloto real.
- **Persona configurada:** um piloto fictício pode ter uma política de risco
  escolhida pelo usuário. Deve ser separado de um perfil estimado de piloto real.

FastF1 pode fornecer observações úteis para o perfilamento. O problema atual é
principalmente a ausência de ingestão desse contexto no nosso contrato, e não
uma insuficiência geral da fonte. Ainda assim, observações não trazem prontas
as regras e os coeficientes de um simulador.

## 2. Dados encontrados e fontes candidatas

### Trotman já disponível: aproveitar antes de adicionar outra fonte

Auditoria somente de leitura do ZIP local `formula-1-race-data-v128.zip`:

| Recorte de 2024 | Registros | Cobertura de corridas |
| --- | ---: | ---: |
| Resultados | 479 | 24 |
| Voltas | 26.574 | 24 |
| Classificação (`qualifying.csv`) | 479 | 24 |
| Paradas | 825 | 24 |

As quatro tabelas têm 24 pilotos distintos nesse recorte, incluindo substitutos.
Há 475 tempos Q1 preenchidos, 357 Q2 e 234 Q3. Participantes eliminados ou sem
tempo não devem receber zero; Q1, Q2 e Q3 não são amostras intercambiáveis.
Essas contagens não comprovam qualidade para calibração e não são a quantidade
de registros já disponível em cada SQLite do projeto.

O adapter atual importa oito dos 14 CSVs para uma corrida por execução.
`qualifying.csv` está na fonte, mas não no agregado canônico. `driverRef`, data
de nascimento e nacionalidade também existem na fonte; peso e altura não.
Preservar referências de origem será útil para cruzar identidades; dados
biográficos não precisam virar parâmetros de desempenho sem uma regra útil.

### FastF1: candidato principal para enriquecimento

Foi inspecionado o código oficial da versão 3.8.3, já usada para a geometria.
A interface de voltas inclui setores, stint, composto, idade do pneu, entradas
e saídas dos boxes, situação da pista e indicadores de qualidade. O clima
inclui temperatura, precipitação booleana, umidade e vento. `Deleted` pode ser
desconhecido; `FastF1Generated` identifica voltas geradas. Esses indicadores
não provam ausência de tráfego. Ver
[contratos oficiais de Session/Laps](https://github.com/theOehrly/Fast-F1/blob/v3.8.3/fastf1/core.py).

Para análises futuras de condução, a fonte também oferece velocidade,
acelerador, freio booleano e DRS. Isso não fornece pressão de frenagem medida.
O guia oficial alerta para frequência limitada, ruído e erros de interpolação;
recomenda calcular sobre as séries originais quando possível. Portanto, não
derivar precisão de frenagem por curva apenas dos pontos reduzidos da #51.
[Guia de precisão do FastF1](https://github.com/theOehrly/Fast-F1/blob/v3.8.3/docs/data_reference/howto_accurate_calculations.rst).

Nesta revisão, a documentação foi consultada pelo repositório oficial porque
`docs.fastf1.dev` retornou 403. Não foram instaladas dependências nem baixadas
sessões completas. Campos documentados não garantem cobertura completa da
amostra desejada; essa auditoria é a primeira fatia proposta abaixo.

### Alternativas verificadas e bases sugeridas pelo professor

**OpenF1:** a documentação anuncia histórico desde 2023, acessível sem
autenticação, com voltas, stints e clima. Uma consulta limitada retornou uma
volta com tempos dos três setores:
[sessão 9636, piloto 1, volta 2](https://api.openf1.org/v1/laps?session_key=9636&driver_number=1&lap_number=2).
A resposta foi inspecionada em memória, sem incorporação ao ETL. Isso comprova
acesso àquela amostra, não cobertura de toda a temporada.

Há restrições relevantes: chuva é ocorrência, não intensidade; o registro de
ultrapassagens também pode incluir mudanças por pit stop ou penalidade e pode
estar incompleto. Não é um indicador pronto de agressividade. O tempo de
serviço `stop_duration` só está disponível a partir do GP dos EUA de 2024.
[Documentação do OpenF1](https://openf1.org/docs/).

**Jolpica:** alternativa para atualizar resultados e classificação, sem
necessidade imediata de duplicar o ZIP que já temos. Seus termos atuais
identificam CC BY-NC-SA 4.0 para os dados; não presumir a mesma licença CC0 do
snapshot Trotman. Avaliar proveniência também quando uma ferramenta acessa
Jolpica indiretamente. [Termos do Jolpica](https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md).

As outras duas bases indicadas pelo professor estão referenciadas no plano:
[AlexJR — Race Data and Telemetry](https://www.kaggle.com/datasets/alexjr2001/formula-1-dataset-race-data-and-telemetry)
e [Vansh Batra — Tyre Strategy Engine](https://www.kaggle.com/datasets/vanshbatra26/f1-tyre-strategy-engine-datasets).
As páginas consultadas não expuseram conteúdo suficiente para validar agora
arquivos, versão, cobertura e licença. Continuam candidatas, não dependências
aprovadas. Se reproduzirem observações já disponíveis via FastF1, comparar
completude e proveniência antes de acrescentar outra transformação intermediária.

**Recomendação:** Trotman para identidade/histórico e avaliação inicial;
FastF1 para contexto de volta. OpenF1 é alternativa a comparar se houver
lacunas concretas, não uma terceira fonte obrigatória. O
[ADR 0003](adr/0003-geometria-mockada-derivada-do-fastf1.md) só autoriza geometria;
adotar novos usos exige registrar escopo, retenção, versão, data, condições da
fonte e transformações. A licença do software não substitui a dos dados.

## 3. Métricas propostas e dados necessários

As fórmulas desta seção são sugestões de modelagem, não conclusões das fontes
consultadas ou coeficientes já calibrados. Evitar inicialmente notas de 0–100.

| Perfil/medida | Dados mínimos | Proposta e limite |
| --- | --- | --- |
| Ritmo de corrida | Tempos, piloto/equipe, evento e voltas elegíveis; contexto de pneu/pista quando disponível. | Estimar referência robusta por contexto, com desvio em ms ou percentual. Com Trotman isolado, declarar contexto incompleto; não chamar de ritmo de pista livre. |
| Consistência | Várias voltas comparáveis, identificação de stint e mudanças de condição. | Estudar dispersão robusta dos resíduos após explicar o contexto. O desvio padrão bruto mistura desgaste, tráfego e chuva com inconsistência. |
| Desempenho em classificação | Q1/Q2/Q3 e companheiro no mesmo segmento da sessão. | Comparar tempos percentualmente dentro do mesmo evento/segmento. Evolução da pista e condições ainda podem distorcer a comparação. |
| Desempenho em chuva | Voltas, clima temporal, composto, pista e cobertura de eventos secos/molhados. | Estimar efeito contextual apenas com amostra suficiente; caso contrário retornar indisponível. Não mapear precipitação booleana para chuva leve/intensa ou neblina. |
| Gestão de pneus | Stints, composto, idade, ritmo e contexto de corrida. | Estimar tendência dentro de stints comparáveis. Não usar a inclinação de todas as voltas da corrida como desgaste atribuível ao piloto. Depende também de #63. |
| Ultrapassagem/defesa | Oportunidades, proximidade, posições sincronizadas, pista/boxes/penalidades. | Adiar: contar posições ganhas não fornece tentativas, risco aceito ou taxa de sucesso. Personas podem existir como hipótese separada. |

Peso e altura não são pré-requisitos desse recorte. Se #61 mantiver esses
atributos, definir primeiro qual regra os consome e obter fonte datada por
piloto, admitindo ausência. Não inferir valores nem transformar características
físicas em habilidade. Potência, carga aerodinâmica, combustível e aderência
também não são identificados isoladamente a partir de um tempo de volta.

## 4. O que ETL e backend precisam entregar

### ETL e persistência: preservar fatos e sua proveniência

1. **Auditar um recorte pequeno:** corrida e classificação de um evento de
   2024, incluindo os companheiros. Depois ampliar para eventos distintos,
   reservando eventos inteiros para validação. Relatar campos ausentes,
   duplicatas, cobertura por piloto/stint e exclusões por motivo.
2. **Mapear identidades:** ligar temporada/etapa/sessão e piloto aos IDs
   canônicos. Conservar `driverRef` e referências de origem; validar a relação
   com identificadores externos. Número de carro ou nome isolado não é chave
   global. Mudanças de equipe devem ser vinculadas ao evento.
3. **Aproveitar Trotman:** adicionar classificação apenas quando o caso de uso
   correspondente entrar. Viabilizar consultas de histórico entre corridas;
   o banco atual por corrida não oferece isso automaticamente.
4. **Após a decisão de fonte, enriquecer voltas:** acrescentar campos canônicos
   opcionais de contexto e qualidade. Manter tempos em ms, temperaturas com
   unidade explícita, ordem e relógio da sessão definidos. Não substituir
   desconhecido por `False`, zero ou um composto padrão. Conferir divergências
   entre fontes antes de escolher precedência para um tempo observado.
5. **Associar séries por tempo:** documentar a janela e a tolerância usadas
   para ligar clima e situação da pista à volta. Marcar observação antiga ou
   ausente. A modelagem decide elegibilidade; o ETL preserva fatos e marcações,
   sem descartar silenciosamente voltas que outro consumidor pode precisar.
6. **Persistir com reprodução:** manifestos, checksums, versão do adaptador e
   relatório de qualidade. Execução offline idempotente, retomada/cache conforme
   a política aprovada e reprocessamento sem apagar histórico ou geometria.

DataFrames são ferramentas de aquisição/análise nas bordas. O domínio recebe
objetos canônicos; não importa FastF1/Pandas nem abre CSVs. Não é necessário
reescrever o ETL: cada necessidade acima deve ampliar uma fronteira existente
ou justificar concretamente um novo adaptador.

### Backend/aplicação: consumir Python, compartilhar o mesmo cálculo

`RaceDataRepository.get_race()` já é uma porta Python. Para o perfil entre
eventos, estudar uma consulta de histórico ou uma composição dos repositories
existentes; evitar uma nova interface para cada métrica. O caso de uso proposto
coordena a leitura e entrega observações canônicas a funções de estimação puras.

O resultado deve identificar piloto, equipe/contexto, recorte de temporadas,
versão do método e fonte, unidades, estimativas disponíveis, número de voltas
e eventos e motivos de exclusão. Incerteza e falta de amostra fazem parte do
contrato. Persistir esse perfil somente se o consumidor precisar reutilizá-lo;
regras de cenário e estado da corrida permanecem separados.

FastAPI pode expor esse mesmo caso de uso. Modelagem e ETL não precisam chamar
HTTP local nem consumir dumps de tabelas. Se o grupo escolher executar Arcade
e núcleo no mesmo processo, um adaptador local poderá consumir os mesmos casos
de uso; o transporte entre frontend/backend continua uma decisão separada,
conforme o ADR 0004. Não condicionar o perfilamento a novos endpoints.

### Trabalho encontrado na branch da issue #43

Em `origin/43-criar-endpoints`, commit `0f6255d`, foram lidos
`backend/app/engine/loader.py`, `models.py` e `routers/simulation.py`.
Há rotas de pilotos e corrida e uma estrutura `DriverParameters`, ainda fora
da `develop` auditada. O loader usa SQL direto e já calcula:

- referência como mediana do quarto mais rápido das voltas;
- tendência linear não negativa de todos os tempos como degradação;
- média das durações de pit stop como perda de parada.

São estimativas de protótipo, não perfis validados. Sem separar stints e
condições, a tendência não identifica desgaste; ausência de observações não
prova efeito zero. A duração registrada de parada tampouco prova a perda total
relativa a permanecer na pista. Coordenar #66/#67 com #43 para mover/reutilizar
o cálculo aprovado na aplicação e deixar SQL no adaptador. A branch não foi
mesclada nem executada nesta revisão; esses achados não descrevem a `develop`.

## 5. Sequência de implementação e critérios de aceite propostos

| Fatia | Entrega | Verificação útil |
| --- | --- | --- |
| 1 — contrato e amostra (#66) | Recorte, identidades, exemplos canônicos e relatório de disponibilidade; começar com dados já autorizados. | Nenhuma colisão silenciosa de IDs; nulos e unidades explícitos; execução sem HTTP. |
| 2 — enriquecimento do ETL | Após ADR de fonte, contexto de um evento; depois histórico de múltiplos eventos. | Teste de round-trip e reingestão; diferenças entre fontes relatadas; metadados preservados. |
| 3 — ritmo e consistência (#67) | Estimadores puros e resultado com cobertura; reutilização acordada com #43. | Valores conhecidos em pequena amostra controlada, entradas insuficientes e reprodução; não duplicar a implementação em testes. |
| 4 — validação fora da amostra | Comparação com uma referência simples em corridas reservadas. | Erro em ms/percentual, estabilidade e cobertura; nenhum evento de validação usado para ajustar limiares. |
| 5 — aplicação e simulação (#70/#71) | Perfil versionado convertido explicitamente em parâmetros do participante. | Corrida determinística; não contar novamente efeito de carro/pneu já incluído na referência. |
| 6 — extensões | Classificação, chuva, gestão de pneus e, por último, decisões de ultrapassagem. | Cada efeito exige amostra, consumidor e critério próprio antes de ampliar o modelo. |

Não escolher agora limiar de amostra mínima, coeficientes de chuva ou escala
de habilidade. Primeiro avaliar cobertura e sensibilidade. Para incerteza,
considerar reamostragem por evento/stint, não tratar todas as voltas correlatas
como observações independentes. Reservar corridas futuras em relação ao recorte
de calibração quando a alegação for capacidade de previsão.

Gráficos fazem parte da futura análise: cobertura/ausências por piloto e
evento, tempos por volta com boxes e mudanças de condição, resíduos por stint
e erro nas corridas reservadas. Gerá-los com a amostra auditada e unidades
explícitas; nesta entrega não há gráficos nem calibração executada.

## 6. Branches, decisões pendentes e continuidade

- `40-planejamento-modelagem`: documentação desta revisão, criada a partir
  de `develop` em `3ea8a0b`, no worktree `../mc857-etl-geometria`.
- `67-modelagem-pilotos`: preparação para implementação, mesma base, no
  worktree `../mc857-modelagem-pilotos`; sem código de modelo nesta etapa.

Nenhum commit foi criado nesta revisão. A documentação está na branch #40,
fora da `develop`. Antes de implementar na #67, integrar os commits de
documentação revisados e combinar a reutilização com #43; a criação da branch
não altera responsáveis ou estado das issues.

Decisões ainda necessárias: recorte/cenário oficial; expansão de FastF1 além
da geometria e política de dados; métodos e amostra mínima após auditoria;
responsabilidade pelo cálculo compartilhado com #43; distinção entre perfil
observacional e persona. A opção de transporte Arcade/backend não bloqueia
funções puras nem o contrato Python do perfilamento.
