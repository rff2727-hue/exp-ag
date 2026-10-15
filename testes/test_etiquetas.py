"""Etiquetas e placas: contagem, folhas, conteúdo do QR e leitura real dos códigos (OpenCV, se instalado)."""

import io

import pytest
from pypdf import PdfReader

from aplicacao.exemplos import cenario_a, cenario_b
from motor.exportacao.etiquetas import MODELOS, etiquetas_unidades, gerar_pdf


def test_quantidades_e_folhas():
    p = cenario_b()
    et = etiquetas_unidades(p)
    assert len(et) == 30 and len({e.codigo for e in et}) == 30
    pdf = gerar_pdf(et, "a4_21", p.meta.codigo)
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 2                          # 30 etiquetas, 21 por folha
    assert len(PdfReader(io.BytesIO(gerar_pdf(et, "a4_21", "X", pular=12))).pages) == 2   # 42 posições
    assert len(PdfReader(io.BytesIO(gerar_pdf(et, "a4_21", "X", pular=13))).pages) == 3   # 43 posições
    am = etiquetas_unidades(p, amostras=[("S020", "Solo 0–20 cm"), ("F", "Folha")])
    assert len(am) == 60 and am[0].codigo.endswith("-S020") and am[1].codigo.endswith("-F")


def test_filtro_por_bloco_e_ordem_de_implantacao():
    p = cenario_a()
    et = etiquetas_unidades(p, blocos=[2])
    assert len(et) == 10 and all(e.bloco == "II" for e in et)
    assert [e.parcela for e in et] == [str(200 + i) for i in range(1, 11)]


def test_qr_com_link_ou_texto():
    p = cenario_b()
    assert etiquetas_unidades(p)[0].qr.startswith("EXP=EX-VASOS;UE=")
    link = etiquetas_unidades(p, "https://exp.exemplo.app/", 7)[0].qr
    assert link.startswith("https://exp.exemplo.app/experimento?exp=7&ue=EX-VASOS-")


@pytest.mark.parametrize("modelo", list(MODELOS))
def test_todos_os_modelos_geram_pdf(modelo):
    p = cenario_a()
    pdf = gerar_pdf(etiquetas_unidades(p)[:5], modelo, p.meta.codigo)
    assert pdf[:4] == b"%PDF"


@pytest.mark.parametrize("modelo,url", [("a4_40", ""), ("a4_21", "https://exp-ag.streamlit.app")])
def test_qr_legivel(modelo, url):
    """Renderiza a 1ª folha a 600 dpi e lê o QR de cada etiqueta, recortada como seria escaneada."""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    pdfium = pytest.importorskip("pypdfium2")
    p = cenario_a()
    m = MODELOS[modelo]
    et = etiquetas_unidades(p, url, 3)[: m.colunas * m.linhas]
    pdf = gerar_pdf(et, modelo, p.meta.codigo)
    img = np.array(pdfium.PdfDocument(pdf)[0].render(scale=600 / 72).to_pil().convert("L"))
    px = 600 / 25.4
    det = cv2.QRCodeDetector()
    lidos = []
    for k, e in enumerate(et):
        lin, col = divmod(k, m.colunas)
        x, y = int((m.margem_esq + col * m.passo_h) * px), int((m.margem_topo + lin * m.passo_v) * px)
        corte = cv2.copyMakeBorder(img[y:y + int(m.altura * px), x:x + int(m.largura * px)], 60, 60, 60, 60,
                                   cv2.BORDER_CONSTANT, value=255)
        texto, _, _ = det.detectAndDecode(corte)
        lidos.append(texto == e.qr)
    assert sum(lidos) >= len(et) - 1, f"{sum(lidos)} de {len(et)}"           # tolera 1 falha do detector
