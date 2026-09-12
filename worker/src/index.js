// Proxy mínimo para a API do Bulário: o runner do GitHub é bloqueado pelo Cloudflare da ANVISA
// (regra de origem), mas um Worker sai por endereços da própria Cloudflare.
//
// GET /api/consulta/...  →  https://consultas.anvisa.gov.br/api/consulta/...
// Exige o header X-Proxy-Key igual ao segredo PROXY_KEY (`wrangler secret put PROXY_KEY`).

const UPSTREAM = "https://consultas.anvisa.gov.br";

// Os mesmos headers de src/bulario/api.py.
const HEADERS = {
  Authorization: "Guest",
  Accept: "application/json, text/plain, */*",
  Referer: "https://consultas.anvisa.gov.br/",
  "User-Agent":
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
};

// Headers da resposta que o cliente usa (Retry-After no 429; Content-Type para PDF vs JSON).
const PASSTHROUGH = ["content-type", "content-length", "retry-after", "cf-ray"];

function keyOk(given, expected) {
  if (!given || !expected) return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  return a.byteLength === b.byteLength && crypto.subtle.timingSafeEqual(a, b);
}

export default {
  async fetch(request, env) {
    if (request.method !== "GET") {
      return new Response("method not allowed", { status: 405 });
    }
    if (!keyOk(request.headers.get("X-Proxy-Key"), env.PROXY_KEY)) {
      return new Response("forbidden", { status: 403 });
    }
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/consulta/")) {
      return new Response("not found", { status: 404 });
    }
    let upstream;
    try {
      upstream = await fetch(UPSTREAM + url.pathname + url.search, { headers: HEADERS });
    } catch (e) {
      // falha de rede até a ANVISA: 502 explícito em vez do erro 1101 do Worker
      return new Response(`upstream unreachable: ${e.message}`, { status: 502 });
    }
    const headers = new Headers();
    for (const name of PASSTHROUGH) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  },
};
