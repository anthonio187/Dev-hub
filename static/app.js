/* DevX — single-page frontend (vanilla JS, no build step).
 * All user-provided text is inserted with textContent / text nodes, never innerHTML.
 */
(() => {
  "use strict";

  const POST_MAX = 280;
  const LANGS = ["javascript", "typescript", "python", "go", "rust", "java", "kotlin", "swift",
    "c", "cpp", "csharp", "php", "ruby", "sql", "bash", "html", "css", "json", "yaml", "dart", "text"];
  const ROOT = document.getElementById("app");
  const state = { me: null, navId: 0, cleanups: [] };

  // ------------------------------------------------------------------ helpers
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k === "value") el.value = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of children.flat(Infinity)) {
      if (c === null || c === undefined || c === false) continue;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }

  const ICONS = {
    home: '<path d="M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>',
    bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><polyline points="22,6 12,13 2,6"/>',
    bookmark: '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
    user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
    reply: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6A8.4 8.4 0 0 1 12.5 3h.5a8.5 8.5 0 0 1 8 8z"/>',
    repeat: '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
    heart: '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21.3l7.8-7.8 1-1.1a5.5 5.5 0 0 0 0-7.8z"/>',
    share: '<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/>',
    more: '<circle cx="5" cy="12" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/><circle cx="19" cy="12" r="1.2" fill="currentColor"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
    code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    folder: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
    trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    at: '<circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
  };
  function icon(name, size) {
    const span = document.createElement("span");
    span.className = "ico";
    span.style.display = "inline-flex";
    span.innerHTML = `<svg viewBox="0 0 24 24" width="${size || 20}" height="${size || 20}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
    return span;
  }

  function parseIso(iso) {
    return new Date(String(iso).replace(/(\.\d{3})\d+/, "$1"));
  }
  function timeAgo(iso) {
    const d = parseIso(iso);
    const s = (Date.now() - d.getTime()) / 1000;
    if (s < 60) return Math.max(1, Math.floor(s)) + "s";
    if (s < 3600) return Math.floor(s / 60) + "m";
    if (s < 86400) return Math.floor(s / 3600) + "h";
    const opts = d.getFullYear() === new Date().getFullYear()
      ? { month: "short", day: "numeric" } : { month: "short", day: "numeric", year: "numeric" };
    return d.toLocaleDateString(undefined, opts);
  }
  function fullDate(iso) { return parseIso(iso).toLocaleString(); }
  function joined(iso) {
    return parseIso(iso).toLocaleDateString(undefined, { month: "long", year: "numeric" });
  }
  function compact(n) {
    return new Intl.NumberFormat("en", { notation: "compact" }).format(n || 0);
  }
  function colorFor(s) {
    let x = 0;
    for (const c of String(s)) x = (x * 31 + c.charCodeAt(0)) >>> 0;
    return `hsl(${x % 360} 55% 42%)`;
  }
  function avatar(user, size = 40) {
    const el = h("div", { class: "avatar", style: { width: size + "px", height: size + "px", fontSize: Math.round(size * 0.42) + "px" } });
    if (user && user.avatar_url) el.append(h("img", { src: user.avatar_url, alt: "", loading: "lazy" }));
    else {
      const letter = ((user && (user.display_name || user.username)) || "?")[0].toUpperCase();
      el.textContent = letter;
      el.style.background = colorFor(user ? user.username : "?");
    }
    return el;
  }
  function withCursor(path, next) {
    return next ? `${path}${path.includes("?") ? "&" : "?"}before=${encodeURIComponent(next)}` : path;
  }
  function snippet(text, max = 160) {
    const t = String(text || "").replace(/\s+/g, " ").trim();
    return t.length > max ? t.slice(0, max) + "…" : t;
  }

  async function api(path, { method = "GET", body, form } = {}) {
    const opts = {
      method,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
    };
    if (form) opts.body = form;
    else if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      throw new Error("Network error. Check your connection.");
    }
    let data = {};
    try { data = await res.json(); } catch (_) { /* empty body */ }
    if (!res.ok) {
      const err = new Error(data.error || `Request failed (${res.status})`);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function toast(msg, kind = "") {
    const wrap = document.getElementById("toasts");
    const t = h("div", { class: "toast " + kind, role: "status" }, msg);
    wrap.append(t);
    setTimeout(() => t.remove(), 3200);
  }

  async function copyText(text, okMsg = "Copied to clipboard") {
    try {
      await navigator.clipboard.writeText(text);
      toast(okMsg);
    } catch (_) {
      toast(text);
    }
  }

  function onLeave(fn) { state.cleanups.push(fn); }
  function teardown() {
    const fns = state.cleanups.splice(0);
    for (const fn of fns) { try { fn(); } catch (_) { /* ignore */ } }
  }

  function navigate(path) {
    if (location.pathname + location.search !== path) history.pushState({}, "", path);
    render();
    window.scrollTo(0, 0);
  }

  function requireLogin() {
    if (state.me) return true;
    toast("Log in to do that");
    navigate("/login");
    return false;
  }

  // ------------------------------------------------------------ menus & modal
  let menuCloser = null;
  function closeMenus() {
    document.querySelectorAll(".menu").forEach((m) => m.remove());
    if (menuCloser) { document.removeEventListener("click", menuCloser); menuCloser = null; }
  }
  function openMenu(anchor, items) {
    closeMenus();
    const rect = anchor.getBoundingClientRect();
    const menu = h("div", { class: "menu", role: "menu" }, items.map((it) =>
      h("button", {
        class: "menu-item" + (it.danger ? " danger" : ""), type: "button", role: "menuitem",
        onclick: (e) => { e.stopPropagation(); closeMenus(); it.onClick(); },
      }, it.icon ? icon(it.icon, 18) : null, it.label)));
    document.body.append(menu);
    const left = Math.min(window.scrollX + rect.left, window.scrollX + window.innerWidth - 230);
    menu.style.top = window.scrollY + rect.bottom + 6 + "px";
    menu.style.left = Math.max(8, left) + "px";
    menuCloser = () => closeMenus();
    setTimeout(() => { if (menuCloser) document.addEventListener("click", menuCloser); }, 0);
  }

  function openModal(content, { wide = false, bare = false } = {}) {
    closeModal();
    const modal = h("div", { class: "modal" + (wide ? " wide" : "") + (bare ? " lightbox" : ""), role: "dialog", "aria-modal": "true" },
      bare ? null : h("button", { class: "icon-btn modal-x", type: "button", "aria-label": "Close", onclick: closeModal }, icon("x", 18)),
      content);
    const bd = h("div", { class: "backdrop" }, modal);
    bd.addEventListener("mousedown", (e) => { if (e.target === bd) closeModal(); });
    document.body.append(bd);
    document.body.classList.add("no-scroll");
    return bd;
  }
  function closeModal() {
    document.querySelectorAll(".backdrop").forEach((n) => n.remove());
    document.body.classList.remove("no-scroll");
  }

  function lightbox(url) {
    openModal(h("img", { class: "lightbox-img", src: url, alt: "Image" }), { bare: true });
  }

  // ------------------------------------------------------------ counts & badges
  function setBadges(n, m) {
    document.querySelectorAll('[data-badge="notifications"]').forEach((el) => {
      el.textContent = n > 99 ? "99+" : String(n || "");
      el.hidden = !n;
    });
    document.querySelectorAll('[data-badge="messages"]').forEach((el) => {
      el.textContent = m > 99 ? "99+" : String(m || "");
      el.hidden = !m;
    });
  }
  async function refreshCounts() {
    if (!state.me) return setBadges(0, 0);
    try {
      const c = await api("/api/counts");
      setBadges(c.notifications, c.messages);
    } catch (_) { /* offline: keep old badges */ }
  }

  // ------------------------------------------------------------ rich text
  const TOKEN_RE = /(https?:\/\/[^\s<]+[^\s<.,:;"')\]!?])|(#[A-Za-z][A-Za-z0-9_]{0,49})|(@[A-Za-z0-9_]{1,15})/g;
  function linkify(text, parent) {
    let last = 0;
    for (const m of String(text).matchAll(TOKEN_RE)) {
      if (m.index > last) parent.append(document.createTextNode(text.slice(last, m.index)));
      const tok = m[0];
      let node;
      if (tok.startsWith("http")) {
        node = h("a", { href: tok, target: "_blank", rel: "noopener noreferrer nofollow" }, tok);
      } else if (tok[0] === "#") {
        node = h("a", { href: "/search?q=" + encodeURIComponent(tok) }, tok);
      } else {
        node = h("a", { href: "/u/" + tok.slice(1) }, tok);
      }
      parent.append(node);
      last = m.index + tok.length;
    }
    if (last < text.length) parent.append(document.createTextNode(text.slice(last)));
    return parent;
  }

  function codeBlock(code, lang) {
    return h("div", { class: "code-block" },
      h("div", { class: "code-head" },
        h("span", {}, lang || "code"),
        h("button", {
          class: "copy", type: "button",
          onclick: (e) => { e.stopPropagation(); copyText(code, "Code copied"); },
        }, "Copy")),
      h("pre", {}, h("code", {}, code)));
  }

  function mediaGrid(urls) {
    if (!urls || !urls.length) return null;
    return h("div", { class: `media media-${Math.min(urls.length, 4)}` },
      urls.map((u) => h("img", {
        src: u, alt: "Attached image", loading: "lazy",
        onclick: (e) => { e.stopPropagation(); lightbox(u); },
      })));
  }

  function quoteCard(q, { link = true } = {}) {
    if (!q) return null;
    const body = q.body
      ? h("div", { class: "qbody" }, snippet(q.body, 280))
      : h("div", { class: "qbody muted-note" }, q.code ? "Shared a code snippet" : q.media.length ? "Shared an image" : "");
    const inner = [
      h("div", { class: "qhead" }, avatar(q.author, 20), h("b", {}, q.author.display_name),
        h("span", { class: "muted" }, "@" + q.author.username + " · " + timeAgo(q.created_at))),
      body,
      q.code ? h("div", { class: "qbody muted-note" }, `</> ${q.code_lang || "code"} snippet`) : null,
    ];
    return link
      ? h("a", { class: "quote-card", href: "/post/" + q.id }, inner)
      : h("div", { class: "quote-card" }, inner);
  }

  // ------------------------------------------------------------ post actions
  function bumpCount(id, field, delta) {
    const el = document.querySelector(`article.tweet[data-pid="${id}"]`);
    if (!el || !el._item) return;
    patchPost(id, { [field]: Math.max(0, (el._item.post[field] || 0) + delta) });
  }

  function patchPost(id, changes) {
    for (const el of document.querySelectorAll(`article.tweet[data-pid="${id}"]`)) {
      const item = el._item;
      const next = { ...item, post: { ...item.post, ...changes } };
      el.replaceWith(postCard(next, { detail: el.classList.contains("detail") }));
    }
  }

  async function toggleLike(p) {
    if (!requireLogin()) return;
    try {
      const on = !p.liked;
      const r = await api(`/api/posts/${p.id}/like`, { method: on ? "POST" : "DELETE" });
      patchPost(p.id, { liked: r.liked, like_count: r.like_count });
    } catch (e) { toast(e.message, "error"); }
  }

  async function toggleRepost(p) {
    if (!requireLogin()) return;
    try {
      const on = !p.reposted;
      const r = await api(`/api/posts/${p.id}/repost`, { method: on ? "POST" : "DELETE" });
      patchPost(p.id, { reposted: r.reposted, repost_count: r.repost_count });
      toast(on ? "Reposted" : "Repost undone");
    } catch (e) { toast(e.message, "error"); }
  }

  async function toggleBookmark(p) {
    if (!requireLogin()) return;
    try {
      const on = !p.bookmarked;
      await api(`/api/posts/${p.id}/bookmark`, { method: on ? "POST" : "DELETE" });
      if (!on && location.pathname === "/bookmarks") {
        document.querySelectorAll(`article.tweet[data-pid="${p.id}"]`).forEach((el) => el.remove());
      } else {
        patchPost(p.id, { bookmarked: on });
      }
      toast(on ? "Saved to bookmarks" : "Removed from bookmarks");
    } catch (e) { toast(e.message, "error"); }
  }

  async function deletePost(p) {
    if (!window.confirm("Delete this post? This can't be undone.")) return;
    try {
      await api(`/api/posts/${p.id}`, { method: "DELETE" });
      toast("Post deleted");
      if (location.pathname === `/post/${p.id}`) return navigate("/");
      document.querySelectorAll(`article.tweet[data-pid="${p.id}"]`).forEach((el) => el.remove());
    } catch (e) { toast(e.message, "error"); }
  }

  function actionBar(p) {
    const act = (cls, ic, count, label, onclick, on) => h("button", {
      class: `act ${cls}${on ? " on" : ""}`, type: "button", title: label, "aria-label": label,
      onclick: (e) => { e.stopPropagation(); onclick(e); },
    }, icon(ic, 18), h("span", { class: "cnt" }, count ? compact(count) : ""));

    const repostBtn = act("repost", "repeat", p.repost_count, "Repost", (e) => {
      if (!requireLogin()) return;
      openMenu(e.currentTarget, [
        { label: p.reposted ? "Undo repost" : "Repost", icon: "repeat", onClick: () => toggleRepost(p) },
        { label: "Quote", icon: "edit", onClick: () => openComposer({ quote: p }) },
      ]);
    }, p.reposted);

    return h("div", { class: "actions" },
      act("reply", "reply", p.reply_count, "Reply", () => openComposer({ replyTo: p })),
      repostBtn,
      act("like", "heart", p.like_count, p.liked ? "Unlike" : "Like", () => toggleLike(p), p.liked),
      act("bookmark", "bookmark", 0, p.bookmarked ? "Remove bookmark" : "Bookmark", () => toggleBookmark(p), p.bookmarked),
      act("share", "share", 0, "Share", () => copyText(`${location.origin}/post/${p.id}`, "Link copied")));
  }

  function postMenu(p) {
    const items = [];
    if (p.mine) items.push({ label: "Edit post", icon: "edit", onClick: () => editPostModal(p) });
    if (p.mine) items.push({ label: "Delete post", icon: "trash", danger: true, onClick: () => deletePost(p) });
    items.push({ label: "Copy link", icon: "link", onClick: () => copyText(`${location.origin}/post/${p.id}`, "Link copied") });
    return h("button", {
      class: "icon-btn more", type: "button", "aria-label": "More", title: "More",
      onclick: (e) => { e.stopPropagation(); openMenu(e.currentTarget, items); },
    }, icon("more", 18));
  }

  // ------------------------------------------------------------ post card
  function postCard(item, { detail = false } = {}) {
    const p = item.post;
    const card = h("article", { class: "tweet" + (detail ? " detail" : ""), "data-pid": p.id, tabindex: "0" });
    card._item = item;

    if (item.kind === "repost" && item.by) {
      card.append(h("div", { class: "context" }, icon("repeat", 14), " ",
        h("a", { href: "/u/" + item.by.username }, item.by.display_name), " reposted"));
    }

    const repoSlot = h("div");
    const main = h("div", { class: "tweet-main" },
      h("div", { class: "tweet-head" },
        h("a", { class: "name", href: "/u/" + p.author.username }, p.author.display_name),
        h("span", { class: "handle" }, " @" + p.author.username),
        h("span", { class: "muted" }, " · "),
        h("a", { class: "time", href: "/post/" + p.id, title: fullDate(p.created_at) }, timeAgo(p.created_at)),
        p.edited_at ? h("span", { class: "muted small", title: fullDate(p.edited_at) }, " · edited") : null,
        h("span", { class: "spacer" }),
        postMenu(p)),
      p.reply_to_username ? h("div", { class: "reply-to" }, "Replying to ",
        h("a", { href: "/u/" + p.reply_to_username }, "@" + p.reply_to_username)) : null,
      p.body ? linkify(p.body, h("div", { class: "tweet-body" })) : null,
      p.code ? codeBlock(p.code, p.code_lang) : null,
      mediaGrid((p.attachments || []).filter((a) => a.kind === "image").map((a) => a.url)),
      fileChips(p.attachments),
      quoteCard(p.quoted),
      repoSlot,
      detail ? h("div", { class: "time-full" }, fullDate(p.created_at)) : null,
      actionBar(p));

    card.append(h("div", { class: "tweet-row" }, avatar(p.author, 40), main));
    repoPreviewFor(p.body, repoSlot);
    if (!detail) {
      card.addEventListener("click", (e) => {
        if (e.target.closest("a, button, img, pre, .menu")) return;
        navigate("/post/" + p.id);
      });
      card.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target === card) navigate("/post/" + p.id); });
    }
    return card;
  }

  // ------------------------------------------------------------ composer
  function composer({ replyTo = null, quote = null, compact: isCompact = false, inModal = false, placeholder } = {}) {
    const media = [];
    let codeOn = false;
    let posting = false;

    const ta = h("textarea", {
      class: "compose-text", rows: isCompact ? 2 : 3, "aria-label": "Post text",
      placeholder: placeholder || (replyTo ? "Post your reply" : quote ? "Add a comment" : "What's happening?"),
    });
    const previews = h("div", { class: "compose-previews" });
    const codeTa = h("textarea", { class: "code-input", rows: 6, placeholder: "Paste your code snippet…", spellcheck: "false" });
    const langSel = h("select", { class: "lang-select", "aria-label": "Language" }, LANGS.map((l) => h("option", { value: l }, l)));
    const codeWrap = h("div", { class: "compose-code", hidden: true },
      h("div", { class: "row between" }, h("span", { class: "muted small" }, "Code snippet"), langSel), codeTa);
    const fileIn = h("input", { type: "file", accept: ATTACH_ACCEPT, multiple: true, hidden: true });
    const counter = h("span", { class: "counter" });
    const postBtn = h("button", { class: "btn primary blue", type: "button" }, replyTo ? "Reply" : "Post");
    const imgBtn = h("button", { class: "icon-btn", type: "button", title: "Add images or files", "aria-label": "Add images or files", onclick: () => fileIn.click() }, icon("image", 19));
    const codeBtn = h("button", { class: "icon-btn", type: "button", title: "Add code snippet", "aria-label": "Add code snippet", onclick: toggleCode }, icon("code", 19));

    function toggleCode() {
      codeOn = !codeOn;
      codeWrap.hidden = !codeOn;
      if (codeOn) codeTa.focus();
      update();
    }

    function renderPreviews() {
      previews.replaceChildren(...media.map((m, i) => h("div", { class: "thumb" + (m.status === "uploading" ? " busy" : "") + (m.kind === "file" || !m.url ? " thumb-file" : "") },
        m.kind === "file" || !m.url ? h("span", { class: "file-name" }, m.name || "file") : h("img", { src: m.url, alt: "" }),
        h("button", { class: "thumb-x", type: "button", "aria-label": "Remove image", onclick: () => { media.splice(i, 1); renderPreviews(); } }, "×"))));
      update();
    }

    function update() {
      const len = ta.value.length;
      const rem = POST_MAX - len;
      counter.textContent = rem <= 20 ? String(rem) : "";
      counter.className = "counter" + (rem < 0 ? " over" : rem <= 20 ? " warn" : "");
      const busy = media.some((m) => m.status === "uploading");
      const hasContent = ta.value.trim() || media.some((m) => m.id) || (codeOn && codeTa.value.trim()) || quote;
      postBtn.disabled = !hasContent || rem < 0 || busy || posting;
      imgBtn.disabled = media.length >= 4;
    }

    fileIn.addEventListener("change", async () => {
      const files = [...fileIn.files];
      fileIn.value = "";
      for (const f of files) {
        if (media.length >= 4) { toast("You can attach up to 4 files or images", "error"); break; }
        const item = { url: f.type.startsWith("image/") ? URL.createObjectURL(f) : "", name: f.name, kind: "", id: null, status: "uploading" };
        media.push(item);
        renderPreviews();
        try {
          const fd = new FormData();
          fd.append("file", f);
          const r = await api("/api/media", { method: "POST", form: fd });
          item.id = r.id;
          item.kind = r.kind;
          item.status = "done";
        } catch (e) {
          media.splice(media.indexOf(item), 1);
          toast(e.message, "error");
        }
        renderPreviews();
      }
    });

    async function submit() {
      if (posting || postBtn.disabled) return;
      if (!requireLogin()) return;
      posting = true;
      update();
      try {
        const code = codeOn ? codeTa.value.replace(/\s+$/, "") : "";
        const r = await api("/api/posts", {
          method: "POST",
          body: {
            body: ta.value.trim(),
            code,
            code_lang: code ? langSel.value : "",
            media_ids: media.filter((m) => m.id).map((m) => m.id),
            reply_to: replyTo ? replyTo.id : null,
            quote_id: quote ? quote.id : null,
          },
        });
        ta.value = "";
        codeTa.value = "";
        codeOn = false;
        codeWrap.hidden = true;
        media.length = 0;
        renderPreviews();
        if (replyTo) bumpCount(replyTo.id, "reply_count", 1);
        window.dispatchEvent(new CustomEvent("devx:posted", { detail: r.post }));
        toast(replyTo ? "Your reply was sent" : "Your post was sent");
        if (inModal) closeModal();
      } catch (e) {
        toast(e.message, "error");
      } finally {
        posting = false;
        update();
      }
    }

    postBtn.addEventListener("click", submit);
    ta.addEventListener("input", update);
    codeTa.addEventListener("input", update);
    ta.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit(); });
    update();

    return h("div", { class: "composer" + (inModal ? " in-modal" : "") },
      avatar(state.me || { username: "?" }, 40),
      h("div", { class: "compose-main" },
        ta, previews,
        quote ? quoteCard(quote, { link: false }) : null,
        codeWrap,
        h("div", { class: "compose-tools" }, imgBtn, codeBtn, h("span", { class: "spacer" }), counter, postBtn),
        fileIn));
  }

  function openComposer({ replyTo = null, quote = null } = {}) {
    if (!requireLogin()) return;
    const title = replyTo ? `Replying to @${replyTo.author.username}` : quote ? "Quote post" : "New post";
    openModal(h("div", {},
      h("div", { class: "modal-title" }, title),
      composer({ replyTo, quote, inModal: true, compact: true })));
  }

  // ------------------------------------------------------------ feeds
  function feed(loadPage, { renderItem = postCard, empty = "Nothing here yet.", accepts = null, position = "start" } = {}) {
    const list = h("div", { class: "feed" });
    const status = h("div", { class: "feed-status" });
    const sentinel = h("div", { style: { height: "1px" } });
    const more = h("button", { class: "btn ghost small", type: "button", style: { margin: "12px auto", display: "none" } }, "Show more");
    const wrap = h("div", {}, list, status, sentinel, h("div", { style: { textAlign: "center" } }, more));
    let next = null, busy = false, finished = false, loaded = 0;

    async function load() {
      if (busy || finished) return;
      busy = true;
      more.disabled = true;
      status.textContent = "Loading…";
      try {
        const data = await loadPage(next);
        const items = data.items || data.users || [];
        for (const it of items) list.append(renderItem(it));
        loaded += items.length;
        next = data.next || null;
        finished = !next;
        if (!loaded) status.textContent = empty;
        else status.textContent = finished ? "You're all caught up." : "";
        more.style.display = next ? "" : "none";
      } catch (e) {
        status.textContent = e.message;
        finished = true;
      } finally {
        busy = false;
        more.disabled = false;
      }
    }

    more.addEventListener("click", load);
    const io = new IntersectionObserver((entries) => {
      if (entries.some((en) => en.isIntersecting)) load();
    }, { rootMargin: "400px" });
    io.observe(sentinel);
    onLeave(() => io.disconnect());

    if (accepts) {
      const on = (e) => {
        if (!accepts(e.detail)) return;
        const node = postCard({ kind: "post", post: e.detail });
        if (position === "end") list.append(node); else list.prepend(node);
      };
      window.addEventListener("devx:posted", on);
      onLeave(() => window.removeEventListener("devx:posted", on));
    }
    load();
    return { el: wrap, reload: () => { list.replaceChildren(); next = null; finished = false; loaded = 0; load(); } };
  }

  // ------------------------------------------------------------ layout
  const NAV = [
    ["home", "Home", "/", "home"],
    ["explore", "Explore", "/explore", "search"],
    ["devs", "Developers", "/devs", "code"],
    ["projects", "Projects", "/projects", "folder"],
    ["collab", "Collaborate", "/collab", "users"],
    ["notifications", "Notifications", "/notifications", "bell", "notifications"],
    ["messages", "Messages", "/messages", "mail", "messages"],
    ["bookmarks", "Bookmarks", "/bookmarks", "bookmark"],
    ["profile", "Profile", null, "user"],
  ];

  function leftNav(active) {
    const items = NAV.filter(([key]) => state.me || key === "home" || key === "explore" || key === "devs" || key === "projects" || key === "collab").map(([key, label, path, ic, badge]) => {
      const href = key === "profile" ? "/u/" + state.me.username : path;
      return h("a", { class: "nav-item" + (active === key ? " active" : ""), href, "aria-label": label, title: label },
        icon(ic, 26), h("span", { class: "label" }, label),
        badge ? h("span", { class: "badge" + (badge === "messages" ? " msg" : ""), "data-badge": badge, hidden: true }) : null);
    });
    if (!state.me) {
      items.push(h("a", { class: "nav-item", href: "/login" }, h("span", { class: "label" }, "Log in")));
    }
    const account = state.me
      ? h("div", {
        class: "account", role: "button", tabindex: "0", title: "Account",
        onclick: (e) => openMenu(e.currentTarget, [
          { label: "Settings", icon: "settings", onClick: () => navigate("/settings") },
          { label: "Log out", icon: "logout", onClick: logout },
        ]),
      }, avatar(state.me, 40), h("div", { class: "who" }, h("b", {}, state.me.display_name), h("span", {}, "@" + state.me.username)), h("span", { class: "muted" }, "⋯"))
      : null;
    return h("nav", { class: "sidebar", "aria-label": "Main" },
      h("a", { class: "logo", href: "/" }, h("span", { class: "logo-mark" }, "</>"), h("span", {}, "DevX")),
      ...items,
      state.me ? h("button", { class: "btn primary post-btn", type: "button", onclick: () => openComposer() }, "Post") : null,
      state.me ? h("button", { class: "btn primary blue mobile-post", type: "button", "aria-label": "New post", onclick: () => openComposer() }, icon("plus", 20)) : null,
      account);
  }

  function rightColumn() {
    const col = h("aside", { class: "right-col" });
    const searchIn = h("input", { class: "search-input", type: "search", placeholder: "Search DevX", "aria-label": "Search", name: "q" });
    const form = h("form", { class: "side-search search-wrap", onsubmit: (e) => { e.preventDefault(); const q = searchIn.value.trim(); if (q) navigate("/search?q=" + encodeURIComponent(q)); } },
      icon("search", 18), searchIn);
    const trendsBox = h("div", { class: "card" }, h("div", { class: "card-title" }, "Trending in developer circles"), h("div", { class: "muted card-item" }, "Loading…"));
    const whoBox = h("div", { class: "card" }, h("div", { class: "card-title" }, "Who to follow"), h("div", { class: "muted card-item" }, "Loading…"));
    col.append(form, trendsBox, whoBox, h("p", { class: "muted small" }, "DevX · Built for developers · Share code, ship in public."));

    api("/api/trends").then((d) => {
      const body = d.tags.length
        ? d.tags.map((t) => h("a", { class: "card-item", href: "/search?q=" + encodeURIComponent("#" + t.tag) },
          h("div", { class: "t-meta" }, "Trending"), h("div", { class: "t-tag" }, "#" + t.tag),
          h("div", { class: "t-meta" }, `${compact(t.count)} post${t.count === 1 ? "" : "s"}`)))
        : [h("div", { class: "card-item muted" }, "No trends yet. Tag your posts with #hashtags.")];
      trendsBox.replaceChildren(h("div", { class: "card-title" }, "Trending in developer circles"), ...body);
    }).catch(() => {});

    api("/api/who-to-follow").then((d) => {
      const rows = d.users.filter((u) => !state.me || u.id !== state.me.id);
      const body = rows.length
        ? rows.map((u) => h("div", { class: "person" }, avatar(u, 40),
          h("div", { class: "who" }, h("a", { href: "/u/" + u.username }, u.display_name), h("span", {}, "@" + u.username)),
          state.me ? followButton(u) : null))
        : [h("div", { class: "card-item muted" }, "You're following everyone here. 🎉")];
      whoBox.replaceChildren(h("div", { class: "card-title" }, "Who to follow"), ...body);
    }).catch(() => {});
    return col;
  }

  function mountShell(active, { right = true } = {}) {
    teardown();
    closeMenus();
    closeModal();
    const token = ++state.navId;
    const main = h("main", { class: "center" });
    const shell = h("div", { class: "shell" + (right ? "" : " no-right") }, leftNav(active), main, right ? rightColumn() : null);
    ROOT.replaceChildren(shell);
    return { main, alive: () => token === state.navId };
  }

  function head(title, { back = false, right = null, tabs = null, sub = null, search = false } = {}) {
    return h("header", { class: "center-head" },
      h("div", { class: "head-row" },
        back ? h("button", { class: "icon-btn plain", type: "button", title: "Back", "aria-label": "Back", onclick: () => (history.length > 1 ? history.back() : navigate("/")) }, icon("back", 20)) : null,
        h("div", { class: "head-title" }, h("h1", {}, title), sub ? h("div", { class: "muted small" }, sub) : null),
        search ? null : h("span", { class: "spacer" }),
        right),
      tabs);
  }

  function tabBar(items, active, onSelect) {
    return h("div", { class: "tabs", role: "tablist" }, items.map(([key, label]) =>
      h("button", { class: "tab" + (active === key ? " active" : ""), type: "button", role: "tab", "aria-selected": active === key ? "true" : "false", onclick: () => onSelect(key) }, label)));
  }

  function emptyBox(title, text) {
    return h("div", { class: "empty" }, h("h2", {}, title), h("div", {}, text));
  }

  function loginPrompt(main, text) {
    main.append(head(""), h("div", { class: "login-prompt" },
      h("h2", {}, "Join the conversation"), h("div", { class: "muted" }, text),
      h("div", { class: "btns" },
        h("a", { class: "btn primary", href: "/login" }, "Log in"),
        h("a", { class: "btn ghost", href: "/signup" }, "Sign up"))));
  }

  function errorBox(msg) {
    return h("div", { class: "empty" }, h("h2", {}, "Something went wrong"), h("div", {}, msg || "Please try again."));
  }

  // ------------------------------------------------------------ auth
  function field(label, attrs) {
    const input = h("input", { class: "input", ...attrs });
    return { wrap: h("label", { class: "field" }, h("span", { class: "field-label" }, label), input), input };
  }

  function authCard(initial = "login") {
    let mode = initial;
    const card = h("section", { class: "auth-card" });
    function draw() {
      const isLogin = mode === "login";
      const user = isLogin
        ? field("Username or email", { name: "username", placeholder: "ada_codes or you@example.com", autocomplete: "username", required: true })
        : field("Username", { name: "username", placeholder: "e.g. ada_codes", minlength: "4", maxlength: "15", autocomplete: "username", required: true });
      const email = isLogin ? null : field("Email", { name: "email", type: "email", placeholder: "you@example.com", autocomplete: "email", maxlength: "254", required: true });
      const pass = field("Password", { name: "password", type: "password", placeholder: "At least 8 characters", minlength: "8", autocomplete: isLogin ? "current-password" : "new-password", required: true });
      const err = h("p", { class: "error", role: "alert" });
      const btn = h("button", { class: "btn primary blue wide", type: "submit" }, isLogin ? "Log in" : "Create account");
      const form = h("form", {
        onsubmit: async (e) => {
          e.preventDefault();
          err.textContent = "";
          btn.disabled = true;
          const body = isLogin
            ? { username: user.input.value.trim(), password: pass.input.value }
            : { username: user.input.value.trim(), email: email.input.value.trim(), password: pass.input.value };
          try {
            const r = await api(isLogin ? "/api/auth/login" : "/api/auth/signup", { method: "POST", body });
            state.me = r.user;
            toast(isLogin ? `Welcome back, @${r.user.username}` : `Welcome to DevX, @${r.user.username}!`);
            navigate("/");
          } catch (ex) {
            err.textContent = ex.message;
            btn.disabled = false;
          }
        },
      }, user.wrap, email ? email.wrap : null, pass.wrap, err, btn,
        isLogin ? h("button", { class: "link-btn small forgot", type: "button", onclick: () => navigate("/forgot") }, "Forgot password?") : null);
      card.replaceChildren(
        h("h2", {}, isLogin ? "Log in to DevX" : "Create your account"),
        h("div", { style: { height: "14px" } }),
        form,
        h("p", { class: "muted small switch" }, isLogin ? "New to DevX? " : "Already have an account? ",
          h("button", { class: "link-btn", type: "button", onclick: () => { mode = isLogin ? "signup" : "login"; draw(); } },
            isLogin ? "Sign up" : "Log in")));
    }
    draw();
    return card;
  }

  // ------------------------------------------------------------ developer features
  const GH_REPO_RE = /https:\/\/github\.com\/[A-Za-z0-9][\w-]*\/[A-Za-z0-9._-]+/;
  const guard = (fn) => async (...args) => {
    try { return await fn(...args); } catch (e) { toast(e.message, "error"); }
  };

  function repoCard(p) {
    return h("a", {
      class: "repo-card", href: p.url, target: "_blank", rel: "noopener noreferrer nofollow",
      onclick: (e) => e.stopPropagation(),
    },
      h("div", { class: "repo-head" }, icon("code", 16), h("b", {}, p.full_name)),
      p.description ? h("div", { class: "repo-desc" }, p.description) : null,
      h("div", { class: "repo-meta" },
        p.language ? h("span", {}, "● " + p.language) : null,
        h("span", {}, "★ " + compact(p.stars)),
        p.forks != null ? h("span", {}, "⑂ " + compact(p.forks)) : null));
  }

  function repoPreviewFor(body, slot) {
    const m = GH_REPO_RE.exec(body || "");
    if (!m) return;
    const url = m[0].replace(/\.git$/, "");
    api("/api/link-preview?url=" + encodeURIComponent(url))
      .then((d) => { if (d.preview) slot.replaceChildren(repoCard(d.preview)); })
      .catch(() => {});
  }

  function stat(n, label) {
    return h("div", { class: "stat" }, h("b", {}, compact(n)), " ", label);
  }

  function linkRow(title, url, sub) {
    return h("a", { class: "dev-link", href: url, target: "_blank", rel: "noopener noreferrer nofollow" },
      h("b", {}, title), sub ? h("span", { class: "muted small" }, " · " + sub) : null);
  }

  function platformCard(a) {
    const d = a.data || {};
    const body = [];
    if (a.provider === "github") {
      body.push(h("div", { class: "dev-stats" }, stat(d.followers, "followers"), stat(d.public_repos, "repos"), stat(d.total_stars, "stars")));
      if (d.languages && d.languages.length) {
        body.push(h("div", { class: "chips" }, d.languages.map((l) => h("span", { class: "chip static" }, `${l.name} · ${l.repos}`))));
      }
      for (const r of d.top_repos || []) body.push(repoCard({ full_name: r.name, url: r.url, description: r.description, stars: r.stars, language: r.language }));
    } else if (a.provider === "gitlab") {
      for (const pr of d.projects || []) body.push(linkRow(pr.name, pr.url, `★ ${pr.stars}${pr.description ? " · " + pr.description : ""}`));
    } else if (a.provider === "devto") {
      for (const art of d.articles || []) body.push(linkRow(art.title, art.url, `♥ ${art.reactions}`));
    } else if (a.provider === "npm") {
      for (const pk of d.packages || []) body.push(linkRow(pk.name, pk.url, `v${pk.version}${pk.description ? " · " + pk.description : ""}`));
    }
    return h("div", { class: "dev-card" },
      h("div", { class: "dev-head" },
        h("b", {}, a.label), " ",
        h("a", { href: d.url || "#", target: "_blank", rel: "noopener noreferrer nofollow" }, "@" + a.handle),
        a.verified ? h("span", { class: "verified", title: "Ownership verified" }, " ✓ verified") : null,
        a.error ? h("span", { class: "muted small" }, " · stats may be outdated") : null),
      body);
  }

  function devPanel(dev) {
    if (!dev) return null;
    const accs = Object.values(dev.accounts || {});
    if (!accs.length && !dev.open_to_work) return null;
    return h("section", { class: "dev-panel" },
      dev.open_to_work ? h("div", { class: "pill open" }, "🟢 Open to work", dev.available_for ? " · " + dev.available_for : "") : null,
      accs.map(platformCard));
  }

  function devRow(u) {
    const gh = u.dev && u.dev.accounts ? u.dev.accounts.github : null;
    const lang = gh && gh.data && gh.data.languages && gh.data.languages[0] ? gh.data.languages[0].name : "";
    return h("div", { class: "user-row" },
      h("a", { href: "/u/" + u.username }, avatar(u, 44)),
      h("div", { class: "who" },
        h("div", {}, h("a", { class: "nm", href: "/u/" + u.username }, u.display_name),
          gh && gh.verified ? h("span", { class: "verified", title: "Verified GitHub account" }, " ✓") : null),
        h("div", { class: "muted small" }, "@" + u.username + (lang ? " · " + lang : "")),
        u.tech && u.tech.length ? h("div", { class: "chips" }, u.tech.slice(0, 6).map((t) => h("span", { class: "chip static" }, t))) : null,
        u.dev && u.dev.open_to_work ? h("div", { class: "pill open" }, "🟢 Open to work" + (u.dev.available_for ? " · " + u.dev.available_for : "")) : null),
      state.me && !u.is_me ? followButton(u) : null);
  }

  async function devsView() {
    const { main } = mountShell("devs");
    let tech = "";
    let availableOnly = false;
    const techIn = h("input", {
      class: "search-input", type: "search", placeholder: "Filter by tech — python, postgres, react…",
      "aria-label": "Filter by tech", style: { paddingLeft: "44px" },
    });
    const otwIn = h("input", { type: "checkbox", "aria-label": "Open to work only" });
    const holder = h("div");
    const draw = () => {
      const qs = new URLSearchParams({ tech });
      if (availableOnly) qs.set("available", "1");
      holder.replaceChildren(feed((next) => api(withCursor("/api/devs?" + qs.toString(), next)), {
        renderItem: devRow, empty: "No developers match these filters yet.",
      }).el);
    };
    let timer = null;
    techIn.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => { tech = techIn.value.trim().toLowerCase(); draw(); }, 350);
    });
    otwIn.addEventListener("change", () => { availableOnly = otwIn.checked; draw(); });
    onLeave(() => clearTimeout(timer));
    main.append(
      head("Developers", { sub: "Find people by stack, and who's open to work" }),
      h("div", { class: "dev-filters" },
        h("div", { class: "search-wrap" }, icon("search", 18), techIn),
        h("label", { class: "check" }, otwIn, " Open to work")),
      holder);
    draw();
  }

  function platformRow(p, st, onState) {
    const acc = st.accounts[p.id];
    const input = h("input", {
      class: "input", placeholder: p.placeholder, maxlength: "100", "aria-label": p.label + " username",
      value: acc ? acc.handle : "",
    });
    const err = h("p", { class: "error", role: "alert" });
    const linkBtn = h("button", { class: "btn ghost small", type: "button" }, acc ? "Update" : "Link account");
    linkBtn.addEventListener("click", guard(async () => {
      err.textContent = "";
      const r = await api(`/api/me/dev/${p.id}`, { method: "POST", body: { handle: input.value.trim() } });
      toast(`${p.label} linked`);
      onState(r);
    }));
    const children = [
      h("div", { class: "dev-row-head" }, h("b", {}, p.label), " ",
        acc ? (acc.verified ? h("span", { class: "verified" }, "✓ verified") : h("span", { class: "muted small" }, "linked · unverified"))
          : h("span", { class: "muted small" }, "not connected")),
      h("div", { class: "row" }, input, linkBtn),
      h("p", { class: "muted small", style: { margin: "4px 0 0" } }, p.hint),
      err,
    ];
    if (acc && p.verify && !acc.verified && acc.verify_code) {
      const verifyBtn = h("button", { class: "btn primary blue small", type: "button" }, "Verify ownership");
      verifyBtn.addEventListener("click", guard(async () => {
        const r = await api(`/api/me/dev/${p.id}/verify`, { method: "POST" });
        toast(`${p.label} verified ✓`);
        onState(r);
      }));
      children.push(h("div", { class: "verify-box" },
        h("div", {}, `Add this code to your ${p.label} bio, save it, then verify:`),
        h("code", {}, acc.verify_code),
        verifyBtn));
    }
    if (acc) {
      const refreshBtn = h("button", { class: "link-btn", type: "button" }, "Refresh stats");
      refreshBtn.addEventListener("click", guard(async () => {
        const r = await api(`/api/me/dev/${p.id}/refresh`, { method: "POST" });
        toast("Stats refreshed");
        onState(r);
      }));
      const unlinkBtn = h("button", { class: "link-btn danger-text", type: "button" }, "Unlink");
      unlinkBtn.addEventListener("click", guard(async () => {
        if (!window.confirm(`Unlink your ${p.label} account?`)) return;
        const r = await api(`/api/me/dev/${p.id}`, { method: "DELETE" });
        toast(`${p.label} unlinked`);
        onState(r);
      }));
      children.push(h("div", { class: "row", style: { gap: "16px" } }, refreshBtn, unlinkBtn));
      if (acc.error) children.push(h("p", { class: "muted small" }, `Last refresh failed (${acc.error}). Showing your last good data.`));
    }
    return h("div", { class: "dev-row" }, children);
  }

  async function devSettingsSection() {
    const section = h("section", { class: "settings-section" },
      h("h2", {}, "Developer accounts"),
      h("p", { class: "muted small" }, "Connect your public developer profiles. Your stats show on your DevX profile and in the Developers directory. GitHub accounts need a quick ownership check."));
    const list = h("div", { class: "dev-settings" }, h("div", { class: "muted" }, "Loading…"));
    section.append(list);
    const [{ providers }, initial] = await Promise.all([api("/api/devs/providers"), api("/api/me/dev")]);
    const draw = (st) => list.replaceChildren(...providers.map((p) => platformRow(p, st, draw)));
    draw(initial);
    return section;
  }

  function availabilitySection(me) {
    const otw = h("input", { type: "checkbox", "aria-label": "Open to work", checked: !!me.open_to_work });
    const avail = field("Available for (shown when open to work)", { value: me.available_for || "", maxlength: "60", placeholder: "Freelance backend work, remote roles…" });
    const save = h("button", { class: "btn primary blue", type: "button" }, "Save availability");
    save.addEventListener("click", guard(async () => {
      const r = await api("/api/me", { method: "PATCH", body: { open_to_work: otw.checked, available_for: avail.input.value.trim() } });
      state.me = r.user;
      toast("Availability saved");
    }));
    return h("section", { class: "settings-section" },
      h("h2", {}, "Availability"),
      h("label", { class: "check", style: { marginBottom: "12px" } }, otw, " I'm open to work"),
      avail.wrap,
      save);
  }

  // ------------------------------------------------------------ views
  async function homeView() {
    const { main, alive } = mountShell("home");
    if (!state.me) return landingView(main, alive);
    let tab = "foryou";
    const holder = h("div");
    const tabsHolder = h("div");
    const drawTabs = () => tabsHolder.replaceChildren(
      tabBar([["foryou", "For you"], ["following", "Following"]], tab, (k) => { tab = k; drawAll(); }));
    const drawAll = () => {
      drawTabs();
      const f = tab === "foryou"
        ? feed((next) => api(withCursor("/api/explore", next)), {
          empty: "No posts yet. Be the first to share something!",
          accepts: (p) => !p.parent_id,
        })
        : feed((next) => api(withCursor("/api/timeline", next)), {
          empty: "Follow some developers to fill your timeline.",
          accepts: (p) => !p.parent_id && p.author.id === state.me.id,
        });
      holder.replaceChildren(f.el);
    };
    main.append(head("Home", { tabs: tabsHolder }), composer({ compact: true, placeholder: "What are you building?" }), holder);
    drawAll();
  }

  function searchForm(value = "") {
    const input = h("input", { class: "search-input", type: "search", value, placeholder: "Search DevX", "aria-label": "Search", name: "q", style: { paddingLeft: "16px" } });
    const form = h("form", {
      class: "head-search", style: { flex: "1" },
      onsubmit: (e) => { e.preventDefault(); const v = input.value.trim(); if (v) navigate("/search?q=" + encodeURIComponent(v)); },
    }, input);
    return form;
  }

  async function landingView(main, alive) {
    main.append(head("Home"));
    main.append(h("section", { class: "hero" },
      h("h2", { class: "big" }, "Where developers ", h("span", { style: { color: "var(--blue)" } }, "ship in public.")),
      h("p", {}, "Share code snippets, post your progress, reply, repost and message other developers — the X-style network built for builders.")));
    main.append(authCard("signup"));
    main.append(h("div", { class: "section-title" }, "Latest from the community"));
    const f = feed((next) => api(withCursor("/api/explore", next)), { empty: "Nothing posted yet. Sign up and be first!" });
    main.append(f.el);
  }

  async function exploreView() {
    const { main } = mountShell("explore");
    main.append(head("Explore", { right: searchForm("") }));
    main.append(h("div", { class: "section-title", style: { paddingBottom: "0" } }, "Latest posts"));
    const f = feed((next) => api(withCursor("/api/explore", next)), { empty: "Nothing here yet." });
    main.append(f.el);
  }

  async function searchView() {
    const q = new URLSearchParams(location.search).get("q") || "";
    const { main, alive } = mountShell("explore", { right: true });
    main.append(head("Search", { right: searchForm(q), search: true }));
    if (!q) { main.append(emptyBox("Search DevX", "Find posts, developers and #hashtags.")); return; }

    const TABS = [["top", "Top"], ["latest", "Latest"], ["people", "People"], ["tags", "Hashtags"], ["projects", "Projects"]];
    let tab = "top";
    const tabsHolder = h("div");
    const body = h("div");
    const lang = new URLSearchParams(location.search).get("lang") || "";
    const data = await api("/api/search?q=" + encodeURIComponent(q) + (lang ? "&lang=" + encodeURIComponent(lang) : ""));
    const langSel = h("select", { class: "input small-input", "aria-label": "Filter posts by language",
      onchange: (e) => navigate(`/search?q=${encodeURIComponent(q)}${e.target.value ? "&lang=" + encodeURIComponent(e.target.value) : ""}`) },
      h("option", { value: "" }, "Any language"), LANGS.map((l) => h("option", { value: l, selected: l === lang }, l)));
    if (!alive()) return;
    const draw = () => {
      tabsHolder.replaceChildren(tabBar(TABS, tab, (k) => { tab = k; draw(); }));
      body.replaceChildren();
      if (tab === "top" || tab === "latest") {
        if (!data.posts.length) body.append(emptyBox(`No posts for “${q}”`, "Try another word or hashtag."));
        else data.posts.forEach((p) => body.append(postCard({ kind: "post", post: p })));
      } else if (tab === "people") {
        if (!data.people.length) body.append(emptyBox("No people found", "Try a different name or username."));
        else data.people.forEach((u) => body.append(userRow(u)));
      } else if (tab === "projects") {
        if (!data.projects.length) body.append(emptyBox("No projects found", "Try another word or tag."));
        else data.projects.forEach((p) => body.append(projectCard(p)));
      } else {
        if (!data.tags.length) body.append(emptyBox("No hashtags", "Tag your posts with #hashtags to show up here."));
        else data.tags.forEach((t) => body.append(h("a", { class: "conv-row", href: "/search?q=" + encodeURIComponent("#" + t.tag) },
          h("div", { class: "who" }, h("b", {}, "#" + t.tag), h("div", { class: "muted small" }, `${compact(t.count)} posts`)))));
      }
    };
    main.append(h("div", { class: "row wrap filters" }, langSel), tabsHolder, body);
    draw();
  }

  async function notificationsView() {
    const { main, alive } = mountShell("notifications");
    if (!state.me) return loginPrompt(main, "Log in to see your notifications.");
    const markBtn = h("button", {
      class: "btn ghost small", type: "button",
      onclick: async () => {
        try { await api("/api/notifications/read", { method: "POST" }); refreshCounts(); toast("All caught up"); } catch (e) { toast(e.message, "error"); }
      },
    }, "Mark all read");
    main.append(head("Notifications", { right: markBtn }));
    const verbs = { like: "liked your post", repost: "reposted your post", reply: "replied to your post", quote: "quoted your post", mention: "mentioned you", follow: "followed you", message: "sent you a message", project_like: "liked your project", collab_interest: "wants to collaborate on your request", collab_status: "responded to your collaboration interest" };
    const icons = { like: "heart", repost: "repeat", reply: "reply", quote: "edit", mention: "at", follow: "user", message: "mail", project_like: "heart", collab_interest: "users", collab_status: "users" };
    const renderItem = (n) => {
      const a = n.actor;
      const text = h("div", { class: "ntext" },
        h("div", {}, avatar(a, 32), " ", h("a", { href: "/u/" + a.username, style: { color: "var(--text)", fontWeight: "700" } }, a.display_name),
          " ", h("span", {}, verbs[n.type] || "interacted")),
        n.post ? h("a", { class: "snip", href: "/post/" + n.post.id }, snippet(n.post.body || (n.post.code ? "Code snippet" : "Image"), 200)) : (n.link ? h("a", { class: "snip", href: n.link }, "Open →") : null));
      return h("article", { class: "notif" + (n.is_read ? "" : " unread") },
        h("div", { class: "ico " + n.type }, icons[n.type] === "at" ? h("span", { style: { fontWeight: "900", fontSize: "20px" } }, "@") : icon(icons[n.type] || "bell", 24)),
        text);
    };
    const f = feed((next) => api(withCursor("/api/notifications", next)), { renderItem, empty: "No notifications yet. Post something!" });
    main.append(f.el);
    const t = setTimeout(() => { if (alive()) api("/api/notifications/read", { method: "POST" }).then(refreshCounts).catch(() => {}); }, 2000);
    onLeave(() => clearTimeout(t));
  }

  function userRow(u) {
    return h("div", { class: "user-row" },
      h("a", { href: "/u/" + u.username }, avatar(u, 44)),
      h("div", { class: "who" },
        h("a", { class: "nm", href: "/u/" + u.username }, u.display_name),
        h("div", { class: "muted small" }, "@" + u.username)),
      state.me && !u.is_me && u.id !== state.me.id ? followButton(u) : null);
  }

  function followButton(u, onChange) {
    let following = !!u.following;
    const label = h("span", { class: "f-text" }, following ? "Following" : "Follow");
    const btn = h("button", { class: "btn small follow-btn" + (following ? " following" : ""), type: "button" }, label);
    const paint = () => {
      btn.className = "btn small follow-btn" + (following ? " following" : "");
      label.textContent = following ? "Following" : "Follow";
    };
    btn.addEventListener("mouseenter", () => { if (following) label.textContent = "Unfollow"; });
    btn.addEventListener("mouseleave", () => { if (following) label.textContent = "Following"; });
    btn.addEventListener("click", async (e) => {
      e.preventDefault(); e.stopPropagation();
      if (!requireLogin()) return;
      try {
        const r = await api(`/api/users/${encodeURIComponent(u.username)}/follow`, { method: following ? "DELETE" : "POST" });
        following = r.following;
        paint();
        if (onChange) onChange(following, r);
      } catch (ex) { toast(ex.message, "error"); }
    });
    return btn;
  }

  async function profileView(username) {
    const { main, alive } = mountShell("profile");
    const data = await api("/api/users/" + encodeURIComponent(username));
    if (!alive()) return;
    const u = data.user;
    const isMe = data.is_me;
    let tab = "posts";
    const feedHolder = h("div");
    const tabsHolder = h("div");
    const drawTabs = () => tabsHolder.replaceChildren(tabBar([["posts", "Posts"], ["replies", "Replies"], ["media", "Media"], ["likes", "Likes"], ["projects", "Projects"]], tab, (k) => { tab = k; drawTabs(); drawFeed(); }));
    const drawFeed = () => feedHolder.replaceChildren(tab === "projects" ? projectFeed(u.username) : feed((next) => api(withCursor(`/api/users/${encodeURIComponent(u.username)}/posts?tab=${tab}`, next)), {
      empty: tab === "likes" ? "No likes yet." : tab === "media" ? "No media yet." : tab === "replies" ? "No replies yet." : "No posts yet.",
      accepts: tab === "posts" ? (p) => p.author.username === u.username && !p.parent_id : tab === "replies" ? (p) => p.author.username === u.username && p.parent_id : null,
    }).el);

    const banner = h("div", { class: "banner" }, u.banner_url ? h("img", { src: u.banner_url, alt: "" }) : null);
    const followBtn = !isMe && state.me
      ? followButton({ ...u, following: data.following }, (f, r) => { statsEl.textContent = ""; statsEl.append(...statsRow(r.followers, data.stats.following)); })
      : null;
    const actions = h("div", { class: "profile-actions" },
      isMe ? h("a", { class: "btn ghost small", href: "/settings" }, "Edit profile") : null,
      !isMe && state.me ? h("button", { class: "btn ghost small", type: "button", "aria-label": "Message", onclick: () => startConversation(u.username) }, icon("mail", 18)) : null,
      followBtn);
    const statsRow = (followers, following) => [
      h("a", { href: `/u/${u.username}/following` }, h("b", {}, compact(following)), " Following"), " ",
      h("a", { href: `/u/${u.username}/followers` }, h("b", {}, compact(followers)), " Followers"),
    ];
    const statsEl = h("div", { class: "stat-links" }, statsRow(data.stats.followers, data.stats.following));

    main.append(head(u.display_name, { back: true, sub: `${data.stats.posts} post${data.stats.posts === 1 ? "" : "s"}` }));
    main.append(h("div", {}, banner,
      h("div", { class: "profile-top" },
        h("div", { class: "row between", style: { alignItems: "flex-end" } },
          h("div", { class: "profile-av" }, avatar(u, 134)), h("span")),
        actions,
        h("div", { class: "profile-name" }, u.display_name),
        h("div", { class: "profile-handle" }, "@" + u.username),
        u.bio ? h("div", { class: "profile-bio" }, linkify(u.bio, h("span"))) : null,
        h("div", { class: "profile-meta" },
          u.location ? h("span", {}, "📍 " + u.location) : null,
          u.website ? h("a", { href: u.website, target: "_blank", rel: "noopener noreferrer nofollow" }, "🔗 " + u.website.replace(/^https?:\/\//, "")) : null,
          u.linkedin ? h("a", { href: u.linkedin, target: "_blank", rel: "noopener noreferrer nofollow" }, "💼 LinkedIn") : null,
          h("span", {}, "📅 Joined " + joined(u.created_at))),
        u.tech && u.tech.length ? h("div", { class: "chips" }, u.tech.map((t) => h("span", { class: "chip static" }, t))) : null,
        statsEl,
        devPanel(data.dev),
        !data.is_me && data.follows_you ? h("div", { class: "muted small", style: { marginBottom: "8px" } }, "Follows you") : null)));
    main.append(tabsHolder, feedHolder);
    drawTabs();
    drawFeed();
  }

  async function startConversation(username) {
    if (!requireLogin()) return;
    try {
      const r = await api("/api/conversations", { method: "POST", body: { username } });
      navigate(`/messages/${r.id}`);
    } catch (e) { toast(e.message, "error"); }
  }

  async function followView(username, kind) {
    const { main, alive } = mountShell("profile");
    const u = await api("/api/users/" + encodeURIComponent(username));
    if (!alive()) return;
    main.append(head("@" + username, { back: true }));
    main.append(tabBar([["followers", "Followers"], ["following", "Following"]], kind, (k) => navigate(`/u/${username}/${k}`)));
    main.append(feed((next) => api(withCursor(`/api/users/${encodeURIComponent(username)}/${kind}`, next)), {
      renderItem: userRow,
      empty: kind === "followers" ? "No followers yet." : "Not following anyone yet.",
    }).el);
    void u;
  }

  async function postView(id) {
    const { main, alive } = mountShell("home");
    const data = await api("/api/posts/" + id);
    if (!alive()) return;
    main.append(head("Post", { back: true }));
    for (const p of data.thread) main.append(postCard({ kind: "post", post: p }));
    const detail = postCard({ kind: "post", post: data.post }, { detail: true });
    main.append(detail);
    if (state.me) main.append(composer({ replyTo: data.post, compact: true, placeholder: "Post your reply" }));
    const replies = h("div", { class: "replies" });
    main.append(replies);
    const r = await api(`/api/posts/${id}/replies`);
    if (!alive()) return;
    if (!r.items.length) replies.append(h("div", { class: "feed-status" }, "No replies yet. Be the first!"));
    for (const p of r.items) replies.append(postCard({ kind: "post", post: p }));
    const on = (e) => {
      if (e.detail.parent_id !== id) return;
      replies.querySelector(".feed-status")?.remove();
      replies.append(postCard({ kind: "post", post: e.detail }));
    };
    window.addEventListener("devx:posted", on);
    onLeave(() => window.removeEventListener("devx:posted", on));
  }

  async function bookmarksView() {
    const { main } = mountShell("bookmarks");
    if (!state.me) return loginPrompt(main, "Log in to see your bookmarks.");
    main.append(head("Bookmarks", { sub: "@" + state.me.username }));
    main.append(feed((next) => api(withCursor("/api/bookmarks", next)), {
      empty: "Save posts to find them here later.",
    }).el);
  }

  async function messagesView() {
    const { main, alive } = mountShell("messages", { right: false });
    if (!state.me) return loginPrompt(main, "Log in to send and receive messages.");
    const newBtn = h("button", { class: "btn primary blue small", type: "button", onclick: newMessageModal }, "New message");
    main.append(head("Messages", { right: newBtn }));
    const data = await api("/api/conversations");
    if (!alive()) return;
    if (!data.conversations.length) {
      main.append(emptyBox("Welcome to your inbox!", "Drop a line to any developer — share a snippet, ask for code review, or just say hi."));
      return;
    }
    for (const c of data.conversations) {
      const prev = c.last ? (c.last.mine ? "You: " : "") + c.last.text : "No messages yet";
      main.append(h("a", { class: "conv-row", href: `/messages/${c.id}` },
        avatar(c.user, 44),
        h("div", { class: "who" }, h("b", {}, c.user.display_name), h("div", { class: "prev" }, prev || "Image")),
        c.last ? h("span", { class: "when" }, timeAgo(c.last.created_at)) : null,
        c.unread ? h("span", { class: "dot", title: `${c.unread} unread` }) : null));
    }
  }

  function newMessageModal() {
    const input = h("input", { class: "input", placeholder: "Username (without @)", minlength: "4", maxlength: "15" });
    const err = h("p", { class: "error" });
    const start = async (e) => {
      e.preventDefault();
      const name = input.value.trim().replace(/^@/, "");
      if (!name) return;
      try {
        const r = await api("/api/conversations", { method: "POST", body: { username: name } });
        closeModal();
        navigate(`/messages/${r.id}`);
      } catch (ex) { err.textContent = ex.message; }
    };
    openModal(h("form", { onsubmit: start, style: { paddingTop: "40px" } },
      h("div", { class: "modal-title", style: { padding: "0 0 12px" } }, "New message"),
      h("label", { class: "field" }, h("span", { class: "field-label" }, "To"), input),
      err,
      h("button", { class: "btn primary blue wide", type: "submit" }, "Start conversation")), { wide: true });
    setTimeout(() => input.focus(), 0);
  }

  async function conversationView(cid) {
    const { main, alive } = mountShell("messages", { right: false });
    if (!state.me) return loginPrompt(main, "Log in to send messages.");
    const data = await api(`/api/conversations/${cid}/messages`);
    if (!alive()) return;
    const other = data.user;
    const seen = new Set();
    let lastId = 0;
    const list = h("div", { class: "dm-list", role: "log", "aria-live": "polite" });
    const older = h("button", { class: "btn ghost small", type: "button", style: { alignSelf: "center" }, hidden: true }, "Load older messages");
    let nextOlder = data.next;

    function bubble(m) {
      const b = h("div", { class: "bubble " + (m.mine ? "mine" : "theirs") });
      if (m.media && m.media.kind === "file") b.append(h("a", { class: "file-chip dm-file", href: m.media.url, download: m.media.name }, icon("file", 18), h("span", { class: "file-name" }, m.media.name), h("span", { class: "muted small" }, fmtBytes(m.media.size))));
      else if (m.media_url) b.append(h("img", { class: "dm-img", src: m.media_url, alt: "Shared image", onclick: () => lightbox(m.media_url) }));
      if (m.body) b.append(linkify(m.body, h("span")));
      b.append(h("span", { class: "bubble-time", title: fullDate(m.created_at) }, timeAgo(m.created_at)));
      return b;
    }
    function addMessages(msgs, where = "end") {
      const fresh = msgs.filter((m) => !seen.has(m.id));
      fresh.forEach((m) => seen.add(m.id));
      const nodes = fresh.map((m) => { const w = h("div", { style: { display: "flex", flexDirection: "column", alignItems: m.mine ? "flex-end" : "flex-start" }, "data-mid": m.id }, bubble(m)); return w; });
      if (where === "start") list.prepend(...nodes); else list.append(...nodes);
      for (const m of msgs) lastId = Math.max(lastId, m.id);
      return fresh.length;
    }
    function scrollBottom() { list.scrollTop = list.scrollHeight; }

    addMessages(data.messages);
    older.hidden = !nextOlder;
    older.addEventListener("click", async () => {
      if (!nextOlder) return;
      older.disabled = true;
      try {
        const r = await api(`/api/conversations/${cid}/messages?before=${nextOlder}`);
        const prevH = list.scrollHeight;
        const fresh = r.messages.filter((m) => !seen.has(m.id));
        fresh.forEach((m) => seen.add(m.id));
        list.prepend(...fresh.map((m) => h("div", { style: { display: "flex", flexDirection: "column", alignItems: m.mine ? "flex-end" : "flex-start" }, "data-mid": m.id }, bubble(m))));
        nextOlder = r.next;
        older.hidden = !nextOlder;
        list.scrollTop = list.scrollHeight - prevH;
      } catch (e) { toast(e.message, "error"); }
      older.disabled = false;
    });

    // Composer
    let pending = null; // uploaded image {id, url}
    const ta = h("textarea", { class: "dm-input", rows: 1, placeholder: "Start a new message", "aria-label": "Message" });
    const fileIn = h("input", { type: "file", accept: ATTACH_ACCEPT, hidden: true });
    const chipHolder = h("div");
    const sendBtn = h("button", { class: "icon-btn", type: "button", title: "Send", "aria-label": "Send" }, icon("send", 20));
    const attachBtn = h("button", { class: "icon-btn", type: "button", title: "Send an image or file", "aria-label": "Send an image or file", onclick: () => fileIn.click() }, icon("image", 20));
    let sending = false;

    function drawChip() {
      chipHolder.replaceChildren(pending ? h("div", { class: "dm-chip" },
        pending.kind === "file" ? h("span", { class: "file-name" }, pending.name) : h("img", { src: pending.url, alt: "" }), h("span", {}, pending.kind === "file" ? "File ready" : "Image ready"),
        h("button", { class: "icon-btn plain", type: "button", "aria-label": "Remove image", onclick: () => { pending = null; drawChip(); } }, icon("x", 16))) : null);
    }
    fileIn.addEventListener("change", async () => {
      const f = fileIn.files[0];
      fileIn.value = "";
      if (!f) return;
      toast("Uploading…");
      try {
        const fd = new FormData();
        fd.append("file", f);
        const r = await api("/api/media", { method: "POST", form: fd });
        pending = { id: r.id, url: r.url, kind: r.kind, name: r.name };
        drawChip();
      } catch (e) { toast(e.message, "error"); }
    });

    async function send() {
      const body = ta.value.trim();
      if ((!body && !pending) || sending) return;
      sending = true;
      sendBtn.disabled = true;
      try {
        const r = await api(`/api/conversations/${cid}/messages`, { method: "POST", body: { body, media_id: pending ? pending.id : null } });
        ta.value = "";
        pending = null;
        drawChip();
        addMessages([r.message]);
        scrollBottom();
        ta.focus();
      } catch (e) { toast(e.message, "error"); }
      sending = false;
      sendBtn.disabled = false;
    }
    sendBtn.addEventListener("click", send);
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
    });
    ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 140) + "px"; });

    // Live updates via polling (every 3s while the conversation is open)
    let polling = false;
    const timer = setInterval(async () => {
      if (polling || !alive()) return;
      polling = true;
      try {
        const r = await api(`/api/conversations/${cid}/messages?after=${lastId}`);
        if (r.messages.length) {
          addMessages(r.messages);
          scrollBottom();
          refreshCounts();
        }
      } catch (_) { /* transient */ }
      polling = false;
    }, 3000);
    onLeave(() => clearInterval(timer));

    main.append(h("header", { class: "center-head" },
      h("div", { class: "head-row" },
        h("button", { class: "icon-btn plain", type: "button", "aria-label": "Back", onclick: () => navigate("/messages") }, icon("back", 20)),
        avatar(other, 32),
        h("div", { class: "head-title" }, h("h1", { style: { fontSize: "17px" } }, other.display_name),
          h("div", { class: "muted small" }, h("a", { href: "/u/" + other.username }, "@" + other.username))))));
    main.append(h("div", { class: "dm-wrap" },
      h("div", { style: { display: "flex", justifyContent: "center", padding: "8px" } }, older),
      list,
      h("div", { class: "dm-bar" },
        chipHolder,
        h("div", { class: "row" }, attachBtn, ta, sendBtn),
        fileIn)));
    if (!data.messages.length) list.append(h("div", { class: "empty", style: { margin: "auto" } }, `Say hi to @${other.username} 👋`));
    requestAnimationFrame(scrollBottom);
    setTimeout(() => ta.focus(), 50);
    refreshCounts();
  }

  async function settingsView() {
    const { main, alive } = mountShell("settings", { right: false });
    if (!state.me) {
      main.append(head("Settings"));
      main.append(h("section", { class: "auth-page" }, authCard("login")));
      return;
    }
    const me = state.me;
    main.append(head("Settings", { back: true }));

    // Profile section
    const name = field("Display name", { value: me.display_name, maxlength: "50", placeholder: "Your name" });
    const bioTa = h("textarea", { class: "input", rows: 3, maxlength: "160", placeholder: "Tell developers what you build" });
    bioTa.value = me.bio || "";
    const bioCount = h("div", { class: "muted small", style: { textAlign: "right", marginTop: "-10px", marginBottom: "10px" } });
    const drawBio = () => { bioCount.textContent = `${bioTa.value.length}/160`; };
    bioTa.addEventListener("input", drawBio); drawBio();
    const loc = field("Location", { value: me.location, maxlength: "30", placeholder: "Lagos, Nigeria" });
    const web = field("Website", { value: me.website, maxlength: "100", placeholder: "https://yoursite.dev", type: "url" });
    const tech = field("Tech stack (comma separated)", { value: (me.tech || []).join(", "), maxlength: "300", placeholder: "Python, Postgres, React, Go" });
    const linkedin = field("LinkedIn", { value: me.linkedin || "", maxlength: "120", placeholder: "https://www.linkedin.com/in/you", type: "url" });
    const emailF = field("Email (private; used for password reset)", { value: me.email || "", maxlength: "254", placeholder: "you@example.com", type: "email" });

    const avatarImg = h("div", {}, avatar(me, 72));
    const avatarIn = h("input", { type: "file", accept: "image/png,image/jpeg,image/gif,image/webp", hidden: true });
    const bannerIn = h("input", { type: "file", accept: "image/png,image/jpeg,image/gif,image/webp", hidden: true });
    const bannerBox = h("div", { class: "banner-edit" });
    const drawBanner = (url) => bannerBox.replaceChildren(url ? h("img", { src: url, alt: "" }) : h("div", { class: "banner" }), h("div", { class: "btns" },
      h("button", { class: "btn small ghost", type: "button", style: { background: "var(--bg)" }, onclick: () => bannerIn.click() }, "Change banner"),
      url ? h("button", { class: "btn small ghost", type: "button", style: { background: "var(--bg)" }, onclick: () => saveField({ banner_media_id: null }, "Banner removed").then(() => drawBanner(null)) }, "Remove") : null));
    drawBanner(me.banner_url);

    const saveField = async (patch, okMsg) => {
      try {
        const r = await api("/api/me", { method: "PATCH", body: patch });
        state.me = r.user;
        if (!alive()) return;
        toast(okMsg || "Saved");
        return r.user;
      } catch (e) { toast(e.message, "error"); }
    };
    const drawAvatar = () => avatarImg.replaceChildren(avatar(state.me, 72));
    avatarIn.addEventListener("change", async () => {
      const f = avatarIn.files[0]; avatarIn.value = "";
      if (!f) return;
      try {
        const fd = new FormData(); fd.append("file", f);
        const up = await api("/api/media", { method: "POST", form: fd });
        const u = await saveField({ avatar_media_id: up.id }, "Profile photo updated");
        if (u) drawAvatar();
      } catch (e) { toast(e.message, "error"); }
    });
    bannerIn.addEventListener("change", async () => {
      const f = bannerIn.files[0]; bannerIn.value = "";
      if (!f) return;
      try {
        const fd = new FormData(); fd.append("file", f);
        const up = await api("/api/media", { method: "POST", form: fd });
        const u = await saveField({ banner_media_id: up.id }, "Banner updated");
        if (u) drawBanner(u.banner_url);
      } catch (e) { toast(e.message, "error"); }
    });

    const profileForm = h("form", {
      class: "settings-section",
      onsubmit: async (e) => {
        e.preventDefault();
        const btn = e.submitter; if (btn) btn.disabled = true;
        const u = await saveField({
          display_name: name.input.value.trim(),
          bio: bioTa.value,
          location: loc.input.value.trim(),
          website: web.input.value.trim(),
          tech: tech.input.value,
          linkedin: linkedin.input.value.trim(),
          email: emailF.input.value.trim(),
        }, "Profile saved");
        if (btn) btn.disabled = false;
        if (u) drawAvatar();
      },
    },
      h("h2", {}, "Profile"),
      bannerBox,
      h("div", { class: "avatar-edit" }, avatarImg,
        h("button", { class: "btn ghost small", type: "button", onclick: () => avatarIn.click() }, "Change photo"),
        me.avatar_url ? h("button", { class: "btn ghost small", type: "button", onclick: () => saveField({ avatar_media_id: null }, "Photo removed").then(drawAvatar) }, "Remove") : null),
      name.wrap, h("label", { class: "field" }, h("span", { class: "field-label" }, "Bio"), bioTa), bioCount,
      loc.wrap, web.wrap, linkedin.wrap, tech.wrap, emailF.wrap,
      h("button", { class: "btn primary blue", type: "submit" }, "Save profile"),
      avatarIn, bannerIn);
    main.append(profileForm);
    main.append(availabilitySection(me));
    const devSection = await devSettingsSection();
    if (!alive()) return;
    main.append(devSection);

    // Appearance
    const theme = document.documentElement.dataset.theme || "dark";
    const seg = h("div", { class: "seg", role: "group", "aria-label": "Theme" });
    const drawSeg = () => seg.replaceChildren(
      ...[["dark", "Dark"], ["light", "Light"]].map(([k, l]) => h("button", { type: "button", class: (document.documentElement.dataset.theme === k) ? "on" : "", onclick: () => { setTheme(k); drawSeg(); } }, l)));
    drawSeg();
    main.append(h("section", { class: "settings-section" }, h("h2", {}, "Appearance"), seg));

    // Password
    const cur = field("Current password", { type: "password", autocomplete: "current-password" });
    const nw = field("New password", { type: "password", autocomplete: "new-password", minlength: "8" });
    const nw2 = field("Confirm new password", { type: "password", autocomplete: "new-password", minlength: "8" });
    main.append(h("form", {
      class: "settings-section",
      onsubmit: async (e) => {
        e.preventDefault();
        if (nw.input.value !== nw2.input.value) return toast("New passwords don't match", "error");
        try {
          await api("/api/auth/password", { method: "POST", body: { current: cur.input.value, new: nw.input.value } });
          toast("Password changed");
          e.target.reset();
        } catch (ex) { toast(ex.message, "error"); }
      },
    }, h("h2", {}, "Change password"), cur.wrap, nw.wrap, nw2.wrap, h("button", { class: "btn primary blue", type: "submit" }, "Update password")));

    // Danger zone
    const delPass = field("Confirm with your password", { type: "password", autocomplete: "current-password" });
    main.append(h("section", { class: "settings-section" },
      h("div", { class: "danger-zone" },
        h("h3", {}, "Delete account"),
        h("p", { class: "muted small" }, "This permanently deletes your profile, posts, media, messages and follows."),
        h("form", {
          onsubmit: async (e) => {
            e.preventDefault();
            if (!window.confirm("Delete your DevX account forever?")) return;
            try {
              await api("/api/me", { method: "DELETE", body: { password: delPass.input.value } });
              state.me = null;
              toast("Your account was deleted");
              navigate("/");
            } catch (ex) { toast(ex.message, "error"); }
          },
        }, delPass.wrap, h("button", { class: "btn danger", type: "submit" }, "Delete my account")))),
      h("div", { class: "row", style: { marginTop: "16px" } },
        h("button", { class: "btn ghost", type: "button", onclick: logout }, icon("logout", 18), "Log out")));
  }

  function setTheme(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("devx-theme", t); } catch (_) { /* ignore */ }
  }

  async function logout() {
    try { await api("/api/auth/logout", { method: "POST" }); } catch (_) { /* ignore */ }
    state.me = null;
    refreshCounts();
    toast("You've been logged out");
    navigate("/");
  }

  function authView(mode) {
    const { main } = mountShell("login", { right: false });
    if (state.me) return navigate("/");
    main.append(head("", { back: false }));
    main.append(h("section", { class: "auth-page" }, authCard(mode)));
  }

  function notFound() {
    const { main } = mountShell("", { right: false });
    main.append(head("Not found", { back: true }));
    main.append(emptyBox("This page doesn't exist", "Try searching for something else."));
  }

  // ------------------------------------------------------------ projects & collaboration
  const ATTACH_ACCEPT = "image/png,image/jpeg,image/gif,image/webp,.pdf,.zip,.txt,.md,.csv,.json,.yaml,.yml,.toml,.log,.py,.js,.ts,.tsx,.jsx,.go,.rs,.java,.kt,.swift,.c,.h,.cpp,.hpp,.cs,.rb,.php,.sql,.sh,.css,.ini,.xml";
  const STATUS_LABEL = { idea: "💡 Idea", building: "🚧 Building", shipped: "🚀 Shipped", open: "Open", closed: "Closed" };

  function fmtBytes(n) {
    if (!n) return "";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }

  // Document and source-file attachments: link to download, never inline.
  function fileChips(attachments) {
    const files = (attachments || []).filter((a) => a.kind === "file");
    if (!files.length) return null;
    return h("div", { class: "file-chips" }, files.map((a) => h("a", {
      class: "file-chip", href: a.url, download: a.name, onclick: (e) => e.stopPropagation(),
    }, icon("file", 18), h("span", { class: "file-name" }, a.name), h("span", { class: "muted small" }, fmtBytes(a.size)))));
  }

  function chipList(items, cls = "chip") {
    return (items || []).map((t) => h("a", { class: cls, href: "/search?q=" + encodeURIComponent("#" + t) }, t));
  }

  function projectCard(p) {
    const card = h("article", { class: "card-item project-card", "data-id": p.id },
      p.screenshot_url ? h("a", { href: "/projects/" + p.id, class: "proj-shot" }, h("img", { src: p.screenshot_url, alt: "" })) : null,
      h("div", { class: "row between wrap" },
        h("a", { class: "proj-title", href: "/projects/" + p.id }, p.title),
        h("span", { class: "status-badge " + p.status }, STATUS_LABEL[p.status] || p.status)),
      h("div", { class: "muted small" }, "by ", h("a", { href: "/u/" + p.author.username }, "@" + p.author.username)),
      p.description ? h("p", { class: "proj-desc" }, snippet(p.description, 220)) : null,
      h("div", { class: "chips" }, chipList(p.tags)),
      h("div", { class: "row wrap small muted" },
        p.repo_url ? h("a", { href: p.repo_url, target: "_blank", rel: "noopener noreferrer nofollow" }, "⌘ Repo") : null,
        p.live_url ? h("a", { href: p.live_url, target: "_blank", rel: "noopener noreferrer nofollow" }, "🌐 Live") : null,
        h("span", { class: "spacer" }),
        h("span", {}, `♥ ${compact(p.like_count)}`)));
    return card;
  }

  function collabCard(r) {
    return h("article", { class: "card-item collab-card" },
      h("div", { class: "row between wrap" },
        h("a", { class: "proj-title", href: "/collab/" + r.id }, r.title),
        h("span", { class: "status-badge " + r.status }, STATUS_LABEL[r.status] || r.status)),
      h("div", { class: "muted small" }, "by ", h("a", { href: "/u/" + r.author.username }, "@" + r.author.username),
        r.project ? [" · project: ", h("a", { href: "/projects/" + r.project.id }, r.project.title)] : null),
      r.description ? h("p", { class: "proj-desc" }, snippet(r.description, 200)) : null,
      h("div", { class: "chips" }, chipList(r.skills)),
      h("div", { class: "row small muted" }, `${r.interest_count} interested`, h("span", { class: "spacer" }),
        r.my_interest ? h("span", { class: "status-badge " + r.my_interest }, "You: " + r.my_interest) : null));
  }

  function listFilters(fields, onChange) {
    const wrap = h("div", { class: "row wrap filters", role: "search" });
    const controls = {};
    for (const f of fields) {
      if (f.options) {
        controls[f.key] = h("select", { class: "input small-input", "aria-label": f.label },
          f.options.map(([v, l]) => h("option", { value: v }, l)));
      } else {
        controls[f.key] = h("input", { class: "input small-input", placeholder: f.label, "aria-label": f.label, maxlength: "60" });
      }
      controls[f.key].addEventListener(f.options ? "change" : "input", debounce(onChange, 250));
      wrap.append(controls[f.key]);
    }
    const values = () => Object.fromEntries(Object.entries(controls).map(([k, el]) => [k, el.value.trim()]));
    return { el: wrap, values };
  }

  function debounce(fn, ms) {
    let t;
    return () => { clearTimeout(t); t = setTimeout(fn, ms); };
  }

  function qs(params) {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
    const s = p.toString();
    return s ? "?" + s : "";
  }

  async function projectsView() {
    const { main, alive } = mountShell("projects", { right: false });
    const newBtn = h("button", { class: "btn primary blue small", type: "button", onclick: () => projectFormModal(null) }, "New project");
    main.append(head("Projects", { right: state.me ? newBtn : null }));
    main.append(h("p", { class: "muted small", style: { padding: "0 16px" } },
      "Portfolios and showcases from developers. Tag your stack to find people building similar things."));
    const holder = h("div");
    const filters = listFilters([
      { key: "q", label: "Search projects" },
      { key: "tag", label: "Tag, e.g. rust" },
      { key: "status", label: "Status", options: [["", "Any status"], ["idea", "Idea"], ["building", "Building"], ["shipped", "Shipped"]] },
    ], () => draw());
    main.append(filters.el, holder);
    function draw() {
      const v = filters.values();
      const f = feed((next) => api("/api/projects" + qs({ ...v, before: next || "" })), {
        renderItem: projectCard, empty: "No projects match these filters yet.",
      });
      if (!alive()) return;
      holder.replaceChildren(f.el);
    }
    draw();
  }

  function projectFeed(username) {
    return feed(() => api(`/api/users/${encodeURIComponent(username)}/projects`), {
      renderItem: projectCard, empty: "No projects yet.",
    }).el;
  }

  async function projectDetailView(id) {
    const { main, alive } = mountShell("projects", { right: false });
    const data = await api("/api/projects/" + id);
    if (!alive()) return;
    const p = data.project;
    main.append(head("Project", { back: true }));
    const likeBtn = h("button", { class: "btn ghost small", type: "button" }, "");
    const drawLike = () => {
      likeBtn.textContent = `${p.liked ? "♥" : "♡"} ${p.like_count} ${p.liked ? "Liked" : "Like"}`;
      likeBtn.classList.toggle("liked", !!p.liked);
    };
    likeBtn.addEventListener("click", async () => {
      if (!requireLogin()) return;
      try {
        await api(`/api/projects/${id}/like`, { method: p.liked ? "DELETE" : "POST" });
        p.liked = !p.liked;
        p.like_count += p.liked ? 1 : -1;
        drawLike();
      } catch (e) { toast(e.message, "error"); }
    });
    drawLike();
    const actions = [likeBtn];
    if (p.mine) {
      actions.push(h("button", { class: "btn ghost small", type: "button", onclick: () => projectFormModal(p) }, "Edit"));
      actions.push(h("button", {
        class: "btn ghost small danger", type: "button",
        onclick: async () => {
          if (!confirm("Delete this project? This can't be undone.")) return;
          try { await api(`/api/projects/${id}`, { method: "DELETE" }); toast("Project deleted"); navigate("/projects"); }
          catch (e) { toast(e.message, "error"); }
        },
      }, "Delete"));
    } else if (state.me) {
      actions.push(h("button", { class: "btn ghost small", type: "button", onclick: () => startConversation(p.author.username) }, "Message owner"));
    }
    main.append(h("article", { class: "project-detail" },
      p.screenshot_url ? h("img", { class: "proj-hero", src: p.screenshot_url, alt: "Project screenshot" }) : null,
      h("div", { class: "row between wrap" }, h("h2", { class: "proj-title big" }, p.title),
        h("span", { class: "status-badge " + p.status }, STATUS_LABEL[p.status])),
      h("div", { class: "muted small" }, "by ", h("a", { href: "/u/" + p.author.username }, p.author.display_name),
        " · updated ", timeAgo(p.updated_at)),
      p.description ? h("p", { class: "proj-body" }, p.description) : null,
      h("div", { class: "chips" }, chipList(p.tags)),
      h("div", { class: "row wrap" },
        p.repo_url ? h("a", { class: "btn ghost small", href: p.repo_url, target: "_blank", rel: "noopener noreferrer nofollow" }, "⌘ Repository") : null,
        p.live_url ? h("a", { class: "btn ghost small", href: p.live_url, target: "_blank", rel: "noopener noreferrer nofollow" }, "🌐 Live site") : null),
      h("div", { class: "row wrap actions-row" }, actions)));

    const collab = await api(`/api/projects/${id}/collaborators`);
    if (!alive()) return;
    main.append(h("h3", { class: "section-title" }, "Possible collaborators"),
      h("p", { class: "muted small", style: { padding: "0 16px" } }, "Developers with other projects that share a tag with this one."),
      collab.items.length
        ? collab.items.map((c) => h("div", { class: "collab-match" }, userRow(c.user),
          h("div", { class: "small muted" }, "Shared tags: ", chipList(c.shared_tags)),
          h("div", { class: "small muted" }, "Projects: ", c.projects.map((pr, i) => [i ? ", " : "", h("a", { href: "/projects/" + pr.id }, pr.title)]))))
        : emptyBox("No matches yet", "Add tags to your project so developers with similar stacks can find it."));
  }

  function projectFormModal(existing) {
    if (!requireLogin()) return;
    const isEdit = !!existing;
    const title = field("Project name", { value: existing?.title || "", maxlength: "80", required: true, placeholder: "e.g. Tiny Compiler" });
    const desc = h("textarea", { class: "input", rows: 4, maxlength: "1000", placeholder: "What it does, what you learned…" });
    desc.value = existing?.description || "";
    const repo = field("Repository link", { value: existing?.repo_url || "", placeholder: "https://github.com/you/project", type: "url" });
    const live = field("Live link", { value: existing?.live_url || "", placeholder: "https://yourproject.dev", type: "url" });
    const tags = field("Tags (comma separated)", { value: (existing?.tags || []).join(", "), placeholder: "rust, wasm, compilers", maxlength: "200" });
    const status = h("select", { class: "input" }, [["idea", "💡 Idea"], ["building", "🚧 Building"], ["shipped", "🚀 Shipped"]]
      .map(([v, l]) => h("option", { value: v, selected: (existing?.status || "idea") === v }, l)));
    let screenshot = existing?.screenshot_url ? { url: existing.screenshot_url, id: existing.screenshot_media_id || null } : null;
    const preview = h("div", { class: "compose-previews" });
    const drawPreview = () => preview.replaceChildren(screenshot ? h("div", { class: "thumb" }, h("img", { src: screenshot.url, alt: "" }),
      h("button", { class: "thumb-x", type: "button", "aria-label": "Remove screenshot", onclick: () => { screenshot = null; drawPreview(); } }, "×")) : null);
    drawPreview();
    const fileIn = h("input", { type: "file", accept: "image/png,image/jpeg,image/gif,image/webp", hidden: true });
    fileIn.addEventListener("change", async () => {
      const f = fileIn.files[0]; fileIn.value = "";
      if (!f) return;
      try {
        const fd = new FormData(); fd.append("file", f);
        const r = await api("/api/media", { method: "POST", form: fd });
        screenshot = { url: r.url, id: r.id }; drawPreview();
      } catch (e) { toast(e.message, "error"); }
    });
    const err = h("p", { class: "error", role: "alert" });
    const save = h("button", { class: "btn primary blue", type: "submit" }, isEdit ? "Save project" : "Create project");
    const form = h("form", {
      class: "stack",
      onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        save.disabled = true;
        const body = {
          title: title.input.value.trim(), description: desc.value.trim(), repo_url: repo.input.value.trim(),
          live_url: live.input.value.trim(), tags: tags.input.value, status: status.value,
          screenshot_media_id: screenshot ? screenshot.id : null,
        };
        try {
          const r = isEdit
            ? await api(`/api/projects/${existing.id}`, { method: "PATCH", body })
            : await api("/api/projects", { method: "POST", body });
          closeModal();
          toast(isEdit ? "Project saved" : "Project created");
          navigate("/projects/" + r.project.id);
          if (isEdit) render();
        } catch (ex) { err.textContent = ex.message; save.disabled = false; }
      },
    }, title.wrap, h("label", { class: "field" }, h("span", { class: "field-label" }, "Description"), desc),
      repo.wrap, live.wrap, tags.wrap,
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Status"), status),
      h("div", { class: "row" }, h("button", { class: "btn ghost small", type: "button", onclick: () => fileIn.click() }, "Add screenshot"), fileIn),
      preview, err, save);
    openModal(h("div", {}, h("div", { class: "modal-title" }, isEdit ? "Edit project" : "New project"), form), { wide: true });
  }

  async function collabView() {
    const { main, alive } = mountShell("collab", { right: false });
    const newBtn = h("button", { class: "btn primary blue small", type: "button", onclick: () => collabFormModal(null) }, "New request");
    main.append(head("Collaborate", { right: state.me ? newBtn : null }));
    main.append(h("p", { class: "muted small", style: { padding: "0 16px" } },
      "Post a project or a skill you need, or express interest in someone else's request."));
    const holder = h("div");
    const filters = listFilters([
      { key: "q", label: "Search requests" },
      { key: "skill", label: "Skill, e.g. go" },
      { key: "status", label: "Status", options: [["open", "Open"], ["closed", "Closed"]] },
    ], () => draw());
    main.append(filters.el, holder);
    function draw() {
      const v = filters.values();
      const f = feed((next) => api("/api/collab" + qs({ ...v, before: next || "" })), {
        renderItem: collabCard, empty: "No collaboration requests match these filters.",
      });
      if (!alive()) return;
      holder.replaceChildren(f.el);
    }
    draw();
  }

  async function collabDetailView(id) {
    const { main, alive } = mountShell("collab", { right: false });
    const data = await api("/api/collab/" + id);
    if (!alive()) return;
    const r = data.request;
    main.append(head("Collaboration request", { back: true }));
    const body = h("div", { class: "project-detail" },
      h("div", { class: "row between wrap" }, h("h2", { class: "proj-title big" }, r.title),
        h("span", { class: "status-badge " + r.status }, STATUS_LABEL[r.status])),
      h("div", { class: "muted small" }, "by ", h("a", { href: "/u/" + r.author.username }, r.author.display_name),
        r.project ? [" · project: ", h("a", { href: "/projects/" + r.project.id }, r.project.title)] : null),
      r.description ? h("p", { class: "proj-body" }, r.description) : null,
      r.goals ? h("p", {}, h("b", {}, "Goals: "), r.goals) : null,
      h("div", { class: "chips" }, chipList(r.skills)));
    main.append(body);

    if (r.mine) {
      const edit = h("button", { class: "btn ghost small", type: "button", onclick: () => collabFormModal(r) }, "Edit");
      const toggle = h("button", { class: "btn ghost small", type: "button", onclick: async () => {
        try {
          await api(`/api/collab/${id}`, { method: "PATCH", body: { status: r.status === "open" ? "closed" : "open" } });
          toast("Request updated"); render();
        } catch (e) { toast(e.message, "error"); }
      } }, r.status === "open" ? "Close request" : "Reopen request");
      const del = h("button", { class: "btn ghost small danger", type: "button", onclick: async () => {
        if (!confirm("Delete this request?")) return;
        try { await api(`/api/collab/${id}`, { method: "DELETE" }); toast("Request deleted"); navigate("/collab"); }
        catch (e) { toast(e.message, "error"); }
      } }, "Delete");
      main.append(h("div", { class: "row wrap actions-row" }, edit, toggle, del));
      main.append(h("h3", { class: "section-title" }, `Interested developers (${(data.request.interests || []).length})`));
      const interests = data.request.interests || [];
      if (!interests.length) main.append(emptyBox("No one yet", "Share the request so developers can find it."));
      for (const it of interests) {
        const actions = h("div", { class: "row wrap" });
        const setStatus = async (status) => {
          try { await api(`/api/collab/${id}/interests/${it.id}`, { method: "PATCH", body: { status } }); toast(`Marked ${status}`); render(); }
          catch (e) { toast(e.message, "error"); }
        };
        if (it.status === "pending") {
          actions.append(h("button", { class: "btn primary small", type: "button", onclick: () => setStatus("accepted") }, "Accept"),
            h("button", { class: "btn ghost small", type: "button", onclick: () => setStatus("declined") }, "Decline"));
        } else {
          actions.append(h("button", { class: "btn ghost small", type: "button", onclick: () => setStatus("pending") }, "Undo"));
        }
        actions.append(h("button", { class: "btn ghost small", type: "button", onclick: () => startConversation(it.applicant.username) }, "Message"));
        main.append(h("div", { class: "interest-row" }, userRow(it.applicant),
          it.message ? h("p", { class: "interest-msg" }, it.message) : null,
          h("div", { class: "row between wrap" }, h("span", { class: "status-badge " + it.status }, it.status), actions)));
      }
      return;
    }

    if (r.my_interest) {
      main.append(h("p", { class: "muted" }, "You've expressed interest. Status: ",
        h("span", { class: "status-badge " + r.my_interest }, r.my_interest), "."));
      main.append(h("button", { class: "btn ghost small", type: "button", onclick: async () => {
        try { await api(`/api/collab/${id}/interest`, { method: "DELETE" }); toast("Interest withdrawn"); render(); }
        catch (e) { toast(e.message, "error"); }
      } }, "Withdraw interest"));
      if (r.my_interest === "accepted") {
        main.append(h("button", { class: "btn primary blue small", type: "button", onclick: () => startConversation(r.author.username) }, "Message owner"));
      }
    } else if (r.status === "open" && state.me) {
      const msg = h("textarea", { class: "input", rows: 3, maxlength: "500", placeholder: "Say hi and what you'd bring (optional)" });
      const sendBtn = h("button", { class: "btn primary blue", type: "button", onclick: async () => {
        sendBtn.disabled = true;
        try { await api(`/api/collab/${id}/interest`, { method: "POST", body: { message: msg.value.trim() } }); toast("Interest sent"); render(); }
        catch (e) { toast(e.message, "error"); sendBtn.disabled = false; }
      } }, "I'm interested");
      main.append(h("div", { class: "stack", style: { padding: "0 16px" } }, msg, sendBtn));
    } else if (!state.me) {
      main.append(h("p", { class: "muted", style: { padding: "0 16px" } }, h("a", { href: "/login" }, "Log in"), " to express interest."));
    } else {
      main.append(h("p", { class: "muted", style: { padding: "0 16px" } }, "This request is closed."));
    }
  }

  async function collabFormModal(existing) {
    if (!requireLogin()) return;
    const isEdit = !!existing;
    const title = field("Title", { value: existing?.title || "", maxlength: "100", required: true, placeholder: "e.g. Need a Go developer for a CLI" });
    const desc = h("textarea", { class: "input", rows: 4, maxlength: "2000", placeholder: "What you're building and what the collaboration looks like" });
    desc.value = existing?.description || "";
    const goals = field("Goals", { value: existing?.goals || "", maxlength: "500", placeholder: "e.g. ship v1 by December" });
    const skills = field("Skills needed (comma separated)", { value: (existing?.skills || []).join(", "), maxlength: "300", placeholder: "go, cli, testing" });
    const projectSel = h("select", { class: "input" }, h("option", { value: "" }, "No linked project"));
    try {
      const mine = await api("/api/users/" + encodeURIComponent(state.me.username) + "/projects");
      for (const p of mine.items) {
        projectSel.append(h("option", { value: p.id, selected: existing?.project?.id === p.id }, p.title));
      }
    } catch (_) { /* ignore: request still works without a project */ }
    const err = h("p", { class: "error", role: "alert" });
    const save = h("button", { class: "btn primary blue", type: "submit" }, isEdit ? "Save request" : "Post request");
    const form = h("form", {
      class: "stack",
      onsubmit: async (e) => {
        e.preventDefault();
        err.textContent = "";
        save.disabled = true;
        const body = {
          title: title.input.value.trim(), description: desc.value.trim(), goals: goals.input.value.trim(),
          skills: skills.input.value, project_id: projectSel.value ? Number(projectSel.value) : null,
        };
        try {
          const r = isEdit ? await api(`/api/collab/${existing.id}`, { method: "PATCH", body })
            : await api("/api/collab", { method: "POST", body });
          closeModal();
          toast(isEdit ? "Request saved" : "Request posted");
          navigate("/collab/" + r.request.id);
          if (isEdit) render();
        } catch (ex) { err.textContent = ex.message; save.disabled = false; }
      },
    }, title.wrap, h("label", { class: "field" }, h("span", { class: "field-label" }, "Description"), desc),
      goals.wrap, skills.wrap,
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Linked project"), projectSel),
      err, save);
    openModal(h("div", {}, h("div", { class: "modal-title" }, isEdit ? "Edit request" : "New collaboration request"), form), { wide: true });
  }

  // ------------------------------------------------------------ post editing
  function editPostModal(p) {
    const ta = h("textarea", { class: "input", rows: 4, maxlength: String(POST_MAX), "aria-label": "Post text" });
    ta.value = p.body || "";
    const codeTa = h("textarea", { class: "code-input", rows: 6, spellcheck: "false", "aria-label": "Code snippet" });
    codeTa.value = p.code || "";
    const langSel = h("select", { class: "lang-select", "aria-label": "Language" }, LANGS.map((l) => h("option", { value: l, selected: p.code_lang === l }, l)));
    const err = h("p", { class: "error", role: "alert" });
    const save = h("button", { class: "btn primary blue", type: "submit" }, "Save");
    const form = h("form", {
      class: "stack",
      onsubmit: async (e) => {
        e.preventDefault();
        save.disabled = true;
        try {
          const code = codeTa.value.replace(/\s+$/, "");
          const r = await api(`/api/posts/${p.id}`, { method: "PATCH", body: { body: ta.value.trim(), code, code_lang: code ? langSel.value : "" } });
          closeModal();
          patchPost(p.id, r.post);
          toast("Post updated");
        } catch (ex) { err.textContent = ex.message; save.disabled = false; }
      },
    }, ta, h("div", { class: "row between" }, h("span", { class: "muted small" }, "Code (optional)"), langSel), codeTa, err, save);
    openModal(h("div", {}, h("div", { class: "modal-title" }, "Edit post"), form));
  }

  // ------------------------------------------------------------ password reset
  function forgotView() {
    const { main } = mountShell("", { right: false });
    main.append(head("Reset password", { back: true }));
    const email = field("Email", { type: "email", placeholder: "you@example.com", required: true, autocomplete: "email" });
    const msg = h("p", { class: "muted", role: "status" });
    const btn = h("button", { class: "btn primary blue wide", type: "submit" }, "Send reset link");
    main.append(h("section", { class: "auth-card" },
      h("p", { class: "muted small" }, "Enter the email on your account and we'll send a link to choose a new password."),
      h("form", {
        onsubmit: async (e) => {
          e.preventDefault();
          btn.disabled = true;
          try {
            const r = await api("/api/auth/forgot", { method: "POST", body: { email: email.input.value.trim() } });
            msg.textContent = r.message;
          } catch (ex) { msg.textContent = ex.message; } finally { btn.disabled = false; }
        },
      }, email.wrap, msg, btn)));
  }

  function resetView() {
    const { main } = mountShell("", { right: false });
    const token = new URLSearchParams(location.search).get("token") || "";
    main.append(head("Choose a new password", { back: false }));
    const pass = field("New password", { type: "password", minlength: "8", maxlength: "200", autocomplete: "new-password", required: true, placeholder: "At least 8 characters" });
    const err = h("p", { class: "error", role: "alert" });
    const btn = h("button", { class: "btn primary blue wide", type: "submit" }, "Update password");
    const done = h("div", { hidden: true },
      h("p", {}, "Your password was updated. You can log in now."),
      h("a", { class: "btn primary blue wide", href: "/login" }, "Log in"));
    main.append(h("section", { class: "auth-card" },
      !token ? h("p", { class: "error" }, "This link is missing its token. Request a new reset link.") : null,
      token ? h("form", {
        onsubmit: async (e) => {
          e.preventDefault();
          err.textContent = "";
          btn.disabled = true;
          try {
            await api("/api/auth/reset", { method: "POST", body: { token, password: pass.input.value } });
            e.target.hidden = true;
            done.hidden = false;
          } catch (ex) { err.textContent = ex.message; btn.disabled = false; }
        },
      }, pass.wrap, err, btn) : null,
      done,
      h("p", { class: "muted small switch" }, h("a", { href: "/forgot" }, "Request a new link"))));
  }

  // ------------------------------------------------------------ routing
  const ROUTES = [
    [/^\/$/, () => homeView()],
    [/^\/explore$/, () => exploreView()],
    [/^\/devs$/, () => devsView()],
    [/^\/search$/, () => searchView()],
    [/^\/notifications$/, () => notificationsView()],
    [/^\/messages$/, () => messagesView()],
    [/^\/messages\/(\d+)$/, (id) => conversationView(Number(id))],
    [/^\/bookmarks$/, () => bookmarksView()],
    [/^\/settings$/, () => settingsView()],
    [/^\/login$/, () => authView("login")],
    [/^\/signup$/, () => authView("signup")],
    [/^\/u\/([A-Za-z0-9_]+)$/, (u) => profileView(u)],
    [/^\/u\/([A-Za-z0-9_]+)\/(followers|following)$/, (u, k) => followView(u, k)],
    [/^\/projects$/, () => projectsView()],
    [/^\/projects\/(\d+)$/, (id) => projectDetailView(Number(id))],
    [/^\/collab$/, () => collabView()],
    [/^\/collab\/(\d+)$/, (id) => collabDetailView(Number(id))],
    [/^\/forgot$/, () => forgotView()],
    [/^\/reset$/, () => resetView()],
    [/^\/post\/(\d+)$/, (id) => postView(Number(id))],
  ];

  async function render() {
    const path = location.pathname.replace(/\/+$/, "") || "/";
    for (const [re, fn] of ROUTES) {
      const m = path.match(re);
      if (!m) continue;
      try {
        await fn(...m.slice(1));
      } catch (e) {
        const { main } = mountShell("", { right: false });
        main.append(head("Error", { back: true }), errorBox(e.message));
      }
      return;
    }
    notFound();
  }

  // ------------------------------------------------------------ global events
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href]");
    if (!a || a.target === "_blank" || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    const href = a.getAttribute("href");
    if (href.startsWith("/") && !href.startsWith("//") && !href.startsWith("/api") && !href.startsWith("/media")) {
      e.preventDefault();
      navigate(href);
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeMenus(); closeModal(); return; }
    if (e.target.matches("input, textarea, select, [contenteditable]")) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "n" && state.me) { e.preventDefault(); openComposer(); }
    if (e.key === "/") {
      const s = document.querySelector("input[type=search]");
      if (s) { e.preventDefault(); s.focus(); }
    }
  });

  window.addEventListener("popstate", render);

  // ------------------------------------------------------------ boot
  (async function boot() {
    let theme = "dark";
    try { theme = localStorage.getItem("devx-theme") || "dark"; } catch (_) { /* ignore */ }
    document.documentElement.dataset.theme = theme;
    try {
      state.me = (await api("/api/auth/me")).user;
    } catch (_) {
      state.me = null;
    }
    await render();
    refreshCounts();
    setInterval(refreshCounts, 15000);
  })();
})();
