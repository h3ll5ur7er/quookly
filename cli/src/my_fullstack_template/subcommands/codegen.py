from typer import Typer
from openapi_python_client.cli import app
cli = Typer(name="codegen", no_args_is_help=True, help="Generate API client code from the OpenAPI specification")
cli.add_typer(app, name="openapi", help="Generate API client code from the OpenAPI specification using openapi-python-client")