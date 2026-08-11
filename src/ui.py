from rich.console import Console
from rich.panel import Panel

console = Console()

def show_welcome():
    console.print(
        Panel(
            "Welcome Sparker",
            title="Jaswanth's Agent"
        )
    )