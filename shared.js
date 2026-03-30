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
const planRank = {free:0, pro:1, master:2}
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
  if(res.status===401){
    // どのAPIでも401が返ったら即強制ログアウト（停止・期限切れ両対応）
    _forceLogout(data.error||'セッションが無効です')
    throw {status:401,...data}
  }
  if(!res.ok) throw {status:res.status,...data}
  return data
}

function _forceLogout(reason=''){
  // 既にログアウト処理中なら何もしない（多重発火防止）
  if(_forceLogout._running) return
  _forceLogout._running = true
  clearToken()
  if(reason){
    sessionStorage.setItem('logout_reason', reason)
  }
  location.href = "login.html"
}
_forceLogout._running = false

async function requireAuth(){
  if(!getToken()){ location.href='login.html'; return null }
  try {
    const cached=getCachedUser()
    if(cached){
      // キャッシュがあっても必ずサーバーで有効性を確認する
      // （停止・削除されたアカウントをキャッシュで通過させない）
      try {
        const d = await apiRequest('/auth/me')  // ← await で待つ
        setCachedUser(d.user)
        _startSessionWatcher()
        startFallbackWatcher()
        return d.user
      } catch(e) {
        return null
      }
    }
    const d=await apiRequest('/auth/me')
    setCachedUser(d.user)
    _startSessionWatcher()
    startFallbackWatcher()
    return d.user
  } catch(e){
    if(e.status===401){ _forceLogout(e.error||'セッションが無効です') }
    return null
  }
}

// 定期セッション監視（30秒ごとに /auth/me を叩いて停止・期限切れを検出）
let _sessionWatcherTimer = null
function _startSessionWatcher(){
  if(_sessionWatcherTimer) return  // 重複起動防止
  _sessionWatcherTimer = setInterval(async()=>{
    try {
      const d = await apiRequest('/auth/me')
      if(d.user) setCachedUser(d.user)
    } catch(e){
      // 401 は apiRequest 内の _forceLogout が処理するので何もしない
      // その他のエラー（ネット切断等）は無視して次回に持ち越す
    }
  }, 30_000)  // 30秒
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
    <div style="border:2px solid ${p.color};border-radius:12px;padding:16px;cursor:pointer;margin-bottom:10px;transition:background .15s"
         onmouseenter="this.style.background='rgba(201,168,76,.06)'"
         onmouseleave="this.style.background=''"
         onclick="doUpgrade('${p.key}')">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-family:'Fraunces',serif;font-size:18px;font-weight:900;color:${p.color}">${p.label}</span>
        <span style="font-size:20px;font-weight:700">${p.price}<span style="font-size:12px;color:var(--muted)">/月</span></span>
      </div>
      <div style="margin-top:6px;font-size:13px;color:var(--muted)">${p.limit} · ${p.desc}</div>
      <div style="margin-top:8px;font-size:12px;color:var(--gold2);font-weight:600">→ このプランで始める</div>
    </div>`).join('')
  showModal({
    title:'今月の利用上限に達しました',
    body:`<p style="font-size:13px;color:var(--muted);margin-bottom:16px">プランをアップグレードして制限なしでAIと対話しましょう。会話が増えるほどあなた専用のAIに成長します。</p>${cards}
      <div style="text-align:center"><button class="btn btn-g btn-sm" onclick="payAsYouGo()">¥50で今すぐ1回使う</button></div>`,
    actions:[{label:'キャンセル',fn:'closeModal()',cls:'btn-ghost'}],wide:true
  })
}

// ── Stripe アップグレードフロー（shared: chat.html / plan.html 共通）──────

let _stripeInstance = null
async function _getStripe() {
  if (_stripeInstance) return _stripeInstance
  try {
    const cfg = await fetch('/api/config').then(r => r.json())
    if (cfg.stripe_publishable_key && typeof Stripe !== 'undefined') {
      _stripeInstance = Stripe(cfg.stripe_publishable_key)
    }
  } catch(e) {}
  return _stripeInstance
}

function _updatePlanCache(res) {
  const u = getCachedUser() || {}
  if (res.user) {
    setCachedUser({ ...u, ...res.user })
  } else {
    u.plan = res.plan
    u.usage_limit = res.limit
    u.usage_count = 0
    setCachedUser(u)
  }
}

function doUpgrade(plan) {
  // plan.html上ではchangePlan()があればそちらを使う（確認モーダル付き）
  if (typeof changePlan === 'function') {
    closeModal()
    setTimeout(() => changePlan(plan), 100)
  } else {
    // chat.html等では直接アップグレード処理を実行
    closeModal()
    _doUpgradeDirect(plan)
  }
}

async function _doUpgradeDirect(plan) {
  const info = PLANS[plan]
  if (!info) return
  showModal({
    title: `⬆ ${info.name}にアップグレード`,
    body: `<p style="font-size:13px;color:var(--muted);line-height:1.8">
      月額: <strong>¥${info.price.toLocaleString()}</strong> · 月<strong>${info.limit}回</strong>まで会話可能<br>
      <span style="font-size:12px">✅ 今すぐ適用されます。追加の会話が可能になります。</span>
    </p>`,
    actions: [
      {label:'キャンセル', cls:'btn-g', fn:'closeModal()'},
      {label:`${info.name}に変更する`, cls:'btn-gold', fn:`_applyPlanShared('${plan}')`},
    ]
  })
}

async function _applyPlanShared(plan) {
  const info = PLANS[plan]
  const btn = document.querySelector('.m-foot .btn-gold')
  if (btn) { btn.disabled = true; btn.textContent = '処理中...' }

  try {
    const res = await apiRequest('/user/plan', { method: 'PUT', body: { plan } })

    if (res.requires_payment_method) {
      closeModal()
      await _showCardInputModalShared(plan, res.setup_intent_client_secret, res.customer_id)
      return
    }

    if (res.requires_action) {
      closeModal()
      const stripe = await _getStripe()
      if (!stripe) { toast('Stripe未設定です', 'd'); return }
      const { error } = await stripe.confirmCardPayment(res.payment_intent_client_secret)
      if (error) { toast(error.message || '認証に失敗しました', 'd'); return }
      _updatePlanCache(res)
      toast(`${info.name}プランへのアップグレードが完了しました！`, 's')
      setTimeout(() => location.reload(), 900)
      return
    }

    _updatePlanCache(res)
    closeModal()
    toast(`${info.name}プランへのアップグレードが完了しました！`, 's')
    setTimeout(() => location.reload(), 900)

  } catch(e) {
    closeModal()
    toast(e.error || 'プラン変更に失敗しました', 'd')
  }
}

async function _showCardInputModalShared(plan, clientSecret, customerId) {
  const stripe = await _getStripe()
  if (!stripe) {
    toast('決済システムが利用できません', 'd')
    return
  }
  const info = PLANS[plan]
  showModal({
    title: '💳 お支払い情報の入力',
    wide: true,
    body: `
      <p style="font-size:12.5px;color:var(--muted);margin-bottom:14px;line-height:1.7">
        <strong>${info.name}プラン</strong>（¥${info.price.toLocaleString()}/月）のお支払い情報を入力してください。<br>
        カード情報はStripeによって安全に処理されます。
      </p>
      <div id="stripe-card-element" style="border:1px solid var(--border);border-radius:8px;padding:12px;background:var(--surface);margin-bottom:8px"></div>
      <div id="stripe-card-error" style="color:#ef4444;font-size:12px;min-height:18px;margin-top:4px"></div>
      <div style="font-size:11px;color:var(--muted);margin-top:8px">🔒 SSL暗号化・Stripeによる安全な処理</div>`,
    actions: [
      { label: 'キャンセル', cls: 'btn-g', fn: 'closeModal()' },
      { label: `${info.name}プランを開始する`, cls: 'btn-gold', fn: `_submitCardShared('${plan}','${clientSecret}','${customerId}')` },
    ]
  })
  setTimeout(() => {
    const elements = stripe.elements()
    window._stripeCardElement = elements.create('card', {
      style: { base: { fontSize: '14px', color: '#333', fontFamily: 'inherit' } }
    })
    window._stripeCardElement.mount('#stripe-card-element')
    window._stripeCardElement.on('change', e => {
      const el = document.getElementById('stripe-card-error')
      if (el) el.textContent = e.error ? e.error.message : ''
    })
  }, 100)
}

async function _submitCardShared(plan, clientSecret, customerId) {
  const stripe = await _getStripe()
  const btn = document.querySelector('.m-foot .btn-gold')
  if (btn) { btn.disabled = true; btn.textContent = '処理中...' }
  try {
    const { setupIntent, error } = await stripe.confirmCardSetup(clientSecret, {
      payment_method: { card: window._stripeCardElement }
    })
    if (error) {
      const el = document.getElementById('stripe-card-error')
      if (el) el.textContent = error.message
      if (btn) { btn.disabled = false; btn.textContent = `${PLANS[plan].name}プランを開始する` }
      return
    }
    const res = await apiRequest('/user/plan', {
      method: 'PUT',
      body: { plan, payment_method_id: setupIntent.payment_method }
    })
    if (res.requires_action) {
      const { error: ce } = await stripe.confirmCardPayment(res.payment_intent_client_secret)
      if (ce) { toast(ce.message || '認証に失敗しました', 'd'); closeModal(); return }
    }
    _updatePlanCache(res)
    closeModal()
    toast(`${PLANS[plan].name}プランへのアップグレードが完了しました！`, 's')
    setTimeout(() => location.reload(), 900)
  } catch(e) {
    toast(e.error || '決済に失敗しました', 'd')
    if (btn) { btn.disabled = false; btn.textContent = `${PLANS[plan].name}プランを開始する` }
  }
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
  {id:'dashboard',  icon:'⊞', label:'ダッシュボード',   href:'dashboard.html'},
  {id:'all',        icon:'✦', label:'総合チャット',     href:'chat.html?ai=all'},
  {id:'gourmet',    icon:'🍽️',label:'グルメ AI',        href:'chat.html?ai=gourmet'},
  {id:'travel',     icon:'✈️',label:'旅行 AI',          href:'chat.html?ai=travel'},
  {id:'cooking',    icon:'🍳',label:'料理 AI',          href:'chat.html?ai=cooking'},
  {id:'shopping',   icon:'🛍️',label:'買い物 AI',        href:'chat.html?ai=shopping'},
  {id:'diy',        icon:'🔨',label:'DIY AI',           href:'chat.html?ai=diy'},
  {id:'home',       icon:'📺',label:'家電・インテリア', href:'chat.html?ai=home'},
  {id:'health',     icon:'💚',label:'健康 AI',          href:'chat.html?ai=health'},
  {id:'favorites',  icon:'♥', label:'お気に入り',       href:'favorites.html'},
  {id:'plan',       icon:'◈', label:'プラン',           href:'plan.html'},
  {id:'profile',    icon:'◉', label:'プロフィール',     href:'profile.html'},
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

// ── フォールバックモード（メンテナンス中）バナー管理 ─────────
let _fallbackCheckTimer = null

// ── バナー定義（3段階）────────────────────────────────────────
const _BANNER_CONFIG = {
  warning: {
    bg:   'linear-gradient(135deg,#78350f,#92400e)',  // 茶色
    icon: 'ℹ️',
    text: `<strong>お知らせ:</strong> 現在、一時的にシステムメンテナンスを予定しております。
           サービスに影響が出る可能性がありますが、できる限り通常通りご利用いただけるよう対応いたします。
           ご不便をおかけし申し訳ございません。`,
  },
  critical: {
    bg:   'linear-gradient(135deg,#7f1d1d,#991b1b)',  // 赤
    icon: '🔧',
    text: `<strong>【お知らせ】</strong>
           現在、AIチャット機能は一時的にメンテナンス中です。ご不便をおかけし申し訳ございません。`,
  },
}

const _BANNER_H = 48  // バナーの高さ（px）

function _applyBanner(level){
  // 既存バナーを一旦除去
  const old = document.getElementById('fallback-banner')
  if(old){
    if(old.dataset.level === level) return
    old.remove()
    _adjustLayoutForBanner(false)
  }
  const cfg = _BANNER_CONFIG[level]
  if(!cfg) return

  const banner = document.createElement('div')
  banner.id = 'fallback-banner'
  banner.dataset.level = level
  banner.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:99999',
    `background:${cfg.bg}`,
    'color:#fef3c7', 'font-size:13px', 'font-weight:500',
    'padding:10px 24px', 'text-align:center', 'line-height:1.6',
    'display:flex', 'align-items:center', 'justify-content:center', 'gap:10px',
    'box-shadow:0 2px 12px rgba(0,0,0,.35)',
  ].join(';')
  banner.innerHTML = `
    <span style="font-size:16px;flex-shrink:0">${cfg.icon}</span>
    <span>${cfg.text}</span>
  `
  const insertBanner = () => {
    document.body.appendChild(banner)
    _adjustLayoutForBanner(true)
  }
  if(document.body) insertBanner()
  else document.addEventListener('DOMContentLoaded', insertBanner, {once:true})
}

function _adjustLayoutForBanner(show){
  // バナー分だけ各レイアウト要素をずらす
  const h = show ? _BANNER_H : 0
  // main-header（sticky top:0 を補正）
  const header = document.querySelector('.main-header')
  if(header) header.style.top = h + 'px'
  // chat-shell の高さを補正（バナー分だけ縮める）
  const chatShell = document.querySelector('.chat-shell')
  if(chatShell) chatShell.style.height = `calc(100vh - var(--hh) - ${h}px)`
  // モバイルヘッダーも補正
  const mobileHeader = document.getElementById('mobile-header')
  if(mobileHeader) mobileHeader.style.top = h + 'px'
  // body の padding-top で他ページのスクロール基点を補正
  document.body.style.paddingTop = h ? h + 'px' : ''
}

function showFallbackBanner(){
  // 後方互換: critical レベルで表示
  _applyBanner('critical')
}

function hideFallbackBanner(){
  const banner = document.getElementById('fallback-banner')
  if(banner){
    banner.remove()
    _adjustLayoutForBanner(false)
  }
}

async function checkFallbackMode(){
  try {
    const d = await fetch('/api/system/status').then(r=>r.json())
    if(d.fallback_mode || d.budget_warning === 'critical'){
      _applyBanner('critical')
    } else if(d.budget_warning === 'warning'){
      _applyBanner('warning')
    } else {
      hideFallbackBanner()
    }
  } catch(e) { /* ネットワークエラーは無視 */ }
}

function startFallbackWatcher(){
  if(_fallbackCheckTimer) return
  checkFallbackMode()  // 即時チェック
  // 60秒ごとに確認（復旧を自動検知）
  _fallbackCheckTimer = setInterval(checkFallbackMode, 60_000)
}

// ページロード直後に認証不要でフォールバックモードをチェック
// requireAuth()を待たずにバナーを表示できる
document.addEventListener('DOMContentLoaded', ()=>{
  // admin-* ページは admin-shared.js が担当するのでスキップ
  if(!location.pathname.includes('admin')) {
    checkFallbackMode()
  }
})
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
