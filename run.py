import os
import shutil
import subprocess
import sys
import time


def ensure_uv():
    """Garante que o executável uv esteja disponível no sistema."""
    if shutil.which("uv") is not None:
        return

    print("⚠️  'uv' não foi encontrado. Instalando automaticamente...")
    try:
        if os.name == "nt":  # Windows
            cmd = "irm https://astral.sh/uv/install.ps1 | iex"
            subprocess.run(
                ["powershell", "-ExecutionPolicy", "ByPass", "-Command", cmd],
                check=True,
            )

            # Locais padrão de instalação do uv no Windows
            local_bin = os.path.expandvars(r"%USERPROFILE%\.local\bin")
            cargo_bin = os.path.expandvars(r"%USERPROFILE%\.cargo\bin")
            appdata_bin = os.path.expandvars(r"%APPDATA%\uv\bin")
            for path in (local_bin, cargo_bin, appdata_bin):
                if os.path.exists(path):
                    os.environ["PATH"] = path + os.pathsep + \
                        os.environ.get("PATH", "")
        else:  # Linux / macOS / WSL
            cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"
            subprocess.run(cmd, shell=True, check=True)

            local_bin = os.path.expanduser("~/.local/bin")
            cargo_bin = os.path.expanduser("~/.cargo/bin")
            for path in (local_bin, cargo_bin):
                if os.path.exists(path):
                    os.environ["PATH"] = path + os.pathsep + \
                        os.environ.get("PATH", "")

        # Validação final no PATH da sessão
        if shutil.which("uv") is None:
            raise FileNotFoundError(
                "Binário uv instalado, mas não localizado no PATH.")

        print("✅ 'uv' instalado com sucesso!")

    except Exception as e:
        print(f"❌ Falha ao instalar o 'uv' automaticamente: {e}")
        print(
            "Instale manualmente: https://docs.astral.sh/uv/getting-started/installation/")
        sys.exit(1)


def start_system():
    ensure_uv()

    print("📦 [1/3] Subindo Docker (Banco, ETL e Django)...")
    try:
        subprocess.run(["docker", "compose", "up",
                       "-d", "--build"], check=True)
    except subprocess.CalledProcessError:
        print("❌ Erro ao iniciar contêineres Docker. Verifique se o Docker Desktop está aberto.")
        sys.exit(1)

    print("⏳ [2/3] Aguardando o backend estar pronto...")
    time.sleep(3)

    print("🏎️ [3/3] Abrindo Arcade nativo...")
    try:
        subprocess.run(
            ["uv", "run", "--project", "frontend", "-m", "frontend.arcade"],
            check=True,
        )
    except KeyboardInterrupt:
        print("\n🛑 Encerrando aplicação a pedido do usuário...")
    finally:
        print("🧹 Parando contêineres do backend...")
        subprocess.run(["docker", "compose", "down"])


if __name__ == "__main__":
    start_system()
