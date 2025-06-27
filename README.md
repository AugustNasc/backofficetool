# Backoffice Tools

[cite_start]Backoffice Tools é uma plataforma web desenvolvida em Flask para apoiar e automatizar rotinas do time de backoffice, com foco em gestão operacional, controle de pleitos, acompanhamento de SLAs e fluxos jurídicos, além de cálculos contratuais automatizados.

## Visão Geral

- [cite_start]**Painel Intuitivo:** Interface amigável com navegação rápida entre as funcionalidades, layout responsivo e suporte a modo escuro.
- [cite_start]**Foco Operacional:** Desenvolvido especificamente para equipes de backoffice, jurídico e squads de operação, otimizando suas tarefas diárias.

## Funcionalidades Principais

[cite_start]As funcionalidades são projetadas para simplificar e automatizar diversas tarefas do dia a dia:

### **1. Sistema de Autenticação e Gestão de Usuários**
- [cite_start]**Login Seguro:** Autenticação de usuários baseada em banco de dados com hash de senha.
- [cite_start]**Controle de Acesso:** Gerenciamento de sessão (login/logout) e proteção de rotas, garantindo que apenas usuários autorizados acessem determinadas funcionalidades.
- [cite_start]**Perfis de Usuário (Roles):** Definição de diferentes perfis (`Admin`, `Backoffice`, `Consultor`, `Guest`) com permissões granulares para cada funcionalidade (ex: `can_view_all`, `can_edit_pleitos`, `can_manage_users`).
- [cite_start]**Registro de Usuários:** Novos usuários são registrados com a role padrão 'Consultor'.
- [cite_start]**Gerenciamento de Usuários (Apenas Admin):** Interface para administradores visualizarem, editarem perfis e redefinirem senhas de outros usuários.

### **2. Análise e Gestão de Pleitos**
- [cite_start]**Upload de Planilhas:** Suporte para carregamento de arquivos `.xlsx` ou `.xls` contendo dados de pleitos e pendências.
- [cite_start]**Filtragem Avançada:** Capacidade de filtrar dados por colunas como `Consultor`, `Cliente`, `Produto`, `Data Pendência` e `Valor`.
- [cite_start]**Resumo por Consultor:** Geração automática de um resumo agrupado por consultor, exibindo total de clientes e pleitos atrasados.
- [cite_start]**Identificação de Hotlines:** Processamento especial para hotlines, combinando registros relacionados e tratando valores.
- [cite_start]**Exclusão de Clientes:** Filtragem automática de clientes específicos que devem ser excluídos da análise.
- [cite_start]**Contas em Transição (Beta):** Ferramenta para gerenciar a transição de clientes entre consultores, ajustando a gestão dos pleitos automaticamente com base em uma planilha ou inserção manual.
- [cite_start]**Exportação de Dados:** Exporta os dados filtrados para um novo arquivo Excel.

### **3. Cálculo de Multa Contratual**
- [cite_start]**Cálculo Automatizado:** Ferramenta para calcular multas de rescisão/cancelamento de contratos.
- [cite_start]**Regras Específicas:** Inclui regras de cálculo para serviços `RSFN` (multa fixa de 50%) e serviços padrão (percentual variável com base no tempo de contrato cumprido).
- [cite_start]**Consideração de Aviso Prévio:** Opções configuráveis de aviso prévio para impactar o cálculo da multa.
- [cite_start]**Relatório Detalhado:** Geração de uma página de resultados com todos os detalhes do cálculo, pronta para impressão.

### **4. Dashboard SLA Squad**
- [cite_start]**Acompanhamento Mensal:** Permite o cadastro mensal de resultados de SLA, incluindo quantidade dentro/fora SLA e total de processos.
- [cite_start]**Visualização de Desempenho:** Exibe o percentual `Realizado` e a `Meta` definida, com um gráfico de barras para acompanhamento visual.
- [cite_start]**Gestão de Meta:** Capacidade de definir e ajustar a meta mensal do SLA (entre 70% e 100%).
- [cite_start]**Importação/Exportação:** Funcionalidades para importar dados de Excel e exportar o dashboard em formato Excel ou PDF.
- [cite_start]**Fechamento de Ano:** Opção para "fechar o ano" quando todos os 12 meses são preenchidos, calculando a média anual.

### **5. Monitor Jurídico**
- [cite_start]**Análise de Atividades:** Upload e acompanhamento de planilhas de atividades jurídicas.
- [cite_start]**Cálculo de Dias em Aberto:** Calcula automaticamente os dias úteis desde a criação da atividade, sinalizando atrasos (4 dias para "quase atrasando", 5+ dias para "atrasada").
- [cite_start]**Configuração de Feriados:** Um modal permite visualizar e editar a lista de feriados considerados nos cálculos de dias úteis.
- [cite_start]**Gestão Visual:** Interface para marcar atividades como `Concluídas`, `Prioritárias` e indicar `Pendência com Outra Área` com badges visuais.

### **6. Correção Monetária**
- [cite_start]**Cálculo de Correção:** Realiza a correção monetária de valores utilizando índices como `IPCA` e `IGPM`.
- [cite_start]**Flexibilidade de Datas:** Suporte para datas de início e fim no formato completo (`DD/MM/AAAA` ou `AAAA-MM-DD`) ou apenas mês/ano (`MM/AAAA`).
- [cite_start]**Detalhes do Cálculo:** Exibe o fator acumulado, percentual acumulado e o valor corrigido.

### **7. Consulta CNPJ/Cliente**
- [cite_start]**Consulta Direta:** Permite consultar dados de empresas a partir de um CNPJ, utilizando uma API externa.
- [cite_start]**Informações Detalhadas:** Retorna informações como Razão Social, Nome Fantasia, Endereço, Contato, Atividade Principal, entre outros.

### **8. Histórico de Logs**
- [cite_start]**Auditoria Completa:** Registra todas as ações importantes executadas no sistema (login, upload, filtros, exportações, alterações de usuários, cálculos) com detalhes, usuário e timestamp.
- [cite_start]**Exportação:** Permite exportar o histórico de logs para um arquivo Excel para auditoria ou análise externa.

### **9. Páginas de Erro Customizadas**
- [cite_start]**Experiência do Usuário:** Páginas amigáveis e informativas para erros 403 (Acesso Proibido), 404 (Não Encontrado) e 500 (Erro Interno do Servidor), sempre com opções para retornar ao menu ou sair.

## Tecnologias e Requisitos

- [cite_start]**Python 3.9+** 
- [cite_start]**Flask 2.3+**: Microframework web.
- [cite_start]**Flask-SQLAlchemy 3.0.3**: ORM para interação com banco de dados.
- [cite_start]**Flask-WTF 1.2.2**: Integração com formulários WTForms.
- [cite_start]**Flask-Migrate 4.1.0**: Ferramenta para migrações de banco de dados.
- [cite_start]**Pandas 2.0.3**: Para manipulação e análise de dados tabulares.
- [cite_start]**Numpy 1.24.3**: Dependência do Pandas.
- [cite_start]**Openpyxl 3.1.2**: Para leitura/escrita de arquivos `.xlsx`.
- [cite_start]**python-dotenv 1.0.0**: Para gerenciamento de variáveis de ambiente.
- [cite_start]**Werkzeug 2.3.6**: Kit de ferramentas WSGI.
- [cite_start]**fpdf2 2.7.4**: Geração de arquivos PDF.
- [cite_start]**Gunicorn 20.1.0**: Servidor WSGI de produção (recomendado para deploy).
- [cite_start]**Requests 2.31.0**: Para fazer requisições HTTP a APIs externas.
- [cite_start]**XlsxWriter 3.0.3**: Para escrita avançada de arquivos `.xlsx`.
- [cite_start]**Bootstrap 5**: Framework CSS para o design responsivo.
- [cite_start]**Bootstrap Icons 1.8.0**: Conjunto de ícones.

[cite_start]As dependências completas podem ser encontradas no arquivo `requirements.txt`.

## Instalação Rápida

[cite_start]Siga os passos abaixo para configurar e rodar o projeto localmente:

```bash
# Clone o repositório
git clone [https://github.com/seu-usuario/backoffice-tools.git](https://github.com/seu-usuario/backoffice-tools.git)
cd backoffice-tools

# Crie um ambiente virtual e ative (opcional, mas altamente recomendado)
python -m venv venv
source venv/bin/activate  # No Linux/macOS
# venv\Scripts\activate   # No Windows

# Instale as dependências
pip install -r requirements.txt

# Configure variáveis de ambiente
# Crie um arquivo '.env' na raiz do projeto, baseado no '.env.example'.
# Exemplo de .env:
# SECRET_KEY='sua_chave_secreta_super_segura_aqui'
# DATABASE_URL='sqlite:///./instance/backoffice.db' # Ou outra URL de banco de dados

# Inicialize o banco de dados e crie o usuário 'admin' padrão
python init_db.py

# Rode a aplicação localmente
flask run --host=0.0.0.0 --port=10000