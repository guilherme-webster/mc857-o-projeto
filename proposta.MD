[Grupo/Projeto]
Ra

Ra

Ra 

257111

Ra

Tema 3: Simulador de Fórmula 1

Coleta, Análise e Modelagem de Dados

Utilização dos datasets sugeridos somados a fontes externas para reunir o maior volume possível de dados sobre pilotos, circuitos, histórico de corridas e desempenho dos carros.
Os dados serão analisados para compreender como cada variável (como tipo de pista, habilidade do piloto e características do carro) impacta diretamente o ritmo da corrida, garantindo melhor fidelidade na simulação.

Fatores de Simulação 

Durante a corrida, a simulação levará em conta múltiplos fatores dinâmicos, como:

Eventos Aleatórios e Condições de Pista:
Falhas mecânicas com possíveis abandonos
Acidentes e batidas (Bandeira/Safety Car)
Mudanças climáticas
Estratégia e Atributos do Veículo:
Tipos e desgaste de pneus (compostos Macio, Médio e Duro)
Janelas e tempo de parada nos boxes (pit stops).
Consumo de combustível e ritmo de corrida.

Arquitetura do Sistema

Backend: Concentrará o algoritmo principal responsável por calcular tempos de volta, perda de rendimento por desgaste de pneus, paradas no box e a ocorrência de imprevistos. Esses cálculos determinarão o progresso e a posição exata de cada carro na pista a cada instante, enviando os dados atualizados para a tela.

Frontend: Permitirá ao usuário selecionar os parâmetros iniciais (pilotos, pistas, clima e estratégias) e acompanhará a corrida por meio de um mapa 2D interativo com a localização de cada piloto ao longo do circuito, além de uma tabela com as posições, voltas e tempos.



Tema 9: Combatendo incêndios florestais

1. Visão Geral

O projeto consiste em um sistema de avaliação e predição de queimadas florestais que integra informações de diferentes fontes para estimar a probabilidade de ocorrência de incêndios, sua possível extensão e seus impactos sobre o clima e os ecossistemas. A solução buscará relacionar fatores climáticos, florestais, naturais, antrópicos e geológicos, permitindo compreender tanto as causas naturais quanto a influência da atividade humana sobre cada região analisada.

2. Coleta e Integração de Dados

Serão utilizados os datasets sugeridos no tema — TS-SatFire, Next Day Wildfire Spread e Global Wildfire Dataset — em conjunto com outras fontes públicas que possam complementar a análise. Entre os dados considerados estão:

Dados Climáticos:
Temperatura, umidade, precipitação, velocidade e direção do vento e períodos de estiagem.

Dados Florestais e Ambientais:
Cobertura vegetal, tipo e densidade da vegetação, umidade do solo, focos de calor, histórico de queimadas e alterações no ecossistema.

Dados Geográficos e Geológicos:
Relevo, altitude, declividade, tipo de solo e localização da região analisada.

Dados Antrópicos e Antropológicos:
Proximidade de estradas e áreas urbanas, uso e ocupação do solo, desmatamento e outras intervenções humanas potencialmente associadas ao risco de incêndio.

O usuário poderá selecionar uma região e um período de interesse, importar dados em tabelas ou textos e escolher o tipo de análise desejada. O sistema realizará a limpeza, a padronização e o cruzamento espacial e temporal dessas fontes antes da aplicação dos modelos.

3. Análises e Modelagem

O sistema oferecerá dois eixos principais de análise:

Predição de Risco: Estimar a probabilidade de ocorrência de uma queimada em determinada região e período, identificando áreas de maior vulnerabilidade.

Predição de Extensão: Estimar a área potencialmente atingida e a direção de propagação do fogo com base nas condições ambientais, climáticas e geográficas disponíveis.

Além das predições, serão aplicadas técnicas de interpretação dos modelos para indicar quais variáveis mais influenciaram cada resultado. Dessa forma, a solução não se limitará à execução de modelos existentes: o grupo desenvolverá a arquitetura completa de ingestão, integração, análise e apresentação dos dados, experimentando diferentes combinações de fontes e métodos preditivos.

4. Arquitetura do Sistema

Backend: Será responsável pela ingestão e validação dos dados, pelo cruzamento geoespacial e temporal das diferentes fontes, pelo treinamento e execução dos modelos e pela geração de indicadores explicativos. Uma API disponibilizará os resultados processados para a interface.

Frontend: Permitirá ao usuário selecionar a região, o intervalo de tempo, as fontes de dados e o tipo de análise. Os resultados serão apresentados de forma interativa por meio de mapas de risco e de extensão prevista, gráficos temporais, comparações entre variáveis e explicações sobre os fatores que contribuíram para a predição.

5. Resultados Esperados e Avaliação Experimental

Como saída, o sistema produzirá mapas com a localização e o nível de risco das áreas analisadas, estimativas da extensão das queimadas, gráficos sobre a evolução das condições climáticas e ambientais e insights sobre a influência de fatores humanos, florestais e geológicos. A partir desses resultados, também serão sugeridos possíveis pontos de intervenção para reduzir a chance ou o impacto de incêndios florestais.

A avaliação experimental comparará diferentes modelos e combinações de fontes de dados, verificando a capacidade de generalização entre regiões e períodos distintos. Serão utilizadas métricas adequadas às tarefas de classificação e estimativa de área, além de análises de erro e da relevância das variáveis, para verificar não apenas a precisão das predições, mas também a utilidade das explicações apresentadas ao usuário.
