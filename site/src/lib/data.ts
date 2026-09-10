// Dados gerados por `bulario export --out site/src/data`. Os arquivos leves (lista de produtos,
// recentes, feed) são carregados de imediato; o detalhe de cada produto (com o texto dos diffs, MBs)
// só quando a página daquele produto é gerada.
import produtosJson from "../data/produtos.json";
import recentesJson from "../data/recentes.json";
import feedJson from "../data/feed.json";

export interface Produto {
  registro: string;
  idProduto: number;
  nome: string;
  empresa: string;
  cnpj: string;
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
}

export interface SecaoDiff {
  secao: string;
  alterada: boolean;
  declarada: boolean;
  palavras: number;
  ratio: number;
  html: string;
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

const detalhes = import.meta.glob<{ default: Detalhe }>("../data/produtos/*.json");

export async function detalhe(registro: string): Promise<Detalhe> {
  const load = detalhes[`../data/produtos/${registro}.json`];
  if (!load) throw new Error(`produto ${registro} não exportado`);
  return (await load()).default;
}
