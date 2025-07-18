from app import app, db
from models import User, Role, Configuracao, Feriado, AtividadeJuridica
from datetime import datetime, timedelta, date
import json

with app.app_context():
    print("\n--- Iniciando init_db.py ---")
    print("1. Criando/atualizando tabelas do banco de dados...")
    db.create_all()

    roles_data = {
        'Admin': {
            'can_view_all': True, 'can_edit_all': True, 'can_upload_all': True,
            'can_access_pleitos': True, 'can_edit_pleitos': True, 'can_access_cancelamento': True,
            'can_access_monitor_juridico': True, 'can_edit_monitor_juridico': True,
            'can_access_sla': True, 'can_edit_sla': True,
            'can_access_correcao_valores': True, 'can_edit_correcao_valores': True,
            'can_access_consulta_cnpj': True, 'can_access_logs': True, 'can_manage_users': True
        },
        'Backoffice': {
            'can_view_all': True, 'can_edit_all': True, 'can_upload_all': True,
            'can_access_pleitos': True, 'can_edit_pleitos': True, 'can_access_cancelamento': True,
            'can_access_monitor_juridico': True, 'can_edit_monitor_juridico': True,
            'can_access_sla': True, 'can_edit_sla': True,
            'can_access_correcao_valores': True, 'can_edit_correcao_valores': True,
            'can_access_consulta_cnpj': True, 'can_access_logs': True, 'can_manage_users': False
        },
        'Consultor': {
            'can_view_all': True, 'can_edit_all': False, 'can_upload_all': False,
            'can_access_pleitos': True, 'can_edit_pleitos': False, 'can_access_cancelamento': True,
            'can_access_monitor_juridico': True, 'can_edit_monitor_juridico': False,
            'can_access_sla': False, 'can_edit_sla': False,
            'can_access_correcao_valores': False, 'can_edit_correcao_valores': False,
            'can_access_consulta_cnpj': False, 'can_access_logs': False, 'can_manage_users': False
        },
        'Guest': {
            'can_view_all': False, 'can_edit_all': False, 'can_upload_all': False,
            'can_access_pleitos': False, 'can_edit_pleitos': False, 'can_access_cancelamento': False,
            'can_access_monitor_juridico': False, 'can_edit_monitor_juridico': False,
            'can_access_sla': False, 'can_edit_sla': False,
            'can_access_correcao_valores': False, 'can_edit_correcao_valores': False,
            'can_access_consulta_cnpj': False, 'can_access_logs': False, 'can_manage_users': False
        }
    }

    print("\n2. Processando e persistindo perfis (Roles)...")
    for role_name, permissions in roles_data.items():
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name)
            db.session.add(role)
            print(f"  Adicionando perfil '{role_name}' à sessão.")
        else:
            print(f"  Perfil '{role_name}' já existe. Verificando/atualizando permissões...")

        for perm_name, perm_value in permissions.items():
            setattr(role, perm_name, perm_value)

        try:
            db.session.commit()
            print(f"  Perfil '{role_name}' salvo/atualizado com sucesso (ID: {role.id}).")
        except Exception as e:
            db.session.rollback()
            print(f"  ERRO ao salvar/atualizar perfil '{role_name}': {e}")
            print("  Isso pode impedir o funcionamento correto da aplicação. Verifique o models.py e erros anteriores.")

    admin_role = Role.query.filter_by(name='Admin').first()
    consultor_role = Role.query.filter_by(name='Consultor').first()

    if not admin_role or not consultor_role:
        print("\nERRO CRÍTICO: Perfis 'Admin' ou 'Consultor' não foram encontrados/criados após persistência.")
        print("Verifique os logs acima para erros na criação de perfis. Não é possível continuar a inicialização de usuários.")
        exit()

    print("\n3. Processando e persistindo usuário 'admin'...")
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        admin_user = User(username='admin', role=admin_role)
        admin_user.set_password('admin')
        db.session.add(admin_user)
        print("  Usuário 'admin' adicionado à sessão (será criado).")
    elif admin_user.role != admin_role:
        admin_user.role = admin_role
        print("  Usuário 'admin' existente; associando-o ao perfil 'Admin'.")
    else:
        print("  Usuário 'admin' já existe e já tem o perfil 'Admin'.")

    try:
        db.session.commit()
        print("  Usuário 'admin' salvo/atualizado com sucesso.")
    except Exception as e:
        db.session.rollback()
        print(f"  ERRO ao salvar/atualizar usuário 'admin': {e}")
        print("  Isso pode impedir o login do usuário admin. Verifique o models.py e erros anteriores.")

    print("\n4. Verificando e configurando parâmetros iniciais da aplicação...")
    data_padrao_atraso = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    config_atraso = Configuracao.query.filter_by(chave='data_limite_pleitos_atrasados').first()
    if not config_atraso:
        config_atraso = Configuracao(
            chave='data_limite_pleitos_atrasados',
            valor=data_padrao_atraso,
            tipo='date',
            descricao='Pleitos com Data Pendência anterior ou igual a esta data serão considerados atrasados.'
        )
        db.session.add(config_atraso)
        print(f"  Configuração 'data_limite_pleitos_atrasados' adicionada com valor padrão: {data_padrao_atraso}.")
    else:
        print(f"  Configuração 'data_limite_pleitos_atrasados' já existe (valor atual: {config_atraso.valor}).")

    # NOVO: Configuração para Clientes Excluídos
    config_clientes_excluidos = Configuracao.query.filter_by(chave='clientes_excluidos').first()
    if not config_clientes_excluidos:
        # Transfira os clientes excluídos que estavam hardcoded em file_processing.py
        clientes_excluidos_padrao = ["J3 TECNOLOGIA E SISTEMAS LTDA"]
        config_clientes_excluidos = Configuracao(
            chave='clientes_excluidos',
            valor=json.dumps(clientes_excluidos_padrao), # Armazenar como JSON string
            tipo='list',
            descricao='Lista de clientes a serem excluídos globalmente da análise de pleitos.'
        )
        db.session.add(config_clientes_excluidos)
        print(f"  Configuração 'clientes_excluidos' adicionada com valor padrão: {clientes_excluidos_padrao}.")
    else:
        print(f"  Configuração 'clientes_excluidos' já existe (valor atual: {config_clientes_excluidos.valor}).")

    # NOVO: Configuração para Produtos Excluídos
    config_produtos_excluidos = Configuracao.query.filter_by(chave='produtos_excluidos').first()
    if not config_produtos_excluidos:
        # Exemplo: Produtos que continham "taxa" no nome. Ajuste esta lista se necessário.
        produtos_excluidos_padrao = ["taxa"] 
        config_produtos_excluidos = Configuracao(
            chave='produtos_excluidos',
            valor=json.dumps(produtos_excluidos_padrao), # Armazenar como JSON string
            tipo='list',
            descricao='Lista de produtos (ou partes de produtos) a serem excluídos globalmente da análise de pleitos.'
        )
        db.session.add(config_produtos_excluidos)
        print(f"  Configuração 'produtos_excluidos' adicionada com valor padrão: {produtos_excluidos_padrao}.")
    else:
        print(f"  Configuração 'produtos_excluidos' já existe (valor atual: {config_produtos_excluidos.valor}).")

    # NOVO: Configuração para Intervalo de Atualização da Base (em horas)
    config_intervalo_atualizacao = Configuracao.query.filter_by(chave='intervalo_atualizacao_base_horas').first()
    if not config_intervalo_atualizacao:
        config_intervalo_atualizacao = Configuracao(
            chave='intervalo_atualizacao_base_horas',
            valor="24", # Padrão de 24 horas
            tipo='integer',
            descricao='Intervalo em horas para a próxima atualização da base de pleitos.'
        )
        db.session.add(config_intervalo_atualizacao)
        print(f"  Configuração 'intervalo_atualizacao_base_horas' adicionada com valor padrão: 24 horas.")
    else:
        print(f"  Configuração 'intervalo_atualizacao_base_horas' já existe (valor atual: {config_intervalo_atualizacao.valor}).")

    # NOVO: Configuração para Logo na Impressão
    config_logo_impressao = Configuracao.query.filter_by(chave='logo_impressao_url').first()
    if not config_logo_impressao:
        config_logo_impressao = Configuracao(
            chave='logo_impressao_url',
            valor="", # Caminho vazio por padrão
            tipo='string',
            descricao='URL ou caminho da imagem da logo para cabeçalhos de impressão.'
        )
        db.session.add(config_logo_impressao)
        print(f"  Configuração 'logo_impressao_url' adicionada (vazia por padrão).")
    else:
        print(f"  Configuração 'logo_impressao_url' já existe (valor atual: {config_logo_impressao.valor}).")

    if Feriado.query.count() == 0:
        print("\n5. Inserindo feriados padrão no banco de dados...")
        feriados_padrao_nacional = [
            Feriado(data=date(2025, 1, 1), nome="Confraternização Universal", localidade="Nacional", tipo="Nacional"),
            Feriado(data=date(2025, 2, 20), nome="Carnaval (quinta)", localidade="Nacional", tipo="Ponto Facultativo"),
            Feriado(data=date(2025, 3, 3), nome="Carnaval (segunda)", localidade="Nacional", tipo="Ponto Facultativo"),
            Feriado(data=date(2025, 3, 4), nome="Carnaval (terça)", localidade="Nacional", tipo="Ponto Facultativo"),
            Feriado(data=date(2025, 4, 7), nome="Paixão de Cristo", localidade="Nacional", tipo="Nacional"),
            Feriado(data=date(2025, 4, 21), nome="Tiradentes", localidade="Nacional", tipo="Nacional"),
            Feriado(data=date(2025, 5, 1), nome="Dia do Trabalho", localidade="Nacional", tipo="Nacional"),
            Feriado(data=date(2025, 5, 29), nome="Corpus Christi", localidade="Nacional", tipo="Ponto Facultativo"),
            Feriado(data=date(2025, 9, 7), nome="Independência", localidade="Nacional", tipo="Nacional"),
            Feriado(data=date(2025, 10, 12), nome="N. Sra Aparecida", localidade="Nacional", tipo="Nacional"),
            Feriado(data=date(2025, 11, 2), nome="Finados", localidade="Nacional", tipo="Nacional"),
            Feriado(data=date(2025, 11, 15), nome="Proclamação da República", localidade="Nacional", tipo="Nacional"),
            Feriado(data=date(2025, 12, 25), nome="Natal", localidade="Nacional", tipo="Nacional"),
        ]
        feriados_padrao_sp = [
            Feriado(data=date(2025, 1, 25), nome="Aniversário de São Paulo", localidade="SP", tipo="Municipal"),
            Feriado(data=date(2025, 7, 9), nome="Revolução Constitucionalista", localidade="SP", tipo="Estadual"),
            Feriado(data=date(2025, 11, 20), nome="Consciência Negra", localidade="SP", tipo="Estadual"),
        ]
        feriados_padrao_rj = [
            Feriado(data=date(2025, 1, 20), nome="São Sebastião (Rio)", localidade="RJ", tipo="Municipal"),
            Feriado(data=date(2025, 4, 23), nome="São Jorge (Rio)", localidade="RJ", tipo="Municipal"),
            Feriado(data=date(2025, 11, 20), nome="Consciência Negra", localidade="RJ", tipo="Estadual"),
        ]

        for feriado in feriados_padrao_nacional:
            db.session.add(feriado)
        for feriado in feriados_padrao_sp:
            db.session.add(feriado)
        for feriado in feriados_padrao_rj:
            db.session.add(feriado)

        try:
            db.session.commit()
            print("  Feriados padrão inseridos com sucesso.")
        except Exception as e:
            db.session.rollback()
            print(f"  ERRO ao inserir feriados padrão: {e}")
    else:
        print("\n5. Feriados já existem no banco de dados. Pulando inserção de padrões.")

# ... (imports no topo do init_db.py) ...

    if AtividadeJuridica.query.count() == 0:
        print("\n6. Inserindo atividades jurídicas de exemplo no banco de dados...")
        atividades_exemplo = [
            # Exemplo de Squad Contratação
            AtividadeJuridica(tipo='Squad Contratação', assunto='ANÁLISE DE CONTRATO - Cliente A', data_criacao=date(2025, 5, 20), proprietario='Vinicius', criado_por='Augusto', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Squad Contratação', assunto='LIBERAÇÃO DE FLUXO - Cliente C', data_criacao=date(2025, 5, 25), proprietario='Joseane', criado_por='Larissa', prioridade='Normal', status='Pendente'),
            
            # Exemplos de Outros que DEVEM aparecer (com variações de assunto e nome)
            AtividadeJuridica(tipo='Outros', assunto='[ANÁLISE DE CONTRATO] - Cliente B', data_criacao=date(2025, 5, 15), proprietario='Maria', criado_por='Augusto Nascimento', prioridade='Solicitada', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='ID do Contrato 1234 - SOLICITAÇÃO DE DOCUMENTO - Cliente X', data_criacao=date(2025, 5, 22), proprietario='Augusto Nascimento', criado_por='Ana Carolina', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='ELABORACAO DE DOCUMENTOS para o Projeto Y', data_criacao=date(2025, 5, 18), proprietario='Larissa', criado_por='Vinicius', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='[SOLICITACAO DE DOCUMENTOS] - Contrato Z', data_criacao=date(2025, 5, 10), proprietario='Larissa', criado_por='Vinicius', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='ANÁLISE DE CONTRATO Cliente X', data_criacao=date(2025, 5, 26), proprietario='Augusto', criado_por='Augusto Nascimento de Almeida', prioridade='Normal', status='Pendente'), # Adicionado seu exemplo da planilha

            # Exemplos de Outros que NÃO DEVEM aparecer (com "arquivamento" ou assuntos inválidos)
            AtividadeJuridica(tipo='Outros', assunto='ARQUIVAMENTO DE DOCUMENTOS - Cliente Y', data_criacao=date(2025, 5, 20), proprietario='Augusto', criado_por='Maria', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='REUNIÃO COM CLIENTE', data_criacao=date(2025, 5, 21), proprietario='Vinicius', criado_por='Augusto', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='CONFERENCIA DE FATURA', data_criacao=date(2025, 5, 19), proprietario='Larissa', criado_por='Ana Carolina', prioridade='Normal', status='Pendente'),
        ]
        for atividade in atividades_exemplo:
            db.session.add(atividade)
        try:
            db.session.commit()
            print("  Atividades jurídicas de exemplo inseridas com sucesso.")
        except Exception as e:
            db.session.rollback()
            print(f"  ERRO ao inserir atividades jurídicas de exemplo: {e}")
    else:
        print("\n6. Atividades jurídicas já existem no banco de dados. Pulando inserção de exemplos.")

# NOVO: Configuração para Meta de SLA Mensal
    config_sla_meta = Configuracao.query.filter_by(chave='sla_meta_percentual').first()
    if not config_sla_meta:
        config_sla_meta = Configuracao(
            chave='sla_meta_percentual',
            valor="90", # Padrão de 90%
            tipo='integer',
            descricao='Meta percentual para o dashboard de SLA mensal.'
        )
        db.session.add(config_sla_meta)
        print(f"  Configuração 'sla_meta_percentual' adicionada com valor padrão: 90%.")
    else:
        print(f"  Configuração 'sla_meta_percentual' já existe (valor atual: {config_sla_meta.valor}).")

    try:
        db.session.commit()
        print("Configurações iniciais salvas/atualizadas com sucesso.")
    except Exception as e:
        db.session.rollback()
        print(f"ERRO ao salvar/atualizar configurações iniciais: {e}")

    print("\n--- init_db.py concluído! ---")
    print("Banco de dados inicializado com sucesso!")