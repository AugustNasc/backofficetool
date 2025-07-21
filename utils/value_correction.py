import requests
import pandas as pd
from calendar import monthrange
from datetime import datetime

def normalizar_data(data_str, is_final=False):
    """
    Normaliza uma string de data para o formato YYYY-MM-DD.
    Suporta MM/AAAA, DD/MM/AAAA e YYYY-MM-DD.
    """
    data_str = data_str.strip()
    if '/' in data_str and len(data_str) == 7: # MM/AAAA
        mes, ano = data_str.split('/')
        mes = int(mes)
        ano = int(ano)
        if is_final:
            ultimo_dia = monthrange(ano, mes)[1]
            return f"{ano}-{mes:02d}-{ultimo_dia:02d}"
        else:
            return f"{ano}-{mes:02d}-01"
    if '/' in data_str and len(data_str) == 10: # DD/MM/AAAA
        dia, mes, ano = data_str.split('/')
        return f"{ano}-{int(mes):02d}-{int(dia):02d}"
    return data_str # Assume YYYY-MM-DD

def buscar_fatores(indice, data_inicial, data_final):
    """
    Busca fatores de correção de índices (IPCA/IGPM) da API do Banco Central.
    """
    codigo = 0
    if indice == "IPCA":
        codigo = 433
    elif indice == "IGPM":
        codigo = 189
    else:
        raise ValueError("Índice não suportado.")

    url = f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json'
    resp = requests.get(url)
    resp.raise_for_status() # Levanta um erro para status de resposta ruins (4xx ou 5xx)
    df = pd.DataFrame(resp.json())
    df['data'] = pd.to_datetime(df['data'], dayfirst=True)
    df['valor'] = df['valor'].str.replace(',', '.').astype(float)
    df = df[(df['data'] >= pd.to_datetime(data_inicial)) & (df['data'] <= pd.to_datetime(data_final))]
    return df['valor'].tolist()

def corrigir_valor(valor, data_inicial, data_final, indice='IPCA'):
    """
    Corrige um valor monetário com base em um índice (IPCA/IGPM) e período.
    """
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