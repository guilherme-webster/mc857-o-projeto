# Conclusão e reorganização de uma tentativa

A versão `passing-opportunity-revalidation-assumed-v1` reavalia uma passagem
em andamento. Se o alvo abrir mais de 40 m (duas vezes a janela inicial de
20 m), a oportunidade termina. Essa histerese evita alternância na borda da
janela. Antes de emparelhar, a tentativa também termina se o atacante perder
sua vantagem de teto efetivo, comparado no mesmo ponto da pista. Os valores
são hipóteses publicadas em `assumptions.passing_opportunity`.

Encerrar a oportunidade não move o carro instantaneamente para o centro:
`_safe_center`, o limite lateral por tempo e a proteção de corpos continuam
controlando a reorganização. A proteção de movimento trata separadamente
carros de trás: eles restringem o deslocamento lateral do líder, enquanto
manter a separação longitudinal é responsabilidade do seguidor, processado
depois. Misturar essas duas verificações criava espera circular em Mônaco,
inclusive quando o SC obrigava o pelotão a voltar ao centro.

Regressões cobrem o par que reproduzia o bloqueio em XY, impedimento de
atravessamento lateral, conclusão de perseguição improdutiva e o cenário de
SC forçado nas voltas 2–6. O eixo de distância e os parâmetros calibrados
foram preservados.

## Avaliação inicial

Na prévia de Mônaco com os 20 perfis fictícios do projeto, 30 voltas, semente
3, pneus/combustível/boxes e controle de prova, o maior intervalo contínuo
de dois carros lado a lado caiu de 55,8 para 29,4 s. O critério é distância
longitudinal de até um comprimento e separação lateral de pelo menos uma
largura. Não é uma contagem de ataques concluídos. Nas duas versões houve
um abandono por contato e 19 carros terminaram.

Em oito cenários de cinco voltas, circuitos 6/9, sementes 1/2, 20 carros e
passos de 0,1/0,2 s, os abandonos passaram de 1 para 2, sobreposições por
amostra de 207 para 597 e inversões persistentes de posição de 1.446 para
1.379. Todos concluíram. São medidas exploratórias, sem calibração de
acidentes e sem certificação de validade geométrica das ultrapassagens.
Ainda há sobreposições e os resultados dependem da geometria e do passo.

Na matriz ampliada de 36 cenários, incluindo o circuito 14, grids de 10 e 20
e sementes 1–3, todos os carros ativos concluíram sem recuo. Contra a versão
v2 do PR #187, abandonos por contato passaram de 2 para 5, sobreposições por
amostra de 633 para 1.354, inversões persistentes de 4.345 para 3.989 e amostras
de frenagem acima de 50 m/s² de 5.725 para 6.222. O tempo agregado com
diagnóstico foi 72,790 → 75,051 s, em máquina compartilhada. Essa regressão
de contatos exige avaliar a variante além da melhora de emparelhamento. Após
avaliar a prévia experimental, o usuário aprovou sua incorporação ao fluxo
normal do frontend. As limitações numéricas permanecem registradas; não houve
calibração de acidentes reais. O diagnóstico passou a publicar `longest_parallel_s`
e `longest_parallel_pair` para medir o comportamento continuamente.

Antecipar o ataque ou fixar o lado durante toda a disputa foi experimentado e
não incorporado: essas variantes pioraram contatos ou prenderam o pelotão.
O experimento de recalcular o eixo por arco XY também permanece separado,
pois altera contratos e a relação com a calibração e não eliminou regressões.
