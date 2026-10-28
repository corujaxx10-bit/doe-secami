# DOE-GO · Atos da SECAMI

App Streamlit que busca o Diário Oficial do Estado de Goiás, separa os atos da
Secretaria de Estado da Casa Militar e monta a mensagem de WhatsApp.

## Como usar
1. Aba **Buscar no site**: a edição mais recente já vem marcada. Clique em **Baixar e analisar**.
   - Se a lista não aparecer, cole o link do botão DOWNLOAD do site (ou só o número do fim do link).
2. Aba **Enviar PDF**: continua disponível para arquivos baixados à mão.
3. Ajuste a mensagem se quiser e use **Copiar**, **Abrir no WhatsApp** ou **Baixar .txt**.
4. Em **Conferência por edição**, veja cada ato encontrado, os avisos ⚠️ e as menções incidentais.

Edições já analisadas ficam guardadas enquanto o app estiver no ar: quando outra pessoa
da equipe abre a mesma edição, o resultado aparece na hora, sem gastar a cota da IA.

## Estrutura
| Arquivo | O que faz |
|---|---|
| `app.py` | Telas do app |
| `doe/coleta.py` | Lista e baixa as edições do site do DOE-GO |
| `doe/extracao.py` | Texto do PDF (pdfplumber, 2 colunas) e detecção de escaneado |
| `doe/atos.py` | Separação dos atos e filtro `TERMOS_SECAMI` |
| `doe/ia.py` | Gemini com troca de modelo, novas tentativas e conferência dos nomes |
| `doe/mensagem.py` | Mensagem de WhatsApp e plano B sem IA |
| `doe/pipeline.py` | Junta tudo para um PDF |

## Publicar de graça (Streamlit Community Cloud)
1. Crie um repositório **privado** no GitHub e envie esta pasta (o `.gitignore` já impede o envio da chave).
2. Entre em https://share.streamlit.io com a conta do GitHub → **Create app** → escolha o
   repositório e o arquivo `app.py`.
3. Em **Advanced settings → Secrets**, cole: `GEMINI_API_KEY = "sua-chave"`.
4. Depois de publicado, em **Settings → Sharing**, restrinja o acesso aos e-mails da equipe.
   Sem isso, qualquer pessoa com o link usa a sua cota da IA.

## Rodar no computador
```
pip install -r requirements.txt
copie .streamlit/secrets.toml.exemplo para .streamlit/secrets.toml e cole a chave
streamlit run app.py
```

## Problemas comuns
- **"Não consegui acessar o site do Diário Oficial"**: o site pode estar fora do ar ou
  bloquear acessos de fora do Brasil (o Streamlit Cloud roda nos EUA). Use o envio manual.
- **"Não encontrei a lista de edições"**: abra **Diagnóstico da coleta** e envie o texto
  para ajustar `doe/coleta.py`.
- **"cota gratuita do dia esgotada"**: o app tenta outros modelos; se todos falharem, a
  mensagem sai sem IA, com aviso para conferir no original.
