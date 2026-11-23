export default function FilesMap() {
  return (
    <details className="card">
      <summary>Куда это записывается</summary>
      <table className="map">
        <thead>
          <tr><td /><th className="t-direct">Напрямую</th><th className="t-zapret">Через запрет</th></tr>
        </thead>
        <tbody>
          <tr><th>Домен</th><td><code>lists/list-exclude-user.txt</code></td><td><code>lists/list-general-user.txt</code></td></tr>
          <tr><th>IP / подсеть / страна</th><td><code>lists/ipset-exclude-user.txt</code></td><td>добавляется в <code>lists/ipset-all.txt</code></td></tr>
        </tbody>
      </table>
      <p className="hint">
        Исключение сильнее включения. Запрет читает списки при старте, поэтому после изменений его нужно перезапустить
      </p>
    </details>
  );
}
