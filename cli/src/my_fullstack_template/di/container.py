from dependency_injector import containers, providers
from .settings import Settings
try:
    from ..api_client import Client
except (Exception) as e:
    print("Unable to import api client. Did you run the codegen?", e)

class AppContainer(containers.DeclarativeContainer):
    config = providers.Configuration(pydantic_settings=[Settings()])

    wiring_config = containers.WiringConfiguration(modules=[".."])
    try:
        api_client = providers.Singleton(
            Client,
            base_url=config.api.base_url,
        )
    except (Exception) as e:
        print("Unable to import api client. Did you run the codegen?", e)

_container = AppContainer()
def get_container() -> AppContainer:
    global _container
    if _container is None:
        _container = AppContainer()
    return _container