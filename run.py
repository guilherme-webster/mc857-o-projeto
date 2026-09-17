import os
import subprocess
import sys
import time

os.system("")


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RED = "\033[91m"

def download_trotman_dataset():

    print(
        f"{Colors.BLUE}[1/5] Baixando dataset bruto do Trotman "
        f"(formula-1-race-data-v128.zip)...{Colors.RESET}"
    )
    try:
        subprocess.run(
            [sys.executable, "scripts/download_trotman.py"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"{Colors.GREEN}      Dataset bruto disponivel.{Colors.RESET}")
    except subprocess.CalledProcessError:
        print(
            f"{Colors.YELLOW}      Nao foi possivel baixar o dataset bruto. "
            f"O catalogo de corridas pode ficar vazio.{Colors.RESET}"
        )


def generate_race_catalog():

    print(
        f"{Colors.BLUE}[2/5] Gerando catalogo de corridas (races-index.json)...{Colors.RESET}"
    )
    try:
        subprocess.run(
            [sys.executable, "scripts/list_races.py"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"{Colors.GREEN}      Catalogo de corridas gerado.{Colors.RESET}")
    except subprocess.CalledProcessError:
        print(
            f"{Colors.YELLOW}      Nao foi possivel gerar o catalogo "
            f"(arquivo bruto ausente?). A lista de corridas ficara vazia."
            f"{Colors.RESET}"
        )


def start_system():
    download_trotman_dataset()
    generate_race_catalog()

    print(
        f"{Colors.BLUE}[3/5] Subindo containers Docker (Backend)...{Colors.RESET}")
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print(
            f"{Colors.RED}Erro ao iniciar containers Docker. Verifique se o Docker esta em execucao.{Colors.RESET}"
        )
        sys.exit(1)

    print(f"{Colors.GREEN}[4/5] Backend inicializado.{Colors.RESET}")
    print(
        f"      Backend pronto: {Colors.CYAN}http://localhost:8000{Colors.RESET}")
    print(
        f"      Swagger Docs:   {Colors.CYAN}http://localhost:8000/docs{Colors.RESET}")

    logs_process = subprocess.Popen(
        ["docker", "compose", "logs", "-f", "backend"])

    time.sleep(1)

    print(f"{Colors.GREEN}[5/5] Iniciando o frontend Arcade...{Colors.RESET}")
    try:
        subprocess.run(
            ["uv", "run", "python", "-m", "frontend.arcade"],
            check=True,
        )
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Encerrando aplicacao...{Colors.RESET}")
    except subprocess.CalledProcessError as exc:
        print(
            f"\n{Colors.RED}Frontend encerrou com erro (codigo {exc.returncode}).{Colors.RESET}"
        )
    finally:
        print(f"{Colors.YELLOW}Encerrando captura de logs...{Colors.RESET}")
        if logs_process.poll() is None:
            logs_process.terminate()

        print(f"{Colors.YELLOW}Parando containers Docker...{Colors.RESET}")
        subprocess.run(
            ["docker", "compose", "down"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    start_system()
