"""Entidades de domínio do motor científico.

Este módulo não depende de Streamlit nem do banco de dados. Todas as regras
estatísticas, geométricas e de exportação operam sobre estas estruturas, o que
permite testá-las isoladamente e reutilizá-las em outras interfaces.

Terminologia adotada (seção 14 da especificação):

* **Tratamento**: condição aplicada (combinação de níveis de fatores ou
  tratamento adicional).
* **Unidade experimental (UE)**: menor porção de material que recebe um
  tratamento de forma independente (parcela, vaso). É a unidade casualizada.
* **Repetição**: cada UE independente que recebe o mesmo tratamento.
* **Unidade de observação / subamostra**: medida tomada dentro de uma UE —
  *não* é repetição (modelada na Fase 4).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Delineamento(str, Enum):
    """Delineamentos implementados. Novos membros entram com seus testes."""

    DIC = "DIC"
    DBC = "DBC"
    QL = "QL"

    @property
    def nome(self) -> str:
        return {
            Delineamento.DIC: "Delineamento inteiramente casualizado",
            Delineamento.DBC: "Delineamento em blocos casualizados",
            Delineamento.QL: "Delineamento em quadrado latino",
        }[self]

    @property
    def nome_en(self) -> str:
        return {
            Delineamento.DIC: "completely randomized design",
            Delineamento.DBC: "randomized complete block design",
            Delineamento.QL: "Latin square design",
        }[self]

    @property
    def sigla_en(self) -> str:
        return {Delineamento.DIC: "CRD", Delineamento.DBC: "RCBD", Delineamento.QL: "LSD"}[self]


class Arranjo(str, Enum):
    """Como os tratamentos (fatores) se distribuem nas unidades experimentais."""

    CONVENCIONAL = "convencional"  # todos os tratamentos casualizados na mesma unidade
    SUBDIVIDIDA = "subdividida"  # A nas parcelas principais, B nas subparcelas (split-plot)
    FAIXAS = "faixas"  # A em faixas horizontais, B em faixas verticais (strip-plot)

    @property
    def nome(self) -> str:
        return {Arranjo.CONVENCIONAL: "convencional", Arranjo.SUBDIVIDIDA: "parcelas subdivididas",
                Arranjo.FAIXAS: "parcelas em faixas"}[self]

    @property
    def nome_en(self) -> str:
        return {Arranjo.CONVENCIONAL: "", Arranjo.SUBDIVIDIDA: "split-plot", Arranjo.FAIXAS: "strip-plot"}[self]


COMBINACOES_VALIDAS = {
    (Delineamento.DIC, Arranjo.CONVENCIONAL), (Delineamento.DBC, Arranjo.CONVENCIONAL),
    (Delineamento.QL, Arranjo.CONVENCIONAL), (Delineamento.DIC, Arranjo.SUBDIVIDIDA),
    (Delineamento.DBC, Arranjo.SUBDIVIDIDA), (Delineamento.DBC, Arranjo.FAIXAS),
}


class TipoFator(str, Enum):
    QUALITATIVO = "qualitativo"
    QUANTITATIVO = "quantitativo"


class TipoTratamento(str, Enum):
    FATORIAL = "fatorial"  # combinação de níveis (inclui o caso unifatorial)
    ADICIONAL = "adicional"  # fora da estrutura fatorial


class PapelControle(str, Enum):
    NENHUM = ""
    TESTEMUNHA = "testemunha"
    CONTROLE_POSITIVO = "controle positivo"
    CONTROLE_NEGATIVO = "controle negativo"


class Ambiente(str, Enum):
    CAMPO = "campo"
    CASA_VEGETACAO = "casa de vegetação"
    LABORATORIO = "laboratório"
    OUTRO = "outro"


@dataclass
class Nivel:
    rotulo: str
    valor: float | None = None  # valor numérico para fatores quantitativos (doses)


@dataclass
class Fator:
    nome: str
    niveis: list[Nivel]
    tipo: TipoFator = TipoFator.QUALITATIVO
    unidade: str = ""  # unidade de medida dos níveis quantitativos (ex.: kg ha⁻¹)

    def __post_init__(self) -> None:
        self.tipo = TipoFator(self.tipo)
        self.niveis = [n if isinstance(n, Nivel) else Nivel(**n) for n in self.niveis]


@dataclass
class TratamentoAdicional:
    rotulo: str
    descricao: str = ""
    papel: PapelControle = PapelControle.NENHUM

    def __post_init__(self) -> None:
        self.papel = PapelControle(self.papel)


@dataclass
class Tratamento:
    numero: int  # 1..t, estável dentro de uma versão do planejamento
    codigo: str  # ex.: "T01"
    rotulo: str  # ex.: "SFT + Inoculado"
    tipo: TipoTratamento
    niveis: dict[str, str] = field(default_factory=dict)  # fator -> rótulo do nível
    papel: PapelControle = PapelControle.NENHUM
    descricao: str = ""

    def __post_init__(self) -> None:
        self.tipo = TipoTratamento(self.tipo)
        self.papel = PapelControle(self.papel)


@dataclass
class EstruturaTratamentos:
    """Fatores cruzados (fatorial completo) + tratamentos adicionais.

    Um único fator representa um ensaio unifatorial (ex.: 10 tratamentos
    listados ou 5 doses). Dois ou mais fatores produzem o fatorial completo.
    """

    fatores: list[Fator]
    adicionais: list[TratamentoAdicional] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.fatores = [f if isinstance(f, Fator) else Fator(**f) for f in self.fatores]
        self.adicionais = [
            a if isinstance(a, TratamentoAdicional) else TratamentoAdicional(**a)
            for a in self.adicionais
        ]

    @property
    def e_fatorial(self) -> bool:
        return len(self.fatores) >= 2

    @property
    def esquema(self) -> str:
        """Ex.: '3 × 2' ou '3 × 2 + 1'."""
        base = " × ".join(str(len(f.niveis)) for f in self.fatores)
        if self.adicionais:
            base += f" + {len(self.adicionais)}"
        return base


@dataclass
class UnidadeExperimental:
    numero: int  # ordem de casualização 1..N; congelado (não muda se a UE for movida)
    parcela: str  # rótulo da parcela (ex.: "7", "203" ou "103.2" numa subparcela)
    tratamento: int  # número do tratamento
    bloco: int | None  # None em DIC e quadrado latino
    repeticao: int
    posicao: int  # posição lógica dentro do bloco (ou do experimento), 1-based
    codigo: str = ""  # identificador único, gerado pelo módulo de identificadores
    principal: int | None = None  # parcela principal (subdivididas), 1-based no bloco (ou no experimento, DIC)
    sub: int | None = None  # posição da subparcela dentro da parcela principal
    linha: int | None = None  # linha no bloco/quadrado (faixas e quadrado latino)
    coluna: int | None = None  # coluna no bloco/quadrado (faixas e quadrado latino)


@dataclass
class Casualizacao:
    delineamento: Delineamento
    semente: int
    algoritmo: str
    unidades: list[UnidadeExperimental]
    n_tratamentos: int
    n_repeticoes: int
    arranjo: Arranjo = Arranjo.CONVENCIONAL
    niveis_a: int = 0  # subdivididas/faixas: níveis do fator A (parcelas principais ou faixas horizontais)
    niveis_b: int = 0  # subdivididas/faixas: níveis do fator B

    def __post_init__(self) -> None:
        self.delineamento = Delineamento(self.delineamento)
        self.arranjo = Arranjo(self.arranjo)

    @property
    def n_unidades(self) -> int:
        return len(self.unidades)


def para_dict(obj: Any) -> Any:
    """Serializa dataclasses/Enums em tipos JSON."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: para_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: para_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [para_dict(v) for v in obj]
    return obj
