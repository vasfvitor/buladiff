# Buladiff

Arquivo e diff de versões de bulas do Bulário Eletrônico da ANVISA.

A ANVISA publica só o PDF de cada versão. Este projeto baixa todas as
versões de um produto e mostra o que mudou entre duas delas, seção por
seção (as seções são as da RDC 47/2009: 4. Contraindicações,
5. Advertências e precauções e assim por diante).

## Uso

```sh
uv sync                                        # ou: pip install -e .
uv run bulario search dipirona                 # registros, empresa, data da última bula
uv run bulario search --desde 2026-09-01       # tudo que foi publicado desde a data
uv run bulario fetch 118190404                 # baixa as duas versões mais recentes
uv run bulario fetch 118190404 --all           # todas as versões
uv run bulario feed --desde 2026-09-01           # tudo que foi publicado no período
uv run bulario feed --baixar                     # continua de onde parou e arquiva as versões novas
uv run bulario diff --registro 118190404 --tipo vps --html diff.html
uv run bulario diff antiga.pdf nova.pdf        # ou dois PDFs quaisquer
uv run bulario sections a.pdf                  # mostra a segmentação (depuração)
uv run bulario history a.pdf                   # lê a tabela "Histórico de Alteração da Bula"
```

Só depende do Python 3.11+ e do `pdftotext` (pacote `poppler-utils`). O comando `history`
usa o extra `tables` (pdfplumber): `uv sync --extra tables`.
Desenvolvimento: `uv run pytest`, `uv run ruff check`, `uv run scripts/validate.py <registros…>`.

## Estrutura

- `bulario/api.py`: cliente HTTP (busca, histórico paginado, download de PDF, detalhe do produto).
- `bulario/archive.py`: arquivo local em JSON — `VersionText` com seções, tabela de histórico e hash do
  PDF; o PDF é baixado, extraído e descartado.
- `bulario/extract.py`: texto → páginas → sem cabeçalho/rodapé → documentos → seções. Funções puras
  sobre listas de linhas, testáveis sem PDF.
- `bulario/diff.py`: pareamento de documentos por semelhança, diff por palavra, resumo e HTML.
- `bulario/feed.py`: publicações por período (`filter[periodoPublicacao…]`) e arquivo incremental,
  com estado em `data/feed.json`.
- `bulario/history.py`: tabela de histórico do PDF como dados (pdfplumber); casa entradas com o
  expediente da API comparando só os dígitos.
- `bulario/export.py`: gera os JSON do site (`produtos.json` e `produtos/<registro>.json` com versões e diffs).
- `registros.txt`: lista curada de registros com histórico completo.
- `site/`: o site em Astro (pnpm); lê `site/src/data/`, gerado e fora do git.
- `bulario/cli.py`: subcomandos.

## Site

`site/` é um site estático em Astro que lê os JSON gerados por `bulario export` e publica, para cada
produto, a linha do tempo de versões e o diff por seção entre versões consecutivas, com busca (Pagefind).

```sh
uv run bulario export --out site/src/data   # gera os dados do site a partir de data/
pnpm install
pnpm site:dev                               # http://localhost:4321/buladiff/
pnpm site:build                             # site/dist/
```

O site é publicado no GitHub Pages pelo workflow `.github/workflows/daily.yml` a cada push em `main`.
O Cloudflare da ANVISA bloqueia os runners do GitHub, então a coleta roda na sua máquina:
`scripts/coleta-local.sh` (para o cron) faz `feed --baixar` e `fetch --curados`, commita `data/` e dá
push, o que dispara o deploy. O cron diário do workflow ainda tenta coletar no runner e, se a API não
responder, só republica o que já está commitado. O repositório não guarda PDF: só o texto
extraído por versão (`data/<registro>/<data>_<expediente>_<vp|vps>.json`) e o hash do PDF original.

## Como funciona

1. `GET /api/consulta/bulario?filter[numeroRegistro]=…` acha o `idProduto`.
2. `GET /api/consulta/bulario/{idProduto}` devolve o histórico: cada
   expediente com `idBulaPaciente` e `idBulaProfissional`, 10 por página.
3. `GET /api/consulta/medicamentos/arquivo/bula/parecer/{id}/?Authorization=`
   devolve o PDF.
4. `pdftotext -layout`, remoção de cabeçalho e rodapé repetidos por página,
   divisão em bulas (um PDF pode trazer uma bula por apresentação), divisão
   em seções, e diff por palavra dentro de cada seção.

## Avisos

- A API não é documentada: é a que a página `consultas.anvisa.gov.br` usa.
  Exige o header `Authorization: Guest` e headers de navegador (o site está
  atrás do Cloudflare). Pode mudar ou fechar sem aviso.
- Os ids de PDF são JWT com validade de 5 minutos. Baixe logo após consultar.
- O cliente espera 1 segundo entre requisições.

## O que foi validado

Testado em 11 registros de 9 empresas (Multilab, Janssen, Kenvue, Cimed,
Novo Nordisk, Opella, Eurofarma, EMS, Cosmed). O diff automático bateu com a
tabela "Histórico de Alteração da Bula" que a maioria das empresas inclui
no fim do PDF. Casos que exigiram tratamento:

- Cabeçalho ou rodapé com código de versão em toda página (Eurofarma,
  Novo Nordisk): removido antes do diff.
- Várias bulas no mesmo PDF, uma por apresentação, em ordem diferente entre
  versões (Opella, Cosmed, Novo Nordisk, EMS): pareadas por semelhança de texto.
- Títulos sem numeral romano ou sem a linha "IDENTIFICAÇÃO DO MEDICAMENTO"
  (Kenvue, Opella, Cimed).
- Tabela de histórico que cita títulos de seção e ocupa várias páginas
  (Kenvue): descartada.
- Janssen não inclui a tabela de histórico.

## Cruzamento com a tabela de histórico

`scripts/validate.py` compara as seções que o diff detectou com as que a empresa declarou na
linha da tabela correspondente ao expediente. É indicativo, não prova: a coluna "Itens de bula"
mistura VP e VPS, várias empresas deixam a coluna vazia ou genérica ("Dizeres legais"), e a
Janssen não inclui a tabela.

## O que ainda não faz

- Tabelas dentro das seções viram texto corrido e geram ruído no diff.
- Só rastreia o que aparece no bulário. Medicamentos notificados (Notifarmac) usam outro endpoint
  (`/medicamento/{registro}/{5|9}/anexo`) e não têm histórico.
- Não avisa ninguém. A ANVISA tem monitoramento oficial por email (`PUT /api/monitoramento`,
  semanal ou mensal), sem diff.
