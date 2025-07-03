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

# REMOVIDO: CLIENTES_EXCLUIDOS (Agora obtidos do DB)

def filtrar_clientes_excluidos(df, clientes_excluidos_list=None): # Adicionado argumento
    """
    Remove do DataFrame todas as linhas cujo cliente esteja na lista de excluídos.
    :param clientes_excluidos_list: Lista de strings de clientes a excluir, ou None para padrão.
    """
    if 'Cliente' not in df.columns:
        return df
    
    # Use a lista passada, ou uma lista vazia se nenhuma for passada
    clientes_a_excluir = [c.upper() for c in clientes_excluidos_list] if clientes_excluidos_list else []
    
    if not clientes_a_excluir: # Se a lista estiver vazia, não há nada para filtrar
        return df

    return df[~df['Cliente'].astype(str).str.strip().str.upper().isin(clientes_a_excluir)]

def analyze_pleitos(df, consultor_filter="", clientes_excluidos_list=None, produtos_excluidos_list=None): # Adicionados argumentos
    filtro_texto = "000483 - Aguardando documentação do cliente"
    # REMOVIDO: df = df[~df["Produto"].astype(str).str.strip().str.lower().str.startswith("taxa")]

    df = df[df["Fase"].astype(str).str.strip().str.lower() == filtro_texto.lower()]

    # NOVO: Filtrar produtos excluídos
    if produtos_excluidos_list:
        # Cria uma máscara para produtos que contêm qualquer uma das substrings excluídas
        for prod_excluido_part in produtos_excluidos_list:
            df = df[~df["Produto"].astype(str).str.strip().str.lower().str.contains(prod_excluido_part.lower(), na=False)]
    
    # Remover clientes excluídos (agora passando a lista)
    df = filtrar_clientes_excluidos(df, clientes_excluidos_list)
    
    # PROCESSAMENTO DE HOTLINES (já existe e está ok)
    mask_hotline = df["Produto"].astype(str).str.strip().str.lower().str.contains("hotline", na=False)
    if mask_hotline.any():
        df_hotline = df[mask_hotline].copy()
        df_non_hotline = df[~mask_hotline].copy()
        df_hotline_processed = process_hotlines(df_hotline)
        df = pd.concat([df_non_hotline, df_hotline_processed], ignore_index=True)

    # Filtra hotlines COM valor (já adicionado no último fix)
    df = df[
        (~df['Produto'].astype(str).str.lower().str.contains('hotline')) |
        ((df['Produto'].astype(str).str.lower().str.contains('hotline')) & (df['Valor'].apply(safe_float) == 0))
    ]

    # Aplica o filtro de consultor só no final
    if consultor_filter:
        df = df[df["Consultor"].str.contains(consultor_filter, case=False, na=False)]

    return df

def get_consultor_pleitos(df, consultor):
    """
    Aplica a lógica para o Resumo por Consultor e PDF:
    - Usa a base filtrada por analyze_pleitos.
    - Filtra pelo consultor.
    - Hotlines SEM valor devem constar como pleito.
    - Hotlines COM valor NÃO devem constar como pleito.
    - Demais pleitos (não hotlines) são sempre considerados.
    """
    df = analyze_pleitos(df) # analyze_pleitos já faz a filtragem de clientes e produtos excluídos.
    df = df[df['Consultor'].str.strip().str.lower() == consultor.strip().lower()]

    # Lógica para hotlines:
    # Inclui todas as linhas que NÃO são hotlines
    # OU
    # Inclui hotlines SOMENTE se o valor for 0 (ou seja, não tiver valor)
    df = df[
        (~df['Produto'].astype(str).str.lower().str.contains('hotline')) |
        ((df['Produto'].astype(str).str.lower().str.contains('hotline')) & (df['Valor'].apply(safe_float) == 0))
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