"""Rascunho do assistente: um dicionário simples (serializável em JSON) que a
interface edita passo a passo e que é convertido em ``Planejamento`` no fim.
Os modelos da biblioteca usam o mesmo formato.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from motor.casualizacao.gerador import semente_aleatoria
from motor.dominio import EstruturaTratamentos, para_dict
from motor.geometria.layout import ConfigLayout
from motor.identificadores.codigos import padrao_sugerido
from motor.planejamento import Metadados, Planejamento, planejar

PASTA_MODELOS = Path(__file__).resolve().parents[1] / "templates"


def rascunho_vazio() -> dict:
    return {
        "projeto_id": None,
        "meta": asdict(Metadados(codigo="", titulo="")),
        "delineamento": "DBC",
        "arranjo": "convencional",
        "repeticoes": 4,
        "estrutura": {
            "fatores": [{"nome": "Tratamento", "tipo": "qualitativo", "unidade": "",
                         "niveis": [{"rotulo": f"Tratamento {i}", "valor": None} for i in range(1, 6)]}],
            "adicionais": [],
        },
        "semente": semente_aleatoria(),
        "numeracao": "bloco",
        "padrao_codigo": padrao_sugerido("DBC"),
        "layout": ConfigLayout().para_dict(),
        "modelo": "",
    }


def estrutura_de(r: dict) -> EstruturaTratamentos:
    return EstruturaTratamentos(**r["estrutura"])


def planejamento_de(r: dict) -> Planejamento:
    meta = Metadados(**{k: v for k, v in r["meta"].items() if k in Metadados.__dataclass_fields__})
    return planejar(meta, r["delineamento"], estrutura_de(r), int(r["repeticoes"]), int(r["semente"]),
                    ConfigLayout.de_dict(r["layout"]), r["padrao_codigo"], r["numeracao"],
                    arranjo=r.get("arranjo", "convencional"))


def rascunho_de_planejamento(p: Planejamento, projeto_id: int | None = None) -> dict:
    return {
        "projeto_id": projeto_id,
        "meta": asdict(p.meta),
        "delineamento": p.delineamento.value,
        "arranjo": p.arranjo.value,
        "repeticoes": p.repeticoes,
        "estrutura": para_dict(p.estrutura),
        "semente": p.casualizacao.semente,
        "numeracao": p.numeracao,
        "padrao_codigo": p.padrao_codigo,
        "layout": p.layout.para_dict(),
        "modelo": "",
    }


def listar_modelos() -> list[dict]:
    modelos = []
    for arq in sorted(PASTA_MODELOS.glob("*.json")):
        d = json.loads(arq.read_text(encoding="utf-8"))
        d["arquivo"] = arq.stem
        modelos.append(d)
    return modelos


def aplicar_modelo(modelo: dict, base: dict | None = None) -> dict:
    r = base or rascunho_vazio()
    r["arranjo"] = "convencional"
    for k in ("delineamento", "arranjo", "repeticoes", "estrutura", "numeracao", "padrao_codigo"):
        if k in modelo:
            r[k] = json.loads(json.dumps(modelo[k]))
    r["layout"] = {**ConfigLayout().para_dict(), **modelo.get("layout", {})}
    if "ambiente" in modelo:
        r["meta"]["ambiente"] = modelo["ambiente"]
    r["modelo"] = modelo.get("nome", "")
    return r
