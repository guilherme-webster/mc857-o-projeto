# Modificações — modelo calibrado de corrida

Resumo do que mudou nesta branch. Base: `3549828` (`43-criar-endpoints`).
Total: 8 arquivos modificados, 25 novos. Suíte passa de 164 para 288 testes.

---

## Arquivos modificados

1. **`.gitignore`** `+3 −1`
   Ignora `/data/reports/`, porque os relatórios de backtest e o visualizador
   HTML são saídas geradas e o `CONTRIBUTING.md` pede para não versioná-las.

2. **`README.MD`** `+57 −0`
   Duas seções novas: como calibrar e validar o modelo, e como rodar o
   relatório de uma corrida sem frontend. Só acrescenta; nada foi removido.

3. **`backend/app/config.py`** `+16 −0`
   Acrescenta `MODEL_PARAMETERS`, o caminho do JSON calibrado. Aponta para
   `/data/parameters` no container e cai no diretório do repositório fora dele,
   para o backend rodar nos dois modos sem duplicar arquivo.

4. **`backend/app/loaders/loader.py`** `+65 −36`
   Corrige dois estimadores quebrados e separa escopos.
   `_estimate_pit_loss` usava a média de `duration_ms`, inflada 6,1× por
   paradas sob bandeira vermelha (145,68 s em vez de 23,90 s).
   `_estimate_degradation` regredia a corrida inteira e truncava a inclinação
   em zero, então devolvia `0.0` sempre. Agora o ritmo de referência é do
   piloto e degradação, perda de boxes e risco de abandono vêm do modelo.

5. **`backend/app/models/models.py`** `+19 −3`
   Remove os três `# TODO` e documenta o escopo de cada campo: só
   `base_lap_time_ms` é do piloto; os outros três são do modelo e valem o mesmo
   para todos os carros. Antes os quatro tinham a mesma forma e significados
   diferentes.

6. **`backend/app/routers/simulation.py`** `+19 −2`
   `POST /simulation/simulate` passa a aceitar `seed` e `stops`, com validação.
   Omitir a semente usa a padrão do serviço, não um valor aleatório, para que
   duas chamadas seguidas não divirjam sem que o cliente tenha pedido.

7. **`backend/app/services/race_simulation.py`** `+98 −9`
   Troca `simulate_race` por `simulate_detailed_race`: lê os parâmetros
   calibrados, monta um `Entrant` por piloto com estratégia e confiabilidade da
   equipe, injeta a fonte aleatória com semente e falha com 503 se os
   parâmetros não existirem, em vez de cair para ritmo constante em silêncio.

8. **`src/f1_simulator/domain/race_simulation.py`** `+323 −18`
   Acrescenta `simulate_detailed_race`, `Entrant` e `CarState`, com a volta em
   três fases: propor os tempos, resolver as disputas e só então gravar.
   `simulate_race` fica **intacto** e serve de linha de base no backtest; as 18
   linhas removidas são imports e o docstring do módulo.

---

## Arquivos novos

### Domínio — as regras, sem I/O

9. **`domain/model_parameters.py`** `331` — todos os parâmetros do modelo, com
   proveniência e validação. Cada valor declara se é `calibrated` ou `assumed`.
10. **`domain/lap_time.py`** `169` — a soma do tempo de volta, com cada parcela
    devolvida separadamente em `LapTimeBreakdown`.
11. **`domain/disputes.py`** `158` — bloqueio, ultrapassagem, exclusão física e
    contato entre carros vizinhos.
12. **`domain/strategy.py`** `148` — política de paradas (padrão Strategy).
13. **`domain/random_source.py`** `76` — fonte aleatória injetável; mesma
    semente reproduz a mesma corrida.
14. **`domain/tyres.py`** `71` — estado do jogo de pneus e sua penalidade.

### Aplicação — a matemática, sem SQL

15. **`application/calibrate_model.py`** `649` — estima os parâmetros separando
    combustível de pneu por relógios distintos.
16. **`application/backtest_model.py`** `292` — métricas e linhas de base.
17. **`application/pace_profiles.py`** `161` — ritmo de referência fora da
    amostra, reaproveitando o estimador da issue #40.

### Adaptadores — a leitura, nas bordas

18. **`adapters/persistence/sqlite_calibration.py`** `362` — lê e filtra as
    observações de calibração.
19. **`adapters/persistence/sqlite_race_scenario.py`** `232` — monta uma
    corrida observada para comparação.
20. **`adapters/persistence/sqlite_trotman_profiles.py`** `209` — permite o
    método da #40 rodar sobre dados Trotman, sem FastF1.
21. **`adapters/model_parameters_json.py`** `104` — grava e lê os parâmetros
    versionados.

### Scripts e ferramentas

22. **`scripts/calibrate_model.py`** — gera `data/parameters/model-v1.json`.
23. **`scripts/backtest_model.py`** — valida contra corridas reservadas.
24. **`scripts/race_report.py`** — roda e explica uma corrida sem frontend.
25. **`tools/race_viewer_template.html`** — visualizador autocontido da corrida.

### Dados e documentação

26. **`data/parameters/model-v1.json`** — parâmetros calibrados, versionados no
    Git conforme a seção 7.1 do plano.
27. **`docs/modelagem-corrida-calibrada.md`** — método, resultados, defeitos
    corrigidos e limitações.

### Testes — 124 novos

28. **`tests/model_support.py`** — fábricas de parâmetros para os testes.
29. **`tests/test_lap_time_model.py`** `34` — parcelas somam o total, ruído
    reprodutível, validação de parâmetros.
30. **`tests/test_calibrate_model.py`** `29` — recupera coeficientes conhecidos
    de dados sintéticos e rejeita amostra singular.
31. **`tests/test_race_engine.py`** `28` — invariantes da corrida: posições
    únicas, tempo monotônico, carro retirado não volta.
32. **`tests/test_disputes.py`** `18` — bloqueio se propaga, espaçamento mínimo
    respeitado, contato só em disputa.
33. **`tests/test_pace_profiles.py`** `15` — recupera a ordem de ritmo
    construída e respeita o corte fora da amostra.

---

## Observação sobre fim de linha

Os arquivos editados chegaram a ficar com CRLF, enquanto o repositório usa LF.
Isso fazia o `git diff` mostrar arquivos inteiros reescritos — o `README.MD`
aparecia com 356 linhas alteradas em vez de 57. Os 25 arquivos afetados foram
convertidos de volta para LF antes do commit.
