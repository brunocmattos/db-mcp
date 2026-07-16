from db_mcp.errors import (
    ConsultaTimeout,
    ErroBanco,
    ForaDaAllowlist,
    LimiteDeTaxa,
    McpDbError,
    ResultadoGrandeDemais,
    SomenteLeitura,
    SqlInvalido,
)


def test_todos_herdam_da_base_e_tem_codigo():
    for cls in (
        SqlInvalido,
        SomenteLeitura,
        ForaDaAllowlist,
        LimiteDeTaxa,
        ResultadoGrandeDemais,
        ConsultaTimeout,
        ErroBanco,
    ):
        err = cls("mensagem")
        assert isinstance(err, McpDbError)
        assert isinstance(err.codigo, str) and err.codigo
        assert str(err) == "mensagem"
