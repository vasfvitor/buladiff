// Carrega os JSON gerados por `bulario export --out site/src/data`.
import produtosJson from "../data/produtos.json";
import feedJson from "../data/feed.json";

export interface Produto {
  registro: string;
  idProduto: number;
  nome: string;
  empresa: string;
  cnpj: string;
  processo: string;
  ultima_publicacao: string;
  n_versoes: number;
  tem_diff: boolean;
}

export interface Versao {
  expediente: string;
  data: string;
  situacao: string;
  republicada: string[];
  tipos: string[];
  declarado: Record<string, string[]>;
}

export interface SecaoDiff {
  documento: string;
  secao: string;
  palavras: number;
  ratio: number;
  html: string;
  alterada: boolean;
}

export interface Diff {
  de: string;
  para: string;
  de_data: string;
  para_data: string;
  tipo: "vp" | "vps";
  resumo: string;
  alteradas: string[];
  declarado: string[];
  secoes: SecaoDiff[];
}

export interface Detalhe {
  meta: Produto;
  versoes: Versao[];
  diffs: Diff[];
}

export interface Publicacao {
  registro: string;
  id_produto: number;
  nome: string;
  empresa: string;
  cnpj: string;
  expediente: string;
  data: string;
  processo: string;
}

export const produtos = produtosJson as Produto[];
export const feed = feedJson as { ate?: string; ultima_execucao?: string; publicacoes: Publicacao[] };

const detalhes = import.meta.glob<Detalhe>("../data/produtos/*.json", { eager: true, import: "default" });

export function detalhe(registro: string): Detalhe | undefined {
  return detalhes[`../data/produtos/${registro}.json`];
}

export function todosDetalhes(): Detalhe[] {
  return Object.values(detalhes);
}

export const TIPO_NOME: Record<string, string> = { vp: "Bula do paciente", vps: "Bula do profissional" };

export const SECOES: Record<string, Record<string, string>> = {
  vp: {
    I: "Identificação do medicamento",
    II: "Informações ao paciente",
    "1": "Para que este medicamento é indicado?",
    "2": "Como este medicamento funciona?",
    "3": "Quando não devo usar este medicamento?",
    "4": "O que devo saber antes de usar este medicamento?",
    "5": "Onde, como e por quanto tempo posso guardar este medicamento?",
    "6": "Como devo usar este medicamento?",
    "7": "O que devo fazer quando eu me esquecer de usar este medicamento?",
    "8": "Quais os males que este medicamento pode me causar?",
    "9": "O que fazer se alguém usar uma quantidade maior do que a indicada?",
    III: "Dizeres legais",
  },
  vps: {
    I: "Identificação do medicamento",
    II: "Informações técnicas aos profissionais de saúde",
    "1": "Indicações",
    "2": "Resultados de eficácia",
    "3": "Características farmacológicas",
    "4": "Contraindicações",
    "5": "Advertências e precauções",
    "6": "Interações medicamentosas",
    "7": "Cuidados de armazenamento do medicamento",
    "8": "Posologia e modo de usar",
    "9": "Reações adversas",
    "10": "Superdose",
    III: "Dizeres legais",
  },
};

export function nomeSecao(tipo: string, secao: string): string {
  const titulo = SECOES[tipo]?.[secao];
  if (!titulo) return secao;
  return /^\d+$/.test(secao) ? `${secao}. ${titulo}` : `${secao} – ${titulo}`;
}

export function dataBR(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export function url(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

export function diffSlug(d: Diff): string {
  return `${d.de}-${d.para}-${d.tipo}`;
}

export function anvisaUrl(idProduto: number): string {
  return `https://consultas.anvisa.gov.br/#/bulario/detalhe/${idProduto}`;
}

export function formatCnpj(cnpj: string): string {
  const d = cnpj.padStart(14, "0");
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}
