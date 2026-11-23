import { useState } from "react";
import RuleForm from "./RuleForm.jsx";
import GeoForm from "./GeoForm.jsx";
import CheckResult from "./CheckResult.jsx";
import RuleList from "./RuleList.jsx";
import FilesMap from "./FilesMap.jsx";
import "../../styles/split.css";

export default function SplitPage() {
  const [check, setCheck] = useState(null);
  return (
    <section className="tab">
      <div className="intro">
        <h2>Сплит: что через запрет, а что напрямую</h2>
        <p>
          Незаблокированным сайтам обход не нужен — пустите их <b className="t-direct">напрямую</b>. Заблокированное, чего нет
          в списках Flowseal, — <b className="t-zapret">через запрет</b>. Домен охватывает все поддомены.
        </p>
      </div>
      <RuleForm onCheck={setCheck} />
      <GeoForm />
      {check && <CheckResult result={check} />}
      <RuleList onCheck={setCheck} />
      <FilesMap />
    </section>
  );
}
