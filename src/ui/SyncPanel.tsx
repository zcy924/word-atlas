import { useState } from "react";
import { connectSync, disconnectSync, syncNow, useSyncStatus } from "../store/sync";

export function SyncPanel() {
  const sync = useSyncStatus();
  const [mode, setMode] = useState<"login" | "create">("login");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  return (
    <section className="panel sync-panel">
      <h3 className="eyebrow">多设备同步</h3>
      <p className="muted">在其他设备填写同一组同步码和密码，即可同步学习进度、收藏、统计和设置。断网时仍可在本机学习。</p>
      {sync.code ? (
        <>
          <p>同步码：<strong className="sync-code">{sync.code}</strong></p>
          <p className="muted">请妥善保存同步码和密码，目前不提供找回功能。进行中的练习仅留在当前设备。</p>
          <div className="data-actions">
            <button className="btn btn-primary" disabled={sync.busy} onClick={() => void syncNow()}>立即同步</button>
            <button className="btn btn-ghost" disabled={sync.busy} onClick={() => void disconnectSync()}>断开此设备</button>
          </div>
        </>
      ) : (
        <form className="sync-form" onSubmit={(event) => {
          event.preventDefault();
          setError("");
          if (mode === "create" && password !== confirmation) { setError("两次输入的密码不一致。"); return; }
          void connectSync(password, mode === "login" ? code : undefined).then(() => { setPassword(""); setConfirmation(""); });
        }}>
          <div className="segmented">
            <button type="button" className={mode === "login" ? "is-on" : ""} disabled={sync.busy} onClick={() => { setMode("login"); setError(""); }}>连接已有同步空间</button>
            <button type="button" className={mode === "create" ? "is-on" : ""} disabled={sync.busy} onClick={() => { setMode("create"); setError(""); }}>首次开启</button>
          </div>
          {mode === "login" && <label>同步码<input value={code} onChange={(e) => setCode(e.target.value)} required maxLength={20} autoCapitalize="characters" autoComplete="username" placeholder="另一台设备显示的 12 位同步码" /></label>}
          <label>同步密码<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={12} maxLength={128} autoComplete={mode === "create" ? "new-password" : "current-password"} placeholder="至少 12 个字符" /></label>
          {mode === "create" && <>
            <label>再次输入密码<input type="password" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} required minLength={12} maxLength={128} autoComplete="new-password" /></label>
            <p className="muted">创建后会生成专属同步码，并上传本机学习数据。请保存同步码和密码，目前不提供找回功能。</p>
          </>}
          {error && <p className="warn-text" role="alert">{error}</p>}
          <button className="btn btn-primary" disabled={sync.busy}>{sync.busy ? "连接中…" : mode === "create" ? "创建同步空间" : "连接并同步"}</button>
        </form>
      )}
      <p role="status" aria-live="polite" className="muted">{sync.message}{sync.lastSync && !sync.conflict ? ` · ${new Date(sync.lastSync).toLocaleTimeString()}` : ""}</p>
      {sync.conflict && <div className="sync-conflict" role="alert">
        <p>两端数据不同，自动同步已暂停。选择版本会完整替换另一端，请先在下方导出本机备份。</p>
        <div className="data-actions">
          <button className="btn btn-ghost" disabled={sync.busy} onClick={() => {
            if (confirm("用云端数据替换本机记录？本机尚未上传的修改和进行中的练习将被替换。")) void syncNow("pull");
          }}>保留云端，替换本机</button>
          <button className="btn btn-ghost" disabled={sync.busy} onClick={() => {
            if (confirm("用本机数据替换云端记录？其他设备同步时会采用这份数据。")) void syncNow("push");
          }}>保留本机，替换云端</button>
        </div>
      </div>}
    </section>
  );
}
