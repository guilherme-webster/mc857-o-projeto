# Estratégia de disputas no motor 2D

A lógica de seguimento e ultrapassagem é uma adaptação para o motor deste
projeto. Os parâmetros de manobra são hipóteses, não medições de Fórmula 1.

A [reavaliação da oportunidade](conclusao-de-ultrapassagens.md) encerra
perseguições que perderam o alvo ou a vantagem de ritmo antes de emparelhar.
O retorno continua sujeito ao espaço disponível, sem realocar os carros.

O tutorial oficial do [TORCS sobre ultrapassagem](https://torcs.sourceforge.net/api/robot_tutorial_chapter_5.html)
distingue seguir um adversário, escolher um corredor para passar e retornar
quando houver espaço. A referência considera o ritmo desejado em pista livre,
pois o seguidor já pode ter reduzido sua velocidade para acompanhar o líder.
O [modelo lateral do SUMO](https://sumo.dlr.de/docs/Simulation/SublaneModel.html)
ilustra movimento lateral contínuo e verificação de espaço ocupado, mas seus
parâmetros de trânsito não são uma calibração para uma corrida de F1.

A geometria de pista reduzida usa um eixo de distância cuja relação com os
comprimentos dos segmentos XY não é perfeitamente uniforme. A exclusão
espacial evita alguns encontros projetados, mas não garante ausência de
sobreposição em todas as curvas ou passos. Avaliar trajetórias, contatos e
ultrapassagens em conjunto, com sementes e cenários reproduzíveis, antes de
considerar a estratégia validada.
