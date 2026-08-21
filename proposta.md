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

Utilização dos datasets sugeridos somados a fontes externas para reunir o maior volume possível de dados sobre pilotos, circuitos, histórico de corridas e desempenho dos carros.  
Os dados serão analisados para compreender como cada variável (como tipo de pista, habilidade do piloto e características do carro) impacta diretamente o ritmo da corrida, garantindo melhor fidelidade na simulação.

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

**Backend:** Concentrará o algoritmo principal responsável por calcular tempos de volta, perda de rendimento por desgaste de pneus, paradas no box e a ocorrência de imprevistos. Esses cálculos determinarão o progresso e a posição exata de cada carro na pista a cada instante, enviando os dados atualizados para a tela.

**Frontend:** Permitirá ao usuário selecionar os parâmetros iniciais (pilotos, pistas, clima e estratégias) e acompanhará a corrida por meio de um mapa 2D interativo com a localização de cada piloto ao longo do circuito, além de uma tabela com as posições, voltas e tempos.