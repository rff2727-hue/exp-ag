"""Fase 3 — integração com o Google Drive (servidor falso: nenhum acesso à rede)."""

import json
import re
from pathlib import Path

import pytest
from tests_util import RAIZ_APP

from motor.exportacao.projeto_json import importar_json
from motor.integracoes import pacote
from motor.integracoes.google_drive import DOC, PASTA, PLANILHA, Arquivo, ClienteDrive, ErroDrive, sincronizar


class _Resp:
    def __init__(self, status, dados=None):
        self.status_code = status
        self._d = dados or {}
        self.content = json.dumps(self._d).encode()
        self.text = self.content.decode()

    def json(self):
        return self._d


class DriveFalso:
    """Implementa o mínimo da API v3 usada pelo cliente."""

    def __init__(self, token_ok=True):
        self.arquivos = {}       # id -> {name, mimeType, parents, conteudo, trashed}
        self.n = 0
        self.chamadas = []
        self.token_ok = token_ok
        self.tokens = 0

    def post(self, url, data=None, timeout=None):
        self.tokens += 1
        if not self.token_ok:
            return _Resp(400, {"error": "invalid_grant"})
        assert data["grant_type"] == "refresh_token"
        return _Resp(200, {"access_token": "tok", "expires_in": 3600})

    def _novo(self, meta, conteudo=b""):
        self.n += 1
        i = f"id{self.n}"
        self.arquivos[i] = {"name": meta["name"], "mimeType": meta.get("mimeType", "bin"),
                            "parents": meta.get("parents", []), "conteudo": conteudo, "trashed": False}
        return i

    @staticmethod
    def _partes(data, headers):
        lim = re.search(r"boundary=(\S+)", headers["Content-Type"]).group(1).encode()
        partes = data.split(b"--" + lim)
        meta = json.loads(partes[1].split(b"\r\n\r\n", 1)[1].strip())
        conteudo = partes[2].split(b"\r\n\r\n", 1)[1][:-2]
        return meta, conteudo

    def request(self, metodo, url, headers=None, timeout=None, params=None, json=None, data=None):
        assert headers["Authorization"] == "Bearer tok"
        self.chamadas.append((metodo, url))
        if metodo == "GET" and url.endswith("/files"):
            q = params["q"]
            nome = re.search(r"name = '((?:[^'\\]|\\.)*)'", q).group(1).replace("\\'", "'")
            pai = re.search(r"'([^']+)' in parents", q)
            achados = [{"id": i, "name": a["name"]} for i, a in self.arquivos.items()
                       if a["name"] == nome and not a["trashed"] and (not pai or pai.group(1) in a["parents"])]
            return _Resp(200, {"files": achados})
        if metodo == "GET":
            i = url.rsplit("/", 1)[1]
            if i not in self.arquivos:
                return _Resp(404, {"error": {"message": "File not found"}})
            return _Resp(200, {"id": i, "trashed": self.arquivos[i]["trashed"]})
        if metodo == "POST" and "/upload/" not in url:
            return _Resp(200, {"id": self._novo(json)})
        if metodo == "POST":
            meta, conteudo = self._partes(data, headers)
            return _Resp(200, {"id": self._novo(meta, conteudo)})
        if metodo == "PATCH":
            i = url.rsplit("/", 1)[1]
            if i not in self.arquivos:
                return _Resp(404, {"error": {"message": "File not found"}})
            meta, conteudo = self._partes(data, headers)
            self.arquivos[i]["conteudo"] = conteudo
            return _Resp(200, {"id": i})
        raise AssertionError(metodo)


def _cliente(falso, raiz=None):
    return ClienteDrive("cid", "seg", "ref", raiz, sessao=falso)


def test_credenciais_incompletas():
    with pytest.raises(ErroDrive):
        ClienteDrive("", "x", "y")


def test_token_revogado_tem_mensagem_clara():
    c = _cliente(DriveFalso(token_ok=False))
    with pytest.raises(ErroDrive, match="expirou ou foi revogada"):
        c.pasta("Exp-Ag")


def test_pastas_nao_duplicam_e_token_e_reutilizado():
    f = DriveFalso()
    c = _cliente(f)
    a = c.pasta("Exp-Ag")
    assert c.pasta("Exp-Ag") == a
    b = c.pasta("Projeto d'água", a)
    assert c.pasta("Projeto d'água", a) == b and f.arquivos[b]["parents"] == [a]
    assert sum(1 for x in f.arquivos.values() if x["mimeType"] == PASTA) == 2
    assert f.tokens == 1


def test_sincronizar_atualiza_no_mesmo_arquivo_e_preserva_documentos_de_trabalho():
    f = DriveFalso()
    c = _cliente(f, raiz="raizX")
    arqs = [Arquivo("Relatório.pdf", b"v1", "application/pdf"),
            Arquivo("Planilha do experimento", b"x1", "xlsx", PLANILHA),
            Arquivo("Diário de campo", b"<p>d</p>", "text/html", DOC, uma_vez=True),
            Arquivo("exp.kmz", b"k1", "kmz", subpasta="Mapas e GIS")]
    v1 = sincronizar(c, ["Exp-Ag", "Projeto", "EXP-01 — Teste"], arqs, None)
    assert v1["pasta_url"].endswith(v1["pasta_id"])
    assert f.arquivos[v1["arquivos"]["Planilha do experimento"]]["mimeType"] == PLANILHA
    kmz = f.arquivos[v1["arquivos"]["Mapas e GIS/exp.kmz"]]
    assert f.arquivos[kmz["parents"][0]]["name"] == "Mapas e GIS"
    raiz = [a for a in f.arquivos.values() if a["name"] == "Exp-Ag"][0]
    assert raiz["parents"] == ["raizX"]
    n_antes = len(f.arquivos)
    arqs2 = [Arquivo("Relatório.pdf", b"v2", "application/pdf"),
             Arquivo("Planilha do experimento", b"x2", "xlsx", PLANILHA),
             Arquivo("Diário de campo", b"<p>novo</p>", "text/html", DOC, uma_vez=True),
             Arquivo("exp.kmz", b"k2", "kmz", subpasta="Mapas e GIS")]
    v2 = sincronizar(c, ["Exp-Ag", "Projeto", "EXP-01 — Teste"], arqs2, v1)
    assert len(f.arquivos) == n_antes                                       # nada duplicado
    assert v2["arquivos"] == v1["arquivos"]
    assert f.arquivos[v1["arquivos"]["Relatório.pdf"]]["conteudo"] == b"v2"
    assert f.arquivos[v1["arquivos"]["Diário de campo"]]["conteudo"] == b"<p>d</p>"   # documento do usuário intacto


def test_arquivo_apagado_e_pasta_apagada_sao_recriados():
    f = DriveFalso()
    c = _cliente(f)
    arqs = [Arquivo("a.pdf", b"1", "application/pdf")]
    v1 = sincronizar(c, ["Exp-Ag", "P", "E"], arqs, None)
    del f.arquivos[v1["arquivos"]["a.pdf"]]
    v2 = sincronizar(c, ["Exp-Ag", "P", "E"], arqs, v1)
    assert v2["arquivos"]["a.pdf"] != v1["arquivos"]["a.pdf"] and v2["arquivos"]["a.pdf"] in f.arquivos
    f.arquivos[v2["pasta_id"]]["trashed"] = True
    v3 = sincronizar(c, ["Exp-Ag", "P", "E"], arqs, v2)
    assert v3["pasta_id"] != v2["pasta_id"]


def test_pacote_do_experimento():
    from motor.gis import feicoes
    from motor.gis.georref import Georreferencia

    p = importar_json((RAIZ_APP / "exemplos" / "cenario_a_dbc_campo.json").read_bytes())
    cj = feicoes.montar(p, Georreferencia(lat=-22.27, lon=-54.81, azimute=10))
    arqs = pacote.arquivos_experimento(p, cj, ["Altura (cm)"])
    nomes = {a.nome for a in arqs}
    assert {"Relatório de planejamento.pdf", "Planilha do experimento", "Memorial descritivo", "Diário de campo",
            "Planilha de coleta", "Plano de locação.pdf", f"{p.meta.codigo}.kmz"} <= nomes
    memorial = next(a for a in arqs if a.nome == "Memorial descritivo")
    assert memorial.converter == DOC and b"Methods (English)" in memorial.conteudo
    assert all(a.conteudo for a in arqs)
    assert pacote.caminho_experimento(p)[0] == "Exp-Ag"


def test_script_de_autorizacao_existe():
    s = (RAIZ_APP / "ferramentas" / "autorizar_google_drive.py").read_text(encoding="utf-8")
    assert "drive.file" in s and "refresh_token" in s and "access_type" in s
    assert Path(RAIZ_APP / "ferramentas" / "autorizar_google_drive.py").exists()
