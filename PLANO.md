# Plano: extração estruturada, catálogo e enriquecimento

Rascunho de trabalho. Cada etapa vira um commit; o status é atualizado aqui.

## O que já se sabe (sondagens de 2026-09-10)

- `filter[cnpj]` funciona com os 14 dígitos, com ou sem pontuação (Multilab: 195 produtos).
  Com CNPJ parcial devolve 0. O resultado anterior "0" era isso.
- Catálogo inteiro: `filter[nomeProduto]=` vazio com `count=1000` devolve 8.819 produtos em 9 páginas.
  Cada item tem registro, nome, empresa, CNPJ, expediente e data da última bula.
- `GET /medicamento/produtos/codigo/{idProduto}` traz `principioAtivo`, `classesTerapeuticas`,
  `categoriaRegulatoria` (Genérico, Similar, Novo…), `medicamentoReferencia` e as apresentações.
- Os PDFs vêm do Word com árvore de estrutura (`Tagged: yes`): elementos `P`, `H1`, `Table/TR/TD`, e
  todo caractere carrega o `mcid` do seu elemento. A "parent tree" do PDF liga (página, `mcid`) ao
  elemento dono; o pdfplumber expõe o `mcid` em `chars` e `extract_words`.

## Etapas

### 1. CNPJ no `search` (feito na sondagem)

- [x] Confirmar formato aceito.
- [x] `bulario search --cnpj`: aceita pontuação, avisa se não tiver 14 dígitos. README.

### 2. Extração estruturada (parágrafos e tabelas)

Objetivo: cada seção guarda parágrafos (separados por linha em branco) e linhas de tabela
(células separadas por ` | `), em vez de um único bloco de texto. O diff passa a alinhar por parágrafo
e o site mostra parágrafos; tabelas param de inflar o diff.

- [x] 9 dos 11 registros têm PDF marcado (Risperdal/Janssen e Buscopan/Boehringer não; caem no caminho por linhas).
- [x] `tagged.tagged_blocks(pdf)`: guiado pela parent tree (página → MCID → elemento); parágrafos,
      títulos e linhas de tabela (`célula | célula`); cabeçalho/rodapé ficam fora. `None` se não marcado.
      Armadilhas encontradas: o Word aninha os itens de lista seguintes dentro do primeiro e omite `/Pg`
      em elementos herdados (por isso não se desce pela árvore); PDFs com árvore mas `Marked` falso.
- [x] `split_documents(blocos, sep=PARAGRAFO)`; `split_heading` separa título colado ao texto
      ("1. INDICAÇÕES Hipertensão"). As 9 bulas marcadas dão as mesmas seções que o caminho por linhas.
- [x] `diff.word_diff`: a quebra de parágrafo é um token; no HTML vira `<span class="pbr"></span>`.
- [x] Site: regra `.pbr` no CSS; nota na página do diff diz se o texto veio da estrutura; testes.
- [x] Rebaixados os 11 registros com `fetch --curados --keep-pdf` (PDFs ficam locais, fora do git) e
      reextraídos com `bulario reextract`; risperidona VPS dá 4, 5, 7, III (mais um `I` real, "+ 1
      seringa dosadora"). O histórico da API oscila de um dia para o outro: versões que sumiram da
      listagem foram restauradas do git; com os PDFs locais, `reextract` recupera as que já baixamos.
- [x] Tabelas: o Word grava uma tabela inteira como uma linha só com células altas e parte a linha onde
      a página quebra; por célula o diff enchia de ruído. Cada `TR` vira linhas visuais (palavras
      agrupadas por posição vertical), como no pdftotext, o que é estável entre versões.
- [x] O Word troca de trecho (MCID) no meio de palavras (`l` + `osartana`, `placebo` + `-controlled`)
      e o pdfplumber separa palavras por trecho. As palavras são montadas dos caracteres do bloco inteiro:
      separa palavra o espaço em branco, a mudança de linha ou um vão maior que 3 pt.
- [x] Versão marcada contra versão sem marcação: cada JSON de versão marcada guarda também a extração
      por linhas (`documentos_linhas`), e o diff usa a mesma extração dos dois lados. Misturar as duas
      enchia o diff de quebras de parágrafo e de restos de título ("MEDICAMENTO?").
- [x] Título que quebrou de linha no pdftotext ("…DE USAR ESTE" / "MEDICAMENTO?"): a continuação em
      maiúsculas é descartada.
- [x] Mudança só na divisão em parágrafos não conta nem aparece como `<ins>`/`<del>`.

### 3. Detalhe do produto no arquivo e no site

- [x] `fetch` grava `detalhe` no `meta.json` (princípio ativo, classes terapêuticas, ATC, categoria
      regulatória, referência, vencimento do registro, apresentações).
- [x] `export`: campos novos em `produtos.json`; site mostra na página do produto e na lista, e o
      Pagefind indexa princípio ativo (busca por "risperidona" acha Risperdal).
- [x] Filtro da lista cobre nome, empresa, princípio ativo, classe e categoria.
- [x] `detalhe` preenchido nos 11 registros pelo próprio rebaixamento.

### 4. Catálogo inteiro

- [x] `bulario catalogo`: 9 requisições, grava `data/catalogo.json` (registro, nome, empresa, CNPJ,
      data da última bula). Roda no `coleta-local.sh` uma vez por semana.
- [x] Site: contagem na home ("11 produtos acompanhados, de 8.819 no Bulário") e páginas
      `/catalogo/<letra>/` com filtro por nome/empresa e link para a ANVISA nos que não estão arquivados.

### 5. Depois (não começar antes de 2–4)

- Tabelas de verdade no site: hoje cada `TR` vira linhas visuais e o diff mostra texto corrido. Renderizar como
  `<table>` nas seções onde as bulas mais mudam (posologia, reações adversas). Anotado em 2026-09-10.
- Monitoramento oficial por email (`PUT /api/monitoramento`) com o email do Vitor.
- Testar outras nuvens contra o Cloudflare (Worker, Oracle, Fly).
- Lighthouse/axe no site.
