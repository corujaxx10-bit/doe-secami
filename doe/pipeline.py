"""Processa UM PDF do começo ao fim e devolve tudo o que a tela precisa mostrar."""
from .atos import filtrar_secami, separar_atos
from .extracao import dados_edicao, extrair_texto, parece_escaneado
from .ia import chamar_ia, conferir_itens
from .mensagem import formatar_sem_ia, formatar_whatsapp


def processar_pdf(nome, pdf_bytes, api_key, estado_ia, avisar=print, termos=None):
    r = {"arquivo": nome, "numero": "?", "data": "?", "bloco": None, "escaneado": False,
         "total_atos": 0, "selecionados": [], "incidentais": [], "ausentes_ia": [],
         "usou_ia": False, "erro": None}
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
    sel = filtrar_secami(atos, termos)
    r["total_atos"], r["selecionados"] = len(atos), sel
    avisar(f"Edição nº {r['numero']} – {r['data']}: {len(atos)} atos, {len(sel)} pré-selecionados.")

    if not sel:
        r["bloco"] = formatar_whatsapp([], r["numero"], r["data"])
        r["usou_ia"] = True  # nada a analisar; resultado definitivo
        return r

    itens = chamar_ia(sel, api_key, estado_ia, avisar) if api_key else None
    if itens is None:
        avisar("⚠️ IA indisponível: mensagem gerada sem IA para este arquivo.")
        r["bloco"] = formatar_sem_ia(sel, r["numero"], r["data"])
        return r

    itens, ausentes = conferir_itens(itens, sel)
    r["usou_ia"] = True
    r["ausentes_ia"] = ausentes
    r["incidentais"] = [i for i in itens if not i.get("relevante_secami")]
    r["bloco"] = formatar_whatsapp(itens, r["numero"], r["data"])
    return r
