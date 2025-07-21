import io
from fpdf import FPDF
import pandas as pd

# Importa a função necessária do módulo de processamento de arquivos
from utils.file_processing import get_consultor_pleitos

def preparar_base_pdf(df, consultor):
    """
    Prepara a base de dados para o PDF, filtrando por consultor.
    Aplica a lógica global de contagem de pleitos.
    """
    df_pdf = get_consultor_pleitos(df, consultor)
    return df_pdf

def exportar_sla_pdf(resultados, output_stream, meta=90, datahora=None):
    """
    Gera um relatório SLA Mensal em formato PDF.
    resultados: Lista de dicionários com os dados do SLA.
    output_stream: io.BytesIO para salvar o PDF temporariamente.
    meta: Meta percentual do SLA.
    datahora: Data e hora da extração do relatório.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório SLA Mensal", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    if datahora:
        pdf.cell(0, 8, f"Extraído em: {datahora}", ln=True, align="C")
    pdf.cell(0, 10, f"Meta mensal: {int(meta)}%", ln=True, align="C")
    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    col_titles = ['Mês', 'Qtd. Dentro SLA', 'Qtd. Fora SLA', 'Qtd. Processos', 'Realizado (%)', 'Meta (%)']
    for title in col_titles:
        pdf.cell(33, 7, title, 1, 0, 'C')
    pdf.ln()
    pdf.set_font("Arial", "", 11)
    for r in resultados:
        pdf.cell(33, 7, str(r['mes_nome']), 1)
        pdf.cell(33, 7, str(r['qtd_dentro_sla']), 1)
        pdf.cell(33, 7, str(r['qtd_fora_sla']), 1)
        pdf.cell(33, 7, str(r['qtd_processos']), 1)
        pdf.cell(33, 7, f"{r['realizado']:.2f}%", 1)
        pdf.cell(33, 7, f"{int(r['meta'])}", 1)
        pdf.ln()
    pdf.output(output_stream)