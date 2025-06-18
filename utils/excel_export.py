import pandas as pd
from utils.file_processing import analyze_pleitos, filtrar_clientes_excluidos
import io # Importar io para o stream de saída

def preparar_base_excel(df, filter_column='', filter_value=''):
    df = filtrar_clientes_excluidos(df)
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
    df = analyze_pleitos(df)
    return df

def exportar_sla_excel(df, output_stream):
    """
    df: DataFrame ou lista de dicionários com as colunas:
        ['mes_nome', 'qtd_dentro_sla', 'qtd_fora_sla', 'qtd_processos', 'realizado', 'meta']
    output_stream: io.BytesIO para salvar o Excel temporariamente.
    """
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    df = df[['mes_nome', 'qtd_dentro_sla', 'qtd_fora_sla', 'qtd_processos', 'realizado', 'meta']]
    df.columns = ['Mês', 'Qtd. Dentro SLA', 'Qtd. Fora SLA', 'Qtd. Processos', 'Realizado (%)', 'Meta (%)']
    with pd.ExcelWriter(output_stream, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='SLA', index=False)
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