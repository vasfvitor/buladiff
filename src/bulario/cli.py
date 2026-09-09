"""Linha de comando: bulario search | feed | fetch | diff | sections | history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bulario import feed
from bulario.api import Client
from bulario.archive import fetch, local_versions
from bulario.diff import diff_documents, render_html, summary
from bulario.extract import documents_from_pdf


def cmd_search(args: argparse.Namespace) -> None:
    filtro = {"nomeProduto": args.nome} if args.nome else {}
    if args.cnpj:
        filtro["cnpj"] = args.cnpj
    if args.desde:
        filtro["periodoPublicacaoInicial"] = args.desde
        filtro["periodoPublicacaoFinal"] = args.ate
    for p in Client().search_all(**filtro):
        print(
            f"{p['numeroRegistro']}  {p['nomeProduto'][:32]:32}  {p['razaoSocial'][:40]:40}  {p['data'][:10]}"
        )


def cmd_fetch(args: argparse.Namespace) -> None:
    for registro in args.registro:
        try:
            fetch(registro, Path(args.data), latest=None if args.all else args.latest)
        except LookupError as e:
            print(e, file=sys.stderr)


def cmd_diff(args: argparse.Namespace) -> None:
    if args.registro:
        versions = [v for v in local_versions(args.registro, Path(args.data)) if args.tipo in v.files]
        if len(versions) < 2:
            sys.exit(
                f"menos de duas versões {args.tipo} em {args.data}/{args.registro}; rode `bulario fetch`"
            )
        a, b = versions[-2].files[args.tipo], versions[-1].files[args.tipo]
    else:
        a, b = Path(args.a), Path(args.b)
    rows = diff_documents(documents_from_pdf(a), documents_from_pdf(b), skip_preamble=args.sem_preambulo)
    if args.html:
        Path(args.html).write_text(render_html(rows, f"{a.name} → {b.name}"))
        print(f"{args.html}")
    print(summary(rows))


def cmd_feed(args: argparse.Namespace) -> None:
    feed.run(Path(args.data), desde=args.desde, ate=args.ate, download=args.baixar)


def cmd_history(args: argparse.Namespace) -> None:
    from bulario.history import read_history

    for e in read_history(args.pdf).entries:
        secoes = ", ".join(e.secoes) or "-"
        print(f"{e.data:10}  {e.expediente:14}  {e.versoes:7}  seções: {secoes:14}  {e.itens[:70]}")


def cmd_sections(args: argparse.Namespace) -> None:
    for i, d in enumerate(documents_from_pdf(args.pdf), 1):
        print(f"documento {i} ({d.tipo}) — {d.label}")
        for k, v in d.secoes.items():
            print(f"{len(v):7d}  {k}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bulario", description=__doc__)
    p.add_argument("--data", default="data", help="diretório do arquivo local (padrão: data)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="busca produtos no bulário")
    s.add_argument("nome", nargs="?", help="nome do produto")
    s.add_argument("--cnpj")
    s.add_argument("--desde", help="publicadas a partir de AAAA-MM-DD")
    s.add_argument("--ate", default=None, help="até AAAA-MM-DD (padrão: hoje)")
    s.set_defaults(func=cmd_search)

    fd = sub.add_parser("feed", help="bulas publicadas num período; --baixar arquiva as novas versões")
    fd.add_argument("--desde", help="AAAA-MM-DD (padrão: onde a última execução parou, ou hoje)")
    fd.add_argument("--ate", help="AAAA-MM-DD (padrão: hoje)")
    fd.add_argument("--baixar", action="store_true")
    fd.set_defaults(func=cmd_feed)

    f = sub.add_parser("fetch", help="baixa versões de bula de um registro")
    f.add_argument("registro", nargs="+", help="número de registro (9 dígitos)")
    f.add_argument("--all", action="store_true", help="todas as versões (padrão: as 2 mais recentes)")
    f.add_argument("--latest", type=int, default=2)
    f.set_defaults(func=cmd_fetch)

    d = sub.add_parser("diff", help="diff por seção entre duas versões")
    d.add_argument("a", nargs="?", help="PDF antigo")
    d.add_argument("b", nargs="?", help="PDF novo")
    d.add_argument("--registro", help="em vez de PDFs: as duas últimas versões locais do registro")
    d.add_argument("--tipo", choices=["vp", "vps"], default="vp")
    d.add_argument("--html", help="grava relatório HTML neste caminho")
    d.add_argument("--sem-preambulo", action="store_true", help="ignora capa/preâmbulo")
    d.set_defaults(func=cmd_diff)

    h = sub.add_parser("history", help="lê a tabela 'Histórico de Alteração da Bula' (extra: tables)")
    h.add_argument("pdf")
    h.set_defaults(func=cmd_history)

    x = sub.add_parser("sections", help="mostra a segmentação de um PDF")
    x.add_argument("pdf")
    x.set_defaults(func=cmd_sections)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.cmd == "search" and args.desde and not args.ate:
        import datetime

        args.ate = datetime.date.today().isoformat()
    if args.cmd == "diff" and not args.registro and not (args.a and args.b):
        sys.exit("informe dois PDFs ou --registro")
    args.func(args)


if __name__ == "__main__":
    main()
