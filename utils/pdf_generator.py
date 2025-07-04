import pandas as pd
from utils.file_processing import get_consultor_pleitos
from fpdf import FPDF
import io

def preparar_base_pdf(df, consultor):
    """
    Aplica a mesma lógica global de contagem de pleitos:
    - Só conta hotlines com valor > 0
    - Usa a base já filtrada
    - Filtra por consultor exato (case insensitive e trim)
    """
    df_pdf = get_consultor_pleitos(df, consultor)
    return df_pdf

def exportar_sla_pdf(resultados, output_stream, meta=90, datahora=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Relatório SLA Mensal", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    if datahora:
        pdf.cell(0, 8, f"Extraído em: {datahora}", ln=True, align="C")
    pdf.cell(0, 10, f"Meta mensal: {int(meta)}%", ln=True, align="C") # Convertendo meta para int na exibição
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
        # NOVO: Formata o valor realizado para 2 casas decimais
        pdf.cell(33, 7, f"{r['realizado']:.2f}%", 1)
        pdf.cell(33, 7, f"{int(r['meta'])}", 1) # Formata meta como inteiro
        pdf.ln()
    pdf.output(output_stream)