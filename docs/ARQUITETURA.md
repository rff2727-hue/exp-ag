# Exp-Ag — arquitetura e análise crítica

Este documento responde aos itens 1–6 da seção 17 da especificação: análise
crítica, dependências e limitações, arquitetura, modelo de dados, sequência
de implementação e estrutura do repositório.

---

## 1. Análise crítica da especificação

A especificação é sólida no essencial: separa casualização de desenho, exige
reprodutibilidade, distingue unidade experimental de subamostra e propõe um
desenvolvimento por fases com critérios de aceitação verificáveis. Os pontos
abaixo exigiram decisões de projeto ou são riscos a acompanhar.

### 1.1 Reprodutibilidade de longo prazo não é garantida por bibliotecas comuns

"Mesma semente → mesmo resultado" só vale enquanto o gerador não mudar. O
NumPy não garante que `Generator.permutation` produza a mesma sequência entre
versões, e o módulo `random` do Python pode mudar detalhes internos. Uma
casualização publicada com uma semente precisa ser reproduzível daqui a dez
anos.

**Decisão:** algoritmo próprio e versionado, `FY-SHA256-v1` (Fisher–Yates
alimentado por SHA-256 em modo contador, amostragem por rejeição sem viés de
módulo, fluxo independente por bloco). Está documentado em
`motor/casualizacao/gerador.py`, reimplementado de forma independente nos
testes e protegido por valores de referência congelados. Uma mudança futura de
algoritmo recebe outro nome (`-v2`); o nome do algoritmo é gravado com cada
casualização.

### 1.2 O disco do Streamlit Community Cloud é efêmero

SQLite no servidor da nuvem é apagado a cada reinício ou nova implantação. O
cenário D (persistência) só é atendido em produção com banco externo.

**Decisão:** camada de persistência independente (SQLAlchemy + Alembic),
SQLite para uso local e PostgreSQL para uso compartilhado, configurado por
`st.secrets`. Serviços gratuitos como Supabase ou Neon oferecem PostgreSQL com
PostGIS (necessário na Fase 3). O app mostra um aviso explícito quando roda na
nuvem sem banco externo, e todo experimento pode ser exportado/importado em
JSON (com verificação de integridade pela semente).

### 1.3 Edição por arraste não é nativa do Streamlit

Arrastar, rotacionar e selecionar parcelas livremente exige um componente
personalizado (React/JS) com comunicação bidirecional. Fazer isso na Fase 1
comprometeria a estabilidade.

**Decisão:** na Fase 1, o croqui é paramétrico (colunas, espaçamentos,
arranjo, serpentina, rotação) e interativo (zoom, arraste do mapa, consulta e
seleção de unidades por clique/laço). O editor por arraste chegou na Fase 3
(componente `st.components.v2` próprio), com a regra exigida: mudanças só físicas
preservam tratamentos e códigos; mudanças estruturais geram nova versão.

### 1.4 Conflito entre identidade e posição no exemplo de código

O exemplo `EXP-P01-B02-T05-R03` contém `P01`. Se `P` for a posição física,
o código mudaria quando um vaso fosse movido — o que contraria a exigência de
preservar a identidade da unidade.

**Decisão:** `{parcela}` é o número atribuído na casualização e fica
congelado. A posição física é um atributo separado, calculado pela geometria
(e, na Fase 2, registrado em histórico de posições).

### 1.5 Bibliotecas validadas de delineamento são escassas em Python

Para DIC, DBC e fatoriais a implementação é direta e verificável. Para
alfa-látice, blocos incompletos balanceados e látices, a referência de fato é o
ecossistema R (`agricolae`, `FielDHub`, `blocksdesign`); geradores de
alfa-látice dependem de arranjos tabelados (Patterson & Williams). O pacote
`pyDOE` atende experimentos industriais, não agronômicos.

**Decisão:** implementação própria, delineamento a delineamento, cada um com
testes de propriedade e comparação com exemplos de referência publicados antes
de ser liberado.

### 1.6 Outros pontos

- **Restrições de posição ("bloquear posições")** alteram a base
  probabilística da casualização. Serão implementadas como casualização
  restrita explícita, registrada no texto metodológico — não como edição manual
  do resultado.
- **Repetição × bloco**: no DBC a repetição coincide com o bloco; no DIC a
  repetição é a k-ésima ocorrência do tratamento. Isso é explícito no modelo.
- **Imagens de satélite** exigem licença compatível. Camadas como Esri World
  Imagery têm termos de uso próprios; o Google Maps não permite uso de tiles
  fora da API oficial. Avaliar na Fase 3.
- **QR Codes com link** dependem de URL estável e de autenticação; senão expõem
  dados. Previstos para a Fase 2 junto com controle de acesso.
- **Operação offline** não é viável com Streamlit (depende de conexão
  contínua com o servidor). Exigiria um aplicativo separado (PWA) com
  sincronização. Não é prometida.
- **Controle de acesso**: um app público com banco compartilhado expõe todos
  os experimentos. A Fase 1 oferece senha compartilhada opcional; usuários e
  permissões (via `st.login`/OIDC) ficam para as fases de colaboração.
- **Memória**: o Streamlit Community Cloud tem recursos de memória limitados
  (consulte os limites vigentes na documentação). Por isso GeoPandas/Rasterio não entram antes da Fase 3, e a Fase 1 não carrega
  SciPy/statsmodels (não são necessários para planejar).

---

## 2. Dependências técnicas

| Pacote | Uso | Fase |
|---|---|---|
| streamlit | interface | 1 |
| pandas, numpy | tabelas | 1 |
| plotly | croqui interativo | 1 |
| matplotlib | croqui estático (PNG, SVG, PDF) | 1 |
| reportlab, pypdf | relatórios PDF com croqui vetorial | 1 |
| xlsxwriter, openpyxl | exportação e leitura de Excel | 1 |
| sqlalchemy, alembic | persistência e migrações | 1 |
| psycopg | driver PostgreSQL | 1 |
| reportlab (QR, Code 128) | etiquetas — sem dependência extra | 2 |
| scipy, shapely, pyproj, rasterio, requests, pillow, h5py | diagnóstico por satélite | 2 |
| geopandas, folium | WebGIS | 3 |
| statsmodels | análises | 5 |

Python alvo: **3.12** (o NumPy atual exige 3.12 ou superior). Testado em 3.12 e
3.13 na integração contínua.

---

## 3. Arquitetura

```text
┌───────────────────────────── Interface (Streamlit) ─────────────────────────────┐
│ app.py · ui/ (páginas) · componentes/ (formulários, painéis, croqui interativo) │
└───────────────┬─────────────────────────────────────────────────┬───────────────┘
                │ rascunho (dict JSON)                            │ objetos do domínio
┌───────────────▼──────────────┐                    ┌─────────────▼───────────────┐
│ aplicacao/                   │                    │ dados/                      │
│ rascunho ↔ planejamento,     │                    │ repositório (única porta),  │
│ modelos, exemplos            │                    │ ORM, migrações Alembic      │
└───────────────┬──────────────┘                    └─────────────┬───────────────┘
                │                                                 │
┌───────────────▼─────────────────────────────────────────────────▼───────────────┐
│ motor/  (Python puro, sem Streamlit e sem banco — 100 % testável)                │
│ dominio · estatistica (tratamentos, GL, avisos) · casualizacao (gerador, DIC/DBC)│
│ identificadores · geometria (layout, áreas, rotação) · validacao                 │
│ exportacao (Excel, PDF, PNG/SVG, JSON, texto metodológico) · planejamento        │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Fluxo de um planejamento: `EstruturaTratamentos → gerar_tratamentos →
casualizar → aplicar_codigos → gerar_croqui → verificar`. A função
`motor.planejamento.planejar` executa a sequência inteira e recusa o resultado
se qualquer verificação de integridade falhar.

Regras de separação:

- `motor/` não importa Streamlit nem SQLAlchemy.
- A interface não acessa o ORM; usa o repositório, que recebe e devolve objetos
  do domínio.
- A geometria nunca altera a casualização; recebe unidades e devolve posições.
- Tela e papel usam as mesmas regras de cor e rótulo (`exportacao/estilo.py`).

---

## 4. Modelo de dados

```text
projeto 1──N experimento 1──N fator 1──N nivel
                        ├──N tratamento_adicional
                        ├──N tratamento            (versão ativa, para análise)
                        ├──N casualizacao 1──N unidade_experimental
                        │      (versão, semente, algoritmo, arranjo, níveis A/B, ativa, snapshot JSON)
                        ├──N movimento             (posições físicas: {unidade: vaga}, por versão)
                        └──N historico
```

- **unidade_experimental** ganhou na Fase 2 `principal`, `sub`, `linha` e `coluna` (subdivididas, faixas e
  quadrado latino). **movimento** registra cada rotação/remanejamento como o mapa completo `{unidade: vaga}`;
  a posição de qualquer vaso em qualquer data é reconstituível. Migração `0002` (testada contra um banco real
  criado pela versão 0.1.0).

- **experimento** guarda metadados (cultura, local, safra, datas, objetivos…),
  o planejamento ativo (delineamento, repetições, padrão de código, numeração) e
  a configuração física (`layout`, JSON).
- **casualizacao** é versionada. Cada versão guarda um *snapshot* completo do
  planejamento; versões antigas continuam recuperáveis mesmo depois de alterar
  fatores e tratamentos. Exatamente uma versão está ativa.
- **unidade_experimental** guarda a identidade (número, parcela, código,
  tratamento, bloco, repetição, posição lógica), com unicidade de código por
  versão. A posição física é derivada da geometria.

Tabelas previstas:

| Tabela | Fase | Finalidade |
|---|---|---|
| `ambiente_fisico`, `setor` | 3 | casas de vegetação cadastradas, setores e restrições de ocupação |
| `geometria_unidade` (PostGIS) | 3 | polígono, centroide, SRC, precisão e origem |
| `variavel`, `avaliacao`, `observacao` | 4 | dados coletados em formato longo, com subamostra |
| `amostra`, `anexo`, `operacao` | 4 | rastreio de amostras, fotos, histórico de campo |
| `usuario`, `permissao` | 5 | colaboração |

O formato longo da planilha de coleta (unidade, data, variável, subamostra,
valor, unidade de medida) já é exportado na Fase 1, para que os dados coletados
desde já sejam importáveis na Fase 4.

---

## 5. Sequência de implementação

| Fase | Entregas | Estado |
|---|---|---|
| 1 | estrutura, persistência, DIC, DBC, fatoriais + adicionais, casualização reprodutível, croqui de parcelas e vasos, Excel/PDF/PNG/SVG/JSON, testes, CI | **concluída** |
| 2 | parcelas subdivididas (sorteio em dois estratos), faixas, quadrado latino, bancadas, rotação de vasos com histórico, etiquetas e QR Codes, diagnóstico por satélite, identidade Exp-Ag | **concluída** |
| 3 | disposição personalizável (blocos em fileiras, corredores, bordaduras por lado, canto inicial, deslocamento de blocos, cotas); mapa sobre imagem de satélite com arraste e giro; importação de perímetros (KML/KMZ/GeoJSON/GPKG/SHP/GPX/CSV) e desenho no mapa; encaixe automático, coordenadas e pontos de controle; UTM/SIRGAS 2000 com convergência e fator de escala; piquetes, diagonais e plano de locação; KMZ/SHP/GPKG/GeoJSON/GPX/DXF/CSV; Google Earth e Google Drive; editor por arraste; capas | **concluída** |
| 4 | avaliações e coletas, importação de planilhas preenchidas (inclusive a Planilha de coleta do Drive), histórico de operações, amostras, anexos, cálculo de insumos (kg ha⁻¹, g/vaso, mg kg⁻¹) | próxima |
| 5 | ANOVA e modelos mistos com os estratos de erro corretos, comparações múltiplas, regressão, análises conjuntas, colaboração | |

Critério para avançar de fase: todos os testes da fase anterior passando na CI.

---

## 6. Estrutura do repositório

```text
agro-experimentos/
├── app.py                      # entrada: navegação, estilo, controle de acesso
├── requirements.txt            # dependências fixadas (produção)
├── requirements-dev.txt        # + pytest, ruff
├── pyproject.toml              # configuração de pytest e ruff
├── alembic.ini
├── .streamlit/
│   ├── config.toml             # tema
│   └── secrets.toml.example    # modelo de credenciais (o real nunca é versionado)
├── .github/workflows/ci.yml    # testes e lint em 3.12 e 3.13
├── assets/                     # logotipo, ícone, fontes Roboto (licença Apache 2.0)
├── ui/                         # páginas
├── componentes/                # formulários, painéis, croqui interativo, visual
│   ├── mapa/                   # componente de mapa (Leaflet 1.9.4 embutido, licença BSD-2)
│   ├── mapa_ui.py              # aba "Mapa e locação"
│   ├── editor_arraste.py       # editor de disposição por arraste
│   └── drive_ui.py             # Google Drive
├── aplicacao/                  # rascunho do assistente, modelos, exemplos
├── motor/
│   ├── dominio.py · planejamento.py
│   ├── estatistica/            # tratamentos, quadro de GL, avisos
│   ├── casualizacao/           # gerador determinístico e delineamentos
│   ├── geometria/              # layout, áreas, rotação
│   ├── identificadores/        # padrões de código
│   ├── validacao/              # verificações de integridade
│   ├── exportacao/             # Excel, PDF, croqui, JSON, texto metodológico, capas, plano de locação
│   ├── gis/                    # UTM, georreferência, encaixe, pontos de controle, locação, leitura e exportação
│   ├── integracoes/            # Google Drive (REST) e conteúdo da pasta do experimento
│   └── sat/                    # diagnóstico por satélite
├── ferramentas/                # autorizar_google_drive.py (uso único, no computador do responsável)
├── dados/
│   ├── banco.py                # URL, engine, migrações
│   ├── modelos/orm.py
│   ├── repositorios/experimentos.py
│   └── migracoes/              # Alembic
├── templates/                  # biblioteca de modelos (JSON)
├── exemplos/                   # planejamentos de exemplo em JSON
├── testes/
└── docs/
```

O geoprocessamento sugerido na especificação está em `motor/gis/`; os relatórios, em `motor/exportacao/`.


---

## 7. Fase 2 — decisões

- **Subdivididas e faixas** exigem exatamente dois fatores e nenhum tratamento adicional; o primeiro fator é A
  (parcelas principais ou faixas horizontais). O número do tratamento (i, j) é `(i − 1)·b + j`, a mesma ordem da
  matriz fatorial, de modo que tabelas, croquis e exportações não mudam de convenção.
- **Quadrado latino**: permutação de linhas, colunas e símbolos de um quadrado cíclico (procedimento clássico de
  Fisher & Yates, o mesmo do `agricolae::design.lsd`). Não sorteia uniformemente entre *todos* os quadrados latinos
  de ordem t (isso exigiria enumerar quadrados-padrão, viável só até t = 6), mas produz um plano válido e
  aleatorizado, como a prática usual.
- **Rotação de vasos**: a identidade da unidade fica separada da vaga física. Movimentos permitidos: DIC, qualquer
  vaga; DBC, dentro do bloco; subdivididas, parcela principal inteira; quadrado latino, só linhas ou colunas
  inteiras (preserva a propriedade latina); faixas, nenhum. `verificar_mapa` recusa qualquer mapa que viole isso.
- **Etiquetas**: QR com zona de silêncio de 4 módulos e correção de erro nível M; os testes renderizam as folhas
  a 600 dpi e leem cada QR com OpenCV.
- **Diagnóstico por satélite**: portado da recomenda-solo v17 sem alterar análises nem páginas. A única camada
  nova é `motor/sat/moldura.py` (identidade Exp-Ag: logotipo, petróleo/ocre, Roboto). Os demais arquivos são
  idênticos ao original, para que correções possam ser copiadas entre as plataformas. As bases públicas não
  são acessíveis no ambiente de desenvolvimento; os testes usam dados sintéticos (os mesmos da recomenda-solo e
  um diagnóstico completo de 16 páginas), e a primeira execução no servidor é o teste com dados reais.
- **Editor por arraste** foi adiado para a Fase 3: exige componente próprio com comunicação bidirecional, e o
  remanejamento controlado (troca, deslocamento, sorteio) cobre a necessidade com as restrições garantidas.


---

## 8. Fase 3 — decisões

- **Plano local e terreno.** O croqui continua sendo desenhado num plano em metros (origem no canto inferior
  esquerdo, Y para cima). A posição no terreno é guardada à parte (`Georreferencia`: latitude e longitude de um ponto
  de referência, azimute verdadeiro do eixo Y e zona UTM). Mudar a disposição física não perde a posição, e mudar a
  posição não toca no croqui. A rotação de desenho do croqui não entra no mapa; quem orienta o experimento é o azimute.
- **UTM com rigor de locação.** Toda a geometria é calculada em SIRGAS 2000 / UTM (WGS 84 / UTM fora das zonas
  SIRGAS cadastradas), aplicando a **convergência meridiana** (azimute verdadeiro → azimute de quadrícula, até ±3° nas
  bordas da zona) e o **fator de escala** da projeção (0,9996 a ~1,001), calculados numericamente no ponto. Nos testes,
  distâncias de 150 m saem com erro < 2 mm e azimutes com erro < 0,0001°, no meio e nas bordas da zona. O fator de
  elevação é desprezado (1,6 cm em 100 m a 1.000 m de altitude) e isso está documentado no plano de locação.
- **Encaixe automático.** Busca em grade de ângulos (3°, mais as direções do retângulo mínimo da área) e de posições,
  com teste vetorizado dos vértices antes da inclusão exata, refinamento local e polimento contínuo (Nelder–Mead),
  maximizando a folga mínima até a divisa e as áreas a evitar. Quando não cabe, devolve a posição de maior fração
  dentro e quanto falta. Com azimute fixo (linhas de plantio, terraços), otimiza só a posição.
- **Pontos de controle.** Ajuste rígido por mínimos quadrados (Procrustes 2D) com a escala fixada no fator da
  projeção; resíduos por ponto, erro médio quadrático e a escala que se obteria livre (diagnóstico de croqui que não
  bate com o implantado).
- **Blocos arrastados.** Os deslocamentos manuais ficam na própria disposição (`deslocamentos_blocos`), valem para o
  croqui, o mapa, os relatórios e as exportações, e são recusados se dois blocos se sobrepuserem. No mapa, depois de
  arrastar um bloco, a referência é "reancorada" para que os demais blocos fiquem exatamente onde estavam.
- **Componente de mapa.** `st.components.v2` (bidirecional, sem etapa de compilação) com Leaflet 1.9.4 **embutido**
  no código do componente: funciona mesmo onde CDNs são bloqueadas. Renderização em canvas (centenas de parcelas sem
  travar); rótulos dimensionados pelo zoom e girados com o experimento. O mesmo componente, em plano cartesiano, é o
  editor de disposição por arraste (o item adiado da Fase 2). Durante o arraste, o navegador usa uma aproximação de
  plano tangente (erro de centímetros em 1 km); ao soltar, o Python recalcula tudo exatamente em UTM.
- **Sem PostGIS, por ora.** Áreas são guardadas em GeoJSON (WGS 84) em coluna de texto e a posição em JSON: o mesmo
  banco funciona em SQLite e em qualquer PostgreSQL (Supabase e Neon sem extensão). Os cálculos são feitos pelo motor
  (shapely/pyproj). PostGIS passa a valer a pena quando houver consultas espaciais no banco (ex.: "experimentos a
  menos de 5 km"), o que hoje não existe.
- **Formatos.** Leitura e escrita de Shapefile e GeoPackage via pyogrio (GDAL embutido na roda); KML/KMZ, GeoJSON,
  GPX e CSV escritos pelo próprio motor (KML com estilos por tratamento, rótulos, piquetes e enquadramento inicial);
  DXF com ezdxf, em camadas de CAD e com cotas. Shapefile com nomes de campo de até 10 caracteres e `.cpg` UTF-8.
- **Google Earth.** Não há API pública para carregar um KML no Google Earth na Web por endereço. O app abre o Earth
  já voando para o experimento e entrega o KMZ (importar em *Projetos*); com o Google Drive ligado, o KMZ fica na
  pasta do experimento e abre direto no Earth pelo Drive.
- **Google Drive.** OAuth com *refresh token* da conta do responsável (contas de serviço não têm cota em Drive
  pessoal) e escopo `drive.file` (o app só vê o que criou; não exige verificação do Google). Arquivos gerados são
  atualizados no mesmo arquivo (link estável, histórico de versões do Drive); diário de campo e planilha de coleta
  são criados uma vez e nunca sobrescritos. Cliente REST próprio com `requests` (sem o SDK do Google), testado com um
  servidor falso; **não foi testado contra o Google real** no ambiente de desenvolvimento (sem acesso à rede).
- **Capas.** As artes do autor entram como página 1 dos relatórios de planejamento, de implantação, do plano de
  locação e do diagnóstico por satélite, com a identificação na faixa clara entre o título e a ilustração. No
  diagnóstico, `relatorio.pagina_capa` passou a delegar à camada de identidade (`moldura.pagina_capa`) — é a única
  linha alterada em relação à recomenda-solo.
