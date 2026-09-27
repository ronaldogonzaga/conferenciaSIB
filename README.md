# Conferência SIB / ANS

Aplicação web para **conferência cadastral** entre a base local de beneficiários (`cadusu`) e o retorno do **Sistema de Informação de Beneficiários (SIB)** da ANS (`confsib`).

Identifica inconsistências de cadastro (POSANS, CCO, CPF, datas, divergências com a ANS etc.), apresenta um painel com totais e detalhes por regra, permite **pré-visualizar e aplicar correções** selecionadas e exportar os resultados em CSV.

**Versão atual:** ver arquivo [`VERSION`](VERSION).

---

## Objetivo

Apoiar a equipe responsável pelo envio e manutenção de dados na ANS a:

- Detectar automaticamente registros fora das regras esperadas do fluxo SIB
- Comparar dados locais (`cadusu`) com o retorno ANS (`confsib`)
- Priorizar inconsistências por severidade (crítica, alta, média, baixa)
- Corrigir, com confirmação, situações que possuem plano de correção implementado
- Exportar listas de inconsistências para análise externa

---

## Tecnologias

| Camada | Tecnologia |
|--------|------------|
| Backend | Python 3, [Flask](https://flask.palletsprojects.com/) 3+ |
| Banco de dados | PostgreSQL (via [psycopg2](https://www.psycopg.org/)) |
| Configuração | [python-dotenv](https://pypi.org/project/python-dotenv/) (arquivo `.env`) |
| Frontend | HTML, CSS e JavaScript (templates Jinja2 + arquivos estáticos) |

### Dependências Python

Definidas em `requirements.txt`:

- `flask>=3.0.0`
- `psycopg2-binary>=2.9.9`
- `python-dotenv>=1.0.0`

---

## Estrutura do projeto

```
conferenciaSIB/
├── app.py                 # Aplicação Flask e rotas da API
├── config.py              # Configurações (env + versão)
├── db.py                  # Conexão e helpers PostgreSQL
├── requirements.txt       # Dependências Python
├── run.bat                # Atalho Windows: cria venv, instala e inicia
├── VERSION                # Versão da aplicação
├── .env                   # Credenciais e parâmetros (não versionado)
├── validators/
│   ├── sib_rules.py       # Regras de inconsistência (SQL + metadados)
│   └── corrections.py     # Planos de correção (preview / apply)
├── templates/
│   └── index.html         # Interface principal
└── static/
    ├── css/style.css
    ├── js/app.js
    └── favicon.svg
```

---

## Pré-requisitos

- **Python 3.10+** recomendado (o código usa anotações modernas, como `list[dict]`)
- Acesso de rede a um **PostgreSQL** contendo o schema com as tabelas `cadusu` e `confsib`
- No Windows, o atalho `run.bat` facilita a inicialização

---

## Instalação

### 1. Clonar o repositório

```bash
git clone <url-do-repositorio>
cd conferenciaSIB
```

### 2. Criar e ativar o ambiente virtual

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (CMD):**

```bat
python -m venv venv
venv\Scripts\activate.bat
```

**Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar as dependências

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto (ele não é versionado; veja `.gitignore`). Exemplo:

```env
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=seu_usuario
DB_PASSWORD=sua_senha
DB_NAME=Plano_Saude
DB_SCHEMA=WARELINE
FLASK_DEBUG=1
FLASK_PORT=5000
MAX_ROWS=500
```

| Variável | Descrição | Padrão (se omitida) |
|----------|-----------|---------------------|
| `DB_HOST` | Host do PostgreSQL | `10.0.2.15` |
| `DB_PORT` | Porta do PostgreSQL | `6441` |
| `DB_USER` | Usuário do banco | `WARELINE` |
| `DB_PASSWORD` | Senha do banco | *(definida no código/env)* |
| `DB_NAME` | Nome do banco | `Plano_Saude` |
| `DB_SCHEMA` | Schema usado no `search_path` | `WARELINE` |
| `FLASK_DEBUG` | `1` = debug ligado | `1` |
| `FLASK_PORT` | Porta HTTP local | `5000` |
| `MAX_ROWS` | Limite de linhas em detalhes/preview | `500` |

---

## Como executar

### Opção A — Script Windows (`run.bat`)

Duplo clique em `run.bat` ou execute no terminal:

```bat
run.bat
```

O script:

1. Cria o `venv` se ainda não existir
2. Ativa o ambiente virtual
3. Instala/atualiza as dependências de `requirements.txt`
4. Abre o navegador em `http://127.0.0.1:<porta>/`
5. Inicia `python app.py`

### Opção B — Manualmente

Com o venv ativo e o `.env` configurado:

```bash
python app.py
```

A aplicação sobe em:

```text
http://127.0.0.1:5000/
```

(ajuste a porta conforme `FLASK_PORT` no `.env`).

### Verificação rápida

- Interface: abrir a URL acima no navegador  
- Saúde da API / banco: `GET http://127.0.0.1:5000/api/health`

---

## Funcionalidades principais

- **Dashboard** com totais de `cadusu`, `confsib`, ativos, inativos e regras com inconsistência
- **Lista de regras** filtrável por severidade e status (com / sem inconsistência)
- **Detalhe** dos registros flagados por regra
- **Correção assistida** (quando a regra possui plano): preview → seleção → apply com confirmação
- **Exportação CSV** (separador `;`, UTF-8 com BOM) por regra

### Principais endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Interface web |
| `GET` | `/api/health` | Testa conexão com o banco |
| `GET` | `/api/dashboard` | Totais do painel |
| `GET` | `/api/rules` | Catálogo de regras |
| `GET` | `/api/summary` | Contagem de inconsistências por regra |
| `GET` | `/api/rule/<id>/count` | Contagem de uma regra |
| `GET` | `/api/rule/<id>` | Detalhe (linhas) de uma regra |
| `POST` | `/api/rule/<id>/fix/preview` | Pré-visualização da correção |
| `POST` | `/api/rule/<id>/fix/apply` | Aplica correção (`confirm: true` + `ids`) |
| `GET` | `/api/export/<id>` | Download CSV da regra |

---

## Observações

- A aplicação é pensada para uso **local/interno** (`127.0.0.1`). Não exponha a porta à internet sem autenticação e hardening adequados.
- Operações de correção alteram dados em `cadusu`; use sempre o **preview** e confirme os IDs antes do `apply`.
- Não versione o arquivo `.env` com credenciais reais.
