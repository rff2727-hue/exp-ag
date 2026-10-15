"""Serialização completa do planejamento em JSON (backup, compartilhamento,
importação). O arquivo guarda as unidades casualizadas *e* a semente: na
importação, a casualização é refeita e comparada com a armazenada, o que
detecta arquivos corrompidos ou editados à mão.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime

from motor.casualizacao.casualizador import casualizar
from motor.casualizacao.gerador import ALGORITMO
from motor.dominio import (
    Arranjo,
    Casualizacao,
    Delineamento,
    EstruturaTratamentos,
    UnidadeExperimental,
    para_dict,
)
from motor.estatistica.tratamentos import gerar_tratamentos
from motor.geometria.layout import ConfigLayout
from motor.planejamento import Metadados, Planejamento
from motor.validacao.verificacoes import verificar_casualizacao

ESQUEMA = "exp-ag/planejamento@2"
ESQUEMAS_ACEITOS = {ESQUEMA, "agro-experimentos/planejamento@1"}  # @1: Fase 1 (sem arranjo)


class ErroImportacao(ValueError):
    pass


def para_json_dict(p: Planejamento) -> dict:
    return {
        "esquema": ESQUEMA,
        "exportado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "meta": asdict(p.meta),
        "delineamento": p.delineamento.value,
        "arranjo": p.arranjo.value,
        "estrutura": para_dict(p.estrutura),
        "repeticoes": p.repeticoes,
        "layout": p.layout.para_dict(),
        "padrao_codigo": p.padrao_codigo,
        "numeracao": p.numeracao,
        "versao": p.versao,
        "casualizacao": {
            "semente": p.casualizacao.semente,
            "algoritmo": p.casualizacao.algoritmo,
            "unidades": [asdict(u) for u in p.casualizacao.unidades],
        },
        "tratamentos": [para_dict(t) for t in p.tratamentos],
    }


def exportar_json(p: Planejamento) -> bytes:
    return json.dumps(para_json_dict(p), ensure_ascii=False, indent=2).encode("utf-8")


def de_json_dict(d: dict) -> Planejamento:
    if d.get("esquema") not in ESQUEMAS_ACEITOS:
        raise ErroImportacao(f"Arquivo não reconhecido (esperado esquema '{ESQUEMA}').")
    try:
        meta = Metadados(**{k: v for k, v in d["meta"].items() if k in Metadados.__dataclass_fields__})
        delineamento = Delineamento(d["delineamento"])
        arranjo = Arranjo(d.get("arranjo", "convencional"))
        estrutura = EstruturaTratamentos(**d["estrutura"])
        r = int(d["repeticoes"])
        layout = ConfigLayout.de_dict(d["layout"])
        c = d["casualizacao"]
        unidades = [UnidadeExperimental(**u) for u in c["unidades"]]
        tratamentos = gerar_tratamentos(estrutura)
        niveis = [len(f.niveis) for f in estrutura.fatores] if arranjo is not Arranjo.CONVENCIONAL else [0, 0]
        cas = Casualizacao(delineamento, int(c["semente"]), c["algoritmo"], unidades, len(tratamentos), r, arranjo,
                           niveis[0], niveis[1])
    except (KeyError, TypeError, ValueError) as exc:
        raise ErroImportacao(f"Arquivo incompleto ou inválido: {exc}") from exc
    erros = verificar_casualizacao(cas)
    if erros:
        raise ErroImportacao("Casualização inconsistente: " + "; ".join(erros))
    if cas.algoritmo == ALGORITMO:
        ref = casualizar(delineamento, len(tratamentos), r, cas.semente, d.get("numeracao", "sequencial"), arranjo,
                         (cas.niveis_a, cas.niveis_b) if arranjo is not Arranjo.CONVENCIONAL else None)

        def chave(us):
            return [(u.numero, u.parcela, u.tratamento, u.bloco, u.repeticao, u.posicao, u.principal, u.sub, u.linha,
                     u.coluna) for u in us]
        if chave(ref.unidades) != chave(unidades):
            raise ErroImportacao("As unidades do arquivo não correspondem à semente informada "
                                 "(o arquivo pode ter sido editado manualmente).")
    return Planejamento(meta, delineamento, estrutura, r, layout, d.get("padrao_codigo", "{exp}-P{parcela}"),
                        d.get("numeracao", "sequencial"), tratamentos, cas, int(d.get("versao", 1)), arranjo)


def importar_json(dados: bytes | str) -> Planejamento:
    try:
        d = json.loads(dados)
    except json.JSONDecodeError as exc:
        raise ErroImportacao(f"JSON inválido: {exc}") from exc
    return de_json_dict(d)
