# Modelo climático

A issue #69 introduz uma evolução determinística da umidade relativa do ar e
da água superficial por volta em `src/f1_simulator/domain/weather.py`. A seção
[Integração atual](#integração-atual) descreve como ela chega à interface, à
API e ao tempo de volta; o restante deste texto descreve o modelo em si.
Os três valores de entrada (`dry`, `light_rain`, `heavy_rain`) são **intensidades
de chuva prescritas**, não estados da pista. Portanto, uma volta sem chuva
pode começar e terminar com pista molhada.

O estado inicial é anterior à volta 1. Cada saída contém o estado **ao fim**
da volta correspondente. Para cada volta, o modelo aproxima a umidade de um
alvo da intensidade de chuva e depois atualiza a água:

```text
umidade_nova = umidade_atual + resposta * (umidade_alvo - umidade_atual)
evaporacao = evaporacao_por_volta * (1 - umidade_nova / 100)
agua_nova = limitar(agua_atual + aporte_chuva - drenagem - evaporacao, 0, 1)
```

A umidade usa porcentagem de 0 a 100. A água usa um **índice adimensional** de
0 (seca) a 1 (saturada), não milímetros nem um coeficiente de atrito. A
drenagem e a evaporação agem também durante a chuva. A parametrização original
usa uma volta de referência de 1,5 minuto; o integrador da corrida converte os
fluxos para o tempo simulado transcorrido. Não há sorteio; os mesmos dados dão
a mesma saída.

Os valores padrão de `ASSUMED_WEATHER_PARAMETERS` são hipóteses ilustrativas,
versionadas como `assumed-weather-per-lap-v1` e **não calibradas**. O FastF1
fornece `rainfall` booleano: dele não se pode inferir chuva leve/intensa nem
aderência. O modelo não lê fatos históricos, não estima parâmetros a partir
deles e não determina composto de pneu, atrito ou penalidade de tempo. Essas
integrações ficam para outra etapa, com mapeamento explícito dos rótulos da UI
e parâmetros próprios para os efeitos nos carros.

Verificação isolada: `uv run python -m unittest tests.test_weather`.

## Integração atual

Atualizado em 2026-11-06 (issue #119, ADR 0015).

- **Interface:** a tela de configuração da etapa pinta o clima por volta com os
  rótulos "Seco", "Chuva leve" e "Chuva intensa".
  `frontend/arcade/race_launcher.py` os envia como faixas contíguas `dry`,
  `light_rain` e `heavy_rain`. A regra de torneio "Seco em todas" força pista
  seca em todas as etapas. A tela da corrida mostra a condição da volta do líder.
- **API:** `POST /catalog/grid/run` recebe `setup.weather` (faixas
  `from_lap`/`to_lap`/`rain`). Voltas não cobertas são secas
  (`expand_segments`), e as faixas voltam ecoadas em `setup.weather`. O
  resultado traz `track_conditions`, um registro por volta com chuva, umidade,
  água, temperatura do asfalto, borracha e fator de aderência.
- **Tempo:** os fluxos de água valem por "volta de referência" de 1,5 min
  (`WeatherParameters.reference_lap_minutes`); cada volta real acumula e seca
  na proporção do tempo realmente simulado em cada passo do motor 2D.
  Sem duração informada, `simulate_weather` mantém o comportamento original por
  volta.
- **Estado da pista** (`domain/track_condition.py`): a cada passo, a
  temperatura do asfalto acelera a evaporação; a água evolui; a temperatura se
  aproxima de um alvo seco assumido por circuito (35 °C para circuitos sem
  valor específico) ou até 12 °C abaixo (saturada). A borracha cresce com
  distância efetivamente percorrida na pista e a água a lava ao longo do tempo;
  boxes e carros parados não depositam borracha. Tudo vira um **fator de
  aderência** =
  água × borracha. A água descreve a aderência com o pneu adequado: 0,81 com
  água 0,3 (intermediário) e 0,69 saturada (pneu de chuva). Parâmetros
  `assumed-track-condition-v2` e `assumed-circuit-track-temperature-v1`.
  Os seis valores de temperatura específicos são exemplos assumidos, não
  medições; circuitos restantes usam a reserva global. Uma volta equivalente
  de 20 carros deposita 8% da borracha faltante.
- **Tempo de volta:** o fator multiplica o `mu` do carro no motor físico; cada
  carro paga o tempo que a própria física perde naquela pista (pista de curvas
  lentas perde mais). Entra no `speed_scale` do 2D e na decomposição de
  velocidade. O motor detalhado foi arquivado. O efeito linear antigo (+40% com
  pista
  saturada, `weather_penalty_ms`) foi removido.
- **Pneus e corrida (#120):** intermediário e chuva com aderência por água,
  troca por clima com viés por piloto, regra de dois compostos suspensa,
  largada com pneu de chuva se a volta 1 estiver molhada, superaquecimento em
  pista secando e mais acidentes e contatos com água e pneu errado
  (`domain/wet_tyres.py`; valores em `docs/modelagem-heuristica.md`, seção 6).
  A tela da corrida mostra a água e a temperatura do asfalto da volta do líder.
- **Fora da integração:** a temperatura não altera a aderência nem o desgaste;
  o controle de prova não reage diretamente à chuva (só aos incidentes); o
  contato espacial do 2D não depende da água.

A previsão baseada na volta de referência é usada somente para escolher o
composto inicial; durante a corrida a estratégia usa água atual. Os retratos
correspondem ao fim das voltas alcançadas pelo líder, com resolução do passo
do motor; se todos abandonarem antes de terminar, não há retratos fictícios.
