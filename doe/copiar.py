"""Botão "Copiar" para a mensagem (HTML + JavaScript, sem depender do Streamlit)."""
import json


def html_botao_copiar(texto, rotulo="📋 Copiar mensagem"):
    """Devolve o HTML de um botão que copia `texto` para a área de transferência."""
    # json.dumps protege aspas, quebras de linha e emojis; "</" é trocado para não fechar o <script>
    js_texto = json.dumps(texto).replace("</", "<\\/")
    js_rotulo = json.dumps(rotulo)
    return f"""
<meta charset="utf-8">
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin: 0; font-family: sans-serif; }}
  button {{ width: 100%; padding: .65rem 1rem; font-size: 1rem; cursor: pointer;
           border-radius: .5rem; border: 1px solid #8884; background: Canvas; color: CanvasText; }}
  button:hover {{ border-color: #ff4b4b; color: #ff4b4b; }}
</style>
<button id="b"></button>
<script>
  const TEXTO = {js_texto};
  const ROTULO = {js_rotulo};
  const b = document.getElementById('b');
  b.textContent = ROTULO;

  function avisar(ok) {{
    b.textContent = ok ? '✅ Copiado! Agora é só colar no WhatsApp'
                       : '⚠️ Não consegui copiar. Selecione o texto na caixa acima e use Ctrl+C';
    setTimeout(() => b.textContent = ROTULO, 3500);
  }}
  // Plano B para navegadores que bloqueiam a API moderna dentro de quadros
  function copiarAntigo() {{
    const t = document.createElement('textarea');
    t.value = TEXTO; t.style.position = 'fixed'; t.style.opacity = '0';
    document.body.appendChild(t); t.select();
    let ok = false;
    try {{ ok = document.execCommand('copy'); }} catch (e) {{}}
    document.body.removeChild(t);
    return ok;
  }}
  b.addEventListener('click', async () => {{
    try {{ await navigator.clipboard.writeText(TEXTO); avisar(true); }}
    catch (e) {{ avisar(copiarAntigo()); }}
  }});
</script>
"""
