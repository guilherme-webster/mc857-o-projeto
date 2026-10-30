"""Contrato do torneio salvo: cenario congelado mais os resultados ja simulados.

Um torneio salvo serve a dois usos (ADR 0013):

- **reabrir**: mostrar as corridas e a classificacao sem simular nada; o
  registro guarda o resultado completo de cada etapa;
- **reexecutar**: restaurar o grid congelado e rodar de novo cada etapa com o
  mesmo ``setup``. Com a mesma versao de codigo, Python, parametros e dados, a
  derivacao de seeds da #105 reproduz as mesmas corridas.

O registro e JSON puro porque e o proprio formato persistido e trafegado pela
API; aqui ficam so as invariantes que ligam suas partes. A principal: as
corridas precisam ter sido simuladas com o grid que esta sendo congelado. Sem
isso, "reexecutar" rodaria um cenario diferente do que foi salvo, e o erro so
apareceria como um resultado inexplicavelmente distinto.

Os campos ``rules`` e ``plan`` de cada etapa sao da apresentacao (rotulos da
tela do frontend) e passam sem interpretacao: o nucleo so exige que sejam
objetos JSON.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

SAVED_TOURNAMENT_SCHEMA_VERSION = 1
"""Versao do formato; mudar a estrutura exige incrementa-la e migrar/rejeitar."""


class SavedTournamentError(ValueError):
    """O torneio nao forma um cenario consistente para salvar ou reabrir."""


def build_saved_tournament(
    *,
    tournament_id: str,
    name: str,
    saved_at: str,
    grid_state: Mapping,
    rules: Mapping,
    tournament_seed: int | None,
    stages: Sequence[Mapping],
) -> dict:
    """Monte o registro versionado depois de conferir as invariantes.

    ``grid_state`` e o grid no formato persistido do backend
    (``{"seed", "grid": [{"driver_id", ...}]}``), ou seja, a ordem de largada
    e os atributos que o motor usou. Cada etapa traz ``name``, ``circuit_id``,
    ``plan`` (apresentacao), ``setup`` (corpo de ``POST /catalog/grid/run``) e
    ``race`` (o resultado devolvido por essa rota).

    Raises:
        SavedTournamentError: etapa sem resultado, ``setup`` que nao bate com o
            resultado ou corrida simulada com outro grid.
    """

    if not name.strip():
        raise SavedTournamentError("o torneio salvo precisa de um nome")
    if not isinstance(rules, Mapping):
        raise SavedTournamentError("regras do torneio devem ser um objeto")
    if not stages:
        raise SavedTournamentError("torneio sem etapas")
    grid_ids, grid_seed = _grid_identity(grid_state)
    for index, stage in enumerate(stages):
        _check_stage(index, stage, grid_ids, grid_seed, tournament_seed)
    return {
        "schema_version": SAVED_TOURNAMENT_SCHEMA_VERSION,
        "id": tournament_id,
        "name": name.strip(),
        "saved_at": saved_at,
        "tournament_seed": tournament_seed,
        "grid": dict(grid_state),
        "rules": dict(rules),
        "stages": [
            {
                "name": stage["name"],
                "circuit_id": stage["circuit_id"],
                "plan": dict(stage["plan"]),
                "setup": dict(stage["setup"]),
                "race": stage["race"],
            }
            for stage in stages
        ],
    }


def check_saved_tournament(record: Mapping) -> None:
    """Rejeite um registro lido do disco em versao ou forma desconhecida.

    Reabrir nao refaz a checagem contra o grid (os dois estao no proprio
    registro e foram conferidos ao salvar); so garante que o formato e o
    esperado antes de entrega-lo ao frontend.
    """

    version = record.get("schema_version")
    if version != SAVED_TOURNAMENT_SCHEMA_VERSION:
        raise SavedTournamentError(
            f"versao de torneio salvo nao suportada: {version!r}"
        )
    for key in ("id", "name", "saved_at", "grid", "rules", "stages"):
        if key not in record:
            raise SavedTournamentError(f"torneio salvo sem o campo {key!r}")
    if not isinstance(record["stages"], list) or not record["stages"]:
        raise SavedTournamentError("torneio salvo sem etapas")
    _grid_identity(record["grid"])


def tournament_summary(record: Mapping) -> dict:
    """Linha da listagem: identifica o torneio sem carregar as corridas."""

    return {
        "id": record["id"],
        "name": record["name"],
        "saved_at": record["saved_at"],
        "stage_count": len(record["stages"]),
        "circuits": [stage["circuit_id"] for stage in record["stages"]],
        "tournament_seed": record.get("tournament_seed"),
        "grid_seed": record["grid"]["seed"],
        "car_count": len(record["grid"]["grid"]),
    }


def _grid_identity(grid_state: Mapping) -> tuple[tuple[str, ...], int]:
    try:
        rows = grid_state["grid"]
        seed = grid_state["seed"]
        ids = tuple(str(row["driver_id"]) for row in rows)
    except (KeyError, TypeError) as error:
        raise SavedTournamentError(f"grid congelado invalido: {error!r}") from error
    if not ids or len(set(ids)) != len(ids):
        raise SavedTournamentError("grid congelado vazio ou com piloto repetido")
    if type(seed) is not int:
        raise SavedTournamentError("grid congelado sem seed inteira")
    return ids, seed


def _check_stage(
    index: int,
    stage: Mapping,
    grid_ids: tuple[str, ...],
    grid_seed: int,
    tournament_seed: int | None,
) -> None:
    label = f"etapa {index + 1}"
    for key in ("name", "circuit_id", "plan", "setup", "race"):
        if key not in stage:
            raise SavedTournamentError(f"{label}: campo {key!r} ausente")
    setup, race = stage["setup"], stage["race"]
    if not isinstance(stage["plan"], Mapping) or not isinstance(setup, Mapping):
        raise SavedTournamentError(f"{label}: plan e setup devem ser objetos")
    if not isinstance(race, Mapping) or not race.get("classification"):
        raise SavedTournamentError(f"{label}: corrida sem classificacao")

    # A seed do torneio e o indice definem o fluxo aleatorio da etapa (#105);
    # um setup que nao os repete reexecutaria outra corrida.
    if setup.get("tournament_seed") != tournament_seed:
        raise SavedTournamentError(f"{label}: seed do torneio diferente do setup")
    if tournament_seed is not None and setup.get("stage_index") != index:
        raise SavedTournamentError(f"{label}: stage_index fora da ordem")
    if race.get("tournament_seed", tournament_seed) != tournament_seed or (
        tournament_seed is not None and race.get("stage_index") != index
    ):
        raise SavedTournamentError(f"{label}: corrida rodada com outra seed")
    race_laps = (race.get("setup") or {}).get("total_laps")
    if race_laps != setup.get("total_laps"):
        raise SavedTournamentError(f"{label}: voltas do setup e da corrida diferem")

    # O grid e conferido pela seed (atributos sorteados) e pela ordem de
    # largada; atributos editados a mao nao mudam a seed, mas aparecem no
    # proprio grid congelado, que e o que a reexecucao restaura.
    if race.get("grid_seed", race.get("seed")) != grid_seed:
        raise SavedTournamentError(
            f"{label}: corrida simulada com outro grid (seed diferente); "
            "salve o torneio logo depois de simula-lo"
        )
    starting = sorted(race.get("starting_grid") or (), key=lambda row: row["position"])
    if tuple(str(row["driver_id"]) for row in starting) != grid_ids:
        raise SavedTournamentError(
            f"{label}: ordem de largada diferente do grid atual; "
            "salve o torneio logo depois de simula-lo"
        )
