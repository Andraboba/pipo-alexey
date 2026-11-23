import { get } from "../../lib/api.js";

export const checkHost = (host) => {
  if (!host.trim()) throw new Error("Введите домен");
  return get("/api/check-host?host=" + encodeURIComponent(host));
};
