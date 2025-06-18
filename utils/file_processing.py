import pandas as pd
from datetime import datetime

def safe_float(value):
    try:
        return float(str(value).strip() or "0")
    except:
        return 0

def safe_int(value):
    try:
        return int(str(value).strip())
    except:
        return None

def format_detail(record):
    return (f"Produto: {str(record.get('Produto','')).strip()} | "
            f"Cliente: {str(record.get('Cliente','')).strip()} | "
            f"Consultor: {str(record.get('Consultor','')).strip()} | "
            f"Data: {str(record.get('Data Pendência','')).strip()} | "
            f"Valor: {str(record.get('Valor','')).strip()} | "
            f"Código: {str(record.get('Código de Controle','')).strip()}")

def process_hotlines(df_hotline):
    df = df_hotline.copy()
    df["Produto_norm"] = df["Produto"].astype(str).str.strip().str.lower()
    df["DataPendencia_str"] = df["Data Pendência"].astype(str).str.strip()
    df["group_key"] = df["Produto_norm"] + "_" + df["DataPendencia_str"]

    processed_records = []
    groups = df.groupby("group_key")

    for key, group in groups:
        records = group.to_dict(orient="records")
        paired = [False] * len(records)

        for i in range(len(records)):
            if paired[i]:
                continue

            rec_i = records[i]
            val_i = safe_float(rec_i.get("Valor", "0"))

            found_pair = False
            for j in range(i+1, len(records)):
                if paired[j]:
                    continue

                rec_j = records[j]
                val_j = safe_float(rec_j.get("Valor", "0"))
                code_i = safe_int(rec_i.get("Código de Controle", "0"))
                code_j = safe_int(rec_j.get("Código de Controle", "0"))

                if code_i is not None and code_j is not None and abs(code_i - code_j) == 1:
                    if (val_i > 0 and val_j == 0) or (val_i == 0 and val_j > 0):
                        combined = f"{format_detail(rec_i)} x {format_detail(rec_j)}"
                        rec_i["Detalhe_Complementar"] = combined
                        rec_j["Detalhe_Complementar"] = combined
                        processed_records.extend([rec_i, rec_j])
                        paired[i] = paired[j] = True
                        found_pair = True
                        break

            if not found_pair and not paired[i]:
                rec_i["Detalhe_Complementar"] = format_detail(rec_i) + " x Outra ponta não encontrada"
                processed_records.append(rec_i)

    return pd.DataFrame(processed_records)

# Excluir algum cliente específico
CLIENTES_EXCLUIDOS = [
    'J3 TECNOLOGIA E SISTEMAS LTDA'
]

def filtrar_clientes_excluidos(df):
    """
    Remove do DataFrame todas as linhas cujo cliente esteja na lista de excluídos.
    """
    if 'Cliente' not in df.columns:
        return df
    return df[~df['Cliente'].str.strip().str.upper().isin([c.upper() for c in CLIENTES_EXCLUIDOS])]

def analyze_pleitos(df, consultor_filter=""):
    filtro_texto = "000483 - Aguardando documentação do cliente"
    df = df[~df["Produto"].astype(str).str.strip().str.lower().str.startswith("taxa")]
    df = df[df["Fase"].astype(str).str.strip().str.lower() == filtro_texto.lower()]

    # Remover clientes excluídos logo após o filtro inicial
    df = filtrar_clientes_excluidos(df)

    # PROCESSAMENTO DE HOTLINES: não exclui valor zero!
    mask_hotline = df["Produto"].astype(str).str.strip().str.lower().str.contains("hotline", na=False)
    if mask_hotline.any():
        df_hotline = df[mask_hotline].copy()
        df_non_hotline = df[~mask_hotline].copy()
        df_hotline_processed = process_hotlines(df_hotline)
        df = pd.concat([df_non_hotline, df_hotline_processed], ignore_index=True)

    # Aplica o filtro de consultor só no final
    if consultor_filter:
        df = df[df["Consultor"].str.contains(consultor_filter, case=False, na=False)]

    return df

def get_consultor_pleitos(df, consultor):
    """
    Aplica a mesma lógica do Resumo por Consultor e do PDF:
    - Usa a base filtrada por analyze_pleitos.
    - Filtra pelo consultor.
    - Só considera Hotlines com valor > 0 (para contar pleitos).
    """
    df = analyze_pleitos(df)
    df = df[df['Consultor'].str.strip().str.lower() == consultor.strip().lower()]
    # Só considera hotlines com valor > 0, igual ao Resumo
    df = df[
        (~df['Produto'].astype(str).str.lower().str.contains('hotline')) |
        ((df['Produto'].astype(str).str.lower().str.contains('hotline')) & (df['Valor'].apply(safe_float) > 0))
    ]
    return df

import pandas as pd

def analisar_atividades_juridico(df):
    """
    Filtra atividades do tipo 'Squad Contratação', calcula dias em aberto
    e sinaliza atrasos acima de 6 dias.
    """
    hoje = pd.Timestamp.now().normalize()
    # Filtra apenas as linhas com o tipo correto
    df = df[df['Tipo'].astype(str).str.lower().str.strip() == 'squad contratação']
    # Converte a coluna de data
    df['Data de Criação'] = pd.to_datetime(df['Data de Criação'], dayfirst=True, errors='coerce')
    # Calcula dias em aberto
    df['Dias em aberto'] = (hoje - df['Data de Criação']).dt.days
    # Ordena do mais antigo para o mais novo
    df = df.sort_values(['Dias em aberto', 'Data de Criação'], ascending=[False, True])
    return df
