"""Repositório: única porta entre o domínio (``motor``) e o banco de dados.

A interface nunca acessa o ORM diretamente; usa estas operações, que
recebem e devolvem objetos do domínio.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from dados.modelos import orm
from motor.dominio import (
    Arranjo,
    Casualizacao,
    Delineamento,
    EstruturaTratamentos,
    Fator,
    Nivel,
    TratamentoAdicional,
    UnidadeExperimental,
)
from motor.estatistica.tratamentos import gerar_tratamentos
from motor.exportacao.projeto_json import de_json_dict, para_json_dict
from motor.geometria.layout import ConfigLayout
from motor.planejamento import Metadados, Planejamento


class ErroRepositorio(ValueError):
    pass


@dataclass
class ResumoExperimento:
    id: int
    projeto_id: int
    projeto: str
    codigo: str
    titulo: str
    delineamento: str
    n_tratamentos: int
    repeticoes: int
    ambiente: str
    safra: str
    local: str
    status: str
    versao: int
    arquivado: bool
    atualizado_em: datetime


@dataclass
class ResumoVersao:
    versao: int
    semente: int
    ativa: bool
    motivo: str
    criada_em: datetime
    criada_por: str
    n_unidades: int


CAMPOS_META = [f for f in Metadados.__dataclass_fields__ if f not in ("codigo", "titulo", "projeto")]


class RepositorioExperimentos:
    def __init__(self, sessoes: sessionmaker) -> None:
        self._sessoes = sessoes

    # ------------------------------------------------------------- projetos
    def criar_projeto(self, codigo: str, titulo: str, instituicao: str = "", programa: str = "",
                      responsavel: str = "", descricao: str = "") -> int:
        codigo = codigo.strip()
        if not codigo or not titulo.strip():
            raise ErroRepositorio("Informe código e título do projeto.")
        with self._sessoes() as s:
            if s.scalar(select(orm.Projeto.id).where(func.lower(orm.Projeto.codigo) == codigo.lower())):
                raise ErroRepositorio(f"Já existe um projeto com o código '{codigo}'.")
            p = orm.Projeto(codigo=codigo, titulo=titulo.strip(), instituicao=instituicao, programa=programa,
                            responsavel=responsavel, descricao=descricao)
            s.add(p)
            s.commit()
            return p.id

    def atualizar_projeto(self, projeto_id: int, **campos) -> None:
        with self._sessoes() as s:
            p = s.get(orm.Projeto, projeto_id)
            if p is None:
                raise ErroRepositorio("Projeto não encontrado.")
            for k, v in campos.items():
                if hasattr(p, k) and k not in ("id", "criado_em"):
                    setattr(p, k, v)
            s.commit()

    def listar_projetos(self, incluir_arquivados: bool = False) -> list[dict]:
        with self._sessoes() as s:
            q = (select(orm.Projeto, func.count(orm.Experimento.id))
                 .outerjoin(orm.Experimento).group_by(orm.Projeto.id).order_by(orm.Projeto.codigo))
            if not incluir_arquivados:
                q = q.where(orm.Projeto.arquivado.is_(False))
            return [
                {"id": p.id, "codigo": p.codigo, "titulo": p.titulo, "instituicao": p.instituicao,
                 "programa": p.programa, "responsavel": p.responsavel, "descricao": p.descricao,
                 "arquivado": p.arquivado, "n_experimentos": n}
                for p, n in s.execute(q).all()
            ]

    def excluir_projeto(self, projeto_id: int) -> None:
        with self._sessoes() as s:
            p = s.get(orm.Projeto, projeto_id)
            if p is None:
                raise ErroRepositorio("Projeto não encontrado.")
            s.delete(p)
            s.commit()

    # ---------------------------------------------------------- experimentos
    def codigo_disponivel(self, codigo: str, ignorar_id: int | None = None) -> bool:
        with self._sessoes() as s:
            q = select(orm.Experimento.id).where(func.lower(orm.Experimento.codigo) == codigo.strip().lower())
            if ignorar_id:
                q = q.where(orm.Experimento.id != ignorar_id)
            return s.scalar(q) is None

    def salvar_novo(self, projeto_id: int, plano: Planejamento, autor: str = "",
                    motivo: str = "Planejamento inicial") -> int:
        if not self.codigo_disponivel(plano.meta.codigo):
            raise ErroRepositorio(f"Já existe um experimento com o código '{plano.meta.codigo}'.")
        with self._sessoes() as s:
            proj = s.get(orm.Projeto, projeto_id)
            if proj is None:
                raise ErroRepositorio("Projeto não encontrado.")
            plano.meta.projeto = proj.codigo
            e = orm.Experimento(projeto_id=projeto_id, codigo=plano.meta.codigo, titulo=plano.meta.titulo,
                                criado_por=autor, versao_plano=plano.versao,
                                **{k: getattr(plano.meta, k) for k in CAMPOS_META},
                                **self._campos_plano(plano))
            self._escrever_estrutura(e, plano)
            e.casualizacoes.append(self._casualizacao_bd(plano, motivo, autor))
            e.historico.append(orm.Historico(acao="criação", detalhe=motivo, autor=autor))
            s.add(e)
            try:
                s.commit()
            except IntegrityError as exc:
                s.rollback()
                raise ErroRepositorio(f"Não foi possível salvar: {exc.orig}") from exc
            return e.id

    def atualizar_metadados(self, exp_id: int, meta: Metadados, autor: str = "") -> None:
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            if meta.codigo != e.codigo:
                raise ErroRepositorio("O código do experimento não pode ser alterado (os identificadores "
                                      "das unidades dependem dele). Duplique o experimento com outro código.")
            e.titulo = meta.titulo
            for k in CAMPOS_META:
                setattr(e, k, getattr(meta, k))
            e.historico.append(orm.Historico(acao="metadados", detalhe="Informações gerais atualizadas.",
                                             autor=autor))
            s.commit()

    def atualizar_layout(self, exp_id: int, layout: ConfigLayout, autor: str = "") -> None:
        """Mudança puramente física: não altera tratamentos, unidades nem códigos."""
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            antigo = e.layout
            novo = layout.para_dict()
            if antigo == novo:
                return
            e.layout = novo
            difs = [f"{k}: {antigo.get(k)} → {v}" for k, v in novo.items() if antigo.get(k) != v]
            e.historico.append(orm.Historico(acao="layout", detalhe="; ".join(difs), autor=autor))
            ativa = self._ativa(e)
            snap = dict(ativa.snapshot)
            snap["layout"] = novo
            ativa.snapshot = snap
            s.commit()

    def nova_versao(self, exp_id: int, plano: Planejamento, motivo: str, autor: str = "") -> int:
        """Alteração estrutural (tratamentos, repetições, delineamento ou semente).

        Desativa a casualização atual (mantida para consulta) e grava a nova.
        """
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            if plano.meta.codigo != e.codigo:
                raise ErroRepositorio("O código do experimento não pode ser alterado.")
            nova = max(c.versao for c in e.casualizacoes) + 1
            plano.versao = nova
            plano.meta.projeto = e.projeto.codigo
            for c in e.casualizacoes:
                c.ativa = False
            e.fatores.clear()
            e.adicionais.clear()
            e.tratamentos.clear()
            s.flush()
            for k, v in self._campos_plano(plano).items():
                setattr(e, k, v)
            e.versao_plano = nova
            self._escrever_estrutura(e, plano)
            e.casualizacoes.append(self._casualizacao_bd(plano, motivo, autor))
            e.historico.append(orm.Historico(acao="nova versão", detalhe=f"v{nova}: {motivo}", autor=autor))
            s.commit()
            return nova

    def restaurar_versao(self, exp_id: int, versao: int, autor: str = "") -> None:
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            alvo = next((c for c in e.casualizacoes if c.versao == versao), None)
            if alvo is None:
                raise ErroRepositorio(f"Versão {versao} não encontrada.")
            plano = de_json_dict(alvo.snapshot)
        self._reativar(exp_id, versao, plano, autor)

    def _reativar(self, exp_id: int, versao: int, plano: Planejamento, autor: str) -> None:
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            for c in e.casualizacoes:
                c.ativa = c.versao == versao
            e.fatores.clear()
            e.adicionais.clear()
            e.tratamentos.clear()
            s.flush()
            for k, v in self._campos_plano(plano).items():
                setattr(e, k, v)
            e.versao_plano = versao
            self._escrever_estrutura(e, plano)
            e.historico.append(orm.Historico(acao="restauração", detalhe=f"Versão {versao} reativada.",
                                             autor=autor))
            s.commit()

    def carregar(self, exp_id: int) -> Planejamento:
        with self._sessoes() as s:
            e = s.scalar(
                select(orm.Experimento).where(orm.Experimento.id == exp_id).options(
                    selectinload(orm.Experimento.fatores).selectinload(orm.Fator.niveis),
                    selectinload(orm.Experimento.adicionais),
                    selectinload(orm.Experimento.tratamentos),
                    selectinload(orm.Experimento.casualizacoes).selectinload(orm.CasualizacaoBD.unidades),
                    selectinload(orm.Experimento.projeto),
                ))
            if e is None:
                raise ErroRepositorio("Experimento não encontrado.")
            meta = Metadados(codigo=e.codigo, titulo=e.titulo, projeto=e.projeto.codigo,
                             **{k: getattr(e, k) for k in CAMPOS_META})
            estrutura = EstruturaTratamentos(
                fatores=[Fator(f.nome, [Nivel(n.rotulo, n.valor) for n in f.niveis], f.tipo, f.unidade)
                         for f in e.fatores],
                adicionais=[TratamentoAdicional(a.rotulo, a.descricao, a.papel) for a in e.adicionais],
            )
            tratamentos = gerar_tratamentos(estrutura)
            armazenados = [(t.numero, t.codigo, t.rotulo) for t in e.tratamentos]
            if armazenados != [(t.numero, t.codigo, t.rotulo) for t in tratamentos]:
                raise ErroRepositorio("Inconsistência entre fatores e tratamentos armazenados.")
            c = self._ativa(e)
            unidades = [UnidadeExperimental(u.numero, u.parcela, u.tratamento_numero, u.bloco, u.repeticao,
                                            u.posicao, u.codigo, u.principal, u.sub, u.linha, u.coluna)
                        for u in c.unidades]
            cas = Casualizacao(Delineamento(c.delineamento), c.semente, c.algoritmo, unidades,
                               c.n_tratamentos, c.n_repeticoes, Arranjo(c.arranjo), c.niveis_a, c.niveis_b)
            return Planejamento(meta, Delineamento(e.delineamento), estrutura, e.repeticoes,
                                ConfigLayout.de_dict(e.layout), e.padrao_codigo, e.numeracao,
                                tratamentos, cas, c.versao, Arranjo(e.arranjo))

    def projeto_de(self, exp_id: int) -> int:
        with self._sessoes() as s:
            return self._obter(s, exp_id).projeto_id

    def listar(self, projeto_id: int | None = None, incluir_arquivados: bool = False,
               busca: str = "") -> list[ResumoExperimento]:
        with self._sessoes() as s:
            q = (select(orm.Experimento, orm.Projeto.codigo, func.count(orm.Tratamento.id))
                 .join(orm.Projeto).outerjoin(orm.Tratamento)
                 .group_by(orm.Experimento.id, orm.Projeto.codigo)
                 .order_by(orm.Experimento.atualizado_em.desc()))
            if projeto_id:
                q = q.where(orm.Experimento.projeto_id == projeto_id)
            if not incluir_arquivados:
                q = q.where(orm.Experimento.arquivado.is_(False))
            if busca.strip():
                b = f"%{busca.strip().lower()}%"
                q = q.where(func.lower(orm.Experimento.codigo).like(b) | func.lower(orm.Experimento.titulo).like(b)
                            | func.lower(orm.Experimento.cultura).like(b) | func.lower(orm.Experimento.local).like(b))
            return [
                ResumoExperimento(e.id, e.projeto_id, pc, e.codigo, e.titulo, e.delineamento, nt, e.repeticoes,
                                  e.ambiente, e.safra, e.local, e.status, e.versao_plano, e.arquivado,
                                  e.atualizado_em)
                for e, pc, nt in s.execute(q).all()
            ]

    def versoes(self, exp_id: int) -> list[ResumoVersao]:
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            return [ResumoVersao(c.versao, c.semente, c.ativa, c.motivo, c.criada_em, c.criada_por, len(c.unidades))
                    for c in e.casualizacoes]

    def historico(self, exp_id: int) -> list[dict]:
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            return [{"momento": h.momento, "acao": h.acao, "detalhe": h.detalhe, "autor": h.autor}
                    for h in reversed(e.historico)]

    # -------------------------------------------------------- movimentos
    def movimentos(self, exp_id: int) -> list[dict]:
        """Movimentos da versão ativa, em ordem: [{ordem, data, tipo, descricao, mapa, autor}]."""
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            v = self._ativa(e).versao
            return [{"ordem": m.ordem, "data": m.data, "tipo": m.tipo, "descricao": m.descricao,
                     "mapa": {int(k): int(x) for k, x in m.mapa.items()}, "autor": m.autor}
                    for m in e.movimentos if m.versao == v]

    def registrar_movimento(self, exp_id: int, mapa: dict[int, int], tipo: str, descricao: str = "",
                            data: str = "", autor: str = "") -> int:
        """Grava a nova posição física de todas as unidades ({unidade: vaga}). Não altera a casualização."""
        plano = self.carregar(exp_id)
        numeros = sorted(u.numero for u in plano.casualizacao.unidades)
        if sorted(mapa) != numeros or sorted(mapa.values()) != numeros:
            raise ErroRepositorio("O movimento deve posicionar cada unidade em exatamente uma vaga.")
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            v = self._ativa(e).versao
            ordem = 1 + max((m.ordem for m in e.movimentos if m.versao == v), default=0)
            e.movimentos.append(orm.Movimento(versao=v, ordem=ordem, data=data, tipo=tipo, descricao=descricao,
                                              mapa={str(k): int(x) for k, x in mapa.items()}, autor=autor))
            e.historico.append(orm.Historico(acao="movimento", detalhe=f"#{ordem} {tipo}: {descricao}".strip(),
                                             autor=autor))
            s.commit()
            return ordem

    def desfazer_movimento(self, exp_id: int, autor: str = "") -> None:
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            v = self._ativa(e).versao
            dav = [m for m in e.movimentos if m.versao == v]
            if not dav:
                raise ErroRepositorio("Não há movimento para desfazer.")
            ultimo = max(dav, key=lambda m: m.ordem)
            e.movimentos.remove(ultimo)
            e.historico.append(orm.Historico(acao="movimento desfeito", detalhe=f"#{ultimo.ordem} {ultimo.tipo}",
                                             autor=autor))
            s.commit()

    def definir_status(self, exp_id: int, status: str, autor: str = "") -> None:
        if status not in ("planejado", "implantado", "em condução", "concluído"):
            raise ErroRepositorio("Status inválido.")
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            e.status = status
            e.historico.append(orm.Historico(acao="status", detalhe=status, autor=autor))
            s.commit()

    def arquivar(self, exp_id: int, arquivado: bool = True, autor: str = "") -> None:
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            e.arquivado = arquivado
            e.historico.append(orm.Historico(acao="arquivamento" if arquivado else "desarquivamento", autor=autor))
            s.commit()

    def excluir(self, exp_id: int) -> None:
        with self._sessoes() as s:
            s.delete(self._obter(s, exp_id))
            v = s.scalar(select(orm.VinculoDrive).where(orm.VinculoDrive.chave == f"exp:{exp_id}"))
            if v is not None:
                s.delete(v)
            s.commit()

    def duplicar(self, exp_id: int, novo_codigo: str, novo_titulo: str, nova_semente: int | None,
                 autor: str = "") -> int:
        """Duplica configurações. Com ``nova_semente`` gera nova casualização;
        sem ela, reproduz exatamente a mesma (útil para ensaios em vários locais
        com o mesmo croqui — avalie se isso é desejável no seu caso)."""
        from motor.planejamento import planejar

        base = self.carregar(exp_id)
        meta = Metadados(**{**asdict(base.meta), "codigo": novo_codigo, "titulo": novo_titulo,
                            "data_implantacao": ""})
        plano = planejar(meta, base.delineamento, base.estrutura, base.repeticoes,
                         nova_semente if nova_semente is not None else base.casualizacao.semente,
                         base.layout, base.padrao_codigo, base.numeracao, arranjo=base.arranjo)
        return self.salvar_novo(self.projeto_de(exp_id), plano, autor,
                                f"Duplicado de {base.meta.codigo} (v{base.versao})")

    # ---------------------------------------------------------------- áreas (Fase 3)
    def salvar_area(self, nome: str, geometria, tipo: str = "perimetro", projeto_id: int | None = None,
                    origem: str = "", descricao: str = "", autor: str = "") -> int:
        """Grava um perímetro ou área a evitar (geometria shapely em WGS 84)."""
        import json

        from shapely.geometry import mapping

        from motor.gis.leitura import AreaLida

        if tipo not in ("perimetro", "evitar"):
            raise ErroRepositorio("Tipo de área inválido.")
        if not nome.strip():
            raise ErroRepositorio("Dê um nome à área.")
        if geometria is None or geometria.is_empty or geometria.geom_type not in ("Polygon", "MultiPolygon"):
            raise ErroRepositorio("A área precisa ser um polígono.")
        ha = AreaLida(nome, geometria, origem).area_ha
        with self._sessoes() as s:
            a = orm.Area(nome=nome.strip()[:200], tipo=tipo, geojson=json.dumps(mapping(geometria)), area_ha=ha,
                         origem=origem[:300], descricao=descricao, projeto_id=projeto_id, criada_por=autor)
            s.add(a)
            s.commit()
            return a.id

    def listar_areas(self, projeto_id: int | None = None, tipo: str | None = None) -> list[dict]:
        """Áreas do projeto (e as sem projeto), mais recentes primeiro."""
        with self._sessoes() as s:
            q = select(orm.Area).order_by(orm.Area.criada_em.desc(), orm.Area.id.desc())
            if projeto_id is not None:
                q = q.where((orm.Area.projeto_id == projeto_id) | (orm.Area.projeto_id.is_(None)))
            if tipo:
                q = q.where(orm.Area.tipo == tipo)
            return [{"id": a.id, "nome": a.nome, "tipo": a.tipo, "area_ha": a.area_ha, "origem": a.origem,
                     "projeto_id": a.projeto_id, "criada_em": a.criada_em, "criada_por": a.criada_por}
                    for a in s.scalars(q)]

    def carregar_area(self, area_id: int) -> dict:
        import json

        from shapely.geometry import shape

        with self._sessoes() as s:
            a = s.get(orm.Area, area_id)
            if a is None:
                raise ErroRepositorio("Área não encontrada.")
            return {"id": a.id, "nome": a.nome, "tipo": a.tipo, "area_ha": a.area_ha, "origem": a.origem,
                    "projeto_id": a.projeto_id, "geometria": shape(json.loads(a.geojson))}

    def renomear_area(self, area_id: int, nome: str) -> None:
        with self._sessoes() as s:
            a = s.get(orm.Area, area_id)
            if a is None:
                raise ErroRepositorio("Área não encontrada.")
            a.nome = nome.strip()[:200] or a.nome
            s.commit()

    def excluir_area(self, area_id: int) -> None:
        with self._sessoes() as s:
            a = s.get(orm.Area, area_id)
            if a is not None:
                for g in s.scalars(select(orm.Georreferenciamento)):
                    if area_id in (g.evitar_ids or []):
                        g.evitar_ids = [i for i in g.evitar_ids if i != area_id]
                s.delete(a)
                s.commit()

    # ---------------------------------------------------------------- georreferenciamento (Fase 3)
    def salvar_georreferencia(self, exp_id: int, geo, area_id: int | None = None,
                              evitar_ids: list[int] | None = None, autor: str = "") -> None:
        """Grava a posição do experimento no terreno (``motor.gis.georref.Georreferencia``)."""
        from motor.gis.georref import MODOS

        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            g = s.scalar(select(orm.Georreferenciamento).where(orm.Georreferenciamento.experimento_id == exp_id))
            dados = geo.para_dict()
            if g is None:
                g = orm.Georreferenciamento(experimento_id=exp_id, dados=dados)
                s.add(g)
            elif g.dados == dados and g.area_id == area_id and (g.evitar_ids or []) == (evitar_ids or []):
                return
            g.dados = dados
            g.area_id = area_id
            g.evitar_ids = list(evitar_ids or [])
            g.atualizado_por = autor
            e.historico.append(orm.Historico(
                acao="georreferenciamento",
                detalhe=f"{MODOS.get(geo.modo, geo.modo)}: {geo.lat:.7f}, {geo.lon:.7f} ({geo.referencia}); "
                        f"azimute {geo.azimute:.2f}°" + (f"; erro médio {geo.residuo_rms:.2f} m"
                                                         if geo.residuo_rms is not None else ""),
                autor=autor))
            s.commit()

    def carregar_georreferencia(self, exp_id: int) -> dict | None:
        """{"geo": Georreferencia, "area_id", "evitar_ids", "atualizado_em", "atualizado_por"} ou None."""
        from motor.gis.georref import Georreferencia

        with self._sessoes() as s:
            g = s.scalar(select(orm.Georreferenciamento).where(orm.Georreferenciamento.experimento_id == exp_id))
            if g is None:
                return None
            return {"geo": Georreferencia.de_dict(g.dados), "area_id": g.area_id,
                    "evitar_ids": list(g.evitar_ids or []), "atualizado_em": g.atualizado_em,
                    "atualizado_por": g.atualizado_por}

    def remover_georreferencia(self, exp_id: int, autor: str = "") -> None:
        with self._sessoes() as s:
            e = self._obter(s, exp_id)
            g = s.scalar(select(orm.Georreferenciamento).where(orm.Georreferenciamento.experimento_id == exp_id))
            if g is not None:
                s.delete(g)
                e.historico.append(orm.Historico(acao="georreferenciamento", detalhe="Posição no terreno removida.",
                                                 autor=autor))
                s.commit()

    # ---------------------------------------------------------------- Google Drive (Fase 3)
    def vinculo_drive(self, chave: str) -> dict | None:
        with self._sessoes() as s:
            v = s.scalar(select(orm.VinculoDrive).where(orm.VinculoDrive.chave == chave))
            if v is None:
                return None
            return {"pasta_id": v.pasta_id, "pasta_url": v.pasta_url, "arquivos": dict(v.arquivos or {}),
                    "atualizado_em": v.atualizado_em}

    def salvar_vinculo_drive(self, chave: str, pasta_id: str, pasta_url: str, arquivos: dict) -> None:
        with self._sessoes() as s:
            v = s.scalar(select(orm.VinculoDrive).where(orm.VinculoDrive.chave == chave))
            if v is None:
                v = orm.VinculoDrive(chave=chave, pasta_id=pasta_id)
                s.add(v)
            v.pasta_id, v.pasta_url, v.arquivos = pasta_id, pasta_url, dict(arquivos)
            v.atualizado_em = datetime.now().astimezone()
            s.commit()

    def remover_vinculo_drive(self, chave: str) -> None:
        with self._sessoes() as s:
            v = s.scalar(select(orm.VinculoDrive).where(orm.VinculoDrive.chave == chave))
            if v is not None:
                s.delete(v)
                s.commit()

    # ---------------------------------------------------------------- apoio
    @staticmethod
    def _obter(s: Session, exp_id: int) -> orm.Experimento:
        e = s.get(orm.Experimento, exp_id)
        if e is None:
            raise ErroRepositorio("Experimento não encontrado.")
        return e

    @staticmethod
    def _ativa(e: orm.Experimento) -> orm.CasualizacaoBD:
        ativas = [c for c in e.casualizacoes if c.ativa]
        if len(ativas) != 1:
            raise ErroRepositorio("O experimento deveria ter exatamente uma casualização ativa.")
        return ativas[0]

    @staticmethod
    def _campos_plano(p: Planejamento) -> dict:
        return {"delineamento": p.delineamento.value, "arranjo": p.arranjo.value, "repeticoes": p.repeticoes,
                "padrao_codigo": p.padrao_codigo, "numeracao": p.numeracao, "layout": p.layout.para_dict()}

    @staticmethod
    def _escrever_estrutura(e: orm.Experimento, p: Planejamento) -> None:
        for i, f in enumerate(p.estrutura.fatores):
            e.fatores.append(orm.Fator(ordem=i, nome=f.nome, tipo=f.tipo.value, unidade=f.unidade,
                                       niveis=[orm.Nivel(ordem=j, rotulo=n.rotulo, valor=n.valor)
                                               for j, n in enumerate(f.niveis)]))
        for i, a in enumerate(p.estrutura.adicionais):
            e.adicionais.append(orm.TratamentoAdicional(ordem=i, rotulo=a.rotulo, descricao=a.descricao,
                                                        papel=a.papel.value))
        for t in p.tratamentos:
            e.tratamentos.append(orm.Tratamento(numero=t.numero, codigo=t.codigo, rotulo=t.rotulo,
                                                tipo=t.tipo.value, papel=t.papel.value, niveis=t.niveis))

    @staticmethod
    def _casualizacao_bd(p: Planejamento, motivo: str, autor: str) -> orm.CasualizacaoBD:
        c = p.casualizacao
        return orm.CasualizacaoBD(
            versao=p.versao, semente=c.semente, algoritmo=c.algoritmo, delineamento=c.delineamento.value,
            arranjo=c.arranjo.value, niveis_a=c.niveis_a, niveis_b=c.niveis_b,
            n_tratamentos=c.n_tratamentos, n_repeticoes=c.n_repeticoes, ativa=True, motivo=motivo,
            snapshot=para_json_dict(p), criada_por=autor,
            unidades=[orm.UnidadeBD(numero=u.numero, parcela=u.parcela, codigo=u.codigo,
                                    tratamento_numero=u.tratamento, bloco=u.bloco, repeticao=u.repeticao,
                                    posicao=u.posicao, principal=u.principal, sub=u.sub, linha=u.linha,
                                    coluna=u.coluna) for u in c.unidades],
        )
