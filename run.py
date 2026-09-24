import subprocess
import sys
import time
import urllib.error
import urllib.request

import os

os.system("")

BACKEND_URL = "http://localhost:8000"
BACKEND_START_ATTEMPTS = 60
BACKEND_RETRY_INTERVAL_SECONDS = 0.25


class Colors:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RED = "\033[91m"


def wait_for_backend(
    attempts: int = BACKEND_START_ATTEMPTS,
    retry_interval: float = BACKEND_RETRY_INTERVAL_SECONDS,
) -> bool:
    """Wait until FastAPI answers instead of racing the Arcade startup."""

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


def start_system():
    print(
        f"{Colors.BLUE}[1/3] Subindo container (baixa dataset e gera catalogo no boot)..."
        f"{Colors.RESET}"
    )
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print(
            f"{Colors.RED}Erro ao iniciar o Docker. O Docker esta em execucao?{Colors.RESET}"
        )
        sys.exit(1)

    logs_process = subprocess.Popen(["docker", "compose", "logs", "-f", "backend"])
    print(f"{Colors.YELLOW}[2/3] Aguardando o backend ficar pronto...{Colors.RESET}")
    if not wait_for_backend():
        if logs_process.poll() is None:
            logs_process.terminate()
        subprocess.run(
            ["docker", "compose", "down"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(
            f"{Colors.RED}O backend não respondeu em {BACKEND_URL}. "
            f"Consulte os logs acima.{Colors.RESET}"
        )
        sys.exit(1)

    print(f"{Colors.GREEN}[2/3] Backend inicializado.{Colors.RESET}")
    print(f"      Backend: {Colors.CYAN}{BACKEND_URL}{Colors.RESET}")
    print(f"      Swagger: {Colors.CYAN}{BACKEND_URL}/docs{Colors.RESET}")

    print(f"{Colors.GREEN}[3/3] Iniciando o frontend Arcade...{Colors.RESET}")
    try:
        subprocess.run(["uv", "run", "python", "-m", "frontend.arcade"], check=True)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Encerrando aplicacao...{Colors.RESET}")
    except subprocess.CalledProcessError as exc:
        print(
            f"\n{Colors.RED}Frontend encerrou com erro (codigo {exc.returncode})."
            f"{Colors.RESET}"
        )
    finally:
        if logs_process.poll() is None:
            logs_process.terminate()
        print(f"{Colors.YELLOW}Parando containers...{Colors.RESET}")
        subprocess.run(
            ["docker", "compose", "down"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    start_system()
