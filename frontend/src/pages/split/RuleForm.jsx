import { useState } from "react";
import { post } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button, Seg } from "../../ui/controls.jsx";
import { useToast } from "../../ui/Toasts.jsx";
import { checkHost } from "./checkHost.js";

export const ROUTES = [
  { v: "direct", label: "Напрямую" },
  { v: "zapret", label: "Через запрет" },
];

export default function RuleForm({ onCheck }) {
  const { setSplit } = useStore();
  const toast = useToast();
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [route, setRoute] = useState("direct");

  const add = async () => {
    setSplit(await post("/api/split/rules", { value, route, note }));
    toast(`${route === "direct" ? "Напрямую" : "Через запрет"}: ${value.trim()}`);
    setValue("");
    setNote("");
  };

  return (
    <form className="card addrule" autoComplete="off" onSubmit={(e) => e.preventDefault()}>
      <input className="mono grow" aria-label="Домен, ссылка или IP" value={value} onChange={(e) => setValue(e.target.value)} spellCheck={false}
        placeholder="example.com, https://site.ru/page или 1.2.3.0/24" />
      <Seg options={ROUTES} value={route} onChange={setRoute} />
      <input className="note" aria-label="Заметка к правилу" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Заметка" />
      <Button kind="solid" type="submit" disabled={!value.trim()} onClick={add}>Добавить</Button>
      <Button onClick={async () => onCheck(await checkHost(value))}>Проверить доступ</Button>
    </form>
  );
}
