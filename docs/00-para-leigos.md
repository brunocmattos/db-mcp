# db-mcp explicado do zero

> Um guia para quem **não** é da área. Nada aqui pressupõe que você saiba programar ou
> entenda de banco de dados. Cada termo técnico é explicado na primeira vez que aparece,
> com uma comparação do mundo real. Se você quer só instalar, vá pro [README](../README.md);
> aqui a meta é você **entender** — o que é um MCP, o que é este, como usar, como foi feito,
> quais as seguranças, e até como criar um do zero ou adaptar pra outros bancos.

Este guia é longo de propósito: vai do que é um MCP até como adaptar o projeto para outros
bancos. Use o índice para pular pro que te interessa.


## Índice

1. [O que é um MCP (do zero)](#o-que-é-um-mcp-do-zero)
2. [O que é ESTE MCP, por que usar e onde](#o-que-é-este-mcp-por-que-usar-e-onde)
3. [Como usar (e é fácil de configurar e de entender?)](#como-usar-e-é-fácil-de-configurar-e-de-entender)
4. [Como foi montado por dentro e por que assim](#como-foi-montado-por-dentro-e-por-que-assim)
5. [Quais seguranças ele tem, e existem brechas?](#quais-seguranças-ele-tem-e-existem-brechas)
6. [Funciona com qualquer banco?](#funciona-com-qualquer-banco)
7. [Vantagens sobre outros MCPs, funcionalidades e o que falta](#vantagens-sobre-outros-mcps-funcionalidades-e-o-que-falta)
8. [Como criar um MCP do zero, e feito-à-mão vs pronto](#como-criar-um-mcp-do-zero-e-feito-à-mão-vs-pronto)
9. [Como o MCP virou "dinâmico": PostgreSQL, MySQL e SQL Server no mesmo código](#como-o-mcp-virou-dinâmico-postgresql-mysql-e-sql-server-no-mesmo-código)

## O que é um MCP (do zero)

Uma inteligência artificial como o Claude, sozinha, só sabe fazer uma coisa: conversar. Ela lê o que você escreve e responde com texto. Ponto. Ela não consegue, por conta própria, abrir uma gaveta, mandar um e-mail ou olhar dentro de um banco de dados. É como uma pessoa muito culta trancada numa sala vazia, sem telefone e sem janela: ótima de papo, mas incapaz de tocar em qualquer coisa do lado de fora.

Para a IA **agir** no mundo — e não só falar sobre ele — ela precisa de **ferramentas**. Uma ferramenta é uma ação concreta que a IA pode acionar: "buscar este arquivo", "consultar aquele banco", "enviar esta mensagem". A ferramenta é a mão que falta na pessoa trancada na sala.

### O problema que o MCP resolve

Aqui aparece uma chateação. Existem muitas IAs diferentes, e muitíssimos sistemas com que elas poderiam conversar. Se cada IA tivesse que aprender um jeito próprio de falar com cada sistema, seria um festival de gambiarra: um encaixe feito à mão para cada combinação. Trabalhoso, frágil, e refeito toda vez que algo muda.

O **MCP** (sigla em inglês para *Model Context Protocol*, ou "Protocolo de Contexto de Modelo") é a resposta a isso. Ele é um **padrão** — um idioma comum, aberto, publicado pela Anthropic (a empresa que faz o Claude) no fim de 2024 — que qualquer IA e qualquer sistema podem falar. Se os dois falam MCP, eles se entendem. Sem encaixe sob medida.

A melhor imagem é a **tomada de parede padronizada**. Você não fabrica um plugue diferente para cada aparelho da casa. A tomada tem um formato combinado; o abajur, a TV e o carregador do celular vêm com o plugue naquele formato; e tudo encaixa. O MCP é essa tomada para o mundo das IAs. Um sistema que "tem o plugue MCP" pluga em qualquer IA que "tem a tomada MCP".

### Os três tijolos que um servidor MCP pode oferecer

Quem fala MCP pode oferecer três tipos de coisa. Pense em três tijolos de construção:

- **Ferramentas** (*tools*): ações que a IA aciona. É o tijolo do "fazer". Por exemplo: "consultar o banco". A IA decide chamar, a ferramenta executa e devolve o resultado.
- **Recursos** (*resources*): dados que a IA lê, mais parados, como um documento ou um arquivo disponível para consulta. É o tijolo do "olhar".
- **Prompts** (*prompts*): atalhos de instrução prontos, como um botão de "faça deste jeito" que já vem com o texto do pedido montado. É o tijolo do "receita pronta".

Um sistema não precisa oferecer os três. **Este projeto, o db-mcp, oferece só ferramentas** — seis delas, cada uma uma ação sobre o banco de dados: `listar_schemas`, `listar_tabelas`, `listar_views`, `descrever_tabela`, `amostra` e `consultar`. No código elas aparecem marcadas com `@mcp.tool`, que é justamente o rótulo de "isto aqui é uma ferramenta". Nada de recursos, nada de prompts.

### Cliente e servidor: quem pede e quem serve

No mundo do MCP há sempre dois lados, e vale não confundi-los.

De um lado, o **cliente MCP**. É o programa onde a IA vive e de onde ela faz os pedidos — por exemplo o **Claude Desktop** (o aplicativo de conversa) ou o **Claude Code** (a versão para quem programa). O cliente é o freguês sentado à mesa.

Do outro lado, o **servidor MCP**. É o programa que oferece as ferramentas e atende aos pedidos. **Este projeto é um servidor MCP.** Ele fica esperando; quando a IA pede "me lista as tabelas", ele vai ao banco de dados, pega a resposta e devolve.

Vale guardar a imagem do **garçom** para o resto da explicação: o servidor MCP é o garçom que fica entre a IA (o freguês) e o banco de dados (a cozinha, ou melhor, um almoxarifado gigante de fichas organizadas). O freguês não entra na cozinha; ele pede ao garçom, e o garçom traz. O MCP é o idioma em que o pedido é feito. Nas próximas seções veremos que garçom cuidadoso é esse — ele só sabe **olhar** as fichas, nunca rasurar, e ainda passa cada pedido por um segurança na porta antes de servir.

## O que é ESTE MCP, por que usar e onde

Em uma frase: o **db-mcp** é um porteiro que deixa uma IA **olhar** as fichas de um banco de dados, mas nunca rasurar, mudar ou arrancar nenhuma.

Vamos por partes. Um **banco de dados** é como um almoxarifado gigante de fichas muito bem organizadas: fichas de clientes, de pedidos, de produtos, cada tipo em sua própria gaveta. O **PostgreSQL** é uma marca específica desse tipo de almoxarifado — uma das mais usadas no mundo. O db-mcp é um programa que fica entre a IA e esse almoxarifado. Ele traduz os pedidos da IA para a língua do banco e devolve as respostas — mas com uma regra inegociável no meio do caminho: **só leitura**. A IA pode pedir "me mostra as fichas de clientes de São Paulo" e receber a resposta. Não pode pedir "apaga essas fichas" nem "troca o nome em todas elas". Esse pedido nem chega a ser executado.

### O problema que ele resolve

Dar a uma IA acesso direto ao banco é útil e perigoso ao mesmo tempo.

Útil, porque a IA responde perguntas sobre os dados sozinha, na hora, em linguagem normal. Perigoso, porque uma IA é imprevisível — de vez em quando ela "alucina", ou seja, inventa com toda a confiança uma resposta ou uma ação errada. E no banco, um erro desses estraga de verdade:

- Um comando de **apagar uma gaveta inteira** de fichas (no jargão, um `DROP TABLE`), disparado por engano.
- Um comando de **rasurar todas as fichas de uma vez** em vez de só uma (um `UPDATE` sem a condição que limitaria o alcance).
- Um pedido que tenta **puxar dez milhões de fichas de uma vez** e trava o almoxarifado inteiro para todo mundo.

Nenhum desses precisa de má intenção. Basta a IA errar uma vez.

### A filosofia: assuma que a IA vai errar

A saída preguiçosa seria pedir com jeitinho para a IA se comportar e torcer. O db-mcp faz o contrário. Ele **parte do princípio de que a IA vai errar** e deixa o caminho seguro de qualquer jeito.

Se a IA tentar escrever, o próprio banco recusa. Se pedir uma gaveta que não devia, a aplicação barra. Se pedir fichas demais, existe um teto que corta. A segurança não depende de a IA ser bem-comportada — depende de barreiras que ficam de pé mesmo quando ela não é.

### Por que usar

Porque você ganha o lado bom (uma IA que consulta seus dados e responde) sem o lado assustador (o risco de ela escrever, alterar ou derrubar alguma coisa). É leitura, e só leitura: por mais que a IA se descontrole, **escrever, alterar ou apagar dados está fora de alcance** — a tentativa leva um "não" do próprio banco. (Isso não quer dizer que ela vira uma parede perfeita: a IA continua enxergando os dados e a estrutura que tem permissão de ver, e há alguns limites menores já conhecidos e documentados — mas nenhum deles a deixa escrever no banco.)

### Onde usar

Em qualquer situação em que alguém — pessoa ou automação — precisa **consultar** dados, nunca mudá-los. Por exemplo:

- Um **analista** perguntando "quantos pedidos fechamos mês passado?" em português comum, sem saber escrever a consulta técnica.
- Um **agente de suporte** (humano ou automático) checando a situação de um pedido enquanto atende o cliente.
- Uma **automação de relatório** que, toda segunda de manhã, lê os números da semana e monta um resumo.
- Um **desenvolvedor explorando um banco de homologação** — uma cópia de teste do banco, feita justamente para experimentar sem medo — para entender como os dados estão organizados.

O fio que costura todos os casos é o mesmo: **sempre leitura**. No momento em que a tarefa for escrever, alterar ou apagar algo, esta ferramenta não é a certa — e essa recusa é justamente o ponto dela.

Uma observação honesta de escopo: o db-mcp fala com **PostgreSQL**, **MySQL** e **SQL Server**. Funciona com **qualquer** almoxarifado dessas três marcas — você aponta a ferramenta para o seu banco na configuração, e o código não conhece nenhum banco específico de antemão.

## Como usar (e é fácil de configurar e de entender?)

Tem dois jeitos de colocar isto pra funcionar: **na mão** (você digita alguns comandos) ou **assistido** (você pede pro Claude Code fazer por você). Vou explicar os dois, e no fim respondo com honestidade se é fácil de configurar e de entender.

Antes, dois lembretes rápidos:

- **`uv`** é o programa que instala e organiza tudo que o projeto precisa pra rodar. Pense nele como o entregador que traz e monta todas as peças na sua máquina. Você instala o `uv` uma vez.
- **`.env`** é um arquivinho de texto onde ficam os dados sensíveis: o endereço do banco, o nome do banco e a senha. Ele nunca sobe pro repositório (fica "git-ignored", ou seja, escondido do controle de versão) — os segredos ficam só na sua máquina.

### Caminho 1 — na mão

O resumo cabe em quatro linhas:

```bash
uv sync                       # instala tudo
cp .env.example .env          # crie seu .env a partir do modelo
uv run db-mcp doctor # confere se está tudo certo
uv run db-mcp        # sobe o servidor
```

Traduzindo cada passo:

1. **`uv sync`** — o `uv` baixa e monta as peças do projeto. Você não precisa saber quais são.
2. **Copiar o modelo e preencher** — o projeto já vem com um `.env.example`, que é um formulário em branco. Você copia ele pra `.env` e preenche as lacunas: o host (endereço da máquina onde mora o banco), a porta, o nome do banco, o usuário e a senha. O arquivo `docs/01-instalacao.md` mostra o modelo exato dos campos.
3. **`doctor`** — este é o pulo do gato. É um autoexame que roda **seis checagens** e diz, em português, se cada peça está no lugar: a config está válida? a sua máquina alcança o banco pela rede? o usuário e a senha entram? o banco é **mesmo** somente-leitura (ou seja, "pode olhar as fichas, não pode rasurar nem arrancar nenhuma")? as tabelas que você liberou existem? a resposta é rápida? Cada linha vem com um ✅ ou um ❌ e a dica de como consertar. Você não fica no escuro adivinhando.
4. **Subir o servidor** — o último comando liga o garçom-tradutor entre a IA e o seu banco.

**Um aviso honesto:** o `doctor` só fica todo verde depois que o banco foi preparado — quer dizer, depois que alguém com poderes de administrador criou o tal usuário somente-leitura e liberou o acesso pela rede. Isso está no `docs/02-preparar-o-banco.md` e **não** é parte que o projeto faz sozinho; é uma coisa que se mexe dentro do PostgreSQL. Sem esse preparo, as checagens de "entrou" e de "é somente-leitura" falham de propósito, avisando você.

### A demo de 30 segundos (sem banco nenhum seu)

Se você só quer **ver a coisa funcionando** antes de mexer no seu banco de verdade, tem um atalho. O projeto traz um PostgreSQL de brinquedo, já montado e já com o usuário somente-leitura pronto, dentro de um **Docker** (uma caixinha isolada que sobe um sistema completo na sua máquina sem bagunçar nada). Três comandos:

```bash
docker compose up -d                            # sobe o banco de demonstração
uv sync                                          # instala o MCP
uv run db-mcp --env .env.demo doctor    # confere tudo
```

O `doctor` responde com os seis ✅ verdes. E dá pra ver o segurança na porta trabalhando: uma consulta de leitura volta com dados de clientes de mentira; uma tentativa de escrita (`UPDATE`) é barrada com a mensagem "apenas comandos SELECT são permitidos". Quando cansar, `docker compose down -v` apaga tudo sem deixar rastro. É a forma mais rápida de entender o projeto de olho, sem risco.

### Caminho 2 — assistido (o Claude Code faz por você)

Aqui está o diferencial. Você não precisa entender comando nenhum. Você abre a pasta do projeto no **Claude Code** e pede, em português comum:

> "Instala o db-mcp apontando pro meu banco."

Aí entra uma **skill** — uma receita passo a passo que o Claude segue sozinho (a `setup-db-mcp`). Seguindo o `SETUP.md`, ela conduz tudo:

1. **Pergunta os dados** do seu banco num bloco só (host, porta, nome, usuário, senha).
2. **Ajuda a criar o usuário somente-leitura**: se você ainda não tem, ela te entrega o comando de banco já preenchido com os seus valores, pra você (ou seu administrador) rodar. Ela deixa explícito que esse usuário só ganha permissão de olhar, nunca de escrever.
3. **Preenche o `.env`** com os valores que você deu, e confere que ele está escondido do repositório.
4. **Roda o `doctor`** e **interpreta cada checagem pra você** — se algo falha, ela explica a causa e a correção em vez de te deixar com um erro seco. Ela nem avança enquanto o autoexame não fica 100% verde.
5. **Registra o MCP no seu cliente** — seja Claude Code (com um comando pronto) ou Claude Desktop (com o texto de config pra você colar).

No fim, ela sugere um teste: peça "lista os schemas" e veja a resposta chegar. Repare que nenhum segredo entra no repositório em momento nenhum — o `.env` fica só na sua máquina.

### Então: é fácil de configurar?

**Assistido, é muito fácil** — perto de "conversar e responder umas perguntas". O trabalho pesado (entender comandos, ler erros) fica com o Claude. **Na mão, é fácil pra quem tem alguma familiaridade** com terminal: são quatro comandos e um formulário de texto. O que **não** é automático em nenhum dos dois caminhos é preparar o banco em si (criar o usuário somente-leitura e liberar o acesso na rede) — isso depende de quem administra o PostgreSQL, e é assim de propósito, porque é justamente a camada de segurança mais forte. O projeto ajuda com o comando pronto, mas quem aperta o botão dentro do banco é uma pessoa com poderes de admin.

### E é fácil de entender o projeto? Uma IA "pega" ele rápido?

Sim, e isto foi feito de propósito. O projeto é, deliberadamente, muito bem documentado — em camadas, do superficial ao profundo:

- **README** — a porta de entrada: o que é, os "três cadeados" de segurança, a tabela das seis ferramentas, a demo de 30 segundos.
- **VISAO-GERAL** — o projeto contado do começo ao fim: o que é, por que existe, o que foi usado e por quê.
- **DESIGN** — o desenho completo do produto, com a lista de todos os parâmetros de configuração.
- **docs 01 a 04** — instalação, preparar o banco, arquitetura e solução de problemas, cada um num arquivo.
- **Este próprio documento ELI5** — a explicação para leigos, que você está lendo.

E, dentro do código, mais ajuda: **docstrings** (bilhetinhos em português explicando o que cada pedaço faz), **tipos** (marcações que dizem que tipo de dado entra e sai de cada função, checadas de forma rigorosa por uma ferramenta), e **testes legíveis** — são 229 testes que passam, e um teste bem escrito funciona como um exemplo vivo de "quando você faz X, acontece Y".

Na prática, isso quer dizer que se você jogar este repositório numa IA e perguntar "o que este projeto faz?", ela consegue **montar o quadro inteiro rápido**: a estrutura é pequena, os nomes são descritivos, e há texto explicativo em toda camada — do README de topo até o comentário na função. O projeto foi escrito para ser lido, não só executado. Essa é uma das qualidades reais dele.

## Como foi montado por dentro e por que assim

Pense no programa como uma casa. Tem o miolo da casa, onde moram as regras e a porta dos fundos que dá pro almoxarifado de fichas (o banco de dados). E tem a fachada, por onde o garçom entra e sai levando os pedidos. No db-mcp esses dois pedaços são separados de propósito.

### Núcleo por dentro, casca por fora

O **núcleo** é o coração do sistema: são as regras de segurança mais o acesso ao banco. É ele que decide o que pode e o que não pode, e é ele que fala com o almoxarifado.

Por cima do núcleo tem uma **casca fina**. Essa casca é o pedaço que sabe conversar no idioma MCP — o idioma que a IA usa pra pedir coisas ao garçom. A casca só faz uma coisa: recebe o pedido da IA, entrega pro núcleo, e devolve a resposta. Ela não tem regra nenhuma dentro dela. No código, essa casca é um arquivo só, o `server.py`.

Por que separar assim? Porque dá pra testar o núcleo inteiro sem precisar ligar o servidor. As regras (aceitar ou recusar um pedido, cortar o tamanho da resposta, limitar o ritmo) são testadas isoladas, como se você testasse a fechadura na bancada antes de instalar na porta. É por isso que o projeto tem 191 testes de unidade rodando sem subir banco nenhum. O núcleo não depende da casca pra funcionar; a casca é trocável.

### Dois lugares pra guardar coisas: segredo e ajuste

O programa precisa de duas categorias de informação, e elas ficam em arquivos diferentes de propósito.

- **`.env`** guarda os **segredos**: o endereço do banco, o usuário, a senha, o token de acesso. É o cofre.
- **`config.yaml`** guarda os **ajustes**: quantas linhas no máximo por resposta, qual a lista de mesas que o garçom pode servir, se a consulta livre está ligada ou não, o ritmo permitido. É o painel de configuração.

Por que separar? Porque **ajuste não é sigiloso**, então o projeto publica no repositório um modelo do `config.yaml` — o `config.example.yaml`, preenchido só com valores de exemplo — pra qualquer pessoa da equipe ver o formato. Já o `.env` **não pode vazar nunca**: se a senha do banco cair no repositório, qualquer um que veja o código vê a senha. Na prática, tanto o `config.yaml` de verdade quanto o `.env` de verdade ficam **fora do repositório** (bloqueados pelo `.gitignore`); só os modelos de exemplo é que sobem. Manter as duas categorias separadas evita o acidente mais clássico de todos — subir a senha junto com o código sem perceber.

Os dois arquivos são conferidos **na hora em que o programa liga**. Isso é feito por uma peça chamada `pydantic` (um conferente que olha cada campo da configuração e verifica se está no formato certo). Se faltar a senha, ou se um número vier escrito errado, o programa recusa ligar ali, na largada, com um erro claro — em vez de ligar e quebrar no meio de um pedido, quando já é tarde. Isso se chama "falhar cedo".

### Por que cada peça de tecnologia foi escolhida

Nada aqui foi por acaso. Cada peça resolve um problema específico:

- **FastMCP** é quem fala o idioma MCP. Esse idioma tem um monte de regras chatas de conversa entre a IA e o programa. Escrever isso do zero seria reinventar a roda e cheio de erro. O FastMCP já traz tudo pronto — inclusive a checagem do token de acesso no modo de produção. (Detalhe de cuidado: a versão dele foi **travada** entre a 3.4.4 e antes da 4, pra que uma atualização grande e inesperada não mude o comportamento debaixo dos pés.)

- **psycopg** é o motorista que dirige até o PostgreSQL e traz as fichas. Ele é ligado num **modo somente-leitura** — no código, `conn.read_only = True` — que faz toda conversa com o banco ser marcada como "só olhar, não rasurar". Ele também mantém um **pool**, que é um grupinho de conexões já abertas e prontas, pra não ter que abrir uma porta nova a cada pedido (abrir porta é lento).

- **sqlglot** é o segurança na porta que revista o pedido antes de deixar entrar. E aqui está a decisão mais importante do miolo. Um jeito ingênuo de revistar seria procurar palavras proibidas no texto do pedido, tipo "se aparecer a palavra APAGAR, recuse". Isso é frágil: quem quer driblar escreve a palavra de um jeito torto e passa. O sqlglot faz diferente: ele **desmonta o pedido inteiro numa árvore** — separa cada pedaço, entende que isto aqui é uma busca, aquilo ali é uma função, aquele outro é um comando de escrita — e aí inspeciona pedaço por pedaço, de verdade. É a diferença entre o segurança ler a etiqueta da mala e o segurança abrir a mala e olhar dentro. Se o pedido não for exatamente uma consulta de leitura (um `SELECT`, ou um `WITH...SELECT`), é recusado. Comandos de escrita, criação e remoção de tabela, o truque do `SELECT INTO` (que cria tabela escondido), o `FOR UPDATE` (que trava fichas), e uma lista negra de funções perigosas — ler arquivo do servidor, dormir de propósito pra travar, chamar outro banco pela rede — tudo isso a árvore pega. E o sqlglot é escrito em Python puro, ou seja, **instala em qualquer sistema operacional** sem precisar de compilador.

### Por que três camadas de tranca, e não uma

Este é o ponto que o projeto faz questão de deixar honesto. A segurança não está apoiada num muro só. São **três cadeados em série** — a ideia de "defesa em profundidade": se um falha, o próximo ainda segura.

1. **O usuário do banco é fisicamente somente-leitura.** No próprio banco, esse usuário só recebeu permissão de olhar (`GRANT SELECT`). Esta é a tranca **mais forte de todas**, porque ela **não depende do código** do programa. Mesmo que o segurança da porta cochile, o almoxarifado em si se recusa a ser rasurado. (Com uma diferença importante entre as marcas de banco — veja o quadro logo abaixo.)

2. **A rede só deixa esse usuário entrar de endereços conhecidos.** Uma regra do banco (o `pg_hba.conf` no PostgreSQL; o endereço embutido no próprio nome do usuário, no MySQL) só aceita conexão vindo dos computadores certos. Quem está fora não chega nem na porta.

3. **A aplicação revista o pedido.** É todo o núcleo que descrevemos: o segurança sqlglot, a lista de mesas permitidas (a allowlist), o corte automático no número de linhas, o teto no tamanho da resposta, o controle de ritmo. E, quando o pedido volta, a conexão é **limpa** com um comando que apaga qualquer rastro (`DISCARD ALL`), pra que nada que um cliente fez sobre na conexão e vaze pro próximo cliente que a reutilizar.

Repare numa sutileza deliberada: as ferramentas de olhar a estrutura do banco — listar schemas, listar tabelas, descrever uma tabela — **não passam pela lista de mesas permitidas**. Só as ferramentas que trazem dados de verdade (amostra e consulta livre) passam.

### O ponto honesto: onde está o limite de verdade

E aqui a franqueza é central, sem amenizar: a lista de mesas permitidas dentro da **aplicação é defesa-em-profundidade, não o limite último**. Contra um usuário de banco com permissões amplas, sempre vai existir mais uma função obscura pra tentar driblar a revista do segurança. O isolamento forte de verdade não vem do código — vem do **cadeado nº 1**, a permissão restrita configurada no próprio banco, somada à remoção (o `REVOKE`) das funções perigosas. Por isso a ordem dos cadeados importa: o código é a última linha, não a primeira.

Dois furos conhecidos ficam **documentados de propósito**, porque esconder problema não é honestidade:

- **Vazamento de informação sobre a estrutura.** Como a introspecção não passa pela lista de mesas, dá pra descobrir que certos objetos existem fora da lista — o nome, o tamanho, o formato deles — mesmo sem conseguir ler o conteúdo.
- **Pico de memória.** Se um pedido devolver uma única linha gigantesca — imagine uma ficha com quinhentos milhões de letras nela — essa linha é montada inteira na memória **antes** de o teto de tamanho ser checado. O teto barra a resposta, mas o susto de memória já aconteceu.

Fora esses dois pontos, não há outro furo conhecido — e eles ficam à mostra de propósito, porque esconder limite não é honestidade.

### Vale pra qualquer PostgreSQL ou MySQL

Por fim, uma escolha de projeto: o programa **não conhece banco nenhum específico**. Você aponta pro seu banco pela configuração, e ele funciona — seja qual for o seu banco, contanto que seja um dos três suportados. O código não tem nenhuma tabela ou empresa embutida. Ele fala **PostgreSQL, MySQL e SQL Server** hoje.

## Quais seguranças ele tem, e existem brechas?

Este programa foi feito para deixar uma inteligência artificial olhar um banco de dados sem risco de estragar nada. Pense de novo no banco como um almoxarifado gigante de fichas organizadas. A ideia é que a IA possa ler as fichas, mas nunca rasurar, arrancar ou escrever em cima de nenhuma.

Para garantir isso, o projeto não confia em um único mecanismo. Ele usa três cadeados em fila. Se um falhar, o próximo ainda segura a porta. Isso tem um nome no mundo da segurança: defesa em profundidade. É a mesma lógica de ter um portão, uma porta e um cofre, em vez de confiar só no cofre.

### Cadeado nº 1: o banco só deixa ler (o mais forte)

Este é o cadeado mais importante, e ele mora dentro do próprio banco, não no nosso código.

Quando você prepara o banco, cria um usuário exclusivo para a IA. Esse usuário recebe uma permissão chamada `GRANT SELECT`, que quer dizer "só pode consultar". É o "pode olhar as fichas, não pode rasurar nem arrancar nenhuma", imposto pelo próprio almoxarifado.

Por que este é o mais forte? Porque não depende do nosso programa acertar nada. Mesmo que todo o resto falhasse, o banco continuaria recusando escrita sozinho. O manual do projeto (`docs/02-preparar-o-banco.md`) ensina a montar esse usuário passo a passo.

**Aqui vem uma diferença que o projeto não esconde.** No PostgreSQL dá para pendurar no usuário uma trava extra (`default_transaction_read_only = on`) que faz o banco tratar **toda** conversa daquele usuário como leitura — para sempre, sem depender de mais nada. **O MySQL não tem isso.** Lá existe uma trava parecida, mas que vale só para a conexão da vez, e é o **nosso programa** que precisa ligá-la toda vez que pega uma conexão emprestada. Nós ligamos — e temos um teste automático que garante que continuará sendo ligado —, mas é código nosso, não garantia do almoxarifado. **E o SQL Server não tem trava nenhuma dessas.** Medido: pedir "esta sessão é só leitura" para um SQL Server dá um erro de sintaxe — o comando nem existe ali. Não há trava para pendurar no usuário, nem uma versão mais fraca por conexão para o nosso programa ligar. O que sobra é só o `GRANT` (e o seu oposto, o `DENY`, que o SQL Server também oferece).

Tradução prática: **no MySQL, escolher direitinho quais fichas o crachá pode ver (`GRANT SELECT` só nas tabelas certas) não é capricho, é a proteção principal.** No PostgreSQL isso é a segunda camada; no MySQL, é a primeira. **No SQL Server, é a única que existe** — não há segunda camada nenhuma por trás dela.

### Cadeado nº 2: só entra quem vem do endereço certo

Todo computador na rede tem um endereço, o chamado IP. É como o endereço de uma casa.

O banco tem um porteiro de rede, um arquivo chamado `pg_hba.conf`. Nele você escreve: "esse usuário da IA só pode entrar se vier deste endereço aqui" (a sua máquina, ou o servidor onde o programa roda). Um computador desconhecido, vindo de outro endereço, nem chega a bater na porta. É recusado antes.

### Cadeado nº 3: o segurança na porta (a aplicação)

Este é o nosso programa. Antes de qualquer pedido chegar ao banco, ele passa por uma revista. Pense num segurança na porta que revista o pedido antes de deixar entrar. Ele faz várias checagens em sequência:

- **Só passa um pedido de leitura por vez.** O programa usa uma ferramenta chamada sqlglot, que lê e entende a linguagem dos bancos de dados (o SQL) sem nem tocar no banco. Ela confere que o pedido é uma única consulta de leitura (um `SELECT`). Ela barra qualquer coisa que escreva ou altere estrutura: criar, apagar, mudar, mesclar. Barra também truques conhecidos, como um `SELECT` que na verdade cria uma tabela nova, ou que tranca fichas para escrita.
- **Barra funções perigosas por nome.** Existe uma lista negra de comandos especiais do PostgreSQL que poderiam ler arquivos do servidor, fazer chamadas de rede, travar o banco de propósito ou driblar as outras travas. Exemplos que aparecem no código: `pg_read_file` (ler arquivo), `dblink` (falar com outro banco), `pg_sleep` (fazer o banco travar de propósito), `set_config` e os `advisory locks` (mudar o estado da sessão), e os comandos `*_to_xml`, que recebem uma tabela ou consulta escrita como texto e escapariam da revista. Se o pedido usa qualquer um deles, é recusado.
- **A lista de mesas permitidas (allowlist).** Volte à imagem do garçom-tradutor entre a IA e o banco. A allowlist é a lista de mesas que esse garçom tem permissão de servir, ou seja, quais tabelas a IA pode consultar. Um pedido que toque uma tabela fora da lista é barrado.
- **Limite de linhas automático (`LIMIT`).** Se o pedido não disser quantas fichas quer, ou pedir um número exagerado, o programa apara para um teto (o `MAX_ROWS`). Evita que uma consulta puxe o almoxarifado inteiro de uma vez.
- **Teto de tamanho da resposta.** Se o resultado ficar grande demais em quantidade de dados (o `MAX_RESULT_BYTES`), o programa recusa entregar.
- **Limite de ritmo (rate limit).** Cada cliente só pode fazer um tanto de consultas por minuto. É a fila com controle: ninguém empurra pedidos rápido demais e sobrecarrega o banco.
- **Senha de entrada no modo servidor.** Quando o programa roda como serviço em rede (o modo HTTP), toda requisição precisa apresentar uma senha, o `Authorization: Bearer <token>`. E há uma regra rígida: o programa se recusa a ligar se essa senha não estiver configurada. No jargão, isso é fail-closed, "na dúvida, fica trancado". Nunca sobe aberto por acidente.
- **Limpeza entre um cliente e outro (`DISCARD ALL`).** O programa reaproveita conexões com o banco para ser rápido (isso se chama pool de conexões). Ao devolver uma conexão para reuso, ele roda um comando de faxina que apaga qualquer resíduo da sessão anterior. Assim, nada que um cliente fez vaza para o próximo que pegar a mesma conexão.

### E então: existem brechas?

Vale uma resposta honesta, sem maquiagem.

Não existe brecha que deixe a IA **escrever** no banco: essa porta é fechada em três camadas, e a mais forte é o próprio banco recusar qualquer escrita. O que existem são **dois pontos residuais**, conhecidos e documentados de propósito, que o cadeado nº 3 (a aplicação) sozinho não fecha por completo.

1. **Vazamento de metadados.** Metadados são "dados sobre os dados": nomes, tamanhos e a forma das tabelas, sem o conteúdo delas. As ferramentas que descrevem a estrutura do banco (listar tabelas, descrever uma tabela) consultam o catálogo interno do PostgreSQL, e essas consultas não passam pela lista de mesas permitidas. Resultado: dá para descobrir que certos objetos existem, o tamanho deles e como foram montados, mesmo os que estão fora da allowlist. O conteúdo continua protegido; o que escapa é a "planta baixa" do almoxarifado.

2. **Pico de memória de uma linha muito larga.** Os limites do programa controlam quantas fichas voltam, mas não o tamanho de cada ficha. É possível pedir uma única linha absurdamente gorda (por exemplo, um texto com quinhentos milhões de caracteres repetidos). Essa linha é montada na memória antes de o teto de tamanho ser conferido. Ou seja, dá para provocar um pico de uso de memória. O corte de tempo por consulta (o `statement_timeout`) já apara o caso mais extremo, mas fechar isso de vez exigiria uma mudança maior na forma de ler os dados.

### O ponto que não pode passar despercebido

A lista de mesas permitidas (allowlist), que fica no nosso programa, é **defesa em profundidade, não o limite final**. Ela é a segunda tranca, útil e importante, mas não é o muro definitivo.

O motivo é sincero: contra um usuário de banco que tenha permissões amplas, a linguagem SQL é rica demais para uma revista na porta cobrir todos os truques possíveis. Sempre pode existir mais uma função que a análise não previu.

Por isso a regra de ouro do projeto: **o cadeado mais forte é o do próprio banco; a aplicação é a segunda tranca.** O isolamento realmente sólido vem do cadeado nº 1, quando você concede ao usuário da IA permissão de leitura apenas nas tabelas que ele deve ver, e nada mais, e ainda tira dele o direito de executar funções perigosas. Aí o próprio PostgreSQL recusa tudo o que estiver fora, por mais esperto que seja o pedido. O nosso programa ajuda, filtra e organiza, mas quem dá a palavra final, e deve dar, é o banco.

## Funciona com qualquer banco?

Resposta curta: sim, contanto que seja **PostgreSQL, MySQL ou SQL Server**.

O motivo é que o programa não vem com nenhum banco embutido. Ele não conhece "o seu banco". Você é quem aponta para onde ele deve ir, escrevendo o endereço num arquivo de configuração. É como um garçom que não trabalha num restaurante fixo: você diz o endereço e ele vai servir naquele lugar.

### Onde você diz para qual banco apontar

Os dados de conexão ficam num arquivo chamado `.env` (pense nele como uma ficha de contato guardada num cofrinho, porque ali vai a senha). São seis informações:

- `DB_HOST` — o endereço do banco (o "prédio" onde ele mora na rede).
- `DB_PORT` — a porta de entrada nesse endereço (o padrão do PostgreSQL é a `5432`; a do MySQL, `3306`; a do SQL Server, `1433`). Se você deixar em branco, o programa usa a porta certa para o banco escolhido.
- `DB_DBNAME` — o nome do banco específico (um mesmo servidor pode guardar vários almoxarifados; você escolhe qual).
- `DB_USER` e `DB_PASSWORD` — o crachá e a senha com que o programa se identifica.
- `DB_SSLMODE` — se a conversa com o banco vai por um canal fechado à prova de bisbilhoteiro (por padrão vem como `prefer`, que usa o canal fechado quando o banco oferece).

Você troca esses seis valores e pronto: o mesmo programa passa a falar com outro banco. Nada no código muda.

### O que você precisa preparar do lado do banco

O programa não se instala sozinho dentro do seu banco. Duas coisas precisam existir lá, e quem faz é um administrador do banco (ou a skill de instalação, que ajuda no passo a passo):

1. **Criar o crachá de "só olhar".** Um usuário novo (o padrão se chama `mcp_ro`) que tem permissão de ler, e só ler. O núcleo é sempre um `GRANT SELECT` nas tabelas certas. No PostgreSQL some ainda uma trava extra do próprio banco que recusa qualquer escrita daquele crachá para sempre (`default_transaction_read_only = on`); no MySQL essa trava existe só por conexão, e quem liga é o nosso programa; no SQL Server essa trava **não existe de jeito nenhum** — lá o `GRANT` (e o seu oposto, o `DENY`) é o cadeado inteiro. Cada banco tem seu próprio manual em [`docs/02-preparar-o-banco.md`](02-preparar-o-banco.md).

2. **Liberar o seu endereço na portaria da rede.** No PostgreSQL isso é uma lista de portaria chamada `pg_hba.conf`; no MySQL o próprio nome do usuário já carrega o endereço permitido; no SQL Server é o firewall ou o security group da máquina/nuvem. Em qualquer um dos três, a ideia é a mesma: "esse crachá `mcp_ro` só pode entrar vindo de tais endereços" (a sua máquina, o servidor onde o MCP roda). De qualquer outro lugar, o banco nem abre a porta.

Sem esses dois passos, a ferramenta de autodiagnóstico (o `doctor`) acusa o problema logo de cara, antes de qualquer uso.

### Versões e onde ele roda (a verdade sem enfeite)

- Por baixo, cada banco tem seu próprio "tradutor": **psycopg 3** para o PostgreSQL, **mysql-connector** para o MySQL, **pymssql** para o SQL Server. Cada um fala o "idioma" daquele banco — e é por isso que o mesmo programa serve para qualquer banco dessas três marcas para onde você apontar, sem conhecer nenhum banco específico de antemão.
- Funciona bem com bancos **na nuvem** — Amazon RDS, Google Cloud SQL, Azure SQL e parecidos — com uma condição honesta: você precisa conseguir **criar aquele usuário de leitura** e **alcançar o banco pela rede** (o que às vezes exige liberar um IP ou ligar uma VPN). Se você consegue essas duas coisas, funciona.
- Limite claro: hoje ele fala **PostgreSQL, MySQL e SQL Server**. Ainda não serve para outras marcas de banco (Oracle, SQLite e outras ficam de fora).

## Vantagens sobre outros MCPs, funcionalidades e o que falta

Este não é o único garçom que existe para conversar com um PostgreSQL. Vale comparar, sem maquiar, com os outros mais conhecidos.

### Quem são os concorrentes

O mais famoso era o **servidor "postgres" de referência**, feito pela própria organização do protocolo MCP. Ele também era somente-leitura (podia olhar as fichas, não rasurar). Só que ele foi **descontinuado e arquivado em julho de 2025** — largado, sem manutenção. Pior: descobriram nele um buraco que deixava um pedido malandro **furar a trava de somente-leitura** e rodar comandos de escrita. A trava dele era frágil.

O outro popular é o **Postgres MCP Pro** (do projeto crystaldba/postgres-mcp). Esse é bem mais parrudo e vai para o lado oposto: ele **escreve** no banco (por padrão), analisa desempenho, sugere melhorias e mostra o "plano de execução" das consultas. É um canivete suíço para quem administra e otimiza banco.

O db-mcp escolheu deliberadamente ser o contrário de um canivete suíço: uma ferramenta só, muito bem afiada.

### As vantagens deste projeto

**Obsessão por uma coisa só: leitura segura.** Enquanto o Postgres MCP Pro faz muita coisa (e por isso precisa saber escrever), este aqui faz pouca coisa de propósito. Ele nunca escreve. Isso corta uma categoria inteira de acidentes pela raiz.

**Os três cadeados (defesa em camadas).** A segurança não depende de um truque só. São três trancas independentes: (1) o próprio banco só concede permissão de leitura ao usuário; (2) a rede só deixa esse usuário entrar de endereços conhecidos; (3) o código, que revista cada pedido. Se uma tranca falhar, as outras ainda seguram. O cadeado mais forte é o número 1 — porque ele mora no banco, não no código; nenhum erro de programação consegue afrouxá-lo.

**O segurança na porta lê a gramática, não caça palavrão.** Aqui está a diferença técnica que mais importa. Muitos verificadores de SQL funcionam como quem procura palavras proibidas num texto: se achar "DELETE" ou "UPDATE", barra. Isso é frágil — dá para disfarçar a palavra e enganar. Este projeto usa uma biblioteca chamada **sqlglot** que faz uma **árvore sintática**: ela desmonta a frase do pedido inteira, como um professor de português que diagrama a oração no quadro e entende exatamente o que é sujeito, verbo e objeto. Aí ela só aceita se o pedido for uma única consulta de leitura de verdade. Não dá para enganar com disfarce de palavra nem colar um segundo comando escondido depois de um ponto e vírgula. E o servidor de referência? O que o furou não foi um palavrão disfarçado, e sim uma injeção de SQL que escapava da trava de somente-leitura e rodava escrita — justamente o tipo de escape que barrar comandos empilhados e aceitar só uma consulta de leitura, lida por inteiro, fecha.

**A lista de mesas (allowlist).** O garçom pode ser limitado a servir só certas mesas — certas tabelas. O que estiver fora da lista, ele não toca ao ler dados.

**O "doctor" — a revisão antes de abrir.** Antes de o servidor entrar em operação, um comando roda seis checagens: a configuração está válida? A rede alcança o banco? O login funciona? O banco **realmente** recusa escrita (ele tenta escrever e confirma que levou não)? As tabelas da lista existem? A resposta é rápida? É como o piloto que confere o avião item por item antes de decolar. Os outros MCPs, em geral, não têm esse ritual de pré-voo.

**Honestidade escrita na documentação.** Este projeto não promete ser inviolável. Ele diz, com todas as letras, onde ainda há frestas: dá para descobrir a existência e o tamanho de tabelas que estão fora da lista (a introspecção não passa pela allowlist), e um resultado de uma linha gigantesca pode inchar a memória por um instante antes de ser barrado. Isso está documentado de propósito. É raro um projeto apontar os próprios limites assim.

**Testes e verificação contínua.** São 229 testes automáticos (191 de unidade + 38 de integração contra bancos **reais** — a suíte roda inteira contra um PostgreSQL e depois contra um MySQL), todos passando, mais checagens de qualidade de código rodando sozinhas a cada mudança, no Linux e no Windows. É a diferença entre um produto cuidado e um script largado — justamente o que faltou ao servidor de referência abandonado.

### Onde os outros levam vantagem (as desvantagens, sem enrolação)

Ser afiado numa coisa só custa caro em outras. Sendo honesto:

- **Só lê, não escreve.** Se você precisa que a IA insira, corrija ou apague dados, este projeto não serve. O Postgres MCP Pro serve. Aqui a incapacidade de escrever é o produto, não uma falha — mas é uma limitação real.
- **Fala PostgreSQL, MySQL e SQL Server, mas não Oracle nem SQLite** (nem outras marcas). Alguns MCPs concorrentes cobrem mais dialetos.
- **Não analisa desempenho.** Ele não tem o **EXPLAIN** (o recurso do Postgres que mostra o "plano de execução" — o passo a passo que o banco pretende seguir para responder, útil para descobrir por que uma consulta está lenta). O Postgres MCP Pro faz isso e ainda sugere melhorias. Este aqui, não.
- **Não expõe métricas Prometheus.** Prometheus é um sistema muito usado para monitorar programas em produção, coletando números como "quantas consultas por segundo" num painel. Este projeto não oferece esse encaixe pronto (ele registra tudo num arquivo de auditoria, o que é mais simples e menos sofisticado).
- **Um banco por instância.** Cada cópia rodando fala com um único banco. Para atender três bancos, você sobe três cópias. Alguns concorrentes lidam com vários de uma vez.

### O que já vem dentro (as funcionalidades atuais)

- **Seis ferramentas.** Quatro de introspecção — olhar o mapa do almoxarifado sem ler o conteúdo das fichas: `listar_schemas`, `listar_tabelas`, `listar_views` e `descrever_tabela` (colunas e tipos). E duas que leem dados de verdade e por isso passam pela lista de mesas: `amostra` (as primeiras linhas de uma tabela) e `consultar` (uma consulta de leitura livre, sempre revistada — e que dá para **desligar por completo** com um ajuste na configuração, se você quiser que a IA só use as ferramentas prontas).
- **O doctor**, a revisão de pré-voo com as seis checagens.
- **A auditoria.** Toda consulta deixa rastro num diário: quem pediu, o quê, quantas linhas voltaram, quanto demorou e se foi aceita ou recusada. Se algo estranho acontecer, há um histórico para conferir.
- **O rate limit ("balde de fichas").** Cada cliente ganha uma cota de consultas por minuto. Quem pede demais, rápido demais, é segurado. Isso evita que um agente enlouquecido sobrecarregue o banco.

### Faltou alguma funcionalidade?

Faltar, no sentido de "poderia existir e não existe", sim. Mas cada ausência foi uma escolha, não um esquecimento. Candidatos honestos que ficaram de fora **de propósito**, para manter a ferramenta afiada numa coisa só:

- **Consultas nomeadas de negócio.** Em vez de deixar a IA escrever a consulta, o dono do banco cadastraria consultas prontas e seguras ("faturamento do mês", com o mês como parâmetro), e a IA só escolheria qual usar. É mais seguro ainda.
- **EXPLAIN somente-leitura.** Deixar a IA ver o plano de execução para explicar por que algo é lento — sem executar nada. Caberia no espírito de "só leitura", mas não entrou nesta versão.
- **Paginação por cursor.** Um jeito de ler resultados enormes em fatias, página por página, como um marcador de livro que guarda onde você parou. Hoje o resultado vem limitado a um teto; não há esse "próxima página" formal.
- **Máscara de dados sensíveis (PII).** PII é a sigla para dados pessoais — CPF, e-mail, telefone. A máscara borraria automaticamente essas colunas antes de entregar à IA. Ainda não existe.
- **Vários bancos numa instância só.** Já mencionado acima como limitação.

Cada ausência é uma escolha de escopo, não um esquecimento: a ferramenta prefere fazer bem uma coisa só — leitura segura — a fazer muitas pela metade.

---

*Fontes externas sobre os concorrentes:* [servidor postgres de referência (arquivado)](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/postgres), [estudo da falha de segurança nele (Datadog Security Labs)](https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/) e [Postgres MCP Pro (crystaldba/postgres-mcp)](https://github.com/crystaldba/postgres-mcp).

## Como criar um MCP do zero, e feito-à-mão vs pronto

Criar um MCP não começa pelo código. Começa por uma pergunta simples: **o que eu quero deixar a IA fazer?**

Lembre da imagem do garçom. O MCP é o garçom que fica entre a IA e um sistema (aqui, o banco de dados — aquele almoxarifado gigante de fichas organizadas). Antes de contratar o garçom, você decide o cardápio: quais pedidos ele aceita e quais ele nem leva pra cozinha.

### Passo 1: escolher as ferramentas (o cardápio)

Cada coisa que a IA pode pedir é uma **ferramenta** (uma ação). Você lista essas ações uma a uma.

Neste projeto, o cardápio tem exatamente seis pratos:

- `listar_schemas`, `listar_tabelas`, `listar_views`, `descrever_tabela` — servem pra IA olhar a organização do almoxarifado (quais gavetas existem, o que tem dentro).
- `amostra` — traz as primeiras linhas de uma tabela.
- `consultar` — deixa a IA escrever uma pergunta de busca própria.

Repare numa decisão de projeto: as quatro primeiras só olham a "planta" do almoxarifado. As duas últimas tocam nos dados de verdade e, por isso, passam por mais conferência. Isso está escrito no código (`src/db_mcp/server.py`): as de introspecção chamam a busca com `aplicar_allowlist=False`, e a `consultar` até pode ser desligada por completo com uma chave de configuração (`ALLOW_FREEFORM_SQL=false`).

Definir o cardápio é a parte mais importante. Tudo que você **não** colocar aqui, a IA não consegue fazer. Ponto.

### Passo 2: pegar uma biblioteca que já fala o protocolo

MCP é um **protocolo** — um idioma combinado, com regras de como a IA e o garçom conversam. É como o padrão de encaixe de uma tomada: existe uma norma, e todo mundo segue.

Você **não** quer reescrever esse idioma do zero. Seria como fabricar sua própria tomada em vez de usar a da parede. Então você pega uma **biblioteca** (um pacote de código pronto que outra pessoa escreveu e você reaproveita) que já sabe falar MCP.

As duas mais conhecidas:

- **FastMCP**, em Python — a escolhida neste projeto.
- O **SDK oficial**, em TypeScript/JavaScript — outra linguagem de programação, mantido pela própria criadora do protocolo.

Aqui usamos FastMCP (fixada numa faixa de versão segura, `>=3.4.4,<4`, pra uma atualização brusca não quebrar tudo de surpresa). Ela cuida do idioma. Você só cuida do cardápio.

### Passo 3: escrever cada ferramenta como uma função

Uma **função**, em programação, é uma receita com nome: você dá uns ingredientes de entrada, ela devolve um resultado. Cada ferramenta do MCP é uma função dessas, com três coisas obrigatórias:

1. **Nome** — como a IA vai chamar (`somar`).
2. **Descrição** — uma frase explicando o que ela faz, pra IA entender quando usar.
3. **Parâmetros tipados** — quais ingredientes entram e de que tipo (número, texto...). "Tipado" quer dizer que você avisa: "aqui só entra número". Se vier outra coisa, a biblioteca barra na entrada.

Com FastMCP, uma ferramenta minúscula que soma dois números fica assim:

```python
from fastmcp import FastMCP

mcp = FastMCP("minha-calculadora")

@mcp.tool
def somar(a: int, b: int) -> int:
    """Soma dois números e devolve o total."""
    return a + b

mcp.run()
```

Leia devagar. O `@mcp.tool` é uma etiqueta que diz "isto aqui é um prato do cardápio". `a: int, b: int` são os ingredientes tipados (dois números inteiros). A frase entre aspas é a descrição. E `return a + b` é o que a função faz. As ferramentas de verdade deste projeto usam exatamente essa mesma etiqueta `@mcp.tool` — só que, em vez de somar, elas conversam com o banco.

### Passo 4: rodar e plugar no cliente

O `mcp.run()` da última linha liga o garçom. Ele precisa de um **transporte** — o canal por onde a conversa passa. O mais simples chama-se **stdio**: os dois programas (a IA e o seu MCP) falam pelo mesmo cano de texto, na sua própria máquina, sem rede nenhuma.

Depois você registra esse MCP no **cliente** — o programa da IA que você usa (por exemplo, o Claude). A partir daí, quando a IA precisa somar, ela pede pro garçom `somar`, e pronto.

Este projeto oferece dois transportes (visto no `src/db_mcp/cli.py`): **stdio** pra você mexer na sua máquina, e **HTTP** (pela rede, como um serviço rodando num servidor) pra produção. E há uma trava honesta no código: no modo HTTP, ele **se recusa a ligar** sem uma senha de acesso (`AUTH_TOKEN`) configurada — porque um garçom exposto na rede sem senha seria um convite aberto.

### O que dá pra ter dentro de um MCP

Ferramentas são o coração, mas o protocolo permite mais coisas. Vale conhecer os nomes:

- **Ferramentas (tools)** — as ações, o cardápio. Foi o que vimos.
- **Recursos (resources)** — pedaços de dado que a IA pode ler, como se fossem folhetos em cima do balcão (um arquivo, uma tabela de referência).
- **Prompts** — atalhos prontos, tipo um "combo" do cardápio: uma instrução pré-escrita que o usuário aciona com um clique.
- **Validação de entrada** — o garçom conferir o pedido antes de aceitar (o "só entra número" do exemplo).
- **Autenticação** — a senha na porta, pra saber quem está pedindo.
- **Limites e rate-limit** — teto de quanto cada cliente pode pedir num intervalo, pra ninguém abarrotar a cozinha.

Um MCP simples usa só ferramentas. Um MCP levado a sério, como este, usa quase tudo isso ao mesmo tempo.

### Feito sob medida vs. pego da prateleira

Chegamos à decisão central. Existem dois caminhos pra ter um MCP funcionando.

**Caminho A — pegar um MCP "pronto" da prateleira.** A internet já tem MCPs genéricos publicados: você baixa um "MCP pra Postgres" qualquer, aponta pro seu banco e, em minutos, a IA está conectada. É rápido. A troco de quê? Você está confiando numa **caixa-preta** — código de um terceiro que você não leu, que faz o que o autor dele decidiu, do jeito que ele decidiu. Se ele deixa a IA apagar dados, apaga. Se ele manda seus dados pra algum lugar, você talvez nem perceba. Você ganhou velocidade e perdeu controle.

**Caminho B — fazer sob medida**, que é o caso deste projeto. Dá mais trabalho, e em troca você fica dono de três coisas:

- **Controle total.** *Você* escreveu o cardápio. A IA aqui **não pode** rasurar nem arrancar ficha nenhuma — o MCP é somente-leitura (pode olhar, não pode escrever). Isso não é uma promessa no folheto: são três cadeados sobrepostos, sendo o mais forte um usuário do banco que, no próprio banco, só recebeu permissão de leitura. Mesmo se o código tivesse um furo, o banco recusaria a escrita.
- **Segurança feita pro seu risco.** Tem um **segurança na porta que revista cada pedido** antes de deixar entrar (um validador que lê o SQL, aceita só uma busca de leitura e barra comandos perigosos). Tem a **lista de mesas que o garçom pode servir** (a allowlist de tabelas). Tem teto de linhas, teto de tamanho de resposta, e limite de pedidos por cliente. Nada disso vem "de fábrica" num MCP genérico — foi desenhado pro que *este* uso precisa.
- **Auditabilidade.** Você pode conferir tudo. São 229 testes automáticos passando, ferramentas de qualidade de código limpas, e um comando `doctor` que roda seis checagens antes de usar (a configuração está certa? o banco responde? a senha funciona? ele está *mesmo* em modo leitura? a allowlist existe? a resposta é rápida?). Um estranho da prateleira não te entrega esse raio-x.

### A parte honesta

Fazer sob medida **não** significa fortaleza perfeita, e este projeto é franco sobre isso.

A "lista de mesas" (a allowlist) e o segurança na porta são camadas extras — reforço, não a muralha final. Contra alguém com um usuário de banco poderoso, sempre existe mais uma função obscura pra tentar driblar a revista. O isolamento que segura de verdade é o cadeado no próprio banco: dar ao usuário só permissão de leitura e tirar dele as funções perigosas.

E há dois pontos fracos **conhecidos e já anotados** na documentação, não escondidos:

- **Vazamento de metadados.** As ferramentas que olham a planta do almoxarifado não passam pela lista de mesas. Então a IA pode descobrir que certos objetos *existem* (nome, tamanho, formato) mesmo estando fora da allowlist. Ela não lê o conteúdo — mas enxerga a etiqueta da gaveta.
- **Pico de memória.** Uma única linha absurdamente enorme é montada na memória *antes* de o teto de tamanho ser conferido. O teto barra o resultado, mas só depois de o esforço já ter sido feito.

Essa honestidade é, ela mesma, uma vantagem do sob medida. Você sabe onde estão as beiradas do seu próprio sistema. Numa caixa-preta de prateleira, essas beiradas existem do mesmo jeito — você só não faz ideia de onde ficam.

## Como o MCP virou "dinâmico": PostgreSQL, MySQL e SQL Server no mesmo código

Uma pergunta natural: será que dá pra pegar este projeto e transformar num garçom que sabe atender três almoxarifados diferentes — PostgreSQL, MySQL e SQL Server — escolhendo qual banco na hora de instalar?

A resposta não é mais hipótese: **já foi feito, duas vezes.** Primeiro o MySQL, depois o SQL Server. Esta seção conta como, e — mais importante — o que deu errado no meio do caminho, porque as pegadinhas reais só apareceram testando contra um banco de verdade, nunca só lendo o código.

Antes de tudo, os nomes. PostgreSQL, MySQL e SQL Server são três marcas de banco de dados. Pense em três redes de almoxarifado concorrentes. Todas guardam fichas em prateleiras e todas atendem pedidos escritos numa linguagem chamada SQL. Só que cada rede tem seu sotaque de SQL, suas regras internas e seu próprio jeito de organizar o catálogo. É como três países que falam "a mesma língua", mas com gírias e leis diferentes.

### O que amarrava tudo a um banco só

Na primeira versão deste projeto, quatro pedaços do código só sabiam falar "postgresês": o driver que liga no banco (`psycopg`, importado direto em `db.py`), o sotaque que o validador de SQL entendia (fixo em `read="postgres"`), o jeito de consultar o catálogo (filtros e nomes específicos do Postgres) e o comando que declara uma conexão "só leitura" (`conn.read_only = True`, que só existe daquele jeito no Postgres).

### A "tomada universal": um contrato, três encaixes

A peça que resolveu isso é um contrato chamado `Dialeto` (no código, `src/db_mcp/dialetos/base.py`): uma lista fixa do que "todo banco precisa saber fazer" — conectar, ler linhas como dicionário, dizer se um erro do driver significa "recusou por ser somente-leitura", dizer qual é a lista de funções perigosas daquele banco, montar o SQL de introspecção. O resto do programa (o "cérebro", chamado `Nucleo`) conversa só com esse contrato, sem saber qual banco está do outro lado — do mesmo jeito que uma tomada de parede aceita qualquer aparelho que tenha o plugue certo.

Hoje existem **três encaixes** nessa tomada, um arquivo cada: `dialetos/postgres.py`, `dialetos/mysql.py` e `dialetos/sqlserver.py`. Escolher o banco é um único ajuste na configuração (`DIALETO=postgres`, `mysql` ou `sqlserver`), e o `sqlglot` — a biblioteca que faz o papel do segurança na porta — já nasceu poliglota: ela lê SQL em dezenas de sotaques, e o validador passa a usar o sotaque certo (`postgres`, `mysql` ou `tsql`, o nome técnico do sotaque do SQL Server) automaticamente.

### As pegadinhas reais — encontradas testando, não lendo código

Isto é o que a teoria não avisa. Em ambas as vezes (MySQL e SQL Server), o projeto encontrou bugs de verdade só ao rodar contra um banco vivo — nenhum deles seria óbvio só de olhar o código:

- **Cada banco tranca a porta de um jeito bem diferente.** O PostgreSQL tem um cadeado de sessão completo (`default_transaction_read_only`, gravado no usuário, para sempre). O MySQL tem uma versão mais fraca, que vale só para a conexão da vez — e o próprio programa precisa religá-la toda vez que reaproveita uma conexão do pool. **O SQL Server não tem cadeado de sessão nenhum**: pedir "esta sessão é só leitura" dá erro de sintaxe, o comando nem existe ali. Isso mudou o desenho de verdade: no MySQL, o programa reaplica a trava a cada conexão emprestada do pool; no SQL Server, como não há trava nenhuma para reaplicar (e também não há como "limpar" uma conexão reciclada), o programa **abre uma conexão nova a cada consulta** em vez de reaproveitar — a conexão nova faz o papel da limpeza.
- **Um bug real no jeito de cortar o tamanho da resposta.** O programa tem um limite automático de linhas (o `LIMIT`). Ele funcionava perfeitamente no Postgres e no MySQL, mas continha um atalho que, contra um SQL Server de verdade, deixava passar um `LIMIT` — sintaxe que **não existe** em T-SQL (lá o comando certo é `TOP`) — sem traduzir. O SQL Server recusava a consulta inteira. Só apareceu rodando o corpus de ataque contra o banco real pela primeira vez, e foi corrigido antes de seguir.
- **As funções perigosas mudam de banco pra banco.** Cada dialeto tem sua própria lista negra: o Postgres teme `pg_read_file` e `dblink`; o MySQL teme `load_file` e `sleep`; o SQL Server teme `xp_cmdshell` (que roda comandos do sistema operacional) e um grupo de funções (`openrowset`, `opendatasource`) que conseguem alcançar **outros servidores** pela rede. Montar a lista certa para cada banco exigiu estudo específico — errar aqui abre buraco de segurança de verdade.
- **O SQL Server vaza um pouco mais de "planta baixa" que os outros dois.** Medido: sem alguns ajustes extras na hora de criar o usuário (comandos `DENY`, além do `GRANT`), um login com permissão de leitura numa única tabela ainda enxerga a lista de todos os bancos daquela instância e de todos os outros usuários cadastrados — sem ler dado nenhum de conteúdo, mas reconhecimento de terreno de graça, algo que nem o Postgres nem o MySQL fazem. Por isso a receita de instalação do SQL Server, em [`docs/02-preparar-o-banco.md`](02-preparar-o-banco.md), inclui esses `DENY` como parte obrigatória, não como nota de rodapé.

### O teste multiplicou — e hoje cobre os três de verdade

Provar o mesmo comportamento em cada banco significa rodar a suíte inteira contra cada um deles, de verdade, não simulado. Isso é realidade hoje: o CI (a esteira automática que roda a cada mudança) sobe um PostgreSQL, um MySQL **e um SQL Server** de verdade e roda a suíte inteira contra os três, cada um com o seu próprio corpus de ataque.

### O que essa história ensina

Foi um projeto de porte médio em cada rodada, não um retoque de tarde — mas o "cérebro" separado do "encanamento" (a ideia da tomada universal) fez a diferença: o segundo banco custou pouco código novo (um arquivo de dialeto), e o terceiro também. O preço real não foi escrever a conexão nova — foi encontrar, testando contra bancos de verdade, as pegadinhas que nenhuma leitura de documentação teria avisado sozinha.

---

## Em uma frase, para fechar

O db-mcp é um porteiro cuidadoso que deixa uma inteligência artificial **olhar** os
dados de um banco PostgreSQL, MySQL ou SQL Server — nunca mexer neles. Ele foi construído
partindo do princípio de que a IA vai errar, e mesmo assim mantém o caminho seguro: o próprio
banco recusa qualquer escrita, a rede só deixa entrar quem é conhecido, e a aplicação revista
cada pedido antes de servir. É honesto sobre os poucos limites que ainda tem — e sobre como
esses limites mudam de banco para banco —, é fácil de instalar (na mão ou com o Claude
conduzindo), e é simples o bastante para outra IA entender o projeto inteiro sozinha.
