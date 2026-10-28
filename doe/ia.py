"""3. IA (Gemini, camada gratuita) aplicada só aos atos já filtrados."""
import json
import time

from .extracao import normalizar

MODELO_PADRAO = "gemini-flash-lite-latest"  # apelido que o Google atualiza sozinho

PROMPT = """Você analisa atos do Diário Oficial do Estado de Goiás.
Abaixo há atos pré-selecionados por mencionarem a Secretaria de Estado da Casa Militar (SECAMI).
Para CADA ato, devolva um objeto JSON. Regras:
- Use SOMENTE informações escritas no texto. Não deduza nem complete nada.
- Copie nomes de pessoas EXATAMENTE como no texto.
- Se um ato trata de vários órgãos (ex.: decreto com várias nomeações), inclua apenas as pessoas ligadas à SECAMI/Casa Militar.
- "relevante_secami": false se a menção à Casa Militar for incidental (ato de outro órgão sem efeito na SECAMI).
- Em contratos, o "resumo" deve trazer: empresa contratada, objeto em poucas palavras, vigência e valor (se constarem).
- categoria: "nomeacao", "exoneracao", "designacao" (comissões, gestores, fiscais, substitutos), "dispensa", "contrato", "outro".
Formato (lista JSON):
[{"protocolo": "...", "relevante_secami": true, "categoria": "...",
  "titulo_ato": "ex.: Portaria SECAMI nº 148/2026",
  "resumo": "uma frase objetiva do que o ato faz",
  "pessoas": [{"nome": "...", "cargo_ou_funcao": "...", "simbolo": "código do cargo, se houver, senão vazio",
               "detalhe": "ex.: presidente da comissão; a partir de 01/11/2026; vazio se nada"}]}]

ATOS:
"""

# Erros em que vale esperar e tentar de novo o MESMO modelo
TRANSITORIOS = ("503", "UNAVAILABLE", "500", "INTERNAL", "imeout", "timed out", "DEADLINE")
# Erros em que se pula direto para o PRÓXIMO modelo
PULAR_MODELO = ("404", "NOT_FOUND", "429", "RESOURCE_EXHAUSTED")


def montar_entrada_ia(selecionados):
    return PROMPT + "\n\n".join(
        f"### PROTOCOLO {a['protocolo']} (pág. {a['pagina']}, seção: {a['orgao']})\n{a['texto']}"
        for a in selecionados)


def _cliente(api_key):
    from google import genai
    from google.genai import types
    # desiste de cada chamada após 60 s
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60_000))


def _modelos_flash(client):
    try:
        nomes = [m.name.replace("models/", "") for m in client.models.list()]
    except Exception:
        return []
    return sorted([n for n in nomes if "flash" in n
                   and not any(x in n for x in ("image", "tts", "audio", "live"))], reverse=True)


def chamar_ia(selecionados, api_key, estado, avisar=print):
    """Tenta o modelo atual com novas tentativas; se seguir falhando, tenta outros "flash".

    `estado` é um dicionário compartilhado com a chave "modelo" (o último que funcionou).
    Devolve a lista de itens da IA, ou None se nenhum modelo respondeu.
    """
    from google.genai import types
    client = _cliente(api_key)
    atual = estado.get("modelo", MODELO_PADRAO)
    fila = [atual] + [m for m in _modelos_flash(client) if m != atual]
    entrada = montar_entrada_ia(selecionados)
    config = types.GenerateContentConfig(temperature=0, response_mime_type="application/json")
    for modelo in fila:
        for espera in (0, 10, 30):
            if espera:
                avisar(f"Aguardando {espera} s e tentando de novo...")
                time.sleep(espera)
            try:
                avisar(f"⏳ Consultando a IA ({modelo})...")
                resp = client.models.generate_content(model=modelo, contents=entrada, config=config)
                itens = json.loads(resp.text)
                if modelo != atual:
                    avisar(f"✅ Usado o modelo {modelo}; as próximas análises usarão ele também.")
                    estado["modelo"] = modelo
                return [itens] if isinstance(itens, dict) else itens
            except Exception as erro:
                msg = str(erro)
                avisar(f"✗ {modelo}: {explicar_erro(msg)}")
                if any(c in msg for c in PULAR_MODELO):
                    break
                if not any(c in msg for c in TRANSITORIOS):
                    break
    return None


def explicar_erro(msg):
    """Traduz os erros mais comuns da API para quem não é programador."""
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "cota gratuita do dia esgotada para este modelo."
    if "503" in msg or "UNAVAILABLE" in msg:
        return "servidor do Google sobrecarregado no momento."
    if "504" in msg or "DEADLINE" in msg or "imeout" in msg or "timed out" in msg:
        return "a IA demorou demais para responder."
    if "404" in msg or "NOT_FOUND" in msg:
        return "modelo não disponível para esta chave."
    if "API key" in msg or "401" in msg or "403" in msg or "PERMISSION" in msg:
        return "chave da API inválida ou sem permissão."
    if isinstance(msg, str) and msg.startswith(("Expecting", "Unterminated", "Extra data")):
        return "a IA devolveu uma resposta mal formada."
    return msg[:120]


# ---------------------------------------------------------------- Conferência
def _categoria_padrao(cat):
    """Converte qualquer variação ("Nomeação", "comissão"...) para as 6 categorias."""
    c = normalizar(str(cat or ""))
    for chave, cat_ok in (("exonera", "exoneracao"), ("nomea", "nomeacao"),
                          ("dispens", "dispensa"), ("designa", "designacao"),
                          ("comiss", "designacao"), ("contrat", "contrato"),
                          ("aditivo", "contrato")):
        if chave in c:
            return cat_ok
    return "outro"


def conferir_itens(itens, selecionados):
    """Antialucinação e completude.

    - corrige campos ausentes e categorias fora do padrão;
    - marca nomes que não aparecem literalmente no ato original (conferido=False);
    - acrescenta, com aviso, os atos que a IA deixou de devolver (nada some).
    Devolve (itens, protocolos_ausentes).
    """
    por_prot = {a["protocolo"]: a for a in selecionados}
    vistos, limpos = set(), []
    for it in itens if isinstance(itens, list) else []:
        if not isinstance(it, dict):
            continue
        prot = str(it.get("protocolo", "")).strip()
        ato = por_prot.get(prot)
        orig = normalizar(ato["texto"]) if ato else ""
        it["protocolo"] = prot
        it["pagina"] = ato["pagina"] if ato else "?"
        it["relevante_secami"] = it.get("relevante_secami", True) is not False  # na dúvida, entra
        it["categoria"] = _categoria_padrao(it.get("categoria"))
        it["titulo_ato"] = it.get("titulo_ato") or "Ato"
        it["resumo"] = it.get("resumo") or ""
        pessoas = []
        for p in it.get("pessoas") or []:
            if not isinstance(p, dict) or not p.get("nome"):
                continue
            p["conferido"] = bool(orig) and normalizar(p["nome"]) in orig
            pessoas.append(p)
        it["pessoas"] = pessoas
        vistos.add(prot)
        limpos.append(it)

    ausentes = [a for a in selecionados if a["protocolo"] not in vistos]
    for a in ausentes:
        linhas = [l.strip() for l in a["texto"].splitlines() if l.strip()]
        limpos.append({"protocolo": a["protocolo"], "pagina": a["pagina"], "relevante_secami": True,
                       "categoria": "outro", "titulo_ato": linhas[0][:120] if linhas else "Ato",
                       "resumo": "⚠️ não analisado pela IA – conferir no original.",
                       "pessoas": []})
    return limpos, [a["protocolo"] for a in ausentes]
