import pandas as pd
from datetime import datetime

def safe_float(value):
    """Converte um valor para float de forma segura."""
    try:
        return float(str(value).strip() or "0")
    except:
        return 0

def safe_int(value):
    """Converte um valor para int de forma segura."""
    try:
        return int(str(value).strip())
    except:
        return None

def format_detail(record):
    """Formata detalhes de um registro para exibição."""
    return (f"Produto: {str(record.get('Produto','')).strip()} | "
            f"Cliente: {str(record.get('Cliente','')).strip()} | "
            f"Consultor: {str(record.get('Consultor','')).strip()} | "
            f"Data: {str(record.get('Data Pendência','')).strip()} | "
            f"Valor: {str(record.get('Valor','')).strip()} | "
            f"Código: {str(record.get('Código de Controle','')).strip()}")

def process_hotlines(df_hotline):
    """Processa hotlines para agrupar e formatar detalhes."""
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

def filtrar_clientes_excluidos(df, clientes_excluidos_list=None):
    """Remove linhas cujo cliente esteja na lista de excluídos."""
    if 'Cliente' not in df.columns:
        return df
    
    clientes_a_excluir = [c.upper() for c in clientes_excluidos_list] if clientes_excluidos_list else []
    
    if not clientes_a_excluir:
        return df

    return df[~df['Cliente'].astype(str).str.strip().str.upper().isin(clientes_a_excluir)]

def analyze_pleitos(df, consultor_filter="", clientes_excluidos_list=None, produtos_excluidos_list=None):
    """
    Analisa e filtra pleitos com base em regras específicas, excluindo produtos e clientes.
    """
    filtro_texto = "000483 - Aguardando documentação do cliente"

    df = df[df["Fase"].astype(str).str.strip().str.lower() == filtro_texto.lower()]

    if produtos_excluidos_list:
        for prod_excluido_part in produtos_excluidos_list:
            df = df[~df["Produto"].astype(str).str.strip().str.lower().str.contains(prod_excluido_part.lower(), na=False)]
    
    df = filtrar_clientes_excluidos(df, clientes_excluidos_list)
    
    mask_hotline = df["Produto"].astype(str).str.strip().str.lower().str.contains("hotline", na=False)
    if mask_hotline.any():
        df_hotline = df[mask_hotline].copy()
        df_non_hotline = df[~mask_hotline].copy()
        df_hotline_processed = process_hotlines(df_hotline)
        df = pd.concat([df_non_hotline, df_hotline_processed], ignore_index=True)

    df = df[
        (~df['Produto'].astype(str).str.lower().str.contains('hotline')) |
        ((df['Produto'].astype(str).str.lower().str.contains('hotline')) & (df['Valor'].apply(safe_float) == 0))
    ]

    if consultor_filter:
        df = df[df["Consultor"].str.contains(consultor_filter, case=False, na=False)]

    return df

def get_consultor_pleitos(df, consultor):
    """
    Prepara pleitos para o resumo por consultor e exportação (PDF).
    """
    df = analyze_pleitos(df)
    df = df[df['Consultor'].str.strip().str.lower() == consultor.strip().lower()]

    df = df[
        (~df['Produto'].astype(str).str.lower().str.contains('hotline')) |
        ((df['Produto'].astype(str).str.lower().str.contains('hotline')) & (df['Valor'].apply(safe_float) == 0))
    ]
    return df