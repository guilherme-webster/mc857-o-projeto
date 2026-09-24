# O que o perfil de piloto deverá controlar na simulação

Especificação `driver-profile-effects-v1`, de 13/09/2026, para #67.
A especificação original definiu o experimento e seus critérios de aceite.
Em 18/09/2026, o [adaptador Python e consumidor de uma volta](ranking-e-adaptador-pilotos.md)
implementam a primeira integração; a corrida completa permanece pendente. Segue os ADRs 0002/0004/0005 e a decomposição de tempo de
volta do [plano do produto](../Desenvolvimento%20de%20Simulador%20F1.md).

## Objetivo e significado

O primeiro uso proposto do perfil é controlar **tempo relativo de volta** e,
quando houver um modelo de variação calibrado, **flutuação do tempo entre voltas**.
O resultado atual representa desempenho observado do conjunto piloto/equipe no
recorte escolhido. Não é habilidade inata, nota 0–100, chance de acidente,
agressividade, capacidade de ultrapassar ou degradação de pneus.

Separar explicitamente três objetos conceituais, sem criar serviços ou classes
antes de existir consumidor concreto:

1. **Evidência observacional:** `DriverProfile` e `ProfileSupport` existentes,
   com ritmo, MAD, eventos, contextos, voltas, proveniência e incerteza.
2. **Parâmetros de um experimento:** seleção explícita de evidência, escopo e
   hipótese que traduz a evidência em efeito no tempo de volta.
3. **Estado da simulação:** tempo, classificação e eventos produzidos pelo motor.
   O frontend apresenta esse estado; não recalcula perfis.

## Ritmo relativo: alvo do primeiro experimento

| Campo conceitual | Unidade | Regra |
| --- | --- | --- |
| `driver_id` | identificador canônico | Não usar nome ou número do carro como chave |
| `team_id` | identificador canônico | Equipe do recorte, sem assumir transferência do efeito a outra equipe |
| `pace_offset_pct` | % do tempo de referência | Finito e maior que −100; negativo reduz o tempo |
| `reference_lap_time_ms` | ms | Positivo, finito e definido para o cenário/contexto |
| `profile_method_version` / `parameter_version` | identificador | Registrar método e hipótese de aplicação separadamente |
| `source_sessions` / `source_manifest_hashes` | seleção/proveniência | Só dados autorizados para desenvolvimento/calibração |
| `support` / `warnings` | contagens e motivos | Acompanhar o parâmetro, sem se transformar em nota |

A regra determinística candidata é:

```text
pace_effect_ms = reference_lap_time_ms * pace_offset_pct / 100
modeled_lap_time_ms = reference_lap_time_ms + pace_effect_ms
```

Exemplo verificável: referência de 100.000 ms e −1% produzem efeito −1.000 ms
e tempo 99.000 ms; +1% produz 101.000 ms. Isso é uma hipótese de aplicação de
ritmo relativo, não uma equação de previsão já validada.

O parâmetro permanece **conjunto piloto/equipe**. Não somar novamente um efeito
independente de equipe derivado dos mesmos resultados. Se a referência já é
específica do piloto/equipe, aplicar o deslocamento novamente duplicaria o efeito.
Antes da integração, a referência deve declarar precisamente o que já contém.

O perfil agregado entre circuitos não fornece, sozinho, a referência em ms de
um circuito. Também não fornece efeitos causais separados de pneu, combustível,
clima ou tráfego. Usar uma referência que já incorpora determinada condição e
somar sua penalidade novamente seria outra forma de duplicação.

O efeito deve ser calculado uma vez por volta (ou repartido por um contrato de
setores que preserve a soma), nunca reaplicado a cada quadro da interface.
A conversão/arredondamento para relógio inteiro deve ocorrer em um ponto único,
com política registrada na futura integração.

## Variabilidade: significado e limites

`consistency_mad_pct` é o MAD observado dos resíduos, agregado por contexto e
evento. Sua unidade é ponto percentual do tempo relativo, embora o nome legado
termine em `_pct`. Não é desvio padrão, erro da média ou probabilidade de erro.

Para dar escala física, um MAD de 0,2 pp sobre 100.000 ms corresponde a 200 ms
naquela referência. Essa conversão de unidade **não define uma distribuição**
de ruído nem autoriza fazer `gauss(0, 200)`.

O primeiro experimento deve expor dois modos conceituais:

- `disabled`: execução determinística, sem perturbação; uma escolha explícita
  do cenário. Não significa que a variabilidade real do piloto seja zero.
- `calibrated`: perturbações produzidas por um modelo calibrado e versionado,
  com unidades em ms, fonte aleatória injetada e semente registrada. Indisponível
  enquanto distribuição, dependência temporal e limites não forem definidos.

No modo calibrado, o objetivo é variar os tempos ao redor do ritmo modelado,
sem introduzir inadvertidamente outro deslocamento de ritmo. A medida de centro
(média ou mediana), assimetria, autocorrelação e a forma de garantir tempos
positivos precisarão constar da calibração. Não truncar silenciosamente ruído
negativo nem copiar uma distribuição normal por conveniência.

Os intervalos bootstrap quantificam incerteza entre eventos do **estimador**.
Não são a distribuição das perturbações entre voltas e não devem alimentar o
motor como ruído. MAD e largura do intervalo não são intercambiáveis.

## Disponibilidade e comportamento esperado

- Ausência de perfil, equipe incompatível ou suporte abaixo dos mínimos torna
  o parâmetro derivado indisponível; não preencher com zero.
- Um cenário pode escolher explicitamente uma referência neutra para todos os
  pilotos, mas isso deve ser identificado como referência experimental, não como
  perfil inferido. A mesma política vale para participantes sem histórico.
- Avisos de poucos eventos acompanham os valores. Ter cinco eventos ou um
  intervalo estreito não promove automaticamente um parâmetro a calibrado.
- O usuário da simulação deverá saber se está usando referência neutra,
  hipótese experimental ou parâmetro calibrado, sem precisar conhecer formatos
  de banco, ETL ou detalhes internos do bootstrap.
- Falta de suporte é uma condição de domínio legível. Dados canônicos são
  consultados por repository Python; nenhum HTTP é necessário entre esses módulos.

## Critérios de aceite da futura integração

1. Os exemplos de 99.000/100.000/101.000 ms passam sem depender de banco, janela
   ou FastAPI; a decomposição expõe referência, efeito de ritmo e perturbação.
2. Com variabilidade desativada, o mesmo cenário produz exatamente os mesmos
   tempos; com modelo calibrado e mesma semente, repete também as perturbações.
3. Unidades, valores inválidos, indisponibilidade e incompatibilidade de escopo
   são validados antes de iniciar a corrida. Não há fallback silencioso.
4. O cenário registra referência, parâmetros, versão, seleção e proveniência;
   não consome eventos reservados para construir seus parâmetros.
5. A aplicação não aplica efeito da equipe duas vezes e a renderização não
   altera resultados pelo número de quadros.
6. Comparação com a referência neutra usa eventos separados, métricas definidas
   antes da avaliação e os mesmos critérios de disponibilidade.

## Decisões ainda pendentes e motivo

- **Referência em ms:** a [especificação por contexto exato](companheiros-e-referencia-deterministica.md)
  define o microexperimento determinístico. A seleção de referências para uma
  corrida completa e sua transferência para outros eventos continuam pendentes;
  não podem ser extraídas do percentual agregado entre circuitos.
- **Separação piloto/equipe e transferência entre equipes:** requer comparações
  e hipóteses adicionais; o perfil atual não identifica esses efeitos.
- **Ruído calibrado:** requer analisar resíduos e dependência temporal no
  desenvolvimento; MAD sozinho é insuficiente para escolher a distribuição.
- **Limites de extrapolação e suficiência estatística:** precisam ser avaliados
  com mais eventos, não escolhidos a partir de pilotos destacados nos gráficos.

O backend atual possui um gerador de demonstração em
`backend/app/engine/simulation.py`, com tempos fixos por índice/volta. Essa lógica
não constitui integração com o perfil e não é alterada nesta especificação.
A aquisição da amostra que permitirá avançar está no
[protocolo de 2024](amostra-pilotos-2024-expandida.md).
