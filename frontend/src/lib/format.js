export const fmt = (n) => Number(n || 0).toLocaleString("ru");

/** plural(5, "подсеть", "подсети", "подсетей") */
export function plural(n, one, few, many) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export const nets = (n) => plural(n, "подсеть", "подсети", "подсетей");
export const domains = (n) => plural(n, "домен", "домена", "доменов");

export const COUNTRIES = {
  RU: "Россия", BY: "Беларусь", KZ: "Казахстан", UA: "Украина", AM: "Армения", GE: "Грузия", AZ: "Азербайджан",
  UZ: "Узбекистан", KG: "Киргизия", TJ: "Таджикистан", MD: "Молдова", TR: "Турция", FI: "Финляндия", EE: "Эстония",
  LV: "Латвия", LT: "Литва", PL: "Польша", DE: "Германия", NL: "Нидерланды", FR: "Франция", GB: "Великобритания",
  SE: "Швеция", US: "США", CN: "Китай", JP: "Япония",
};

export const ROUTE_LABEL = { off: "не трогать", direct: "напрямую", zapret: "через запрет" };
