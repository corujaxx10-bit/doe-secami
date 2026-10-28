"""5. Coleta automática no site do DOE-GO (https://diariooficial.abc.go.gov.br).

Caminho usado pelo próprio site (conferido em 27/10/2026):
- Edições de um dia:  /apifront/portal/edicoes/edicoes_from_data/AAAA-MM-DD.json
  Resposta: {"erro": "false", "itens": {"0": {"id": "7422", "data": "27/10/2026",
             "numero": "24894", "suplemento": "0", "paginas": "185", ...}, ...}}
  Dia sem edição (fim de semana, feriado, ou antes da publicação):
             {"erro": true, "msg": "Edição não existente!"}
- PDF da edição:      /portal/edicoes/download/<id>
"""
import datetime as dt
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://diariooficial.abc.go.gov.br"
URL_DIA = BASE + "/apifront/portal/edicoes/edicoes_from_data/{data}.json"
URL_DOWNLOAD = BASE + "/portal/edicoes/download/{codigo}"
CABECALHOS = {"User-Agent": "Mozilla/5.0 (monitoramento DOE-GO SECAMI)"}
TEMPO_LIMITE = 90            # segundos por requisição (o PDF principal é grande)
TAMANHO_MAXIMO = 150 * 2**20  # 150 MB


class ErroColeta(Exception):
    """Erro com mensagem já pronta para mostrar ao usuário."""


def _sessao():
    """Sessão com até 3 novas tentativas automáticas em falhas passageiras do site."""
    s = requests.Session()
    s.headers.update(CABECALHOS)
    tentativas = Retry(total=3, backoff_factor=2, status_forcelist=(500, 502, 503, 504),
                       allowed_methods=("GET",))
    s.mount("https://", HTTPAdapter(max_retries=tentativas))
    return s


def _falha_de_acesso(erro):
    return ErroColeta("Não consegui acessar o site do Diário Oficial "
                      f"({erro.__class__.__name__}). O site pode estar fora do ar. "
                      "Tente de novo em alguns minutos ou use a aba Enviar PDF.")


def edicoes_da_data(data):
    """Lista as edições (principal e suplementos) publicadas numa data.

    Devolve lista de dicionários, principal primeiro; lista vazia se não houve edição.
    """
    try:
        r = _sessao().get(URL_DIA.format(data=data.strftime("%Y-%m-%d")), timeout=TEMPO_LIMITE)
        r.raise_for_status()
        resposta = r.json()
    except requests.RequestException as erro:
        raise _falha_de_acesso(erro) from erro
    except ValueError as erro:
        raise ErroColeta("O site respondeu num formato inesperado. "
                         "Use a aba Enviar PDF e avise para ajustar a coleta.") from erro

    if str(resposta.get("erro")).lower() == "true":
        return []  # "Edição não existente!"
    itens = resposta.get("itens") or {}
    itens = itens.values() if isinstance(itens, dict) else itens
    edicoes = []
    for it in itens:
        if not isinstance(it, dict) or not str(it.get("id", "")).isdigit():
            continue
        numero = str(it.get("numero", "?"))
        if numero.isdigit() and len(numero) > 3:
            numero = f"{int(numero):,}".replace(",", ".")  # 24894 -> 24.894
        suplemento = str(it.get("suplemento", "0")) not in ("0", "", "None")
        edicoes.append({
            "codigo": str(it["id"]),
            "data": it.get("data") or data.strftime("%d/%m/%Y"),
            "numero": numero,
            "suplemento": suplemento,
            "paginas": it.get("paginas", "?"),
            "rotulo": f"nº {numero} – {it.get('data', '')}"
                      f"{' – SUPLEMENTO' if suplemento else ''} ({it.get('paginas', '?')} págs.)",
        })
    return sorted(edicoes, key=lambda e: (e["suplemento"], int(e["codigo"])))


def ultima_edicao(ate=None, dias_para_tras=10):
    """Procura, a partir de `ate` (padrão: hoje), o dia mais recente com edição.

    Útil de manhã cedo ou em fim de semana/feriado. Devolve (data, edicoes).
    """
    dia = ate or dt.date.today()
    for _ in range(dias_para_tras + 1):
        edicoes = edicoes_da_data(dia)
        if edicoes:
            return dia, edicoes
        dia -= dt.timedelta(days=1)
    return None, []


def codigo_do_link(texto):
    """Aceita um link de download colado ou só o código numérico."""
    texto = (texto or "").strip()
    m = re.search(r"/edicoes/download/(\d+)", texto) or re.fullmatch(r"(\d+)", texto)
    return m.group(1) if m else None


def baixar_pdf(codigo):
    """Baixa o PDF da edição e confere se é mesmo um PDF."""
    try:
        r = _sessao().get(URL_DOWNLOAD.format(codigo=codigo), timeout=TEMPO_LIMITE, stream=True)
        r.raise_for_status()
        dados = bytearray()
        for pedaco in r.iter_content(1 << 16):
            dados += pedaco
            if len(dados) > TAMANHO_MAXIMO:
                raise ErroColeta("O arquivo do site é grande demais (acima de 150 MB).")
    except requests.RequestException as erro:
        raise ErroColeta(f"Falha ao baixar a edição (código {codigo}): {erro.__class__.__name__}. "
                         "Tente de novo ou use a aba Enviar PDF.") from erro
    if not bytes(dados[:5]).startswith(b"%PDF"):
        raise ErroColeta(f"O site não devolveu um PDF para o código {codigo}. "
                         "Confira o código/link ou use a aba Enviar PDF.")
    nome = _nome_do_arquivo(r.headers.get("Content-Disposition", "")) or f"DOE-GO_{codigo}.pdf"
    return nome, bytes(dados)


def _nome_do_arquivo(disposicao):
    m = re.search(r"filename\*?=(?:UTF-8'')?[\"']?([^\"';]+)", disposicao or "", re.I)
    return m.group(1).strip() if m else None
