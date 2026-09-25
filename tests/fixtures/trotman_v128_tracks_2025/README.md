# Geometria mockada das pistas de 2025

`track_points.csv` complementa os IDs de circuito do Trotman v128 com uma
polilinha 2D reduzida para cada uma das 24 etapas da temporada de 2025. Cada
pista tem 240 pontos ordenados, coordenadas normalizadas, distância acumulada
em metros e primeiro/último ponto coincidentes.

As formas foram derivadas offline de voltas do FastF1 3.8.3. O arquivo não
contém a telemetria original. Fonte, sessões, pilotos, voltas, transformações e
checksum estão registrados em
`data/sources/fastf1-tracks-2025.json`, conforme o ADR 0003.

`pit_lane_points.csv` acrescenta, no mesmo sistema de coordenadas, 80 pontos
entre a entrada e a saída do pit lane de cada circuito. `isServicePoint` marca
um único local representativo de parada. Ele foi inferido do centro do trecho
de menor velocidade de uma parada observada e não representa a garagem exata
de cada equipe. Sua proveniência está em
`data/sources/fastf1-pit-lanes-2025.json`.

O script offline `scripts/rebuild_fastf1_geometry.py` reconstrói esse processo
a partir dos eventos registrados nos manifestos. O gerador original não foi
versionado, portanto novos arquivos devem ser produzidos em um diretório
separado e comparados antes de substituir esta fixture.
