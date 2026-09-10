// Helpers puros (sem dados): rotas, formatação e nomes de seção. Importável por layout e componentes
// sem arrastar o dataset (que fica em data.ts).

export const ANVISA_BULARIO = "https://consultas.anvisa.gov.br/#/bulario/";

export const TIPO_NOME: Record<string, string> = { vp: "Bula do paciente", vps: "Bula do profissional" };

const SECOES: Record<string, Record<string, string>> = {
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

/** Âncora "principal" de uma seção na página do diff (o exportador garante que ela existe para toda seção alterada). */
export function secaoId(tipo: string, secao: string): string {
  return `sec-${tipo}-${secao}`;
}

export function dataBR(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export function formatCnpj(cnpj: string): string {
  const d = cnpj.padStart(14, "0");
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
}

export function anvisaUrl(idProduto: number): string {
  return `${ANVISA_BULARIO}detalhe/${idProduto}`;
}

// rotas do site (único lugar onde os caminhos aparecem)
export function url(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

export function produtoUrl(registro: string): string {
  return url(`/produto/${registro}/`);
}

export function diffUrl(registro: string, slug: string): string {
  return url(`/produto/${registro}/${slug}/`);
}
