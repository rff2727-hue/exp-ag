"""Experimentos de exemplo, correspondentes aos cenários de aceitação A, B e C."""

from __future__ import annotations

from motor.dominio import EstruturaTratamentos, Fator, Nivel, TratamentoAdicional
from motor.geometria.layout import ConfigLayout
from motor.planejamento import Metadados, Planejamento, planejar


def cenario_a() -> Planejamento:
    """Campo: DBC, 10 tratamentos × 4 blocos = 40 parcelas."""
    e = EstruturaTratamentos([Fator("Tratamento", [Nivel(f"Tratamento {i}") for i in range(1, 11)])])
    meta = Metadados("EX-CAMPO", "Exemplo A — DBC a campo com 10 tratamentos", ambiente="campo",
                     cultura="soja", local="Área experimental", safra="2026/27",
                     objetivos="Demonstrar um DBC com 10 tratamentos e 4 blocos.")
    lay = ConfigLayout(tipo="parcelas", colunas_por_bloco=5, largura=3.0, comprimento=6.0, espaco_x=0.5,
                       espaco_y=1.0, espaco_blocos=2.0, bordadura_lateral=0.5, bordadura_cabeceira=0.5)
    return planejar(meta, "DBC", e, 4, 20261001, lay, "{exp}-P{parcela}-B{bloco}-T{trat}", "bloco")


def cenario_b() -> Planejamento:
    """Casa de vegetação: DIC, 6 tratamentos × 5 repetições = 30 vasos."""
    e = EstruturaTratamentos([Fator("Dose de P", [Nivel(str(v), v) for v in (0, 25, 50, 100, 200, 400)],
                                    "quantitativo", "mg kg⁻¹")])
    meta = Metadados("EX-VASOS", "Exemplo B — DIC em vasos com 6 doses de P", ambiente="casa de vegetação",
                     cultura="milho", objetivos="Demonstrar um DIC em vasos com identificação individual.")
    lay = ConfigLayout(tipo="vasos", colunas_por_bloco=6, diametro_vaso=0.25, espaco_vasos=0.10)
    return planejar(meta, "DIC", e, 5, 20261002, lay, "{exp}-P{parcela}-T{trat}-R{rep}", "sequencial")


def cenario_c() -> Planejamento:
    """Fatorial 3 × 2 com 4 repetições (24 unidades) + exemplo de tratamento adicional ausente."""
    e = EstruturaTratamentos([
        Fator("Fonte de P", [Nivel("Superfosfato triplo"), Nivel("Fosfato natural reativo"), Nivel("Organomineral")]),
        Fator("Inoculação", [Nivel("Sem"), Nivel("Com")]),
    ])
    meta = Metadados("EX-FAT", "Exemplo C — fatorial 3 × 2 em DBC", ambiente="campo", cultura="soja",
                     objetivos="Demonstrar a construção automática da matriz fatorial.")
    lay = ConfigLayout(tipo="parcelas", colunas_por_bloco=6, n_linhas_plantio=6, espacamento_linhas=0.45,
                       linhas_bordadura=1, comprimento=6.0, bordadura_cabeceira=0.5)
    return planejar(meta, "DBC", e, 4, 20261003, lay, "{exp}-P{parcela}-B{bloco}-T{trat}", "bloco")


def cenario_c_adicional() -> Planejamento:
    e = EstruturaTratamentos(
        [Fator("Fonte de P", [Nivel("SFT"), Nivel("FNR"), Nivel("OM")]), Fator("Inoculação", [Nivel("Sem"), Nivel("Com")])],
        [TratamentoAdicional("Testemunha sem P", papel="testemunha")],
    )
    meta = Metadados("EX-FATAD", "Exemplo — fatorial 3 × 2 + 1", ambiente="campo")
    return planejar(meta, "DBC", e, 4, 20261004, ConfigLayout(colunas_por_bloco=7), "{exp}-P{parcela}", "bloco")


def carregar_exemplos(repo) -> list[str]:
    """Cria o projeto EXEMPLOS com os cenários A, B e C. Ignora os já existentes."""
    projetos = {p["codigo"]: p["id"] for p in repo.listar_projetos(incluir_arquivados=True)}
    pid = projetos.get("EXEMPLOS") or repo.criar_projeto(
        "EXEMPLOS", "Experimentos de demonstração", descricao="Cenários de aceitação da Fase 1.")
    criados = []
    for fabrica in (cenario_a, cenario_b, cenario_c):
        p = fabrica()
        if repo.codigo_disponivel(p.meta.codigo):
            repo.salvar_novo(pid, p, "exemplo", "Experimento de demonstração")
            criados.append(p.meta.codigo)
    return criados
