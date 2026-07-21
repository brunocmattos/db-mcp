-- Schema da demonstracao SQL Server -- o MESMO do Postgres/MySQL (demo/init/01-schema.sql,
-- demo/init-mysql/01-schema.sql), traduzido pros tipos do T-SQL. Igual de proposito: as tres
-- demos respondem as mesmas perguntas, entao da pra comparar dialeto a dialeto sem ruido de
-- dados.
--
-- A imagem do SQL Server nao roda .sql de um diretorio de init sozinha (diferente de
-- Postgres/MySQL) -- por isso o entrypoint.sh aplica estes arquivos na mao via sqlcmd.

IF DB_ID('demo') IS NULL
    CREATE DATABASE demo;
GO

USE demo;
GO

IF OBJECT_ID('dbo.clientes') IS NULL
    CREATE TABLE dbo.clientes (
        id         INT IDENTITY(1,1) PRIMARY KEY,
        nome       NVARCHAR(120) NOT NULL,
        email      NVARCHAR(180) NOT NULL UNIQUE,
        cidade     NVARCHAR(120) NOT NULL,
        criado_em  DATE NOT NULL DEFAULT CAST(GETDATE() AS DATE)
    );
GO

IF OBJECT_ID('dbo.pedidos') IS NULL
    CREATE TABLE dbo.pedidos (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        cliente_id  INT NOT NULL REFERENCES dbo.clientes (id),
        valor       DECIMAL(10, 2) NOT NULL,
        status      NVARCHAR(30) NOT NULL DEFAULT 'aberto',
        criado_em   DATE NOT NULL DEFAULT CAST(GETDATE() AS DATE)
    );
GO

IF OBJECT_ID('dbo.usuarios') IS NULL
    CREATE TABLE dbo.usuarios (
        id     INT IDENTITY(1,1) PRIMARY KEY,
        login  NVARCHAR(60) NOT NULL UNIQUE,
        papel  NVARCHAR(40) NOT NULL,
        ativo  BIT NOT NULL DEFAULT 1
    );
GO

-- Uma view, pra a demo mostrar que listar_views() tambem funciona.
-- T-SQL nao aceita ORDER BY puro dentro de uma view -- exige TOP/OFFSET junto.
IF OBJECT_ID('dbo.pedidos_por_cliente') IS NOT NULL
    DROP VIEW dbo.pedidos_por_cliente;
GO

CREATE VIEW dbo.pedidos_por_cliente AS
SELECT TOP 100 PERCENT
       c.nome,
       COUNT(p.id)               AS qtd_pedidos,
       COALESCE(SUM(p.valor), 0) AS total
FROM dbo.clientes c
LEFT JOIN dbo.pedidos p ON p.cliente_id = c.id
GROUP BY c.nome
ORDER BY total DESC;
GO
