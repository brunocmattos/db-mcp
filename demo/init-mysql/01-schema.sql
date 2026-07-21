-- Schema da demonstração MySQL — o MESMO do Postgres (demo/init/01-schema.sql),
-- traduzido pros tipos do MySQL. Igual de propósito: as duas demos respondem as
-- mesmas perguntas, então dá pra comparar dialeto a dialeto sem ruído de dados.
--
-- Roda automaticamente na primeira subida do container (o entrypoint do MySQL
-- executa /docker-entrypoint-initdb.d em ordem).

CREATE TABLE clientes (
    id         INT PRIMARY KEY AUTO_INCREMENT,
    nome       VARCHAR(120) NOT NULL,
    email      VARCHAR(180) NOT NULL UNIQUE,
    cidade     VARCHAR(120) NOT NULL,
    criado_em  DATE NOT NULL DEFAULT (CURRENT_DATE)
);

CREATE TABLE pedidos (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    cliente_id  INT NOT NULL,
    valor       DECIMAL(10, 2) NOT NULL,
    status      VARCHAR(30) NOT NULL DEFAULT 'aberto',
    criado_em   DATE NOT NULL DEFAULT (CURRENT_DATE),
    FOREIGN KEY (cliente_id) REFERENCES clientes (id)
);

CREATE TABLE usuarios (
    id     INT PRIMARY KEY AUTO_INCREMENT,
    login  VARCHAR(60) NOT NULL UNIQUE,
    papel  VARCHAR(40) NOT NULL,
    ativo  BOOLEAN NOT NULL DEFAULT TRUE
);

-- Uma view, pra a demo mostrar que listar_views() também funciona.
CREATE VIEW pedidos_por_cliente AS
SELECT c.nome,
       count(p.id)               AS qtd_pedidos,
       coalesce(sum(p.valor), 0) AS total
FROM clientes c
LEFT JOIN pedidos p ON p.cliente_id = c.id
GROUP BY c.nome
ORDER BY total DESC;
