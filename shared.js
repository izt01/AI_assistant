// ═══════════════════════════════════════════════════════════
//  shared.js  ―  Lumina AI  共通ユーティリティ
//  バックエンドAPI連携 + パーソナライズ対応版
// ═══════════════════════════════════════════════════════════

const API_BASE = (window.location.hostname==='localhost'||window.location.hostname==='127.0.0.1')
  ? 'http://localhost:5001/api' : '/api'

const PLANS = {
  free:   { name:'Free',   price:0,    limit:10,  color:'#a89e8c' },
  pro:    { name:'Pro',    price:980,  limit:50,  color:'#c9a84c' },
  master: { name:'Master', price:2980, limit:200, color:'#e8c97a' },
}
const PAY_AS_YOU_GO = 50

function getToken()    { return localStorage.getItem('lu_token') }
function setToken(t)   { localStorage.setItem('lu_token', t) }
function clearToken()  { localStorage.removeItem('lu_token'); localStorage.removeItem('lu_user_cache') }
function getCachedUser(){ try { return JSON.parse(localStorage.getItem('lu_user_cache')) } catch { return null } }
function setCachedUser(u){ localStorage.setItem('lu_user_cache', JSON.stringify(u)) }
function getUser()     { return getCachedUser() }
function clearUser()   { clearToken() }
function getPlanInfo(plan){ return PLANS[plan]||PLANS.free }
function getUsagePct(user){
  const limit=PLANS[user?.plan]?.limit||10
  return Math.min(100, Math.round(((user?.usage_count||user?.used||0)/limit)*100))
}

async function apiRequest(path, opts={}){
  const token=getToken()
  const headers={'Content-Type':'application/json',...(opts.headers||{})}
  if(token) headers['Authorization']=`Bearer ${token}`
  const res=await fetch(`${API_BASE}${path}`,{...opts,headers,
    body:opts.body?JSON.stringify(opts.body):undefined})
  const data=await res.json().catch(()=>({}))
  if(!res.ok) throw {status:res.status,...data}
  return data
}

async function requireAuth(){
  if(!getToken()){ location.href='login.html'; return null }
  try {
    const cached=getCachedUser()
    if(cached){
      apiRequest('/auth/me').then(d=>{if(d.user)setCachedUser(d.user)}).catch(()=>{})
      return cached
    }
    const d=await apiRequest('/auth/me')
    setCachedUser(d.user); return d.user
  } catch(e){
    if(e.status===401){ clearToken(); location.href='login.html' }
    return null
  }
}

async function logout(){
  try{ await apiRequest('/auth/logout',{method:'POST'}) }catch{}
  clearToken(); location.href='login.html'
}

function toast(msg, type=''){
  const root=document.getElementById('toast-root'); if(!root) return
  const t=document.createElement('div')
  t.className=`toast${type?' t-'+type:''}`
  const icon=type==='s'?'✓':type==='d'?'✕':type==='w'?'⚠':'ℹ'
  t.innerHTML=`<span style="font-size:14px">${icon}</span><span>${msg}</span>`
  root.appendChild(t)
  setTimeout(()=>{t.style.opacity='0';t.style.transform='translateX(20px)';
    t.style.transition='.3s ease';setTimeout(()=>t.remove(),320)},3200)
}

function showModal({title,body,actions=[],wide=false,closeBtn=true}){
  const root=document.getElementById('modal-root'); if(!root) return
  root.classList.add('open')
  root.innerHTML=`
    <div class="m-backdrop" onclick="closeModal()"></div>
    <div class="m-box${wide?' wide':''}" style="${wide?'max-width:580px':''}">
      ${closeBtn?'<div class="m-close" onclick="closeModal()">✕</div>':''}
      <div class="m-title">${title}</div>
      <div class="m-body">${body}</div>
      <div class="m-foot">${actions.map(a=>`<button class="btn ${a.cls||'btn-g'}" onclick="${a.fn}">${a.label}</button>`).join('')}</div>
    </div>`
}
function closeModal(){
  const root=document.getElementById('modal-root')
  if(root){root.classList.remove('open');root.innerHTML=''}
}

function showUpgradeModal(currentPlan){
  const plans=[
    {key:'pro',label:'Pro',price:'¥980',limit:'50回/月',color:'#c9a84c',desc:'日常使いに最適'},
    {key:'master',label:'Master',price:'¥2,980',limit:'200回/月',color:'#e8c97a',desc:'使えば使うほど賢くなる'},
  ]
  const cards=plans.filter(p=>p.key!==currentPlan).map(p=>`
    <div style="border:2px solid ${p.color};border-radius:12px;padding:16px;cursor:pointer;margin-bottom:10px;transition:all .15s"
         onclick="doUpgrade('${p.key}')">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-family:'Fraunces',serif;font-size:18px;font-weight:900;color:${p.color}">${p.label}</span>
        <span style="font-size:20px;font-weight:700">${p.price}<span style="font-size:12px;color:var(--muted)">/月</span></span>
      </div>
      <div style="margin-top:6px;font-size:13px;color:var(--muted)">${p.limit} · ${p.desc}</div>
    </div>`).join('')
  showModal({
    title:'今月の利用上限に達しました',
    body:`<p style="font-size:13px;color:var(--muted);margin-bottom:16px">プランをアップグレードして制限なしでAIと対話しましょう。会話が増えるほどあなた専用のAIに成長します。</p>${cards}
      <div style="text-align:center"><button class="btn btn-g btn-sm" onclick="payAsYouGo()">¥50で今すぐ1回使う</button></div>`,
    actions:[{label:'キャンセル',fn:'closeModal()',cls:'btn-ghost'}],wide:true
  })
}

async function doUpgrade(plan){
  const user=getCachedUser(); if(user){user.plan=plan;user.usage_count=0;setCachedUser(user)}
  closeModal(); toast(`${PLANS[plan].name}プランにアップグレードしました！`,'s')
  setTimeout(()=>location.reload(),800)
}
function showLimitReachedModal(){
  showModal({title:'今月の利用上限に達しました',
    body:'<p style="font-size:13px;color:var(--muted)">Masterプランの月間上限(200回)に達しました。来月またご利用ください。</p>',
    actions:[{label:'閉じる',fn:'closeModal()',cls:'btn-g'}]})
}
async function payAsYouGo(){
  const user=getCachedUser(); if(user){user.usage_count=Math.max(0,(user.usage_count||0)-1);setCachedUser(user)}
  closeModal(); toast('¥50で1回分を追加しました','s')
}

async function tryChat(aiType, fn){
  const user=getCachedUser(); if(!user) return
  const limit=PLANS[user.plan]?.limit||10
  if((user.usage_count||0)>=limit){
    if(user.plan==='master') showLimitReachedModal()
    else showUpgradeModal(user.plan)
    return
  }
  await fn()
}

const NAV_ITEMS=[
  {id:'dashboard',icon:'⊞',label:'ダッシュボード',href:'dashboard.html'},
  {id:'all',      icon:'✦',label:'総合チャット',   href:'chat.html?ai=all'},
  {id:'gourmet',  icon:'🍽️',label:'グルメ AI',       href:'chat.html?ai=gourmet'},
  {id:'travel',   icon:'✈️',label:'旅行 AI',        href:'chat.html?ai=travel'},
  {id:'cooking',  icon:'🍳',label:'料理 AI',        href:'chat.html?ai=cooking'},
  {id:'shopping', icon:'🛍️',label:'買い物 AI',      href:'chat.html?ai=shopping'},
  {id:'diy',      icon:'🔨',label:'DIY AI',         href:'chat.html?ai=diy'},
  {id:'home',     icon:'📺',label:'家電・インテリア',href:'chat.html?ai=home'},
  {id:'health',   icon:'💚',label:'健康 AI',         href:'chat.html?ai=health'},
  {id:'plan',     icon:'◈', label:'プラン',          href:'plan.html'},
  {id:'profile',  icon:'◉', label:'プロフィール',    href:'profile.html'},
]

function buildSidebar(activeId){
  const root=document.getElementById('sidebar-root'); if(!root) return
  const user=getCachedUser()||{}
  const pct=getUsagePct(user)
  const planInfo=getPlanInfo(user.plan)
  const warnCls=pct>=90?'dngr':pct>=70?'warn':''
  root.innerHTML=`
  <nav class="sidebar">
    <div class="sb-logo"><span class="sb-logo-mark">✦</span> Lumina AI</div>
    <div class="sb-user">
      <div class="sb-avatar">${(user.nickname||'U')[0]}</div>
      <div>
        <div class="sb-name">${user.nickname||'ゲスト'}</div>
        <div class="sb-plan" style="color:${planInfo.color}">${planInfo.name}</div>
      </div>
    </div>
    <div class="sb-usage-wrap">
      <div class="sb-usage-label">
        <span>今月の使用</span>
        <span class="${warnCls}">${user.usage_count||0} / ${planInfo.limit}</span>
      </div>
      <div class="sb-usage-bar">
        <div class="sb-usage-fill ${warnCls}" style="width:${pct}%"></div>
      </div>
    </div>
    <div class="sb-divider"></div>
    <ul class="sb-nav">
      ${NAV_ITEMS.map(item=>`
        <li><a href="${item.href}" class="sb-link${item.id===activeId?' active':''}">
          <span class="sb-icon">${item.icon}</span><span>${item.label}</span>
        </a></li>`).join('')}
    </ul>
    <div class="sb-bottom">
      <button class="sb-logout" onclick="logout()">ログアウト</button>
    </div>
  </nav>`
}

function buildHeader(title, subtitle){
  const root=document.getElementById('header-root'); if(!root) return
  root.innerHTML=`
  <header class="topbar">
    <button class="topbar-menu" onclick="toggleSidebar()" aria-label="メニュー">
      <span></span><span></span><span></span>
    </button>
    <div>
      <div class="topbar-title">${title}</div>
      ${subtitle?`<div class="topbar-sub">${subtitle}</div>`:''}
    </div>
  </header>`
}
function toggleSidebar(){ document.querySelector('.sidebar')?.classList.toggle('open') }

async function refreshUsage(){
  try{ const d=await apiRequest('/auth/me'); if(d.user) setCachedUser(d.user) }catch{}
}
async function fetchMatchScore(){
  try{ return await apiRequest('/match-score') }
  catch{ return {overall_score:0,total_sessions:0} }
}

// ══════════════════════════════════════════════
//  モバイルUI ヘルパー
// ══════════════════════════════════════════════

/**
 * モバイルヘッダーを生成して <body> 先頭に挿入
 * @param {string} title  - 中央に表示するタイトル
 * @param {string} backHref - 左の戻るボタンのリンク先（省略でロゴ）
 * @param {string} actionHtml - 右側に置くHTML（省略で空）
 */
function buildMobileHeader(title, backHref, actionHtml = '') {
  const el = document.getElementById('mobile-header-root')
  if (!el) return
  const left = backHref
    ? `<a href="${backHref}" class="mh-action" style="font-size:18px">‹</a>`
    : `<div class="mh-logo"><div class="mh-logo-icon">✦</div>Lumina</div>`
  el.innerHTML = `
    <div class="mobile-header" id="mobile-header">
      ${left}
      <div class="mh-title">${title}</div>
      <div style="width:36px;display:flex;justify-content:flex-end">${actionHtml}</div>
    </div>`
}

/**
 * ボトムナビゲーションを生成して <body> 末尾に挿入
 * @param {string} active - アクティブなアイテムのkey
 */
function buildMobileNav(active) {
  const el = document.getElementById('mobile-nav-root')
  if (!el) return
  const items = [
    { key: 'dashboard', icon: '⊞',  label: 'ホーム',   href: 'dashboard.html' },
    { key: 'chat',      icon: '✦',  label: 'チャット', href: 'chat.html?ai=all' },
    { key: 'profile',   icon: '◎',  label: 'プロフィール', href: 'profile.html' },
    { key: 'plan',      icon: '◈',  label: 'プラン',   href: 'plan.html' },
  ]
  el.innerHTML = `
    <nav class="mobile-nav">
      ${items.map(it => `
        <a href="${it.href}" class="mn-item ${active === it.key ? 'active' : ''}">
          <span class="mn-icon">${it.icon}</span>
          ${it.label}
        </a>`).join('')}
    </nav>`
}
