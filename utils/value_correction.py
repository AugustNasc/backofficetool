import requests
import pandas as pd
from calendar import monthrange

def normalizar_data(data_str, is_final=False):
    data_str = data_str.strip()
    # Caso mês/ano: MM/AAAA
    if '/' in data_str and len(data_str) == 7:
        mes, ano = data_str.split('/')
        mes = int(mes)
        ano = int(ano)
        if is_final:
            ultimo_dia = monthrange(ano, mes)[1]
            return f"{ano}-{mes:02d}-{ultimo_dia:02d}"
        else:
            return f"{ano}-{mes:02d}-01"
    # Caso dia/mês/ano: DD/MM/AAAA
    if '/' in data_str and len(data_str) == 10:
        dia, mes, ano = data_str.split('/')
        return f"{ano}-{int(mes):02d}-{int(dia):02d}"
    # Caso ISO: YYYY-MM-DD
    return data_str

def buscar_fatores(indice, data_inicial, data_final):
    if indice == "IPCA":
        codigo = 433  # IPCA
    elif indice == "IGPM":
        codigo = 189  # IGP-M
    else:
        raise ValueError("Índice não suportado")

    url = f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json'
    resp = requests.get(url)
    df = pd.DataFrame(resp.json())
    df['data'] = pd.to_datetime(df['data'], dayfirst=True)
    df['valor'] = df['valor'].str.replace(',', '.').astype(float)
    df = df[(df['data'] >= pd.to_datetime(data_inicial)) & (df['data'] <= pd.to_datetime(data_final))]
    return df['valor'].tolist()

def corrigir_valor(valor, data_inicial, data_final, indice='IPCA'):
    data_inicial_norm = normalizar_data(data_inicial, is_final=False)
    data_final_norm = normalizar_data(data_final, is_final=True)
    fatores = buscar_fatores(indice, data_inicial_norm, data_final_norm)
    fator_acumulado = 1
    for f in fatores:
        fator_acumulado *= (1 + f/100)
    percentual_acumulado = (fator_acumulado - 1) * 100 if fatores else 0
    valor_corrigido = round(valor * fator_acumulado, 2)
    return {
        'valor_corrigido': valor_corrigido,
        'indice_utilizado': indice,
        'fator_acumulado': fator_acumulado,
        'percentual_acumulado': percentual_acumulado
    }
