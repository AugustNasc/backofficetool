import re
import io
import os
import uuid
import json
import logging
import pandas as pd
import requests
import statistics
import json 
import unicodedata 

from datetime import datetime, timedelta, date
from uuid import uuid4
from io import BytesIO
from functools import wraps

from models import db, User, Log, Pleito, Role, Configuracao, Feriado, AtividadeJuridica, Cancelamento, SlaMensal


from flask import (
    Flask, render_template, request, redirect, url_for, session, flash,
    send_from_directory, abort, make_response, send_file, current_app, jsonify
)
from flask_wtf import FlaskForm
from wtforms import StringField, validators

from werkzeug.utils import secure_filename

# modelos e config
from models import db, User, Log, Pleito, Role, Configuracao, Feriado, AtividadeJuridica
from config import Config

# Bibliotecas de terceiros
from fpdf import FPDF
from dateutil.relativedelta import relativedelta
import xlsxwriter

# Utils do projeto
from utils.pdf_generator import preparar_base_pdf, exportar_sla_pdf
from utils.excel_export import preparar_base_excel, exportar_sla_excel, exportar_logs_excel
from utils.file_processing import (
    process_hotlines,
    analyze_pleitos, filtrar_clientes_excluidos, safe_float
)
from utils.dias_uteis import dias_uteis_entre_datas
from utils.value_correction import corrigir_valor
from utils.auth import authenticate_user


from models import db, User, Log, Pleito, Role, Configuracao, Feriado, AtividadeJuridica, Cancelamento # Adicionar Cancelamento aqui

# ===== FIM DOS IMPORTS =====

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============= HANDLERS DE ERRO =============
@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f'Erro 500: {str(e)}')
    return render_template('errors/500.html', error=str(e)), 500

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

# ============= FUNÇÕES AUXILIARES DE PERMISSÃO =============

def role_required(role_name):
    """
    Decorador que verifica se o usuário logado possui uma role específica.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                flash('Você precisa estar logado para acessar esta página.', 'danger')
                return redirect(url_for('login'))
            user = User.query.filter_by(username=session['username']).first()
            if user and user.role.name == role_name:
                return f(*args, **kwargs)
            else:
                flash('Você não tem permissão para acessar esta página.', 'danger')
                return redirect(url_for('menu')) # Redireciona para o menu ou uma página de erro 403
        return decorated_function
    return decorator

def permission_required(permission_name):
    """
    Decorador que verifica se o usuário logado possui uma permissão específica
    (ex: can_access_pleitos, can_edit_all, etc.).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'username' not in session:
                flash('Você precisa estar logado para acessar esta funcionalidade.', 'danger')
                return redirect(url_for('login'))
            user = User.query.filter_by(username=session['username']).first()
            if user and hasattr(user.role, permission_name) and getattr(user.role, permission_name):
                return f(*args, **kwargs)
            else:
                flash('Você não tem permissão para realizar esta ação ou acessar esta página.', 'danger')
                return redirect(url_for('menu')) # Ou abort(403)
        return decorated_function
    return decorator

# Função para passar as permissões do usuário para os templates
@app.before_request
def load_user_permissions():
    if 'username' in session:
        user = User.query.filter_by(username=session['username']).first()
        if user:
            # Verifica se user.role não é None. Se for, pode ser um usuário antigo sem role_id, ou um bug.
            if user.role:
                session['user_role'] = user.role.name
                # Carrega todas as permissões do usuário na sessão
                for col in user.role.__table__.columns:
                    if col.name.startswith('can_') or col.name.startswith('is_'):
                        session[col.name] = getattr(user.role, col.name)
            else:
                # Situação de usuário existe mas sem role (provavelmente DB desatualizado antes de migrations ou erro na criação)
                # Tenta atribuir uma role padrão (ex: Consultor) para tentar recuperar, ou limpa a sessão.
                # Por segurança, vamos limpar a sessão e forçar um novo login/recriação do user
                session.clear()
                flash('Erro de configuração do usuário: perfil não encontrado. Por favor, faça login novamente.', 'danger')
                logger.error(f"Usuário '{user.username}' (ID: {user.id}) encontrado na sessão mas sem ROLE associada.")
                return redirect(url_for('login'))
    else:
        # Usuário não logado. Carrega permissões de 'Guest' ou um Role temporário 'Guest'.
        guest_role = Role.query.filter_by(name='Guest').first()
        if not guest_role:
            # Isso só deve acontecer se 'Guest' não foi criado no init_db.py.
            # Cria um Role temporário em memória (não persistido) com todas as permissões False
            # para evitar AttributeError em templates.
            guest_role = Role(name='Guest')
            for col in Role.__table__.columns:
                if col.name.startswith('can_') or col.name.startswith('is_'):
                    setattr(guest_role, col.name, False)
            logger.warning("Role 'Guest' não encontrada no DB. Usando objeto temporário.")

        session['user_role'] = guest_role.name
        for col in guest_role.__table__.columns:
            if col.name.startswith('can_') or col.name.startswith('is_'):
                session[col.name] = getattr(guest_role, col.name)

    # Colocar isso após as verificações acima para evitar que erros interrompam o carregamento.
    # Exemplo: session.permanent = True # Se quiser sessões mais longas
    current_app.logger.debug(f"Permissões carregadas para {session.get('username', 'Guest')}: {session.get('user_role')}")
    # current_app.logger.debug(f"Can access pleitos: {session.get('can_access_pleitos')}")

# ============= FUNÇÕES AUXILIARES =============
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'xlsx', 'xls'}

def format_currency_global(value): # Renomeada para evitar conflito com local
    try:
        if pd.isna(value) or value is None:
            return '-'
        value = float(value)
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(value)

@app.template_filter('format_date')
def format_date_filter(date_str):
    try:
        if isinstance(date_str, str):
            return datetime.strptime(date_str, '%d/%m/%Y').strftime('%d/%m/%Y')
        elif isinstance(date_str, datetime):
            return date_str.strftime('%d/%m/%Y')
        elif isinstance(date_str, date): # Adicionado para objetos date puros
            return date_str.strftime('%d/%m/%Y')
        return date_str
    except:
        return date_str

# ============= ROTAS PRINCIPAIS =============
@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('menu'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if authenticate_user(username, password):
            session['username'] = username
            user = User.query.filter_by(username=username).first()
            user_id = user.id if user else None
            new_log = Log(
                action="LOGIN",
                details=f"Usuário {username} logou no sistema.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            flash('Login bem-sucedido!', 'success')
            return redirect(url_for('menu'))
        else:
            flash('Usuário ou senha incorretos', 'danger')
            new_log = Log(
                action="LOGIN_FALHA",
                details=f"Tentativa de login falha para o usuário: {username}",
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Validar dados de entrada
        if not username or not password:
            flash('Usuário e senha são obrigatórios.', 'danger')
            return render_template('register.html')

        if len(username) < 3 or len(username) > 50:
            flash('O nome de usuário deve ter entre 3 e 50 caracteres.', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('A senha deve ter no mínimo 6 caracteres.', 'danger')
            return render_template('register.html')

        # Verificar se o usuário já existe
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Nome de usuário já existe. Escolha outro.', 'danger')
            return render_template('register.html')

        # Atribuir a role 'Consultor' por padrão
        consultor_role = Role.query.filter_by(name='Consultor').first()
        if not consultor_role:
            # Isso não deveria acontecer se init_db.py rodou certo
            flash('Erro de configuração: perfil "Consultor" não encontrado. Contate o administrador.', 'danger')
            logger.error("Perfil 'Consultor' não encontrado ao tentar registrar um novo usuário.")
            return render_template('register.html')

        new_user = User(username=username, role=consultor_role)
        new_user.set_password(password)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registro bem-sucedido! Você já pode fazer login.', 'success')
            # Log de registro
            log_user_id = new_user.id # Pega o ID do usuário recém-criado
            new_log = Log(
                action="REGISTRO",
                details=f"Novo usuário '{username}' registrado com o perfil '{consultor_role.name}'.",
                user_id=log_user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback() # Reverte a transação em caso de erro
            flash(f'Erro ao registrar usuário: {str(e)}', 'danger')
            logger.error(f"Erro ao registrar usuário {username}: {str(e)}")

    return render_template('register.html')

@app.route('/logout')
def logout():
    username = session.get('username')
    user_id = None
    if username:
        user = User.query.filter_by(username=username).first()
        if user:
            user_id = user.id

    session.clear()
    flash('Você foi desconectado com sucesso.', 'info')

    new_log = Log(
        action="LOGOUT",
        details=f"Usuário {username if username else 'desconhecido'} desconectado.",
        user_id=user_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(new_log)
    db.session.commit()

    return redirect(url_for('login'))

@app.route('/manage_users', methods=['GET', 'POST'])
@permission_required('can_manage_users') # Apenas Admin pode gerenciar usuários
def manage_users():
    users = User.query.options(db.joinedload(User.role)).all() # Carrega usuários com suas roles
    roles = Role.query.all() # Para o dropdown de roles

    if request.method == 'POST':
        action = request.form.get('action')
        user_id = request.form.get('user_id')

        user_to_act = User.query.get(user_id)
        if not user_to_act:
            flash('Usuário não encontrado.', 'danger')
            return redirect(url_for('manage_users'))

        if action == 'edit_role':
            new_role_id = request.form.get('new_role_id')
            new_role = Role.query.get(new_role_id)
            if new_role:
                old_role_name = user_to_act.role.name if user_to_act.role else 'N/A'
                user_to_act.role = new_role
                db.session.commit()
                flash(f'Perfil do usuário {user_to_act.username} atualizado para {new_role.name}!', 'success')

                # Log da edição de perfil
                editor_user = User.query.filter_by(username=session['username']).first()
                log_details = f"Perfil de '{user_to_act.username}' (ID: {user_to_act.id}) alterado de '{old_role_name}' para '{new_role.name}'."
                new_log = Log(action="EDIT_USER_ROLE", details=log_details, user_id=editor_user.id, timestamp=datetime.utcnow())
                db.session.add(new_log)
                db.session.commit()

            else:
                flash('Perfil selecionado inválido.', 'danger')

        elif action == 'delete_user':
            if user_to_act.username == session['username']:
                flash('Você não pode excluir seu próprio usuário enquanto está logado.', 'danger')
                return redirect(url_for('manage_users'))

            # Não permitir exclusão do Admin principal se for o único Admin
            if user_to_act.role.name == 'Admin' and User.query.filter_by(role=Role.query.filter_by(name='Admin').first()).count() <= 1:
                 flash('Não é possível excluir o único usuário Admin.', 'danger')
                 return redirect(url_for('manage_users'))

            # Log da exclusão (antes de excluir do DB)
            editor_user = User.query.filter_by(username=session['username']).first()
            log_details = f"Usuário '{user_to_act.username}' (ID: {user_to_act.id}) com perfil '{user_to_act.role.name}' excluído."
            new_log = Log(action="DELETE_USER", details=log_details, user_id=editor_user.id, timestamp=datetime.utcnow())
            db.session.add(new_log)
            db.session.commit() # Commit para garantir que o log seja salvo antes do user ser deletado

            db.session.delete(user_to_act)
            db.session.commit()
            flash(f'Usuário {user_to_act.username} excluído com sucesso.', 'success')

        elif action == 'reset_password':
            # Implementar um formulário para redefinir a senha com uma nova (ou genérica)
            # Por simplicidade, vamos usar uma senha temporária 'mudar123'
            temp_password = 'mudar123'
            user_to_act.set_password(temp_password)
            db.session.commit()
            flash(f"Senha do usuário {user_to_act.username} redefinida para '{temp_password}'. Por favor, peça para o usuário alterar a senha no próximo login.", 'info')

            # Log da redefinição de senha
            editor_user = User.query.filter_by(username=session['username']).first()
            log_details = f"Senha do usuário '{user_to_act.username}' (ID: {user_to_act.id}) redefinida."
            new_log = Log(action="RESET_PASSWORD", details=log_details, user_id=editor_user.id, timestamp=datetime.utcnow())
            db.session.add(new_log)
            db.session.commit()

        return redirect(url_for('manage_users'))

    return render_template('manage_users.html', users=users, roles=roles)

# Rota de Admin Settings
@app.route('/admin_settings', methods=['GET', 'POST'])
@permission_required('can_manage_users') # Apenas Admin pode acessar configurações gerais
def admin_settings():
    config_atraso = Configuracao.query.filter_by(chave='data_limite_pleitos_atrasados').first()
    data_limite_atraso = config_atraso.valor if config_atraso else (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d') # Valor padrão se não existir

    config_clientes_excluidos = Configuracao.query.filter_by(chave='clientes_excluidos').first()
    clientes_excluidos = json.loads(config_clientes_excluidos.valor) if config_clientes_excluidos and config_clientes_excluidos.valor else []
    clientes_excluidos_str = ", ".join(clientes_excluidos)

    config_produtos_excluidos = Configuracao.query.filter_by(chave='produtos_excluidos').first()
    produtos_excluidos = json.loads(config_produtos_excluidos.valor) if config_produtos_excluidos and config_produtos_excluidos.valor else []
    produtos_excluidos_str = ", ".join(produtos_excluidos)

    # Recuperar Intervalo de Atualização
    config_intervalo_atualizacao = Configuracao.query.filter_by(chave='intervalo_atualizacao_base_horas').first()
    intervalo_atualizacao_horas = config_intervalo_atualizacao.valor if config_intervalo_atualizacao else "24" # Padrão
    
    # Recuperar URL da Logo de Impressão
    config_logo_impressao = Configuracao.query.filter_by(chave='logo_impressao_url').first()
    logo_impressao_url = config_logo_impressao.valor if config_logo_impressao else ""

    # NOVO: Recuperar Meta de SLA
    config_sla_meta = Configuracao.query.filter_by(chave='sla_meta_percentual').first()
    sla_meta_percentual = config_sla_meta.valor if config_sla_meta else "90" # Padrão

    if request.method == 'POST':
        nova_data_str = request.form.get('data_limite_pleitos_atrasados')
        try:
            datetime.strptime(nova_data_str, '%Y-%m-%d')
            config_atraso = Configuracao.query.filter_by(chave='data_limite_pleitos_atrasados').first()
            if config_atraso:
                config_atraso.valor = nova_data_str
            else:
                config_atraso = Configuracao(chave='data_limite_pleitos_atrasados', valor=nova_data_str, tipo='date', descricao='Pleitos com Data Pendência anterior ou igual a esta data serão considerados atrasados.')
                db.session.add(config_atraso)
            
            clientes_excluidos_input = request.form.get('clientes_excluidos_input', '').strip()
            clientes_list = [c.strip() for c in clientes_excluidos_input.split(',') if c.strip()]
            clientes_list_json = json.dumps(clientes_list)

            config_clientes_excluidos = Configuracao.query.filter_by(chave='clientes_excluidos').first()
            if config_clientes_excluidos:
                config_clientes_excluidos.valor = clientes_list_json
            else:
                config_clientes_excluidos = Configuracao(chave='clientes_excluidos', valor=clientes_list_json, tipo='list', descricao='Lista de clientes a serem excluídos globalmente da análise de pleitos.')
                db.session.add(config_clientes_excluidos)
            
            produtos_excluidos_input = request.form.get('produtos_excluidos_input', '').strip()
            produtos_list = [p.strip() for p in produtos_excluidos_input.split(',') if p.strip()]
            produtos_list_json = json.dumps(produtos_list)

            config_produtos_excluidos = Configuracao.query.filter_by(chave='produtos_excluidos').first()
            if config_produtos_excluidos:
                config_produtos_excluidos.valor = produtos_list_json
            else:
                config_produtos_excluidos = Configuracao(chave='produtos_excluidos', valor=produtos_list_json, tipo='list', descricao='Lista de produtos (ou partes de produtos) a serem excluídos globalmente da análise de pleitos.')
                db.session.add(config_produtos_excluidos)

            # Lógica para Intervalo de Atualização da Base
            intervalo_atualizacao_input = request.form.get('intervalo_atualizacao_base_horas', '').strip()
            try:
                intervalo_atualizacao_int = int(intervalo_atualizacao_input)
                if not (1 <= intervalo_atualizacao_int <= 720): # Limite entre 1 hora e 30 dias (720 horas)
                    flash('Intervalo de atualização deve ser entre 1 e 720 horas.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('admin_settings'))
            except ValueError:
                flash('Intervalo de atualização inválido. Use um número inteiro.', 'danger')
                db.session.rollback()
                return redirect(url_for('admin_settings'))

            config_intervalo_atualizacao = Configuracao.query.filter_by(chave='intervalo_atualizacao_base_horas').first()
            if config_intervalo_atualizacao:
                config_intervalo_atualizacao.valor = str(intervalo_atualizacao_int)
            else:
                config_intervalo_atualizacao = Configuracao(chave='intervalo_atualizacao_base_horas', valor=str(intervalo_atualizacao_int), tipo='integer', descricao='Intervalo em horas para a próxima atualização da base de pleitos.')
                db.session.add(config_intervalo_atualizacao)

            # Lógica para Upload e URL da Logo de Impressão
            logo_file = request.files.get('logo_impressao_file')
            logo_url_input = request.form.get('logo_impressao_url_manual', '').strip()
            
            logo_path_to_save = ""

            if logo_file and logo_file.filename:
                allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'svg'}
                if '.' in logo_file.filename and logo_file.filename.rsplit('.', 1)[1].lower() in allowed_image_extensions:
                    os.makedirs(app.config['UPLOAD_LOGO_FOLDER'], exist_ok=True)
                    filename = secure_filename(f"logo_{uuid.uuid4().hex}_{logo_file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_LOGO_FOLDER'], filename)
                    logo_file.save(filepath)
                    logo_path_to_save = url_for('uploaded_logo', filename=filename) # URL para servir a logo
                else:
                    flash('Tipo de arquivo de logo inválido. Apenas PNG, JPG, JPEG, GIF, SVG são permitidos.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('admin_settings'))
            elif logo_url_input:
                logo_path_to_save = logo_url_input
            else:
                # Se nenhum arquivo ou URL foi fornecido, verifica se é para limpar a logo existente
                if request.form.get('clear_logo_impressao') == 'true':
                    logo_path_to_save = "" # Limpa a URL
                else:
                    # Se não foi para limpar, mantém a URL existente
                    config_logo_impressao_existente = Configuracao.query.filter_by(chave='logo_impressao_url').first()
                    logo_path_to_save = config_logo_impressao_existente.valor if config_logo_impressao_existente else ""


            config_logo_impressao = Configuracao.query.filter_by(chave='logo_impressao_url').first()
            if config_logo_impressao:
                config_logo_impressao.valor = logo_path_to_save
            else:
                config_logo_impressao = Configuracao(chave='logo_impressao_url', valor=logo_path_to_save, tipo='string', descricao='URL ou caminho da imagem da logo para cabeçalhos de impressão.')
                db.session.add(config_logo_impressao)

            # NOVO: Lógica para Meta de SLA
            sla_meta_input = request.form.get('sla_meta_percentual', '').strip()
            try:
                sla_meta_int = int(sla_meta_input)
                if not (0 <= sla_meta_int <= 100): # Limite entre 0 e 100
                    flash('A meta de SLA deve ser entre 0 e 100%.', 'danger')
                    db.session.rollback()
                    return redirect(url_for('admin_settings'))
            except ValueError:
                flash('Meta de SLA inválida. Use um número inteiro.', 'danger')
                db.session.rollback()
                return redirect(url_for('admin_settings'))

            config_sla_meta = Configuracao.query.filter_by(chave='sla_meta_percentual').first()
            if config_sla_meta:
                config_sla_meta.valor = str(sla_meta_int)
            else:
                config_sla_meta = Configuracao(chave='sla_meta_percentual', valor=str(sla_meta_int), tipo='integer', descricao='Meta percentual para o dashboard de SLA mensal.')
                db.session.add(config_sla_meta)


            db.session.commit() # Commit de todas as mudanças

            user = User.query.filter_by(username=session['username']).first()
            user_id = user.id if user else None
            new_log = Log(
                action="UPDATE_ADMIN_SETTINGS",
                details=f"Configurações gerais atualizadas: Data Limite Atrasos='{nova_data_str}', Clientes Excluídos='{clientes_excluidos_input}', Produtos Excluídos='{produtos_excluidos_input}', Intervalo Atualização='{intervalo_atualizacao_input} horas', Logo Impressão='{logo_path_to_save}', Meta SLA='{sla_meta_input}%'.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

            flash(f'Configurações atualizadas com sucesso!', 'success')
            return redirect(url_for('admin_settings'))

        except ValueError:
            flash('Formato de data inválido. Por favor, use AAAA-MM-DD.', 'danger')
            db.session.rollback() # Rollback em caso de erro na data
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao salvar configurações: {str(e)}', 'danger')
            logger.error(f"Erro ao salvar configurações gerais: {str(e)}")

    return render_template(
        'admin_settings.html',
        data_limite_atraso=data_limite_atraso,
        clientes_excluidos_str=clientes_excluidos_str,
        produtos_excluidos_str=produtos_excluidos_str,
        intervalo_atualizacao_horas=intervalo_atualizacao_horas,
        logo_impressao_url=logo_impressao_url,
        sla_meta_percentual=sla_meta_percentual # NOVO
    )


@app.route('/menu')
@permission_required('can_view_all') # Todos que podem acessar o menu
def menu():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('menu.html')

@app.route('/principal', methods=['GET', 'POST'])
@permission_required('can_access_pleitos') # Acesso à funcionalidade de pleitos
def principal():
    from collections import defaultdict

    def format_currency_local(valor): # Manteve localmente para o escopo desta função
        try:
            return "R$ {:,.2f}".format(float(valor)).replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return valor

    if request.method == 'POST' and 'file' in request.files and request.files['file'].filename:
        # Verifica permissão para upload ANTES de processar
        if not session.get('can_upload_all'):
            flash('Você não tem permissão para carregar planilhas.', 'danger')
            return redirect(url_for('principal'))

        session.pop('current_file', None)
        session.pop('filter_column', None)
        session.pop('filter_value', None)

    if request.method == 'POST':
        file = request.files['file']
        if file.filename == '':
            flash('Nenhum arquivo selecionado', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            try:
                df = pd.read_excel(file)
                required_columns = ['Consultor', 'Cliente', 'Produto', 'Data Pendência', 'Valor', 'Fase', 'Código de Controle']
                if not all(col in df.columns for col in required_columns):
                    missing = [col for col in required_columns if col not in df.columns]
                    flash(f'Planilha inválida. Colunas faltando: {", ".join(missing)}', 'danger')
                    return redirect(request.url)
                filename = secure_filename(file.filename)
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.seek(0)
                file.save(filepath)
                session['current_file'] = filename
                flash('Planilha carregada com sucesso!', 'success')

                user = User.query.filter_by(username=session['username']).first()
                user_id = user.id if user else None
                new_log = Log(
                    action="UPLOAD_PLANILHA",
                    details=f"Planilha '{filename}' de pleitos carregada.",
                    user_id=user_id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_log)
                db.session.commit()

            except Exception as e:
                logger.error(f'Erro ao processar arquivo: {str(e)}')
                flash(f'Erro ao processar arquivo: {str(e)}', 'danger')
                return redirect(request.url)
            return redirect(url_for('principal'))

    display_data = None
    data_length = 0
    resumo = []
    ultima_carga_dt = None # Inicializa para o caso de não ter arquivo
    proxima_atualizacao_dt = None # Inicializa para o caso de não ter arquivo

    if 'current_file' in session:
        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_file'])

            # NOVO: Lógica para data de carregamento e próxima atualização
            ultima_carga_timestamp = os.path.getmtime(filepath)
            ultima_carga_dt = datetime.fromtimestamp(ultima_carga_timestamp)

            config_intervalo_atualizacao = Configuracao.query.filter_by(chave='intervalo_atualizacao_base_horas').first()
            intervalo_horas = int(config_intervalo_atualizacao.valor) if config_intervalo_atualizacao and config_intervalo_atualizacao.valor.isdigit() else 24
            
            proxima_atualizacao_dt = ultima_carga_dt + timedelta(hours=intervalo_horas)
            
            df = pd.read_excel(filepath)

            # NOVO: Recuperar clientes e produtos excluídos do DB
            config_clientes_excluidos = Configuracao.query.filter_by(chave='clientes_excluidos').first()
            clientes_excluidos_do_db = json.loads(config_clientes_excluidos.valor) if config_clientes_excluidos and config_clientes_excluidos.valor else []

            config_produtos_excluidos = Configuracao.query.filter_by(chave='produtos_excluidos').first()
            produtos_excluidos_do_db = json.loads(config_produtos_excluidos.valor) if config_produtos_excluidos and config_produtos_excluidos.valor else []

            df['Cliente'] = df['Cliente'].astype(str).str.strip()
            df['Consultor'] = df['Consultor'].astype(str).str.strip()

            contas_transicao = session.get('contas_transicao')

            if contas_transicao:
                transicao_df = pd.DataFrame(contas_transicao)
                transicao_df['Cliente'] = transicao_df['Cliente'].astype(str).str.strip()
                transicao_df['Venda Realizada por'] = transicao_df['Venda Realizada por'].astype(str).str.strip()
                transicao_df['Gestão Atual'] = transicao_df['Gestão Atual'].astype(str).str.strip()
                for idx, row in transicao_df.iterrows():
                    cliente = row['Cliente']
                    vendedor = row['Venda Realizada por']
                    gestao_atual = row['Gestão Atual']
                    if vendedor and gestao_atual and vendedor != gestao_atual:
                        mask_out = (df['Cliente'] == cliente) & (df['Consultor'] == gestao_atual)
                        df = df[~mask_out]
                        linhas_cliente = df[(df['Cliente'] == cliente)]
                        if not linhas_cliente.empty:
                            mask_destino = (df['Cliente'] == cliente) & (df['Consultor'] == vendedor)
                            if not df[mask_destino].any().any():
                                for _, pleito in linhas_cliente.iterrows():
                                    nova_row = pleito.copy()
                                    nova_row['Consultor'] = vendedor
                                    df = pd.concat([df, pd.DataFrame([nova_row])], ignore_index=True)

            filter_column = session.get('filter_column', 'Consultor')
            filter_value = session.get('filter_value', '')

            # NOVO: Chamar analyze_pleitos passando as listas de exclusão
            # Este analyze_pleitos é a primeira e principal aplicação de filtros.
            df = analyze_pleitos(df, consultor_filter="", clientes_excluidos_list=clientes_excluidos_do_db, produtos_excluidos_list=produtos_excluidos_do_db)

            # O filtro de coluna e valor abaixo deve ser aplicado *APÓS* analyze_pleitos,
            # pois analyze_pleitos já faz a filtragem principal e de hotlines.
            # Seu código já aplica o filtro de coluna e valor depois de analyze_pleitos,
            # então ele deve continuar a fazer isso, mas agora em um DataFrame já pré-filtrado.
            if filter_value: 
                if filter_column == 'Valor':
                    try:
                        filter_num = float(filter_value)
                        df = df[df[filter_column] == filter_num]
                    except ValueError:
                        pass
                elif filter_column == 'Data Pendência':
                    try:
                        filter_date = pd.to_datetime(filter_value, dayfirst=True).strftime('%d/%m/%Y')
                        df = df[df[filter_column].astype(str).str.contains(filter_date)]
                    except:
                        pass
                else:
                    df = df[df[filter_column].astype(str).str.contains(filter_value, case=False, na=False)]

            display_data = [{
                'Consultor': row.get('Consultor', ''),
                'Cliente': row.get('Cliente', ''),
                'Produto': row.get('Produto', ''),
                'Data Pendência': row.get('Data Pendência', ''),
                'Valor': format_currency_local(row.get('Valor', ''))
            } for _, row in df.head(20).iterrows()]
            data_length = len(df)

            # OBTENDO A DATA LIMITE DE ATRASO DO BANCO DE DADOS
            config_atraso = Configuracao.query.filter_by(chave='data_limite_pleitos_atrasados').first()
            if config_atraso and config_atraso.valor:
                try:
                    # Usar datetime.strptime para converter a string para objeto date
                    threshold_date = datetime.strptime(config_atraso.valor, '%Y-%m-%d').date()
                except ValueError:
                    logger.warning(f"Data limite de atraso configurada ({config_atraso.valor}) inválida. Usando data atual.")
                    threshold_date = datetime.now().date()
            else:
                threshold_date = datetime.now().date() # Fallback para hoje se não configurado

            consultores_base = set(df['Consultor'].unique().tolist())
            if contas_transicao:
                transicao_df = pd.DataFrame(contas_transicao)
                consultores_zerados = set(transicao_df['Gestão Atual'].astype(str).str.strip().tolist())
            else:
                consultores_zerados = set()
            consultores_total = sorted(consultores_base.union(consultores_zerados))

            resumo_dict = {c: [] for c in consultores_total}
            for _, row in df.iterrows():
                consultor = row.get('Consultor', '')
                resumo_dict.setdefault(consultor, [])
                resumo_dict[consultor].append({
                    'cliente': row.get('Cliente', ''),
                    'assunto': row.get('Produto', ''),
                    'data_criacao': row.get('Data Pendência', ''),
                    'codigo_controle': row.get('Código de Controle', ''),
                    'valor': format_currency_local(row.get('Valor', ''))
                })

            for consultor in consultores_total:
                pleitos = resumo_dict[consultor]
                df_consultor = df[df['Consultor'] == consultor]
                clientes_unicos = df_consultor['Cliente'].nunique()
                pendencia_dt = pd.to_datetime(df_consultor['Data Pendência'], format='%d/%m/%Y', errors='coerce').dt.date

                # AQUI É ONDE USAMOS A threshold_date CONFIGURADA
                mask_atraso = (pendencia_dt < threshold_date)

                clientes_atrasados = df_consultor.loc[mask_atraso, 'Cliente'].unique()
                atrasados = len(clientes_atrasados)
                resumo.append({
                    'consultor': consultor,
                    'total': clientes_unicos,
                    'atrasados': atrasados,
                    'pleitos': pleitos
                })

            for box in resumo:
                pleitos_por_cliente = defaultdict(list)
                for pleito in box['pleitos']:
                    pleitos_por_cliente[pleito['cliente']].append(pleito)
                box['pleitos_por_cliente'] = dict(pleitos_por_cliente)

        except Exception as e:
            logger.error(f'Erro ao processar dados: {str(e)}')
            flash(f'Erro ao processar dados: {str(e)}', 'danger')

    return render_template(
        'principal.html',
        data=display_data,
        data_length=data_length,
        filter_column=session.get('filter_column', ''),
        filter_value=session.get('filter_value', ''),
        resumo=resumo,
        ultima_carga_dt=ultima_carga_dt, # NOVO
        proxima_atualizacao_dt=proxima_atualizacao_dt # NOVO
    )


@app.route('/analisar', methods=['POST'])
@permission_required('can_access_pleitos') # Ação de filtrar pleitos
def analisar():
    if 'username' not in session:
        flash('Faça login para acessar esta funcionalidade', 'danger')
        return redirect(url_for('login'))

    if 'current_file' not in session:
        flash('Carregue uma planilha antes de filtrar', 'warning')
        return redirect(url_for('principal'))

    filter_column = request.form.get('filter_column', 'Consultor')
    filter_value = request.form.get('filter_value', '').strip()

    if not filter_value:
        flash('Digite um valor para filtrar', 'warning')
        return redirect(url_for('principal'))

    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None
    new_log = Log(
        action="FILTRAR_PLEITOS",
        details=f"Filtro aplicado: Coluna='{filter_column}', Valor='{filter_value}' na planilha atual.",
        user_id=user_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(new_log)
    db.session.commit()

    session['filter_column'] = filter_column
    session['filter_value'] = filter_value

    flash('Filtro aplicado com sucesso!', 'success')
    return redirect(url_for('principal'))

@app.route('/limpar_filtro')
@permission_required('can_access_pleitos') # Ação de limpar filtro de pleitos
def limpar_filtro():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None
    new_log = Log(
        action="LIMPAR_FILTRO_PLEITOS",
        details="Filtro de pleitos removido.",
        user_id=user_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(new_log)
    db.session.commit()

    session.pop('filter_column', None)
    session.pop('filter_value', None)
    flash('Filtro removido com sucesso!', 'info')
    return redirect(url_for('principal'))

@app.route('/exportar', methods=['POST'])
@permission_required('can_access_pleitos') # Permissão para exportar pleitos
def exportar():
    if 'username' not in session or 'current_file' not in session:
        return redirect(url_for('login'))

    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_file'])
        df = pd.read_excel(filepath)

        # NOVO: Recuperar clientes e produtos excluídos do DB para exportação
        config_clientes_excluidos = Configuracao.query.filter_by(chave='clientes_excluidos').first()
        clientes_excluidos_do_db = json.loads(config_clientes_excluidos.valor) if config_clientes_excluidos and config_clientes_excluidos.valor else []

        config_produtos_excluidos = Configuracao.query.filter_by(chave='produtos_excluidos').first()
        produtos_excluidos_do_db = json.loads(config_produtos_excluidos.valor) if config_produtos_excluidos and config_produtos_excluidos.valor else []

        filter_column = session.get('filter_column', '')
        filter_value = session.get('filter_value', '')

        # NOVO: Chamar preparar_base_excel passando as listas de exclusão
        df = preparar_base_excel(df, filter_column, filter_value,
                                 clientes_excluidos_list=clientes_excluidos_do_db,
                                 produtos_excluidos_list=produtos_excluidos_do_db)

        export_filename = f"pleitos_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
            worksheet = writer.sheets['Sheet1']
            for idx, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.column_dimensions[chr(65 + idx)].width = min(max_len, 50)
        output.seek(0)

        user = User.query.filter_by(username=session['username']).first()
        user_id = user.id if user else None
        new_log = Log(
            action="EXPORTAR_PLEITOS",
            details=f"Planilha de pleitos exportada: '{export_filename}'.",
            user_id=user_id,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_log)
        db.session.commit()

        return send_file(
            output,
            download_name=export_filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        logger.error(f'Erro ao exportar: {str(e)}')
        flash(f'Erro ao exportar: {str(e)}', 'danger')
        return redirect(url_for('principal'))

@app.route('/logs')
@permission_required('can_access_logs') # Acesso aos logs
def show_logs():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Coleta os parâmetros de filtro da URL
    search_text = request.args.get('search_text', '').strip()
    filter_user = request.args.get('filter_user', '').strip()
    filter_action = request.args.get('filter_action', '').strip()
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()

    # Inicia a query base
    logs_query = Log.query.options(db.joinedload(Log.user)).order_by(Log.timestamp.desc())

    # Aplica filtros com base nos parâmetros
    if search_text:
        # Busca em detalhes, ação, nome_cliente E AGORA CÓDIGO DE CONTROLE
        logs_query = logs_query.filter(
            db.or_(
                Log.details.ilike(f'%{search_text}%'),
                Log.action.ilike(f'%{search_text}%'),
                Log.nome_cliente.ilike(f'%{search_text}%'),
                Log.codigo_controle.ilike(f'%{search_text}%')
            )
        )

    if filter_user:
        # Filtra pelo username do usuário que realizou a ação
        logs_query = logs_query.join(User).filter(User.username == filter_user)

    if filter_action:
        # Filtra pelo tipo de ação
        logs_query = logs_query.filter(Log.action == filter_action)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            logs_query = logs_query.filter(db.func.date(Log.timestamp) >= start_date)
        except ValueError:
            flash('Formato de "Data Início" inválido. Use AAAA-MM-DD.', 'danger')

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            logs_query = logs_query.filter(db.func.date(Log.timestamp) <= end_date)
        except ValueError:
            flash('Formato de "Data Fim" inválido. Use AAAA-MM-DD.', 'danger')

    logs = logs_query.all()

    # Coletar opções únicas para os dropdowns de filtro (do banco de dados)
    unique_users = [user.username for user in User.query.with_entities(User.username).distinct().order_by(User.username).all()]
    unique_actions = [action for action, in db.session.query(Log.action).distinct().order_by(Log.action).all()]


    return render_template(
        'logs.html',
        logs=logs,
        unique_users=unique_users,
        unique_actions=unique_actions,
        search_text=search_text,
        filter_user=filter_user,
        filter_action=filter_action,
        start_date=start_date_str,
        end_date=end_date_str
    )

@app.route('/exportar_logs')
@permission_required('can_access_logs') # Permissão para exportar logs
def export_logs():
    if 'username' not in session:
        return redirect(url_for('login'))

    try:
        # Passar os mesmos filtros para a exportação
        search_text = request.args.get('search_text', '').strip()
        filter_user = request.args.get('filter_user', '').strip()
        filter_action = request.args.get('filter_action', '').strip()
        start_date_str = request.args.get('start_date', '').strip()
        end_date_str = request.args.get('end_date', '').strip()

        logs_query = Log.query.options(db.joinedload(Log.user)).order_by(Log.timestamp.desc())

        if search_text:
            logs_query = logs_query.filter(
                db.or_(
                    Log.details.ilike(f'%{search_text}%'),
                    Log.action.ilike(f'%{search_text}%'),
                    Log.nome_cliente.ilike(f'%{search_text}%'),
                    Log.codigo_controle.ilike(f'%{search_text}%')
                )
            )

        if filter_user:
            logs_query = logs_query.join(User).filter(User.username == filter_user)

        if filter_action:
            logs_query = logs_query.filter(Log.action == filter_action)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                logs_query = logs_query.filter(db.func.date(Log.timestamp) >= start_date)
            except ValueError:
                # Se a data for inválida, não aplica o filtro, mas continua
                pass

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                logs_query = logs_query.filter(db.func.date(Log.timestamp) <= end_date)
            except ValueError:
                # Se a data for inválida, não aplica o filtro, mas continua
                pass

        logs = logs_query.all()


        output = BytesIO()
        exportar_logs_excel(logs, output)
        output.seek(0)

        filename = f"historico_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        user = User.query.filter_by(username=session['username']).first()
        user_id = user.id if user else None
        new_log = Log(
            action="EXPORTAR_LOGS_FILTRADO",
            details=f"Histórico de logs filtrado exportado para '{filename}'. Filtros: Texto='{search_text}', Usuário='{filter_user}', Ação='{filter_action}', Data Início='{start_date_str}', Data Fim='{end_date_str}'.",
            user_id=user_id,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_log)
        db.session.commit()

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        logger.error(f"Erro ao exportar logs: {str(e)}")
        flash(f"Erro ao exportar logs: {str(e)}", "danger")
        return redirect(url_for('show_logs'))

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@app.route('/calcular-multa', methods=['GET', 'POST'])
@permission_required('can_access_cancelamento')
def calcular_multa():
    if 'username' not in session:
        return redirect(url_for('login'))

    config_logo_impressao = Configuracao.query.filter_by(chave='logo_impressao_url').first()
    logo_impressao_url = config_logo_impressao.valor if config_logo_impressao else ""

    if request.method == 'POST':
        try:
            data_recebimento_str = request.form.get('data_recebimento')
            data_ativacao_str = request.form.get('data_ativacao')
            valor_servicos_str = request.form.get('valor_servicos')
            servico_rsfn = 'servico' in request.form and request.form['servico'] == 'rsfn'
            
            multa_personalizada_str = request.form.get('multa_personalizada')
            percentual_multa_personalizada = None
            if multa_personalizada_str:
                try:
                    percentual_multa_personalizada = float(multa_personalizada_str) / 100.0
                    if not (0 <= percentual_multa_personalizada <= 1):
                        flash('Percentual de multa personalizado deve ser entre 0 e 100.', 'danger')
                        return redirect(url_for('calcular_multa'))
                except ValueError:
                    flash('Percentual de multa personalizado inválido.', 'danger')
                    return redirect(url_for('calcular_multa'))

            nome_cliente = request.form.get('nome_cliente', '').strip()
            if not nome_cliente:
                flash('O nome do cliente é obrigatório para o cálculo de multa.', 'danger')
                return redirect(url_for('calcular_multa'))

            if not data_recebimento_str or not data_ativacao_str:
                flash('Preencha todas as datas!', 'warning')
                return redirect(url_for('calcular_multa'))

            try:
                # REMOVIDO .date() redundante aqui
                data_recebimento = datetime.strptime(data_recebimento_str, '%Y-%m-%d').date()
                # REMOVIDO .date() redundante aqui
                data_ativacao = datetime.strptime(data_ativacao_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Datas inválidas! Use o formato correto (AAAA-MM-DD).', 'danger')
                return redirect(url_for('calcular_multa'))

            if data_ativacao > data_recebimento:
                flash('A data de ativação não pode ser depois da data de recebimento da carta.', 'danger')
                return redirect(url_for('calcular_multa'))

            try:
                valor_servicos = float(valor_servicos_str)
                if valor_servicos <= 0:
                    flash('O valor dos serviços deve ser maior que zero.', 'danger')
                    return redirect(url_for('calcular_multa'))
            except (TypeError, ValueError):
                flash('Valor dos serviços inválido.', 'danger')
                return redirect(url_for('calcular_multa'))

            if servico_rsfn:
                prazo_contrato = 1
                percentual_multa = 0.50
                aviso_previo = 0
            else:
                try:
                    prazo_contrato = int(request.form.get('prazo_contrato'))
                    aviso_previo_val = request.form.get('aviso_custom') or request.form.get('aviso_previo')
                    aviso_previo = int(aviso_previo_val) if aviso_previo_val else 0
                except (TypeError, ValueError):
                    flash('Prazo contratual e aviso prévio inválidos.', 'danger')
                    return redirect(url_for('calcular_multa'))

            # REMOVIDO .date() redundante aqui
            data_fim_contrato = (data_ativacao + relativedelta(years=prazo_contrato)) - timedelta(days=1)
            prazo_total_dias = (data_fim_contrato - data_ativacao).days + 1
            data_inicio_aviso = data_recebimento
            data_termino_aviso = data_recebimento + timedelta(days=aviso_previo)
            data_inicio_multa = data_termino_aviso
            data_cancelamento = data_termino_aviso
            prazo_cumprido = (data_cancelamento - data_ativacao).days
            prazo_faltante = prazo_total_dias - prazo_cumprido

            valor_diario = valor_servicos / 30 if valor_servicos else 0

            if percentual_multa_personalizada is not None:
                percentual_multa = percentual_multa_personalizada
                percentual_multa_display = percentual_multa * 100
            elif servico_rsfn:
                percentual_multa = 0.50
                percentual_multa_display = 50
            else:
                prazo_cumprido_anos = prazo_cumprido / 365.25
                if prazo_cumprido_anos < 1:
                    percentual_multa = 0.50
                elif prazo_cumprido_anos < 2:
                    percentual_multa = 0.40
                else:
                    percentual_multa = 0.30
                percentual_multa_display = percentual_multa * 100

            if servico_rsfn:
                valor_multa = valor_servicos * 0.5
                paga_multa = True
            elif data_cancelamento > data_fim_contrato:
                valor_multa = 0
                paga_multa = False
            else:
                valor_multa = valor_diario * prazo_faltante * percentual_multa
                paga_multa = valor_multa > 0

            codigo_controle = str(uuid4())[:8]

            user = User.query.filter_by(username=session['username']).first()
            user_id = user.id if user else None

            novo_cancelamento = Cancelamento(
                codigo_controle=codigo_controle,
                nome_cliente=nome_cliente,
                servico_rsfn=servico_rsfn,
                data_recebimento=data_recebimento,
                data_ativacao=data_ativacao,
                aviso_previo_dias=aviso_previo,
                prazo_contrato_anos=prazo_contrato,
                valor_servicos=valor_servicos,
                percentual_multa_aplicado=percentual_multa_display,
                valor_multa=valor_multa,
                paga_multa=paga_multa,
                data_calculo=datetime.utcnow(),
                data_fim_contrato=data_fim_contrato,
                data_cancelamento_efetivo=data_cancelamento,
                prazo_cumprido_dias=prazo_cumprido,
                prazo_faltante_dias=prazo_faltante,
                valor_diario_produto=valor_diario,
                user_id=user_id
            )
            db.session.add(novo_cancelamento)
            db.session.commit()

            log_action = "CALCULO_MULTA"
            log_details = (
                f"Serviço RSFN: {'Sim' if servico_rsfn else 'Não'} | "
                f"Multa: {percentual_multa_display:.0f}% {'(personalizada)' if percentual_multa_personalizada is not None else '(automática)'} | "
                f"Valor: R$ {valor_multa:.2f} | "
                f"Cliente: {nome_cliente} | "
                f"Código: {codigo_controle} | "
                f"ID do Cancelamento: {novo_cancelamento.id}"
            )
            new_log = Log(
                action=log_action,
                details=log_details,
                user_id=user_id,
                codigo_controle=codigo_controle,
                nome_cliente=nome_cliente,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

            return render_template(
                'resultado_multa.html',
                servico_rsfn=servico_rsfn,
                paga_multa=paga_multa,
                aviso_previo=aviso_previo,
                data_recebimento=data_recebimento.strftime('%d/%m/%Y'),
                data_ativacao=data_ativacao.strftime('%d/%m/%Y'),
                data_inicio_aviso=data_inicio_aviso.strftime('%d/%m/%Y'),
                data_termino_aviso=data_termino_aviso.strftime('%d/%m/%Y'),
                data_inicio_multa=data_inicio_multa.strftime('%d/%m/%Y'),
                prazo_contrato=prazo_contrato,
                valor_servicos=valor_servicos,
                valor_diario=valor_diario,
                prazo_cumprido=prazo_cumprido,
                prazo_faltante=prazo_faltante,
                data_cancelamento=data_cancelamento.strftime('%d/%m/%Y'),
                data_fim_contrato=data_fim_contrato.strftime('%d/%m/%Y'),
                percentual_multa=percentual_multa_display,
                valor_multa=valor_multa,
                data_calculo=datetime.now().strftime('%d/%m/%Y às %H:%M'),
                codigo_controle=codigo_controle,
                nome_cliente=nome_cliente,
                logo_impressao_url=logo_impressao_url
            )
        except Exception as e:
            flash(f'Erro no cálculo: {str(e)}', 'danger')
            logger.error(f"Erro no cálculo de multa: {str(e)}")
            user = User.query.filter_by(username=session['username']).first()
            user_id = user.id if user else None
            new_log = Log(
                action="ERRO_CALCULO_MULTA",
                details=f"Erro ao calcular multa: {str(e)}",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            return redirect(url_for('calcular_multa'))

    hoje = datetime.now().strftime('%Y-%m-%d')
    return render_template('calcular_multa.html', hoje=hoje, logo_impressao_url=logo_impressao_url)

# app.py (trecho da rota /monitor_juridico)

# ... (Seus imports existentes no topo do arquivo) ...
# from models import db, User, Log, Pleito, Role, Configuracao, Feriado, AtividadeJuridica
# from datetime import datetime, timedelta, date

# ... (imports no topo do arquivo app.py) ...

# ... (Imports no topo do app.py, certifique-se de que todos os módulos necessários estão importados) ...

# ... (Imports no topo do app.py) ...

# ... (imports no topo do app.py) ...
# Adicione a importação para normalização de string (se não tiver):
import unicodedata 

@app.route('/monitor_juridico', methods=['GET', 'POST'])
@permission_required('can_access_monitor_juridico')
def monitor_juridico():
    all_holidays_db = Feriado.query.order_by(Feriado.data).all()
    feriados_for_calc = {f.data for f in all_holidays_db}
    feriados_str = [f.format_date_br() for f in all_holidays_db]

    erro = None
    
    if request.method == 'POST' and 'feriados_raw_input' in request.form:
        if not session.get('can_edit_monitor_juridico'):
            flash('Você não tem permissão para editar os feriados.', 'danger')
            return redirect(url_for('monitor_juridico'))

        raw_input = request.form.get('feriados_raw_input')
        feriados_para_salvar = []
        parsed_dates = set()
        errors_parsing = []

        try:
            db.session.query(Feriado).delete()
            db.session.commit()
            logger.info("Todos os feriados existentes foram removidos para atualização.")
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao limpar feriados antigos: {e}", "danger")
            logger.error(f"Erro ao limpar feriados antigos: {e}")
            return redirect(url_for('monitor_juridico'))

        if raw_input:
            for f_str in raw_input.split(','):
                f_str = f_str.strip()
                if f_str:
                    try:
                        f_date = datetime.strptime(f_str, "%d/%m/%Y").date()
                        if f_date not in parsed_dates:
                            feriados_para_salvar.append(Feriado(data=f_date, nome="Feriado Manual", localidade="Manual", tipo="Manual"))
                            parsed_dates.add(f_date)
                    except ValueError:
                        errors_parsing.append(f_str)
                        logger.warning(f"Formato de feriado inválido ignorado: {f_str}")

        if errors_parsing:
            flash(f'Alguns feriados tinham formato inválido e foram ignorados: {", ".join(errors_parsing)}. Use DD/MM/AAAA.', 'warning')
        else:
            flash('Feriados atualizados com sucesso!', 'success')

        try:
            for feriado_obj in feriados_para_salvar:
                db.session.add(feriado_obj)
            db.session.commit()
            user = User.query.filter_by(username=session['username']).first()
            user_id = user.id if user else None
            new_log = Log(
                action="ATUALIZAR_FERIADOS_MANUAL",
                details=f"Feriados atualizados manualmente. Total: {len(feriados_para_salvar)}. Ignorados: {len(errors_parsing)}.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Erro ao salvar os novos feriados: {e}", "danger")
            logger.error(f"Erro ao salvar os novos feriados: {e}")

        all_holidays_db = Feriado.query.order_by(Feriado.data).all()
        feriados_for_calc = {f.data for f in all_holidays_db}
        feriados_str = [f.format_date_br() for f in all_holidays_db]

    elif request.method == 'POST' and 'file' in request.files and request.files['file'] and request.files['file'].filename:
        if not session.get('can_upload_all'):
            flash('Você não tem permissão para carregar planilhas no Monitor Jurídico.', 'danger')
            return redirect(url_for('monitor_juridico'))

        file = request.files['file']
        try:
            df = pd.read_excel(file)

            required_columns_juridico = [
                'Tipo', 'Assunto', 'Data de Criação', 'Proprietário', 'Criada por', 'Prioridade'
            ]

            df.columns = df.columns.str.strip()
            current_columns = df.columns.tolist()

            missing_columns = [col for col in required_columns_juridico if col not in current_columns]

            if missing_columns:
                error_msg = f'Planilha inválida para Monitor Jurídico. Colunas obrigatórias faltando: {", ".join(missing_columns)}.'
                flash(error_msg, 'danger')
                logger.error(f'Erro de validação ao carregar planilha no Monitor Jurídico: {error_msg}')

                user = User.query.filter_by(username=session['username']).first()
                user_id = user.id if user else None
                new_log = Log(
                    action="UPLOAD_JURIDICO_FALHA",
                    details=f"Tentativa de upload de planilha inválida para Monitor Jurídico. Erro: {error_msg}",
                    user_id=user_id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_log)
                db.session.commit()
                return redirect(url_for('monitor_juridico'))

            try:
                db.session.query(AtividadeJuridica).delete()
                db.session.commit()
                logger.info("Todas as atividades jurídicas existentes foram removidas para atualização via planilha.")
            except Exception as e:
                db.session.rollback()
                flash(f"Erro ao limpar atividades jurídicas antigas: {e}", "danger")
                logger.error(f"Erro ao limpar atividades jurídicas antigas: {e}")
                return redirect(url_for('monitor_juridico'))

            # Função auxiliar para normalizar string (remover acentos, etc.)
            def normalize_string(s):
                if not isinstance(s, str):
                    return ""
                s = s.lower().strip()
                s = ''.join(c for c in s if c.isalnum() or c.isspace()) # Remove caracteres especiais
                s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('utf-8')
                return s

            atividades_salvas_count = 0
            for index, row in df.iterrows():
                try:
                    data_criacao_excel = pd.to_datetime(row['Data de Criação'], dayfirst=True, errors='coerce').date()
                    if pd.isna(data_criacao_excel):
                        logger.warning(f"Linha {index+2} da planilha ignorada: Data de Criação inválida.")
                        continue

                    tipo_str = str(row.get('Tipo', '')).strip().lower()
                    assunto_original = str(row.get('Assunto', '')).strip() # Manter original para salvar
                    assunto_normalizado = normalize_string(assunto_original) # Usar a nova função de normalização

                    is_squad_contratacao = tipo_str == 'squad contratação'
                    is_liberacao_fluxo = 'liberacao de fluxo' in assunto_normalizado # Usar assunto normalizado
                    
                    is_outros_valido = False
                    if tipo_str == 'outros':
                        # Lista de assuntos válidos para o tipo "Outros" (já normalizados para comparação)
                        assuntos_validos_outros_norm = [
                            'analise de contrato', 
                            'elaboracao de documentos',
                            'solicitacao de documento', 
                            'solicitacao de documentos'
                        ]
                        
                        # Verifica se o assunto_normalizado CONTÉM qualquer um dos termos válidos
                        if any(term in assunto_normalizado for term in assuntos_validos_outros_norm):
                            is_outros_valido = True
                        
                        # Exclusão: Garante que "arquivamento" ou "arquivo" NÃO está no assunto_normalizado
                        if 'arquivamento' in assunto_normalizado or 'arquivo' in assunto_normalizado:
                            is_outros_valido = False 

                    if is_squad_contratacao or is_liberacao_fluxo or is_outros_valido:
                        status_from_excel = row.get('Status', 'Pendente') if 'Status' in df.columns else 'Pendente'

                        nova_atividade = AtividadeJuridica(
                            tipo=row.get('Tipo'),
                            assunto=assunto_original, # Salvar o assunto original
                            data_criacao=data_criacao_excel,
                            proprietario=row.get('Proprietário'),
                            criado_por=row.get('Criada por'),
                            prioridade=row.get('Prioridade', 'Normal'),
                            status=status_from_excel
                        )
                        db.session.add(nova_atividade)
                        atividades_salvas_count += 1

                except Exception as e:
                    logger.error(f"Erro ao processar linha {index+2} da planilha de atividades: {e}")

            db.session.commit()
            flash(f'Planilha de Monitor Jurídico carregada e {atividades_salvas_count} atividades salvas no banco de dados!', 'success')

            user = User.query.filter_by(username=session['username']).first()
            user_id = user.id if user else None
            new_log = Log(
                action="UPLOAD_JURIDICO",
                details=f"Planilha '{file.filename}' carregada para Monitor Jurídico. {atividades_salvas_count} atividades salvas no DB.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

            return redirect(url_for('monitor_juridico'))

        except Exception as e:
            db.session.rollback()
            erro = f"Erro ao ler/salvar o arquivo: {str(e)}. Certifique-se de que é um arquivo Excel válido (.xlsx ou .xls)."
            flash(f"Erro ao carregar planilha de Monitor Jurídico: {erro}", 'danger')
            logger.error(f"Erro inesperado ao carregar planilha no Monitor Jurídico: {erro}")

            user = User.query.filter_by(username=session['username']).first()
            user_id = user.id if user else None
            new_log = Log(
                action="UPLOAD_JURIDICO_FALHA",
                details=f"Erro inesperado ao processar planilha para Monitor Jurídico: {erro}",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            return redirect(url_for('monitor_juridico'))

    # === GET normal ou atualização de página (CARREGAR DO BANCO DE DADOS) ===
    filter_proprietario = request.args.get('filter_proprietario', '').strip()

    def primeiro_nome(nome_completo):
        return str(nome_completo).strip().split(' ')[0] if nome_completo and str(nome_completo).strip() else ""

    query_atividades = AtividadeJuridica.query

    if filter_proprietario:
        query_atividades = query_atividades.filter(
            db.or_(
                # Tenta casar o primeiro nome (até o primeiro espaço)
                db.func.lower(db.func.substr(AtividadeJuridica.proprietario, 1, db.func.instr(AtividadeJuridica.proprietario, ' ') - 1)) == db.func.lower(filter_proprietario),
                # Tenta casar o nome completo se for um nome simples ou o primeiro nome não casar
                db.func.lower(AtividadeJuridica.proprietario) == db.func.lower(filter_proprietario)
            )
        )
    
    all_activities_from_db = query_atividades.all()
    
    atividades_geral = []
    atividades_liberacao = []

    for row_obj in all_activities_from_db:
        data_criacao = row_obj.data_criacao
        assunto = row_obj.assunto
        proprietario = primeiro_nome(row_obj.proprietario) 
        criado_por = primeiro_nome(row_obj.criado_por) 
        prioridade = row_obj.prioridade
        current_status_db = row_obj.status
        tipo_atividade = row_obj.tipo 
        areas_pendentes_db = row_obj.areas_pendentes
        
        hoje = datetime.now().date()
        dias = dias_uteis_entre_datas(data_criacao, hoje, feriados_for_calc)

        cor = ''
        status_display = current_status_db
        
        if str(current_status_db).lower() == 'concluída':
            cor = 'table-success'
            status_display = 'Concluída'
        elif areas_pendentes_db and areas_pendentes_db.strip() and areas_pendentes_db.lower() != 'null':
            cor = 'table-area-externa'
            status_display = f"Pendente: {areas_pendentes_db.replace(',', ', ')}"
        elif isinstance(dias, int) and dias >= 5:
            cor = 'table-danger'
            status_display = 'Atrasada'
        elif isinstance(dias, int) and dias == 4:
            cor = 'table-warning'
            status_display = 'Quase atrasando'
        elif isinstance(dias, int) and dias <= 1:
            cor = 'table-primary'
            status_display = 'Recém criada'
        else:
            status_display = 'Pendente'

        atividade_dict = {
            'id': row_obj.id,
            'data_criacao': data_criacao.strftime('%d/%m/%Y'),
            'assunto': assunto,
            'proprietario': proprietario, 
            'criador': criado_por, 
            'prioridade': prioridade,
            'status': status_display,
            'dias': dias,
            'cor': cor,
            'tipo': tipo_atividade, 
            'original_status': current_status_db,
            'areas_pendentes': areas_pendentes_db
        } 

        if 'liberação de fluxo' in assunto.lower():
            atividades_liberacao.append(atividade_dict)
        else:
            atividades_geral.append(atividade_dict)
            
    atividades_geral = sorted(atividades_geral, key=lambda x: datetime.strptime(x['data_criacao'], "%d/%m/%Y"), reverse=False)
    atividades_liberacao = sorted(atividades_liberacao, key=lambda x: datetime.strptime(x['data_criacao'], "%d/%m/%Y"), reverse=False)

    unique_proprietarios = db.session.query(
        AtividadeJuridica.proprietario
    ).filter(AtividadeJuridica.proprietario != None).distinct().order_by(AtividadeJuridica.proprietario).all()
    
    unique_proprietarios_list = sorted(list(set(primeiro_nome(p[0]) for p in unique_proprietarios if p[0])))

    return render_template(
        'monitor_juridico.html',
        atividades=atividades_geral,
        liberacoes=atividades_liberacao,
        feriados=feriados_str,
        erro=erro,
        now=datetime.now(),
        unique_proprietarios=unique_proprietarios_list,
        filter_proprietario=filter_proprietario
    )

# Rota para buscar feriados em JSON para o modal (para recarregar a textarea)
@app.route('/monitor_juridico/get_holidays_json', methods=['GET'])
@permission_required('can_access_monitor_juridico')
def get_holidays_json():
    holidays = Feriado.query.order_by(Feriado.data).all()
    holidays_data = []
    for h in holidays:
        holidays_data.append({
            'date': h.data.strftime('%Y-%m-%d'),
            'date_formatted': h.format_date_br(),
            'name': h.nome,
            'location': h.localidade,
            'type': h.tipo
        })
    return jsonify({'success': True, 'holidays': holidays_data})

# Rota para atualização de atividades jurídicas via AJAX
@app.route('/monitor_juridico/update_atividade/<int:atividade_id>', methods=['POST'])
@permission_required('can_edit_monitor_juridico')
def update_atividade_juridica(atividade_id):
    atividade = AtividadeJuridica.query.get(atividade_id)
    if not atividade:
        return jsonify({'success': False, 'message': 'Atividade não encontrada.'}), 404

    data = request.get_json()
    action_type = data.get('action_type')
    new_value = data.get('new_value')

    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None
    log_details = f"Atividade ID {atividade_id} (Assunto: {atividade.assunto}). "

    try:
        if action_type == 'status':
            old_status = atividade.status
            atividade.status = new_value
            atividade.data_ultimo_status = datetime.utcnow()
            # Se status for "Concluída", limpa áreas pendentes
            if new_value == 'Concluída':
                atividade.areas_pendentes = None
            log_details += f"Status alterado de '{old_status}' para '{new_value}'."
        elif action_type == 'prioridade':
            old_prioridade = atividade.prioridade
            atividade.prioridade = new_value
            log_details += f"Prioridade alterada de '{old_prioridade}' para '{new_value}'."
        elif action_type == 'areas_pendentes':
            old_areas = atividade.areas_pendentes
            atividade.areas_pendentes = new_value
            # Se áreas pendentes são definidas, o status principal pode ser ajustado
            if new_value and new_value != 'null': # Se está definindo áreas pendentes, o status vira "Pendente com Área"
                atividade.status = 'Pendente com Área'
            else: # Se áreas pendentes são removidas, o status pode voltar para "Pendente" ou original
                if atividade.status == 'Pendente com Área': # Só muda se era "Pendente com Área"
                    atividade.status = 'Pendente' # Volta para pendente padrão
            atividade.data_ultimo_status = datetime.utcnow()
            log_details += f"Áreas pendentes alteradas de '{old_areas}' para '{new_value}'. Status atualizado para '{atividade.status}'."
        else:
            return jsonify({'success': False, 'message': 'Tipo de ação inválido.'}), 400

        db.session.commit()

        new_log = Log(action=f"UPDATE_JURIDICO_{action_type.upper()}", details=log_details, user_id=user_id, timestamp=datetime.utcnow())
        db.session.add(new_log)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Atividade atualizada com sucesso!'})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao atualizar atividade jurídica ID {atividade_id} (action: {action_type}): {e}")
        return jsonify({'success': False, 'message': f'Erro ao atualizar atividade: {e}'}), 500

# Rota para buscar feriados da API
@app.route('/fetch_holidays_api', methods=['GET'])
@permission_required('can_edit_monitor_juridico')
def fetch_holidays_api():
    ano = request.args.get('ano', datetime.now().year, type=int)
    estado = request.args.get('estado', '').upper()
    municipio = request.args.get('municipio', '').title()

    feriados_encontrados = []

    url_nacionais = f'https://brasilapi.com.br/api/feriados/v1/{ano}'
    try:
        response = requests.get(url_nacionais, timeout=10)
        response.raise_for_status()
        data = response.json()
        for f in data:
            feriados_encontrados.append({
                'date': f['date'],
                'name': f['name'],
                'type': f['type'],
                'location': 'Nacional'
            })
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar feriados nacionais da API: {e}")
        pass

    return jsonify({
        'success': True,
        'holidays': feriados_encontrados,
        'message': f"Feriados para {ano} encontrados. (Busca principal por feriados nacionais, via BrasilAPI)."
    })

# Rota para adicionar/remover feriados via AJAX
@app.route('/manage_holiday_db', methods=['POST'])
@permission_required('can_edit_monitor_juridico')
def manage_holiday_db():
    action = request.json.get('action')
    holiday_data = request.json.get('holiday')

    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None

    try:
        if action == 'add':
            f_date = datetime.strptime(holiday_data['date'], '%Y-%m-%d').date()
            existing_holiday = Feriado.query.filter_by(data=f_date, localidade=holiday_data.get('location', 'Nacional')).first()
            if existing_holiday:
                return jsonify({'success': False, 'message': 'Feriado já existe para esta data e localidade.'})

            new_holiday = Feriado(
                data=f_date,
                nome=holiday_data.get('name', 'Feriado'),
                localidade=holiday_data.get('location', 'Nacional'),
                tipo=holiday_data.get('type', 'Desconhecido')
            )
            db.session.add(new_holiday)
            db.session.commit()

            log_details = f"Adicionado feriado: {new_holiday.format_date_br()} ({new_holiday.nome}) em {new_holiday.localidade}."
            new_log = Log(action="ADD_FERIADO", details=log_details, user_id=user_id, timestamp=datetime.utcnow())
            db.session.add(new_log)
            db.session.commit()

            return jsonify({'success': True, 'message': 'Feriado adicionado com sucesso!'})

        elif action == 'remove':
            f_date = datetime.strptime(holiday_data['date'], '%Y-%m-%d').date()
            feriado_to_delete = Feriado.query.filter_by(data=f_date, localidade=holiday_data.get('location', 'Nacional')).first()

            if not feriado_to_delete:
                return jsonify({'success': False, 'message': 'Feriado não encontrado para remoção.'})

            db.session.delete(feriado_to_delete)
            db.session.commit()

            log_details = f"Removido feriado: {feriado_to_delete.format_date_br()} ({feriado_to_delete.nome}) em {feriado_to_delete.localidade}."
            new_log = Log(action="REMOVE_FERIADO", details=log_details, user_id=user_id, timestamp=datetime.utcnow())
            db.session.add(new_log)
            db.session.commit()

            return jsonify({'success': True, 'message': 'Feriado removido com sucesso!'})

        else:
            return jsonify({'success': False, 'message': 'Ação inválida.'})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao gerenciar feriado no DB (ação: {action}): {e}")
        return jsonify({'success': False, 'message': f'Erro ao processar feriado: {e}'})


MESES_PADRAO = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

MESES_NOME = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
MESES_NOME_INV = {v: k for k, v in MESES_NOME.items()}

@app.route('/sla_dashboard', methods=['GET', 'POST'])
@permission_required('can_access_sla')
def sla_dashboard():
    if 'username' not in session:
        flash('Você precisa estar logado para acessar esta página.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None

    config_sla_meta = Configuracao.query.filter_by(chave='sla_meta_percentual').first()
    meta = float(config_sla_meta.valor) if config_sla_meta and config_sla_meta.valor and config_sla_meta.valor.replace('.', '', 1).isdigit() else 90.0

    MESES_NOME = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }

    if request.method == 'POST':
        acao = request.form.get('acao')
        ano_atual = datetime.now().year

        if acao == 'adicionar_mes':
            if not session.get('can_edit_sla'):
                flash('Você não tem permissão para adicionar dados ao Dashboard SLA.', 'danger')
                return redirect(url_for('sla_dashboard'))

            mes = request.form.get('mes')
            qtd_dentro_sla = request.form.get('qtd_dentro_sla')
            qtd_fora_sla = request.form.get('qtd_fora_sla')
            qtd_processos = request.form.get('qtd_processos')
            realizado = request.form.get('realizado')

            if not all([mes, qtd_dentro_sla, qtd_fora_sla, qtd_processos, realizado]):
                flash('Por favor, preencha todos os campos.', 'danger')
                return redirect(url_for('sla_dashboard'))
            
            try:
                mes = int(mes)
                qtd_dentro_sla = int(qtd_dentro_sla)
                qtd_fora_sla = int(qtd_fora_sla)
                qtd_processos = int(qtd_processos)
                realizado = float(realizado)
            except ValueError:
                flash('Valores inválidos para os campos numéricos.', 'danger')
                return redirect(url_for('sla_dashboard'))

            existing_sla = SlaMensal.query.filter_by(mes=mes, ano=ano_atual).first()
            if existing_sla:
                existing_sla.qtd_dentro_sla = qtd_dentro_sla
                existing_sla.qtd_fora_sla = qtd_fora_sla
                existing_sla.qtd_processos = qtd_processos
                existing_sla.realizado_percentual = realizado
                existing_sla.meta_percentual = meta
                flash(f'Dados de SLA para {MESES_NOME.get(mes)} de {ano_atual} atualizados com sucesso!', 'success')
                log_action = "SLA_ATUALIZADO"
                log_details = f"Dados de SLA para {MESES_NOME.get(mes)}/{ano_atual} atualizados. Realizado: {realizado:.2f}%." # 'MESES_NOME' corrigido
            else:
                new_sla = SlaMensal(
                    mes=mes,
                    ano=ano_atual,
                    qtd_dentro_sla=qtd_dentro_sla,
                    qtd_fora_sla=qtd_fora_sla,
                    qtd_processos=qtd_processos,
                    realizado_percentual=realizado,
                    meta_percentual=meta
                )
                db.session.add(new_sla)
                flash(f'Dados de SLA para {MESES_NOME.get(mes)} de {ano_atual} adicionados com sucesso!', 'success')
                log_action = "SLA_ADICIONADO"
                log_details = f"Dados SLA adicionados para {MESES_NOME.get(mes)}/{ano_atual} adicionados. Realizado: {realizado:.2f}%." # 'MESES_NOME' corrigido
            
            db.session.commit()
            new_log = Log(
                action=log_action,
                details=log_details,
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            return redirect(url_for('sla_dashboard'))

        elif acao == 'limpar':
            if not session.get('can_edit_sla'):
                flash('Você não tem permissão para limpar o Dashboard SLA.', 'danger')
                return redirect(url_for('sla_dashboard'))
            
            SlaMensal.query.filter_by(ano=ano_atual).delete()
            db.session.commit()
            flash(f'Todos os dados de SLA para o ano {ano_atual} foram limpos.', 'warning')
            new_log = Log(
                action="SLA_LIMPO",
                details=f"Todos os dados de SLA para o ano {ano_atual} foram limpos.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            return redirect(url_for('sla_dashboard'))

        elif acao == 'exportar_excel':
            if not session.get('can_access_sla'): # Usar a permissão de acesso, ou criar uma 'can_export_data' se for mais granular
                flash('Você não tem permissão para exportar dados.', 'danger')
                return redirect(url_for('sla_dashboard'))
            
            all_sla_data = SlaMensal.query.filter_by(ano=ano_atual).order_by(SlaMensal.mes).all()
            data_for_excel = []
            for s in all_sla_data:
                data_for_excel.append({
                    'mes_nome': MESES_NOME.get(s.mes),
                    'qtd_dentro_sla': s.qtd_dentro_sla,
                    'qtd_fora_sla': s.qtd_fora_sla,
                    'qtd_processos': s.qtd_processos,
                    'realizado': s.realizado_percentual, # Será arredondado no excel_export.py
                    'meta': s.meta_percentual # Será arredondado no excel_export.py
                })
            
            df = pd.DataFrame(data_for_excel)
            output = BytesIO()
            # exportar_sla_excel (função de utils/excel_export.py) já fará o arredondamento
            exportar_sla_excel(df, output) 
            output.seek(0)

            new_log = Log(
                action="SLA_EXPORT_EXCEL",
                details=f"Dados de SLA para o ano {ano_atual} exportados para Excel.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

            return send_file(output, download_name=f'sla_mensal_{ano_atual}.xlsx', as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        elif acao == 'exportar_pdf':
            if not session.get('can_access_sla'): # Usar a permissão de acesso, ou criar uma 'can_export_data' se for mais granular
                flash('Você não tem permissão para exportar dados.', 'danger')
                return redirect(url_for('sla_dashboard'))

            all_sla_data = SlaMensal.query.filter_by(ano=ano_atual).order_by(SlaMensal.mes).all()
            resultados_para_pdf = []
            for s in all_sla_data:
                resultados_para_pdf.append({
                    'mes_nome': MESES_NOME.get(s.mes),
                    'qtd_dentro_sla': s.qtd_dentro_sla,
                    'qtd_fora_sla': s.qtd_fora_sla,
                    'qtd_processos': s.qtd_processos,
                    'realizado': s.realizado_percentual, # Será arredondado no pdf_generator.py
                    'meta': s.meta_percentual # Será arredondado no pdf_generator.py
                })

            # A função exportar_sla_pdf precisa da lista de resultados e da meta.
            # Se você tiver uma logo_url, passe-a.
            # Verifique os parâmetros de 'exportar_sla_pdf' em utils/pdf_generator.py
            pdf_output = io.BytesIO()
            exportar_sla_pdf(resultados_para_pdf, pdf_output, meta=meta, datahora=datetime.now().strftime('%d/%m/%Y %H:%M'))
            pdf_output.seek(0)

            new_log = Log(
                action="SLA_EXPORT_PDF",
                details=f"Dados de SLA para o ano {ano_atual} exportados para PDF.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

            return send_file(pdf_output, download_name=f'sla_mensal_{ano_atual}.pdf', as_attachment=True, mimetype='application/pdf')

        elif acao == 'importar_excel':
            if not session.get('can_upload_all'):
                flash('Você não tem permissão para importar dados para o Dashboard SLA.', 'danger')
                return redirect(url_for('sla_dashboard'))

            if 'importar_excel' not in request.files:
                flash('Nenhum arquivo selecionado.', 'danger')
                return redirect(url_for('sla_dashboard'))
            
            file = request.files['importar_excel']
            if file.filename == '':
                flash('Nenhum arquivo selecionado.', 'danger')
                return redirect(url_for('sla_dashboard'))
            
            # Ajuste para permitir 'xls' também, se a função allowed_file permitir.
            # Verifique a função allowed_file se é necessário ajustar para 'xlsx' apenas.
            if file and (file.filename.lower().endswith('.xlsx') or file.filename.lower().endswith('.xls')): 
                try:
                    df = pd.read_excel(file)
                    
                    col_mapping = {
                        'Mês': 'mes',
                        'Qtd. Dentro SLA': 'qtd_dentro_sla',
                        'Qtd. Fora SLA': 'qtd_fora_sla',
                        'Qtd. Processos': 'qtd_processos',
                        'Realizado (%)': 'realizado_percentual',
                        'Meta (%)': 'meta_percentual'
                    }
                    df.rename(columns=col_mapping, inplace=True)

                    meses_reverso = {v.lower(): k for k, v in MESES_NOME.items()}
                    df['mes'] = df['mes'].apply(lambda x: meses_reverso.get(str(x).lower(), None))

                    required_cols = ['mes', 'qtd_dentro_sla', 'qtd_fora_sla', 'qtd_processos', 'realizado_percentual', 'meta_percentual']
                    if not all(col in df.columns for col in required_cols):
                        flash('O arquivo Excel não contém todas as colunas necessárias: Mês, Qtd. Dentro SLA, Qtd. Fora SLA, Qtd. Processos, Realizado (%), Meta (%).', 'danger')
                        return redirect(url_for('sla_dashboard'))

                    imported_count = 0
                    updated_count = 0
                    for index, row in df.iterrows():
                        mes = row['mes']
                        if pd.isna(mes): 
                            continue
                        mes = int(mes)

                        existing_sla = SlaMensal.query.filter_by(mes=mes, ano=ano_atual).first()
                        
                        qtd_dentro_sla = int(row['qtd_dentro_sla']) if pd.notna(row['qtd_dentro_sla']) else 0
                        qtd_fora_sla = int(row['qtd_fora_sla']) if pd.notna(row['qtd_fora_sla']) else 0
                        qtd_processos = int(row['qtd_processos']) if pd.notna(row['qtd_processos']) else 0
                        realizado_percentual = float(row['realizado_percentual']) if pd.notna(row['realizado_percentual']) else 0.0
                        meta_percentual = float(row['meta_percentual']) if pd.notna(row['meta_percentual']) else meta 

                        if existing_sla:
                            existing_sla.qtd_dentro_sla = qtd_dentro_sla
                            existing_sla.qtd_fora_sla = qtd_fora_sla
                            existing_sla.qtd_processos = qtd_processos
                            existing_sla.realizado_percentual = realizado_percentual
                            existing_sla.meta_percentual = meta_percentual
                            updated_count += 1
                        else:
                            new_sla = SlaMensal(
                                mes=mes,
                                ano=ano_atual,
                                qtd_dentro_sla=qtd_dentro_sla,
                                qtd_fora_sla=qtd_fora_sla,
                                qtd_processos=qtd_processos,
                                realizado_percentual=realizado_percentual,
                                meta_percentual=meta_percentual
                            )
                            db.session.add(new_sla)
                            imported_count += 1
                    
                    db.session.commit()
                    flash(f'Importação concluída! {imported_count} registros adicionados, {updated_count} atualizados.', 'success')
                    new_log = Log(
                        action="SLA_IMPORT_EXCEL",
                        details=f"Importados {imported_count} e atualizados {updated_count} registros de SLA para o ano {ano_atual} via Excel.",
                        user_id=user_id,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(new_log)
                    db.session.commit()

                except Exception as e:
                    db.session.rollback()
                    flash(f'Erro ao processar o arquivo Excel: {str(e)}', 'danger')
                    # Log de erro: logger.error(f"Erro ao importar SLA Excel: {str(e)}")
            else:
                flash('Formato de arquivo inválido. Por favor, use .xlsx ou .xls', 'danger')
            
            return redirect(url_for('sla_dashboard'))

        elif acao == 'fechar_ano':
            if not session.get('can_edit_sla'):
                flash('Você não tem permissão para fechar o ano do Dashboard SLA.', 'danger')
                return redirect(url_for('sla_dashboard'))
            
            all_sla_data = SlaMensal.query.filter_by(ano=ano_atual).order_by(SlaMensal.mes).all()
            if len(all_sla_data) == 12:
                valores_realizados = [s.realizado_percentual for s in all_sla_data if s.realizado_percentual is not None]
                if valores_realizados:
                    media_ano = statistics.median(valores_realizados) 
                else:
                    media_ano = 0
                
                flash(f"Ano fiscal {ano_atual} fechado! Mediana do ano: {media_ano:.2f}%", 'success')
                new_log = Log(
                    action="SLA_FECHAR_ANO",
                    details=f"Ano fiscal do Dashboard SLA {ano_atual} fechado. Mediana anual: {media_ano:.2f}%.",
                    user_id=user_id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_log)
                db.session.commit()
            else:
                flash(f"Ainda não há 12 meses preenchidos ({len(all_sla_data)} de 12) para fechar o ano {ano_atual}.", 'warning')
    
    # Carrega todos os resultados do SLA para o ano atual do banco de dados
    all_sla_data = SlaMensal.query.filter_by(ano=datetime.now().year).order_by(SlaMensal.mes).all()
    resultados = []
    for s in all_sla_data:
        resultados.append({
            'mes': s.mes,
            'mes_nome': MESES_NOME.get(s.mes),
            'qtd_dentro_sla': s.qtd_dentro_sla,
            'qtd_fora_sla': s.qtd_fora_sla,
            'qtd_processos': s.qtd_processos,
            'realizado': s.realizado_percentual,
            'meta': s.meta_percentual
        })
    
    valores_realizados_para_media = [r['realizado'] for r in resultados if r['realizado'] is not None]
    media_realizado = statistics.median(valores_realizados_para_media) if valores_realizados_para_media else 0 

    return render_template(
        'sla_dashboard.html',
        resultados=resultados,
        meta=int(meta),
        media_realizado=media_realizado,
        meses_nome={v: k for k, v in MESES_NOME.items()}
    )

@app.route('/correcao-valores', methods=['GET', 'POST'])
@permission_required('can_access_correcao_valores') # Acesso à correção monetária
def correcao_valores():
    resultado = None
    indices = ['IPCA', 'IGPM']
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None

    if request.method == 'POST':
        # Verifica permissão para calcular/enviar formulário
        if not session.get('can_edit_correcao_valores'): # Ou can_edit_all
             flash('Você não tem permissão para realizar correções monetárias.', 'danger')
             return redirect(url_for('correcao_valores'))

        indice = request.form.get('indice')
        data_final = request.form.get('data_final')
        datas_iniciais = request.form.getlist('data_inicial[]')
        valores = request.form.getlist('valor[]')
        resultado = []
        
        all_success = True
        for idx, (data_inicial, valor) in enumerate(zip(datas_iniciais, valores)):
            try:
                res = corrigir_valor(float(valor), data_inicial, data_final, indice)
                valor_corrigido = res['valor_corrigido']
                indice_utilizado = res['indice_utilizado']
                percentual_acumulado = res['percentual_acumulado']
                fator_acumulado = res['fator_acumulado']
                
                new_log = Log(
                    action="CORRECAO_MONETARIA_SUCESSO",
                    details=f"Valor de R${float(valor):.2f} de {data_inicial} corrigido para R${valor_corrigido:.2f} até {data_final} usando {indice_utilizado}.",
                    user_id=user_id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_log)
                db.session.commit()

            except Exception as e:
                flash(f"Erro ao corrigir o valor para a data '{data_inicial}': {str(e)}. Use formato DD/MM/AAAA, AAAA-MM-DD ou MM/AAAA.", "danger")
                logger.error(f"Erro na correção monetária: {str(e)} para data {data_inicial}, valor {valor}, indice {indice}")
                valor_corrigido = "Erro"
                indice_utilizado = '-'
                percentual_acumulado = '-'
                fator_acumulado = '-'
                all_success = False
                new_log = Log(
                    action="CORRECAO_MONETARIA_ERRO",
                    details=f"Erro ao corrigir valor (data_inicial={data_inicial}, valor_original={valor}, indice={indice}): {str(e)}",
                    user_id=user_id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_log)
                db.session.commit()

            resultado.append({
                'id': idx,
                'data_inicial': data_inicial,
                'valor_original': valor,
                'valor_corrigido': valor_corrigido,
                'indice_utilizado': indice_utilizado,
                'percentual_acumulado': percentual_acumulado,
                'fator_acumulado': fator_acumulado
            })
        
        if all_success and resultado:
            flash("Cálculo de correção monetária realizado com sucesso!", "success")

    hoje = datetime.now().strftime('%Y-%m-%d')
    return render_template('correcao_valores.html', indices=indices, hoje=hoje, resultado=resultado)

@app.template_filter('br_decimal')
def br_decimal(value, casas=2):
    try:
        float_value = float(value)
        formato = f"{{:.{casas}f}}".format(float_value)
        return formato.replace('.', ',')
    except (ValueError, TypeError):
        return str(value)


@app.template_filter('moeda_br')
def moeda_br(value):
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(value)


@app.route('/contas_transicao', methods=['POST'])
@permission_required('can_edit_pleitos') # Ações de transição de contas alteram dados de pleitos
def contas_transicao():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None

    if 'current_file' in session:
        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_file'])
            if filepath.endswith('.csv'):
                base_df = pd.read_csv(filepath)
            else:
                base_df = pd.read_excel(filepath)
        except Exception as e:
            flash(f'Não foi possível carregar a base principal do arquivo: {str(e)}', 'danger')
            logger.error(f"Erro ao carregar base principal para contas transicao: {str(e)}")
            new_log = Log(
                action="ERRO_TRANSICAO_CARREGAR_BASE",
                details=f"Erro ao carregar base principal para Contas em Transição: {str(e)}",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            return redirect(url_for('principal'))
    else:
        flash('Carregue uma base principal antes de usar Contas em Transição.', 'warning')
        return redirect(url_for('principal'))

    transicao_df = pd.DataFrame(columns=['Cliente', 'Venda Realizada por', 'Gestão Atual'])
    file = request.files.get('arquivo_transicao')
    
    log_detail_file = "Nenhum arquivo de transição importado."
    if file and file.filename:
        try:
            if file.filename.endswith('.csv'):
                transicao_df = pd.read_csv(file)
            else:
                transicao_df = pd.read_excel(file)
            log_detail_file = f"Arquivo '{file.filename}' importado."
        except Exception as e:
            flash(f"Erro ao ler arquivo de transição: {str(e)}", 'danger')
            logger.error(f"Erro ao ler arquivo de transicao: {str(e)}")
            new_log = Log(
                action="ERRO_TRANSICAO_ARQUIVO",
                details=f"Erro ao ler arquivo de transição: {str(e)}",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            return redirect(url_for('principal'))
    else:
        linhas_manualmente = request.form.get('linhas_manualmente', '[]')
        rows = json.loads(linhas_manualmente)
        if rows:
            transicao_df = pd.DataFrame(rows, columns=['Cliente', 'Venda Realizada por', 'Gestão Atual'])
            log_detail_file = f"Dados inseridos manualmente: {len(rows)} linhas."
        else:
            flash('Adicione pelo menos uma linha para realizar a transição!', 'warning')
            return redirect(url_for('principal'))

    if transicao_df.empty:
        flash('Adicione pelo menos uma linha para realizar a transição!', 'warning')
        return redirect(url_for('principal'))
    
    log_transacoes = []
    for idx, row in transicao_df.iterrows():
        cliente = str(row['Cliente']).strip()
        novo_consultor = str(row['Venda Realizada por']).strip()
        consultor_atual = str(row['Gestão Atual']).strip()

        mask_origem = (base_df['Cliente'].astype(str).str.strip() == cliente) & (base_df['Consultor'].astype(str).str.strip() == consultor_atual)
        linhas_origem = base_df[mask_origem]
        
        if not linhas_origem.empty:
            base_df = base_df[~mask_origem]
            novas_linhas = linhas_origem.copy()
            novas_linhas['Consultor'] = novo_consultor
            base_df = pd.concat([base_df, novas_linhas], ignore_index=True)
            log_transacoes.append(f"'{cliente}' de '{consultor_atual}' para '{novo_consultor}'")
        else:
            log_transacoes.append(f"Cliente '{cliente}' (Origem: '{consultor_atual}', Destino: '{novo_consultor}') - Não encontrada correspondência para transição.")

    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_file'])
        if filepath.endswith('.csv'):
            base_df.to_csv(filepath, index=False)
        else:
            base_df.to_excel(filepath, index=False)
        flash('Contas em transição aplicadas! Agora ao visualizar os pleitos, a gestão dos clientes será corrigida.', 'success')
        
        details_log_trans = f"Transição de contas aplicada. Total de transações processadas: {len(log_transacoes)}. "
        if log_transacoes:
            details_log_trans += f"Primeiras transações: {'; '.join(log_transacoes[:5])}{'...' if len(log_transacoes) > 5 else ''}"
        else:
            details_log_trans += "Nenhuma transação efetivada."

        new_log = Log(
            action="CONTAS_TRANSICAO_APLICADA",
            details=details_log_trans,
            user_id=user_id,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_log)
        db.session.commit()

    except Exception as e:
        flash(f'Não foi possível salvar a base principal após transição: {str(e)}', 'danger')
        logger.error(f"Erro ao salvar base principal apos transicao: {str(e)}")
        new_log = Log(
            action="ERRO_TRANSICAO_SALVAR_BASE",
            details=f"Erro ao salvar base principal após Contas em Transição: {str(e)}",
            user_id=user_id,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_log)
        db.session.commit()
        return redirect(url_for('principal'))

    session['contas_transicao'] = transicao_df.to_dict('records')
    return redirect(url_for('principal'))


@app.route('/consulta_cnpj', methods=['GET', 'POST'])
@permission_required('can_access_consulta_cnpj') # Acesso à consulta CNPJ
def consulta_cnpj():
    resultado = None
    erro = None
    cnpj_input = ''
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None

    if request.method == 'POST':
        cnpj_input = request.form.get('cnpj', '').strip()
        cnpj = re.sub(r'\D', '', cnpj_input)
        if len(cnpj) != 14:
            erro = 'CNPJ inválido. Insira 14 dígitos.'
            new_log = Log(
                action="CONSULTA_CNPJ_INVALIDO",
                details=f"Tentativa de consulta CNPJ inválido: '{cnpj_input}'.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

        else:
            url = f'https://brasilapi.com.br/api/cnpj/v1/{cnpj}'
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    dados = resp.json()
                    resultado = {
                        'CNPJ': dados.get('cnpj', 'Não informado'),
                        'Nome': dados.get('razao_social', 'Não informado'),
                        'Fantasia': dados.get('nome_fantasia', 'Não informado'),
                        'Abertura': dados.get('data_abertura', 'Não informado'),
                        'Situação': dados.get('descricao_situacao_cadastral', 'Não informado'),
                        'Natureza Jurídica': dados.get('natureza_juridica', 'Não informado'),
                        'Atividade Principal': dados.get('cnae_fiscal_descricao', 'Não informado'),
                        'UF': dados.get('uf', 'Não informado'),
                        'Município': dados.get('municipio', 'Não informado'),
                        'Telefone': dados.get('ddd_telefone_1', 'Não informado'),
                        'Email': dados.get('email', 'Não informado'),
                        'Logradouro': dados.get('logradouro', 'Não informado'),
                        'Número': dados.get('numero', 'Não informado'),
                        'Complemento': dados.get('complemento', ''),
                        'Bairro': dados.get('bairro', 'Não informado'),
                        'CEP': dados.get('cep', 'Não informado'),
                    }
                    flash(f"CNPJ {cnpj} consultado com sucesso!", "success")
                    new_log = Log(
                        action="CONSULTA_CNPJ_SUCESSO",
                        details=f"CNPJ '{cnpj}' consultado com sucesso. Razão Social: '{resultado.get('Nome', 'Não informado')}'",
                        user_id=user_id,
                        nome_cliente=resultado.get('Nome', None),
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(new_log)
                    db.session.commit()
                else:
                    erro = 'CNPJ não encontrado ou API indisponível.'
                    flash(erro, "danger")
                    new_log = Log(
                        action="CONSULTA_CNPJ_FALHA",
                        details=f"Consulta CNPJ falhou para '{cnpj}': {erro}",
                        user_id=user_id,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(new_log)
                    db.session.commit()
            except requests.exceptions.Timeout:
                erro = 'Tempo limite da consulta excedido. Tente novamente.'
                flash(erro, "danger")
                new_log = Log(
                    action="CONSULTA_CNPJ_TIMEOUT",
                    details=f"Tempo limite excedido na consulta CNPJ para '{cnpj}'.",
                    user_id=user_id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_log)
                db.session.commit()
            except Exception as e:
                erro = f'Erro na consulta: {e}'
                flash(erro, "danger")
                logger.error(f"Erro inesperado na consulta CNPJ: {str(e)}")
                new_log = Log(
                    action="CONSULTA_CNPJ_ERRO",
                    details=f"Erro inesperado na consulta CNPJ para '{cnpj}': {str(e)}",
                    user_id=user_id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_log)
                db.session.commit()

    return render_template('consulta_cnpj.html', resultado=resultado, erro=erro, cnpj_input=cnpj_input)

@app.route('/logos/<filename>')
def uploaded_logo(filename):
    return send_from_directory(app.config['UPLOAD_LOGO_FOLDER'], filename)

# ============= INICIALIZAÇÃO =============
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("A aplicação está inicializando. Garanta que 'python init_db.py' foi executado para configurar o banco de dados e usuários.")

    app.run(host='0.0.0.0', port=10000, debug=True)