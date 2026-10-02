"""Sobe o backend em Docker e o frontend conforme o ambiente grafico do host."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

os.system("")

BACKEND_URL = "http://localhost:8000"
BACKEND_START_ATTEMPTS = 240
BACKEND_RETRY_INTERVAL_SECONDS = 0.5

PROJECT_ROOT = Path(__file__).resolve().parent
XAUTH_PATH = Path(tempfile.gettempdir()) / "f1-sim-docker.xauth"


class Colors:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RED = "\033[91m"


def info(message: str) -> None:
    print(f"{Colors.BLUE}{message}{Colors.RESET}")


def ok(message: str) -> None:
    print(f"{Colors.GREEN}{message}{Colors.RESET}")


def warn(message: str) -> None:
    print(f"{Colors.YELLOW}{message}{Colors.RESET}")


def fail(message: str) -> None:
    print(f"{Colors.RED}{message}{Colors.RESET}")


def running_in_wsl() -> bool:
    if platform.system() != "Linux":
        return False
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def wslg_available() -> bool:
    return running_in_wsl() and Path("/mnt/wslg").exists()


def check_docker() -> None:
    if shutil.which("docker") is None:
        fail("Docker nao encontrado no PATH. Instale o Docker e tente novamente.")
        sys.exit(1)
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        fail("Docker Compose indisponivel. Verifique a instalacao do Docker.")
        sys.exit(1)
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        fail("Docker nao esta em execucao. Inicie o Docker e tente novamente.")
        sys.exit(1)


def prepare_linux_display(env: dict[str, str]) -> None:
    display = os.environ.get("DISPLAY", ":0")
    env["DISPLAY"] = display
    env["F1_XAUTHORITY"] = str(XAUTH_PATH)
    get_uid = getattr(os, "getuid", None)
    get_gid = getattr(os, "getgid", None)
    if get_uid and get_gid:
        env.setdefault("LOCAL_UID", str(get_uid()))
        env.setdefault("LOCAL_GID", str(get_gid()))

    if shutil.which("xauth") is None:
        warn(
            "xauth nao encontrado. O container tentara acessar o display sem "
            "cookie dedicado; instale xauth se a janela nao abrir."
        )
        XAUTH_PATH.touch(mode=0o600, exist_ok=True)
        return

    XAUTH_PATH.unlink(missing_ok=True)
    XAUTH_PATH.touch(mode=0o600)
    try:
        listing = subprocess.run(
            ["xauth", "nlist", display],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError:
        warn(
            f"Nao foi possivel ler cookies X11 para DISPLAY={display}. "
            "Confirme que ha uma sessao grafica ativa."
        )
        return
    patched = "".join(
        f"ffff{line[4:]}\n" for line in listing.splitlines() if line
    )
    subprocess.run(
        ["xauth", "-f", str(XAUTH_PATH), "nmerge", "-"],
        input=patched,
        text=True,
        check=False,
    )


def resolve_frontend_mode() -> tuple[str, str, dict[str, str]]:
    """Return (mode, profile, extra_env) for the current host.

    ``mode`` is ``container`` quando o frontend roda em Docker (Linux e WSLg) ou
    ``host`` quando a janela Arcade deve ser aberta localmente (Windows nativo e
    WSL sem WSLg), caso em que ``profile`` fica vazio.
    """

    env: dict[str, str] = {}
    system = platform.system()

    if system == "Linux" and not running_in_wsl():
        prepare_linux_display(env)
        return "container", "linux", env

    if wslg_available():
        env["DISPLAY"] = os.environ.get("DISPLAY", ":0")
        return "container", "wslg", env

    return "host", "", env


def wait_for_backend(
    attempts: int = BACKEND_START_ATTEMPTS,
    retry_interval: float = BACKEND_RETRY_INTERVAL_SECONDS,
) -> bool:
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(BACKEND_URL, timeout=1) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            pass
        if attempt < attempts - 1:
            time.sleep(retry_interval)
    return False


def compose(args: list[str], env: dict[str, str], **kwargs):
    merged = {**os.environ, **env}
    return subprocess.run(["docker", "compose", *args], env=merged, **kwargs)


def run_frontend_container(profile: str, env: dict[str, str]) -> None:
    service = f"frontend-{profile}"
    ok(f"[4/4] Iniciando o frontend Arcade em container (perfil '{profile}')...")
    compose(["--profile", profile, "up", "--build", service], env, check=True)


def run_frontend_host() -> None:
    if shutil.which("uv") is None:
        fail(
            "uv nao encontrado. No Windows nativo, o frontend roda localmente e "
            "depende do uv:\n"
            "  - Windows (PowerShell/WinGet): winget install astral-sh.uv\n"
            "  - ou veja https://docs.astral.sh/uv/getting-started/installation/\n"
            "Depois rode novamente python run.py."
        )
        sys.exit(1)

    ok("[4/4] Iniciando o frontend Arcade localmente...")
    info("      Sincronizando o ambiente com uv sync...")
    subprocess.run(["uv", "sync"], check=True)
    env = {**os.environ, "F1_API_BASE_URL": BACKEND_URL}
    subprocess.run(
        ["uv", "run", "python", "-m", "frontend.arcade"],
        check=True,
        env=env,
    )


def start_system() -> None:
    check_docker()

    mode, profile, extra_env = resolve_frontend_mode()
    env = dict(extra_env)
    if mode == "container":
        env["COMPOSE_PROFILES"] = profile
        ok(f"[1/4] Frontend em container (perfil '{profile}').")
    else:
        ok("[1/4] Frontend local; backend em container.")

    info("[2/4] Construindo imagem do backend...")
    try:
        compose(["build", "backend"], env, check=True)
    except subprocess.CalledProcessError:
        fail("Falha ao construir a imagem do backend.")
        sys.exit(1)

    info("      Subindo o backend...")
    try:
        compose(
            ["up", "-d", "backend"],
            env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        fail("Falha ao subir o backend. Verifique os logs do Docker.")
        sys.exit(1)

    logs_process = subprocess.Popen(
        ["docker", "compose", "logs", "-f", "backend"],
        env={**os.environ, **env},
    )
    warn("[3/4] Aguardando o backend ficar pronto...")
    if not wait_for_backend():
        if logs_process.poll() is None:
            logs_process.terminate()
        compose(["down"], env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        fail(f"O backend nao respondeu em {BACKEND_URL}. Consulte os logs acima.")
        sys.exit(1)

    if logs_process.poll() is None:
        logs_process.terminate()
    ok("[3/4] Backend inicializado.")
    print(f"      Backend: {Colors.CYAN}{BACKEND_URL}{Colors.RESET}")
    print(f"      Swagger: {Colors.CYAN}{BACKEND_URL}/docs{Colors.RESET}")

    try:
        if mode == "container":
            run_frontend_container(profile, env)
        else:
            run_frontend_host()
    except KeyboardInterrupt:
        warn("\nEncerrando aplicacao...")
    except subprocess.CalledProcessError as exc:
        fail(f"\nO frontend encerrou com erro (codigo {exc.returncode}).")
    finally:
        warn("Parando containers...")
        compose(["down"], env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if XAUTH_PATH.exists():
            XAUTH_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    start_system()
