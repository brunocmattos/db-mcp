-- Dados fictícios pra demonstração.

INSERT INTO clientes (nome, email, cidade) VALUES
    ('Ana Souza',      'ana@exemplo.test',      'Porto Alegre'),
    ('Bruno Lima',     'bruno@exemplo.test',    'Curitiba'),
    ('Carla Nunes',    'carla@exemplo.test',    'São Paulo'),
    ('Diego Farias',   'diego@exemplo.test',    'Recife'),
    ('Elisa Prado',    'elisa@exemplo.test',    'Belo Horizonte'),
    ('Felipe Rocha',   'felipe@exemplo.test',   'Florianópolis');

INSERT INTO pedidos (cliente_id, valor, status) VALUES
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

INSERT INTO usuarios (login, papel, ativo) VALUES
    ('admin',    'administrador', true),
    ('operador', 'operador',      true),
    ('leitura',  'somente_leitura', true),
    ('antigo',   'operador',      false);
