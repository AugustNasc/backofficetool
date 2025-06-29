# utils/dias_uteis.py

from datetime import datetime, timedelta, date 

# REMOVIDO: FERIADOS_2025 (Serão obtidos do DB agora)

def dias_uteis_entre_datas(data_ini, data_fim, feriados):
    """
    Calcula os dias úteis entre duas datas, excluindo fins de semana e feriados.

    :param data_ini: Data de início (objeto datetime.date ou string 'DD/MM/YYYY').
    :param data_fim: Data de fim (objeto datetime.date ou string 'DD/MM/YYYY').
    :param feriados: Uma lista de objetos datetime.date representando os feriados a serem excluídos.
    :return: Número de dias úteis.
    """
    if isinstance(data_ini, str):
        data_ini = datetime.strptime(data_ini, "%d/%m/%Y").date()
    if isinstance(data_fim, str):
        data_fim = datetime.strptime(data_fim, "%d/%m/%Y").date()

    # feriados_set já deve vir como set de objetos date de quem chamou
    # Ou, se feriados é uma lista de strings, converter aqui:
    feriados_set = set()
    for f in feriados:
        if isinstance(f, datetime): # Se já for datetime object
            feriados_set.add(f.date())
        elif isinstance(f, date): # Se já for date object
            feriados_set.add(f)
        elif isinstance(f, str): # Se for string 'DD/MM/YYYY'
            try:
                feriados_set.add(datetime.strptime(f.strip(), "%d/%m/%Y").date())
            except Exception:
                continue # Ignora strings inválidas

    count = 0
    data = data_ini
    while data <= data_fim:
        if data.weekday() < 5 and data not in feriados_set: # weekday() < 5 = segunda a sexta
            count += 1
        data += timedelta(days=1)
    return count