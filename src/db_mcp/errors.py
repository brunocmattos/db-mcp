class McpDbError(Exception):
    """Erro tratado do MCP. Cada subclasse tem um `codigo` estável."""

    codigo = "erro"


class SqlInvalido(McpDbError):
    codigo = "sql_invalido"


class SomenteLeitura(McpDbError):
    codigo = "somente_leitura"


class ForaDaAllowlist(McpDbError):
    codigo = "fora_da_allowlist"


class LimiteDeTaxa(McpDbError):
    codigo = "limite_de_taxa"


class ResultadoGrandeDemais(McpDbError):
    codigo = "resultado_grande_demais"


class ConsultaTimeout(McpDbError):
    codigo = "timeout"


class ErroBanco(McpDbError):
    """Qualquer outro erro vindo do PostgreSQL (tabela/coluna inexistente, etc.)."""

    codigo = "erro_banco"
