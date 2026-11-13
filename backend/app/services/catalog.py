from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import UTC
from pathlib import Path

from fastapi import HTTPException, status

from app.config import (
    CURRENT_GRID_JSON,
    CURRENT_RACE_JSON,
    FUEL_PARAMETERS,
    HISTORY_DB,
    MODEL_PARAMETERS,
    REFERENCE_LAPS,
    SAVED_RACES_DIR,
)
from f1_simulator.application import catalog as core_catalog

_HISTORY_NOT_FOUND = (
    f"history database ({HISTORY_DB.name}) has not been built yet; "
    "run POST /api/history/build to import the full history"
)
_GRID_NOT_FOUND = "no current grid; run POST /catalog/grid to build one"

# O caminho fica nesta composition root porque ``backend/app/config.py`` nao
# pertence a esta fatia. O default atende execucao local a partir do checkout;
# ``F1_DRIVER_PRESETS_JSON`` permite que empacotamentos montem o mesmo arquivo
# em outro lugar sem acoplar o nucleo ao sistema de arquivos.
_REPOSITORY_DRIVER_PRESETS = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "drivers"
    / "perfis-ficticios.json"
)
DRIVER_PRESETS_JSON = Path(
    os.environ.get("F1_DRIVER_PRESETS_JSON", _REPOSITORY_DRIVER_PRESETS)
)

# Presets ficticios de carro por equipe, no mesmo molde dos de piloto. O
# default atende execucao local a partir do checkout; ``F1_CAR_PRESETS_JSON``
# permite montar o arquivo em outro lugar no container sem acoplar o nucleo.
_REPOSITORY_CAR_PRESETS = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "cars"
    / "perfis-ficticios.json"
)
CAR_PRESETS_JSON = Path(
    os.environ.get("F1_CAR_PRESETS_JSON", _REPOSITORY_CAR_PRESETS)
)

# Presets ficticios de execucao de equipe (organizacao de pit stop). Mesmo
# molde dos de carro; ``F1_TEAM_PRESETS_JSON`` permite montar em outro lugar.
_REPOSITORY_TEAM_PRESETS = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "teams"
    / "perfis-ficticios.json"
)
TEAM_PRESETS_JSON = Path(
    os.environ.get("F1_TEAM_PRESETS_JSON", _REPOSITORY_TEAM_PRESETS)
)


def _repository():
    from f1_simulator.adapters.persistence.sqlite_history import (
        SQLiteHistoryRepository,
    )

    if not HISTORY_DB.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_HISTORY_NOT_FOUND
        )
    return SQLiteHistoryRepository(HISTORY_DB)


def list_entries() -> tuple[core_catalog.CatalogEntry, ...]:
    try:
        return core_catalog.list_entries(_repository())
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error


def _select_pairs(pool, size, mode, manual_pair_ids, seed):
    from f1_simulator.application.build_grid import build_grid as core_build_grid
    from f1_simulator.domain.random_source import SeededRandomSource

    rng = SeededRandomSource(seed).spawn("grid") if mode == "random" else None
    try:
        return core_build_grid(
            size, pool, mode=mode, manual_pair_ids=manual_pair_ids, rng=rng
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


def _generate(driver_ids, seed):
    from f1_simulator.application.generate_attributes import (
        apply_presets,
        generate_attributes,
    )
    from f1_simulator.domain.random_source import SeededRandomSource

    source = SeededRandomSource(seed).spawn("attributes")
    attributes = generate_attributes(driver_ids, source)
    if DRIVER_PRESETS_JSON.exists():
        from f1_simulator.adapters.driver_presets_json import (
            DriverPresetError,
            load_driver_presets,
        )

        try:
            presets = load_driver_presets(DRIVER_PRESETS_JSON)
            attributes = apply_presets(attributes, presets, source)
        except DriverPresetError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(error),
            ) from error
    return {item.driver_id: item for item in attributes}


def build_grid(size, *, mode, manual_pair_ids, seed, race_id=None):
    """Monte e persista o grid atual.

    ``mode="race"`` reproduz a largada de ``race_id`` no historico: os pares
    vem de ``starting_grid_pair_ids`` e seguem pelo modo manual, de modo que
    a validacao do catalogo e a mesma.
    """

    used_seed = seed if seed is not None else _new_seed()
    if mode == "race":
        manual_pair_ids = _race_pair_ids(race_id)
        size, mode = len(manual_pair_ids), "manual"
    pairs = _select_pairs(list_entries(), size, mode, manual_pair_ids, used_seed)
    attributes = _generate([entry.driver_id for entry in pairs], used_seed)
    _write_current_grid(pairs, attributes, used_seed)
    return pairs, attributes, used_seed


def _race_pair_ids(race_id):
    try:
        return core_catalog.starting_grid_pair_ids(_repository(), race_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error


def driver_profiles():
    """Perfis ficticios nomeados e o aviso do arquivo, ou ``({}, None)``.

    Sem arquivo de presets o grid continua valido, apenas sem perfis.
    """

    if not DRIVER_PRESETS_JSON.exists():
        return {}, None
    from f1_simulator.adapters.driver_presets_json import (
        DriverPresetError,
        load_driver_preset_file,
    )

    try:
        return load_driver_preset_file(DRIVER_PRESETS_JSON)
    except DriverPresetError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error


def _car_presets():
    """Presets de carro: ``(presets, disclaimer, overrides_por_piloto)``.

    Sem arquivo de presets o grid corre com o carro de referencia unico e o
    resultado nao muda; nao e erro. Arquivo presente porem invalido e erro de
    implantacao e vira 500, como os demais parametros de configuracao.
    """

    if not CAR_PRESETS_JSON.exists():
        return None, None, {}
    from f1_simulator.adapters.car_presets_json import (
        CarPresetError,
        load_car_preset_file_with_overrides,
    )

    try:
        return load_car_preset_file_with_overrides(CAR_PRESETS_JSON)
    except CarPresetError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error


def _team_presets():
    """Presets de execucao de equipe (pit), ou ``(None, None)`` sem arquivo.

    Nao modela confiabilidade mecanica (abandono), que segue calibrada em
    ``model-v1.json``. Ausencia nao e erro; arquivo invalido vira 500.
    """

    if not TEAM_PRESETS_JSON.exists():
        return None, None
    from f1_simulator.adapters.team_presets_json import (
        TeamPresetError,
        load_team_preset_file,
    )

    try:
        return load_team_preset_file(TEAM_PRESETS_JSON)
    except TeamPresetError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error


def read_current_grid():
    if not CURRENT_GRID_JSON.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_GRID_NOT_FOUND
        )
    try:
        state = json.loads(CURRENT_GRID_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    return _deserialize_grid(state)


def edit_current_grid(*, overrides=None, order=None):
    """Aplique atributos e/ou uma permutacao e publique o grid uma unica vez.

    Todas as validacoes acontecem antes da escrita atomica. Reordenar reutiliza
    os mesmos ``GridEntry`` e o mesmo mapa de atributos, preservando tambem a
    seed; os perfis expostos pela rota continuam derivados dessas origens.
    """

    from f1_simulator.application.build_grid import GridOrderError, reorder_grid
    from f1_simulator.application.generate_attributes import apply_overrides

    pairs, attributes, seed = read_current_grid()
    if order is not None:
        try:
            pairs = reorder_grid(pairs, order)
        except GridOrderError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
            ) from error
    if overrides is None:
        overrides = ()
    patch = {
        item.driver_id: {
            field: value
            for field, value in (
                ("pace_offset_pct", item.pace_offset_pct),
                ("consistency_factor", item.consistency_factor),
                ("tyre_management_factor", item.tyre_management_factor),
                ("aggression", item.aggression),
                ("composure", item.composure),
            )
            if value is not None
        }
        for item in overrides
    }
    if patch:
        try:
            edited = apply_overrides(list(attributes.values()), patch)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error
        attributes = {item.driver_id: item for item in edited}
    _write_current_grid(pairs, attributes, seed)
    return pairs, attributes, seed


def _track_reference(track_id):
    """Valide o ID no catalogo de geometria e devolva ID canonico e extensao."""

    if track_id is None:
        return None, None
    from app.services.track_geometry import list_available_tracks

    canonical = track_id if track_id.startswith("circuit:") else f"circuit:{track_id}"
    tracks = {item["circuit_id"]: item for item in list_available_tracks()["tracks"]}
    if canonical not in tracks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"track_id desconhecido no catalogo: {track_id}",
        )
    return canonical, tracks[canonical]["lap_length_m"]


def _model_parameters():
    """Carregue o artefato do modelo ou sinalize indisponibilidade da API."""

    from f1_simulator.adapters.model_parameters_json import read_parameters

    try:
        return read_parameters(MODEL_PARAMETERS)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"parametros do modelo indisponiveis: {error}",
        ) from error


def _reference_lap(track_id):
    """Entrada da tabela historica para a pista, ou ``None`` se nao houver.

    Arquivo ausente ou circuito sem entrada nao sao erro: o caso de uso cai na
    hipotese de ritmo por km e declara isso nas ``assumptions``. Um arquivo
    presente porem invalido e erro de implantacao e vira 503.
    """

    if track_id is None:
        return None
    from f1_simulator.adapters.reference_laps_json import (
        ReferenceLapsError,
        read_reference_laps,
    )

    try:
        table = read_reference_laps(REFERENCE_LAPS)
    except FileNotFoundError:
        return None
    except (OSError, ReferenceLapsError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"tabela de voltas de referencia invalida: {error}",
        ) from error
    return table.get(track_id)


def _track_geometry(track_id):
    """TrackGeometry da pista para o motor fisico (ADR), ou None sem artefato.

    Pista sem geometria disponivel nao e erro: o motor cai no tempo calibrado.
    """

    if track_id is None:
        return None
    from app.services.track_geometry import geometry_object

    try:
        return geometry_object(track_id)
    except HTTPException:
        return None


def _fuel_parameters():
    """Modelo de massa de combustivel, ou ``None`` se o artefato nao existe.

    Ausencia nao e erro: o motor usa o combustivel linear de ``model-v1.json``
    e o resultado simplesmente nao traz o bloco ``fuel``. Artefato presente
    porem invalido e erro de implantacao e vira 503.
    """

    from f1_simulator.adapters.fuel_parameters_json import (
        FuelParametersError,
        read_fuel_parameters,
    )

    try:
        return read_fuel_parameters(FUEL_PARAMETERS)
    except FileNotFoundError:
        return None
    except (OSError, FuelParametersError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"parametros de combustivel invalidos: {error}",
        ) from error


def _pit_entry_fraction(track_id):
    """Posicao da entrada dos boxes na volta, pela geometria; ``None`` sem ela.

    Geometria ausente ou invalida nao impede a corrida: o caso de uso supoe a
    entrada na linha de chegada.
    """

    if track_id is None:
        return None
    from app.services.track_geometry import geometry_dataset
    from f1_simulator.adapters.datasets.mock_track_geometry import (
        MockTrackDatasetError,
    )
    from f1_simulator.domain.track_geometry import pit_entry_lap_fraction
    from f1_simulator.factories.track_geometry_factory import (
        TrackGeometryFactory,
        TrackGeometryValidationError,
    )

    try:
        dataset = geometry_dataset()
        if dataset is None:
            return None
        geometry = TrackGeometryFactory.build(dataset.load_geometry(track_id))
        return pit_entry_lap_fraction(geometry)
    except (OSError, ValueError, MockTrackDatasetError, TrackGeometryValidationError):
        return None


def run_grid(
    *,
    total_laps,
    track_id,
    weather,
    tournament_seed=None,
    stage_index=0,
    on_progress=None,
    cancellation=None,
):
    from f1_simulator.application.run_grid_simulation import (
        RaceSetup,
        run_grid_simulation,
    )
    from f1_simulator.domain.random_source import (
        TOURNAMENT_STAGE_STREAM_VERSION,
        SeededRandomSource,
        derive_tournament_stage_seed,
    )
    from f1_simulator.domain.weather import RainLevel, WeatherSegment

    pairs, attributes, seed = read_current_grid()
    canonical_track_id, lap_length_m = _track_reference(track_id)
    geometry = _track_geometry(canonical_track_id)
    try:
        segments = tuple(
            WeatherSegment(
                from_lap=item.from_lap,
                to_lap=item.to_lap,
                rain=RainLevel(item.rain),
            )
            for item in weather
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    setup = RaceSetup(
        total_laps=total_laps,
        track_id=canonical_track_id,
        weather=segments,
        tournament_seed=tournament_seed,
        stage_index=stage_index,
    )
    rng = SeededRandomSource(seed).spawn("race")
    car_presets, car_preset_disclaimer, car_overrides = _car_presets()
    team_presets, team_preset_disclaimer = _team_presets()
    try:
        result = run_grid_simulation(
            pairs,
            attributes,
            setup,
            parameters=_model_parameters(),
            lap_length_m=lap_length_m,
            rng=rng,
            reference_lap=_reference_lap(canonical_track_id),
            geometry=geometry,
            fuel_parameters=_fuel_parameters(),
            pit_entry_fraction=_pit_entry_fraction(canonical_track_id),
            car_presets=car_presets,
            car_preset_disclaimer=car_preset_disclaimer,
            car_overrides_by_driver=car_overrides,
            team_presets=team_presets,
            team_preset_disclaimer=team_preset_disclaimer,
            on_progress=on_progress,
            **({"check_cancelled": cancellation.check} if cancellation else {}),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    result["seed"] = seed
    result["grid_seed"] = seed
    result["tournament_seed"] = tournament_seed
    result["stage_index"] = stage_index
    if tournament_seed is None:
        # O filho legado de ``spawn('race')`` tem 256 bits. Texto decimal evita
        # perda silenciosa em clientes JSON baseados em ``double``; a derivacao
        # nova cabe em 53 bits, mas usa o mesmo formato estavel na resposta.
        result["race_seed"] = str(rng.seed)
        result["race_stream_id"] = "grid-seed-v1:race"
    else:
        result["race_seed"] = str(
            derive_tournament_stage_seed(tournament_seed, stage_index)
        )
        result["race_stream_id"] = (
            f"{TOURNAMENT_STAGE_STREAM_VERSION}:{stage_index}"
        )
    # A decisao de cancelar e as duas gravacoes compartilham o mesmo lock.
    # Uma corrida cancelada nunca chega a substituir o resultado anterior.
    from contextlib import nullcontext

    with cancellation.commit() if cancellation else nullcontext():
        _write_json(CURRENT_RACE_JSON, result)
        _persist_saved_race(result, _default_race_name(result))
    return result


def _serialize_grid(pairs, attributes, seed) -> dict:
    return {
        "seed": seed,
        "grid": [
            {
                "driver_id": entry.driver_id,
                "driver_name": entry.driver_name,
                "team_id": entry.team_id,
                "team_name": entry.team_name,
                "attributes": {
                    "archetype": attributes[entry.driver_id].archetype,
                    "pace_offset_pct": attributes[entry.driver_id].pace_offset_pct,
                    "consistency_factor": attributes[
                        entry.driver_id
                    ].consistency_factor,
                    "tyre_management_factor": attributes[
                        entry.driver_id
                    ].tyre_management_factor,
                    "aggression": attributes[entry.driver_id].aggression,
                    "composure": attributes[entry.driver_id].composure,
                    "sources": dict(attributes[entry.driver_id].sources),
                },
            }
            for entry in pairs
        ],
    }


def _deserialize_grid(state: dict):
    from f1_simulator.application.build_grid import GridEntry
    from f1_simulator.domain.driver_attributes import DriverAttributes

    pairs = []
    attributes = {}
    for row in state["grid"]:
        pairs.append(
            GridEntry(
                driver_id=row["driver_id"],
                driver_name=row["driver_name"],
                team_id=row["team_id"],
                team_name=row["team_name"],
            )
        )
        attribute = row["attributes"]
        missing_v2_fields = {
            "aggression",
            "composure",
        }.difference(attribute)
        if missing_v2_fields:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "current grid uses the driver-attributes v1 schema and "
                    "cannot run the simulation; rebuild it with "
                    "POST /catalog/grid"
                ),
            )
        attributes[row["driver_id"]] = DriverAttributes(
            driver_id=row["driver_id"],
            archetype=attribute["archetype"],
            pace_offset_pct=attribute["pace_offset_pct"],
            consistency_factor=attribute["consistency_factor"],
            tyre_management_factor=attribute["tyre_management_factor"],
            aggression=attribute["aggression"],
            composure=attribute["composure"],
            sources=attribute["sources"],
        )
    return tuple(pairs), attributes, state["seed"]


def _write_current_grid(pairs, attributes, seed) -> None:
    _write_json(CURRENT_GRID_JSON, _serialize_grid(pairs, attributes, seed))


def _write_json(destination, payload: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, destination)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def save_current_race(name=None, race=None):
    """Grave a corrida enviada (a que a tela mostra) ou, sem ela, a atual.

    Corrida enviada precisa de ``setup`` e ``classification``, o minimo para a
    listagem e a reabertura funcionarem. Sem ``name``, usa o nome padrao.
    """

    if race is None:
        race = _read_current_race()
    elif not isinstance(race, dict) or "setup" not in race or "classification" not in race:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="corrida incompleta: faltam setup ou classification",
        )
    return _persist_saved_race(race, name or _default_race_name(race))


def _read_current_race() -> dict:
    if not CURRENT_RACE_JSON.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no current race; run POST /catalog/grid/run before saving",
        )
    try:
        return json.loads(CURRENT_RACE_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error


def _persist_saved_race(race: dict, name: str) -> dict:
    from datetime import datetime

    race_id = _unique_saved_id(name)
    setup = race.get("setup", {})
    meta = {
        "id": race_id,
        "name": name,
        "saved_at": datetime.now(UTC).isoformat(),
        "seed": race.get("seed"),
        "track_id": setup.get("track_id"),
        "track_name": _track_name(race),
        "total_laps": setup.get("total_laps"),
        "car_count": len(race.get("classification", [])),
    }
    _write_json(SAVED_RACES_DIR / f"{race_id}.json", {"meta": meta, "race": race})
    return meta


def _track_name(race: dict) -> str | None:
    """Nome legivel da pista; sem nome do modelo, o proprio id do circuito.

    O nome do modelo so vale quando ele corresponde ao circuito pedido no setup,
    para nao rotular a corrida com outra pista.
    """

    setup = race.get("setup", {})
    track_id = setup.get("track_id")
    reference = race.get("track_reference")
    if (
        track_id
        and isinstance(reference, dict)
        and reference.get("model_track_name")
        and track_id in (reference.get("requested_track_id"), reference.get("model_track_id"))
    ):
        return str(reference["model_track_name"])
    return track_id


def _default_race_name(race: dict) -> str:
    """Nome de corrida salva sem escolha do usuario: pista e data local."""

    from datetime import datetime

    track = _track_name(race) or "Sem pista"
    stamp = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")
    return f"{track} · {stamp}"


def list_saved_races():
    if not SAVED_RACES_DIR.exists():
        return []
    saved = []
    for path in SAVED_RACES_DIR.glob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            saved.append(document["meta"])
        except (OSError, ValueError, KeyError):
            continue
    saved.sort(key=lambda item: item.get("saved_at", ""), reverse=True)
    return saved


def read_saved_race(race_id):
    path = SAVED_RACES_DIR / f"{_safe_id(race_id)}.json"
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"saved race not found: {race_id}",
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    return document["race"]


def _saved_race_path(race_id: str):
    path = SAVED_RACES_DIR / f"{_safe_id(race_id)}.json"
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"saved race not found: {race_id}",
        )
    return path


def rename_saved_race(race_id: str, name: str) -> dict:
    """Troca o nome da corrida salva; o resto do arquivo fica como estava."""

    if not name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="informe um nome para a corrida",
        )
    path = _saved_race_path(race_id)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["meta"]["name"] = name.strip()
    _write_json(path, document)
    return document["meta"]


def delete_saved_race(race_id: str) -> None:
    _saved_race_path(race_id).unlink()


def _slug(name: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "race"


def _safe_id(race_id: str) -> str:
    # Impede travessia de diretório vinda do id informado pelo cliente.
    import re

    cleaned = re.sub(r"[^a-z0-9-]", "", str(race_id).lower())
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid saved race id",
        )
    return cleaned


def _unique_saved_id(name: str) -> str:
    import secrets

    base = _slug(name)
    SAVED_RACES_DIR.mkdir(parents=True, exist_ok=True)
    return f"{base}-{secrets.token_hex(3)}"


def _new_seed() -> int:
    import secrets

    # 53 bits fit a JSON client's double without losing reproducibility.
    return secrets.randbelow(2**53)
