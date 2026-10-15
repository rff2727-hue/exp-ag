# Exp-Ag

Plataforma web para **planejar, casualizar, implantar e documentar experimentos agronômicos** — do cadastro do
projeto ao croqui de campo, ao experimento posicionado no terreno com todas as medidas, às etiquetas dos vasos e ao
diagnóstico da área por satélite — com rigor estatístico, reprodutibilidade e exportações prontas para relatório,
GPS, SIG e publicação.

Python + Streamlit, motor científico independente da interface, persistência em SQLite (local) ou PostgreSQL
(compartilhado) e testes automatizados que cobrem os cenários de aceitação.

> **Versão 0.3.0 — Fases 1, 2 e 3.** Módulos de fases seguintes aparecem na interface marcados como *fase futura*;
> nenhum botão simula uma função inexistente.

---

## O que a plataforma faz

| Área | Recursos |
|---|---|
| Projetos | projetos com vários experimentos; busca; arquivamento; duplicação; exclusão confirmada; importação/exportação em JSON; backup em ZIP |
| Delineamentos | **DIC**, **DBC** e **quadrado latino** (3 a 12 tratamentos) |
| Arranjos | convencional, **parcelas subdivididas** (DIC ou DBC) e **faixas** (DBC) |
| Tratamentos | unifatorial (lista ou doses), fatorial completo de 2 a 4 fatores, tratamentos adicionais (testemunhas, controles); fatores qualitativos e quantitativos |
| Conferência estatística | quadro de GL esperado **com os estratos de erro** (resíduos *a*, *b* e *c* nas subdivididas e faixas), avisos de GL e de número de unidades |
| Casualização | algoritmo próprio e versionado (`FY-SHA256-v1`), reprodutível pela semente; em cada estrutura o sorteio ocorre na unidade correta (parcela principal, subparcela, faixa, linha/coluna) |
| Identificadores | padrão personalizável: `{exp}` `{parcela}` `{bloco}` `{trat}` `{rep}` `{n}` `{pp}` `{sp}` `{lin}` `{col}`; unicidade garantida |
| Croqui | parcelas em escala ou vasos; parcelas principais contornadas; faixas e quadrado latino com rótulos de linha/coluna; bancadas; dimensões, linhas de plantio, bordaduras, carreadores, serpentina, rotação, Norte; áreas total, útil, de bordadura e de circulação; **cotas** (medidas) no desenho |
| Disposição | **blocos em fileiras** (ex.: 8 blocos em 2 × 4) com espaço próprio entre fileiras e numeração linear ou em serpentina; **corredores internos** a cada *n* parcelas ou linhas; **bordadura diferente em cada lado**; **canto de início** da numeração; **deslocamento livre de blocos** (por tabela ou arrastando com o mouse), com recusa de sobreposição |
| Mapa e locação | o experimento **sobre a imagem de satélite**: arrastar e girar, mover blocos, encaixe automático no perímetro com folga e áreas a evitar, coordenadas coladas do Google Maps, **pontos de controle de GPS** com erro por ponto; perímetros de KML/KMZ, GeoJSON, Shapefile (ZIP), GeoPackage, GPX e CSV, ou desenhados no mapa; UTM SIRGAS 2000 com convergência e fator de escala; conferência (dentro da área, folga, parcelas fora), medidas e diagonais |
| Locação no campo | **plano de locação em PDF** (situação, detalhe com cotas, piquetes em coordenadas locais, UTM e geográficas, diagonais, roteiro de trena); piquetes em CSV e GPX para GPS |
| Google Earth e SIG | KMZ com estilos por tratamento e rótulos (abre no Google Earth), atalho que abre o Earth no local; Shapefile, GeoPackage, GeoJSON e DXF (CAD) com todos os atributos das parcelas |
| Google Drive | pasta por experimento com relatórios, **Planilha Google**, **Documento Google** (memorial em português e inglês), diário de campo e planilha de coleta (nunca sobrescritos) e a subpasta *Mapas e GIS*; o diagnóstico por satélite também pode ir para o Drive |
| Casa de vegetação | bancadas (uma por bloco ou a cada *n* vasos); **rotação de vasos** com histórico: deslocamento, inversão, novo sorteio, troca, linhas/colunas do quadrado latino — sempre respeitando o delineamento; plano de rotações em Excel |
| Etiquetas | vasos, amostras (unidade × tipo de amostra) e placas de parcela, em folhas A4, com **QR Code** e código de barras; o QR pode abrir o app direto na unidade |
| Diagnóstico por satélite | a partir só do perímetro (KML/KMZ): histórico de uso (MapBiomas/PRODES), lavoura (Sentinel-2: NDVI, NDRE, NDMI, MSAVI2), relevo e água (Copernicus DEM), clima e vento (CHIRPS/NASA POWER), solo (SoilGrids), temperatura de superfície (Landsat) e água no solo (balanço hídrico e NISAR) — relatório em PDF, Excel e KML de pontos de visita |
| Exportações | relatório de planejamento (PDF), relatório de implantação (PDF), plano de locação (PDF) — todos com capa —, Excel (8 abas), croqui PNG 300/600 dpi, SVG e PDF vetoriais, CSV, JSON |
| Metodologia | descrição em português e inglês gerada apenas a partir das configurações |
| Modelos | 10 modelos prontos, incluindo subdivididas, faixas e quadrado latino em bancada |

---

## Executar localmente

Requisito: **Python 3.12** (ou 3.13).

```bash
git clone https://github.com/<seu-usuario>/exp-ag.git
cd exp-ag
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

O navegador abre em `http://localhost:8501`. Sem configuração adicional, os dados ficam em
`dados_locais/agro_experimentos.db` (SQLite). Em **Configurações → Carregar exemplos** você cria três
experimentos de demonstração.

### Testes

```bash
pip install -r requirements-dev.txt
pytest            # 220+ testes: motor, delineamentos, rotação, etiquetas (com leitura real dos QR), satélites,
                  # disposição, georreferenciamento (precisão milimétrica), encaixe, pontos de controle, formatos
                  # GIS (lidos de volta pelo GDAL), Google Drive (servidor falso), persistência, migrações e interface
ruff check .
```

Para testar também contra PostgreSQL, defina `TESTE_POSTGRES_URL=postgresql://usuario:senha@host:5432/banco_teste`
(o banco é **apagado** a cada teste — use um banco exclusivo).

---

## Publicar no GitHub

1. Crie um repositório vazio em <https://github.com/new> (ex.: `exp-ag`). Pode ser privado.
2. Na pasta do projeto:

   ```bash
   git init -b main          # se ainda não for um repositório
   git add .
   git commit -m "Exp-Ag 0.2.0"
   git remote add origin https://github.com/<seu-usuario>/exp-ag.git
   git push -u origin main
   ```

   Sem usar o terminal: no repositório novo, clique em **uploading an existing file**, arraste **o conteúdo** da
   pasta (não a pasta em si) e clique em **Commit changes**. Confira se aparecem `app.py` e as pastas `motor`,
   `ui`, `componentes`, `dados` e `assets`. O Windows esconde `.streamlit` e `.github`: sem elas o app funciona,
   mas perde o tema e a verificação automática — envie-as quando possível.
3. A aba **Actions** executa lint e testes (Python 3.12 e 3.13, SQLite e PostgreSQL) a cada envio.

O `.gitignore` já impede o envio de bancos locais e de `.streamlit/secrets.toml`.

---

## Implantar no Streamlit Community Cloud

1. Em <https://share.streamlit.io>, entre com o GitHub e clique em **Create app → Deploy a public app from GitHub**.
2. Repositório, ramo `main`, arquivo principal `app.py`.
3. Em **Advanced settings**, selecione **Python 3.12** e cole os Secrets (abaixo).
4. **Deploy.** A primeira instalação leva alguns minutos (bibliotecas geoespaciais do módulo de satélite).

### Secrets

```toml
# Diagnóstico por satélite (opcional) — chaves soltas vêm antes das seções
google_maps_key = "..."        # imagem de fundo do Raio-X; sem ela usa Esri World Imagery
earthdata_token = "..."        # NASA Earthdata, para ler a umidade do NISAR (ou earthdata_user/earthdata_password)

[database]
url = "postgresql://usuario:senha@host:5432/postgres?sslmode=require"

[acesso]
senha = "uma-senha-para-a-equipe"   # opcional: bloqueia o app com senha única

[app]
url_publica = "https://seu-app.streamlit.app"   # opcional: QR Codes das etiquetas abrem o app na unidade

[google_drive]                 # opcional: pastas por experimento no seu Google Drive (ver abaixo)
client_id = "…apps.googleusercontent.com"
client_secret = "…"
refresh_token = "…"
```

São as mesmas chaves `google_maps_key` e `earthdata_*` da recomenda-solo: dá para copiar de lá.

### Google Drive (opcional)

1. No [Google Cloud Console](https://console.cloud.google.com), crie um projeto e ative a **Google Drive API**.
2. Em *Google Auth Platform* (tela de consentimento OAuth): público **Externo**, adicione seu e-mail e clique em
   **Publicar aplicativo** (status *Em produção*). Em modo *Teste*, o Google invalida a autorização a cada 7 dias.
   O escopo usado (`drive.file`) não exige verificação do Google.
3. Em *Clientes*, crie um **ID do cliente OAuth** do tipo **App para computador** e baixe o JSON.
4. No seu computador, na pasta do projeto: `python ferramentas/autorizar_google_drive.py client_secret_XXXX.json`.
   O navegador abre; autorize com a sua conta. O script imprime o bloco `[google_drive]`: cole nos Secrets.
5. Em **Configurações → Google Drive**, use *Testar conexão*.

O Exp-Ag só enxerga o que ele mesmo criar no seu Drive (pasta `Exp-Ag`). Para compartilhar com a equipe, compartilhe
essa pasta pelo próprio Drive.

### Banco de dados persistente (obrigatório para uso real)

O disco do Streamlit Community Cloud é **temporário**: um SQLite ali é apagado a cada reinício. Use um PostgreSQL
externo com plano gratuito, como **Supabase** (<https://supabase.com>; se a conexão direta falhar, use a string do
*connection pooler*, modo sessão) ou **Neon** (<https://neon.tech>). Ambos oferecem PostGIS (Fase 3). As tabelas são
criadas e atualizadas automaticamente (migrações Alembic); um banco criado na versão 0.1.0 é migrado sem perda.

### Privacidade

Um app público com banco compartilhado mostra todos os experimentos a quem tiver o link. Use a senha de acesso
e/ou configure o app como privado no Streamlit Community Cloud, convidando os colegas por e-mail.

---

## Uso rápido

1. **Novo experimento** abre o assistente: *Projeto → Delineamento → Tratamentos → Casualização → Croqui →
   Revisão.* Em **Delineamento**, escolha DIC, DBC ou quadrado latino e o arranjo (convencional, subdivididas,
   faixas). Nas subdivididas e faixas, o **primeiro fator** vai para as parcelas principais (ou faixas
   horizontais) e o **segundo** para as subparcelas (ou faixas verticais).
2. No experimento salvo:
   - **Croqui** — visualização interativa e ajuste físico (não altera o sorteio);
   - **Posições e rotação** — posição vigente dos vasos, novos movimentos, plano de rotações e histórico;
   - **Etiquetas** — PDFs A4 de etiquetas e placas com QR Code;
   - **Exportações** — relatórios, Excel, figuras e texto metodológico.
   - **Mapa e locação** — o experimento no terreno (ver abaixo);
3. **Diagnóstico por satélite** (menu *Áreas*) — envie o KML da área (ou use uma área salva); o relatório sai em 2 a
   5 minutos.

### Do croqui ao terreno em poucos cliques

1. Na aba **Mapa e locação**, em *Adicionar área*, envie o perímetro do talhão (KML do Google Earth, Shapefile, GPX
   do GPS…) ou desenhe-o no mapa. Marque também as áreas a evitar, se houver.
2. Em *Encaixar no perímetro*, clique **Encaixar**: a plataforma acha a posição e a orientação de maior folga (ou
   use o azimute das linhas de plantio). Ajuste à mão arrastando o experimento, girando pela alça ocre ou movendo
   blocos; ou informe coordenadas, ou use pontos medidos com GPS.
3. **Salvar posição**. A conferência mostra se tudo cabe, a folga e as medidas; baixe o **plano de locação** e o
   **KMZ** para o Google Earth, os piquetes para o GPS e os arquivos para o SIG.

O azimute informado e exibido é o **verdadeiro** (o do Google Earth). Para bússola, desconte a declinação magnética
(no Centro-Oeste, cerca de −14° a −20°).

### Regras que a plataforma garante

- Cada estrutura é sorteada na sua unidade: no DBC, cada bloco tem todos os tratamentos uma vez; nas subdivididas,
  A é sorteado nas parcelas principais e B dentro de cada uma; nas faixas, A nas linhas e B nas colunas; no
  quadrado latino, cada tratamento aparece uma vez por linha e por coluna.
- A posição física nunca altera tratamento, bloco ou identificador; a rotação de vasos respeita o bloco, mantém a
  parcela principal inteira e preserva o quadrado latino.
- Alterar tratamentos, repetições, delineamento ou semente cria nova versão; a anterior fica guardada.
- Subamostras não são repetições: etiquetas de amostra e planilha de coleta as vinculam à unidade de origem.

---

## Reprodutibilidade

A casualização usa o algoritmo `FY-SHA256-v1`, independente de versões de NumPy ou Python: Fisher–Yates alimentado
por SHA-256 em modo contador (`SHA-256("semente|contexto|contador")`), com amostragem por rejeição e um fluxo
independente por bloco, parcela principal, linha ou coluna. A especificação está em
`motor/casualizacao/gerador.py` e é reimplementada de forma independente em `testes/test_casualizacao.py`.

---

## Estrutura

```text
app.py               entrada da aplicação
ui/                  páginas (inclui satelites.py)
componentes/         formulários, painéis, croqui interativo, mapa (Leaflet embutido), rotação, etiquetas, Drive
aplicacao/           rascunho do assistente, modelos, exemplos
motor/               regras científicas (Python puro, sem interface nem banco)
  sat/               diagnóstico por satélite (portado da recomenda-solo v17; moldura.py = identidade Exp-Ag)
  gis/               UTM, georreferência, encaixe, pontos de controle, piquetes, leitura e exportação GIS
  integracoes/       Google Drive e conteúdo da pasta do experimento
dados/               banco, ORM, repositório, migrações
ferramentas/         autorizar_google_drive.py (uso único, no seu computador)
templates/           biblioteca de modelos (JSON)
exemplos/            planejamentos de exemplo (JSON importável)
testes/              suíte de testes
docs/ARQUITETURA.md  análise crítica, arquitetura, modelo de dados e roteiro
```

O código de `motor/sat/` é mantido idêntico ao da recomenda-solo — só `moldura.py` difere, e `relatorio.py` delega a
capa a ela —, para que correções feitas numa plataforma possam ser copiadas para a outra.

---

## Roteiro

| Fase | Conteúdo |
|---|---|
| **1** ✔ | MVP: DIC, DBC, fatoriais, casualização reprodutível, croquis, exportações, persistência |
| **2** ✔ | subdivididas, faixas, quadrado latino; bancadas e rotação de vasos; etiquetas e QR Codes; diagnóstico por satélite |
| **3** ✔ | disposição personalizável e cotas; mapa com arraste e giro; perímetros e áreas a evitar; encaixe, coordenadas e pontos de controle; plano de locação; KMZ/SHP/GPKG/GeoJSON/GPX/DXF; Google Earth e Google Drive; editor por arraste; capas |
| 4 | avaliações, importação das planilhas de coleta preenchidas (inclusive do Drive), amostras, anexos, cálculo de insumos |
| 5 | ANOVA, modelos mistos (com os estratos já registrados), comparações múltiplas, regressão, análises conjuntas, colaboração |

Detalhes e justificativas em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

---

## Créditos

Fonte Roboto (Google), licença Apache 2.0 — `assets/fonts/LICENSE.txt`. Leaflet 1.9.4, licença BSD-2 —
`componentes/mapa/vendor/LICENSE-leaflet.txt`. Imagens de fundo do mapa: Esri World Imagery e OpenStreetMap (com
atribuição na tela). Artes das capas: autor (`assets/capas`).
