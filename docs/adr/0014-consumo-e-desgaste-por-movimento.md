# 0014 - Consumo e desgaste por movimento no motor 2D

- Status: aceita
- Data: 2026-10-26
- Autorização: usuário, ao solicitar a implementação da issue #104
- Integração revista em 06/11/2026 na develop: número 0014 preserva o ADR 0013
  dos torneios salvos, já aceito nessa branch.
- Atualiza: aproximação por volta dos recursos no motor 2D dos ADRs 0011/0012
- Relaciona-se: ADRs 0008 (heurísticas), 0009 (massa de combustível, proposta)
  e 0010 (envelope físico de velocidade)

## Contexto

O 2D já produz movimentos sub-volta, mas envelhecia o pneu e descontava uma
quantidade fixa de combustível apenas ao cruzar a linha. Uma curva rápida
não gastava mais pneu que uma reta, e a exibição de combustível interpolava
uma perda uniforme. O usuário pediu consumo e desgaste sensíveis à velocidade,
aceleração/frenagem, estilo e curvas, fundamentados em referências reais.

## Decisão

Integrar recursos em cada movimento efetivo do motor 2D, também durante a
pit lane e o serviço. Manter o motor por volta e seus parâmetros existentes.

- Estimar curvatura em 1/m pelo ângulo entre tangentes e pelo arco em metros
  das mesmas fixtures. Aceleração lateral é `v² * curvatura`; um teto
  configurável de 6 g limita a influência de picos do mock.
- Acumular desgaste em **voltas equivalentes de carga**, separado da idade
  em voltas completadas. Somar exposição por distância, carga lateral e
  aceleração/frenagem. Sem deslocamento não há desgaste. A penalidade de
  composto recebe essa idade equivalente, sem somar outra vez a idade real.
- Normalizar os índices pela volta limpa do envelope base do circuito, a
  mesma para todos os pilotos. Não normalizar pelo envelope de cada piloto,
  pois isso apagaria as diferenças de estilo. A severidade do circuito e os
  coeficientes de composto continuam no cálculo da penalidade, uma única vez.
- Aplicar gestão de pneus à acumulação, uma vez. Agressividade já afeta o
  movimento pelo envelope/frenagem e pelas manobras; não ganha um segundo
  multiplicador arbitrário de recursos.
- Planejar a troca obrigatória de composto pelo desgaste equivalente e pela
  preferência individual semeada de ±2 voltas, antes do último prazo comum.
  O orçamento neutro é metade da corrida menos a volta de entrada, escolhido
  por `SpatialPitPlanningParameters`, não calibrado. Essa regra é exclusiva
  do 2D; o prazo final e estratégias explícitas continuam preservados.
- Usar um proxy de demanda de combustível por distância, velocidade ao
  quadrado e aceleração positiva; desaceleração reduz o proxy de tração.
  Adicionar marcha lenta por segundo, inclusive no serviço parado. Não
  inferir posição real do acelerador ou RPM de uma simples desaceleração.
- Aplicar 100 kg/h como limite de referência **2025**, art. 5.2.3, compatível
  com os dados 2022–2025. Não é o regulamento de 2026 nem um mapa de consumo
  calibrado. Esse limite pode reduzir a média abaixo do consumo nominal.
- Não aplicar os antigos fatores de queima SC/VSC no caminho contínuo: o
  ritmo menor já reduz o esforço. A massa atual e o desgaste acumulado
  atualizam `speed_scale`, tornando o efeito progressivo dentro da volta.
- Pane seca interrompe o movimento no subpasso; não cria uma volta fictícia
  para satisfazer o formato legado. O frontend lê o instante final da
  trajetória e aceita abandono com zero voltas somente no formato 2D.
- Acrescentar combustível e desgaste aos campos opcionais 6 e 7 das
  trajetórias HTTP. O frontend interpola as amostras do domínio, preservando
  formatos antigos de 4 e 5 campos. `usage_2d` expõe referência, curvatura e
  parcelas acumuladas para auditoria; modelo ausente permanece nulo.

## Evidência e limites

As fontes primárias, os pesos, as fórmulas e o diagnóstico reproduzível ficam
em [consumo-desgaste-dinamicos.md](../consumo-desgaste-dinamicos.md). Pirelli
relaciona curvas rápidas a altas cargas laterais; Michelin descreve mapas de
consumo dependentes de RPM/acelerador e economia por lift-and-coast. Essas
fontes fundamentam tendências, não fornecem os pesos do nosso simulador.

Os novos parâmetros são assumidos (`dynamic-usage-v1`), não calibrados.
Temperatura, pressão, escorregamento, desgaste em mm, mapa de motor e ERS
continuam ausentes. A marcha lenta também é uma hipótese. A entrada nos boxes
mantém o limite instantâneo e o ponto único do ADR 0012; reabastecimento no 2D
continua fora desta entrega. Os pesos físicos não garantem previsão de corrida.

Não há dataset novo nem alteração das fixtures ou dos JSONs calibrados.
Publicações externas são referências bibliográficas. O histórico Trotman local
foi consultado pela API existente, pois o arquivo não é legível pelo usuário
do host. Seus tempos de voltas/paradas não trazem combustível ou perda de
borracha medidos; não houve estimação ou correlação estatística entre essas
grandezas medidas e os novos fatores.

Validação: tendências conhecidas (mesma curva mais rápida, reta, coasting),
conservação de massa, particionamento de movimento, convergência do passo,
serviço parado, troca de jogo, pane seca e reprodução pelo frontend.
