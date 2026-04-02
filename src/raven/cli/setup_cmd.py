from __future__ import annotations

import getpass
import logging
import os
import shutil
import subprocess
from pathlib import Path

import typer
from rich.panel import Panel
from rich.text import Text

from raven.util.console import console

log = logging.getLogger(__name__)


def _check_dependencies() -> bool:
    """Checks for presence and version of required binaries."""
    console.print("[bold]1. Checking dependencies...[/bold]")
    from rich.table import Table
    table = Table(show_header=False, box=None)
    table.add_column("Dependency", style="cyan")
    table.add_column("Status")

    all_ok = True
    deps = ["nft", "nsenter", "systemd"]

    # Check podman separately for version
    podman_path = shutil.which("podman")
    if podman_path:
        try:
            # Using subprocess.run to capture output
            result = subprocess.run(["podman", "--version"], capture_output=True, text=True, check=True)
            version_str = result.stdout.strip().split(" ")[2]
            major, minor, *_ = map(int, version_str.split("."))
            if major > 4 or (major == 4 and minor >= 4):
                table.add_row("podman (>= 4.4)", f"[green]✓ Found at {podman_path} (version {version_str})[/green]")
            else:
                table.add_row("podman (>= 4.4)", f"[red]✗ Found, but version {version_str} is too old.[/red]")
                all_ok = False
        except (subprocess.CalledProcessError, IndexError, ValueError) as e:
            table.add_row("podman (>= 4.4)", f"[red]✗ Found, but could not parse version: {e}[/red]")
            all_ok = False
    else:
        table.add_row("podman (>= 4.4)", "[red]✗ Not found in PATH.[/red]")
        all_ok = False

    # Check other dependencies
    for dep in deps:
        path = shutil.which(dep)
        if path:
            table.add_row(dep, f"[green]✓ Found at {path}[/green]")
        else:
            table.add_row(dep, "[red]✗ Not found in PATH.[/red]")
            all_ok = False

    console.print(table)
    console.print()
    return all_ok


def _setup_sudoers() -> bool:
    """Checks for and offers to install the sudoers file for the nft helper."""
    console.print("[bold]2. Checking sudoers configuration...[/bold]")
    user = getpass.getuser()
    helper_path = "/usr/local/bin/raven-nft-helper"  # As specified in GEMINI.md
    sudoers_file = Path("/etc/sudoers.d/raven")

    sudo_lines = [
        f"{user} ALL=(root) NOPASSWD: {helper_path} apply *",
        f"{user} ALL=(root) NOPASSWD: {helper_path} delete *",
    ]
    content = "\n".join(sudo_lines) + "\n"

    panel_content = Text("Raven requires sudo privileges to manage network rules inside the container.\n", justify="center")
    panel_content.append(f"The following lines will be added to [cyan]{sudoers_file}[/cyan]:\n\n")
    sudoers_text = "\n".join(sudo_lines)
    panel_content.append(f'[yellow]{sudoers_text}[/yellow]')

    console.print(Panel(
        panel_content,
        title="[bold yellow]Sudoers Configuration[/bold yellow]",
        border_style="yellow",
        padding=(1, 2)
    ))

    if sudoers_file.exists():
        console.print(f"[yellow]Note: {sudoers_file} already exists. This will overwrite it.[/yellow]")

    confirmed = typer.confirm(f"Do you want to write this configuration to {sudoers_file}?", default=True)

    if confirmed:
        try:
            command = ["sudo", "tee", str(sudoers_file)]
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = proc.communicate(content)

            if proc.returncode == 0:
                console.print(f"[green]✓ Sudoers file created at {sudoers_file}.[/green]")
                console.print()
                return True
            else:
                console.print("[red]✗ Failed to write sudoers file.[/red]")
                console.print(f"[red]  Stdout: {stdout.strip()}[/red]")
                console.print(f"[red]  Stderr: {stderr.strip()}[/red]")
                console.print()
                return False

        except Exception as e:
            console.print(f"[red]✗ An unexpected error occurred: {e}[/red]")
            console.print()
            return False
    else:
        console.print("Skipping sudoers configuration. Raven network commands may not work.")
        console.print()
        return False


def _setup_linger() -> bool:
    """Checks if linger is enabled for the user and offers to enable it."""
    console.print("[bold]3. Checking user linger status...[/bold]")
    user = getpass.getuser()
    try:
        result = subprocess.run(
            ["loginctl", "show-user", user, "--property=Linger"],
            capture_output=True, text=True, check=True
        )
        status = result.stdout.strip()
        if status == "Linger=yes":
            console.print("[green]✓ User linger is already enabled.[/green]")
            console.print()
            return True
        else:
            console.print("[yellow]User linger is disabled. This is required to keep environments running after you log out.[/yellow]")
            confirmed = typer.confirm(f"Do you want to enable linger for user '{user}'?", default=True)
            if confirmed:
                enable_result = subprocess.run(
                    ["sudo", "loginctl", "enable-linger", user],
                    capture_output=True, text=True
                )
                if enable_result.returncode == 0:
                    console.print(f"[green]✓ Successfully enabled linger for user '{user}'.[/green]")
                    console.print()
                    return True
                else:
                    console.print(f"[red]✗ Failed to enable linger: {enable_result.stderr.strip()}[/red]")
                    console.print()
                    return False
            else:
                console.print("Skipping linger setup. Environments will be stopped on logout.")
                console.print()
                return False
    except FileNotFoundError:
        console.print("[yellow]Could not find 'loginctl'. Skipping linger check. (This is expected on non-systemd systems)[/yellow]")
        console.print()
        return True  # Not a failure, just not applicable.
    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗ Failed to check linger status: {e.stderr.strip()}[/red]")
        console.print()
        return False


def _get_shell_rc_file() -> Path | None:
    """Detects the user's shell and returns the path to its rc file."""
    shell = os.environ.get("SHELL", "")
    if "bash" in shell:
        return Path.home() / ".bashrc"
    elif "zsh" in shell:
        return Path.home() / ".zshrc"
    elif "fish" in shell:
        return Path.home() / ".config" / "fish" / "config.fish"
    return None


def _setup_path() -> bool:
    """Checks if ~/.local/bin is in PATH and offers to add it."""
    console.print("[bold]4. Checking PATH configuration...[/bold]")
    local_bin = Path.home() / ".local" / "bin"
    path_var = os.environ.get("PATH", "")

    if str(local_bin) in path_var.split(os.pathsep):
        console.print(f"[green]✓ Your PATH includes {local_bin}.[/green]")
        console.print()
        return True
    else:
        console.print(f"[yellow]Your PATH does not seem to include {local_bin}.[/yellow]")
        console.print("This is needed to run binaries installed by user-level package managers (like `pipx` or `uv`).")

        rc_file = _get_shell_rc_file()
        if not rc_file:
            console.print(f"[red]Could not detect your shell's configuration file. Please add {local_bin} to your PATH manually.[/red]")
            console.print()
            return False

        if "fish" in str(rc_file):
            export_line = f'\nfish_add_path "{local_bin}"\n'
        else:
            export_line = f'\nexport PATH="{local_bin}:$PATH"\n'

        console.print(f"I can add it to your [cyan]{rc_file}[/cyan] file.")
        confirmed = typer.confirm("Do you want me to append the necessary line?", default=True)

        if confirmed:
            try:
                with open(rc_file, "a") as f:
                    f.write(export_line)
                console.print(f"[green]✓ Successfully appended to {rc_file}. Please restart your shell for changes to take effect.[/green]")
                console.print()
                return True
            except IOError as e:
                console.print(f"[red]✗ Failed to write to {rc_file}: {e}[/red]")
                console.print()
                return False
        else:
            console.print(f"Skipping PATH modification. Please add {local_bin} to your PATH manually.")
            console.print()
            return False


def setup() -> None:
    """
    Checks for required dependencies and guides the user through first-time setup.
    """
    console.rule("[bold green]Raven Environment Setup[/bold green]")
    console.print("This tool will check for dependencies and help you configure your system.")
    console.print()

    # Step 1: Dependency checks
    deps_ok = _check_dependencies()

    # Step 2: Sudoers configuration
    sudo_ok = _setup_sudoers()

    # Step 3: Linger configuration
    linger_ok = _setup_linger()

    # Step 4: PATH configuration
    path_ok = _setup_path()

    console.print()
    if all([deps_ok, sudo_ok, linger_ok, path_ok]):
        console.print("[bold green]✅ Your system is configured correctly for Raven![/bold green]")
        raise typer.Exit(0)
    else:
        console.print("[bold yellow]⚠️ Some manual configuration steps are still required. Please review the output above.[/bold yellow]")
        raise typer.Exit(1)
