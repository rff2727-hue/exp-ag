"""Google Drive: uma pasta por experimento, com relatórios, Planilhas e Documentos Google e os arquivos de mapa.

Autorização: OAuth 2.0 com *refresh token* da conta Google do responsável (gerado uma vez pelo script
``ferramentas/autorizar_google_drive.py``) e escopo ``drive.file`` — o aplicativo só enxerga as pastas e os arquivos
que ele mesmo criou; o restante do Drive fica inacessível. Contas de serviço não servem para Drive pessoal (não têm
cota de armazenamento), por isso a autorização é a do usuário.

Política de atualização: arquivos gerados pela plataforma (relatórios, planilha-resumo, mapas) são **atualizados no
mesmo arquivo** — o link não muda e o Drive guarda as versões anteriores; documentos de trabalho (diário de campo,
planilha de coleta) são criados **uma única vez** e nunca sobrescritos.

Usa só ``requests`` (API REST v3), sem o SDK do Google.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
ESCOPO = "https://www.googleapis.com/auth/drive.file"
PASTA = "application/vnd.google-apps.folder"
DOC = "application/vnd.google-apps.document"
PLANILHA = "application/vnd.google-apps.spreadsheet"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ErroDrive(RuntimeError):
    pass


@dataclass
class Arquivo:
    """Um arquivo a enviar. ``converter``: DOC ou PLANILHA para virar Documento/Planilha Google."""
    nome: str
    conteudo: bytes
    mime: str
    converter: str | None = None
    subpasta: str | None = None
    uma_vez: bool = False  # documento de trabalho: cria se não existir, nunca sobrescreve


def link_pasta(pasta_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{pasta_id}"


def _escapar(nome: str) -> str:
    return nome.replace("\\", "\\\\").replace("'", "\\'")


class ClienteDrive:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, pasta_raiz: str | None = None,
                 sessao=None, timeout: float = 60) -> None:
        if not (client_id and client_secret and refresh_token):
            raise ErroDrive("Credenciais do Google Drive incompletas (client_id, client_secret e refresh_token).")
        self.client_id, self.client_secret, self.refresh_token = client_id, client_secret, refresh_token
        self.pasta_raiz = pasta_raiz or None
        self.s = sessao or requests.Session()
        self.timeout = timeout
        self._token: str | None = None
        self._expira = 0.0

    # ------------------------------------------------------------------ autenticação
    def token(self) -> str:
        if self._token and time.time() < self._expira - 60:
            return self._token
        r = self.s.post(TOKEN_URL, data={"client_id": self.client_id, "client_secret": self.client_secret,
                                         "refresh_token": self.refresh_token, "grant_type": "refresh_token"},
                        timeout=self.timeout)
        if r.status_code != 200:
            try:
                erro = r.json().get("error", "")
            except ValueError:
                erro = r.text[:200]
            if erro == "invalid_grant":
                raise ErroDrive("A autorização do Google Drive expirou ou foi revogada. Gere um novo refresh_token "
                                "com ferramentas/autorizar_google_drive.py (e deixe o app OAuth como 'Em produção', "
                                "senão o token vence em 7 dias).")
            raise ErroDrive(f"Falha ao autenticar no Google ({r.status_code}): {erro}")
        d = r.json()
        self._token = d["access_token"]
        self._expira = time.time() + float(d.get("expires_in", 3600))
        return self._token

    def _req(self, metodo: str, url: str, **kw):
        cab = kw.pop("headers", {})
        cab["Authorization"] = f"Bearer {self.token()}"
        r = self.s.request(metodo, url, headers=cab, timeout=self.timeout, **kw)
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", "")
            except ValueError:
                msg = r.text[:200]
            e = ErroDrive(f"Google Drive respondeu {r.status_code}: {msg}")
            e.status = r.status_code  # type: ignore[attr-defined]
            raise e
        return r.json() if r.content else {}

    # ------------------------------------------------------------------ pastas e arquivos
    def buscar(self, nome: str, pai: str | None, mime: str | None = None) -> str | None:
        q = [f"name = '{_escapar(nome)}'", "trashed = false"]
        if pai:
            q.append(f"'{pai}' in parents")
        if mime:
            q.append(f"mimeType = '{mime}'")
        d = self._req("GET", f"{API}/files", params={"q": " and ".join(q), "fields": "files(id,name)",
                                                      "spaces": "drive", "pageSize": 10})
        fs = d.get("files", [])
        return fs[0]["id"] if fs else None

    def existe(self, arquivo_id: str) -> bool:
        try:
            d = self._req("GET", f"{API}/files/{arquivo_id}", params={"fields": "id,trashed"})
        except ErroDrive as e:
            if getattr(e, "status", 0) == 404:
                return False
            raise
        return not d.get("trashed", False)

    def pasta(self, nome: str, pai: str | None = None) -> str:
        """Id da pasta (cria se não existir)."""
        pai = pai or self.pasta_raiz
        achada = self.buscar(nome, pai, PASTA)
        if achada:
            return achada
        meta = {"name": nome, "mimeType": PASTA}
        if pai:
            meta["parents"] = [pai]
        return self._req("POST", f"{API}/files", json=meta, params={"fields": "id"})["id"]

    def _multipart(self, meta: dict, conteudo: bytes, mime: str) -> tuple[bytes, str]:
        limite = f"expag{uuid.uuid4().hex}"
        corpo = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
                 f"--{limite}\r\nContent-Type: {mime}\r\n\r\n").encode() + conteudo + f"\r\n--{limite}--".encode()
        return corpo, f"multipart/related; boundary={limite}"

    def enviar(self, arq: Arquivo, pai: str, arquivo_id: str | None = None) -> str:
        """Cria (ou atualiza, se ``arquivo_id`` existir) e devolve o id."""
        if arquivo_id:
            meta = {"name": arq.nome}
            corpo, ct = self._multipart(meta, arq.conteudo, arq.mime)
            try:
                return self._req("PATCH", f"{UPLOAD}/files/{arquivo_id}", data=corpo,
                                 headers={"Content-Type": ct}, params={"uploadType": "multipart", "fields": "id"})["id"]
            except ErroDrive as e:
                if getattr(e, "status", 0) != 404:
                    raise                                  # apagado pelo usuário: recria abaixo
        meta = {"name": arq.nome, "parents": [pai]}
        if arq.converter:
            meta["mimeType"] = arq.converter
        corpo, ct = self._multipart(meta, arq.conteudo, arq.mime)
        return self._req("POST", f"{UPLOAD}/files", data=corpo, headers={"Content-Type": ct},
                         params={"uploadType": "multipart", "fields": "id"})["id"]


def sincronizar(cliente: ClienteDrive, caminho: list[str], arquivos: list[Arquivo], vinculo: dict | None,
                progresso=None) -> dict:
    """Garante a pasta (``caminho`` a partir da raiz) e envia os arquivos. Devolve o novo vínculo
    {"pasta_id", "pasta_url", "arquivos": {chave: id}} — a chave é "subpasta/nome"."""
    vinculo = dict(vinculo or {})
    pasta_id = vinculo.get("pasta_id")
    if not pasta_id or not cliente.existe(pasta_id):
        pai = None
        for nome in caminho:
            pai = cliente.pasta(nome, pai)
        pasta_id = pai
        vinculo["arquivos"] = {}
    ids = dict(vinculo.get("arquivos") or {})
    subpastas: dict[str, str] = {}
    for i, arq in enumerate(arquivos, start=1):
        if progresso:
            progresso(i, len(arquivos), arq.nome)
        destino = pasta_id
        if arq.subpasta:
            if arq.subpasta not in subpastas:
                subpastas[arq.subpasta] = cliente.pasta(arq.subpasta, pasta_id)
            destino = subpastas[arq.subpasta]
        chave = f"{arq.subpasta + '/' if arq.subpasta else ''}{arq.nome}"
        atual = ids.get(chave)
        if arq.uma_vez:
            if atual and cliente.existe(atual):
                continue
            ids[chave] = cliente.enviar(arq, destino)
        else:
            ids[chave] = cliente.enviar(arq, destino, atual)
    return {"pasta_id": pasta_id, "pasta_url": link_pasta(pasta_id), "arquivos": ids}
