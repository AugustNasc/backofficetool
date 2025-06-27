# Backoffice Tools

 Backoffice Tools é uma plataforma web desenvolvida em Flask para apoiar e automatizar rotinas do time de backoffice, com foco em gestão operacional, controle de pleitos, acompanhamento de SLAs e fluxos jurídicos, além de cálculos contratuais automatizados.

## Visão Geral

 **Painel Intuitivo:** Interface amigável com navegação rápida entre as funcionalidades, layout responsivo e suporte a modo escuro.
 **Foco Operacional:** Desenvolvido especificamente para equipes de backoffice, jurídico e squads de operação, otimizando suas tarefas diárias.

## Funcionalidades Principais

 As funcionalidades são projetadas para simplificar e automatizar diversas tarefas do dia a dia:

### **1. Sistema de Autenticação e Gestão de Usuários**
 **Login Seguro:** Autenticação de usuários baseada em banco de dados com hash de senha.
 **Controle de Acesso:** Gerenciamento de sessão (login/logout) e proteção de rotas, garantindo que apenas usuários autorizados acessem determinadas funcionalidades.
 **Perfis de Usuário (Roles):** Definição de diferentes perfis (`Admin`, `Backoffice`, `Consultor`, `Guest`) com permissões granulares para cada funcionalidade (ex: `can_view_all`, `can_edit_pleitos`, `can_manage_users`).
 **Registro de Usuários:** Novos usuários são registrados com a role padrão 'Consultor'.
 **Gerenciamento de Usuários (Apenas Admin):** Interface para administradores visualizarem, editarem perfis e redefinirem senhas de outros usuários.

### **2. Análise e Gestão de Pleitos**
 **Upload de Planilhas:** Suporte para carregamento de arquivos `.xlsx` ou `.xls` contendo dados de pleitos e pendências.
 **Filtragem Avançada:** Capacidade de filtrar dados por colunas como `Consultor`, `Cliente`, `Produto`, `Data Pendência` e `Valor`.
 **Resumo por Consultor:** Geração automática de um resumo agrupado por consultor, exibindo total de clientes e pleitos atrasados.
 **Identificação de Hotlines:** Processamento especial para hotlines, combinando registros relacionados e tratando valores.
 **Exclusão de Clientes:** Filtragem automática de clientes específicos que devem ser excluídos da análise.
 **Contas em Transição (Beta):** Ferramenta para gerenciar a transição de clientes entre consultores, ajustando a gestão dos pleitos automaticamente com base em uma planilha ou inserção manual.
 **Exportação de Dados:** Exporta os dados filtrados para um novo arquivo Excel.

### **3. Cálculo de Multa Contratual**
 **Cálculo Automatizado:** Ferramenta para calcular multas de rescisão/cancelamento de contratos.
 **Regras Específicas:** Inclui regras de cálculo para serviços `RSFN` (multa fixa de 50%) e serviços padrão (percentual variável com base no tempo de contrato cumprido).
 **Consideração de Aviso Prévio:** Opções configuráveis de aviso prévio para impactar o cálculo da multa.
 **Relatório Detalhado:** Geração de uma página de resultados com todos os detalhes do cálculo, pronta para impressão.

### **4. Dashboard SLA Squad**
 **Acompanhamento Mensal:** Permite o cadastro mensal de resultados de SLA, incluindo quantidade dentro/fora SLA e total de processos.
 **Visualização de Desempenho:** Exibe o percentual `Realizado` e a `Meta` definida, com um gráfico de barras para acompanhamento visual.
 **Gestão de Meta:** Capacidade de definir e ajustar a meta mensal do SLA (entre 70% e 100%).
 **Importação/Exportação:** Funcionalidades para importar dados de Excel e exportar o dashboard em formato Excel ou PDF.
 **Fechamento de Ano:** Opção para "fechar o ano" quando todos os 12 meses são preenchidos, calculando a média anual.

### **5. Monitor Jurídico**
 **Análise de Atividades:** Upload e acompanhamento de planilhas de atividades jurídicas.
 **Cálculo de Dias em Aberto:** Calcula automaticamente os dias úteis desde a criação da atividade, sinalizando atrasos (4 dias para "quase atrasando", 5+ dias para "atrasada").
 **Configuração de Feriados:** Um modal permite visualizar e editar a lista de feriados considerados nos cálculos de dias úteis.
 **Gestão Visual:** Interface para marcar atividades como `Concluídas`, `Prioritárias` e indicar `Pendência com Outra Área` com badges visuais.

### **6. Correção Monetária**
 **Cálculo de Correção:** Realiza a correção monetária de valores utilizando índices como `IPCA` e `IGPM`.
 **Flexibilidade de Datas:** Suporte para datas de início e fim no formato completo (`DD/MM/AAAA` ou `AAAA-MM-DD`) ou apenas mês/ano (`MM/AAAA`).
 **Detalhes do Cálculo:** Exibe o fator acumulado, percentual acumulado e o valor corrigido.

### **7. Consulta CNPJ/Cliente**
 **Consulta Direta:** Permite consultar dados de empresas a partir de um CNPJ, utilizando uma API externa.
 **Informações Detalhadas:** Retorna informações como Razão Social, Nome Fantasia, Endereço, Contato, Atividade Principal, entre outros.

### **8. Histórico de Logs**
 **Auditoria Completa:** Registra todas as ações importantes executadas no sistema (login, upload, filtros, exportações, alterações de usuários, cálculos) com detalhes, usuário e timestamp.
 **Exportação:** Permite exportar o histórico de logs para um arquivo Excel para auditoria ou análise externa.

### **9. Páginas de Erro Customizadas**
 **Experiência do Usuário:** Páginas amigáveis e informativas para erros 403 (Acesso Proibido), 404 (Não Encontrado) e 500 (Erro Interno do Servidor), sempre com opções para retornar ao menu ou sair.

## Tecnologias e Requisitos

 **Python 3.9+** 
 **Flask 2.3+**: Microframework web.
 **Flask-SQLAlchemy 3.0.3**: ORM para interação com banco de dados.
 **Flask-WTF 1.2.2**: Integração com formulários WTForms.
 **Flask-Migrate 4.1.0**: Ferramenta para migrações de banco de dados.
 **Pandas 2.0.3**: Para manipulação e análise de dados tabulares.
 **Numpy 1.24.3**: Dependência do Pandas.
 **Openpyxl 3.1.2**: Para leitura/escrita de arquivos `.xlsx`.
 **python-dotenv 1.0.0**: Para gerenciamento de variáveis de ambiente.
 **Werkzeug 2.3.6**: Kit de ferramentas WSGI.
 **fpdf2 2.7.4**: Geração de arquivos PDF.
 **Gunicorn 20.1.0**: Servidor WSGI de produção (recomendado para deploy).
 **Requests 2.31.0**: Para fazer requisições HTTP a APIs externas.
 **XlsxWriter 3.0.3**: Para escrita avançada de arquivos `.xlsx`.
 **Bootstrap 5**: Framework CSS para o design responsivo.
 **Bootstrap Icons 1.8.0**: Conjunto de ícones.

 As dependências completas podem ser encontradas no arquivo `requirements.txt`.

## Instalação Rápida

 Siga os passos abaixo para configurar e rodar o projeto localmente:

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