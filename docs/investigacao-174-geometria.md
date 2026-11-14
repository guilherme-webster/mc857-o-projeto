# Issue #174 — investigação da sobreposição residual

Base: `dd3d0cea0e7399a43d5d687bc4e9bcd85d3310e8`. A correção residual
foi implementada apenas uma redução experimental de sobreposição longitudinal.
Este registro não representa uma validação visual nem uma solução completa.

## Evidência e mecanismo

Com os 20 primeiros perfis de `configs/drivers/perfis-ficticios.json`, Mônaco
(`circuit:6`), uma volta, semente 2 e passo 0,2 s, o diagnóstico local
`/tmp/issue174_monaco_projection.py` encontrou 868 pares-passos com interseção
de retângulos orientados de 5 × 2 m, dos quais 788 depois de 500 m; 37 pares
distintos e nenhum abandono por contato. A contagem compara carros ativos na
mesma volta, fora dos boxes, com distância circular ao longo da pista de até
15 m. É uma amostra discreta, não uma contagem de colisões reais ou de todos
os cruzamentos possíveis. O diagnóstico usa a posição interpolada e a normal
interpolada **normalizada** do frontend, e aplica o teorema dos eixos
separadores. `TrackSpace.position` atualmente não normaliza essa normal após
interpolá-la: essa diferença também deve ser tratada ao definir a geometria
única usada para desenhar e testar corpos.

No instante 27,2 s, dois centros com lateral zero estão em 997,512 m e
1002,512 m. Ambos pertencem ao segmento acumulado 989,308–1003,048 m: o
incremento é 13,740 m, mas o comprimento XY dividido pela escala média da
volta é 4,8655 m. A interpolação produz separação cartesiana de 1,7047 m,
embora o motor imponha 5 m em distância acumulada. Isso acontece mesmo dentro
de um único segmento reto da polilinha: não é necessário atribuir o resultado
ao encurtamento da corda de uma curva.

O fixture contém 240 pontos, 239 incrementos entre 13,740 e 13,741 m, e
comprimento acumulado 3283,953 m. A escala média XY é 0,002069121818205241
por metro. As razões comprimento XY escalado / incremento acumulado têm
mínimo 0,35411, percentis 10/50/90 de 0,78030 / 0,99491 / 1,22395 e máximo
1,64666; um segmento fica abaixo de 0,5 e um acima de 1,5. A normalização XY
é uniforme entre eixos, mas isso não implica que cada incremento acumulado
corresponda ao comprimento da corda. A diferença pode refletir amostragem,
interpolação e fontes de erro da geometria reduzida; sem os dados originais ou
uma auditoria de geração não é possível atribuir uma causa específica. O
ADR 0003 descreve amostragem por distância igual; o gerador reconstruído não
promete reproduzir os artefatos originais byte a byte.

O integrador usa intervalos longitudinais e laterais como se fossem distâncias
cartesianas: `_nearest_ahead_same_lane`, `_side_by_side`, `_limit_lateral_move`
e `_rubbing` não comparam retângulos orientados projetados. O algoritmo de
contato permanece ativo, mas não detecta este par porque a distância acumulada
é de 5 m; ausência de abandono não prova ausência de sobreposição. Há ainda
supressão de contatos na zona de largada, hipótese existente do modelo.

## Efeito de trocar o eixo

Experimento em memória, sem alterar arquivos: substituir cada distância
acumulada pela soma dos comprimentos XY, escalada para conservar o comprimento
total, mantendo pontos e parâmetros físicos. Os resultados abaixo comparam
`lap_time_ms(steady_lap(...))` e os tetos de `speed_ceiling` nos mesmos índices.

| Circuito | Tempo original | Tempo experimental | Maior deslocamento do eixo | Maior diferença do teto |
| --- | ---: | ---: | ---: | ---: |
| Mônaco (6) | 79,237 s | 78,967 s | 20,23 m | 5,497 m/s |
| Albert Park (1) | 82,829 s | 82,580 s | 13,75 m | 6,735 m/s |
| Circuito 9 | 90,301 s | 90,024 s | 13,99 m | 3,830 m/s |
| Circuito 14 | 79,841 s | 79,552 s | 20,11 m | 4,052 m/s |

`speed_ceiling` usa as distâncias acumuladas para antecipar a frenagem, e a
integração por distância usa os mesmos incrementos para tempo e aceleração.
Uma troca geral de eixo mudaria esses resultados, posições de pista e boxes,
e a relação com a calibração do ADR 0015; os números acima não constituem
recalibração nem medem efeito no pelotão inteiro. A geometria original, a
telemetria e o código da física foram preservados.

Reprodução do experimento de reparametrização, na raiz da worktree:

```bash
PYTHONPATH=.:src uv run python - <<'PY'
from dataclasses import replace
from math import hypot
from tests.race_invariants import real_geometry
from f1_simulator.domain.speed_dynamics import speed_ceiling, steady_lap, lap_time_ms

for circuit in ('6', '1', '9', '14'):
    geometry = real_geometry('circuit:' + circuit)
    points = geometry.track_points
    segments = [hypot(b.x_normalized - a.x_normalized, b.y_normalized - a.y_normalized)
                for a, b in zip(points, points[1:])]
    cumulative = [0.0]
    for segment in segments:
        cumulative.append(cumulative[-1] + segment)
    modified = replace(geometry, track_points=tuple(
        replace(point, cumulative_distance_m=d / cumulative[-1] * geometry.lap_length_m)
        for point, d in zip(points, cumulative)))
    old_d, old_v = speed_ceiling(geometry)
    new_d, new_v = speed_ceiling(modified)
    print(circuit, lap_time_ms(steady_lap(geometry)), lap_time_ms(steady_lap(modified)),
          max(abs(a-b) for a, b in zip(old_d, new_d)),
          max(abs(a-b) for a, b in zip(old_v, new_v)))
PY
```

## Fatia experimental e limites

O integrador conserva as regras e o eixo anteriores. Para o carro à frente na
mesma faixa, numa janela de até duas somas dos comprimentos dos carros (20 m
para carros padrão), projeta retângulos com a normal normalizada e limita o
avanço se o estado inicial estiver livre e o final se sobrepuser. A busca
binária pressupõe uma única transição entre esses estados; não garante detectar
passagem completa entre extremos livres. Não há teletransporte de estados já
sobrepostos; colisões e ultrapassagens permanecem ativas. Os outros pares,
movimento lateral, trechos dobrados distantes no eixo e ingresso/saída dos
boxes não são cobertos pela nova verificação. A diferença em
`TrackSpace.position` também permanece; a nova consulta iguala a projeção usada
pelo diagnóstico e pelo frontend sem mudar o contrato existente dessa função.

No diagnóstico local, para semente 2 e 0,2 s, os pares-passos caíram de 868
para 107 (depois de 500 m: 788 para 99). Para 0,1 s caíram de 1043 para 202
(depois de 500 m: 849 para 187); os abandonos por contato mudaram de 2 para 1.
Para semente 3 e 0,2 s caíram de 868 para 90 e os contatos passaram de 0 a 1;
o par do contato apresenta interseção cartesiana no instante da retirada.
Mudanças de trajetória afetam os sorteios e a comparação de contagens não
isola causalmente uma única diferença. Ainda há sobreposições laterais e
centros separados por apenas 1,54 m no caso de 0,1 s. Não se pode declarar a
issue resolvida.

Desempenho exploratório: cinco execuções locais, 20 perfis, Mônaco, cinco
voltas, semente 2 e passo 0,2 s, sem instrumentar os retângulos no diagnóstico:
mediana de 0,57 s na base e 0,67 s na fatia (aproximadamente +18%). São
medições curtas nesta máquina e as trajetórias também mudam; não garantem custo
em corridas longas. O requisito de preservar desempenho ainda não foi validado.

## Próxima etapa

Uma solução sem trocar o eixo precisa resolver exclusão, avanço e movimento
lateral usando corpos no mesmo espaço cartesiano da apresentação, com busca
espacial adequada a trechos dobrados, transição entre segmentos, linha de
chegada e boxes. Precisa manter a detecção de contatos e lidar explicitamente
com estados iniciais já sobrepostos, sem teletransporte ou bloqueio circular.
A prova deve cobrir retas, curvas, diferentes distâncias de amostragem,
dobragens, passos de tempo, desempenho e resultados com geometria real.
Uma comparação SAT isolada após o avanço não garante exclusão durante o
movimento e pode fabricar ou esconder contatos; portanto não foi incorporada
como correção parcial. A proposta precisa de prévia e revisão antes do merge.

## Continuação: intenção de passagem e previsão traseira

Na branch experimental baseada em `4300dfb`, a decisão considera o teto livre
na posição do líder e mantém a detecção de contato. O corredor inicial estima a
chegada de carros mais rápidos por trás com velocidade longitudinal constante;
o atacante percorre a lateral à velocidade assumida `ASSUMED_LANE_CHANGE_MS`.
O horizonte é a duração dessa mudança lateral, sem parâmetro novo. Testa-se a
interseção temporal das dimensões dos corpos ao longo da travessia. A regra
existente para candidatos ocupados continua em vigor. É uma aproximação, não
um modelo calibrado nem uma garantia contra aceleração ou mudança lateral de
outros carros; distâncias do eixo original não equivalem sempre a distâncias XY.
A orientação veio do [tutorial oficial do TORCS](https://torcs.sourceforge.net/api/robot_tutorial_chapter_5.html).

Esta primeira fatia consulta a previsão apenas ao **iniciar** uma passagem. O
compromisso existente não revalida o corredor, e o retorno ao centro não prevê
tráfego traseiro. Experimentos locais que aplicaram a previsão também nesses
casos alteraram a exposição: em Mônaco/seed 3, o teste registrou contatos sem
interseção SAT no retrato de abandono (por exemplo `[False, False]`). O teste
geométrico original foi mantido; a ampliação foi retirada e precisa de solução
própria. Tampouco se verificam todos os cruzamentos de trajetórias em pistas
que se dobram ou entre amostras. Há cobertura determinística para carro rápido
6 m atrás, carro não se aproximando, carro distante, virada da linha de chegada,
faixa atravessada e escolha do lado alternativo.

### Medidas exploratórias

Comparação com `4300dfb`, 20 carros, Mônaco, seed 2, uma volta: o diagnóstico
SAT `/tmp/issue174_monaco_projection.py` encontrou 107 → 117 pares-passos em
0,2 s e 202 → 224 em 0,1 s. Os contatos foram 0 → 2 e 1 → 3, respectivamente.
A contagem não é número de colisões: amostra retângulos e inclui os pares ativos
fora dos boxes a até 15 m de distância circular. Trajetórias e sorteios mudam.
Não há justificativa para declarar o problema de proximidade resolvido.

Na seed 3, cinco voltas a 0,2 s, `/tmp/issue174_persistent.py` encontrou
53 inversões persistentes em 51 pares em `4300dfb` e 42 em 41 pares nesta
fatia; houve respectivamente duas e uma inversões adicionais de pares repetidos.
A métrica exige 5 m de separação em cinco amostras antes e depois, mas não
certifica passagem geométrica. Os últimos carros concluíram em 554,52 e 409,88 s;
os dois cenários houve respectivamente um e dois abandonos por contato.
As cinco execuções de `/tmp/issue174_bench5.py 3 normal` deram mediana de
0,750 s e 0,651 s; são medições curtas e concorrentes, afetadas pelas próprias
trajetórias. Os scripts citados vivem em `/tmp`, não são artefatos versionados.

Próximo passo: reprojetar revalidação e retorno junto da geometria de contato,
sem filtrar contatos para melhorar métricas, e conferir o resultado em prévia
visual com o usuário. Nenhum merge ou fechamento antes dessa revisão.
