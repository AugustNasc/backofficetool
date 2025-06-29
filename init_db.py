from app import app, db
from models import User, Role, Configuracao, Feriado, AtividadeJuridica
from datetime import datetime, timedelta, date

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

    if AtividadeJuridica.query.count() == 0:
        print("\n6. Inserindo atividades jurídicas de exemplo no banco de dados...")
        atividades_exemplo = [
            AtividadeJuridica(tipo='Squad Contratação', assunto='ANÁLISE DE CONTRATO - Cliente A', data_criacao=date(2025, 5, 20), proprietario='Vinicius', criado_por='Augusto', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='SOLICITAÇÃO DE DOCUMENTO - Cliente B', data_criacao=date(2025, 5, 15), proprietario='Maria', criado_por='Augusto', prioridade='Solicitada', status='Pendente'),
            AtividadeJuridica(tipo='Squad Contratação', assunto='LIBERAÇÃO DE FLUXO - Cliente C', data_criacao=date(2025, 5, 25), proprietario='Joseane', criado_por='Larissa', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Squad Contratação', assunto='ANÁLISE DE CONTRATO - Cliente D', data_criacao=date(2025, 5, 10), proprietario='Vinicius', criado_por='Augusto', prioridade='Normal', status='Pendente', areas_pendentes='Produtos,Faturamento'),
            AtividadeJuridica(tipo='Squad Contratação', assunto='ANÁLISE DE CONTRATO - Cliente E', data_criacao=date(2025, 5, 18), proprietario='Ana', criado_por='Larissa', prioridade='Normal', status='Concluída'),
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

    try:
        db.session.commit()
        print("Configurações iniciais salvas/atualizadas com sucesso.")
    except Exception as e:
        db.session.rollback()
        print(f"ERRO ao salvar/atualizar configurações iniciais: {e}")

    print("\n--- init_db.py concluído! ---")
    print("Banco de dados inicializado com sucesso!")