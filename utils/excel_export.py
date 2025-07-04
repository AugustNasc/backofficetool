import pandas as pd
import io 
import xlsxwriter 

from utils.file_processing import analyze_pleitos


def preparar_base_excel(df, filter_column='', filter_value='', clientes_excluidos_list=None, produtos_excluidos_list=None):
    # REMOVIDO: df = filtrar_clientes_excluidos(df) # O filtro agora é feito dentro de analyze_pleitos

    # Aplica o filtro de coluna e valor antes de analyze_pleitos para garantir que a análise seja feita na subseleção
    if filter_column and filter_value:
        if filter_column == 'Valor':
            try:
                filter_num = float(filter_value)
                df = df[df[filter_column] == filter_num]
            except ValueError:
                pass
        elif filter_column == 'Data Pendência':
            try:
                filter_date = pd.to_datetime(filter_value, dayfirst=True).strftime('%d/%m/%Y')
                df = df[df[filter_column].astype(str).str.contains(filter_date)]
            except:
                pass
        else:
            df = df[df[filter_column].astype(str).str.contains(filter_value, case=False, na=False)]
    
    # NOVO: Chamar analyze_pleitos passando as listas de exclusão
    df = analyze_pleitos(df, clientes_excluidos_list=clientes_excluidos_list, produtos_excluidos_list=produtos_excluidos_list)
    return df

def exportar_sla_excel(df_input, output_stream):
    """
    df_input: DataFrame ou lista de dicionários com as colunas:
        ['mes_nome', 'qtd_dentro_sla', 'qtd_fora_sla', 'qtd_processos', 'realizado', 'meta']
    output_stream: io.BytesIO para salvar o Excel temporariamente.
    """
    df = pd.DataFrame(df_input)
    
    # --- Início da correção para KeyError 'realizado' ---
    # Verifica se as colunas 'realizado' e 'meta' existem.
    # Se não existirem com esses nomes, tenta identificar se foram renomeadas
    # para 'Realizado (%)' e 'Meta (%)' (nomes finais do Excel)
    
    # Primeiro, verificar se as colunas com os nomes finais já estão presentes
    if 'Realizado (%)' in df.columns and 'realizado' not in df.columns:
        df.rename(columns={'Realizado (%)': 'realizado'}, inplace=True)
    
    if 'Meta (%)' in df.columns and 'meta' not in df.columns:
        df.rename(columns={'Meta (%)': 'meta'}, inplace=True)

    # Agora, se 'realizado' ou 'meta' ainda não existirem, o problema está na origem dos dados.
    if 'realizado' not in df.columns:
        # Você pode adicionar um log aqui se desejar, como logger.error(...)
        raise KeyError(f"Coluna 'realizado' não encontrada no DataFrame. Colunas disponíveis: {df.columns.tolist()}. Verifique a preparação dos dados em app.py.")
    
    if 'meta' not in df.columns:
        # Você pode adicionar um log aqui se desejar
        raise KeyError(f"Coluna 'meta' não encontrada no DataFrame. Colunas disponíveis: {df.columns.tolist()}. Verifique a preparação dos dados em app.py.")
    # --- Fim da correção para KeyError 'realizado' ---


    # Aplica arredondamento e conversão de tipo nas colunas relevantes
    df_export = df.copy() # Trabalha em uma cópia para evitar SettingWithCopyWarning

    df_export['realizado'] = df_export['realizado'].round(2)
    df_export['meta'] = df_export['meta'].round(0).astype(int)

    # Seleciona e reordena as colunas, depois as renomeia para a saída final do Excel
    df_export = df_export[['mes_nome', 'qtd_dentro_sla', 'qtd_fora_sla', 'qtd_processos', 'realizado', 'meta']]
    df_export.columns = ['Mês', 'Qtd. Dentro SLA', 'Qtd. Fora SLA', 'Qtd. Processos', 'Realizado (%)', 'Meta (%)']
    
    with pd.ExcelWriter(output_stream, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, sheet_name='SLA', index=False)
        worksheet = writer.sheets['SLA']
        worksheet.set_column('A:A', 14)
        worksheet.set_column('B:F', 18)

def exportar_logs_excel(logs, output_stream):
    """
    Exporta uma lista de objetos Log para um arquivo Excel.
    logs: Lista de objetos Log do SQLAlchemy.
    output_stream: io.BytesIO para salvar o Excel temporariamente.
    """
    # Preparar os dados para o DataFrame
    data_for_df = []
    for log in logs:
        data_for_df.append({
            'Data/Hora': log.timestamp.strftime('%d/%m/%Y %H:%M:%S') if log.timestamp else '',
            'Ação': log.action,
            'Código de Controle': log.codigo_controle if log.codigo_controle else '-',
            'Nome do Cliente': log.nome_cliente if log.nome_cliente else '-',
            'Usuário': log.user.username if log.user else 'Desconhecido',
            'Detalhes': log.details if log.details else '-'
        })
    df = pd.DataFrame(data_for_df)

    with pd.ExcelWriter(output_stream, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Logs')
        worksheet = writer.sheets['Logs']
        # Ajustar largura das colunas
        for idx, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_len, 60) # Limita a largura para evitar colunas muito grandes