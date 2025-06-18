from app import app, db
from models import User, Role

with app.app_context():
    print("\n--- Iniciando init_db.py ---")
    print("1. Criando/atualizando tabelas do banco de dados...")
    db.create_all() # Primeiro, cria todas as tabelas vazias

    # NOVO: Dicionário completo de permissões para cada role
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

    # === Processamento e persistência das Roles ===
    print("\n2. Processando e persistindo perfis (Roles)...")
    for role_name, permissions in roles_data.items():
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name)
            db.session.add(role)
            print(f"  Adicionando perfil '{role_name}' à sessão.")
        else:
            print(f"  Perfil '{role_name}' já existe. Verificando/atualizando permissões...")

        # Atualiza as permissões no objeto role (seja ele novo ou existente)
        for perm_name, perm_value in permissions.items():
            setattr(role, perm_name, perm_value)
            
        # Tenta commitar o perfil APÓS configurar suas permissões
        try:
            db.session.commit() # Commit individual para cada role
            print(f"  Perfil '{role_name}' salvo/atualizado com sucesso (ID: {role.id}).")
        except Exception as e:
            db.session.rollback() # Em caso de erro, desfaz a transação
            print(f"  ERRO ao salvar/atualizar perfil '{role_name}': {e}")
            print("  Isso pode impedir o funcionamento correto da aplicação. Verifique o models.py e erros anteriores.")
            # Se um perfil essencial falhar, pode ser necessário abortar.
            # continue # Não continue se a role não foi salva

    # Rebusca as roles para garantir que os objetos estejam ligados ao DB
    admin_role = Role.query.filter_by(name='Admin').first()
    consultor_role = Role.query.filter_by(name='Consultor').first()

    if not admin_role or not consultor_role:
        print("\nERRO CRÍTICO: Perfis 'Admin' ou 'Consultor' não foram encontrados/criados após persistência.")
        print("Verifique os logs acima para erros na criação de perfis. Não é possível continuar a inicialização de usuários.")
        # Pode forçar uma saída se roles críticas não existirem
        exit() # Aborta o script se roles essenciais não foram criadas
    
    # === Processamento e persistência do Usuário Admin ===
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
        db.session.commit() # Commit final para o usuário admin (se foi criado/atualizado)
        print("  Usuário 'admin' salvo/atualizado com sucesso.")
    except Exception as e:
        db.session.rollback()
        print(f"  ERRO ao salvar/atualizar usuário 'admin': {e}")
        print("  Isso pode impedir o login do usuário admin. Verifique o models.py e erros anteriores.")
    
    print("\n--- init_db.py concluído! ---")
    print("Banco de dados inicializado com sucesso!")