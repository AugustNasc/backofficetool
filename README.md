
# Backoffice Tools

Backoffice Tools é uma plataforma web desenvolvida em Flask para apoiar e automatizar rotinas do time de backoffice, com foco em gestão operacional, controle de pleitos, acompanhamento de SLAs e fluxos jurídicos, além de cálculos contratuais automatizados.

## Visão Geral

- **Painel intuitivo:** Interface amigável com navegação rápida entre as funcionalidades, layout responsivo e suporte a modo escuro.
- **Foco operacional:** Feito para equipes de backoffice, jurídico e squads de operação.

## Funcionalidades Principais

- **Login seguro**
  - Autenticação de usuários via banco de dados (com hash de senha).
  - Controle de sessão (login/logout), proteção de rotas e logs de acesso.

- **Análise de Pleitos**
  - Upload de planilhas (.xlsx ou .xls) contendo dados de pleitos e pendências.
  - Filtros inteligentes por consultor, cliente, produto, data e valor.
  - Resumo automático por consultor: total de clientes, atrasados, relatórios em PDF e exportação em Excel.
  - Identificação automática de pleitos “atrasados” e clientes excluídos da análise.
  - Logs de cada ação relevante (upload, filtro, exportação).

- **Cálculo de Multa Contratual**
  - Calculadora para rescisões e cancelamentos contratuais, com regras específicas para serviços RSFN e padrões.
  - Suporte a cálculo de aviso prévio, vigência, percentual de multa e valor final de cobrança.
  - Geração de relatório detalhado, pronto para impressão.

- **Dashboard SLA Squad**
  - Cadastro mensal de resultados de SLA (quantidade dentro/fora SLA, total de processos, realizado e meta).
  - Gráfico de barras e tabelas para acompanhamento visual.
  - Importação/exportação em Excel e PDF do dashboard anual.
  - Definição e controle de meta mensal dinâmica.
  - Opção de “fechar ano” e reiniciar acompanhamento.

- **Monitor Jurídico**
  - Upload e acompanhamento de planilhas de atividades jurídicas.
  - Cálculo automático de dias em aberto, sinalização de atrasos (com legenda visual e badges).
  - Modal para configuração de feriados e ajustes conforme calendário real.
  - Gestão visual de status, prioridade, conclusão e liberações de fluxo.
  - Exportação dos dados e histórico.

- **Histórico de Logs**
  - Tabela auditável de todas as ações executadas no sistema, com usuário, horário e tipo de evento.

- **Erros customizados**
  - Páginas customizadas para erros 403, 404 e 500, sempre com opção de retornar ao menu ou logout.

## Tecnologias e Requisitos

- **Python 3.9+**
- **Flask 2.3+**, **Flask-SQLAlchemy**, **Flask-WTF**, **Pandas**, **Openpyxl**, **FPDF**, **Bootstrap 5**
- Demais dependências no `requirements.txt`

## Instalação Rápida

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/backoffice-tools.git
cd backoffice-tools

# Crie um ambiente virtual e ative (opcional, mas recomendado)
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate no Windows

# Instale as dependências
pip install -r requirements.txt

# Configure variáveis de ambiente (exemplo .env)
cp .env.example .env

# Inicialize o banco de dados
python init_db.py

# Rode a aplicação localmente
flask run
```

Acesse em [http://localhost:5000](http://localhost:5000).

## Estrutura de Pastas

```
.
├── instance/
│   └── backoffice           # Banco de dados SQLite
├── styles/
│   └── styles.css           # Arquivo de estilos customizado
├── templates/
│   ├── base.html
│   ├── calcular_multa.html
│   ├── logs.html
│   ├── login.html
│   ├── menu.html
│   ├── monitor_juridico.html
│   ├── principal.html
│   ├── resultado_multa.html
│   ├── sla_dashboard.html
│   └── errors/              # Páginas de erro personalizadas (403, 404, 500)
├── uploads/                 # (Usada para uploads de planilhas)
├── utils/
│   ├── auth.py
│   ├── dias_uteis.py
│   ├── excel_export.py
│   ├── file_processing.py
│   └── pdf_generator.py
├── app.py
├── config.py
├── init_db.py
├── models.py
├── README.md
└── requirements.txt
```

- As pastas estão separadas para organização de arquivos de banco, templates, utilitários e uploads.
- O arquivo `README.md` deve ficar na **raiz do projeto**.
- A pasta `errors/` dentro de `templates` contém os HTMLs personalizados de erro.

## Observações

- **Segurança:** Recomenda-se sempre definir uma `SECRET_KEY` forte e proteger o banco em produção.
- **Personalização:** Ajuste a lista de clientes excluídos e regras de negócio em `utils/file_processing.py` conforme a realidade da sua empresa.
- **Logs:** Todas as ações sensíveis (upload, filtros, exportações) são registradas em banco.
- **Escalável:** Fácil de adaptar para novas rotinas, dashboards ou integrações.

---

Desenvolvido para facilitar o operacional. Qualquer dúvida ou sugestão, abra um issue ou entre em contato!

