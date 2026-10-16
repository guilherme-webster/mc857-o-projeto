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
drenagem e a evaporação agem também durante a chuva. Como a unidade temporal
é uma volta, e não minutos, pistas e voltas de duração diferente ainda não
têm secagem comparável. Não há sorteio; os mesmos dados dão a mesma saída.

Os valores padrão de `ASSUMED_WEATHER_PARAMETERS` são hipóteses ilustrativas,
versionadas como `assumed-weather-per-lap-v1` e **não calibradas**. O FastF1
fornece `rainfall` booleano: dele não se pode inferir chuva leve/intensa nem
aderência. O modelo não lê fatos históricos, não estima parâmetros a partir
deles e não determina composto de pneu, atrito ou penalidade de tempo. Essas
integrações ficam para outra etapa, com mapeamento explícito dos rótulos da UI
e parâmetros próprios para os efeitos nos carros.

Verificação isolada: `uv run python -m unittest tests.test_weather`.

## Integração atual

Atualizado em 2026-10-16.

- **Interface:** a tela de configuração da etapa pinta o clima por volta com os
  rótulos "Seco", "Chuva leve" e "Chuva intensa".
  `frontend/arcade/race_launcher.py` os envia como faixas contíguas `dry`,
  `light_rain` e `heavy_rain`. A regra de torneio "Seco em todas" força pista
  seca em todas as etapas. A tela da corrida mostra a condição da volta do líder.
- **API:** `POST /catalog/grid/run` recebe `setup.weather` (faixas
  `from_lap`/`to_lap`/`rain`). Voltas não cobertas são secas
  (`expand_segments`), e as faixas voltam ecoadas em `setup.weather`.
- **Tempo de volta:** `run_detailed_grid_simulation` roda `simulate_weather` e
  entrega ao motor a água ao fim de cada volta. O motor soma
  `weather_penalty_ms`, que vai até 40% do tempo de referência com pista
  saturada (`ASSUMED_WEATHER_EFFECT`, `assumed-weather-effect-v1`, não
  calibrado, proporcional à água). A parcela aparece como `weather_ms` na
  decomposição do tempo de volta.
- **Fora da integração:** disputas, incidentes, controle de prova e a escolha de
  pneus não consideram o clima. Não há compostos intermediário ou de chuva.
