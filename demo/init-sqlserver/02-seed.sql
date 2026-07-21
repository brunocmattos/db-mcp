-- Dados ficticios pra demonstracao -- os MESMOS do demo Postgres/MySQL
-- (demo/init/02-seed.sql, demo/init-mysql/02-seed.sql).

USE demo;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.clientes)
BEGIN
    -- N'...' pra Unicode chegar certo nas colunas NVARCHAR via sqlcmd (-f 65001 no entrypoint).
    INSERT INTO dbo.clientes (nome, email, cidade) VALUES
        (N'Ana Souza',      'ana@exemplo.test',      N'Porto Alegre'),
        (N'Bruno Lima',     'bruno@exemplo.test',    N'Curitiba'),
        (N'Carla Nunes',    'carla@exemplo.test',    N'São Paulo'),
        (N'Diego Farias',   'diego@exemplo.test',    N'Recife'),
        (N'Elisa Prado',    'elisa@exemplo.test',    N'Belo Horizonte'),
        (N'Felipe Rocha',   'felipe@exemplo.test',   N'Florianópolis');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.pedidos)
BEGIN
    INSERT INTO dbo.pedidos (cliente_id, valor, status) VALUES
        (1, 149.90, 'pago'),
        (1,  59.90, 'pago'),
        (2, 320.00, 'aberto'),
        (3,  89.90, 'pago'),
        (3, 210.50, 'enviado'),
        (3,  45.00, 'cancelado'),
        (4, 999.99, 'aberto'),
        (5,  12.50, 'pago'),
        (5,  75.00, 'enviado'),
        (6, 430.00, 'pago');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.usuarios)
BEGIN
    INSERT INTO dbo.usuarios (login, papel, ativo) VALUES
        ('admin',    'administrador',   1),
        ('operador', 'operador',        1),
        ('leitura',  'somente_leitura', 1),
        ('antigo',   'operador',        0);
END
GO
