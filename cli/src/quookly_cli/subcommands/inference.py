"""What model this instance is pointed at, and whether it answers (UC-8.2).

An operator's diagnostic, run on the machine the instance runs on at the moment something
is wrong. What it must never do is fail in a way that looks like the thing it is
diagnosing: an unreachable Quookly and an unreachable model are two different machines to
go and look at, and conflating them sends somebody to the wrong one.
"""

from typing import Annotated

import httpx
from rich.console import Console
from typer import Option, Typer

from ..di.container import get_container
from ..helpers import coro

try:
    from ..api_client import AuthenticatedClient
    from ..api_client.api.instance import get_inference_status as get_inference_status_api
except Exception as e:  # noqa: BLE001 - the client only exists after codegen
    print("Unable to import api client. Did you run the codegen?", e)

cli = Typer(
    name="inference",
    no_args_is_help=True,
    help="Check the model this instance is pointed at",
)
console = Console()


@cli.command()
@coro
async def status(
    token: Annotated[
        str,
        Option(
            envvar="QUOOKLY_TOKEN",
            help="An administrator's token. Sign in through the app to get one.",
        ),
    ] = "",
) -> None:
    """Report the configured inference provider and whether it is answering."""
    if not token:
        # Said plainly rather than sent to collect a 403. The endpoint is administrators
        # only because it names an address on the operator's own network.
        console.print(
            "[red]An administrator's token is needed.[/red] "
            "Pass [bold]--token[/bold] or set [bold]QUOOKLY_TOKEN[/bold]."
        )
        raise SystemExit(1)

    base_url = get_container().config.api.base_url()
    try:
        async with AuthenticatedClient(base_url=base_url, token=token) as client:
            found = await get_inference_status_api.asyncio(client=client)
    except httpx.HTTPError as unreachable:
        # A diagnostic that answers an unreachable server with a stack trace has told the
        # operator nothing except that something else is also broken.
        found = None
        console.print(f"[dim]{unreachable}[/dim]")

    if found is None:
        console.print(
            f"[red]Quookly itself is unreachable at {base_url}[/red] — "
            "which is a different thing from the model being unreachable."
        )
        raise SystemExit(1)

    if not found.configured:
        # The API's own words, which name the settings to set. Printing a headline as well
        # would say the same thing twice.
        console.print(f"[yellow]{found.detail or 'No inference provider is configured.'}[/yellow]")
        console.print(
            "\nWithout one this instance cannot read a page that publishes no recipe "
            "data. Everything else still works."
        )
        raise SystemExit(1)

    console.print(f"Provider: [bold]{found.base_url}[/bold]")
    console.print(f"Model:    [bold]{found.model}[/bold]")
    console.print(f"Key:      {'set' if found.authenticated else 'none (a local provider)'}")

    if found.reachable:
        console.print("Status:   [green]reachable[/green]")
        return

    console.print("Status:   [red]not answering[/red]")
    if found.detail:
        console.print(f"          {found.detail}")
    raise SystemExit(1)
