# Layout Snippets

Copy-paste-ready HTML/CSS building blocks for screen layouts. All visual properties use CSS custom properties — set once per project via `snippets-variables.md`.

> **Usage**: Pick ONE layout per screen. Wrap it with the Page Shell. Fill the content area with components from `snippets-components.md`.

---

## Page Shell

Every screen starts with this. Set the `--` variables from `snippets-variables.md`, then paste the layout inside `<body>`.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{SCREEN_TITLE}}</title>
  <link href="https://fonts.googleapis.com/css2?family={{FONT_FAMILY}}:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    /* === PASTE :root VARIABLES FROM snippets-variables.md === */

    /* === Reset === */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: var(--font-family);
      font-size: var(--font-size-base);
      line-height: 1.5;
      color: var(--color-text);
      background: var(--color-bg);
      -webkit-font-smoothing: antialiased;
    }
    a { color: var(--color-primary); text-decoration: none; }
    a:hover { text-decoration: underline; }
    img { max-width: 100%; display: block; }
    button, input, select, textarea { font: inherit; color: inherit; }
    h1, h2, h3, h4 { line-height: 1.2; font-weight: var(--font-weight-heading); }
    h1 { font-size: var(--font-size-h1); }
    h2 { font-size: var(--font-size-h2); }
    h3 { font-size: var(--font-size-h3); }

    /* === PASTE LAYOUT CSS BELOW === */
    /* === PASTE COMPONENT CSS BELOW === */
  </style>
</head>
<body>
  <!-- PASTE LAYOUT HTML HERE -->
</body>
</html>
```

---

## Layout A: Sidebar + Content

Use for: Dashboards, admin panels, settings, list views, detail views.

### HTML

```html
<div class="app-layout">
  <aside class="sidebar">
    <div class="sidebar-logo">
      <span class="logo-icon">{{LOGO_ICON_OR_SVG}}</span>
      <span class="logo-text">{{APP_NAME}}</span>
    </div>
    <nav class="sidebar-nav">
      <!-- Repeat .nav-item for each menu entry -->
      <a href="#" class="nav-item active">
        <svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{{ICON_PATH}}</svg>
        <span>{{NAV_LABEL}}</span>
      </a>
      <a href="#" class="nav-item">
        <svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{{ICON_PATH}}</svg>
        <span>{{NAV_LABEL}}</span>
      </a>
      <!-- Optional: section divider -->
      <div class="nav-divider"></div>
      <span class="nav-section-label">{{SECTION_LABEL}}</span>
      <a href="#" class="nav-item">
        <svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{{ICON_PATH}}</svg>
        <span>{{NAV_LABEL}}</span>
      </a>
    </nav>
    <div class="sidebar-footer">
      <div class="user-info">
        <div class="avatar">{{USER_INITIALS}}</div>
        <div class="user-details">
          <div class="user-name">{{USER_NAME}}</div>
          <div class="user-role">{{USER_ROLE}}</div>
        </div>
      </div>
    </div>
  </aside>

  <div class="main-area">
    <header class="topbar">
      <button class="sidebar-toggle" aria-label="Toggle sidebar">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h18M3 6h18M3 18h18"/></svg>
      </button>
      <div class="topbar-search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        <input type="text" placeholder="Search..." class="search-input">
      </div>
      <div class="topbar-actions">
        <button class="icon-btn" aria-label="Notifications">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        </button>
        <div class="avatar avatar-sm">{{USER_INITIALS}}</div>
      </div>
    </header>

    <main class="content">
      <div class="page-header">
        <div>
          <h1>{{PAGE_TITLE}}</h1>
          <p class="page-subtitle">{{PAGE_SUBTITLE}}</p>
        </div>
        <div class="page-actions">
          <!-- Optional: primary action button -->
          <button class="btn btn-primary">{{ACTION_LABEL}}</button>
        </div>
      </div>

      <div class="page-body">
        <!-- PASTE COMPONENTS HERE -->
      </div>
    </main>
  </div>
</div>
```

### CSS

```css
.app-layout {
  display: flex;
  min-height: 100vh;
}

/* --- Sidebar --- */
.sidebar {
  width: var(--sidebar-width, 260px);
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 40;
  transition: transform 0.2s ease;
}
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 20px 16px;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-heading);
  color: var(--color-text);
}
.logo-icon { font-size: 24px; }
.sidebar-nav {
  flex: 1;
  padding: 8px 12px;
  overflow-y: auto;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius);
  color: var(--color-muted);
  font-size: var(--font-size-sm);
  font-weight: 500;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}
.nav-item:hover {
  background: var(--color-hover);
  color: var(--color-text);
  text-decoration: none;
}
.nav-item.active {
  background: var(--color-primary);
  color: var(--color-on-primary);
}
.nav-icon { flex-shrink: 0; }
.nav-divider {
  height: 1px;
  background: var(--color-border);
  margin: 12px 0;
}
.nav-section-label {
  display: block;
  padding: 4px 12px 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-muted);
}
.sidebar-footer {
  padding: 16px;
  border-top: 1px solid var(--color-border);
}
.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--color-primary);
  color: var(--color-on-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}
.avatar-sm { width: 32px; height: 32px; font-size: 12px; }
.user-name { font-size: var(--font-size-sm); font-weight: 600; }
.user-role { font-size: 12px; color: var(--color-muted); }

/* --- Main area --- */
.main-area {
  flex: 1;
  margin-left: var(--sidebar-width, 260px);
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* --- Top bar --- */
.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 24px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 30;
}
.sidebar-toggle {
  display: none;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-muted);
  padding: 4px;
}
.topbar-search {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 400px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 7px 12px;
  color: var(--color-muted);
}
.search-input {
  border: none;
  background: none;
  outline: none;
  width: 100%;
  font-size: var(--font-size-sm);
}
.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: var(--radius);
  color: var(--color-muted);
  transition: background 0.15s, color 0.15s;
}
.icon-btn:hover { background: var(--color-hover); color: var(--color-text); }

/* --- Content --- */
.content {
  flex: 1;
  padding: 24px;
  max-width: 1200px;
  width: 100%;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}
.page-subtitle {
  color: var(--color-muted);
  font-size: var(--font-size-sm);
  margin-top: 4px;
}
.page-actions { display: flex; gap: 8px; flex-shrink: 0; }
.page-body { display: flex; flex-direction: column; gap: 24px; }

/* --- Responsive --- */
@media (max-width: 1024px) {
  .sidebar { transform: translateX(-100%); }
  .sidebar.open { transform: translateX(0); }
  .sidebar-toggle { display: block; }
  .main-area { margin-left: 0; }
}
```

---

## Layout B: Top Navigation

Use for: Marketing sites, simpler apps, public-facing pages.

### HTML

```html
<div class="app-topnav">
  <header class="topnav">
    <div class="topnav-inner">
      <div class="topnav-brand">
        <span class="logo-icon">{{LOGO_ICON_OR_SVG}}</span>
        <span class="logo-text">{{APP_NAME}}</span>
      </div>
      <nav class="topnav-links">
        <a href="#" class="topnav-link active">{{NAV_LABEL}}</a>
        <a href="#" class="topnav-link">{{NAV_LABEL}}</a>
        <a href="#" class="topnav-link">{{NAV_LABEL}}</a>
      </nav>
      <div class="topnav-actions">
        <button class="icon-btn" aria-label="Notifications">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        </button>
        <div class="avatar avatar-sm">{{USER_INITIALS}}</div>
      </div>
    </div>
  </header>

  <main class="content-topnav">
    <div class="page-header">
      <div>
        <h1>{{PAGE_TITLE}}</h1>
        <p class="page-subtitle">{{PAGE_SUBTITLE}}</p>
      </div>
      <div class="page-actions">
        <button class="btn btn-primary">{{ACTION_LABEL}}</button>
      </div>
    </div>

    <div class="page-body">
      <!-- PASTE COMPONENTS HERE -->
    </div>
  </main>
</div>
```

### CSS

```css
.app-topnav {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.topnav {
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 30;
}
.topnav-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 32px;
}
.topnav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: var(--font-weight-heading);
  font-size: var(--font-size-lg);
  color: var(--color-text);
  flex-shrink: 0;
}
.topnav-links {
  display: flex;
  gap: 4px;
  flex: 1;
}
.topnav-link {
  padding: 8px 14px;
  border-radius: var(--radius);
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-muted);
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}
.topnav-link:hover { background: var(--color-hover); color: var(--color-text); text-decoration: none; }
.topnav-link.active { background: var(--color-primary); color: var(--color-on-primary); }
.topnav-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.content-topnav {
  flex: 1;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  padding: 24px;
}

@media (max-width: 768px) {
  .topnav-links { display: none; }
  .topnav-inner { padding: 0 16px; }
  .content-topnav { padding: 16px; }
}
```

---

## Layout C: Centered Card

Use for: Login, signup, password reset, email verification, onboarding steps.

### HTML

```html
<div class="auth-layout">
  <div class="auth-card">
    <div class="auth-logo">
      <span class="logo-icon">{{LOGO_ICON_OR_SVG}}</span>
      <span class="logo-text">{{APP_NAME}}</span>
    </div>
    <h1 class="auth-title">{{TITLE}}</h1>
    <p class="auth-subtitle">{{SUBTITLE}}</p>

    <form class="auth-form">
      <!-- PASTE FORM FIELDS FROM snippets-components.md -->
    </form>

    <div class="auth-footer">
      <p>{{FOOTER_TEXT}} <a href="#">{{FOOTER_LINK}}</a></p>
    </div>
  </div>
</div>
```

### CSS

```css
.auth-layout {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--color-bg);
}
.auth-card {
  width: 100%;
  max-width: 400px;
  background: var(--color-surface);
  border: var(--card-border);
  border-radius: var(--radius-lg, 12px);
  box-shadow: var(--card-shadow);
  padding: 40px 32px;
}
.auth-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 24px;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-heading);
  color: var(--color-text);
}
.auth-title {
  text-align: center;
  font-size: var(--font-size-h2);
  margin-bottom: 8px;
}
.auth-subtitle {
  text-align: center;
  color: var(--color-muted);
  font-size: var(--font-size-sm);
  margin-bottom: 24px;
}
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.auth-footer {
  text-align: center;
  margin-top: 24px;
  font-size: var(--font-size-sm);
  color: var(--color-muted);
}

@media (max-width: 480px) {
  .auth-card {
    padding: 24px 20px;
    border: none;
    box-shadow: none;
    background: var(--color-bg);
  }
}
```

---

## Shared: Button Styles

Used across all layouts. Include in every screen.

```css
/* --- Buttons --- */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 16px;
  font-size: var(--font-size-sm);
  font-weight: 500;
  border-radius: var(--radius);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
  white-space: nowrap;
}
.btn-primary {
  background: var(--color-primary);
  color: var(--color-on-primary);
  border-color: var(--color-primary);
}
.btn-primary:hover { background: var(--color-primary-hover); border-color: var(--color-primary-hover); }
.btn-secondary {
  background: var(--color-surface);
  color: var(--color-text);
  border-color: var(--color-border);
}
.btn-secondary:hover { background: var(--color-hover); }
.btn-ghost {
  background: transparent;
  color: var(--color-muted);
  border-color: transparent;
}
.btn-ghost:hover { background: var(--color-hover); color: var(--color-text); }
.btn-danger {
  background: var(--color-error);
  color: #fff;
  border-color: var(--color-error);
}
.btn-sm { padding: 5px 10px; font-size: 12px; }
.btn-lg { padding: 12px 20px; font-size: var(--font-size-base); }
```
