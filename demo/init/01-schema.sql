-- Schema da demonstração. Roda automaticamente na primeira subida do container
-- (Postgres executa os arquivos de /docker-entrypoint-initdb.d em ordem).
-- Nada aqui é dado real — é só o suficiente pra ver o MCP respondendo.

CREATE TABLE clientes (
    id         integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    nome       text NOT NULL,
    email      text NOT NULL UNIQUE,
    cidade     text NOT NULL,
    criado_em  date NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE pedidos (
    id          integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    cliente_id  integer NOT NULL REFERENCES clientes (id),
    valor       numeric(10, 2) NOT NULL,
    status      text NOT NULL DEFAULT 'aberto',
    criado_em   date NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE usuarios (
    id     integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    login  text NOT NULL UNIQUE,
    papel  text NOT NULL,
    ativo  boolean NOT NULL DEFAULT true
);

-- Uma view, pra a demo mostrar que listar_views() também funciona.
CREATE VIEW pedidos_por_cliente AS
SELECT c.nome,
       count(p.id)          AS qtd_pedidos,
       coalesce(sum(p.valor), 0) AS total
FROM clientes c
LEFT JOIN pedidos p ON p.cliente_id = c.id
GROUP BY c.nome
ORDER BY total DESC;
