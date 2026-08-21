from typer import Typer

from .subcommands import codegen_cli, inference_cli, status_cli

app = Typer(no_args_is_help=True)
app.add_typer(status_cli, name="status", help="Check the status of the API server")
app.add_typer(inference_cli, name="inference", help="Check the model this instance is pointed at")
app.add_typer(
    codegen_cli,
    name="codegen",
    help="Generate API client code from the OpenAPI specification",
)


def main() -> None:
    app()
