# Contato e reprodução espacial — diagnóstico das issues #174 e #175

O modelo `spatial-contact-severity-assumed-v2` distingue proximidade, encontro
físico, dano e abandono. Seus limiares são **hipóteses**, sem calibração em
acidentes reais. A margem lateral de 30 cm orienta o planejamento; ela não
dispara um sorteio de abandono. O detector compara os retângulos orientados
no mesmo XY usado pela geometria. A proteção de movimento consulta subpassos
de até meia largura de carro para reduzir atravessamentos entre extremos.

Um episódio é avaliado uma vez, até que os corpos se separem por 0,5 m. Um
contato com aproximação normal relativa de até 2 m/s é toque leve e não causa
dano ou abandono, independentemente da velocidade absoluta na pista. Acima
disso o dano aumenta 0,025 por m/s excedente, dividido entre os envolvidos. O
risco de abandono cresce quadraticamente até a referência de 12 m/s e é
limitado a 0,8, modulado pela agressividade. Um carro com dano máximo pode
perder até 15% do teto de velocidade. Esses valores ficam em `ContactParameters`
e são publicados em `contact_model` e `assumptions`.

`contact_events_2d` registra tempo, par, episódio, aproximação, gravidade e dano
de cada carro. A tela mostra o toque e o dano no instante correspondente; o
painel de velocidade não antecipa o dano antes do contato. Só abandonos entram
como incidentes no controle de prova. A zona de largada e as neutralizações
mantêm as supressões de disputa existentes.

A proteção permite continuar longitudinalmente quando só a troca lateral está
bloqueada. Ela não usa um carro de trás para bloquear o avanço do líder. Os
dados originais e o eixo de distância calibrado foram preservados; o modelo
ainda depende da qualidade da polilinha, de estados iniciais válidos e do
passo de integração. A verificação é discreta, não uma prova matemática de
ausência de colisão para qualquer passo ou geometria.

A ordem de avanço agora considera primeiro o carro mais à frente. Na reprodução,
a Hermite limita as tangentes quando a distância e as velocidades das pontas
são incompatíveis, impedindo recuo entre amostras de distância não decrescente.
Os recursos e o percurso de boxes continuam usando seus contratos existentes.
A duração das amostras é 200 ms no passo padrão; transições são preservadas e,
com outros passos, amostram-se os retratos disponíveis, sem inventar pontos.

## Comparação reproduzível do modelo v2

Base de comparação: `4dfaa8e` (já contém o diagnóstico, antes do modelo v2).
Foram executados 36 cenários em cada versão: circuitos 6, 9 e 14, sementes
1–3, grids de 10/20 carros, cinco voltas e passos de 0,1/0,2 s. Os atributos
do diagnóstico são sintéticos, com ritmo em ordem inversa ao grid; não são
avaliações de pilotos reais. Clima, pneus, combustível, boxes e risco mecânico
estão desligados nessa matriz para isolar a disputa espacial.

| Medida agregada | Base | Modelo v2 |
| --- | ---: | ---: |
| Abandonos por contato | 13 | 2 |
| Pares de corpos sobrepostos por amostra | 15.738 | 633 |
| Inversões persistentes de posição | 4.084 | 4.345 |
| Amostras com frenagem acima de 50 m/s² | 4.417 | 5.725 |
| Carros ativos que não concluíram no limite do diagnóstico | 0 | 0 |
| Amostras de distância regressiva | 0 | 0 |
| Tempo total incluindo diagnóstico | 41,875 s | 72,790 s |

Os tempos foram medidos uma vez na mesma máquina em uso compartilhado. As
inversões persistentes não certificam ultrapassagens geometricamente válidas,
nem os pares por amostra são contagens de acidentes independentes. O limite
de frenagem é diagnóstico, não referência física calibrada. As frenagens
bruscas e o custo aumentaram e permanecem pendentes de melhoria. Uma tentativa
de envelope antecipado de frenagem foi descartada por bloquear um cenário;
essa conclusão é protegida por teste de regressão de conclusão da corrida.

Comando para repetir a matriz (JSON em stdout; não versionar o resultado):

```bash
PYTHONPATH=src uv run python scripts/analyze_spatial_contacts.py \
  --circuits circuit:6,circuit:9,circuit:14 --seeds 1,2,3 \
  --grids 10,20 --laps 5 --dts 0.1,0.2
```

## Histórico da avaliação exploratória v1

Em 13/11/2026 foram simuladas 9 corridas de 10 voltas, 20 carros e sementes
1, 2 e 3, com geometrias reduzidas versionadas do fixture (`circuit:1`, `6`
e `9`), partida parada, passo padrão 0,2 s e controle de prova padrão. Os 20
primeiros perfis fictícios existentes em `configs/drivers/perfis-ficticios.json`
foram usados na ordem do arquivo, com valores ausentes neutros, sem gerar ou
forçar diversidade adicional. Não foram ativados planos de pneus ou combustível
nem risco mecânico. Abandonos por contato, por semente:

| Circuito | 1 | 2 | 3 |
| --- | ---: | ---: | ---: |
| 1 | 4 | 3 | 4 |
| 6 | 2 | 2 | 3 |
| 9 | 5 | 2 | 3 |

Em outro diagnóstico de 5 voltas com os mesmos 20 carros **sem atributos**, as
sementes 1–3 produziram respectivamente 0/0/0 contatos no circuito 1, 1/0/1
no 6 e 0/0/0 no 9. Não se deve forçar diferença entre sementes: sem exposição
não existe sorteio de contato. Esses números são apenas casos de exercício,
não taxas reais nem validação estatística. Corridas completas, circuitos e
combinações adicionais, impacto no tempo/memória e inspeção visual continuam
necessários antes de julgar realismo e desempenho.

Para reproduzir o primeiro quadro a partir da raiz do repositório:

```bash
PYTHONPATH=src python - <<'PY'
from collections import Counter
from tests.race_invariants import real_geometry
from tests.geometry_support import attribute
from f1_simulator.adapters.driver_presets_json import load_driver_presets
from f1_simulator.domain.race_simulation_2d import simulate_2d_race
from f1_simulator.domain.random_source import SeededRandomSource

presets = list(load_driver_presets('configs/drivers/perfis-ficticios.json').values())[:20]
entries = []
for i, preset in enumerate(presets, 1):
    attrs = attribute(preset.driver_id, **preset.values)
    entries.append(dict(driver_id=preset.driver_id, name=preset.driver_name,
                        grid_position=i, attributes=attrs, aggression=attrs.aggression))
for circuit in ('circuit:1', 'circuit:6', 'circuit:9'):
    for seed in (1, 2, 3):
        race = simulate_2d_race(entries, real_geometry(circuit), total_laps=10,
                                rng=SeededRandomSource(seed))
        print(circuit, seed, dict(Counter(row['retirement_cause'] or 'FINISHED'
                                         for row in race['classification'])))
PY
```
