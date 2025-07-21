from datetime import datetime, timedelta, date

def dias_uteis_entre_datas(data_ini, data_fim, feriados):
    """
    Calcula os dias úteis entre duas datas, excluindo fins de semana e feriados.

    :param data_ini: Data de início (objeto datetime.date).
    :param data_fim: Data de fim (objeto datetime.date).
    :param feriados: Um set de objetos datetime.date representando os feriados a serem excluídos.
    :return: Número de dias úteis.
    """
    # Converte strings de data para objetos date, se necessário
    if isinstance(data_ini, str):
        data_ini = datetime.strptime(data_ini, "%d/%m/%Y").date()
    if isinstance(data_fim, str):
        data_fim = datetime.strptime(data_fim, "%d/%m/%Y").date()

    feriados_set = set()
    for f in feriados:
        if isinstance(f, datetime):
            feriados_set.add(f.date())
        elif isinstance(f, date):
            feriados_set.add(f)
        elif isinstance(f, str):
            try:
                feriados_set.add(datetime.strptime(f.strip(), "%d/%m/%Y").date())
            except ValueError: # Captura erro se string não for válida, ignora
                continue

    count = 0
    current_date = data_ini
    while current_date <= data_fim:
        if current_date.weekday() < 5 and current_date not in feriados_set:
            count += 1
        current_date += timedelta(days=1)
    return count