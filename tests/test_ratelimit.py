import threading

from pg_readonly_mcp.guardrails.ratelimit import RateLimiter


def test_estoura_e_recupera_com_o_tempo():
    rl = RateLimiter(por_minuto=2)
    t = 1000.0
    assert rl.permitir("cli", agora=t) is True
    assert rl.permitir("cli", agora=t) is True
    assert rl.permitir("cli", agora=t) is False  # estourou (2/min)
    assert rl.permitir("cli", agora=t + 30) is True  # +30s = +1 ficha
    assert rl.permitir("outro", agora=t) is True  # balde por cliente


def test_concorrencia_nao_estoura_a_capacidade():
    # Num instante fixo (sem reabastecimento), só existem `por_minuto` fichas.
    # Com várias threads disputando, o lock garante que nem uma a mais seja concedida.
    rl = RateLimiter(por_minuto=100)
    agora = 5000.0
    concedidas = 0
    contagem_lock = threading.Lock()

    def worker() -> None:
        nonlocal concedidas
        for _ in range(50):
            if rl.permitir("c", agora=agora):
                with contagem_lock:
                    concedidas += 1

    threads = [threading.Thread(target=worker) for _ in range(10)]  # 500 tentativas
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert concedidas == 100
