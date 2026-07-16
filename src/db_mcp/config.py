from __future__ import annotations

from contextvars import ContextVar
from typing import Literal

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# Qual config.yaml o load() atual está usando. É um ContextVar (não um atributo de
# classe) pra que `load()` não mute estado global: cada chamada seta o seu valor e
# o reseta no fim, e chamadas concorrentes não se atropelam.
_yaml_file_atual: ContextVar[str] = ContextVar("db_mcp_yaml_file", default="config.yaml")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    # --- conexão / segredos (via .env / env vars) ---
    pg_host: str
    pg_port: int = 5432
    pg_dbname: str
    pg_user: str = "mcp_ro"
    pg_password: str
    pg_sslmode: str = "prefer"
    auth_token: str | None = None

    # --- ajustes (via config.yaml, com env como override) ---
    transport: Literal["stdio", "http"] = "stdio"
    http_host: str = "127.0.0.1"
    http_port: int = 8080
    allowlist: list[str] = Field(default_factory=lambda: ["*"])
    allow_freeform_sql: bool = True
    max_rows: int = 1000
    max_result_bytes: int = 1_000_000
    statement_timeout_ms: int = 5000
    rate_limit_per_min: int = 60
    pool_min: int = 1
    pool_max: int = 5
    log_level: str = "INFO"
    audit_log_path: str = "./audit.log"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Prioridade: init > env > .env > config.yaml
        yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=_yaml_file_atual.get())
        return (init_settings, env_settings, dotenv_settings, yaml_source)

    @classmethod
    def load(cls, env_file: str | None = ".env", yaml_file: str = "config.yaml") -> Settings:
        # `_env_file` é kwarg nativo do BaseSettings (por instância); o yaml vai pelo
        # ContextVar. Nada disso muta model_config, então loads não se contaminam.
        token = _yaml_file_atual.set(yaml_file)
        try:
            return cls(_env_file=env_file)  # type: ignore[call-arg]
        finally:
            _yaml_file_atual.reset(token)
