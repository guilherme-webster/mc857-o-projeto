import subprocess
import sys
import time

import os

os.system("")


class Colors:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RED = "\033[91m"


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

    print(f"{Colors.GREEN}[2/3] Backend inicializado.{Colors.RESET}")
    print(f"      Backend: {Colors.CYAN}http://localhost:8000{Colors.RESET}")
    print(f"      Swagger: {Colors.CYAN}http://localhost:8000/docs{Colors.RESET}")

    logs_process = subprocess.Popen(["docker", "compose", "logs", "-f", "backend"])
    time.sleep(1)

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
