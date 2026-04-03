# Component Snippets

Copy-paste-ready HTML/CSS building blocks for screen content. All visual properties use CSS custom properties from `snippets-variables.md`.

> **Usage**: Pick components needed per screen. Paste into the `.page-body` area of a layout from `snippets-layout.md`. Customize content (labels, data, field names) per screen.

---

## Data Table

Use for: User lists, orders, products, transactions, logs, any tabular data.

### HTML

```html
<div class="table-container">
  <div class="table-toolbar">
    <div class="table-search">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" placeholder="Search {{ITEMS}}..." class="table-search-input">
    </div>
    <div class="table-filters">
      <select class="filter-select">
        <option>All {{FILTER_NAME}}</option>
        <option>{{OPTION_1}}</option>
        <option>{{OPTION_2}}</option>
      </select>
      <!-- Add more filter selects as needed -->
    </div>
    <button class="btn btn-primary btn-sm">+ Add {{ITEM}}</button>
  </div>

  <table class="data-table">
    <thead>
      <tr>
        <th><input type="checkbox" class="row-check"></th>
        <th>{{COL_1}}</th>
        <th>{{COL_2}}</th>
        <th>{{COL_3}}</th>
        <th>{{COL_4}}</th>
        <th>Status</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      <!-- Repeat <tr> with realistic data for 5-8 rows -->
      <tr>
        <td><input type="checkbox" class="row-check"></td>
        <td class="cell-primary">{{VALUE}}</td>
        <td>{{VALUE}}</td>
        <td>{{VALUE}}</td>
        <td>{{VALUE}}</td>
        <td><span class="badge badge-success">{{STATUS}}</span></td>
        <td>
          <button class="icon-btn" aria-label="More actions">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/></svg>
          </button>
        </td>
      </tr>
    </tbody>
  </table>

  <div class="table-footer">
    <span class="table-info">Showing 1-10 of {{TOTAL}} {{ITEMS}}</span>
    <div class="pagination">
      <button class="btn btn-ghost btn-sm" disabled>&laquo; Prev</button>
      <button class="btn btn-sm page-btn active">1</button>
      <button class="btn btn-ghost btn-sm page-btn">2</button>
      <button class="btn btn-ghost btn-sm page-btn">3</button>
      <button class="btn btn-ghost btn-sm">Next &raquo;</button>
    </div>
  </div>
</div>
```

### CSS

```css
.table-container {
  background: var(--color-surface);
  border: var(--card-border);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--card-shadow);
  overflow: hidden;
}
.table-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
  flex-wrap: wrap;
}
.table-search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 6px 12px;
  color: var(--color-muted);
  flex: 1;
  min-width: 200px;
  max-width: 320px;
}
.table-search-input {
  border: none;
  background: none;
  outline: none;
  width: 100%;
  font-size: var(--font-size-sm);
}
.table-filters { display: flex; gap: 8px; }
.filter-select {
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  font-size: var(--font-size-sm);
  color: var(--color-text);
  cursor: pointer;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
}
.data-table th {
  text-align: left;
  padding: 10px 16px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-muted);
  background: var(--color-table-header, var(--color-bg));
  border-bottom: 1px solid var(--color-border);
}
.data-table td {
  padding: 12px 16px;
  font-size: var(--font-size-sm);
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}
.data-table tbody tr:hover { background: var(--color-hover); }
.data-table tbody tr:last-child td { border-bottom: none; }
.cell-primary { font-weight: 500; color: var(--color-text); }
.row-check { accent-color: var(--color-primary); cursor: pointer; }
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border);
  font-size: 13px;
  color: var(--color-muted);
}
.pagination { display: flex; gap: 4px; }
.page-btn.active {
  background: var(--color-primary);
  color: var(--color-on-primary);
  border-color: var(--color-primary);
}
```

---

## Card Grid

Use for: Dashboards, product catalogs, project lists, content cards.

### HTML

```html
<div class="card-grid">
  <!-- Repeat .card for each item -->
  <div class="card">
    <div class="card-img" style="background-image: url('{{IMAGE_URL_OR_PLACEHOLDER}}')"></div>
    <!-- Or without image: remove .card-img -->
    <div class="card-body">
      <div class="card-meta">
        <span class="badge badge-info">{{CATEGORY}}</span>
        <span class="card-date">{{DATE}}</span>
      </div>
      <h3 class="card-title">{{TITLE}}</h3>
      <p class="card-desc">{{DESCRIPTION}}</p>
    </div>
    <div class="card-footer">
      <div class="card-author">
        <div class="avatar avatar-sm">{{INITIALS}}</div>
        <span>{{AUTHOR}}</span>
      </div>
      <button class="btn btn-ghost btn-sm">View</button>
    </div>
  </div>
</div>
```

### CSS

```css
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}
.card {
  background: var(--color-surface);
  border: var(--card-border);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--card-shadow);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.15s;
}
.card:hover { box-shadow: var(--card-shadow-hover, 0 4px 12px rgba(0,0,0,0.1)); }
.card-img {
  height: 160px;
  background-size: cover;
  background-position: center;
  background-color: var(--color-bg);
}
.card-body { padding: 16px; flex: 1; }
.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--color-muted);
}
.card-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin-bottom: 6px;
}
.card-desc {
  font-size: var(--font-size-sm);
  color: var(--color-muted);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border);
}
.card-author {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-muted);
}

@media (max-width: 640px) {
  .card-grid { grid-template-columns: 1fr; }
}
```

---

## Stats Row

Use for: Dashboard metrics, KPI summaries, overview numbers.

### HTML

```html
<div class="stats-row">
  <!-- Repeat .stat-card for each metric -->
  <div class="stat-card">
    <div class="stat-header">
      <span class="stat-label">{{METRIC_NAME}}</span>
      <span class="stat-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">{{ICON_PATH}}</svg>
      </span>
    </div>
    <div class="stat-value">{{VALUE}}</div>
    <div class="stat-trend trend-up">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m18 15-6-6-6 6"/></svg>
      <span>{{PERCENT}}% vs last month</span>
    </div>
  </div>
</div>
```

### CSS

```css
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}
.stat-card {
  background: var(--color-surface);
  border: var(--card-border);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--card-shadow);
  padding: 20px;
}
.stat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.stat-label {
  font-size: var(--font-size-sm);
  color: var(--color-muted);
  font-weight: 500;
}
.stat-icon { color: var(--color-muted); }
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.2;
  margin-bottom: 8px;
}
.stat-trend {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
}
.trend-up { color: var(--color-success); }
.trend-down { color: var(--color-error); }

@media (max-width: 640px) {
  .stats-row { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 400px) {
  .stats-row { grid-template-columns: 1fr; }
}
```

---

## Form

Use for: Create/edit screens, settings, profile, onboarding steps.

### HTML

```html
<div class="form-container">
  <form class="form">
    <div class="form-section">
      <h3 class="form-section-title">{{SECTION_TITLE}}</h3>
      <p class="form-section-desc">{{SECTION_DESCRIPTION}}</p>

      <div class="form-grid">
        <!-- Full-width field -->
        <div class="field full">
          <label class="field-label">{{LABEL}} <span class="required">*</span></label>
          <input type="text" class="field-input" placeholder="{{PLACEHOLDER}}" value="{{VALUE}}">
          <span class="field-hint">{{HINT_TEXT}}</span>
        </div>

        <!-- Half-width fields (side by side) -->
        <div class="field">
          <label class="field-label">{{LABEL}}</label>
          <input type="text" class="field-input" placeholder="{{PLACEHOLDER}}">
        </div>
        <div class="field">
          <label class="field-label">{{LABEL}}</label>
          <select class="field-input">
            <option>{{OPTION_1}}</option>
            <option>{{OPTION_2}}</option>
          </select>
        </div>

        <!-- Textarea -->
        <div class="field full">
          <label class="field-label">{{LABEL}}</label>
          <textarea class="field-input field-textarea" rows="4" placeholder="{{PLACEHOLDER}}"></textarea>
        </div>

        <!-- Toggle -->
        <div class="field full">
          <label class="toggle-row">
            <div>
              <div class="field-label" style="margin-bottom:2px">{{TOGGLE_LABEL}}</div>
              <div class="field-hint">{{TOGGLE_DESCRIPTION}}</div>
            </div>
            <div class="toggle">
              <input type="checkbox" class="toggle-input" checked>
              <span class="toggle-slider"></span>
            </div>
          </label>
        </div>
      </div>
    </div>

    <!-- Repeat .form-section for more sections -->

    <div class="form-actions">
      <button type="button" class="btn btn-secondary">Cancel</button>
      <button type="submit" class="btn btn-primary">Save Changes</button>
    </div>
  </form>
</div>
```

### CSS

```css
.form-container {
  background: var(--color-surface);
  border: var(--card-border);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--card-shadow);
  padding: 24px;
}
.form-section { margin-bottom: 32px; }
.form-section-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  margin-bottom: 4px;
}
.form-section-desc {
  font-size: var(--font-size-sm);
  color: var(--color-muted);
  margin-bottom: 20px;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.field.full { grid-column: 1 / -1; }
.field-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--color-text);
}
.required { color: var(--color-error); }
.field-input {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-bg);
  font-size: var(--font-size-sm);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.field-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-ring, rgba(37,99,235,0.1));
}
.field-textarea { resize: vertical; min-height: 80px; }
.field-hint {
  display: block;
  font-size: 12px;
  color: var(--color-muted);
  margin-top: 4px;
}
.field-error .field-input { border-color: var(--color-error); }
.field-error .field-hint { color: var(--color-error); }
.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  cursor: pointer;
}
.toggle {
  position: relative;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}
.toggle-input {
  opacity: 0;
  width: 0;
  height: 0;
  position: absolute;
}
.toggle-slider {
  position: absolute;
  inset: 0;
  background: var(--color-border);
  border-radius: 12px;
  transition: background 0.2s;
}
.toggle-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  bottom: 3px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}
.toggle-input:checked + .toggle-slider { background: var(--color-primary); }
.toggle-input:checked + .toggle-slider::before { transform: translateX(20px); }
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 24px;
  border-top: 1px solid var(--color-border);
}

@media (max-width: 640px) {
  .form-grid { grid-template-columns: 1fr; }
  .field.full { grid-column: auto; }
}
```

---

## Modal / Dialog

Use for: Confirmation dialogs, quick-create forms, detail popups.

### HTML

```html
<!-- Add at end of <body>, before closing </body> -->
<div class="modal-overlay" id="modal">
  <div class="modal">
    <div class="modal-header">
      <h3>{{MODAL_TITLE}}</h3>
      <button class="icon-btn" aria-label="Close">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
      </button>
    </div>
    <div class="modal-body">
      <p>{{MODAL_CONTENT}}</p>
      <!-- Or paste form fields here -->
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary">Cancel</button>
      <button class="btn btn-primary">{{CONFIRM_LABEL}}</button>
    </div>
  </div>
</div>
```

### CSS

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 24px;
}
.modal {
  background: var(--color-surface);
  border-radius: var(--radius-lg, 12px);
  box-shadow: 0 20px 60px rgba(0,0,0,0.15);
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 0;
}
.modal-header h3 {
  font-size: var(--font-size-lg);
  font-weight: 600;
}
.modal-body {
  padding: 16px 24px;
  font-size: var(--font-size-sm);
  color: var(--color-muted);
  line-height: 1.6;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 24px 20px;
}
```

---

## Tabs

Use for: Settings pages, detail views with multiple sections, content tabs.

### HTML

```html
<div class="tabs-container">
  <div class="tabs-nav">
    <button class="tab active">{{TAB_1}}</button>
    <button class="tab">{{TAB_2}}</button>
    <button class="tab">{{TAB_3}}</button>
  </div>
  <div class="tab-content">
    <!-- Content for active tab -->
  </div>
</div>
```

### CSS

```css
.tabs-container {
  background: var(--color-surface);
  border: var(--card-border);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--card-shadow);
  overflow: hidden;
}
.tabs-nav {
  display: flex;
  border-bottom: 1px solid var(--color-border);
  padding: 0 16px;
  overflow-x: auto;
}
.tab {
  padding: 12px 16px;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s;
}
.tab:hover { color: var(--color-text); }
.tab.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}
.tab-content { padding: 24px; }
```

---

## Badges

Use inline for: Status indicators, labels, categories.

### HTML

```html
<span class="badge badge-success">Active</span>
<span class="badge badge-warning">Pending</span>
<span class="badge badge-error">Expired</span>
<span class="badge badge-info">New</span>
<span class="badge badge-neutral">Draft</span>
```

### CSS

```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 999px;
  white-space: nowrap;
}
.badge-success { background: #ecfdf5; color: #059669; }
.badge-warning { background: #fef3c7; color: #92400e; }
.badge-error { background: #fef2f2; color: #dc2626; }
.badge-info { background: #eff6ff; color: #2563eb; }
.badge-neutral { background: var(--color-bg); color: var(--color-muted); }
```

---

## Empty State

Use for: Tables, lists, or grids with no data.

### HTML

```html
<div class="empty-state">
  <div class="empty-icon">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">{{ICON_PATH}}</svg>
  </div>
  <h3 class="empty-title">{{TITLE}}</h3>
  <p class="empty-desc">{{DESCRIPTION}}</p>
  <button class="btn btn-primary">{{CTA_LABEL}}</button>
</div>
```

### CSS

```css
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}
.empty-icon { margin-bottom: 16px; color: var(--color-muted); }
.empty-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  margin-bottom: 8px;
}
.empty-desc {
  font-size: var(--font-size-sm);
  color: var(--color-muted);
  max-width: 360px;
  margin-bottom: 20px;
}
```

---

## Breadcrumbs

Use at top of detail/sub-pages.

### HTML

```html
<nav class="breadcrumbs">
  <a href="#" class="breadcrumb-link">{{PARENT}}</a>
  <span class="breadcrumb-sep">/</span>
  <a href="#" class="breadcrumb-link">{{SECTION}}</a>
  <span class="breadcrumb-sep">/</span>
  <span class="breadcrumb-current">{{CURRENT}}</span>
</nav>
```

### CSS

```css
.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  margin-bottom: 16px;
}
.breadcrumb-link { color: var(--color-muted); text-decoration: none; }
.breadcrumb-link:hover { color: var(--color-primary); text-decoration: underline; }
.breadcrumb-sep { color: var(--color-border); }
.breadcrumb-current { color: var(--color-text); font-weight: 500; }
```

---

## Detail Layout

Use for: Single-item detail views (user profile, order detail, product detail).

### HTML

```html
<div class="detail-layout">
  <div class="detail-main">
    <!-- Primary content sections -->
    <div class="detail-section">
      <h3>{{SECTION_TITLE}}</h3>
      <div class="detail-fields">
        <div class="detail-field">
          <span class="detail-label">{{LABEL}}</span>
          <span class="detail-value">{{VALUE}}</span>
        </div>
        <div class="detail-field">
          <span class="detail-label">{{LABEL}}</span>
          <span class="detail-value">{{VALUE}}</span>
        </div>
      </div>
    </div>
  </div>
  <div class="detail-sidebar">
    <!-- Sidebar with actions or metadata -->
    <div class="detail-section">
      <h3>Actions</h3>
      <div class="detail-actions">
        <button class="btn btn-primary" style="width:100%">{{PRIMARY_ACTION}}</button>
        <button class="btn btn-secondary" style="width:100%">{{SECONDARY_ACTION}}</button>
      </div>
    </div>
  </div>
</div>
```

### CSS

```css
.detail-layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 24px;
  align-items: start;
}
.detail-main, .detail-sidebar {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.detail-section {
  background: var(--color-surface);
  border: var(--card-border);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--card-shadow);
  padding: 20px;
}
.detail-section h3 {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border);
}
.detail-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.detail-label {
  display: block;
  font-size: 12px;
  color: var(--color-muted);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 500;
}
.detail-value {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text);
}
.detail-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

@media (max-width: 900px) {
  .detail-layout { grid-template-columns: 1fr; }
}
```

---

## Notification List

Use for: Notification center, activity feed, message list.

### HTML

```html
<div class="notification-list">
  <!-- Repeat .notif-item -->
  <div class="notif-item unread">
    <div class="notif-dot"></div>
    <div class="notif-icon">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">{{ICON_PATH}}</svg>
    </div>
    <div class="notif-content">
      <div class="notif-text"><strong>{{ACTOR}}</strong> {{ACTION}} <strong>{{OBJECT}}</strong></div>
      <div class="notif-time">{{TIME_AGO}}</div>
    </div>
  </div>
</div>
```

### CSS

```css
.notification-list {
  background: var(--color-surface);
  border: var(--card-border);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--card-shadow);
  overflow: hidden;
}
.notif-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border);
  position: relative;
}
.notif-item:last-child { border-bottom: none; }
.notif-item:hover { background: var(--color-hover); }
.notif-item.unread { background: var(--color-bg); }
.notif-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
  flex-shrink: 0;
  margin-top: 6px;
  display: none;
}
.notif-item.unread .notif-dot { display: block; }
.notif-icon {
  color: var(--color-muted);
  flex-shrink: 0;
  margin-top: 2px;
}
.notif-content { flex: 1; min-width: 0; }
.notif-text {
  font-size: var(--font-size-sm);
  color: var(--color-text);
  line-height: 1.5;
}
.notif-time {
  font-size: 12px;
  color: var(--color-muted);
  margin-top: 2px;
}
```
