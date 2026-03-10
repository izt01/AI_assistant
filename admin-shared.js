/* admin-shared.js — 管理者画面 共通ユーティリティ */

// ── 認証 ──────────────────────────────────────────────────────
function getAdminToken(){ return localStorage.getItem('admin_token') }
function getAdminUser(){
  try{ return JSON.parse(localStorage.getItem('admin_user') || '{}') }
  catch{ return {} }
}
function adminLogout(){
  localStorage.removeItem('admin_token')
  localStorage.removeItem('admin_user')
  location.href = 'admin-login.html'
}
function requireAdmin(){
  if(!getAdminToken()){ location.href = 'admin-login.html'; return false }
  return true
}

// ── API ───────────────────────────────────────────────────────
async function adminApi(path, opts={}){
  const token = getAdminToken()
  const res = await fetch('/api/admin' + path, {
    ...opts,
    headers:{
      'Content-Type':'application/json',
      'Authorization': token ? `Bearer ${token}` : '',
      ...(opts.headers||{})
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  if(res.status === 401 || res.status === 403){ adminLogout(); return null }
  return res.json()
}

// ── フォーマット ───────────────────────────────────────────────
function fmt$( usd, dec=2 ){ return '$' + Number(usd||0).toFixed(dec).replace(/\B(?=(\d{3})+(?!\d))/g,',') }
function fmtJPY( usd ){ return '¥' + Math.round((usd||0)*150).toLocaleString() }
function fmtN( n   ){ return Number(n||0).toLocaleString() }
function fmtDt(iso ){
  if(!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('ja-JP',{year:'numeric',month:'2-digit',day:'2-digit'})
       + ' ' + d.toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'})
}
function fmtDate(iso){
  if(!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('ja-JP',{year:'numeric',month:'2-digit',day:'2-digit'})
}

// ── トースト ───────────────────────────────────────────────────
function adminToast(msg, type='s'){
  let t = document.getElementById('admin-toast')
  if(!t){
    t = document.createElement('div')
    t.id = 'admin-toast'
    t.style.cssText='position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px'
    document.body.appendChild(t)
  }
  const el = document.createElement('div')
  el.style.cssText=`background:${type==='s'?'rgba(34,197,94,.12)':type==='e'?'rgba(239,68,68,.12)':'rgba(201,168,76,.12)'};
    border:1px solid ${type==='s'?'rgba(34,197,94,.3)':type==='e'?'rgba(239,68,68,.3)':'rgba(201,168,76,.3)'};
    color:${type==='s'?'#4ade80':type==='e'?'#f87171':'#e8c97a'};
    padding:10px 18px;border-radius:10px;font-size:13px;font-family:inherit;
    box-shadow:0 8px 24px rgba(0,0,0,.3);animation:fadeUp .25s ease`
  el.textContent = msg
  t.appendChild(el)
  setTimeout(()=>el.remove(), 3200)
}

// ── モーダル ───────────────────────────────────────────────────
function adminModal({title='', body='', onOk=null, okLabel='実行', okColor='var(--red)', cancelLabel='キャンセル'}={}){
  let overlay = document.getElementById('admin-modal-overlay')
  if(!overlay){
    overlay = document.createElement('div')
    overlay.id = 'admin-modal-overlay'
    overlay.style.cssText='position:fixed;inset:0;z-index:8000;background:rgba(0,0,0,.7);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:24px'
    document.body.appendChild(overlay)
  }
  overlay.innerHTML=`
    <div style="background:#1c1f28;border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:28px;max-width:420px;width:100%;box-shadow:0 24px 60px rgba(0,0,0,.5)">
      <div style="font-family:'Fraunces',serif;font-size:18px;font-weight:700;margin-bottom:10px">${title}</div>
      <div style="font-size:13px;color:rgba(232,228,220,.6);line-height:1.7;margin-bottom:24px">${body}</div>
      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button id="modal-cancel" style="background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);color:rgba(232,228,220,.7);padding:9px 20px;border-radius:8px;font-family:inherit;font-size:13px;cursor:pointer">${cancelLabel}</button>
        <button id="modal-ok" style="background:${okColor};border:none;color:#fff;padding:9px 20px;border-radius:8px;font-family:inherit;font-size:13px;font-weight:700;cursor:pointer">${okLabel}</button>
      </div>
    </div>`
  overlay.style.display='flex'
  document.getElementById('modal-cancel').onclick = ()=>{ overlay.style.display='none' }
  document.getElementById('modal-ok').onclick = ()=>{ overlay.style.display='none'; onOk&&onOk() }
}

// ── サイドナビ描画 ─────────────────────────────────────────────
function buildAdminNav(active='dashboard'){
  const nav_items = [
    {id:'dashboard', icon:'▣',  label:'ダッシュボード',  href:'admin-dashboard.html'},
    {id:'charges',   icon:'⬡',  label:'API費用・チャージ', href:'admin-charges.html'},
    {id:'users',     icon:'◉',  label:'ユーザー管理',    href:'admin-users.html'},
  ]
  const user = getAdminUser()
  return `
  <nav class="admin-nav">
    <div class="admin-logo">
      <div class="admin-logo-gem">⚙</div>
      <div>
        <div class="admin-logo-name">Lumina</div>
        <div class="admin-logo-sub">ADMIN</div>
      </div>
    </div>
    <ul class="admin-nav-list">
      ${nav_items.map(n=>`
        <li>
          <a href="${n.href}" class="admin-nav-link ${active===n.id?'active':''}">
            <span class="admin-nav-icon">${n.icon}</span>
            <span>${n.label}</span>
          </a>
        </li>`).join('')}
    </ul>
    <div class="admin-nav-footer">
      <div class="admin-nav-user">
        <div class="admin-nav-avatar">A</div>
        <div>
          <div style="font-size:12.5px;font-weight:600">${user.nickname||user.email||'Admin'}</div>
          <div style="font-size:10.5px;color:rgba(232,228,220,.35)">管理者</div>
        </div>
      </div>
      <button class="admin-nav-logout" onclick="adminLogout()">ログアウト</button>
    </div>
  </nav>`
}

// ── 共通CSS（全管理画面で <style id="admin-shared-css"> で差し込む）
const ADMIN_CSS = `
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,700;0,900;1,400&family=Noto+Sans+JP:wght@300;400;500;700&family=JetBrains+Mono:wght@400;600&display=swap');
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes spin{to{transform:rotate(360deg)}}

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#0a0b0f;--ink2:#12141a;--ink3:#1c1f28;--ink4:#242731;
  --cream:#e8e4dc;--muted:rgba(232,228,220,.45);--subtle:rgba(232,228,220,.22);
  --gold:#c9a84c;--gold2:#e8c97a;
  --border:rgba(201,168,76,.12);--border2:rgba(255,255,255,.07);
  --red:#ef4444;--red-bg:rgba(239,68,68,.08);--red-border:rgba(239,68,68,.2);
  --green:#22c55e;--green-bg:rgba(34,197,94,.08);--green-border:rgba(34,197,94,.2);
  --blue:#3b82f6;--blue-bg:rgba(59,130,246,.08);--blue-border:rgba(59,130,246,.2);
  --orange:#f97316;--orange-bg:rgba(249,115,22,.08);
  --nav-w:220px;--r:10px;
}
body{font-family:'Noto Sans JP',sans-serif;background:var(--ink2);color:var(--cream);
  min-height:100vh;-webkit-font-smoothing:antialiased;overflow-x:hidden}

/* ── レイアウト ── */
.admin-layout{display:flex;min-height:100vh}
.admin-main{flex:1;margin-left:var(--nav-w);min-height:100vh;padding:32px 36px;
  background:var(--ink2);position:relative}
.admin-main::before{content:'';position:fixed;top:0;right:0;width:60%;height:100%;
  background:radial-gradient(ellipse 60% 50% at 80% 20%,rgba(201,168,76,.04) 0%,transparent 60%);
  pointer-events:none;z-index:0}

/* ── サイドナビ ── */
.admin-nav{position:fixed;top:0;left:0;width:var(--nav-w);height:100vh;
  background:var(--ink);border-right:1px solid var(--border2);
  display:flex;flex-direction:column;z-index:100;overflow:hidden}
.admin-logo{display:flex;align-items:center;gap:10px;padding:22px 20px 18px;
  border-bottom:1px solid var(--border2)}
.admin-logo-gem{width:30px;height:30px;background:linear-gradient(135deg,var(--red),#b91c1c);
  border-radius:7px;display:flex;align-items:center;justify-content:center;
  font-size:12px;color:#fff;font-weight:700;flex-shrink:0}
.admin-logo-name{font-family:'Fraunces',serif;font-size:16px;font-weight:900;letter-spacing:-.02em}
.admin-logo-sub{font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:600;
  color:var(--red);letter-spacing:.15em}
.admin-nav-list{list-style:none;padding:14px 10px;flex:1;display:flex;flex-direction:column;gap:3px}
.admin-nav-link{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:8px;
  font-size:13px;color:var(--muted);text-decoration:none;transition:all .18s}
.admin-nav-link:hover{background:rgba(255,255,255,.05);color:var(--cream)}
.admin-nav-link.active{background:rgba(201,168,76,.1);color:var(--gold2);font-weight:600}
.admin-nav-icon{font-size:14px;width:18px;text-align:center;flex-shrink:0}
.admin-nav-footer{padding:14px 14px 18px;border-top:1px solid var(--border2)}
.admin-nav-user{display:flex;align-items:center;gap:9px;margin-bottom:10px}
.admin-nav-avatar{width:28px;height:28px;border-radius:50%;
  background:linear-gradient(135deg,var(--gold),var(--gold2));
  display:flex;align-items:center;justify-content:center;
  font-size:12px;font-weight:700;color:var(--ink);flex-shrink:0}
.admin-nav-logout{width:100%;background:none;border:1px solid rgba(239,68,68,.2);
  border-radius:7px;padding:7px;font-size:11.5px;font-family:inherit;
  color:rgba(239,68,68,.6);cursor:pointer;transition:all .18s}
.admin-nav-logout:hover{background:var(--red-bg);color:var(--red)}

/* ── ページヘッダー ── */
.admin-page-hdr{margin-bottom:28px;position:relative;z-index:1}
.admin-page-title{font-family:'Fraunces',serif;font-size:26px;font-weight:900;
  letter-spacing:-.03em;margin-bottom:4px}
.admin-page-sub{font-size:13px;color:var(--muted)}

/* ── KPIカード ── */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px;margin-bottom:24px}
.kpi{background:rgba(255,255,255,.03);border:1px solid var(--border2);border-radius:14px;
  padding:18px 20px;position:relative;overflow:hidden;transition:border-color .2s}
.kpi:hover{border-color:rgba(201,168,76,.2)}
.kpi-label{font-size:11px;font-weight:600;color:var(--muted);letter-spacing:.06em;
  text-transform:uppercase;margin-bottom:10px}
.kpi-val{font-family:'Fraunces',serif;font-size:30px;font-weight:900;letter-spacing:-.04em;line-height:1}
.kpi-sub{font-size:11.5px;color:var(--muted);margin-top:5px}
.kpi-icon{position:absolute;right:16px;top:16px;font-size:22px;opacity:.18}
.kpi.gold .kpi-val{color:var(--gold2)}
.kpi.red  .kpi-val{color:#f87171}
.kpi.green .kpi-val{color:#4ade80}
.kpi.blue .kpi-val{color:#60a5fa}

/* ── セクション ── */
.admin-section{background:rgba(255,255,255,.025);border:1px solid var(--border2);
  border-radius:14px;padding:22px 24px;margin-bottom:20px;position:relative;z-index:1}
.admin-section-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;flex-wrap:wrap;gap:10px}
.admin-section-title{font-family:'Fraunces',serif;font-size:16px;font-weight:700;letter-spacing:-.02em}

/* ── テーブル ── */
.admin-table{width:100%;border-collapse:collapse}
.admin-table th{font-size:10.5px;font-weight:600;color:var(--muted);letter-spacing:.08em;
  text-transform:uppercase;padding:0 12px 10px;text-align:left;border-bottom:1px solid var(--border2)}
.admin-table td{font-size:12.5px;padding:11px 12px;border-bottom:1px solid rgba(255,255,255,.04)}
.admin-table tr:last-child td{border-bottom:none}
.admin-table tr:hover td{background:rgba(255,255,255,.02)}
.admin-table .mono{font-family:'JetBrains Mono',monospace;font-size:11px}

/* ── バッジ ── */
.badge{display:inline-flex;align-items:center;padding:2px 9px;border-radius:99px;
  font-size:10.5px;font-weight:600;letter-spacing:.04em}
.badge-free{background:rgba(255,255,255,.06);color:var(--muted)}
.badge-pro{background:var(--blue-bg);border:1px solid var(--blue-border);color:#93c5fd}
.badge-master{background:rgba(201,168,76,.1);border:1px solid rgba(201,168,76,.25);color:var(--gold2)}
.badge-active{background:var(--green-bg);border:1px solid var(--green-border);color:#4ade80}
.badge-inactive{background:var(--red-bg);border:1px solid var(--red-border);color:#f87171}

/* ── ボタン ── */
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;
  border-radius:var(--r);font-size:12.5px;font-weight:600;font-family:inherit;
  cursor:pointer;transition:all .18s;border:1.5px solid transparent;white-space:nowrap}
.btn-gold{background:linear-gradient(135deg,var(--gold),var(--gold2));color:var(--ink);border:none;
  box-shadow:0 3px 14px rgba(201,168,76,.2)}
.btn-gold:hover{box-shadow:0 5px 20px rgba(201,168,76,.35);transform:translateY(-1px)}
.btn-ghost{background:transparent;color:var(--cream);border-color:var(--border2)}
.btn-ghost:hover{background:rgba(255,255,255,.05);border-color:rgba(255,255,255,.15)}
.btn-danger{background:var(--red-bg);color:#f87171;border-color:var(--red-border)}
.btn-danger:hover{background:rgba(239,68,68,.15)}
.btn-sm{padding:5px 11px;font-size:11.5px}
.btn-xs{padding:3px 9px;font-size:11px}

/* ── 進捗バー ── */
.progress-bar{height:6px;background:rgba(255,255,255,.07);border-radius:99px;overflow:hidden;margin-top:8px}
.progress-fill{height:100%;border-radius:99px;transition:width .5s ease;
  background:linear-gradient(90deg,var(--gold),var(--gold2))}
.progress-fill.danger{background:linear-gradient(90deg,#ef4444,#f97316)}
.progress-fill.warning{background:linear-gradient(90deg,#f97316,#eab308)}

/* ── 入力 ── */
.inp{background:rgba(255,255,255,.05);border:1px solid var(--border2);border-radius:8px;
  padding:9px 13px;font-size:13px;font-family:inherit;color:var(--cream);outline:none;transition:border-color .18s}
.inp:focus{border-color:rgba(201,168,76,.4)}
.inp::placeholder{color:var(--subtle)}
select.inp option{background:var(--ink3);color:var(--cream)}

/* ── ローダー ── */
.spinner{width:18px;height:18px;border:2px solid rgba(255,255,255,.1);
  border-top-color:var(--gold);border-radius:50%;animation:spin .7s linear infinite;display:inline-block}

/* ── アラートバー ── */
.alert-bar{border-radius:10px;padding:11px 16px;font-size:12.5px;
  display:flex;align-items:center;gap:10px;margin-bottom:16px}
.alert-bar.warning{background:rgba(234,179,8,.08);border:1px solid rgba(234,179,8,.2);color:#fde047}
.alert-bar.danger{background:var(--red-bg);border:1px solid var(--red-border);color:#f87171}
.alert-bar.info{background:var(--blue-bg);border:1px solid var(--blue-border);color:#93c5fd}

@media(max-width:768px){
  .admin-nav{width:100%;height:auto;position:static;flex-direction:row;border-right:none;border-bottom:1px solid var(--border2)}
  .admin-main{margin-left:0;padding:20px 16px}
  .kpi-grid{grid-template-columns:1fr 1fr}
}
`
