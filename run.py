import subprocess
import sys
import time


def start_system():
    print("[1/3] Subindo containers Docker (Backend)...")
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print(
            "Erro ao iniciar containers Docker. Verifique se o Docker está em execução."
        )
        sys.exit(1)

    print("[2/3] Aguardando o backend inicializar...")
    print("      Backend pronto: http://localhost:8000")
    print("      Swagger Docs:  http://localhost:8000/docs")

    print("[3/3] Iniciando o frontend Arcade...")
    try:
        subprocess.run(
            ["uv", "run", "python", "-m", "frontend.arcade"],
            check=True,
        )
    except KeyboardInterrupt:
        print("\nEncerrando aplicacao...")
    except subprocess.CalledProcessError as e:
        print(f"\nFrontend encerrou com erro (codigo {e.returncode}).")
    finally:
        print("Parando containers Docker...")
        subprocess.run(
            ["docker", "compose", "down"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    start_system()
