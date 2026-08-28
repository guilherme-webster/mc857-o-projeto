# 0001 - Frontend desktop com Arcade

- Status: aceita
- Data: 2026-08-28
- Responsaveis: grupo do projeto

## Contexto

O MVP precisa oferecer as etapas de configuracao, acompanhamento da corrida em
uma pista 2D e consulta do resultado. O motor e o backend usam Python, e a
equipe quer iniciar o desenvolvimento assincrono com uma tecnologia de
visualizacao definida.

O projeto [IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay)
demonstra que a biblioteca Arcade atende bem a uma visualizacao de Formula 1
com pista renderizada, marcadores dos pilotos, leaderboard, informacoes de volta
e controles interativos. O repositorio e uma referencia de experiencia e de
viabilidade, nao a arquitetura nem a fonte das regras deste simulador.

## Alternativas consideradas

- **Arcade:** mantem a interface em Python e oferece janela, ciclo de eventos,
  desenho 2D, entrada por mouse/teclado e separacao de telas com `arcade.View`.
  Exige ambiente grafico e suporte a OpenGL 3.3 ou superior.
- **Streamlit com Plotly:** favorece paineis web rapidos, mas oferece menos
  controle sobre uma animacao 2D interativa e reintroduziria a direcao antiga
  que o grupo decidiu substituir.
- **Frontend web em JavaScript/TypeScript:** oferece amplo ecossistema de
  visualizacao e distribuicao pelo navegador, ao custo de uma segunda pilha de
  linguagem e mais trabalho de integracao para o MVP.

## Decisao

O frontend do MVP sera uma aplicacao desktop em Python feita com Arcade. Uma
unica `arcade.Window` alternara entre tres `arcade.View`: Parametros, Corrida e
Resultados. A tela Corrida desenhara a pista, os carros e o leaderboard e
oferecera, inicialmente, os comandos iniciar, pausar/continuar, ajustar a
velocidade de reproducao e reiniciar.

Django permanece como adaptador de backend. O cliente Arcade enviara comandos e
consultara configuracoes, `RaceSnapshot` e resultado por uma API HTTP/JSON. A
forma exata dos endpoints sera definida por contrato antes da integracao. O
cliente nao importa modelos Django nem regras do motor, e Django nao importa
tipos da interface grafica.

O ciclo `on_update` do Arcade controla apenas consulta e apresentacao. O tempo
simulado, classificacao, eventos e termino da corrida pertencem ao backend e nao
podem depender da taxa de quadros, da GPU ou da latencia da interface.

## Consequencias

- A equipe compartilha a mesma linguagem entre motor, backend e interface, mas
  preserva limites de processo e de responsabilidade.
- O fluxo de tres telas sera implementado com `arcade.View`, evitando varias
  janelas.
- O prototipo inicial deve validar Arcade e OpenGL 3.3 nos ambientes dos cinco
  integrantes e documentar uma forma de executar testes sem abrir janela.
- Testes de regras permanecem totalmente headless. A interface tera testes de
  apresentadores/controladores e um conjunto pequeno de testes graficos ou
  manuais, sem transformar captura de pixels na principal estrategia de teste.
- Atualizacoes da corrida comecarao por consultas HTTP periodicas. WebSocket ou
  streaming so serao avaliados com evidencia de que esse mecanismo e
  insuficiente.
- Ideias aproveitaveis do `f1-race-replay` incluem pista 2D, leaderboard,
  controles de reproducao e separacao entre preparo dos dados e renderizacao.
  Nao serao copiadas as regras de classificacao nem o acoplamento entre quadro
  visual e telemetria, pois este projeto gera estados de uma simulacao.
- O projeto de referencia usa licenca MIT. Nenhum codigo ou recurso visual sera
  copiado apenas por esta decisao; qualquer reutilizacao futura devera ser
  revisada, atribuida e acompanhada dos avisos de licenca aplicaveis.

Esta decisao nao resolve a escolha pendente entre MVC e camadas com portas e
adaptadores.
