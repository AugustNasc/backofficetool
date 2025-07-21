from app import app, db
from models import User, Role, Configuracao, Feriado, AtividadeJuridica
from datetime import datetime, timedelta, date
import json

with app.app_context():
    print("\n--- Iniciando inicialização do banco de dados ---")
    print("1. Criando/atualizando tabelas...")
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

    print("\n2. Processando perfis (Roles)...")
    for role_name, permissions in roles_data.items():
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name)
            db.session.add(role)
            print(f"  Adicionando perfil '{role_name}'.")
        else:
            print(f"  Perfil '{role_name}' já existe. Atualizando permissões...")

        for perm_name, perm_value in permissions.items():
            setattr(role, perm_name, perm_value)

        try:
            db.session.commit()
            print(f"  Perfil '{role_name}' salvo/atualizado.")
        except Exception as e:
            db.session.rollback()
            print(f"  ERRO ao salvar/atualizar perfil '{role_name}': {e}")
            print("  Verifique o models.py e erros anteriores.")

    admin_role = Role.query.filter_by(name='Admin').first()
    consultor_role = Role.query.filter_by(name='Consultor').first()

    if not admin_role or not consultor_role:
        print("\nERRO CRÍTICO: Perfis 'Admin' ou 'Consultor' não encontrados/criados.")
        print("Não é possível continuar a inicialização de usuários.")
        exit()

    print("\n3. Processando usuário 'admin'...")
    admin_user = User.query.filter_by(username='admin').first()
    if not admin_user:
        admin_user = User(username='admin', role=admin_role)
        admin_user.set_password('admin')
        db.session.add(admin_user)
        print("  Usuário 'admin' adicionado.")
    elif admin_user.role != admin_role:
        admin_user.role = admin_role
        print("  Usuário 'admin' existente; associando ao perfil 'Admin'.")
    else:
        print("  Usuário 'admin' já existe e tem o perfil 'Admin'.")

    try:
        db.session.commit()
        print("  Usuário 'admin' salvo/atualizado.")
    except Exception as e:
        db.session.rollback()
        print(f"  ERRO ao salvar/atualizar usuário 'admin': {e}")

    print("\n4. Verificando configurações iniciais...")
    data_padrao_atraso = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    config_keys = {
        'data_limite_pleitos_atrasados': {'value': data_padrao_atraso, 'type': 'date', 'desc': 'Pleitos com Data Pendência anterior ou igual a esta data serão considerados atrasados.'},
        'clientes_excluidos': {'value': json.dumps(["J3 TECNOLOGIA E SISTEMAS LTDA"]), 'type': 'list', 'desc': 'Lista de clientes a serem excluídos globalmente da análise de pleitos.'},
        'produtos_excluidos': {'value': json.dumps(["taxa"]), 'type': 'list', 'desc': 'Lista de produtos (ou partes de produtos) a serem excluídos globalmente da análise de pleitos.'},
        'intervalo_atualizacao_base_horas': {'value': "24", 'type': 'integer', 'desc': 'Intervalo em horas para a próxima atualização da base de pleitos.'},
        'logo_impressao_url': {'value': "", 'type': 'string', 'desc': 'URL ou caminho da imagem da logo para cabeçalhos de impressão.'},
        'sla_meta_percentual': {'value': "90", 'type': 'integer', 'desc': 'Meta percentual para o dashboard de SLA mensal.'},
    }

    for key, data in config_keys.items():
        config_entry = Configuracao.query.filter_by(chave=key).first()
        if not config_entry:
            config_entry = Configuracao(chave=key, valor=data['value'], tipo=data['type'], descricao=data['desc'])
            db.session.add(config_entry)
            print(f"  Configuração '{key}' adicionada com valor padrão.")
        else:
            print(f"  Configuração '{key}' já existe (valor atual: {config_entry.valor}).")

    if Feriado.query.count() == 0:
        print("\n5. Inserindo feriados padrão...")
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

        db.session.add_all(feriados_padrao_nacional)
        db.session.add_all(feriados_padrao_sp)
        db.session.add_all(feriados_padrao_rj)

        try:
            db.session.commit()
            print("  Feriados padrão inseridos.")
        except Exception as e:
            db.session.rollback()
            print(f"  ERRO ao inserir feriados padrão: {e}")
    else:
        print("\n5. Feriados já existem no banco de dados. Pulando inserção de padrões.")

    if AtividadeJuridica.query.count() == 0:
        print("\n6. Inserindo atividades jurídicas de exemplo...")
        atividades_exemplo = [
            AtividadeJuridica(tipo='Squad Contratação', assunto='ANÁLISE DE CONTRATO - Cliente A', data_criacao=date(2025, 5, 20), proprietario='Vinicius', criado_por='Augusto', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Squad Contratação', assunto='LIBERAÇÃO DE FLUXO - Cliente C', data_criacao=date(2025, 5, 25), proprietario='Joseane', criado_por='Larissa', prioridade='Normal', status='Pendente'),
            
            AtividadeJuridica(tipo='Outros', assunto='[ANÁLISE DE CONTRATO] - Cliente B', data_criacao=date(2025, 5, 15), proprietario='Maria', criado_por='Augusto Nascimento', prioridade='Solicitada', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='ID do Contrato 1234 - SOLICITAÇÃO DE DOCUMENTO - Cliente X', data_criacao=date(2025, 5, 22), proprietario='Augusto Nascimento', criado_por='Ana Carolina', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='ELABORACAO DE DOCUMENTOS para o Projeto Y', data_criacao=date(2025, 5, 18), proprietario='Larissa', criado_por='Vinicius', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='[SOLICITACAO DE DOCUMENTOS] - Contrato Z', data_criacao=date(2025, 5, 10), proprietario='Larissa', criado_por='Vinicius', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='ANÁLISE DE CONTRATO Cliente X', data_criacao=date(2025, 5, 26), proprietario='Augusto', criado_por='Augusto Nascimento de Almeida', prioridade='Normal', status='Pendente'),

            AtividadeJuridica(tipo='Outros', assunto='ARQUIVAMENTO DE DOCUMENTOS - Cliente Y', data_criacao=date(2025, 5, 20), proprietario='Augusto', criado_por='Maria', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='REUNIÃO COM CLIENTE', data_criacao=date(2025, 5, 21), proprietario='Vinicius', criado_por='Augusto', prioridade='Normal', status='Pendente'),
            AtividadeJuridica(tipo='Outros', assunto='CONFERENCIA DE FATURA', data_criacao=date(2025, 5, 19), proprietario='Larissa', criado_por='Ana Carolina', prioridade='Normal', status='Pendente'),
        ]
        db.session.add_all(atividades_exemplo)
        try:
            db.session.commit()
            print("  Atividades jurídicas de exemplo inseridas.")
        except Exception as e:
            db.session.rollback()
            print(f"  ERRO ao inserir atividades jurídicas de exemplo: {e}")
    else:
        print("\n6. Atividades jurídicas já existem no banco de dados. Pulando inserção de exemplos.")

    try:
        db.session.commit()
        print("Configurações iniciais salvas/atualizadas.")
    except Exception as e:
        db.session.rollback()
        print(f"ERRO ao salvar/atualizar configurações iniciais: {e}")

    print("\n--- Inicialização do banco de dados concluída! ---")