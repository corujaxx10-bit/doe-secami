"""5. Coleta automática no site do DOE-GO (https://diariooficial.abc.go.gov.br).

O PDF de cada edição é servido em /portal/edicoes/download/<código>.
A lista de "Últimas edições" é lida da página inicial. Se o site mudar o jeito
de montar essa lista, a função devolve um diagnóstico para facilitar o ajuste,
e o app continua aceitando upload manual e link colado.
"""
import html
import re

import requests

BASE = "https://diariooficial.abc.go.gov.br"
URL_DOWNLOAD = BASE + "/portal/edicoes/download/{codigo}"
CABECALHOS = {"User-Agent": "Mozilla/5.0 (monitoramento DOE-GO SECAMI)"}
TEMPO_LIMITE = 60          # segundos por requisição
TAMANHO_MAXIMO = 80 * 2**20  # 80 MB


class ErroColeta(Exception):
    """Erro com mensagem já pronta para mostrar ao usuário."""


def _texto_limpo(trecho):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", trecho))).strip()


def listar_edicoes():
    """Devolve (edicoes, diagnostico).

    edicoes: lista de {"codigo": "...", "rotulo": "..."}, da mais nova para a mais antiga.
    diagnostico: texto curto explicando o que foi encontrado na página.
    """
    try:
        r = requests.get(BASE + "/", headers=CABECALHOS, timeout=TEMPO_LIMITE)
        r.raise_for_status()
    except requests.RequestException as erro:
        raise ErroColeta(f"Não consegui acessar o site do Diário Oficial ({erro.__class__.__name__}). "
                         "Tente de novo em alguns minutos ou use o envio manual do PDF.") from erro
    pagina = r.text
    edicoes = {}

    # 1) opções do menu "Últimas edições"
    for m in re.finditer(r"<option[^>]*value=[\"']?(\d+)[\"']?[^>]*>(.*?)</option>", pagina, re.S | re.I):
        codigo, rotulo = m.group(1), _texto_limpo(m.group(2))
        if codigo != "0" and rotulo:
            edicoes[codigo] = rotulo
    # 2) links diretos de download presentes na página
    for m in re.finditer(r"/portal/edicoes/download/(\d+)", pagina):
        if m.group(1) != "0":
            edicoes.setdefault(m.group(1), f"Edição (código {m.group(1)})")

    lista = sorted(({"codigo": c, "rotulo": t} for c, t in edicoes.items()),
                   key=lambda e: int(e["codigo"]), reverse=True)
    diagnostico = (f"Página lida ({len(pagina):,} caracteres); "
                   f"{pagina.lower().count('<option')} opções de menu, "
                   f"{len(re.findall(r'/portal/edicoes/download/', pagina))} links de download, "
                   f"{len(lista)} edições reconhecidas.")
    return lista, diagnostico


def codigo_do_link(texto):
    """Aceita um link de download colado ou só o código numérico."""
    texto = (texto or "").strip()
    m = re.search(r"/edicoes/download/(\d+)", texto) or re.fullmatch(r"(\d+)", texto)
    return m.group(1) if m else None


def baixar_pdf(codigo):
    """Baixa o PDF da edição e confere se é mesmo um PDF."""
    url = URL_DOWNLOAD.format(codigo=codigo)
    try:
        r = requests.get(url, headers=CABECALHOS, timeout=TEMPO_LIMITE, stream=True)
        r.raise_for_status()
        dados = bytearray()
        for pedaco in r.iter_content(1 << 16):
            dados += pedaco
            if len(dados) > TAMANHO_MAXIMO:
                raise ErroColeta("O arquivo do site é grande demais (acima de 80 MB).")
    except requests.RequestException as erro:
        raise ErroColeta(f"Falha ao baixar a edição {codigo} ({erro.__class__.__name__}). "
                         "Tente de novo ou use o envio manual.") from erro
    if not bytes(dados[:5]).startswith(b"%PDF"):
        raise ErroColeta(f"O site não devolveu um PDF para o código {codigo}. "
                         "Confira o código/link ou use o envio manual.")
    nome = _nome_do_arquivo(r.headers.get("Content-Disposition", "")) or f"DOE-GO_{codigo}.pdf"
    return nome, bytes(dados)


def _nome_do_arquivo(disposicao):
    m = re.search(r"filename\*?=(?:UTF-8'')?[\"']?([^\"';]+)", disposicao or "", re.I)
    return m.group(1).strip() if m else None
