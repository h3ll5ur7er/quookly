from typer import Typer
from .subcommands import status_cli, codegen_cli

app = Typer(no_args_is_help=True)
app.add_typer(status_cli, name="status", help="Check the status of the API server")
app.add_typer(codegen_cli, name="codegen", help="Generate API client code from the OpenAPI specification")
def main():
    app()