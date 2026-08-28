# Projeto de Disciplina \- MC857

					Grupo “X” \- Projeto Y

| Nome do Integrante | RA |
| ----- | :---: |
| Guilherme Webster Chamoun | 257111 |
| José Mauricio De Vasconcellos Junior | 219255 |
| Gustavo Jun Tsuji  | 252278 |
| Davi Gabriel Bandeira Coutinho | 183710 |
| Vinicius Forato Coracin | 231528 |

# Tema 3: Simulador de Fórmula 1

## 1\. Coleta, Análise e Modelagem de Dados

No MVP, utilização de um único dataset, com fonte, versão e licença registradas,
para uma corrida completa em um circuito. Fontes adicionais poderão ser
incorporadas depois do primeiro incremento sem alterar o contrato do motor. Os
dados serão analisados para compreender como cada variável (como tipo de pista,
habilidade do piloto e características do carro) impacta o ritmo da corrida.

## 2\. Fatores de Simulação

Durante a corrida, a simulação levará em conta múltiplos fatores dinâmicos, como:

* **Eventos Aleatórios e Condições de Pista:**  
  * Falhas mecânicas com possíveis abandonos  
  * Acidentes e batidas (Bandeira/Safety Car)  
  * Mudanças climáticas  
* **Estratégia e Atributos do Veículo:**  
  * Tipos e desgaste de pneus (compostos Macio, Médio e Duro)  
  * Janelas e tempo de parada nos boxes (pit stops).  
  * Consumo de combustível e ritmo de corrida.

## 3\. Arquitetura do Sistema

**Backend:** Django exporá o contrato HTTP/JSON para configurar, iniciar e
consultar a corrida. O motor Python independente dos frameworks calculará tempos
de volta, perda de rendimento, paradas e imprevistos conforme o escopo de cada
incremento. O backend disponibilizará snapshots; a interface não recalculará a
classificação nem será a fonte de verdade da simulação.

**Frontend:** Será uma aplicação desktop em Python implementada com a biblioteca
Arcade. Permitirá ao usuário selecionar os parâmetros iniciais (pilotos, pistas,
clima e estratégias) e acompanhar a corrida por meio de um mapa 2D interativo
com a localização de cada piloto ao longo do circuito, além de uma tabela com as
posições, voltas e tempos. A experiência visual terá como referência principal o
projeto [IAmTomShaw/f1-race-replay](https://github.com/IAmTomShaw/f1-race-replay),
sem confundir reprodução de telemetria histórica com o motor de simulação deste
projeto.
