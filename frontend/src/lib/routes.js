import { COUNTRIES, domains } from "./format.js";

/** Потоки одного маршрута для схемы: что именно и сколько идёт через запрет / напрямую. */
export function flowsFor(split, route, ipsetMode) {
  const out = [];
  if (route === "zapret" && split.base_size) {
    const on = ipsetMode === "loaded";
    out.push({ key: "base", what: "Списки Flowseal", sub: on ? "" : "IPSet выключен", n: on ? split.base_size : 0, unit: "nets" });
  }
  for (const p of split.profiles.filter((p) => p.route === route)) {
    out.push({ key: "p" + p.id, what: p.name, sub: p.domains.length ? `+ ${p.domains.length} ${domains(p.domains.length)}` : "", n: p.total, unit: "nets" });
  }
  for (const r of split.rules.filter((r) => r.enabled && r.kind === "geo" && r.route === route)) {
    out.push({ key: "g" + r.id, what: COUNTRIES[r.value] || r.value, sub: "GeoIP", n: r.size, unit: "nets" });
  }
  const own = split.rules.filter((r) => r.enabled && r.route === route && r.kind !== "geo");
  const dom = own.filter((r) => r.kind === "domain").length;
  const ip = own.filter((r) => r.kind === "ip").length;
  if (dom) out.push({ key: "dom", what: "Свои домены", sub: "", n: dom, unit: "domains" });
  if (ip) out.push({ key: "ip", what: "Свои IP", sub: "", n: ip, unit: "nets" });
  return out;
}

export const netTotal = (flows) => flows.filter((f) => f.unit === "nets").reduce((a, f) => a + f.n, 0);

export function domainsThroughZapret(split) {
  return (
    split.rules.filter((r) => r.enabled && r.kind === "domain" && r.route === "zapret").length +
    split.profiles.filter((p) => p.route === "zapret").reduce((a, p) => a + p.domains.length, 0)
  );
}
