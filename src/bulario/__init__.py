"""Arquivo e diff de versões de bula do Bulário Eletrônico da ANVISA."""

from bulario.api import Client
from bulario.diff import diff_documents, render_html
from bulario.extract import Document, documents_from_pdf

__all__ = ["Client", "Document", "diff_documents", "documents_from_pdf", "render_html"]
