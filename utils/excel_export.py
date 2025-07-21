import io 
import pandas as pd
import xlsxwriter

from utils.file_processing import analyze_pleitos

def preparar_base_excel(df, filter_column='', filter_value='', clientes_excluidos_list=None, produtos_excluidos_list=None):
    """
    Prepara a base de dados para exportação Excel, aplicando filtros e análises.
    """
    # Aplica filtro de coluna e valor
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
    
    # Aplica análise de pleitos e exclusões globais
    df = analyze_pleitos(df, clientes_excluidos_list=clientes_excluidos_list, produtos_excluidos_list=produtos_excluidos_list)
    return df

def exportar_sla_excel(df_input, output_stream):
    """
    Exporta dados de SLA para um arquivo Excel.
    df_input: DataFrame ou lista de dicionários com os dados do SLA.
    output_stream: io.BytesIO para salvar o Excel temporariamente.
    """
    df = pd.DataFrame(df_input)
    
    # Renomeia colunas se necessário para garantir chaves consistentes
    if 'Realizado (%)' in df.columns and 'realizado' not in df.columns:
        df.rename(columns={'Realizado (%)': 'realizado'}, inplace=True)
    
    if 'Meta (%)' in df.columns and 'meta' not in df.columns:
        df.rename(columns={'Meta (%)': 'meta'}, inplace=True)

    # Verifica a existência das colunas necessárias para evitar KeyError
    if 'realizado' not in df.columns:
        raise KeyError(f"Coluna 'realizado' não encontrada no DataFrame. Colunas disponíveis: {df.columns.tolist()}.")
    
    if 'meta' not in df.columns:
        raise KeyError(f"Coluna 'meta' não encontrada no DataFrame. Colunas disponíveis: {df.columns.tolist()}.")

    df_export = df.copy()

    df_export['realizado'] = df_export['realizado'].round(2)
    df_export['meta'] = df_export['meta'].round(0).astype(int)

    # Seleciona e renomeia colunas para a saída final
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
        for idx, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_len, 60)