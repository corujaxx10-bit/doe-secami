"""2. Separação dos atos e classificação dos que se relacionam à SECAMI (sem IA).

SECAMI = Secretaria de Estado da Casa Militar (Poder Executivo de Goiás),
secretário-chefe: Cel. Marco Aurélio Godinho.

O filtro trabalha em 3 níveis, para não misturar a SECAMI com o "gabinete militar"
de outros órgãos (ex.: Tribunal de Justiça):
- FORTE: seção da Casa Militar, ou termo que identifica a SECAMI sem ambiguidade
  -> o ato segue para a IA e para a mensagem;
- A CONFERIR: só aparece "casa militar"/"gabinete militar", sem outro órgão por perto
  -> NÃO entra na mensagem; aparece na tela para uma pessoa decidir;
- DESCARTADO: "casa/gabinete militar" colado ao nome de outro órgão
  -> fora da mensagem; fica listado na tela, para transparência.
"""
import re

from .extracao import normalizar

ABRE = re.compile(r"<#ABC#(\d+)#(\d+)#\d+>")
FECHA = re.compile(r"<#ABC#\d+#\d+#\d+/>")

# Cabeçalhos que iniciam uma nova seção (órgão). Incluir os de outros Poderes e
# órgãos evita que um ato deles "herde" a seção da Casa Militar do ato anterior.
CABECALHO_ORGAO = re.compile(
    r"^(secretaria|agencia|gabinete|casa|controladoria|procuradoria|policia|corpo de bombeiros|"
    r"vice-governadoria|governadoria|departamento|instituto|fundacao|junta|universidade|"
    r"detran|goinfra|saneago|celg|economia|atos do poder|poder |"
    r"tribunal|assembleia|ministerio publico|defensoria|municipio|prefeitura|camara|conselho|"
    r"autarquia|empresa)", re.I)

# Termos (sem acento, minúsculo). Para ampliar, acrescente aqui.
TERMOS_FORTES = ["secami", "secretaria de estado da casa militar",
                 "marco aurelio godinho"]          # secretário-chefe
TERMOS_FRACOS = ["casa militar", "gabinete militar"]  # existem também em outros órgãos

FRACOS_RE = re.compile("|".join(re.escape(t) for t in TERMOS_FRACOS))

# Órgãos que, colados a "casa/gabinete militar", indicam que NÃO é a SECAMI.
# (Polícia Militar e Bombeiros ficam de fora de propósito: oficiais deles servem na SECAMI.)
OUTROS_ORGAOS = re.compile(
    r"\b(tribunal de justica|tjgo|tj-go|tribunal de contas|tce|tcm|tcu|"
    r"assembleia legislativa|alego|ministerio publico|mpgo|defensoria|"
    r"camara municipal|camara dos deputados|camara legislativa|prefeitura|"
    r"poder judiciario|poder legislativo|justica federal|justica militar)\b")
JANELA = 160  # caracteres olhados antes e depois do termo fraco


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


def _perto_de_outro_orgao(corpo_n, ocorrencia):
    """True se, ao redor do termo fraco, aparece o nome de outro órgão."""
    ini, fim = max(0, ocorrencia.start() - JANELA), ocorrencia.end() + JANELA
    return bool(OUTROS_ORGAOS.search(corpo_n[ini:fim]))


def _trecho_original(texto, tamanho=200):
    """Pedaço do texto ORIGINAL ao redor da primeira menção, para mostrar na tela."""
    m = re.search(r"(casa|gabinete)\s+militar", texto, re.I)
    if not m:
        return re.sub(r"\s+", " ", texto[:2 * tamanho])
    trecho = texto[max(0, m.start() - tamanho): m.end() + tamanho]
    return "…" + re.sub(r"\s+", " ", trecho).strip() + "…"


def classificar_atos(atos):
    """Devolve (fortes, a_conferir, descartados). Só os 'fortes' vão para a IA e a mensagem."""
    fortes, a_conferir, descartados = [], [], []
    for a in atos:
        orgao_n, corpo_n = normalizar(a["orgao"]), normalizar(a["texto"])
        motivo = []
        if any(t in orgao_n for t in TERMOS_FORTES + TERMOS_FRACOS):
            motivo.append("seção SECAMI")
        if any(t in corpo_n for t in TERMOS_FORTES):
            motivo.append("termo da SECAMI no texto")
        if motivo:
            fortes.append({**a, "motivo_filtro": ", ".join(motivo)})
            continue

        ocorrencias = list(FRACOS_RE.finditer(corpo_n))
        if not ocorrencias:
            continue
        livres = [o for o in ocorrencias if not _perto_de_outro_orgao(corpo_n, o)]
        item = {**a, "trecho": _trecho_original(a["texto"])}
        if livres:
            a_conferir.append({**item, "motivo_filtro":
                               "cita só 'casa/gabinete militar', sem confirmar que é a SECAMI"})
        else:
            descartados.append({**item, "motivo_filtro":
                                "'casa/gabinete militar' de outro órgão (tribunal, assembleia etc.)"})
    return fortes, a_conferir, descartados
