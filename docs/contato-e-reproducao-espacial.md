# Contato e reprodução espacial — diagnóstico das issues #174 e #175

A taxa de contato `spatial-contact-assumed-v1` é uma **hipótese**, não uma
frequência medida ou calibrada. A base de 0,15 s⁻¹ vale enquanto dois carros
roçam lado a lado; é multiplicada pela média das agressividades e gera a
probabilidade `1 - exp(-taxa * dt)` por passo de exposição. O contato pode
causar abandono. A zona de largada e as neutralizações já previstas pelo motor
continuam suprimindo o sorteio; não se zerou artificialmente a taxa. Alterar o
passo também altera trajetórias e exposições, de modo que essa fórmula não
assegura resultados idênticos para passos diferentes.

A ordem de avanço agora considera primeiro o carro mais à frente. Na reprodução,
a Hermite limita as tangentes quando a distância e as velocidades das pontas
são incompatíveis, impedindo recuo entre amostras de distância não decrescente.
Os recursos e o percurso de boxes continuam usando seus contratos existentes.
A duração das amostras é 200 ms no passo padrão; transições são preservadas e,
com outros passos, amostram-se os retratos disponíveis, sem inventar pontos.

## Avaliação exploratória

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
