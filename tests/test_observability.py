import json
import threading

from pg_readonly_mcp.observability import Auditoria


def test_grava_linha_json(tmp_path):
    caminho = tmp_path / "audit.log"
    aud = Auditoria(str(caminho))
    aud.registrar(cliente="cli", sql="SELECT 1", linhas=1, ms=12, veredito="ok")
    linha = json.loads(caminho.read_text(encoding="utf-8").strip())
    assert linha["cliente"] == "cli"
    assert linha["linhas"] == 1
    assert linha["veredito"] == "ok"
    assert "ts" in linha


def test_escritas_concorrentes_nao_corrompem(tmp_path):
    aud = Auditoria(str(tmp_path / "audit.log"))

    def worker(n: int) -> None:
        for i in range(50):
            aud.registrar(cliente=f"c{n}", sql="SELECT 1", linhas=i, ms=1.0, veredito="ok")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    linhas = (tmp_path / "audit.log").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 20 * 50  # nenhuma escrita perdida
    for linha in linhas:
        json.loads(linha)  # nenhuma linha intercalada/corrompida
