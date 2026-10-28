"""Processa UM PDF do começo ao fim e devolve tudo o que a tela precisa mostrar."""
import re

from .atos import classificar_atos, separar_atos
from .extracao import dados_edicao, extrair_texto, parece_escaneado
from .ia import chamar_ia, conferir_itens
from .mensagem import formatar_sem_ia, formatar_whatsapp

# Aumente este número sempre que a lógica de seleção mudar: os resultados antigos,
# guardados na memória do app, deixam de ser reaproveitados.
VERSAO_LOGICA = 3


def processar_pdf(nome, pdf_bytes, api_key, estado_ia, avisar=print):
    r = {"arquivo": nome, "numero": "?", "data": "?", "bloco": None, "escaneado": False,
         "total_atos": 0, "selecionados": [], "a_conferir": [], "descartados": [],
         "incidentais": [], "ausentes_ia": [], "usou_ia": False, "erro": None,
         "itens": None}  # itens analisados pela IA (None = edição gerada sem IA)
    try:
        texto, n_pag = extrair_texto(pdf_bytes)
    except Exception as erro:
        r["erro"] = f"Não foi possível abrir o PDF ({erro}). O arquivo pode estar corrompido."
        return r

    escaneado, media = parece_escaneado(texto, n_pag)
    if escaneado:
        r["escaneado"] = True
        avisar(f"🚫 PDF parece escaneado ({media:.0f} caracteres/página): leitura manual necessária.")
        return r

    r["numero"], r["data"] = dados_edicao(texto)
    atos = separar_atos(texto)
    sel, r["a_conferir"], r["descartados"] = classificar_atos(atos)
    r["total_atos"], r["selecionados"] = len(atos), sel
    avisar(f"Edição nº {r['numero']} – {r['data']}: {len(atos)} atos, {len(sel)} da SECAMI, "
           f"{len(r['a_conferir'])} a conferir, {len(r['descartados'])} descartados (outro órgão).")

    if not sel:
        r["bloco"] = formatar_whatsapp([], r["numero"], r["data"])
        r["usou_ia"] = True  # nada a analisar; resultado definitivo
        r["itens"] = []
        return r

    itens = chamar_ia(sel, api_key, estado_ia, avisar) if api_key else None
    if itens is None:
        avisar("⚠️ IA indisponível: mensagem gerada sem IA para este arquivo.")
        r["bloco"] = formatar_sem_ia(sel, r["numero"], r["data"])
        return r

    itens, ausentes = conferir_itens(itens, sel)
    r["usou_ia"] = True
    r["ausentes_ia"] = ausentes

    # Segunda barreira: se o ato NÃO está na seção da Casa Militar e a IA não provou, com um
    # trecho literal, que ele é da SECAMI, ele sai da mensagem e vai para "a conferir".
    por_prot = {a["protocolo"]: a for a in sel}
    mantidos = []
    for it in itens:
        ato = por_prot.get(it["protocolo"])
        if (it["relevante_secami"] and ato and "seção SECAMI" not in ato["motivo_filtro"]
                and not it["ligacao_ok"]):
            r["a_conferir"].append({
                **ato, "item_ia": it,  # análise que a IA já fez, reaproveitada se a pessoa incluir
                "trecho": re.sub(r"\s+", " ", ato["texto"][:400]),
                "motivo_filtro": "a IA não apontou, no texto, trecho que prove a ligação com a SECAMI"})
            continue
        mantidos.append(it)
    r["itens"] = mantidos
    r["incidentais"] = [i for i in mantidos if not i.get("relevante_secami")]
    r["bloco"] = formatar_whatsapp(mantidos, r["numero"], r["data"])
    return r


# ---------------------------------------------------------------- Inclusão manual
def item_incluido_manualmente(ato, api_key, estado_ia, avisar=print):
    """Prepara um ato da lista "a conferir" para entrar na mensagem, por decisão da pessoa.

    Reaproveita a análise da IA se ela já existir; senão consulta a IA só para este ato;
    se a IA estiver indisponível, usa o título e o início do texto, com aviso.
    """
    if ato.get("item_ia"):
        it = dict(ato["item_ia"])
    else:
        it = None
        itens = chamar_ia([ato], api_key, estado_ia, avisar) if api_key else None
        if itens:
            itens, _ = conferir_itens(itens, [ato])
            it = next((dict(i) for i in itens if i["protocolo"] == ato["protocolo"]), None)
    if it is None:
        partes = [l.strip() for l in ato["texto"].splitlines() if l.strip()]
        corpo = re.sub(r"\s+", " ", " ".join(partes[1:]))
        it = {"protocolo": ato["protocolo"], "pagina": ato["pagina"], "categoria": "outro",
              "titulo_ato": partes[0][:120] if partes else "Ato", "pessoas": [],
              "resumo": corpo[:300] + ("..." if len(corpo) > 300 else "")
                        + " (incluído manualmente, sem IA – conferir no original)"}
    it["relevante_secami"] = True  # a pessoa decidiu que o ato é da SECAMI
    return it


def bloco_final(r, extras):
    """Bloco da edição com os atos que a pessoa incluiu à mão.

    `extras`: lista de {"ato": ..., "item": ...}. Não altera `r`, que é compartilhado pela equipe.
    """
    if not extras or r.get("escaneado"):
        return r["bloco"]
    if r.get("itens") is None:  # edição gerada sem IA: mesmo formato do plano B
        return formatar_sem_ia(r["selecionados"] + [e["ato"] for e in extras], r["numero"], r["data"])
    return formatar_whatsapp(r["itens"] + [e["item"] for e in extras], r["numero"], r["data"])
