"""2. Separação dos atos e filtro amplo da SECAMI (sem IA)."""
import re

from .extracao import normalizar

ABRE = re.compile(r"<#ABC#(\d+)#(\d+)#\d+>")
FECHA = re.compile(r"<#ABC#\d+#\d+#\d+/>")
CABECALHO_ORGAO = re.compile(
    r"^(secretaria|agencia|gabinete|casa|controladoria|procuradoria|policia|corpo de bombeiros|"
    r"vice-governadoria|governadoria|departamento|instituto|fundacao|junta|universidade|"
    r"detran|goinfra|saneago|celg|economia|atos do poder|poder )", re.I)

# Termos do filtro (sem acento, minúsculo). Para ampliar, acrescente aqui.
TERMOS_SECAMI = ["casa militar", "secami", "gabinete militar",
                 "marco aurelio godinho"]  # secretário-chefe


def separar_atos(texto):
    """Devolve lista de atos: protocolo, página, órgão (seção) e texto."""
    atos, orgao, pos = [], "", 0
    for m in ABRE.finditer(texto):
        # o trecho entre o fim do ato anterior e este contém o cabeçalho da seção
        intervalo = FECHA.sub("", texto[pos:m.start()])
        for linha in intervalo.splitlines():
            l = linha.strip()
            if CABECALHO_ORGAO.match(normalizar(l)) and len(l) < 120:
                orgao = l
        fim = FECHA.search(texto, m.end())
        corpo = texto[m.end(): fim.start() if fim else len(texto)]
        atos.append({"protocolo": m.group(1), "pagina": int(m.group(2)),
                     "orgao": orgao, "texto": corpo.strip()})
        pos = fim.end() if fim else m.end()
    if not atos:  # edição sem marcadores: corta pelos "Protocolo NNNN"
        for i, bloco in enumerate(re.split(r"Protocolo\s+\d+", texto)):
            atos.append({"protocolo": f"bloco{i}", "pagina": 0, "orgao": "", "texto": bloco.strip()})
    return atos


def filtrar_secami(atos, termos=None):
    """Filtro AMPLO: seção da Casa Militar OU qualquer menção no corpo do ato."""
    termos = termos or TERMOS_SECAMI
    sel = []
    for a in atos:
        orgao_n, corpo_n = normalizar(a["orgao"]), normalizar(a["texto"])
        motivo = []
        if any(t in orgao_n for t in termos):
            motivo.append("seção SECAMI")
        if any(t in corpo_n for t in termos):
            motivo.append("menção no texto")
        if motivo:
            sel.append({**a, "motivo_filtro": ", ".join(motivo)})
    return sel
