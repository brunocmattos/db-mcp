from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from .config import Settings
from .observability import configurar_logging
from .server import construir_servidor

if TYPE_CHECKING:
    from fastmcp import FastMCP


def montar(
    env_file: str | None = ".env", yaml_file: str = "config.yaml", conectar: bool = True
) -> FastMCP:
    s = Settings.load(env_file=env_file, yaml_file=yaml_file)
    configurar_logging(s.log_level)
    return construir_servidor(s, conectar=conectar)


def main() -> None:
    parser = argparse.ArgumentParser(prog="db-mcp")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--env", default=".env")
    parser.add_argument(
        "--dialect",
        choices=["postgres", "mysql", "sqlserver"],
        default=None,
        help="sobrescreve o dialeto da config",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_doc = sub.add_parser("doctor", help="checagens de saúde/preflight")
    p_doc.add_argument("--color", choices=["auto", "always", "never"], default="auto")

    sub.add_parser("run", help="sobe o servidor MCP (padrão)")

    args = parser.parse_args()

    if args.cmd == "doctor":
        from .doctor import executar_doctor

        # O doctor carrega o Settings por conta própria, então o --dialect precisa ser
        # propagado explicitamente. Enquanto só `postgres` resolvia isso era inofensivo;
        # com o MySQL registrado, a flag passaria a MENTIR em silêncio (rodaria as 6
        # checagens contra o dialeto errado e diria que está tudo bem).
        raise SystemExit(executar_doctor(args.env, args.config, args.color, args.dialect))

    # default (sem subcomando) e "run": sobe o servidor (comportamento da Fase 1)
    s = Settings.load(env_file=args.env, yaml_file=args.config)
    if args.dialect:
        s.dialeto = args.dialect
    configurar_logging(s.log_level)
    # Fail-closed: HTTP sem token ficaria sem autenticação. Exige AUTH_TOKEN.
    if s.transport == "http" and not s.auth_token:
        raise SystemExit(
            "TRANSPORT=http exige AUTH_TOKEN (defina no .env). Sem token o endpoint HTTP "
            "ficaria aberto; use stdio ou configure um AUTH_TOKEN."
        )
    mcp = construir_servidor(s)
    if s.transport == "http":
        mcp.run(transport="http", host=s.http_host, port=s.http_port)
    else:
        mcp.run()  # stdio


if __name__ == "__main__":
    main()
