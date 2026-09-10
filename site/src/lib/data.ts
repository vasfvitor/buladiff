// Dados gerados por `bulario export --out site/src/data`. Os arquivos leves (lista de produtos,
// recentes, feed) são carregados de imediato; o detalhe de cada produto (com o texto dos diffs, MBs)
// só quando a página daquele produto é gerada.
import produtosJson from "../data/produtos.json";
import recentesJson from "../data/recentes.json";
import feedJson from "../data/feed.json";
import catalogoJson from "../data/catalogo.json";

export interface Produto {
  registro: string;
  idProduto: number;
  nome: string;
  empresa: string;
  cnpj: string;
  principio_ativo: string;
  classes: string[]; // classes terapêuticas
  categoria: string; // categoria regulatória (Genérico, Similar, Novo…)
  referencia: string; // medicamento de referência
  apresentacoes: string[];
  ultima_publicacao: string;
  n_versoes: number;
  diffs: string[]; // slugs
}

export interface Versao {
  expediente: string;
  data: string;
  republicada: string[];
  situacao: string;
  declarado: Record<string, string[]>;
  repetida: boolean; // mesmos PDFs de uma versão anterior (expediente novo, texto igual)
}

export interface SecaoDiff {
  secao: string;
  alterada: boolean;
  declarada: boolean;
  palavras: number;
  ratio: number;
  html: string;
  contexto: string; // "" quando a seção é curta (html já é o contexto)
  ancora: string;
}

export interface DocumentoDiff {
  indice: number;
  rotulo: string;
  secoes: SecaoDiff[];
}

export interface Diff {
  slug: string;
  de: string;
  para: string;
  de_data: string;
  para_data: string;
  tipo: "vp" | "vps";
  alteradas: string[];
  declarado: string[];
  marcado: boolean; // as duas versões vieram de PDF marcado (parágrafos preservados)
  documentos: DocumentoDiff[];
}

export interface Detalhe {
  meta: Produto;
  versoes: Versao[];
  diffs: Diff[];
}

export interface Recente {
  registro: string;
  nome: string;
  empresa: string;
  slug: string;
  tipo: "vp" | "vps";
  para_data: string;
  alteradas: string[];
  declarado: string[];
}

export interface Publicacao {
  registro: string;
  nome: string;
  empresa: string;
  expediente: string;
  data: string;
  arquivado: boolean;
}

export const produtos = produtosJson as Produto[];
export const recentes = recentesJson as Recente[];
export const feed = feedJson as { ate: string | null; publicacoes: Publicacao[] };

export interface ItemCatalogo {
  registro: string;
  idProduto: number;
  nome: string;
  empresa: string;
  cnpj: string;
  data: string; // última bula publicada
  arquivado: boolean;
}
export const catalogo = catalogoJson as { atualizado: string | null; produtos: ItemCatalogo[] };

/** Letra inicial usada para dividir o catálogo em páginas ("0-9" para o que não começa com letra). */
export function letraCatalogo(nome: string): string {
  const c = nome.trim().charAt(0).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
  return /[A-Z]/.test(c) ? c : "0-9";
}

const detalhes = import.meta.glob<{ default: Detalhe }>("../data/produtos/*.json");

export async function detalhe(registro: string): Promise<Detalhe> {
  const load = detalhes[`../data/produtos/${registro}.json`];
  if (!load) throw new Error(`produto ${registro} não exportado`);
  return (await load()).default;
}
