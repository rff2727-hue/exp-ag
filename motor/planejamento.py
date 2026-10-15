"""Orquestração pura do planejamento: estrutura → tratamentos → casualização →
identificadores → croqui. Ponto único de entrada usado pela aplicação e pelos
testes de aceitação.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from motor.casualizacao.casualizador import casualizar
from motor.dominio import Ambiente, Arranjo, Casualizacao, Delineamento, EstruturaTratamentos, Tratamento
from motor.estatistica.delineamentos import avisos_planejamento
from motor.estatistica.tratamentos import gerar_tratamentos
from motor.geometria.layout import ConfigLayout, Croqui, gerar_croqui
from motor.identificadores.codigos import aplicar_codigos, validar_codigo_experimento
from motor.validacao.verificacoes import verificar_casualizacao, verificar_croqui


class ErroPlanejamento(ValueError):
    pass


@dataclass
class Metadados:
    codigo: str
    titulo: str
    projeto: str = ""
    instituicao: str = ""
    responsavel: str = ""
    colaboradores: str = ""
    objetivos: str = ""
    hipoteses: str = ""
    cultura: str = ""
    cultivar: str = ""
    local: str = ""
    municipio: str = ""
    uf: str = ""
    safra: str = ""
    ambiente: str = Ambiente.CAMPO.value
    data_prevista: str = ""  # ISO yyyy-mm-dd
    data_implantacao: str = ""
    observacoes: str = ""


@dataclass
class Planejamento:
    meta: Metadados
    delineamento: Delineamento
    estrutura: EstruturaTratamentos
    repeticoes: int
    layout: ConfigLayout
    padrao_codigo: str
    numeracao: str
    tratamentos: list[Tratamento]
    casualizacao: Casualizacao
    versao: int = 1
    arranjo: Arranjo = Arranjo.CONVENCIONAL
    _croqui: Croqui | None = field(default=None, repr=False)

    @property
    def croqui(self) -> Croqui:
        if self._croqui is None:
            self._croqui = gerar_croqui(self.casualizacao, self.layout)
        return self._croqui

    def trocar_layout(self, layout: ConfigLayout) -> None:
        """Alteração puramente física: preserva tratamentos, unidades e códigos."""
        self.layout = layout
        self._croqui = None

    def verificar(self) -> list[str]:
        return verificar_casualizacao(self.casualizacao) + verificar_croqui(self.casualizacao, self.croqui)


def planejar(
    meta: Metadados,
    delineamento: Delineamento | str,
    estrutura: EstruturaTratamentos,
    repeticoes: int,
    semente: int,
    layout: ConfigLayout,
    padrao_codigo: str,
    numeracao: str = "sequencial",
    versao: int = 1,
    arranjo: Arranjo | str = Arranjo.CONVENCIONAL,
) -> Planejamento:
    delineamento, arranjo = Delineamento(delineamento), Arranjo(arranjo)
    meta.codigo = validar_codigo_experimento(meta.codigo)
    if not meta.titulo.strip():
        raise ErroPlanejamento("Informe o título do experimento.")
    erros = [a.mensagem for a in avisos_planejamento(delineamento, estrutura, repeticoes, arranjo)
             if a.nivel == "erro"]
    if erros:
        raise ErroPlanejamento(" ".join(erros))
    tratamentos = gerar_tratamentos(estrutura)
    if delineamento is Delineamento.QL:
        repeticoes = len(tratamentos)
        numeracao = "sequencial"
    if delineamento is not Delineamento.DBC:
        numeracao = "sequencial"
    niveis = tuple(len(f.niveis) for f in estrutura.fatores) if arranjo is not Arranjo.CONVENCIONAL else None
    cas = casualizar(delineamento, len(tratamentos), repeticoes, semente, numeracao, arranjo, niveis)
    aplicar_codigos(cas, meta.codigo, padrao_codigo)
    plano = Planejamento(meta, delineamento, estrutura, repeticoes, layout, padrao_codigo,
                         numeracao, tratamentos, cas, versao, arranjo)
    problemas = plano.verificar()
    if problemas:  # salvaguarda: nunca deveria ocorrer
        raise ErroPlanejamento("Falha de integridade: " + "; ".join(problemas))
    return plano
