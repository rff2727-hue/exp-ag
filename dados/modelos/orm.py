"""Modelo relacional (SQLAlchemy 2.x). Compatível com SQLite e PostgreSQL.

Princípios:

* As tabelas normalizadas (fator, nível, tratamento, unidade) representam a
  versão **ativa** do planejamento e servem a consultas e análises.
* Cada casualização guarda também um *snapshot* JSON completo do planejamento
  que a originou, de modo que versões anteriores permanecem recuperáveis
  mesmo depois que fatores e tratamentos forem alterados.
* A identidade da unidade experimental (``unidade_experimental``) é separada
  de sua posição física; o histórico de posições (rotação de vasos) e a
  geometria georreferenciada entram como tabelas próprias nas Fases 2 e 3.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def agora() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Projeto(Base):
    __tablename__ = "projeto"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    titulo: Mapped[str] = mapped_column(String(300))
    instituicao: Mapped[str] = mapped_column(String(200), default="")
    programa: Mapped[str] = mapped_column(String(200), default="")
    responsavel: Mapped[str] = mapped_column(String(200), default="")
    descricao: Mapped[str] = mapped_column(Text, default="")
    arquivado: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)

    experimentos: Mapped[list[Experimento]] = relationship(back_populates="projeto", cascade="all, delete-orphan")


class Experimento(Base):
    __tablename__ = "experimento"

    id: Mapped[int] = mapped_column(primary_key=True)
    projeto_id: Mapped[int] = mapped_column(ForeignKey("projeto.id", ondelete="CASCADE"), index=True)
    codigo: Mapped[str] = mapped_column(String(24), unique=True)
    titulo: Mapped[str] = mapped_column(String(300))
    instituicao: Mapped[str] = mapped_column(String(200), default="")
    responsavel: Mapped[str] = mapped_column(String(200), default="")
    colaboradores: Mapped[str] = mapped_column(Text, default="")
    objetivos: Mapped[str] = mapped_column(Text, default="")
    hipoteses: Mapped[str] = mapped_column(Text, default="")
    cultura: Mapped[str] = mapped_column(String(120), default="")
    cultivar: Mapped[str] = mapped_column(String(120), default="")
    local: Mapped[str] = mapped_column(String(200), default="")
    municipio: Mapped[str] = mapped_column(String(120), default="")
    uf: Mapped[str] = mapped_column(String(4), default="")
    safra: Mapped[str] = mapped_column(String(20), default="")
    ambiente: Mapped[str] = mapped_column(String(30), default="campo")
    data_prevista: Mapped[str] = mapped_column(String(10), default="")
    data_implantacao: Mapped[str] = mapped_column(String(10), default="")
    observacoes: Mapped[str] = mapped_column(Text, default="")
    # planejamento ativo
    delineamento: Mapped[str] = mapped_column(String(10))
    arranjo: Mapped[str] = mapped_column(String(20), default="convencional", server_default="convencional")
    repeticoes: Mapped[int] = mapped_column(Integer)
    padrao_codigo: Mapped[str] = mapped_column(String(120))
    numeracao: Mapped[str] = mapped_column(String(20), default="sequencial")
    layout: Mapped[dict] = mapped_column(JSON)
    versao_plano: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="planejado")
    arquivado: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_por: Mapped[str] = mapped_column(String(200), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)

    projeto: Mapped[Projeto] = relationship(back_populates="experimentos")
    fatores: Mapped[list[Fator]] = relationship(cascade="all, delete-orphan", order_by="Fator.ordem")
    adicionais: Mapped[list[TratamentoAdicional]] = relationship(
        cascade="all, delete-orphan", order_by="TratamentoAdicional.ordem")
    tratamentos: Mapped[list[Tratamento]] = relationship(cascade="all, delete-orphan", order_by="Tratamento.numero")
    casualizacoes: Mapped[list[CasualizacaoBD]] = relationship(
        cascade="all, delete-orphan", order_by="CasualizacaoBD.versao")
    historico: Mapped[list[Historico]] = relationship(cascade="all, delete-orphan", order_by="Historico.momento")
    movimentos: Mapped[list[Movimento]] = relationship(cascade="all, delete-orphan", order_by="Movimento.ordem")


class Fator(Base):
    __tablename__ = "fator"

    id: Mapped[int] = mapped_column(primary_key=True)
    experimento_id: Mapped[int] = mapped_column(ForeignKey("experimento.id", ondelete="CASCADE"), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    nome: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(20), default="qualitativo")
    unidade: Mapped[str] = mapped_column(String(40), default="")
    niveis: Mapped[list[Nivel]] = relationship(cascade="all, delete-orphan", order_by="Nivel.ordem")


class Nivel(Base):
    __tablename__ = "nivel"

    id: Mapped[int] = mapped_column(primary_key=True)
    fator_id: Mapped[int] = mapped_column(ForeignKey("fator.id", ondelete="CASCADE"), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    rotulo: Mapped[str] = mapped_column(String(120))
    valor: Mapped[float | None] = mapped_column(Float, nullable=True)


class TratamentoAdicional(Base):
    __tablename__ = "tratamento_adicional"

    id: Mapped[int] = mapped_column(primary_key=True)
    experimento_id: Mapped[int] = mapped_column(ForeignKey("experimento.id", ondelete="CASCADE"), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    rotulo: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str] = mapped_column(Text, default="")
    papel: Mapped[str] = mapped_column(String(30), default="")


class Tratamento(Base):
    """Tratamentos gerados para a versão ativa (desnormalizados para análise)."""

    __tablename__ = "tratamento"
    __table_args__ = (UniqueConstraint("experimento_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    experimento_id: Mapped[int] = mapped_column(ForeignKey("experimento.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    codigo: Mapped[str] = mapped_column(String(10))
    rotulo: Mapped[str] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(20))
    papel: Mapped[str] = mapped_column(String(30), default="")
    niveis: Mapped[dict] = mapped_column(JSON, default=dict)


class CasualizacaoBD(Base):
    __tablename__ = "casualizacao"
    __table_args__ = (UniqueConstraint("experimento_id", "versao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    experimento_id: Mapped[int] = mapped_column(ForeignKey("experimento.id", ondelete="CASCADE"), index=True)
    versao: Mapped[int] = mapped_column(Integer)
    semente: Mapped[int] = mapped_column(BigInteger)
    algoritmo: Mapped[str] = mapped_column(String(40))
    delineamento: Mapped[str] = mapped_column(String(10))
    arranjo: Mapped[str] = mapped_column(String(20), default="convencional", server_default="convencional")
    niveis_a: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    niveis_b: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    n_tratamentos: Mapped[int] = mapped_column(Integer)
    n_repeticoes: Mapped[int] = mapped_column(Integer)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo: Mapped[str] = mapped_column(Text, default="")
    snapshot: Mapped[dict] = mapped_column(JSON)  # planejamento completo (formato projeto_json)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criada_por: Mapped[str] = mapped_column(String(200), default="")

    unidades: Mapped[list[UnidadeBD]] = relationship(cascade="all, delete-orphan", order_by="UnidadeBD.numero")


class UnidadeBD(Base):
    __tablename__ = "unidade_experimental"
    __table_args__ = (
        UniqueConstraint("casualizacao_id", "numero"),
        UniqueConstraint("casualizacao_id", "codigo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    casualizacao_id: Mapped[int] = mapped_column(ForeignKey("casualizacao.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    parcela: Mapped[str] = mapped_column(String(12))
    codigo: Mapped[str] = mapped_column(String(160))
    tratamento_numero: Mapped[int] = mapped_column(Integer)
    bloco: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repeticao: Mapped[int] = mapped_column(Integer)
    posicao: Mapped[int] = mapped_column(Integer)
    principal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sub: Mapped[int | None] = mapped_column(Integer, nullable=True)
    linha: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coluna: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Historico(Base):
    __tablename__ = "historico"

    id: Mapped[int] = mapped_column(primary_key=True)
    experimento_id: Mapped[int] = mapped_column(ForeignKey("experimento.id", ondelete="CASCADE"), index=True)
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    acao: Mapped[str] = mapped_column(String(60))
    detalhe: Mapped[str] = mapped_column(Text, default="")
    autor: Mapped[str] = mapped_column(String(200), default="")


class Movimento(Base):
    """Mudança de posição física das unidades (rotação de vasos, remanejamento).

    `mapa` guarda {número da unidade: vaga} *depois* do movimento; as vagas são as posições físicas do croqui
    original (1..N). A identidade das unidades não muda. Cada movimento vale para uma versão da casualização.
    """

    __tablename__ = "movimento"
    __table_args__ = (UniqueConstraint("experimento_id", "versao", "ordem"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    experimento_id: Mapped[int] = mapped_column(ForeignKey("experimento.id", ondelete="CASCADE"), index=True)
    versao: Mapped[int] = mapped_column(Integer)  # versão da casualização
    ordem: Mapped[int] = mapped_column(Integer)
    data: Mapped[str] = mapped_column(String(10), default="")  # ISO yyyy-mm-dd
    tipo: Mapped[str] = mapped_column(String(40))
    descricao: Mapped[str] = mapped_column(Text, default="")
    mapa: Mapped[dict] = mapped_column(JSON)
    autor: Mapped[str] = mapped_column(String(200), default="")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Area(Base):
    """Perímetro (área de implantação) ou área a evitar, em WGS 84 (GeoJSON).

    A geometria é guardada como texto GeoJSON, e não em coluna PostGIS, para que o mesmo banco funcione em SQLite
    e em qualquer PostgreSQL; os cálculos geométricos são feitos em UTM pelo motor (shapely/pyproj).
    """

    __tablename__ = "area"

    id: Mapped[int] = mapped_column(primary_key=True)
    projeto_id: Mapped[int | None] = mapped_column(ForeignKey("projeto.id", ondelete="SET NULL"), nullable=True,
                                                   index=True)
    nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(20), default="perimetro")  # perimetro | evitar
    geojson: Mapped[str] = mapped_column(Text)
    area_ha: Mapped[float] = mapped_column(Float, default=0.0)
    origem: Mapped[str] = mapped_column(String(300), default="")
    descricao: Mapped[str] = mapped_column(Text, default="")
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criada_por: Mapped[str] = mapped_column(String(200), default="")


class Georreferenciamento(Base):
    """Posição do experimento no terreno (uma por experimento; mudanças ficam no histórico)."""

    __tablename__ = "georreferenciamento"

    id: Mapped[int] = mapped_column(primary_key=True)
    experimento_id: Mapped[int] = mapped_column(ForeignKey("experimento.id", ondelete="CASCADE"), unique=True)
    dados: Mapped[dict] = mapped_column(JSON)  # motor.gis.georref.Georreferencia.para_dict()
    area_id: Mapped[int | None] = mapped_column(ForeignKey("area.id", ondelete="SET NULL"), nullable=True)
    evitar_ids: Mapped[list] = mapped_column(JSON, default=list)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)
    atualizado_por: Mapped[str] = mapped_column(String(200), default="")


class VinculoDrive(Base):
    """Pasta do Google Drive ligada a um experimento ou a um diagnóstico, e os arquivos já enviados."""

    __tablename__ = "vinculo_drive"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(160), unique=True)  # "exp:12", "sat:…"
    pasta_id: Mapped[str] = mapped_column(String(200))
    pasta_url: Mapped[str] = mapped_column(String(400), default="")
    arquivos: Mapped[dict] = mapped_column(JSON, default=dict)  # {nome lógico: id do arquivo}
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)
