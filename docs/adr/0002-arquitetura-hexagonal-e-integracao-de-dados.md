# 0002 - Arquitetura hexagonal e integracao de dados

- Status: aceita
- Data: 2026-08-28
- Responsaveis: grupo do projeto

## Contexto

O simulador precisa manter as regras da corrida independentes do cliente Arcade,
do backend Django, da persistencia e dos formatos dos datasets. O MVP adotara
uma unica fonte de dados, mas a evolucao prevista inclui outras fontes com
esquemas, identificadores, granularidades e unidades diferentes.

O grupo tambem precisa separar duas responsabilidades na entrada de dados:
traduzir representacoes externas para um modelo canonico e construir objetos de
dominio validos a partir desse modelo. Misturar as duas atividades faria o
motor conhecer CSVs, tabelas do Kaggle ou detalhes de persistencia.

Foram avaliadas tres fontes iniciais. A base de estrategia de pneus e agregada
por stint e nao sustenta sozinha uma corrida volta a volta. A base de telemetria
e mais volumosa e nao declara uma licenca clara. A base historica de James
Trotman oferece tabelas relacionais de corridas, resultados, voltas e paradas,
com licenca CC0.

## Alternativas consideradas

- **MVC como arquitetura predominante:** oferece uma organizacao familiar para
  interfaces, mas nao torna explicitas as fronteiras entre o motor, Django,
  Arcade, persistencia e fontes de dados.
- **Arquitetura hexagonal:** mantem aplicacao e dominio no centro e representa
  interfaces, frameworks, persistencia e datasets como adaptadores conectados
  por portas criadas para fronteiras concretas.
- **Acesso direto aos dados pelo motor:** reduz o numero inicial de componentes,
  mas acopla regras da corrida a nomes de colunas, arquivos e bibliotecas de
  manipulacao tabular.
- **Somente Adapter ou somente Factory:** cada padrao resolve apenas parte do
  problema. O Adapter traduz formatos externos; a Factory garante a construcao
  consistente de objetos complexos.

## Decisao

Adotar **arquitetura hexagonal** para o sistema. O dominio e os casos de uso
ficam no centro; Django, Arcade, datasets, ETL e persistencia ficam nas bordas.
As dependencias apontam para o nucleo, e portas ou interfaces so devem ser
criadas quando houver uma fronteira externa ou variacao concreta.

Adotar uma abordagem combinada, ou hibrida, entre os padroes **Adapter** e
**Factory** para a integracao de dados:

1. o Adapter le a representacao externa e converte nomes, tipos, unidades e
   identificadores para dados canonicos;
2. a Factory recebe exclusivamente dados ja normalizados e constroi objetos de
   dominio validos, como `Race`, `Circuit`, participantes e
   `SimulationConfig`;
3. os casos de uso recebem esses objetos prontos e nao conhecem o formato da
   fonte original.

A Factory nao le CSV, nao consulta banco e nao escolhe adaptadores. O Adapter
nao executa regras da corrida nem usa objetos da interface grafica.

Selecionar como fonte inicial unica do MVP o dataset
[Formula 1 Race Data](https://www.kaggle.com/datasets/jtrotman/formula-1-race-data),
de James Trotman. A primeira ingestao usara a versao 128, publicada antes da
decisao, com licenca CC0: Public Domain. Data de download, checksum dos arquivos
e transformacoes aplicadas deverao ser registrados durante a implementacao do
ETL.

## Consequencias

- O motor permanece executavel e testavel sem Django, Arcade, Pandas, arquivos,
  rede, banco de dados, janela ou GPU.
- O primeiro adaptador de dataset conhece apenas a estrutura da base de
  Trotman. Uma segunda fonte exigira outro adaptador, sem condicionais da fonte
  espalhadas pelo dominio.
- O esquema canonico e o contrato entre Adapter e Factory precisam ser pequenos
  e orientados somente ao circuito e a corrida escolhidos para o MVP.
- Dados brutos permanecem imutaveis e fora do Git; apenas amostras pequenas,
  reproduziveis e com origem registrada podem ser versionadas para testes.
- A base escolhida cobre cadastros, resultados, voltas e pit stops, mas nao
  fornece compostos de pneus, clima, telemetria detalhada ou geometria completa
  da pista. Esses dados nao serao inventados nem obtidos silenciosamente de uma
  segunda fonte; qualquer expansao exige decisao explicita e registro de
  proveniencia e licenca.
- A arquitetura hexagonal nao autoriza uma interface para cada classe nem
  abstracoes antecipadas. Os componentes serao introduzidos por fatias verticais
  conforme os casos de uso do MVP.
- A organizacao do backlog continua orientada ao valor percebido pelo usuario.
  Trabalhos tecnicos habilitadores, como o ETL, podem permanecer vinculados ao
  epico funcional que viabilizam, sem exigir um epico tecnico separado.
