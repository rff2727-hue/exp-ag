"""Botões e painéis do Google Drive."""

from __future__ import annotations

import streamlit as st

from motor.integracoes.google_drive import Arquivo, ClienteDrive, ErroDrive, sincronizar

ss = st.session_state


def _config() -> dict | None:
    try:
        c = st.secrets.get("google_drive")
    except Exception:  # noqa: BLE001 — sem secrets.toml
        return None
    if not c or not all(c.get(k) for k in ("client_id", "client_secret", "refresh_token")):
        return None
    return dict(c)


def configurado() -> bool:
    return _config() is not None


def cliente() -> ClienteDrive:
    c = _config()
    if c is None:
        raise ErroDrive("Google Drive não configurado.")
    return ClienteDrive(c["client_id"], c["client_secret"], c["refresh_token"], c.get("pasta_raiz"))


def _sem_configuracao(texto: str, chave: str) -> None:
    st.button(texto, disabled=True, width="stretch", icon=":material/add_to_drive:", key=f"drv_off_{chave}",
              help="Ligue o Google Drive em Configurações → Google Drive (passo a passo no README).")


def botao_drive_experimento(p, exp_id: int, repo, cj=None, chave: str = "") -> None:
    """Envia/atualiza a pasta do experimento no Drive e mostra o link."""
    from motor.integracoes.pacote import arquivos_experimento, caminho_experimento

    vinc = repo.vinculo_drive(f"exp:{exp_id}")
    if not configurado():
        _sem_configuracao("Enviar ao Google Drive", f"{chave}_{exp_id}")
        if vinc:
            st.link_button("Abrir pasta no Google Drive", vinc["pasta_url"], width="stretch")
        return
    rotulo = "Atualizar pasta no Google Drive" if vinc else "Criar pasta no Google Drive"
    if st.button(rotulo, key=f"drv_{chave}_{exp_id}", width="stretch", icon=":material/add_to_drive:",
                 help="Relatórios, Planilha e Documento Google, diário de campo e, se georreferenciado, os mapas "
                      "(KMZ abre direto no Google Earth). Arquivos gerados são atualizados no mesmo lugar; diário e "
                      "planilha de coleta nunca são sobrescritos."):
        barra = st.progress(0.0, "Preparando arquivos…")
        try:
            arqs = arquivos_experimento(p, cj)
            novo = sincronizar(cliente(), caminho_experimento(p), arqs, vinc,
                               progresso=lambda i, n, nome: barra.progress(i / n, f"Enviando {nome} ({i}/{n})"))
        except (ErroDrive, OSError) as e:
            barra.empty()
            st.error(str(e))
            return
        except Exception as e:  # noqa: BLE001 — rede instável etc.
            barra.empty()
            st.error(f"Não foi possível concluir o envio ao Google Drive: {e}")
            return
        repo.salvar_vinculo_drive(f"exp:{exp_id}", novo["pasta_id"], novo["pasta_url"], novo["arquivos"])
        barra.empty()
        st.toast("Pasta do experimento atualizada no Google Drive.")
        vinc = novo
    if vinc:
        st.link_button("Abrir pasta no Google Drive", vinc["pasta_url"], width="stretch", icon=":material/folder_open:")


def botao_drive_arquivos(chave: str, caminho: list[str], arquivos, repo, rotulo: str) -> None:
    """Envio genérico (ex.: diagnóstico por satélite). ``arquivos``: lista de Arquivo ou função que a devolve
    (gerada só no clique)."""
    vinc = repo.vinculo_drive(chave)
    if not configurado():
        _sem_configuracao(rotulo, chave)
        return
    if st.button(rotulo, key=f"drv_{chave}", width="stretch", icon=":material/add_to_drive:"):
        with st.spinner("Enviando ao Google Drive…"):
            try:
                lista: list[Arquivo] = arquivos() if callable(arquivos) else arquivos
                novo = sincronizar(cliente(), caminho, lista, vinc)
            except Exception as e:  # noqa: BLE001
                st.error(f"Não foi possível enviar ao Google Drive: {e}")
                return
        repo.salvar_vinculo_drive(chave, novo["pasta_id"], novo["pasta_url"], novo["arquivos"])
        vinc = novo
        st.toast("Arquivos enviados ao Google Drive.")
    if vinc:
        st.link_button("Abrir pasta no Google Drive", vinc["pasta_url"], width="stretch", icon=":material/folder_open:")


def painel_configuracao() -> None:
    if not configurado():
        st.markdown(
            "O Google Drive ainda não está ligado. Com ele, cada experimento ganha uma pasta com os relatórios, uma "
            "**Planilha Google**, um **Documento Google** (memorial), um **diário de campo** e, se georreferenciado, "
            "os mapas — o KMZ abre direto no **Google Earth**.\n\n"
            "1. No Google Cloud Console, ative a *Google Drive API*, configure a tela de consentimento (Externo, "
            "**Em produção**) e crie um cliente OAuth do tipo *App para computador*; baixe o JSON.\n"
            "2. No seu computador, na pasta do projeto: `python ferramentas/autorizar_google_drive.py "
            "client_secret.json` e autorize com sua conta Google.\n"
            "3. Cole o bloco `[google_drive]` impresso pelo script nos *Secrets* do Streamlit.\n\n"
            "O acesso é restrito (escopo `drive.file`): o Exp-Ag só enxerga o que ele mesmo criar.")
        return
    st.success("Google Drive configurado.", icon=":material/add_to_drive:")
    if st.button("Testar conexão", key="drv_teste"):
        try:
            pid = cliente().pasta("Exp-Ag")
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
        else:
            from motor.integracoes.google_drive import link_pasta

            st.success("Conexão funcionando.")
            st.link_button("Abrir a pasta Exp-Ag", link_pasta(pid))
