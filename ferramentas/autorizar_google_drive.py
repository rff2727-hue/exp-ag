"""Autoriza o Exp-Ag a criar pastas e arquivos no seu Google Drive (executar uma única vez, no seu computador).

Pré-requisitos (Google Cloud Console, https://console.cloud.google.com):
  1. Crie um projeto (ou use um existente) e ative a "Google Drive API".
  2. Em "Tela de consentimento OAuth" (Google Auth Platform): tipo "Externo"; adicione seu e-mail como usuário;
     em "Público-alvo", clique em "Publicar aplicativo" (status "Em produção"). Em "Teste", o Google invalida o
     token em 7 dias. O escopo usado, drive.file, não exige verificação do Google.
  3. Em "Clientes" (Credenciais), crie um "ID do cliente OAuth" do tipo "App para computador" e baixe o JSON.

Uso:
  python ferramentas/autorizar_google_drive.py caminho/para/client_secret_XXXX.json

O navegador abre para você entrar com a conta Google e autorizar. Ao final, o script imprime o bloco
[google_drive] para colar nos Secrets do Streamlit (ou em .streamlit/secrets.toml).

Só usa a biblioteca padrão do Python. O escopo drive.file dá acesso apenas ao que o próprio Exp-Ag criar.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import socket
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

ESCOPO = "https://www.googleapis.com/auth/drive.file"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        dados = json.load(f)
    cfg = dados.get("installed") or dados.get("web")
    if not cfg:
        sys.exit("JSON inesperado: use o arquivo do cliente OAuth do tipo 'App para computador'.")
    client_id, client_secret = cfg["client_id"], cfg["client_secret"]

    porta = _porta_livre()
    redirect = f"http://127.0.0.1:{porta}/"
    verificador = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    estado = secrets.token_urlsafe(16)
    url = AUTH + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": ESCOPO,
        "access_type": "offline", "prompt": "consent", "state": estado,
        "code_challenge": desafio, "code_challenge_method": "S256"})
    resultado: dict = {}

    class Receptor(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            resultado.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = "code" in resultado and resultado.get("state") == estado
            msg = "Autorização concluída. Pode fechar esta aba e voltar ao terminal." if ok else \
                "Autorização não concluída. Volte ao terminal."
            self.wfile.write(f"<html><body style='font-family:sans-serif'><h3>Exp-Ag</h3><p>{msg}</p></body></html>"
                             .encode())

        def log_message(self, *a):  # silencioso
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", porta), Receptor)
    t = threading.Thread(target=servidor.handle_request, daemon=True)
    t.start()
    print("Abrindo o navegador para autorizar… Se não abrir, copie este endereço:\n\n" + url + "\n")
    webbrowser.open(url)
    t.join(timeout=300)
    servidor.server_close()
    if resultado.get("state") != estado or "code" not in resultado:
        sys.exit(f"Autorização não concluída: {resultado.get('error', 'tempo esgotado')}")

    corpo = urllib.parse.urlencode({
        "code": resultado["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verificador}).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN, data=corpo), timeout=30) as r:
        tok = json.load(r)
    if "refresh_token" not in tok:
        sys.exit("O Google não devolveu refresh_token. Revogue o acesso em https://myaccount.google.com/permissions "
                 "e execute de novo.")
    print("Pronto! Cole o bloco abaixo nos Secrets do Streamlit (Settings → Secrets):\n")
    print("[google_drive]")
    print(f'client_id = "{client_id}"')
    print(f'client_secret = "{client_secret}"')
    print(f'refresh_token = "{tok["refresh_token"]}"')
    print('# pasta_raiz = "ID de uma pasta já criada pelo Exp-Ag" (opcional; sem ela, cria "Exp-Ag" na raiz do Drive)')


if __name__ == "__main__":
    main()
