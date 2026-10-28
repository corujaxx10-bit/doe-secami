"""4. Mensagem de WhatsApp, montada pelo código (não pela IA)."""
import re

SECOES = [("nomeacao", "👤 *NOMEAÇÕES*"), ("exoneracao", "🚪 *EXONERAÇÕES*"),
          ("designacao", "📌 *DESIGNAÇÕES / COMISSÕES*"), ("dispensa", "↩️ *DISPENSAS*"),
          ("contrato", "📄 *CONTRATOS*"), ("outro", "📋 *OUTROS ATOS*")]
SEPARADOR = "━━━━━━━━━━━━━━━"


def formatar_whatsapp(itens, numero, data):
    itens = [i for i in itens if i.get("relevante_secami")]
    linhas = [f"*📰 DOE-GO nº {numero} – {data}*", "*Atos relativos à SECAMI*", ""]
    if not itens:
        return "\n".join(linhas + ["Nenhum ato relativo à SECAMI nesta edição."])
    if not any(i.get("categoria") in ("nomeacao", "exoneracao") for i in itens):
        linhas += ["_Sem nomeações ou exonerações nesta edição._", ""]
    alertas = False
    for cat, titulo in SECOES:
        grupo = [i for i in itens if i.get("categoria") == cat]
        if not grupo:
            continue
        linhas.append(titulo)
        for i in grupo:
            linhas.append(f"• *{i.get('titulo_ato', 'Ato')}* (pág. {i.get('pagina', '?')}) – {i.get('resumo', '')}")
            for p in i.get("pessoas", []):
                cargo = p.get("cargo_ou_funcao", "") or ""
                if p.get("simbolo"):
                    cargo += f" ({p['simbolo']})"
                extra = f" – {p['detalhe']}" if p.get("detalhe") else ""
                aviso = "" if p.get("conferido") else " ⚠️"
                alertas |= not p.get("conferido")
                linhas.append(f"   ◦ {p['nome']}{' – ' + cargo if cargo else ''}{extra}{aviso}")
        linhas.append("")
    if alertas:
        linhas.append("_⚠️ nome não localizado literalmente no texto – conferir no original._")
    return "\n".join(linhas).strip()


def formatar_sem_ia(selecionados, numero, data):
    """Plano B: mensagem montada só com o texto original, sem IA."""
    linhas = [f"*📰 DOE-GO nº {numero} – {data}*", "*Atos relativos à SECAMI*", ""]
    for a in selecionados:
        partes = [l.strip() for l in a["texto"].splitlines() if l.strip()]
        titulo = partes[0] if partes else "Ato"
        corpo = re.sub(r"\s+", " ", " ".join(partes[1:]))
        linhas.append(f"• *{titulo}* (pág. {a['pagina']})")
        linhas.append(f"   {corpo[:350]}{'...' if len(corpo) > 350 else ''}")
        linhas.append("")
    linhas.append("_⚙️ Resumo automático sem IA (serviço indisponível) – conferir no original._")
    return "\n".join(linhas)


def _chave_ordem(r):
    try:
        return int(str(r["numero"]).replace(".", ""))
    except ValueError:
        return 10**9


def mensagem_unica(resultados):
    """Junta os blocos de todas as edições numa só mensagem, ordenada pelo número."""
    resultados = sorted(resultados, key=_chave_ordem)
    numeros = [r["numero"] for r in resultados]
    partes = ["*📋 ATOS RELATIVOS À SECAMI – DOE-GO*"]
    for r in resultados:
        partes.append(SEPARADOR)
        if r["escaneado"]:
            partes.append(f"*📰 {r['arquivo']}*\n🚫 PDF sem texto legível (escaneado) – leitura manual necessária.")
            continue
        linhas = r["bloco"].split("\n")
        del linhas[1]                                   # remove o "Atos relativos à SECAMI" repetido
        if numeros.count(r["numero"]) > 1:              # mesma edição em 2 arquivos (ex.: suplemento)
            linhas[0] = linhas[0].rstrip("*") + f" ({r['arquivo']})*"
        partes.append("\n".join(linhas).strip())
    return "\n".join(partes)
