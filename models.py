from datetime import datetime, date
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
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    role = db.relationship('Role', backref=db.backref('users', lazy=True))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(100), unique=True, nullable=False)
    valor = db.Column(db.String(255), nullable=True)
    tipo = db.Column(db.String(50), nullable=True)
    descricao = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Configuracao {self.chave}: {self.valor}>'

class Feriado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, unique=False)
    nome = db.Column(db.String(100), nullable=True)
    localidade = db.Column(db.String(50), nullable=True)
    tipo = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f'<Feriado {self.data.strftime("%d/%m/%Y")} ({self.localidade or "Nacional"})>'

    def format_date_br(self):
        return self.data.strftime('%d/%m/%Y')

class AtividadeJuridica(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(120), nullable=True)
    assunto = db.Column(db.String(255), nullable=True)
    data_criacao = db.Column(db.Date, nullable=False)
    proprietario = db.Column(db.String(120), nullable=True)
    criado_por = db.Column(db.String(120), nullable=True)
    prioridade = db.Column(db.String(50), default='Normal')
    status = db.Column(db.String(50), default='Pendente')
    data_ultimo_status = db.Column(db.DateTime, default=datetime.utcnow)
    areas_pendentes = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f'<AtividadeJuridica {self.assunto} - {self.status}>'

    def to_dict(self):
        return {
            'id': self.id,
            'tipo': self.tipo,
            'assunto': self.assunto,
            'data_criacao': self.data_criacao.strftime('%d/%m/%Y') if self.data_criacao else None,
            'proprietario': self.proprietario,
            'criado_por': self.criado_por,
            'prioridade': self.prioridade,
            'status': self.status,
            'data_ultimo_status': self.data_ultimo_status.strftime('%d/%m/%Y %H:%M') if self.data_ultimo_status else None,
            'areas_pendentes': self.areas_pendentes
        }

class Cancelamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo_controle = db.Column(db.String(50), unique=True, nullable=False)
    nome_cliente = db.Column(db.String(255), nullable=False)
    servico_rsfn = db.Column(db.Boolean, default=False)
    data_recebimento = db.Column(db.Date, nullable=False)
    data_ativacao = db.Column(db.Date, nullable=False)
    aviso_previo_dias = db.Column(db.Integer, nullable=False)
    prazo_contrato_anos = db.Column(db.Integer, nullable=False)
    valor_servicos = db.Column(db.Float, nullable=False)
    percentual_multa_aplicado = db.Column(db.Float, nullable=False)
    valor_multa = db.Column(db.Float, nullable=False)
    paga_multa = db.Column(db.Boolean, default=True)
    data_calculo = db.Column(db.DateTime, default=datetime.utcnow)
    
    data_fim_contrato = db.Column(db.Date)
    data_cancelamento_efetivo = db.Column(db.Date)
    prazo_cumprido_dias = db.Column(db.Integer)
    prazo_faltante_dias = db.Column(db.Integer)
    valor_diario_produto = db.Column(db.Float)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('cancelamentos', lazy=True))

    def __repr__(self):
        return f'<Cancelamento {self.codigo_controle} - {self.nome_cliente}>'

class SlaMensal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mes = db.Column(db.Integer, nullable=False)
    ano = db.Column(db.Integer, nullable=False)
    qtd_dentro_sla = db.Column(db.Integer, nullable=False)
    qtd_fora_sla = db.Column(db.Integer, nullable=False)
    qtd_processos = db.Column(db.Integer, nullable=False)
    realizado_percentual = db.Column(db.Float, nullable=False)
    meta_percentual = db.Column(db.Float, nullable=False)
    data_registro = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('mes', 'ano', name='_mes_ano_uc'),)

    def __repr__(self):
        return f'<SlaMensal {self.mes}/{self.ano} - Realizado: {self.realizado_percentual:.2f}%>'

    def get_mes_nome(self):
        meses_nomes = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
            5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
            9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }
        return meses_nomes.get(self.mes, "Desconhecido")
    
class CnpjConsultaHistorico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('cnpj_consultas', lazy=True))
    cnpj = db.Column(db.String(18), nullable=False)
    razao_social = db.Column(db.String(255), nullable=True)
    nome_fantasia = db.Column(db.String(255), nullable=True)
    data_consulta = db.Column(db.DateTime, default=datetime.utcnow)
    dados_json = db.Column(db.Text, nullable=True) 

    def __repr__(self):
        return f'<CnpjConsultaHistorico {self.cnpj} - {self.razao_social}>'

class CorrecaoMonetariaHistorico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('correcoes_monetarias', lazy=True))
    nome_cliente = db.Column(db.String(255), nullable=True)
    data_calculo = db.Column(db.DateTime, default=datetime.utcnow)
    
    indice_utilizado = db.Column(db.String(20), nullable=False)
    data_inicial = db.Column(db.Date, nullable=False)
    data_final = db.Column(db.Date, nullable=False)
    valor_original = db.Column(db.Float, nullable=False)
    valor_corrigido = db.Column(db.Float, nullable=False)
    percentual_acumulado = db.Column(db.Float, nullable=False)
    fator_acumulado = db.Column(db.Float, nullable=False)
    
    origem_calculo = db.Column(db.String(50), nullable=False)
    detalhes_erro = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<CorrecaoMonetariaHistorico {self.data_calculo.strftime("%d/%m/%Y")} - {self.nome_cliente}>'