# Consumo e desgaste dinâmicos — issue #104

Implementação no motor **2D**, conforme o [ADR 0014](adr/0014-consumo-e-desgaste-por-movimento.md).
O motor `detailed` preserva os contratos por volta. O 2D consome movimento em
`domain/dynamic_usage.py`; Arcade apresenta os resultados HTTP sem calcular
consumo ou desgaste. Nenhuma dependência foi acrescentada.

## Referências reais consultadas em 26/10/2026

- [Pirelli, prévia de Silverstone, 04/07/2023](https://press.pirelli.com/an-important-debut-on-one-of-the-toughest-tracks-for-tyres/):
  relata cargas laterais superiores a 5 g em curvas rápidas e alto esforço
  dos pneus. Sustenta usar carga lateral, mas não fornece uma lei de desgaste.
- [Michelin/Canopy, condução eficiente de F1](https://simulation.michelin.com/canopy/technical-articles/save-more-fuel-than-lando-norris-how-to-drive-an-f1-car-efficiently):
  descreve mapas de consumo por RPM/acelerador e economia ao tirar o pé antes
  da frenagem. Não publica um mapa de motor utilizável para calibrar o projeto.
- [FIA, regulamento técnico 2025, edição 1 de 11/12/2024, §5.2.3](https://www.fia.com/sites/default/files/fia_2025_formula_1_technical_regulations_-_issue_01_-_2024-12-11_1.pdf):
  estabelece o teto de 100 kg/h usado aqui. A referência é do período dos
  datasets do projeto; não se afirma conformidade com as regras de 2026.

Essas páginas são referências bibliográficas; não se incorporou um novo
dataset ou se redistribuiu o conteúdo. Versão/data são as da publicação
identificada, com consulta acima. As fixtures derivadas do FastF1 mantêm sua
proveniência e licença nos manifestos originais. O banco local não permitiu
leitura direta pelo usuário do host, mas foi consultado pela API já ativa:
`GET /api/history/tables`, `GET /api/history/schema/laps` e
`GET /api/history/schema/pit_stops`. Na consulta havia 879.870 voltas e 22.613
paradas do Trotman v128; os schemas contêm tempos, posições e identificadores,
sem medição de combustível ou perda física de borracha. Não há observações
FastF1 nesse banco. Esses fatos não identificam os novos coeficientes nem
permitem afirmar uma correlação estatística medida entre consumo/desgaste e carga.

## Curvas e pneus

```text
curvatura = |ângulo entre tangentes| / arco médio                    [1/m]
aceleração lateral = velocidade² × curvatura                         [m/s²]
desgaste = distância × (peso_base + peso_lateral × carga_lateral
                      + peso_longitudinal × esforço_longitudinal)
           × gestão / (comprimento_volta × índice_médio_referência)
```

Os termos de carga são adimensionais: lateral dividida por 3 g,
longitudinal por 5 m/s². A lateral fica limitada a 6 g e a longitudinal
a 20 m/s². O desgaste é expresso em **voltas equivalentes de carga**,
não em percentual de borracha restante. A idade real continua contando
voltas, separadamente. A penalidade do composto passa a usar o desgaste
equivalente e a estratégia recebe o mesmo valor.

O 2D planeja a primeira troca obrigatória por um orçamento de desgaste,
`max(0, total_voltas × 0,5 − 1)`, com a preferência individual de ±2 voltas
equivalentes já prevista na estratégia. A composição sorteia essa preferência
em um fluxo por ID de piloto, independente da posição no grid e dos sorteios
de incidentes. O desgaste real decide quando atingir o orçamento; não se
marca uma volta única para todos. O último prazo para cumprir dois compostos
e a restrição de parada nas voltas finais continuam valendo. Os coeficientes
e os offsets aparecem em `pit_planning_2d` (`spatial-pit-planning-v1`).
Estratégias explícitas são preservadas. Paradas iguais ainda são possíveis
quando as decisões coincidirem ou um SC favorecer todos; não se sorteiam
voltas diferentes apenas para produzir diversidade visual.

Uma curva de raio 150 m, a 144 km/h, corresponde a aproximadamente 1,09 g;
a 288 km/h, a aproximadamente 4,35 g. Assim, a parcela lateral por metro
quadruplica na mesma curva. Em reta, a parcela lateral é zero mesmo a alta
velocidade. Esse é um exemplo analítico, não uma medição de pista.

Pesos assumidos: distância 0,30; lateral 0,55; longitudinal 0,15. A referência
é calculada com uma volta limpa do envelope **base**, não do piloto. Sua
média de desgaste é uma volta equivalente. Isso redistribui a carga pelos
trechos sem duplicar a severidade já aplicada no modelo do circuito.
Gestão de pneus usa a heurística existente uma vez; agressividade atua pelo
movimento, não por outro multiplicador. Durante o serviço o desgaste não
aumenta e, ao concluí-lo, o desgaste do jogo novo começa em zero.

## Combustível

```text
tração = 0,20 + 0,50 × (v / v_referência)² + 0,30 × aceleração_positiva / 5
índice = distância × tração + 1 m/s × tempo
queima = consumo_nominal_kg_por_m × índice / índice_médio_referência
```

Em desaceleração maior que 0,10 m/s², a parcela de tração é reduzida a 10%
e não há parcela positiva de aceleração. A velocidade de referência é
200 km/h. O termo de 1 m/s é uma **distância equivalente de marcha lenta**,
não movimento do carro: mantém um pequeno consumo parado. O limite final
é 100 kg/h × duração do passo. Esses pesos e a marcha lenta são assumidos;
desaceleração é só um proxy de coasting, não acelerador medido. Não há RPM,
eficiência de motor, ERS ou consumo por marcha.

O consumo por km existente normaliza a magnitude antes do teto de vazão.
Se o envelope simulado exigir mais vazão que o limite histórico, a queima
fica abaixo desse alvo; não se aumenta artificialmente a vazão para forçar
a média. Não se desconta outra quantidade ao fechar a volta, nem se aplicam
os fatores antigos de 0,5/0,6 sob SC/VSC: velocidade e esforço já caem.
A massa atual altera o ritmo. A pane seca pode ocorrer entre duas linhas,
inclusive antes de completar a primeira volta, sem creditar uma volta falsa.

## Resposta e reprodução

Cada ponto de `trajectories_2d` pode trazer:

```text
[tempo_ms, distância_corrida_m, lateral_m, velocidade_kmh,
 distância_pit_m_ou_null, combustível_kg_ou_null, desgaste_equivalente_ou_null]
```

Os quatro/cinco primeiros campos preservam a leitura de corridas antigas.
O medidor de combustível lê as novas amostras em vez de distribuir a queima
pela volta inteira. Mudanças de fase dos boxes preservam o intervalo parado
e a troca de jogo. `usage_2d` expõe as três parcelas de desgaste, combustível
gasto, carga lateral máxima, referências e curvatura. `assumptions` contém
pesos, envelope neutro, fontes e versão `dynamic-usage-v1`.

## Verificação e diagnóstico

```bash
uv run python -m unittest tests.test_dynamic_usage tests.test_pit_lane tests.test_spatial_pit_planning -v
PYTHONPATH=src uv run python scripts/analyze_dynamic_usage.py --circuit circuit:9
```

Sem `--circuit`, o diagnóstico percorre as 24 fixtures, sem baixar dados nem
gravar nelas. Lista os cinco trechos de maior parcela lateral por metro.
Em Silverstone, o envelope base estimou pico de 5,47 g em um trecho a
238,7 km/h. É um resultado **derivado**, na ordem de grandeza da publicação
da Pirelli, não uma validação de curva identificada nem uma correlação medida.

Nos 24 circuitos, a normalização produziu uma volta equivalente em cada
referência. Entretanto, os picos laterais brutos ficaram entre 4,83 e 24,61 g,
com 273 segmentos acima do limite de 6 g. Isso evidencia limites do envelope
de velocidade e da curvatura do mock: os valores mais altos não são cargas
fisicamente verificadas. O teto reduz sua influência no desgaste, mas não
corrige nem calibra o envelope de velocidade. O diagnóstico mostra os valores
brutos justamente para que esse problema não seja escondido pelo limite.

Ficam para outra etapa: calibração com alvos observados independentes,
temperatura/pressão, escorregamento, efeitos térmicos do estilo, pneus de chuva,
mapa de motor/ERS e reabastecimento no 2D. Os pesos não são universais nem
permitem extrapolar uma previsão real de desgaste a partir da velocidade.
