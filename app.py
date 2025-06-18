import re
import io
import os
import uuid
import json
import logging
import pandas as pd
import requests
import statistics

from datetime import datetime, timedelta
from uuid import uuid4
from io import BytesIO
from functools import wraps # Importado para os decoradores

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash,
    send_from_directory, abort, make_response, send_file, current_app, jsonify
)
from flask_wtf import FlaskForm
from wtforms import StringField, validators

from werkzeug.utils import secure_filename

# modelos e config
from models import db, User, Log, Pleito, Role # Importado Role
from config import Config

# Bibliotecas de terceiros
from fpdf import FPDF
from dateutil.relativedelta import relativedelta
import xlsxwriter

# Utils do projeto
from utils.pdf_generator import preparar_base_pdf, exportar_sla_pdf
from utils.excel_export import preparar_base_excel, exportar_sla_excel, exportar_logs_excel
from utils.file_processing import (
    analisar_atividades_juridico, process_hotlines,
    analyze_pleitos, filtrar_clientes_excluidos, safe_float
)
from utils.dias_uteis import dias_uteis_entre_datas, FERIADOS_2025
from utils.value_correction import corrigir_valor
from utils.auth import authenticate_user

# ===== FIM DOS IMPORTS ORGANIZADOS =====

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
# Função para passar as permissões do usuário para os templates
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

    if 'current_file' in session:
        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_file'])
            df = pd.read_excel(filepath)
            df = filtrar_clientes_excluidos(df)

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

            df = analyze_pleitos(df)
            display_data = [{
                'Consultor': row.get('Consultor', ''),
                'Cliente': row.get('Cliente', ''),
                'Produto': row.get('Produto', ''),
                'Data Pendência': row.get('Data Pendência', ''),
                'Valor': format_currency_local(row.get('Valor', ''))
            } for _, row in df.head(20).iterrows()]
            data_length = len(df)

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

            threshold_date = datetime.now()
            for consultor in consultores_total:
                pleitos = resumo_dict[consultor]
                df_consultor = df[df['Consultor'] == consultor]
                clientes_unicos = df_consultor['Cliente'].nunique()
                pendencia_dt = pd.to_datetime(df_consultor['Data Pendência'], format='%d/%m/%Y', errors='coerce')
                
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
        resumo=resumo
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

        filter_column = session.get('filter_column', '')
        filter_value = session.get('filter_value', '')
        df = preparar_base_excel(df, filter_column, filter_value)
        
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
    
    logs = Log.query.options(db.joinedload(Log.user)).order_by(Log.timestamp.desc()).all()
    return render_template('logs.html', logs=logs)

@app.route('/exportar_logs')
@permission_required('can_access_logs') # Permissão para exportar logs
def export_logs():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    try:
        logs = Log.query.options(db.joinedload(Log.user)).order_by(Log.timestamp.desc()).all()
        
        output = BytesIO()
        exportar_logs_excel(logs, output)
        output.seek(0)
        
        filename = f"historico_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        user = User.query.filter_by(username=session['username']).first()
        user_id = user.id if user else None
        new_log = Log(
            action="EXPORTAR_LOGS",
            details=f"Histórico de logs exportado para '{filename}'.",
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
@permission_required('can_access_cancelamento') # Acesso ao cálculo de multa
def calcular_multa():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            data_recebimento_str = request.form.get('data_recebimento')
            data_ativacao_str = request.form.get('data_ativacao')

            if not data_recebimento_str or not data_ativacao_str:
                flash('Preencha todas as datas!', 'warning')
                return redirect(url_for('calcular_multa'))

            try:
                data_recebimento = datetime.strptime(data_recebimento_str, '%Y-%m-%d')
                data_ativacao = datetime.strptime(data_ativacao_str, '%Y-%m-%d')
            except ValueError:
                flash('Datas inválidas! Use o formato correto (AAAA-MM-DD).', 'danger')
                return redirect(url_for('calcular_multa'))

            if data_ativacao > data_recebimento:
                flash('A data de ativação não pode ser depois da data de recebimento da carta.', 'danger')
                return redirect(url_for('calcular_multa'))

            valor_servicos_str = request.form.get('valor_servicos')
            try:
                valor_servicos = float(valor_servicos_str)
                if valor_servicos <= 0:
                    flash('O valor dos serviços deve ser maior que zero.', 'danger')
                    return redirect(url_for('calcular_multa'))
            except (TypeError, ValueError):
                flash('Valor dos serviços inválido.', 'danger')
                return redirect(url_for('calcular_multa'))

            servico_rsfn = 'servico' in request.form and request.form['servico'] == 'rsfn'
            if servico_rsfn:
                prazo_contrato = 1
                percentual_multa = 0.50
                aviso_previo = 0
            else:
                try:
                    prazo_contrato = int(request.form.get('prazo_contrato'))
                    aviso_previo = int(request.form.get('aviso_custom') or request.form.get('aviso_previo'))
                except (TypeError, ValueError):
                    flash('Prazo contratual e aviso prévio inválidos.', 'danger')
                    return redirect(url_for('calcular_multa'))

            data_fim_contrato = data_ativacao + relativedelta(years=prazo_contrato) - timedelta(days=1)
            prazo_total_dias = (data_fim_contrato - data_ativacao).days + 1
            data_inicio_aviso = data_recebimento
            data_termino_aviso = data_recebimento + timedelta(days=aviso_previo)
            data_inicio_multa = data_termino_aviso + timedelta(days=1)
            data_cancelamento = data_inicio_multa
            prazo_cumprido = (data_inicio_multa - data_ativacao).days
            prazo_faltante = prazo_total_dias - prazo_cumprido
            valor_diario = valor_servicos / 30 if valor_servicos else 0
            prazo_cumprido_anos = prazo_cumprido / 365
            if servico_rsfn:
                percentual_multa = 0.50
            else:
                if prazo_cumprido_anos < 1:
                    percentual_multa = 0.50
                elif prazo_cumprido_anos < 2:
                    percentual_multa = 0.40
                else:
                    percentual_multa = 0.30

            if servico_rsfn:
                valor_multa = valor_servicos * 0.5
                paga_multa = True
            elif data_cancelamento > data_fim_contrato:
                valor_multa = 0
                paga_multa = False
            else:
                valor_multa = valor_diario * prazo_faltante * percentual_multa
                paga_multa = valor_multa > 0

            nome_cliente = request.form.get('nome_cliente', '').strip()
            codigo_controle = str(uuid4())[:8]

            user = User.query.filter_by(username=session['username']).first()
            user_id = user.id if user else None

            log_action = "CALCULO_MULTA"
            log_details = (
                f"Serviço RSFN: {'Sim' if servico_rsfn else 'Não'} | "
                f"Multa: {percentual_multa*100:.0f}% | "
                f"Valor: R$ {valor_multa:.2f}"
            )
            new_log = Log(
                action=log_action,
                details=log_details,
                user_id=user_id,
                codigo_controle=codigo_controle,
                nome_cliente=nome_cliente if nome_cliente else None,
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
                percentual_multa=percentual_multa*100,
                valor_multa=valor_multa,
                data_calculo=datetime.now().strftime('%d/%m/%Y às %H:%M'),
                codigo_controle=codigo_controle,
                nome_cliente=nome_cliente
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
    return render_template('calcular_multa.html', hoje=hoje)


@app.route('/monitor_juridico', methods=['GET', 'POST'])
@permission_required('can_access_monitor_juridico') # Acesso ao monitor jurídico
def monitor_juridico():
    feriados = list(FERIADOS_2025)
    atividades = []
    liberacoes = []
    erro = None
    df = None

    # === POST do MODAL de FERIADOS (sem upload de arquivo) ===
    if request.method == 'POST' and 'feriados' in request.form and (not request.files or not request.files.get('file') or not request.files.get('file').filename):
        # Verifica permissão para editar feriados
        if not session.get('can_edit_monitor_juridico'):
            flash('Você não tem permissão para editar os feriados.', 'danger')
            # Tenta carregar o arquivo existente se houver, para não perder os dados na tela
            if 'current_juridico_file' in session:
                try:
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_juridico_file'])
                    df = pd.read_excel(filepath)
                except Exception as e:
                    erro = f"Erro ao ler o arquivo: {str(e)}"
            return render_template(
                'monitor_juridico.html',
                atividades=atividades,
                liberacoes=liberacoes,
                feriados=feriados,
                erro=erro
            )

        raw = request.form.get('feriados')
        if raw:
            feriados = [x.strip() for x in raw.split(',') if x.strip()]
        else:
            feriados = list(FERIADOS_2025)
        
        user = User.query.filter_by(username=session['username']).first()
        user_id = user.id if user else None
        new_log = Log(
            action="ATUALIZAR_FERIADOS",
            details=f"Feriados atualizados para: {', '.join(feriados)}",
            user_id=user_id,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_log)
        db.session.commit()

        if 'current_juridico_file' in session:
            try:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_juridico_file'])
                df = pd.read_excel(filepath)
            except Exception as e:
                erro = f"Erro ao ler o arquivo: {str(e)}"

    # === UPLOAD DE PLANILHA ===
    elif request.method == 'POST' and 'file' in request.files and request.files['file'] and request.files['file'].filename:
        # Verifica permissão para upload
        if not session.get('can_upload_all'): # Ou can_upload_monitor_juridico, se mais específico
            flash('Você não tem permissão para carregar planilhas no Monitor Jurídico.', 'danger')
            # Tenta carregar o arquivo existente se houver
            if 'current_juridico_file' in session:
                try:
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_juridico_file'])
                    df = pd.read_excel(filepath)
                except Exception as e:
                    erro = f"Erro ao ler o arquivo: {str(e)}"
            return render_template(
                'monitor_juridico.html',
                atividades=atividades,
                liberacoes=liberacoes,
                feriados=feriados,
                erro=erro
            )

        file = request.files['file']
        try:
            df = pd.read_excel(file)
            
            # NOVO: VALIDAÇÃO DAS COLUNAS DA PLANILHA DE MONITOR JURÍDICO
            required_columns_juridico = [
                'Tipo', 'Assunto', 'Data de Criação', 'Proprietário', 'Criada por', 'Prioridade'
            ]
            
            # Normaliza os nomes das colunas do DataFrame para comparação case-insensitive e strip
            df.columns = df.columns.str.strip() # Remove espaços em branco
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
                
                # Se houver um arquivo anterior carregado, tentamos lê-lo para manter os dados na tela
                if 'current_juridico_file' in session:
                    try:
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_juridico_file'])
                        df = pd.read_excel(filepath)
                    except Exception as e:
                        erro = f"Erro ao reler o arquivo anterior: {str(e)}"
                else:
                    df = None # Nenhuma planilha para processar se for a primeira tentativa

                # Retornar o template com o estado atual (vazio ou com dados anteriores)
                return render_template(
                    'monitor_juridico.html',
                    atividades=atividades, # Estarão vazias ou com os dados da releitura
                    liberacoes=liberacoes,
                    feriados=feriados,
                    erro=erro
                )

            # Se todas as colunas obrigatórias estiverem presentes, procede com o salvamento e processamento
            ext = os.path.splitext(file.filename)[1]
            secure_name = f"{uuid.uuid4().hex}{ext}"
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.seek(0)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_name))
            session['current_juridico_file'] = secure_name
            flash('Planilha de Monitor Jurídico carregada com sucesso!', 'success')
            
            user = User.query.filter_by(username=session['username']).first()
            user_id = user.id if user else None
            new_log = Log(
                action="UPLOAD_JURIDICO",
                details=f"Planilha '{file.filename}' carregada para Monitor Jurídico.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

        except Exception as e:
            # Captura outros erros de leitura do Excel (formato inválido, etc.)
            erro = f"Erro ao ler o arquivo: {str(e)}. Certifique-se de que é um arquivo Excel válido (.xlsx ou .xls)."
            df = None
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

            # Tenta reler o arquivo anterior se existir, para não deixar a tela vazia
            if 'current_juridico_file' in session:
                try:
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['current_juridico_file'])
                    df = pd.read_excel(filepath)
                except Exception as e:
                    erro = f"Erro ao reler o arquivo anterior após erro: {str(e)}"
            else:
                df = None

    # === GET normal ou atualização de página ===
    # O processamento das atividades (atividades_geral, atividades_liberacao)
    # só deve acontecer se df não for None e tiver sido validado.
    # A estrutura atual já garante que df será None ou válido aqui, mas é bom ter em mente.
    if df is not None and not df.empty: # Adicionado 'and not df.empty' para segurança
        mask_squad = df['Tipo'].astype(str).str.contains('Squad Contratação', case=False, na=False)
        mask_analise = df['Assunto'].astype(str).str.contains('AN[ÁA]LISE DE CONTRATO', case=False, na=False, regex=True)
        mask_sol_doc = df['Assunto'].astype(str).str.contains('SOLICITA[ÇC][AÃ]O DE DOCUMENTO', case=False, na=False, regex=True)
        mask_liberacao = df['Assunto'].astype(str).str.contains('LIBERA[ÇC][AÃ]O DE FLUXO', case=False, na=False, regex=True)
        mask_outros_condicionado = ( df['Tipo'].astype(str).str.strip().str.lower() == 'outros') & (df['Assunto'].astype(str).str.contains(r'AN[ÁA]LISE DE CONTRATO|SOLICITA[ÇC][AÃ]O DE DOCUMENTO', case=False, regex=True))
        mask_geral = (mask_squad & (mask_analise | mask_sol_doc)) | mask_outros_condicionado
        atividades_geral = df[mask_geral].copy()
        atividades_liberacao = df[mask_liberacao].copy()

        def primeiro_nome(nome):
            return str(nome).split()[0] if nome else ""

        atividades = []
        for _, row in atividades_geral.iterrows():
            try:
                data_criacao = pd.to_datetime(row['Data de Criação'], dayfirst=True, errors='coerce').date()
            except Exception:
                data_criacao = None
            assunto = row.get('Assunto', '')
            proprietario = primeiro_nome(row.get('Proprietário', ''))
            criador = primeiro_nome(row.get('Criada por', ''))
            prioridade = row.get('Prioridade', '')
            status = row.get('Status', '')
            tipo_atividade = row.get('Tipo', '')
            hoje = datetime.now().date()
            if data_criacao:
                dias = dias_uteis_entre_datas(data_criacao, hoje, feriados)
            else:
                dias = '-'
            cor = ''
            if str(status).lower() == 'concluída':
                cor = 'table-success'
            elif isinstance(dias, int) and dias >= 5:
                cor = 'table-danger'
            elif isinstance(dias, int) and dias == 4:
                cor = 'table-warning'
            elif isinstance(dias, int) and dias <= 1:
                cor = 'table-primary'
            atividades.append({
                'data_criacao': data_criacao.strftime('%d/%m/%Y') if data_criacao else '',
                'assunto': assunto,
                'proprietario': proprietario,
                'criador': criador,
                'prioridade': prioridade,
                'status': status,
                'dias': dias,
                'cor': cor,
                'tipo': tipo_atividade
            })
        atividades = sorted(atividades, key=lambda x: datetime.strptime(x['data_criacao'], "%d/%m/%Y") if x['data_criacao'] else datetime.now())

        liberacoes = []
        for _, row in atividades_liberacao.iterrows():
            try:
                data_criacao = pd.to_datetime(row['Data de Criação'], dayfirst=True, errors='coerce').date()
            except Exception:
                data_criacao = None
            assunto = row.get('Assunto', '')
            proprietario = primeiro_nome(row.get('Proprietário', ''))
            criador = primeiro_nome(row.get('Criada por', ''))
            prioridade = row.get('Prioridade', '')
            status = row.get('Status', '')
            tipo_atividade = row.get('Tipo', '')
            hoje = datetime.now().date()
            if data_criacao:
                dias = dias_uteis_entre_datas(data_criacao, hoje, feriados)
            else:
                dias = '-'
            cor = 'table-secondary'
            liberacoes.append({
                'data_criacao': data_criacao.strftime('%d/%m/%Y') if data_criacao else '',
                'assunto': assunto,
                'proprietario': proprietario,
                'criador': criador,
                'prioridade': prioridade,
                'status': status,
                'dias': dias,
                'cor': cor,
                'tipo': tipo_atividade
            })

    return render_template(
        'monitor_juridico.html',
        atividades=atividades,
        liberacoes=liberacoes,
        feriados=feriados,
        erro=erro
    )

@app.route('/monitor_juridico/status/<int:idx>', methods=['POST'])
@permission_required('can_edit_monitor_juridico') # Permissão para ações de edição no Monitor Jurídico
def marcar_concluida(idx):
    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None
    new_log = Log(
        action="ATIVIDADE_CONCLUIDA",
        details=f"Atividade {idx} marcada como concluída no Monitor Jurídico (frontend-only).",
        user_id=user_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(new_log)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/monitor_juridico/prioridade/<int:idx>', methods=['POST'])
@permission_required('can_edit_monitor_juridico') # Permissão para ações de edição no Monitor Jurídico
def solicitar_prioridade(idx):
    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None
    new_log = Log(
        action="SOLICITAR_PRIORIDADE",
        details=f"Prioridade solicitada para atividade {idx} no Monitor Jurídico (frontend-only).",
        user_id=user_id,
        timestamp=datetime.utcnow()
    )
    db.session.add(new_log)
    db.session.commit()
    return jsonify({'success': True})

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
@permission_required('can_access_sla') # Acesso ao dashboard SLA
def sla_dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    if 'sla_resultados' not in session:
        session['sla_resultados'] = []
    resultados = session['sla_resultados']
    meta = session.get('sla_meta', 90)
    mensagem = None

    user = User.query.filter_by(username=session['username']).first()
    user_id = user.id if user else None

    if request.method == 'POST':
        acao = request.form.get('acao')

        if not acao:
            # Ação de adicionar mês - verifica permissão de edição/upload para SLA
            if not session.get('can_edit_sla'): # Ou can_edit_all
                flash('Você não tem permissão para adicionar dados ao Dashboard SLA.', 'danger')
                return redirect(url_for('sla_dashboard'))

            try:
                mes = int(request.form.get('mes'))
                qtd_dentro = int(request.form.get('qtd_dentro_sla') or 0)
                qtd_fora = int(request.form.get('qtd_fora_sla') or 0)
                qtd_proc = int(request.form.get('qtd_processos') or (qtd_dentro + qtd_fora))
                realizado = (qtd_dentro / qtd_proc) * 100 if qtd_proc > 0 else 0

                mes_nome = MESES_NOME[mes]
                if any(r['mes_nome'] == mes_nome for r in resultados):
                    flash('Esse mês já foi preenchido.', 'warning')
                else:
                    resultados.append({
                        'mes': mes,
                        'mes_nome': mes_nome,
                        'qtd_dentro_sla': qtd_dentro,
                        'qtd_fora_sla': qtd_fora,
                        'qtd_processos': qtd_proc,
                        'realizado': realizado,
                        'meta': meta
                    })
                    resultados.sort(key=lambda x: x['mes'])
                    session['sla_resultados'] = resultados
                    flash(f'Dados de {mes_nome} adicionados com sucesso!', 'success')
                    new_log = Log(
                        action="SLA_ADD_MES",
                        details=f"Dados SLA adicionados para {mes_nome}: Dentro={qtd_dentro}, Fora={qtd_fora}, Processos={qtd_proc}, Realizado={realizado:.2f}%",
                        user_id=user_id,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(new_log)
                    db.session.commit()
            except Exception as e:
                flash(f"Dados inválidos para o mês: {str(e)}.", "danger")
                logger.error(f"Erro ao adicionar dados SLA: {str(e)}")

        elif acao == 'limpar':
            if not session.get('can_edit_sla'): # Ou can_edit_all
                flash('Você não tem permissão para limpar os resultados do Dashboard SLA.', 'danger')
                return redirect(url_for('sla_dashboard'))
            
            session['sla_resultados'] = []
            resultados = []
            flash('Resultados limpos!', 'info')
            new_log = Log(
                action="SLA_LIMPAR_RESULTADOS",
                details="Todos os resultados do Dashboard SLA foram limpos.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

        elif acao == 'definir_meta':
            if not session.get('can_edit_sla'): # Ou can_edit_all
                flash('Você não tem permissão para definir a meta do Dashboard SLA.', 'danger')
                return redirect(url_for('sla_dashboard'))

            meta_input = request.form.get('meta_mensal')
            try:
                meta_input = int(meta_input)
                if 70 <= meta_input <= 100:
                    session['sla_meta'] = meta_input
                    meta = meta_input
                    for r in resultados:
                        r['meta'] = meta
                    flash(f"Meta mensal definida como {meta_input}%", 'success')
                    new_log = Log(
                        action="SLA_DEFINIR_META",
                        details=f"Meta mensal do SLA definida para {meta_input}%.",
                        user_id=user_id,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(new_log)
                    db.session.commit()
                else:
                    flash("Meta fora do intervalo permitido (70% a 100%).", 'warning')
            except Exception as e:
                flash(f"Meta inválida: {str(e)}.", 'danger')
                logger.error(f"Erro ao definir meta SLA: {str(e)}")

        elif acao == 'exportar_excel':
            # Permissão para exportar, geralmente 'can_access_sla' já cobre
            if not resultados or len(resultados) == 0:
                flash('Adicione pelo menos uma linha antes de exportar para Excel!', 'warning')
                return redirect(url_for('sla_dashboard'))
            df = pd.DataFrame(resultados)
            output = io.BytesIO()
            exportar_sla_excel(df, output)
            output.seek(0)
            
            filename = f'dashboard_sla_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            new_log = Log(
                action="SLA_EXPORTAR_EXCEL",
                details=f"Dashboard SLA exportado para Excel: '{filename}'.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

            return send_file(output, download_name=filename, as_attachment=True)

        elif acao == 'exportar_pdf':
            # Permissão para exportar, geralmente 'can_access_sla' já cobre
            if not resultados or len(resultados) == 0:
                flash('Adicione pelo menos uma linha antes de exportar para PDF!', 'warning')
                return redirect(url_for('sla_dashboard'))
            now = datetime.now().strftime('%d/%m/%Y %H:%M')
            output = io.BytesIO()
            exportar_sla_pdf(resultados, output, meta=meta, datahora=now)
            output.seek(0)

            filename = f'dashboard_sla_{now.replace("/","-").replace(":","-")}.pdf'
            new_log = Log(
                action="SLA_EXPORTAR_PDF",
                details=f"Dashboard SLA exportado para PDF: '{filename}'.",
                user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()

            return send_file(output, download_name=filename, as_attachment=True)

        elif acao == 'importar_excel':
            if not session.get('can_upload_all'): # Ou can_upload_sla, se mais específico
                flash('Você não tem permissão para importar dados para o Dashboard SLA.', 'danger')
                return redirect(url_for('sla_dashboard'))

            file = request.files.get('importar_excel')
            if file:
                try:
                    df = pd.read_excel(file)
                    colunas_esperadas = ['Mês', 'Qtd. Dentro SLA', 'Qtd. Fora SLA', 'Qtd. Processos', 'Realizado (%)', 'Meta (%)']
                    if not all(col in df.columns for col in colunas_esperadas):
                        flash("Planilha incompatível! Utilize um arquivo gerado pela própria exportação.", "danger")
                    else:
                        session['sla_resultados'] = []
                        for _, row in df.iterrows():
                            mes_nome = str(row['Mês'])
                            mes = MESES_NOME_INV.get(mes_nome, None)
                            if mes is not None:
                                try:
                                    qtd_dentro = float(str(row['Qtd. Dentro SLA']).replace(',', '.'))
                                    qtd_processos = float(str(row['Qtd. Processos']).replace(',', '.'))
                                    realizado = (qtd_dentro / qtd_processos) * 100 if qtd_processos > 0 else 0
                                except Exception:
                                    qtd_dentro = qtd_processos = realizado = 0
                                session['sla_resultados'].append({
                                    'mes': mes,
                                    'mes_nome': mes_nome,
                                    'qtd_dentro_sla': qtd_dentro,
                                    'qtd_fora_sla': float(str(row['Qtd. Fora SLA']).replace(',', '.')),
                                    'qtd_processos': qtd_processos,
                                    'realizado': realizado,
                                    'meta': float(str(row.get('Meta (%)', meta)).replace(',', '.'))
                                })
                        session['sla_resultados'].sort(key=lambda x: x['mes'])
                        flash('Excel importado com sucesso!', 'success')
                        new_log = Log(
                            action="SLA_IMPORTAR_EXCEL",
                            details=f"Dashboard SLA importado do arquivo '{file.filename}'.",
                            user_id=user_id,
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(new_log)
                        db.session.commit()
                except Exception as e:
                    flash("Erro ao importar: " + str(e), "danger")
                    logger.error(f"Erro ao importar SLA Excel: {str(e)}")
            else:
                flash("Arquivo não selecionado para importação!", "danger")

        elif acao == 'fechar_ano':
            if not session.get('can_edit_sla'): # Ou can_edit_all
                flash('Você não tem permissão para fechar o ano do Dashboard SLA.', 'danger')
                return redirect(url_for('sla_dashboard'))

            if len(resultados) == 12:
                valores_realizados = []
                for r in resultados:
                    try:
                        val = float(str(r['realizado']).replace(',', '.'))
                        valores_realizados.append(val)
                    except Exception:
                        pass
                if valores_realizados:
                    media_ano = statistics.median(valores_realizados)
                else:
                    media_ano = 0
                flash(f"Ano fechado! Média do ano: {media_ano:.2f}%", 'success')
                new_log = Log(
                    action="SLA_FECHAR_ANO",
                    details=f"Ano fiscal do Dashboard SLA fechado. Média anual: {media_ano:.2f}%.",
                    user_id=user_id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(new_log)
                db.session.commit()
            else:
                flash("Ainda não há 12 meses preenchidos para fechar o ano.", 'warning')

    valores_realizados = []
    if resultados:
        for r in resultados:
            try:
                val = float(str(r['realizado']).replace(',', '.'))
                valores_realizados.append(val)
            except Exception:
                pass
    if valores_realizados:
        media_realizado = statistics.median(valores_realizados)
    else:
        media_realizado = 0

    return render_template(
        'sla_dashboard.html',
        resultados=session.get('sla_resultados', []),
        meta=session.get('sla_meta', 90),
        mensagem=mensagem,
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


# ============= INICIALIZAÇÃO =============
if __name__ == '__main__':
    with app.app_context():
        # Esta linha garante que o db.create_all() seja executado caso app.py seja rodado diretamente
        # antes de init_db.py, o que pode causar erros em um ambiente real.
        # O ideal é SEMPRE rodar init_db.py primeiro para setup inicial.
        db.create_all() 
        print("A aplicação está inicializando. Garanta que 'python init_db.py' foi executado para configurar o banco de dados e usuários.")

    app.run(host='0.0.0.0', port=10000, debug=True)
