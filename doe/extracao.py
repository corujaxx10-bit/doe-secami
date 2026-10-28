"""1. Extração do texto do PDF (mesma lógica do Colab)."""
import io
import re
import unicodedata

import pdfplumber

# Abaixo desta média de caracteres por página, o PDF é tratado como escaneado.
LIMITE_ESCANEADO = 300


def extrair_texto(pdf_bytes):
    """Lê o PDF seguindo a ordem interna do arquivo (respeita as 2 colunas).

    Devolve (texto, numero_de_paginas).
    """
    paginas = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            paginas.append(p.extract_text(use_text_flow=True) or "")
    return "\n".join(paginas), len(paginas)


def parece_escaneado(texto, n_paginas):
    """True se o PDF quase não tem texto (provável imagem escaneada)."""
    media = len(texto.strip()) / max(n_paginas, 1)
    return media < LIMITE_ESCANEADO, media


def normalizar(t):
    """minúsculas, sem acento, junta hifenização de fim de linha, espaços únicos."""
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t or "")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).lower()


def dados_edicao(texto):
    """Número e data da edição, lidos do cabeçalho do DOE-GO."""
    num = re.search(r"N[°º]\s*([\d.]+)", texto)
    data = re.search(r"(\d{1,2}) DE ([A-ZÇ]+) DE (\d{4})", texto)
    return (num.group(1) if num else "?",
            f"{data.group(1)} de {data.group(2).lower()} de {data.group(3)}" if data else "?")
