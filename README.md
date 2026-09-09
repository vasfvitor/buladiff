# Bulario

Arquivo e diff de versões de bulas do Bulário Eletrônico da ANVISA.

A ANVISA publica só o PDF de cada versão. Este projeto baixa todas as
versões de um produto e mostra o que mudou entre duas delas, seção por
seção (as seções são as da RDC 47/2009: 4. Contraindicações,
5. Advertências e precauções e assim por diante).

## Uso

```sh
python3 bulario.py search dipirona            # registros, empresa, data da última bula
python3 bulario.py fetch 118190404            # baixa as duas versões mais recentes
python3 bulario.py fetch 118190404 --all      # todas as versões
python3 bulario.py diff a.pdf b.pdf saida.html
python3 bulario.py sections a.pdf             # mostra a segmentação (depuração)
```

Só depende do Python 3 e do `pdftotext` (pacote `poppler-utils`).

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

## O que ainda não faz

- Não lê a tabela "Histórico de Alteração da Bula" (o `-layout` a embaralha;
  precisa de extração de tabela).
- Tabelas dentro das seções viram texto corrido e geram ruído no diff.
- Não monitora: rode `fetch` de novo para ver se há versão nova.
