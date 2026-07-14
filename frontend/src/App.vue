<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, session } from './api'

const user = ref(null)
const hardware = ref([])
const users = ref([])
const audit = ref(null)
const view = ref('inventory')
const busy = ref(false)
const notice = reactive({ text: '', kind: 'success' })
const filters = reactive({ search: '', status: 'All', sort: 'name' })
const loginForm = reactive({ email: 'admin@booksy.com', password: 'Admin123!' })
const deviceForm = reactive({ name: '', brand: '', purchase_date: '', status: 'Available', notes: '' })
const userForm = reactive({ name: '', email: '', password: '', role: 'user' })

const nav = computed(() => [
  { id: 'inventory', label: 'Hardware list', icon: '▦' },
  { id: 'rentals', label: 'My rentals', icon: '↗' },
  { id: 'audit', label: 'AI inventory audit', icon: '✦' },
  ...(user.value?.role === 'admin' ? [{ id: 'admin', label: 'Admin panel', icon: '⚙' }] : []),
])

const shownHardware = computed(() => {
  const term = filters.search.trim().toLowerCase()
  return [...hardware.value]
    .filter((item) => filters.status === 'All' || item.status === filters.status)
    .filter((item) => !term || `${item.name} ${item.brand} ${item.notes || ''}`.toLowerCase().includes(term))
    .sort((a, b) => String(a[filters.sort] || '').localeCompare(String(b[filters.sort] || '')))
})

const myRentals = computed(() => hardware.value.filter((item) => item.assigned_to === user.value?.email))
const stats = computed(() => ({
  total: hardware.value.length,
  available: hardware.value.filter((item) => item.status === 'Available' && !item.is_damaged).length,
  inUse: hardware.value.filter((item) => item.status === 'In Use').length,
  attention: hardware.value.filter((item) => item.status === 'Repair' || item.is_damaged).length,
}))

function flash(text, kind = 'success') {
  notice.text = text
  notice.kind = kind
  window.setTimeout(() => { if (notice.text === text) notice.text = '' }, 4000)
}

async function loadHardware() {
  hardware.value = await api('/hardware')
}

async function restoreSession() {
  if (!session.token) return
  try {
    user.value = await api('/auth/me')
    await loadHardware()
  } catch {
    session.token = null
  }
}

async function login() {
  busy.value = true
  try {
    const result = await api('/auth/login', { method: 'POST', body: JSON.stringify(loginForm) })
    session.token = result.access_token
    user.value = result.user
    await loadHardware()
  } catch (error) {
    flash(error.message, 'error')
  } finally {
    busy.value = false
  }
}

function logout() {
  session.token = null
  user.value = null
  hardware.value = []
  audit.value = null
  view.value = 'inventory'
}

async function act(path, success) {
  busy.value = true
  try {
    await api(path, { method: 'POST' })
    await loadHardware()
    flash(success)
  } catch (error) {
    flash(error.message, 'error')
  } finally {
    busy.value = false
  }
}

async function runAudit() {
  busy.value = true
  try {
    audit.value = await api('/audit', { method: 'POST' })
  } catch (error) {
    flash(error.message, 'error')
  } finally {
    busy.value = false
  }
}

async function openView(next) {
  view.value = next
  if (next === 'admin' && !users.value.length) users.value = await api('/users')
  if (next === 'audit' && !audit.value) await runAudit()
}

async function addDevice() {
  busy.value = true
  try {
    await api('/hardware', { method: 'POST', body: JSON.stringify({ ...deviceForm, purchase_date: deviceForm.purchase_date || null, notes: deviceForm.notes || null }) })
    Object.assign(deviceForm, { name: '', brand: '', purchase_date: '', status: 'Available', notes: '' })
    await loadHardware()
    flash('Hardware added')
  } catch (error) { flash(error.message, 'error') } finally { busy.value = false }
}

async function addUser() {
  busy.value = true
  try {
    await api('/users', { method: 'POST', body: JSON.stringify(userForm) })
    Object.assign(userForm, { name: '', email: '', password: '', role: 'user' })
    users.value = await api('/users')
    flash('Account created')
  } catch (error) { flash(error.message, 'error') } finally { busy.value = false }
}

async function repair(item) {
  let body = {}
  if (item.status === 'Repair' && item.is_damaged) {
    const resolutionNote = window.prompt('Describe the completed repair (required to clear the safety hold):')
    if (resolutionNote === null) return
    body = { resolve_damage: true, resolution_note: resolutionNote }
  }
  try {
    await api(`/hardware/${item.id}/repair`, { method: 'PATCH', body: JSON.stringify(body) })
    await loadHardware()
    flash(item.status === 'Repair' ? 'Repair completed' : 'Marked for repair')
  } catch (error) { flash(error.message, 'error') }
}

async function removeDevice(item) {
  if (!window.confirm(`Delete ${item.name}?`)) return
  try {
    await api(`/hardware/${item.id}`, { method: 'DELETE' })
    await loadHardware()
    flash('Hardware deleted')
  } catch (error) { flash(error.message, 'error') }
}

function statusClass(item) {
  if (item.is_damaged) return 'danger'
  return { Available: 'available', 'In Use': 'in-use', Repair: 'repair' }[item.status]
}

function severityIcon(level) {
  return { critical: '!', high: '!', medium: '△', low: 'i' }[level] || 'i'
}

onMounted(restoreSession)
</script>

<template>
  <div v-if="notice.text" class="toast" :class="notice.kind">{{ notice.text }}</div>

  <main v-if="!user" class="login-page">
    <section class="login-story">
      <div class="brand brand-light"><span class="brand-mark">H</span><span>Hardware Hub</span></div>
      <div class="story-copy">
        <span class="eyebrow">Booksy internal tools</span>
        <h1>The right gear.<br><em>Ready when you are.</em></h1>
        <p>Rent, return and care for company hardware from one thoughtful workspace.</p>
      </div>
      <div class="story-foot">Secure equipment operations · Warsaw</div>
    </section>
    <section class="login-panel">
      <form class="login-card" @submit.prevent="login">
        <div class="mobile-brand brand"><span class="brand-mark">H</span><span>Hardware Hub</span></div>
        <span class="kicker">Welcome back</span>
        <h2>Sign in to your account</h2>
        <p class="muted">Use an account created by your administrator.</p>
        <label>Work email<input v-model="loginForm.email" type="email" autocomplete="email" required></label>
        <label>Password<input v-model="loginForm.password" type="password" autocomplete="current-password" minlength="8" required></label>
        <button class="button primary full" :disabled="busy">{{ busy ? 'Signing in…' : 'Sign in' }} <span>→</span></button>
        <p class="demo-hint">Demo admin: admin@booksy.com · Admin123!</p>
      </form>
    </section>
  </main>

  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark">H</span><span>Hardware Hub</span></div>
      <nav>
        <button v-for="item in nav" :key="item.id" :class="{ active: view === item.id }" @click="openView(item.id)">
          <span class="nav-icon">{{ item.icon }}</span>{{ item.label }}
        </button>
      </nav>
      <div class="profile">
        <span class="avatar">{{ user.name.split(' ').map((part) => part[0]).join('').slice(0, 2) }}</span>
        <div><strong>{{ user.name }}</strong><small>{{ user.role }}</small></div>
        <button class="logout" title="Log out" @click="logout">↪</button>
      </div>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div><span class="eyebrow">Operations / {{ view }}</span><h1>{{ nav.find((item) => item.id === view)?.label }}</h1></div>
        <div class="top-actions"><span class="live-dot"></span><span>Inventory live</span><button class="icon-button" @click="loadHardware">↻</button></div>
      </header>

      <div v-if="view === 'inventory'" class="content">
        <section class="hero-row">
          <div><span class="kicker">Inventory overview</span><h2>Everything your team needs,<br><em>accounted for.</em></h2></div>
          <button class="button ghost" @click="openView('audit')">✦ Run AI audit</button>
        </section>
        <section class="stats-grid">
          <article><span>Total hardware</span><strong>{{ stats.total }}</strong><small>Accepted inventory</small></article>
          <article><span>Ready to rent</span><strong>{{ stats.available }}</strong><small class="positive">Available now</small></article>
          <article><span>In use</span><strong>{{ stats.inUse }}</strong><small>With team members</small></article>
          <article><span>Needs attention</span><strong>{{ stats.attention }}</strong><small class="negative">Repair or damage</small></article>
        </section>
        <section class="card inventory-card">
          <div class="card-head"><div><h3>Hardware inventory</h3><p>{{ shownHardware.length }} items shown</p></div></div>
          <div class="filters">
            <label class="search"><span>⌕</span><input v-model="filters.search" placeholder="Search hardware or brand…"></label>
            <select v-model="filters.status"><option>All</option><option>Available</option><option>In Use</option><option>Repair</option></select>
            <select v-model="filters.sort"><option value="name">Sort: name</option><option value="brand">Sort: brand</option><option value="purchase_date">Sort: purchase date</option><option value="status">Sort: status</option></select>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Device</th><th>Brand</th><th>Purchased</th><th>Status</th><th>Assigned to</th><th></th></tr></thead>
              <tbody>
                <tr v-for="item in shownHardware" :key="item.id">
                  <td><div class="device-cell"><span class="device-icon">{{ item.name.includes('Mac') || item.name.includes('Dell') ? '▰' : item.name.includes('Phone') || item.name.includes('Galaxy') ? '▯' : '◇' }}</span><div><strong>{{ item.name }}</strong><small>#{{ String(item.id).padStart(3, '0') }}<span v-if="item.is_damaged" class="damage-note"> · safety hold</span></small></div></div></td>
                  <td>{{ item.brand }}</td><td>{{ item.purchase_date || '—' }}</td>
                  <td><span class="status" :class="statusClass(item)"><i></i>{{ item.is_damaged ? 'Damaged' : item.status }}</span></td>
                  <td class="muted-cell">{{ item.assigned_to || '—' }}</td>
                  <td class="align-right"><button v-if="item.status === 'Available'" class="button small" :disabled="item.is_damaged || busy" @click="act(`/hardware/${item.id}/rent`, `${item.name} rented`) ">Rent</button><button v-else-if="item.status === 'In Use' && (item.assigned_to === user.email || user.role === 'admin')" class="button small secondary" :disabled="busy" @click="act(`/hardware/${item.id}/return`, `${item.name} returned`)">Return</button><span v-else class="unavailable">Unavailable</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <div v-else-if="view === 'rentals'" class="content narrow">
        <section class="hero-row"><div><span class="kicker">Your workspace</span><h2>Gear currently<br><em>in your care.</em></h2></div></section>
        <section class="rental-grid">
          <article v-for="item in myRentals" :key="item.id" class="card rental-card"><span class="device-icon large">▰</span><div><small>{{ item.brand }}</small><h3>{{ item.name }}</h3><p>Rented to {{ user.email }}</p></div><button class="button primary" @click="act(`/hardware/${item.id}/return`, `${item.name} returned`)">Return hardware</button></article>
          <article v-if="!myRentals.length" class="empty card"><span>◇</span><h3>No active rentals</h3><p>Available hardware is waiting in the inventory.</p><button class="button" @click="view = 'inventory'">Browse inventory</button></article>
        </section>
      </div>

      <div v-else-if="view === 'audit'" class="content audit-page">
        <section class="audit-hero">
          <div><span class="kicker light">AI-native layer</span><h2>Inventory intelligence,<br><em>with receipts.</em></h2><p>Every finding is grounded in accepted inventory or preserved seed-import evidence.</p></div>
          <button class="button light" :disabled="busy" @click="runAudit">{{ busy ? 'Auditing…' : '✦ Run again' }}</button>
        </section>
        <section v-if="audit" class="audit-summary">
          <div><span>Audit mode</span><strong>{{ audit.mode === 'rules+llm' ? 'Rules + OpenRouter' : 'Deterministic safety floor' }}</strong><small>{{ audit.llm_status.message }}</small></div>
          <div><span>Total findings</span><strong>{{ audit.summary.total }}</strong></div>
          <div><span>Critical</span><strong class="critical-text">{{ audit.summary.critical }}</strong></div>
          <div><span>Guarded drops</span><strong>{{ audit.hallucination_guard.dropped_unknown_ids + audit.hallucination_guard.dropped_rule_duplicates }}</strong><small>Unknown IDs + duplicates</small></div>
        </section>
        <section v-if="audit" class="findings">
          <article v-for="(finding, index) in audit.findings" :key="index" class="finding card" :class="finding.severity">
            <span class="finding-icon">{{ severityIcon(finding.severity) }}</span>
            <div><div class="finding-meta"><span>{{ finding.severity }}</span><small>{{ finding.source }} · ID {{ finding.hardware_id ?? 'n/a' }}</small></div><h3>{{ finding.title }}</h3><p>{{ finding.explanation }}</p><code>{{ typeof finding.evidence === 'string' ? finding.evidence : `${finding.evidence.name || 'Unknown record'} · ${finding.evidence.status || 'no status'}` }}</code></div>
          </article>
        </section>
      </div>

      <div v-else-if="view === 'admin'" class="content admin-page">
        <section class="hero-row"><div><span class="kicker">Command center</span><h2>Manage the fleet.<br><em>Protect the team.</em></h2></div></section>
        <section class="admin-grid">
          <form class="card form-card" @submit.prevent="addDevice"><div class="card-head"><div><h3>Add hardware</h3><p>Create a new inventory record</p></div><span class="step">01</span></div><div class="form-grid"><label>Device name<input v-model="deviceForm.name" required placeholder="MacBook Pro 16"></label><label>Brand<input v-model="deviceForm.brand" required placeholder="Apple"></label><label>Purchase date<input v-model="deviceForm.purchase_date" type="date"></label><label>Status<select v-model="deviceForm.status"><option>Available</option><option>Repair</option></select></label><label class="span-2">Notes<textarea v-model="deviceForm.notes" placeholder="Condition or service notes"></textarea></label></div><button class="button primary" :disabled="busy">Add hardware →</button></form>
          <form class="card form-card" @submit.prevent="addUser"><div class="card-head"><div><h3>Create account</h3><p>Accounts are admin-issued only</p></div><span class="step">02</span></div><div class="form-grid"><label>Full name<input v-model="userForm.name" required placeholder="Jamie Doe"></label><label>Work email<input v-model="userForm.email" required type="email" placeholder="j.doe@booksy.com"></label><label>Password<input v-model="userForm.password" required type="password" minlength="8" placeholder="Minimum 8 characters"></label><label>Role<select v-model="userForm.role"><option value="user">User</option><option value="admin">Admin</option></select></label></div><button class="button primary" :disabled="busy">Create account →</button></form>
        </section>
        <section class="card manage-card"><div class="card-head"><div><h3>Fleet controls</h3><p>Repair and deletion actions are guarded by current state</p></div></div><div class="manage-list"><div v-for="item in hardware" :key="item.id" class="manage-row"><div class="device-cell"><span class="device-icon">◇</span><div><strong>{{ item.name }}</strong><small>{{ item.brand }} · {{ item.status }}</small></div></div><div><button class="button small secondary" @click="repair(item)">{{ item.status === 'Repair' ? 'Complete repair' : 'Send to repair' }}</button><button class="text-button danger-text" @click="removeDevice(item)">Delete</button></div></div></div></section>
        <section class="card manage-card"><div class="card-head"><div><h3>Accounts</h3><p>{{ users.length }} authorized users</p></div></div><div class="manage-list"><div v-for="account in users" :key="account.id" class="manage-row"><div class="device-cell"><span class="avatar mini">{{ account.name.slice(0, 2).toUpperCase() }}</span><div><strong>{{ account.name }}</strong><small>{{ account.email }}</small></div></div><span class="role-badge">{{ account.role }}</span></div></div></section>
      </div>
    </section>
  </div>
</template>
