"""App Streamlit: DOE-GO -> atos da SECAMI -> mensagem de WhatsApp.

Rodar no computador:  streamlit run app.py
A chave da IA fica em .streamlit/secrets.toml (local) ou nos Secrets do Streamlit Cloud.
"""
import datetime as dt
import hashlib
import urllib.parse
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

from doe.coleta import ErroColeta, baixar_pdf, codigo_do_link, edicoes_da_data, ultima_edicao
from doe.ia import MODELO_PADRAO
from doe.mensagem import mensagem_unica
from doe.copiar import html_botao_copiar
from doe.pipeline import VERSAO_LOGICA, bloco_final, item_incluido_manualmente, processar_pdf

st.set_page_config(page_title="DOE-GO · SECAMI", page_icon="📰", layout="centered")


# ------------------------------------------------------------ Estado compartilhado
@st.cache_resource
def memoria_compartilhada():
    """Vale para TODA a equipe enquanto o app estiver no ar.

    - "resultados": análise de cada PDF, guardada pelo hash MD5 (evita gastar cota
      da IA quando outra pessoa abre a mesma edição);
    - "ia": o último modelo do Gemini que funcionou.
    """
    return {"resultados": {}, "ia": {"modelo": MODELO_PADRAO}}


@st.cache_data(ttl=10 * 60, show_spinner="Consultando o Diário Oficial...")
def edicoes_do_dia(data):
    """Guardado por 10 min: a equipe toda reaproveita a mesma consulta."""
    return edicoes_da_data(data)


@st.cache_data(ttl=10 * 60, show_spinner="Procurando a última edição publicada...")
def ultima_antes_de(data):
    return ultima_edicao(ate=data)


def hoje_em_goias():
    """O servidor do Streamlit Cloud fica em outro fuso; a data vale pelo horário de Goiás."""
    return dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()


MEMORIA = memoria_compartilhada()


def _ler_chave():
    try:
        return st.secrets.get("GEMINI_API_KEY", "")
    except Exception:  # sem arquivo de secrets
        return ""


API_KEY = _ler_chave()

# ------------------------------------------------------------ Cabeçalho
st.title("📰 DOE-GO · Atos da SECAMI")
st.caption("Busca o Diário Oficial de Goiás, separa os atos da Casa Militar e monta a mensagem de WhatsApp.")
if not API_KEY:
    st.warning("Chave da IA não configurada. As mensagens serão geradas **sem IA** "
               "(título e início de cada ato). Veja o README para configurar.")

# ------------------------------------------------------------ Escolha das edições
pdfs = []  # lista de (nome, bytes)
aba_site, aba_upload = st.tabs(["🌐 Buscar no site", "📤 Enviar PDF"])

with aba_site:
    hoje = hoje_em_goias()
    data = st.date_input("Data da edição", value=hoje, max_value=hoje, format="DD/MM/YYYY")

    edicoes = []
    try:
        edicoes = edicoes_do_dia(data)
        if not edicoes:
            # fim de semana, feriado ou edição de hoje ainda não publicada
            dia_anterior, edicoes = ultima_antes_de(data - dt.timedelta(days=1))
            if edicoes:
                st.info(f"Não há edição em {data:%d/%m/%Y}. "
                        f"Mostrando a última publicada antes dessa data: **{dia_anterior:%d/%m/%Y}**.")
            else:
                st.warning("Não encontrei edições nos 10 dias anteriores a essa data.")
    except ErroColeta as erro:
        st.error(str(erro))

    escolhidas = []
    if edicoes:
        rotulos = {e["codigo"]: e["rotulo"] for e in edicoes}
        escolhidas = st.multiselect("Edições do dia", options=list(rotulos), default=list(rotulos),
                                    format_func=lambda c: rotulos[c],
                                    help="A edição principal e os suplementos do dia já vêm marcados.")

    with st.expander("Outras opções"):
        link = st.text_input("Colar link de download (ou código) de uma edição específica",
                             placeholder="https://diariooficial.abc.go.gov.br/portal/edicoes/download/7422")
        if link:
            codigo = codigo_do_link(link)
            if codigo:
                escolhidas = list(dict.fromkeys(escolhidas + [codigo]))
            else:
                st.error("Link não reconhecido. Ele deve terminar em /portal/edicoes/download/<número>.")
        if st.button("Consultar o site de novo"):
            edicoes_do_dia.clear()
            ultima_antes_de.clear()
            st.rerun()

    buscar = st.button("🔎 Baixar e analisar", type="primary", disabled=not escolhidas,
                       use_container_width=True, key="buscar")

with aba_upload:
    enviados = st.file_uploader("PDFs do Diário Oficial", type="pdf", accept_multiple_files=True)
    analisar_upload = st.button("🔎 Analisar PDFs enviados", type="primary", disabled=not enviados,
                                use_container_width=True, key="analisar_upload")

# ------------------------------------------------------------ Processamento
if buscar:
    with st.status("Baixando do site...", expanded=True) as caixa:
        for codigo in escolhidas:
            try:
                nome, dados = baixar_pdf(codigo)
                pdfs.append((nome, dados))
                caixa.write(f"✓ {nome} ({len(dados) / 2**20:.1f} MB)")
            except ErroColeta as erro:
                caixa.write(f"✗ {erro}")
        caixa.update(label="Download concluído", state="complete")
elif analisar_upload:
    pdfs = [(f.name, f.getvalue()) for f in enviados]

if pdfs:
    resultados, vistos = [], set()
    for nome, dados in pdfs:
        md5 = hashlib.md5(dados).hexdigest()
        if md5 in vistos:
            st.info(f"↺ Ignorado (duplicado): {nome}")
            continue
        vistos.add(md5)

        chave = f"v{VERSAO_LOGICA}:{md5}"  # a versão evita reaproveitar resultados de regras antigas
        guardado = MEMORIA["resultados"].get(chave)
        if guardado:  # já analisado por alguém da equipe
            resultados.append({**guardado, "arquivo": nome})
            continue
        with st.status(f"📄 {nome}", expanded=True) as caixa:
            r = processar_pdf(nome, dados, API_KEY, MEMORIA["ia"], avisar=caixa.write)
            caixa.update(label=f"📄 {nome} – nº {r['numero']}", state="error" if r["erro"] else "complete",
                         expanded=False)
        if r["erro"]:
            st.error(f"{nome}: {r['erro']}")
            continue
        r["chave"] = chave
        if r["usou_ia"] or r["escaneado"]:  # resultado definitivo: guarda para a equipe
            MEMORIA["resultados"][chave] = r
        resultados.append(r)
    st.session_state["resultados"] = resultados

# ------------------------------------------------------------ Resultado
resultados = st.session_state.get("resultados")

# Atos que a PESSOA decidiu incluir à mão (valem só para esta sessão; não alteram o que a equipe vê)
st.session_state.setdefault("incluidos", {})


def com_inclusoes(lista):
    """Devolve os resultados com os atos incluídos manualmente já dentro do bloco de cada edição."""
    saida = []
    for r in lista:
        extras = [v for k, v in st.session_state["incluidos"].items()
                  if k.startswith(r.get("chave", "?") + "|")]
        saida.append({**r, "bloco": bloco_final(r, extras)} if extras else r)
    return saida


if resultados:
    st.divider()
    st.subheader("💬 Mensagem para o WhatsApp")
    n_manuais = len(st.session_state["incluidos"])
    if n_manuais:
        st.caption(f"✅ {n_manuais} ato(s) incluído(s) manualmente nesta mensagem (veja em Conferência).")
    texto = st.text_area("Você pode ajustar o texto antes de enviar",
                         mensagem_unica(com_inclusoes(resultados)), height=320,
                         help="Depois de editar, clique fora da caixa antes de copiar.")
    components.html(html_botao_copiar(texto), height=56)
    c1, c2 = st.columns(2)
    c1.link_button("📲 Abrir no WhatsApp", "https://wa.me/?text=" + urllib.parse.quote(texto),
                   use_container_width=True)
    c2.download_button("⬇️ Baixar .txt", texto, file_name="SECAMI_DOE-GO.txt", use_container_width=True)

    st.subheader("🔍 Conferência por edição")
    for r in resultados:
        n_conferir = len(r["a_conferir"])
        titulo = f"🚫 {r['arquivo']} (escaneado)" if r["escaneado"] else \
                 (f"nº {r['numero']} – {r['data']} · {len(r['selecionados'])} de {r['total_atos']} atos"
                  + (f" · ⚠️ {n_conferir} a conferir" if n_conferir else ""))
        with st.expander(titulo, expanded=bool(n_conferir)):
            if r["escaneado"]:
                st.error("PDF sem texto legível. Faça a leitura manual desta edição.")
                continue
            if not r["usou_ia"]:
                st.warning("Gerado sem IA – conferir no original.")
            if r["ausentes_ia"]:
                st.warning("A IA não devolveu estes protocolos (entraram em 'Outros' com aviso): "
                           + ", ".join(r["ausentes_ia"]))
            if r["incidentais"]:
                st.info("Menção incidental, fora da mensagem: " + ", ".join(
                    f"{i['titulo_ato']} (prot. {i['protocolo']})" for i in r["incidentais"]))
            if r["a_conferir"]:
                st.warning(f"⚠️ {n_conferir} ato(s) citam 'casa/gabinete militar' mas **não foi possível "
                           "confirmar que são da SECAMI**. Eles só entram na mensagem se você clicar em "
                           "**Incluir**. Leia e decida:")
                for a in r["a_conferir"]:
                    st.markdown(f"**Protocolo {a['protocolo']}** · pág. {a['pagina']} · "
                                f"{a['orgao'] or '—'} · _{a['motivo_filtro']}_")
                    st.text(a.get("trecho", ""))
                    ch = f"{r['chave']}|{a['protocolo']}"
                    if ch in st.session_state["incluidos"]:
                        col1, col2 = st.columns([3, 1])
                        col1.success("✅ Incluído na mensagem")
                        if col2.button("↩️ Remover", key=f"rem_{ch}", use_container_width=True):
                            del st.session_state["incluidos"][ch]
                            st.rerun()
                    elif st.button("➕ Incluir na mensagem", key=f"inc_{ch}"):
                        with st.spinner("Analisando o ato..."):
                            item = item_incluido_manualmente(a, API_KEY, MEMORIA["ia"], avisar=st.write) \
                                if r.get("itens") is not None else None
                        st.session_state["incluidos"][ch] = {"ato": a, "item": item}
                        st.rerun()
            if r["descartados"]:
                st.caption("Descartados por citarem 'casa/gabinete militar' de outro órgão: "
                           + "; ".join(f"prot. {a['protocolo']} (pág. {a['pagina']}, {a['orgao'] or '—'})"
                                       for a in r["descartados"]))
            for a in r["selecionados"]:
                st.markdown(f"**Protocolo {a['protocolo']}** · pág. {a['pagina']} · {a['orgao'] or '—'} "
                            f"· _{a['motivo_filtro']}_")
                st.text(a["texto"][:1500] + ("..." if len(a["texto"]) > 1500 else ""))
