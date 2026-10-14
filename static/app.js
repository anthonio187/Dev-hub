/* DevHub — frontend logic (all pages) */
"use strict";

const $ = (sel) => document.querySelector(sel);
const page = document.body.dataset.page;
const profileUsername = document.body.dataset.username || "";

const STATUS_META = {
  idea:        { label: "Idea",        icon: "💡", cls: "badge-idea" },
  in_progress: { label: "In progress", icon: "🚧", cls: "badge-progress" },
  shipped:     { label: "Shipped",     icon: "🚀", cls: "badge-shipped" },
};

const AVATARS = ["🧑‍💻", "👩‍💻", "👨‍💻", "🦄", "🐙", "🦊", "🐸", "🐼",
                 "🦉", "🚀", "🤖", "👾", "🐍", "☕", "⚡", "🌟"];

/* ---------- utilities ---------- */

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: options.body ? { "Content-Type": "application/json" } : {},
    ...options,
  });
  let data = {};
  try { data = await res.json(); } catch (_) { /* empty body */ }
  if (!res.ok) {
    const err = new Error(data.error || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

let toastTimer;
function toast(message, ok = true) {
  let el = $("#toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.className = ok ? "ok" : "err";
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

function fmtDate(iso) {
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function timeAgo(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 7 * 86400) return `${Math.floor(s / 86400)}d ago`;
  return fmtDate(iso);
}

function isEdited(p) {
  const c = new Date(p.created_at).getTime();
  const u = new Date(p.updated_at).getTime();
  return u - c > 120000;
}

/* Markdown-lite: **bold**, *italic*, `code`, [text](url), bare links. Escapes first. */
function md(text) {
  let s = esc(text);
  const tokens = [];
  s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (_m, label, url) => {
    tokens.push(`<a href="${url}" target="_blank" rel="noopener">${label}</a>`);
    return `\x00${tokens.length - 1}\x00`;
  });
  s = s.replace(/(^|[\s>])(https?:\/\/[^\s<]+)/g, (_m, pre, url) => {
    tokens.push(`<a href="${url}" target="_blank" rel="noopener">${url}</a>`);
    return `${pre}\x00${tokens.length - 1}\x00`;
  });
  s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  s = s.replace(/\x00(\d+)\x00/g, (_m, i) => tokens[Number(i)]);
  return s;
}

function techList(tech) {
  return (tech || "").split(",").map((t) => t.trim()).filter(Boolean).slice(0, 8);
}

function techChips(tech) {
  return techList(tech)
    .map((t) => `<span class="chip" data-tech="${esc(t)}">${esc(t)}</span>`)
    .join("");
}

function statusBadge(status) {
  const meta = STATUS_META[status] || STATUS_META.in_progress;
  return `<span class="badge ${meta.cls}">${meta.icon} ${esc(meta.label)}</span>`;
}

function avatarHtml(a, size = "") {
  return `<span class="avatar ${size}" title="${esc(a?.display_name || a?.username || "")}">${esc(a?.avatar || "🧑‍💻")}</span>`;
}

function authorLink(p) {
  if (!p.author) return "";
  return `<a href="/u/${esc(p.author.username)}">${esc(p.author.display_name)}</a>`;
}

function progressBar(p) {
  if (!p.progress) return "";
  return `<div class="progress" title="${p.progress}% complete"><span style="width:${Number(p.progress) || 0}%"></span></div>`;
}

function projectCard(p, mine = false) {
  const links = [];
  if (p.repo_url) links.push(`<a href="${esc(p.repo_url)}" target="_blank" rel="noopener">📦 Code</a>`);
  if (p.live_url) links.push(`<a href="${esc(p.live_url)}" target="_blank" rel="noopener">🔗 Live</a>`);
  const edited = isEdited(p) ? ` <span class="muted" title="Updated ${timeAgo(p.updated_at)}">(edited)</span>` : "";
  const likeBtn = `<button type="button" class="like-btn${p.liked_by_me ? " liked" : ""}" data-like="${p.id}"
        title="${p.liked_by_me ? "Unlike" : "Like"}">❤️ <span class="lc">${p.likes}</span></button>`;
  const commentBtn = `<button type="button" data-open="${p.id}" title="Comments">💬 ${p.comments_count}</button>`;
  const shareBtn = `<button type="button" data-share="${p.id}" title="Copy share link">🔗</button>`;
  const saveBtn = `<button type="button" class="save-btn${p.bookmarked_by_me ? " liked" : ""}" data-save="${p.id}" title="${p.bookmarked_by_me ? "Remove bookmark" : "Save for later"}">${p.bookmarked_by_me ? "🔖" : "📑"}</button>`;
  const pinBadge = p.pinned ? `<span class="badge badge-pin" title="Pinned">📌 Pinned</span>` : "";
  const actions = mine
    ? `<div class="actions">
         <button class="btn small ghost" data-edit="${p.id}">✏️ Edit</button>
         <button class="btn small ghost" data-pin="${p.id}">${p.pinned ? "📍 Unpin" : "📌 Pin"}</button>
         <button class="btn small danger" data-delete="${p.id}">🗑️</button>
       </div>`
    : "";
  return `
  <article class="card project" data-open="${p.id}">
    ${p.cover_url ? `<img class="cover" src="${esc(p.cover_url)}" alt="" loading="lazy">` : ""}
    <div class="project-top">
      <h3>${esc(p.name)}</h3>
      <span style="display:flex;gap:6px;flex:none;">${pinBadge}${statusBadge(p.status)}</span>
    </div>
    <div class="byline">${avatarHtml(p.author, "sm")} <span>by</span> ${authorLink(p)} <span>· ${timeAgo(p.created_at)}${edited}</span></div>
    ${p.description ? `<p class="desc">${esc(p.description.length > 180 ? p.description.slice(0, 180) + "…" : p.description)}</p>` : ""}
    ${progressBar(p)}
    ${techChips(p.tech) ? `<div class="chips">${techChips(p.tech)}</div>` : ""}
    <div class="project-foot">
      <div class="card-stats">${likeBtn}${commentBtn}${shareBtn}${saveBtn}<span title="Views">👁️ ${p.views}</span></div>
      <div class="links">${links.join("")}</div>
    </div>
    ${actions}
  </article>`;
}

/* ---------- theme ---------- */

function initTheme() {
  const saved = localStorage.getItem("devhub-theme");
  if (saved === "light") document.documentElement.dataset.theme = "light";
  updateThemeBtn();
  $("#theme-btn")?.addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme === "light" ? "light" : "dark";
    const next = cur === "light" ? "dark" : "light";
    if (next === "light") document.documentElement.dataset.theme = "light";
    else delete document.documentElement.dataset.theme;
    localStorage.setItem("devhub-theme", next);
    updateThemeBtn();
  });
  // broken remote images → hide gracefully
  document.addEventListener("error", (e) => {
    if (e.target && e.target.tagName === "IMG") e.target.style.display = "none";
  }, true);
}

function updateThemeBtn() {
  const btn = $("#theme-btn");
  if (btn) btn.textContent = document.documentElement.dataset.theme === "light" ? "🌙" : "☀️";
}

/* ---------- modal (project detail + shortcuts) ---------- */

function ensureOverlays() {
  if (!$("#modal-backdrop")) {
    document.body.insertAdjacentHTML("beforeend",
      `<div id="modal-backdrop" hidden><div id="modal" class="card"></div></div>`);
    $("#modal-backdrop").addEventListener("click", (e) => {
      if (e.target.id === "modal-backdrop") closeModal();
    });
  }
}

function closeModal() {
  const bd = $("#modal-backdrop");
  if (bd) bd.hidden = true;
}

function openModalHTML(html) {
  ensureOverlays();
  $("#modal").innerHTML = html;
  $("#modal-backdrop").hidden = false;
}

let modalProject = null;

async function openProjectModal(id) {
  id = Number(id);
  if (!id) return;
  try {
    const [{ project }, commentsData] = await Promise.all([
      api(`/api/projects/${id}`),
      api(`/api/projects/${id}/comments`),
    ]);
    modalProject = project;
    renderProjectModal(project, commentsData.comments);
  } catch (err) {
    toast(err.message, false);
  }
}

function renderProjectModal(p, comments) {
  const links = [];
  if (p.repo_url) links.push(`<a class="btn ghost small" href="${esc(p.repo_url)}" target="_blank" rel="noopener">📦 Code</a>`);
  if (p.live_url) links.push(`<a class="btn ghost small" href="${esc(p.live_url)}" target="_blank" rel="noopener">🔗 Live</a>`);
  const isSelf = me && p.author && me.username === p.author.username;
  const followBtn = me && !isSelf
    ? `<button class="btn ghost small" data-follow="${esc(p.author.username)}">➕ Follow</button>`
    : "";
  const edited = isEdited(p) ? ` <span class="muted">(edited)</span>` : "";
  const commentItems = comments.map((c) => `
    <div class="comment">
      ${avatarHtml(c.author, "sm")}
      <div class="comment-body">
        <div class="comment-head">
          <span class="who">${esc(c.author.display_name)}</span>
          <span class="muted small">${timeAgo(c.created_at)}</span>
          ${c.mine ? `<button type="button" class="btn small ghost" data-del-comment="${c.id}">🗑️</button>` : ""}
        </div>
        ${esc(c.body)}
      </div>
    </div>`).join("");

  openModalHTML(`
    ${p.cover_url ? `<img class="cover" src="${esc(p.cover_url)}" alt="">` : ""}
    <div class="modal-top">
      <h2>${esc(p.name)}</h2>
      <span style="display:flex;gap:6px;flex:none;">${p.pinned ? `<span class="badge badge-pin">📌</span>` : ""}${statusBadge(p.status)}</span>
    </div>
    <div class="modal-byline">
      ${avatarHtml(p.author, "mid")}
      <div>
        <div><a href="/u/${esc(p.author.username)}"><strong>${esc(p.author.display_name)}</strong></a> <span class="muted">@${esc(p.author.username)}</span></div>
        <div class="modal-stats">🕒 ${timeAgo(p.created_at)}${edited} · 👁️ ${p.views} views · ❤️ <span data-likes-count="${p.id}">${p.likes}</span> · 💬 ${comments.length}</div>
      </div>
      ${followBtn}
    </div>
    <div class="modal-desc">${p.description ? md(p.description) : "<span class='muted'>No description yet.</span>"}</div>
    ${progressBar(p)}
    ${techChips(p.tech) ? `<div class="chips" style="margin-top:10px;">${techChips(p.tech)}</div>` : ""}
    <div class="modal-actions">
      ${links.join("")}
      <button class="btn ghost small like-btn${p.liked_by_me ? " liked" : ""}" data-like="${p.id}" type="button">❤️ <span class="lc">${p.likes}</span></button>
      <button class="btn ghost small" data-share="${p.id}" type="button">🔗 Share</button>
      <button class="btn ghost small" id="modal-close" type="button">✖ Close</button>
    </div>
    <h3>💬 Comments (${comments.length})</h3>
    <div id="modal-comments">${commentItems || `<p class="muted small">No comments yet. Start the conversation!</p>`}</div>
    ${me
      ? `<form id="comment-form" class="comment-form">
           <textarea maxlength="500" required placeholder="Add a comment… (max 500 chars)"></textarea>
           <div class="form-actions"><button class="btn primary small" type="submit">Post comment</button></div>
         </form>`
      : `<p class="muted small"><a href="/#auth-section">Log in</a> to like, comment and follow.</p>`}
  `);

  $("#modal-close").addEventListener("click", closeModal);
  $("#comment-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const ta = e.target.querySelector("textarea");
    const body = ta.value.trim();
    if (!body) return;
    try {
      const data = await api(`/api/projects/${p.id}/comments`, {
        method: "POST", body: JSON.stringify({ body }),
      });
      const list = $("#modal-comments");
      if (list.querySelector("p.muted")) list.innerHTML = "";
      list.insertAdjacentHTML("beforeend", `
        <div class="comment">
          ${avatarHtml(data.comment.author, "sm")}
          <div class="comment-body">
            <div class="comment-head">
              <span class="who">${esc(data.comment.author.display_name)}</span>
              <span class="muted small">just now</span>
              <button type="button" class="btn small ghost" data-del-comment="${data.comment.id}">🗑️</button>
            </div>
            ${esc(data.comment.body)}
          </div>
        </div>`);
      ta.value = "";
      modalProject && (modalProject.comments_count = (modalProject.comments_count || 0) + 1);
      updateCommentCounts(p.id, modalProject ? modalProject.comments_count : null);
      toast("Comment posted 💬");
    } catch (err) {
      toast(err.message, false);
    }
  });
}

function updateCommentCounts(projectId) {
  const p = findProject(projectId);
  if (!p) return;
  document.querySelectorAll(`.project[data-open="${projectId}"]`).forEach((card) => {
    const btn = card.querySelector(".card-stats button[data-open]");
    if (btn) btn.innerHTML = `💬 ${p.comments_count}`;
  });
  const head = document.querySelector("#modal .modal-stats");
  if (head && modalProject && modalProject.id === projectId) {
    head.innerHTML = head.innerHTML.replace(/💬 \d+/, `💬 ${p.comments_count}`);
  }
}

function findProject(id) {
  return showcase.find((x) => x.id === id)
      || myProjects.find((x) => x.id === id)
      || (modalProject && modalProject.id === id ? modalProject : null);
}

function openShortcuts() {
  openModalHTML(`
    <div class="modal-top"><h2>⌨️ Keyboard shortcuts</h2></div>
    <div class="shortcut-row"><span>Focus search</span><span class="kbd">/</span></div>
    <div class="shortcut-row"><span>New project</span><span class="kbd">N</span></div>
    <div class="shortcut-row"><span>This help</span><span class="kbd">?</span></div>
    <div class="shortcut-row"><span>Close dialogs</span><span class="kbd">Esc</span></div>
    <div class="form-actions" style="margin-top:14px;"><button class="btn primary small" id="modal-close" type="button">Got it</button></div>
  `);
  $("#modal-close").addEventListener("click", closeModal);
}

/* ---------- shared state & nav ---------- */

let me = null;
let followingIds = new Set();
let showcase = [];
let myProjects = [];
let visibleCount = PAGE_SIZE;
let sortMode = "newest";
let followOnly = false;
let unread = 0;
let techFilter = null;

async function loadMe() {
  try {
    const data = await api("/api/me");
    me = data.authenticated ? data.user : null;
    unread = data.authenticated ? (data.unread || 0) : 0;
  } catch (_) {
    me = null;
    unread = 0;
  }
  return me;
}

async function loadFollowing() {
  if (!me) { followingIds = new Set(); return; }
  try {
    const data = await api("/api/me/following");
    followingIds = new Set(data.following.map((u) => u.username));
  } catch (_) {
    followingIds = new Set();
  }
}

async function doLogout() {
  try { await api("/api/logout", { method: "POST" }); } catch (_) { /* ignore */ }
  window.location.reload();
}

function renderNav() {
  const nav = $("#nav-auth");
  if (!nav) return;
  nav.innerHTML = me
    ? `<a class="btn ghost small" href="/saved" title="Saved projects">🔖</a>
       <a class="btn ghost small" href="/notifications" title="Notifications">🔔${unread ? ` <b>${unread > 99 ? "99+" : unread}</b>` : ""}</a>
       <span class="chip user-chip" title="@${esc(me.username)}">${esc(me.avatar)} @${esc(me.username)}</span>
       ${page !== "dashboard" ? `<a class="btn primary" href="/dashboard">Dashboard</a>` : ""}`
    : `<a class="btn ghost" href="/#auth-section">Log in</a>`;
  document.querySelectorAll(".nav-links a").forEach((a) => {
    if (a.dataset.nav === page) a.setAttribute("aria-current", "page");
  });
}

/* ---------- global click handling ---------- */

function updateLikeButtons(projectId, liked, count) {
  document.querySelectorAll(`[data-like="${projectId}"]`).forEach((btn) => {
    btn.classList.toggle("liked", liked);
    const lc = btn.querySelector(".lc");
    if (lc) lc.textContent = count;
    btn.title = liked ? "Unlike" : "Like";
  });
  const mc = document.querySelector(`[data-likes-count="${projectId}"]`);
  if (mc) mc.textContent = count;
}

async function handleLike(btn) {
  if (!me) { toast("Log in to like projects ❤️", false); return; }
  const id = Number(btn.dataset.like);
  try {
    const data = await api(`/api/projects/${id}/like`, { method: "POST" });
    for (const list of [showcase, myProjects]) {
      const p = list.find((x) => x.id === id);
      if (p) { p.liked_by_me = data.liked; p.likes = data.likes; }
    }
    if (modalProject && modalProject.id === id) { modalProject.liked_by_me = data.liked; modalProject.likes = data.likes; }
    updateLikeButtons(id, data.liked, data.likes);
    if (sortMode === "likes" && page === "landing") renderShowcase();
  } catch (err) {
    toast(err.message, false);
  }
}

async function handleSave(btn) {
  if (!me) { toast("Log in to save projects 🔖", false); return; }
  const id = Number(btn.dataset.save);
  try {
    const data = await api(`/api/projects/${id}/bookmark`, { method: "POST" });
    document.querySelectorAll(`[data-save="${id}"]`).forEach((b) => {
      b.classList.toggle("liked", data.bookmarked);
      b.textContent = data.bookmarked ? "🔖" : "📑";
      b.title = data.bookmarked ? "Remove bookmark" : "Save for later";
    });
    for (const list of [showcase, myProjects]) {
      const p = list.find((x) => x.id === id);
      if (p) p.bookmarked_by_me = data.bookmarked;
    }
    if (page === "saved" && !data.bookmarked) initSaved();
    toast(data.bookmarked ? "Saved 🔖" : "Removed from saved");
  } catch (err) {
    toast(err.message, false);
  }
}

async function handleShare(btn) {
  const id = Number(btn.dataset.share);
  const url = `${window.location.origin}/?project=${id}`;
  try {
    await navigator.clipboard.writeText(url);
    toast("Link copied to clipboard 🔗");
  } catch (_) {
    window.prompt("Copy this link:", url);
  }
}

async function handleFollow(btn) {
  if (!me) { toast("Log in to follow developers 👥", false); return; }
  const username = btn.dataset.follow;
  try {
    const data = await api(`/api/users/${encodeURIComponent(username)}/follow`, { method: "POST" });
    if (data.following) followingIds.add(username); else followingIds.delete(username);
    document.querySelectorAll(`[data-follow="${CSS.escape(username)}"]`).forEach((b) => {
      b.textContent = data.following ? "✅ Following" : "➕ Follow";
      b.classList.toggle("toggled", data.following);
    });
    document.querySelectorAll(`[data-followers-of="${CSS.escape(username)}"]`).forEach((el) => {
      el.textContent = data.followers;
    });
    toast(data.following ? `Following @${username} 🎉` : `Unfollowed @${username}`);
    if (followOnly && page === "landing") renderShowcase();
  } catch (err) {
    toast(err.message, false);
  }
}

async function handleDelete(btn) {
  const id = Number(btn.dataset.delete);
  const p = myProjects.find((x) => x.id === id);
  if (!confirm(`Delete “${p ? p.name : "this project"}”? This cannot be undone.`)) return;
  try {
    await api(`/api/projects/${id}`, { method: "DELETE" });
    toast("Project deleted 🗑️");
    if (editingId === id) resetForm();
    await loadMyProjects();
  } catch (err) {
    toast(err.message, false);
  }
}

function handleEdit(btn) {
  const p = myProjects.find((x) => x.id === Number(btn.dataset.edit));
  if (p) fillForm(p);
}

async function handlePin(btn) {
  const id = Number(btn.dataset.pin);
  try {
    const data = await api(`/api/projects/${id}/pin`, { method: "POST" });
    const p = myProjects.find((x) => x.id === id);
    if (p) p.pinned = data.pinned;
    myProjects.sort((a, b) => (b.pinned - a.pinned) || new Date(b.created_at) - new Date(a.created_at));
    renderMyProjects();
    toast(data.pinned ? "Pinned to top 📌" : "Unpinned 📍");
  } catch (err) {
    toast(err.message, false);
  }
}

async function handleDeleteComment(btn) {
  if (!confirm("Delete this comment?")) return;
  try {
    await api(`/api/comments/${Number(btn.dataset.delComment)}`, { method: "DELETE" });
    btn.closest(".comment")?.remove();
    if (modalProject) modalProject.comments_count = Math.max(0, (modalProject.comments_count || 1) - 1);
    toast("Comment deleted 🗑️");
  } catch (err) {
    toast(err.message, false);
  }
}

function globalClickHandler(e) {
  const delComment = e.target.closest("[data-del-comment]");
  if (delComment) return handleDeleteComment(delComment);
  const likeBtn = e.target.closest("[data-like]");
  if (likeBtn) return handleLike(likeBtn);
  const saveBtn = e.target.closest("[data-save]");
  if (saveBtn) { e.stopPropagation(); return handleSave(saveBtn); }
  const shareBtn = e.target.closest("[data-share]");
  if (shareBtn) return handleShare(shareBtn);
  const folBtn = e.target.closest("[data-follow]");
  if (folBtn) return handleFollow(folBtn);
  const delBtn = e.target.closest("[data-delete]");
  if (delBtn) return handleDelete(delBtn);
  const editBtn = e.target.closest("[data-edit]");
  if (editBtn) return handleEdit(editBtn);
  const pinBtn = e.target.closest("[data-pin]");
  if (pinBtn) return handlePin(pinBtn);
  const avatarChoice = e.target.closest("[data-avatar-choice]");
  if (avatarChoice) return selectAvatar(avatarChoice);
  const chip = e.target.closest(".chip[data-tech]");
  if (chip && page === "landing") return setTechFilter(chip.dataset.tech);
  if (e.target.closest("a")) return;
  const openEl = e.target.closest("[data-open]");
  if (openEl) return openProjectModal(openEl.dataset.open);
}

/* ---------- landing page ---------- */

function renderShowcase() {
  const grid = $("#showcase-grid");
  if (!grid) return;
  const q = ($("#search")?.value || "").toLowerCase();
  const status = $("#status-filter")?.value || "";
  let list = showcase.slice();

  if (q) {
    list = list.filter((p) => {
      const hay = `${p.name} ${p.description} ${p.tech} ${p.author?.display_name || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }
  if (status) list = list.filter((p) => p.status === status);
  if (followOnly) list = list.filter((p) => p.author && followingIds.has(p.author.username));
  if (techFilter) {
    list = list.filter((p) => techList(p.tech).some((t) => t.toLowerCase() === techFilter.toLowerCase()));
  }

  list.sort((a, b) => {
    switch (sortMode) {
      case "oldest": return new Date(a.created_at) - new Date(b.created_at);
      case "likes": return b.likes - a.likes;
      case "views": return b.views - a.views;
      case "name": return a.name.localeCompare(b.name);
      default: return new Date(b.created_at) - new Date(a.created_at);
    }
  });

  const shown = list.slice(0, visibleCount);
  const loadMoreBtn = $("#load-more");
  if (loadMoreBtn) {
    loadMoreBtn.hidden = list.length <= visibleCount;
    if (!loadMoreBtn.hidden) {
      loadMoreBtn.textContent = `Load more (${list.length - visibleCount} remaining)`;
    }
  }

  const activeTech = $("#active-tech");
  if (activeTech) {
    if (techFilter) {
      activeTech.hidden = false;
      activeTech.innerHTML = `Filtering by tech: <span class="chip">${esc(techFilter)}<span class="x" title="Clear filter">✕</span></span>`;
    } else {
      activeTech.hidden = true;
      activeTech.innerHTML = "";
    }
  }

  if (!shown.length) {
    grid.innerHTML = `<p class="muted empty">${
      showcase.length ? "No projects match your filters. 🔎" : "No projects yet — be the first to add one! 🎉"
    }</p>`;
    return;
  }
  grid.innerHTML = shown.map((p) => projectCard(p)).join("");
}

function setTechFilter(tech) {
  techFilter = techFilter === tech ? null : tech;
  visibleCount = PAGE_SIZE;
  renderShowcase();
}

async function loadGlobalStats() {
  const el = $("#global-stats");
  if (!el) return;
  try {
    const s = await api("/api/stats");
    const items = [
      [s.developers, "👩‍💻 Developers"],
      [s.projects, "📁 Projects"],
      [s.shipped, "🚀 Shipped"],
      [s.likes, "❤️ Likes"],
      [s.comments, "💬 Comments"],
    ];
    el.innerHTML = items
      .map(([n, lbl]) => `<div class="stat"><span class="num">${n}</span><span class="lbl">${lbl}</span></div>`)
      .join("");
  } catch (_) { /* stats are cosmetic */ }
}

async function loadShowcase() {
  const grid = $("#showcase-grid");
  if (!grid) return;
  grid.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    const data = await api("/api/projects");
    showcase = data.projects;
    renderShowcase();
  } catch (err) {
    grid.innerHTML = `<p class="muted empty">Could not load showcase: ${esc(err.message)}</p>`;
  }
}

async function initLanding() {
  const form = $("#auth-form");
  const tabLogin = $("#tab-login");
  const tabSignup = $("#tab-signup");
  const submitBtn = form.querySelector('button[type="submit"]');
  const hint = $("#auth-hint");
  let mode = "login";

  function setMode(next) {
    mode = next;
    tabLogin.classList.toggle("active", mode === "login");
    tabSignup.classList.toggle("active", mode === "signup");
    submitBtn.textContent = mode === "login" ? "Log in" : "Create account";
    hint.textContent = mode === "login"
      ? "New here? Switch to “Create account”."
      : "Username: 3–30 chars (letters, numbers, _). Password: at least 6 chars.";
  }
  tabLogin.addEventListener("click", () => setMode("login"));
  tabSignup.addEventListener("click", () => setMode("signup"));
  setMode("login");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    submitBtn.disabled = true;
    try {
      await api(mode === "login" ? "/api/login" : "/api/signup", {
        method: "POST",
        body: JSON.stringify({
          username: $("#auth-username").value.trim(),
          password: $("#auth-password").value,
        }),
      });
      window.location.href = "/dashboard";
    } catch (err) {
      toast(err.message, false);
      submitBtn.disabled = false;
    }
  });

  $("#search")?.addEventListener("input", () => { visibleCount = PAGE_SIZE; renderShowcase(); });
  $("#status-filter")?.addEventListener("change", () => { visibleCount = PAGE_SIZE; renderShowcase(); });
  $("#sort")?.addEventListener("change", (e) => { sortMode = e.target.value; renderShowcase(); });
  $("#load-more")?.addEventListener("click", () => { visibleCount += PAGE_SIZE; renderShowcase(); });
  $("#follow-toggle")?.addEventListener("click", (e) => {
    if (!me) { toast("Create an account to follow developers 👥", false); return; }
    followOnly = !followOnly;
    e.currentTarget.classList.toggle("toggled", followOnly);
    visibleCount = PAGE_SIZE;
    renderShowcase();
  });
  $("#active-tech")?.addEventListener("click", (e) => {
    if (e.target.closest(".x")) { techFilter = null; renderShowcase(); }
  });

  renderNav();
  if (me) {
    await loadFollowing();
    const authSection = $("#auth-section");
    authSection.innerHTML = `
      <div class="logged-in">
        <p>👋 Welcome back, <strong>@${esc(me.username)}</strong>!</p>
        <a class="btn primary" href="/dashboard">Go to your dashboard</a>
      </div>`;
  }
  loadGlobalStats();
  loadShowcase().then(() => {
    const pid = new URLSearchParams(window.location.search).get("project");
    if (pid) openProjectModal(pid);
  });
}

/* ---------- dashboard ---------- */

let editingId = null;
let chosenAvatar = null;

function renderStats() {
  const el = $("#stats");
  if (!el) return;
  const count = (s) => myProjects.filter((p) => p.status === s).length;
  const views = myProjects.reduce((acc, p) => acc + (p.views || 0), 0);
  const likes = myProjects.reduce((acc, p) => acc + (p.likes || 0), 0);
  const items = [
    [myProjects.length, "📁 Total projects"],
    [count("shipped"), "🚀 Shipped"],
    [count("in_progress"), "🚧 In progress"],
    [count("idea"), "💡 Ideas"],
    [views, "👁️ Views"],
    [likes, "❤️ Likes received"],
  ];
  el.innerHTML = items
    .map(([n, lbl]) => `<div class="stat"><span class="num">${n}</span><span class="lbl">${lbl}</span></div>`)
    .join("");
}

function renderMyProjects() {
  const grid = $("#my-grid");
  if (!myProjects.length) {
    grid.innerHTML = `<p class="muted empty">No projects yet. Add your first one above! 👆</p>`;
    return;
  }
  grid.innerHTML = myProjects.map((p) => projectCard({ ...p, author: null }, true)).join("");
}

function initAvatarPicker(current) {
  chosenAvatar = current || "🧑‍💻";
  const picker = $("#avatar-picker");
  if (!picker) return;
  picker.innerHTML = AVATARS.map((a) =>
    `<button type="button" data-avatar-choice="${a}" class="${a === chosenAvatar ? "active" : ""}" title="${a}">${a}</button>`
  ).join("");
}

function selectAvatar(btn) {
  chosenAvatar = btn.dataset.avatarChoice;
  document.querySelectorAll("#avatar-picker button").forEach((b) =>
    b.classList.toggle("active", b === btn));
}

function resetForm() {
  editingId = null;
  $("#project-form").reset();
  $("#p-status").value = "in_progress";
  $("#p-progress").value = 0;
  $("#progress-val").textContent = "0%";
  $("#desc-counter").textContent = "0 / 2000";
  $("#form-title").textContent = "Add a project";
  $("#project-submit").textContent = "Add project";
  $("#cancel-edit").hidden = true;
}

function fillForm(p) {
  editingId = p.id;
  $("#p-name").value = p.name;
  $("#p-status").value = p.status;
  $("#p-tech").value = p.tech;
  $("#p-cover").value = p.cover_url || "";
  $("#p-repo").value = p.repo_url;
  $("#p-live").value = p.live_url;
  $("#p-progress").value = p.progress || 0;
  $("#progress-val").textContent = `${p.progress || 0}%`;
  $("#p-desc").value = p.description;
  $("#desc-counter").textContent = `${p.description.length} / 2000`;
  $("#form-title").textContent = `Edit “${p.name}”`;
  $("#project-submit").textContent = "Save changes";
  $("#cancel-edit").hidden = false;
  $("#form-title").scrollIntoView({ behavior: "smooth", block: "center" });
}

async function loadMyProjects() {
  try {
    const data = await api("/api/my/projects");
    myProjects = data.projects;
    renderStats();
    renderMyProjects();
  } catch (err) {
    toast(err.message, false);
  }
}

function projectPayload() {
  return {
    name: $("#p-name").value.trim(),
    status: $("#p-status").value,
    tech: $("#p-tech").value.trim(),
    cover_url: $("#p-cover").value.trim(),
    repo_url: $("#p-repo").value.trim(),
    live_url: $("#p-live").value.trim(),
    progress: Number($("#p-progress").value) || 0,
    description: $("#p-desc").value.trim(),
  };
}

function initDashboard() {
  loadMe().then(async () => {
    if (!me) {
      window.location.href = "/";
      return;
    }
    renderNav();
    await loadFollowing();
    initAvatarPicker(me.avatar);
    $("#display_name").value = me.display_name || me.username;
    $("#bio").value = me.bio || "";
  });

  $("#p-progress").addEventListener("input", (e) => {
    $("#progress-val").textContent = `${e.target.value}%`;
  });
  $("#p-desc").addEventListener("input", (e) => {
    $("#desc-counter").textContent = `${e.target.value.length} / 2000`;
  });

  $("#project-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("#project-submit");
    btn.disabled = true;
    try {
      if (editingId) {
        await api(`/api/projects/${editingId}`, { method: "PUT", body: JSON.stringify(projectPayload()) });
        toast("Project updated ✅");
      } else {
        await api("/api/projects", { method: "POST", body: JSON.stringify(projectPayload()) });
        toast("Project added 🎉");
      }
      resetForm();
      await loadMyProjects();
    } catch (err) {
      toast(err.message, false);
    } finally {
      btn.disabled = false;
    }
  });

  $("#cancel-edit").addEventListener("click", resetForm);

  $("#profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = await api("/api/me", {
        method: "PUT",
        body: JSON.stringify({
          display_name: $("#display_name").value.trim(),
          bio: $("#bio").value.trim(),
          avatar: chosenAvatar,
        }),
      });
      me = data.user;
      renderNav();
      toast("Profile saved ✅");
    } catch (err) {
      toast(err.message, false);
    }
  });

  $("#password-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/me/password", {
        method: "PUT",
        body: JSON.stringify({
          current_password: $("#cur-pass").value,
          new_password: $("#new-pass").value,
        }),
      });
      e.target.reset();
      toast("Password changed 🔑");
    } catch (err) {
      toast(err.message, false);
    }
  });

  $("#delete-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!confirm("Really delete your account and ALL your data? This cannot be undone.")) return;
    try {
      await api("/api/me", {
        method: "DELETE",
        body: JSON.stringify({ password: $("#del-pass").value }),
      });
      toast("Account deleted. Goodbye 👋");
      setTimeout(() => { window.location.href = "/"; }, 900);
    } catch (err) {
      toast(err.message, false);
    }
  });

  loadMyProjects();
}

/* ---------- profile page ---------- */

async function initProfile() {
  const head = $("#profile-head");
  const grid = $("#user-grid");
  try {
    const [data] = await Promise.all([api(`/api/users/${encodeURIComponent(profileUsername)}`), loadMe()]);
    const u = data.user;
    const isSelf = me && me.username === u.username;
    renderNav();
    head.innerHTML = `
      <div class="profile-id">
        ${avatarHtml(u, "big")}
        <div>
          <h1>${esc(u.display_name)} <span class="muted">@${esc(u.username)}</span></h1>
          <p class="muted" style="margin:0;">${u.bio ? esc(u.bio) : "<em>No bio yet.</em>"}</p>
          <p class="muted small" style="margin:6px 0 0;">📅 Joined ${fmtDate(u.created_at)}</p>
        </div>
      </div>
      <div>
        <div class="profile-stats">
          <span class="pstat"><span class="num">${data.stats.projects}</span><span class="lbl">Projects</span></span>
          <span class="pstat"><span class="num">${data.stats.shipped}</span><span class="lbl">Shipped</span></span>
          <span class="pstat"><span class="num" data-followers-of="${esc(u.username)}">${data.stats.followers}</span><span class="lbl">Followers</span></span>
          <span class="pstat"><span class="num">${data.stats.following}</span><span class="lbl">Following</span></span>
          <span class="pstat"><span class="num">${data.stats.likes_received}</span><span class="lbl">❤️</span></span>
        </div>
        ${!isSelf ? `<div class="form-actions" style="margin-top:12px;">
          ${me
            ? `<button class="btn ${data.following ? "ghost toggled" : "primary"}" data-follow="${esc(u.username)}" type="button">${data.following ? "✅ Following" : "➕ Follow"}</button>`
            : `<a class="btn primary" href="/#auth-section">Log in to follow</a>`}
        </div>` : `<div class="form-actions" style="margin-top:12px;"><a class="btn ghost" href="/dashboard">⚙️ Manage my projects</a></div>`}
      </div>`;
    grid.innerHTML = data.projects.length
      ? data.projects.map((p) => projectCard(p)).join("")
      : `<p class="muted empty">No projects yet. 💤</p>`;
  } catch (err) {
    head.innerHTML = `<p class="muted">${esc(err.message)}</p>`;
    grid.innerHTML = "";
  }
}

/* ---------- leaderboard ---------- */

async function initLeaderboard() {
  const el = $("#leaderboard");
  try {
    const data = await api("/api/leaderboard");
    if (!data.leaders.length) {
      el.innerHTML = `<p class="muted empty">No developers yet. 🌱</p>`;
      return;
    }
    const medals = ["🥇", "🥈", "🥉"];
    el.innerHTML = `
      <table class="lb-table">
        <tr><th>#</th><th>Developer</th><th>❤️ Likes</th><th>🚀 Shipped</th><th>📁 Projects</th></tr>
        ${data.leaders.map((u, i) => `
          <tr>
            <td class="num">${medals[i] || i + 1}</td>
            <td><span class="lb-user">${avatarHtml(u, "sm")}<a href="/u/${esc(u.username)}">${esc(u.display_name)}</a> <span class="muted small">@${esc(u.username)}</span></span></td>
            <td class="num">${u.likes_received}</td>
            <td class="num">${u.shipped}</td>
            <td class="num">${u.projects}</td>
          </tr>`).join("")}
      </table>`;
  } catch (err) {
    el.innerHTML = `<p class="muted">${esc(err.message)}</p>`;
  }
}

/* ---------- activity feed ---------- */

const ACTIVITY_META = {
  user_joined:    { icon: "👋", fmt: (a) => `<a href="/u/${esc(a.actor_username)}">${esc(a.actor_display)}</a> joined DevHub` },
  project_added:  { icon: "📁", fmt: (a) => `<a href="/u/${esc(a.actor_username)}">${esc(a.actor_display)}</a> added <a href="/?project=${a.project_id}">${esc(a.project_name || "a project")}</a>` },
  project_shipped:{ icon: "🚀", fmt: (a) => `<a href="/u/${esc(a.actor_username)}">${esc(a.actor_display)}</a> shipped <a href="/?project=${a.project_id}">${esc(a.project_name || "a project")}</a> 🎉` },
  comment_added:  { icon: "💬", fmt: (a) => `<a href="/u/${esc(a.actor_username)}">${esc(a.actor_display)}</a> commented on <a href="/?project=${a.project_id}">${esc(a.project_name || "a project")}</a>` },
};

async function initActivity() {
  const el = $("#activity-feed");
  try {
    const data = await api("/api/activity");
    if (!data.activities.length) {
      el.innerHTML = `<p class="muted empty">Nothing has happened yet. Be the first! 🎬</p>`;
      return;
    }
    el.innerHTML = data.activities.map((a) => {
      const meta = ACTIVITY_META[a.type] || { icon: "✨", fmt: () => esc(a.type) };
      return `
        <div class="feed-item">
          <span class="feed-icon">${meta.icon}</span>
          <span class="feed-text">${meta.fmt(a)}</span>
          <span class="feed-time">${timeAgo(a.created_at)}</span>
        </div>`;
    }).join("");
  } catch (err) {
    el.innerHTML = `<p class="muted">${esc(err.message)}</p>`;
  }
}

/* ---------- trending / saved / notifications ---------- */

function renderGrid(sel, list, emptyMsg) {
  const el = $(sel);
  if (!el) return;
  for (const p of list) if (!showcase.find((x) => x.id === p.id)) showcase.push(p);
  el.innerHTML = list.length ? list.map((p) => projectCard(p)).join("") : `<p class="muted empty">${emptyMsg}</p>`;
}

async function initTrending() {
  try {
    const data = await api("/api/trending");
    renderGrid("#trending-grid", data.projects, "Nothing trending yet. 🌱");
  } catch (err) {
    $("#trending-grid").innerHTML = `<p class="muted">${esc(err.message)}</p>`;
  }
}

async function initSaved() {
  if (!me) { $("#saved-grid").innerHTML = `<p class="muted empty">Log in to see your saved projects.</p>`; return; }
  try {
    const data = await api("/api/me/bookmarks");
    renderGrid("#saved-grid", data.projects, "Nothing saved yet — tap 📑 on any project.");
  } catch (err) {
    $("#saved-grid").innerHTML = `<p class="muted">${esc(err.message)}</p>`;
  }
}

const NOTIF_META = {
  like:    { icon: "❤️", fmt: (n) => `<a href="/u/${esc(n.actor_username)}">${esc(n.actor_display)}</a> liked <a href="/?project=${n.project_id}">${esc(n.project_name || "your project")}</a>` },
  comment: { icon: "💬", fmt: (n) => `<a href="/u/${esc(n.actor_username)}">${esc(n.actor_display)}</a> commented on <a href="/?project=${n.project_id}">${esc(n.project_name || "your project")}</a>` },
  follow:  { icon: "👥", fmt: (n) => `<a href="/u/${esc(n.actor_username)}">${esc(n.actor_display)}</a> started following you` },
};

async function initNotifications() {
  const el = $("#notif-feed");
  if (!me) { el.innerHTML = `<p class="muted empty">Log in to see notifications.</p>`; return; }
  try {
    const data = await api("/api/notifications");
    if (!data.notifications.length) { el.innerHTML = `<p class="muted empty">All quiet. 🌙</p>`; return; }
    el.innerHTML = data.notifications.map((n) => {
      const meta = NOTIF_META[n.type] || { icon: "✨", fmt: () => esc(n.type) };
      return `<div class="feed-item" ${n.is_read ? "" : 'style="font-weight:600"'}>
        <span class="feed-icon">${meta.icon}</span>
        <span class="feed-text">${meta.fmt(n)}</span>
        <span class="feed-time">${timeAgo(n.created_at)}</span></div>`;
    }).join("");
    $("#mark-read").addEventListener("click", async () => {
      try { await api("/api/notifications/read", { method: "POST" }); unread = 0; renderNav(); initNotifications(); }
      catch (err) { toast(err.message, false); }
    });
  } catch (err) {
    el.innerHTML = `<p class="muted">${esc(err.message)}</p>`;
  }
}

/* ---------- keyboard shortcuts ---------- */

function isTyping() {
  const el = document.activeElement;
  return el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName);
}

function initShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeModal(); return; }
    if (isTyping()) return;
    if (e.key === "/") {
      const search = $("#search");
      if (search) { e.preventDefault(); search.focus(); }
    } else if (e.key === "?" || (e.shiftKey && e.key === "/")) {
      const bd = $("#modal-backdrop");
      if (!bd || bd.hidden) openShortcuts();
    } else if (e.key.toLowerCase() === "n" && me) {
      if (page === "dashboard") { e.preventDefault(); $("#p-name").focus(); }
      else window.location.href = "/dashboard";
    }
  });
}

/* ---------- boot ---------- */

document.addEventListener("DOMContentLoaded", () => {
  document.addEventListener("click", globalClickHandler);
  initTheme();
  ensureOverlays();

  loadMe().then(() => {
    renderNav();
    if (page === "landing") initLanding();
    else if (page === "dashboard") initDashboard();
    else if (page === "profile") initProfile();
    else if (page === "leaderboard") initLeaderboard();
    else if (page === "activity") initActivity();
    else if (page === "trending") initTrending();
    else if (page === "saved") initSaved();
    else if (page === "notifications") initNotifications();
  });

  initShortcuts();
});
