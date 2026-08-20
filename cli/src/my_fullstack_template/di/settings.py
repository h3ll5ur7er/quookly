
from pydantic_settings import BaseSettings

class ApiSettings(BaseSettings):
    base_url: str = "http://localhost:8000"
    
class Settings(BaseSettings):
    api: ApiSettings = ApiSettings()