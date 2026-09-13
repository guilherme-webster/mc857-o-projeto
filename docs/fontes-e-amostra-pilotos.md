# Fontes e ampliação da amostra de pilotos

Pesquisa executada em 12/09/2026 e concluída/documentada em 13/09/2026, para
#61/#66/#67. O pedido autoriza investigar fontes adicionais e ampliar a amostra.
O [ADR 0005](adr/0005-historico-completo-e-enriquecimento-fastf1.md) continua
regendo a ingestão de produção. Consultas exploratórias abaixo não acrescentam
uma fonte silenciosamente ao modelo nem substituem os fatos já ingeridos.

## Conclusão e entrega concreta

O gargalo inicial era o recorte de **um evento com contexto FastF1**, não a
quantidade de provedores. O catálogo Trotman já contém o histórico entre eventos.
Para aumentar a amostra utilizável agora, foram ingeridas pelo ETL existente as
corridas de **Bahrein, Grã-Bretanha/Silverstone e São Paulo de 2024**.

| Evento | Sessão canônica | Voltas observadas | Voltas comparáveis |
| --- | --- | ---: | ---: |
| Bahrein | `session:1121:R` | 1.129 | 760 |
| Grã-Bretanha | `session:1132:R` | 960 | 504 |
| São Paulo | `session:1141:R` | 1.134 | 580 |
| Total | Três corridas | **3.223** | **1.844** |

A seleção contém 23 pilotos distintos. Com mínimo de dois eventos comparáveis,
20 têm estimativa agregada disponível. As janelas permanecem 10 voltas e 5
voltas de idade do pneu; tolerância de clima 120.000 ms; mínimo de três voltas
por contexto e três pilotos. Aumentar dados não demonstra, por si só, robustez
ou capacidade preditiva. Não houve ajuste das fórmulas nem validação fora da
amostra nesta entrega.

A nova base é `data/curated/history-profile-sample-2024.sqlite`. A base anterior,
com corrida/classificação de São Paulo e telemetria completa, foi preservada.
O novo recorte usa `--without-telemetry`: mantém voltas, pneus, clima e eventos
necessários ao método atual; amostras de carro/posição ficam `not_requested`.
Distâncias estimadas de marcadores podem ficar indisponíveis sem telemetria,
sem afetar o perfilamento, que não consome esses campos.

## Fontes investigadas

| Fonte | Evidência inspecionada | Utilidade para este projeto | Limite e decisão desta entrega |
| --- | --- | --- | --- |
| FastF1 3.8.3 | ETL executado em três eventos; manifestos e observações canônicas | Ampliar eventos/temporadas mantendo qualidade, pneus e relógios já integrados | Usada para a ampliação imediata; aquisição e transformação não equivalem a observações independentes de outros provedores |
| OpenF1 API v1 | Catálogo de 24 corridas de 2024, 57 voltas de Verstappen no Bahrein e uma janela de intervalos entre carros | Candidata para contexto de tráfego, conferência e eventual preenchimento de lacunas | Amostra exploratória consultada; ainda sem adapter de produção ou mistura automática com FastF1 |
| Vansh Batra, v1 | ZIP de 5.164.531 bytes, 11 CSVs, cabeçalhos e contagens auditados | Exemplos de agregação por stint e clima em 2023/2024 | O autor declara origem FastF1; arquivos brutos, limpos e agregados se sobrepõem. Não somar linhas como novas voltas |
| AlexJR, v1 | Metadados e descrição pela API pública do Kaggle | Referência de pré-processamento de telemetria | Declara FastF1/Ergast como origem e licença `Unknown`; arquivos não baixados nem integrados |
| Jolpica | README e termos oficiais | Atualizar catálogo/resultados além do snapshot Trotman | Não resolve sozinho o contexto de tráfego/qualidade; não foi duplicado no ETL |

Referências primárias:

- [FastF1 3.8.3](https://github.com/theOehrly/Fast-F1/tree/v3.8.3).
- [Documentação OpenF1](https://openf1.org/docs/): histórico desde 2023,
  sem autenticação para consultas históricas; endpoints de intervalos,
  voltas, stints e mensagens. Acesso público não define uma licença unificada
  de redistribuição dos dados. Essa condição permanece por registrar antes
  de uma adoção de produção.
- [Vansh — descrição e licença](https://www.kaggle.com/api/v1/datasets/view/vanshbatra26/f1-tyre-strategy-engine-datasets):
  v1, atualização declarada em 08/06/2026, CC BY-SA 4.0 segundo o publicador.
- [AlexJR — descrição e licença](https://www.kaggle.com/api/v1/datasets/view/alexjr2001/formula-1-dataset-race-data-and-telemetry):
  v1, atualização declarada em 12/11/2024, licença desconhecida nos metadados.
- [Termos Jolpica](https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md):
  CC BY-NC-SA 4.0 declarada para os dados; não presumir a licença CC0 do ZIP
  histórico Trotman. Nenhuma conclusão aqui concede permissão de redistribuição.

As páginas HTML do Kaggle não expuseram os detalhes necessários, mas a API
pública retornou descrição, versão e licença. Isso permitiu avançar além do
levantamento anterior sem credenciais ou assinatura.

## Auditoria da base Vansh

O ZIP foi adquirido apenas para pesquisa e guardado fora do Git em
`data/raw/source-research/vansh-v1.zip`. SHA-256:
`9da27f9c036cbb988de88cb68b7d3ebaf36bbc15f724b32da637e5b27c0021a2`.

| Arquivo/grupo | Linhas |
| --- | ---: |
| `driver_2023_cleaned.csv` | 40.752 |
| `final_merged_2023_data.csv` | 39.877 |
| `stints_2023_weather.csv` / `stints_clean.csv` | 1.198 cada |
| `weather_2023.csv` / `weather_2023_cleaned.csv` | 10.026 cada |
| `cleaned_driver_2024.csv` | 50.462 |
| `final_merged_2024_data.csv` | 40.412 |
| `cleaned_weather_2024.csv` | 7.417 |
| `stints_2024.csv` / `stints_2024_weather.csv` | 1.229 cada |

Os arquivos finais misturam treinos, classificação e corrida; o arquivo final
2023 também contém sessão vazia. Foram encontrados 22 GPs no final 2023,
24 no final 2024 e 21 no agregado de stints/clima 2023. Contagem de linhas não
é quantidade de voltas de corrida elegíveis nem cobertura uniforme.

Os campos de stint incluem GP, abreviação do piloto, composto, comprimento e
temperaturas médias. Os cabeçalhos auditados não oferecem os mesmos indicadores
`accurate`, `deleted`, `generated` e de boxes/pista exigidos pelo nosso método.
Antes de qualquer uso seria preciso documentar filtros anteriores, mapeamento
de identidades, sessões e associação temporal de clima. Não substituir o
contexto de cada volta por médias de stint de forma implícita.

## Verificação pontual do OpenF1

Foram consultadas sessões históricas de 2024, identificando Bahrein (`9472`),
Silverstone (`9558`) e São Paulo (`9636`). Para o Bahrein, a consulta do carro 1
retornou 57 voltas. A comparação exploratória com `driver:830` no catálogo do
mesmo evento encontrou **56 tempos iguais e uma diferença de 475 ms na primeira
volta**: OpenF1 97.759 ms, FastF1 97.284 ms. A primeira volta já é excluída pelo
perfilamento. Isso não estabelece precedência geral ou equivalência dos provedores.

A janela de 15:10:00–15:11:00 UTC do carro 11 retornou 18 observações de
intervalo, entre 0,296 e 0,676 segundos para o carro à frente. Esse é um exemplo
concreto de contexto que o contrato atual ainda não representa. Não é taxa de
ultrapassagem, distância física nem prova de uma volta inteira em tráfego.

Consultas reproduzíveis:

- [Sessões de corrida de 2024](https://api.openf1.org/v1/sessions?year=2024&session_name=Race).
- [Voltas do carro 1 no Bahrein](https://api.openf1.org/v1/laps?session_key=9472&driver_number=1).
- [Intervalos do carro 11 na janela auditada](https://api.openf1.org/v1/intervals?session_key=9472&driver_number=11&date%3E=2024-03-02T15:10:00&date%3C=2024-03-02T15:11:00).

As respostas, metadados e hashes estão em
`data/curated/source-research/manifest.json`; são evidência local de pesquisa,
não uma fixture de calibração nem registros já incorporados ao modelo.

## Próximas fatias recomendadas

1. Expandir o recorte FastF1 para outras corridas, preservando filtros/versão
   e relatórios de cobertura. Reservar eventos inteiros ainda não analisados,
   por exemplo Itália e Abu Dhabi/2024, antes de ajustar limiares. Esses eventos
   são uma sugestão de reserva, não validações realizadas.
2. Para OpenF1, registrar decisão de adoção e condições dos dados. Implementar
   adapter de intervalos com identidade por evento/sessão/piloto e relógio UTC.
   O número do carro só pode ser resolvido dentro da sessão; valores nulos ou
   especiais precisam permanecer explícitos. Não usar nomes como chaves.
3. Definir uma observação canônica de tráfego: sessão, piloto, instante UTC,
   intervalo em ms, distância temporal ao líder e proveniência. Preservar
   valores upstream para auditoria e definir tolerância de associação à volta.
4. Comparar cobertura/conflitos entre provedores, sem concatenar duas cópias
   da mesma volta. Testar o efeito de filtros de tráfego nos eventos reservados.
5. Só depois estimar incerteza por evento/stint e converter perfis em parâmetros
   do motor. Não criar notas universais de habilidade a partir dessa ampliação.

## Reprodução da amostra e gráficos com nomes

```bash
# Usar um ambiente com requirements-etl.txt instalado.
python3 -B scripts/ingest_fastf1.py \
  --base data/curated/history.sqlite \
  --season 2024 --rounds 1 12 21 --sessions R --without-telemetry \
  --output data/curated/history-profile-sample-2024.sqlite \
  --cache-dir data/raw/fastf1-cache
```

Saída existente é recusada; para substituir deliberadamente o banco derivado,
acrescentar `--overwrite`. Não apagar o banco de entrada para repetir gráficos.

```bash
set -e
perfil_run_dir=$(mktemp -d data/curated/perfil-ampliado.XXXXXX)
pipenv run python -B scripts/profile_drivers.py \
  --database data/curated/history-profile-sample-2024.sqlite \
  --sessions session:1121:R session:1132:R session:1141:R \
  --lap-window 10 --tyre-age-window 5 --weather-max-age-ms 120000 \
  --min-laps-per-context 3 --min-drivers-per-context 3 --min-events 2 \
  --plot-dir "$perfil_run_dir/graficos" > "$perfil_run_dir/perfil.json"
printf 'Resultado em: %s\n' "$perfil_run_dir"
```

`ProfileRun.driver_names` transporta pares imutáveis de ID/nome do cadastro
canônico. Gráficos exibem nome completo; homônimos recebem ID entre parênteses
para desambiguação. Nome ausente conserva o ID como diagnóstico. Consultas,
perfis e cálculos continuam usando IDs estáveis. A legenda fica fora da área de
dados e só inclui pilotos com pontos comparáveis naquela sessão.
