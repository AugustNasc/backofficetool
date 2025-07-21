# Changelog

## [1.0.0] - 2025-07-20

### Added
- **Módulo de Correção Monetária**:
    - Novo cálculo de correção de valores usando índices IPCA e IGPM.
    - Suporte para datas em formatos DD/MM/AAAA, AAAA-MM-DD e MM/AAAA.
    - Exibição das cotações atuais e históricas (últimos 12 meses) dos índices (BrasilAPI).
    - Opção de nome de cliente para identificação do cálculo.
    - Histórico persistente dos últimos 10 cálculos realizados por usuário no banco de dados.
    - Funcionalidade de upload de planilha para correção automática de múltiplos valores.
- **Módulo de Consulta CNPJ/Cliente**:
    - Consulta de dados de empresas via CNPJ utilizando a BrasilAPI.
    - Histórico persistente das últimas 10 consultas realizadas por usuário no banco de dados.
    - Feedback visual de carregamento (spinner) durante a consulta.
- **Gestão de Usuários e Perfil**:
    - Tela "Meu Perfil" acessível pela navbar com informações do usuário logado e cargo.
    - Opção de "Alterar Minha Senha" acessível diretamente do menu do usuário na navbar.

### Changed
- **Cálculo de Multa Contratual**:
    - Geração de "Código de Controle" único para cada cálculo de multa.
    - Todos os cálculos de multa são salvos no banco de dados.
    - A URL da logo de impressão agora é configurável nas "Configurações Gerais".
- **Dashboard SLA Squad**:
    - Todos os dados de SLA são persistidos no banco de dados.
    - A meta mensal do SLA é configurável nas "Configurações Gerais".
    - Exportação de dados para Excel e PDF com formatação aprimorada.
    - Funcionalidade de "Fechar Ano" para calcular a mediana anual do SLA.
    - Suporte para importação de dados de SLA via planilha Excel.
- **Monitor Jurídico**:
    - Atividades jurídicas são salvas no banco de dados.
    - Cálculo de dias úteis em aberto agora utiliza feriados do banco de dados.
    - Implementação de modal para gerenciar feriados (adicionar, remover, buscar da BrasilAPI).
    - Botões de ação para Status (Concluída, Pendente com Área) e Prioridade (Solicitada/Normal) com atualização via AJAX.
    - Filtragem de atividades por Proprietário.
- **Configurações Gerais (Admin)**:
    - Adicionadas configurações para clientes e produtos a serem excluídos da análise de pleitos.
    - Adicionada configuração para o intervalo de atualização da base de pleitos.
    - Adicionada configuração para URL da logo de impressão.
    - Adicionada configuração da meta percentual de SLA.

### Fixed
- Corrigido erro `TypeError: Object of type Undefined is not JSON serializable` na Consulta CNPJ ao exibir detalhes do histórico, garantindo serialização correta do JSON.
- Corrigido problema de fuso horário na exibição da Data da Consulta na tabela de histórico de CNPJ.
- Corrigido erro `unconverted data remains: 00:00:00` na Correção Monetária ao importar planilhas com datas.
- Corrigido `TemplateSyntaxError` em `consulta_cnpj.html` devido a blocos Jinja não fechados.
- Corrigido `werkzeug.routing.exceptions.BuildError` para endpoints de perfil/senha devido à ordem de definição das rotas em `app.py`.
- Corrigido `jinja2.exceptions.UndefinedError` para `hasattr` em templates Jinja, movendo a lógica para o backend.
- Corrigido botão "Ver detalhes" na Consulta CNPJ que não puxava dados, e posteriormente removido junto com a coluna "Ações" para simplificar a interface.
- Unificação de todos os imports e remoção de duplicações em `app.py`, `models.py`, e arquivos HTML e Python auxiliares (`file_processing.py`, `excel_export.py`, `pdf_generator.py`, `dias_uteis.py`, `auth.py`, `config.py`, `init_db.py`, e todos os `.html` que passaram pela revisão).
- Remoção de comentários desnecessários.
- Padronização das cores das tabelas de histórico na Consulta CNPJ.
- Ajuste do tempo de atualização do cache de CNPJ para 1 dia.
- Ajuste do limite de itens no histórico de Correção Monetária para 10.