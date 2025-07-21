from models import User

def authenticate_user(username, password):
    """
    Autentica um usuário verificando o nome de usuário e a senha.
    """
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        return True
    return False