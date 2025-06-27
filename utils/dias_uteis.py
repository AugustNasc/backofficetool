from datetime import datetime, timedelta

FERIADOS_2025 = [
    "01/01/2025",  # Confraternização Universal
    "25/01/2025",  # Aniversário SP
    "20/02/2025",  # Carnaval (quarta)
    "03/03/2025",  # Carnaval (segunda)
    "04/03/2025",  # Carnaval (terça)
    "07/04/2025",  # Paixão de Cristo
    "21/04/2025",  # Tiradentes
    "01/05/2025",  # Dia do Trabalho
    "09/07/2025",  # Revolução Constitucionalista SP
    "07/09/2025",  # Independência
    "12/10/2025",  # N. Sra Aparecida
    "02/11/2025",  # Finados
    "15/11/2025",  # Proclamação da República
    "20/11/2025",  # Consciência Negra (SP e RJ)
    "25/12/2025",  # Natal
    "19/06/2025",  # Corpus Christi (SP)
]

def dias_uteis_entre_datas(data_ini, data_fim, feriados):
    if isinstance(data_ini, str):
        data_ini = datetime.strptime(data_ini, "%d/%m/%Y").date()
    if isinstance(data_fim, str):
        data_fim = datetime.strptime(data_fim, "%d/%m/%Y").date()
    feriados_set = set()
    for f in feriados:
        try:
            feriados_set.add(datetime.strptime(f.strip(), "%d/%m/%Y").date())
        except Exception:
            continue
    count = 0
    data = data_ini
    while data <= data_fim:
        if data.weekday() < 5 and data not in feriados_set:
            count += 1
        data += timedelta(days=1)
    return count
