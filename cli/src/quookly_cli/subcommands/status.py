from rich.console import Console
from typer import Typer

from ..di.container import get_container
from ..helpers import coro

try:
    from ..api_client.api.status import get_status as get_status_api
except Exception as e:  # noqa: BLE001 - the client only exists after codegen
    print("Unable to import api client. Did you run the codegen?", e)

cli = Typer(name="status", no_args_is_help=True, help="Check the status of the API server")
console = Console()


@cli.command()
@coro
async def get_status() -> None:
    with get_container().api_client() as client:
        response = await get_status_api.asyncio(client=client)
    if response is None:
        console.print("[red]Quookly API is unreachable or returned no status.[/red]")
        raise SystemExit(1)
    console.print(f"Quookly API status: [green]{response.status}[/green]")
