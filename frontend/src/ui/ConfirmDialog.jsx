import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

const ConfirmCtx = createContext(async () => false);

/** const ok = await confirm({ title, body: <jsx/>, ok: "Удалить", danger: true }) */
export function ConfirmProvider({ children }) {
  const [req, setReq] = useState(null);
  const ref = useRef(null);

  const confirm = useCallback((opts) => new Promise((resolve) => setReq({ ...opts, resolve })), []);

  useEffect(() => {
    if (req && ref.current && !ref.current.open) ref.current.showModal();
  }, [req]);

  const close = (value) => {
    ref.current?.close();
    req?.resolve(value);
    setReq(null);
  };

  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      <dialog ref={ref} onCancel={(e) => { e.preventDefault(); close(false); }}>
        {req && (
          <>
            <h3>{req.title}</h3>
            <div className="confirm-body">{req.body}</div>
            <div className="row end">
              <button className="btn ghost" onClick={() => close(false)}>Отмена</button>
              <button className={"btn solid" + (req.danger ? " danger" : "")} onClick={() => close(true)} autoFocus>
                {req.ok || "Да"}
              </button>
            </div>
          </>
        )}
      </dialog>
    </ConfirmCtx.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmCtx);
