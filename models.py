from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    can_view_all = db.Column(db.Boolean, default=False)
    can_edit_all = db.Column(db.Boolean, default=False)
    can_upload_all = db.Column(db.Boolean, default=False)
    can_access_pleitos = db.Column(db.Boolean, default=False)
    can_edit_pleitos = db.Column(db.Boolean, default=False)
    can_access_cancelamento = db.Column(db.Boolean, default=False)
    can_access_monitor_juridico = db.Column(db.Boolean, default=False)
    can_edit_monitor_juridico = db.Column(db.Boolean, default=False)
    can_access_sla = db.Column(db.Boolean, default=False)
    can_edit_sla = db.Column(db.Boolean, default=False)
    can_access_correcao_valores = db.Column(db.Boolean, default=False)
    can_edit_correcao_valores = db.Column(db.Boolean, default=False)
    can_access_consulta_cnpj = db.Column(db.Boolean, default=False)
    can_access_logs = db.Column(db.Boolean, default=False)
    can_manage_users = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Role {self.name}>'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # MUITO IMPORTANTE: role_id DEVE ser nullable=False e SEM default AQUI.
    # O valor será atribuído via código no init_db.py ou na rota /register.
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False) 
    role = db.relationship('Role', backref=db.backref('users', lazy=True))
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Pleito(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consultor = db.Column(db.String(120), nullable=False)
    cliente = db.Column(db.String(120), nullable=False)
    produto = db.Column(db.String(120), nullable=False)
    data_pendencia = db.Column(db.Date, nullable=False)
    valor = db.Column(db.Float)
    codigo_controle = db.Column(db.String(50))
    loja = db.Column(db.String(50))
    fase = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('logs', lazy=True))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    codigo_controle = db.Column(db.String(50), nullable=True)
    nome_cliente = db.Column(db.String(120), nullable=True)