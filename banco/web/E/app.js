/* =========================================================
   Grano Sur — interacciones
   Tema (localStorage) · filtro del menú · menú móvil · estado abierto/cerrado
   ========================================================= */
"use strict";

const root = document.documentElement;
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- Tema claro / oscuro ---------- */
const THEME_KEY = "grano-sur-theme";
const themeToggle = document.getElementById("theme-toggle");

function applyTheme(theme, persist) {
  root.setAttribute("data-theme", theme);
  const isDark = theme === "dark";
  themeToggle.setAttribute("aria-pressed", String(isDark));
  themeToggle.setAttribute("aria-label", isDark ? "Cambiar a modo claro" : "Cambiar a modo oscuro");
  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* almacenamiento no disponible: el tema se mantiene solo para esta visita */
    }
  }
}

(function initTheme() {
  let stored = null;
  try {
    stored = localStorage.getItem(THEME_KEY);
  } catch {
    stored = null;
  }
  const saved = stored === "dark" || stored === "light" ? stored : null;
  const preferred = saved ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(preferred, false);
})();

themeToggle.addEventListener("click", () => {
  const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
  applyTheme(next, true);
});

/* ---------- Menú móvil ---------- */
const navToggle = document.getElementById("nav-toggle");
const navLinks = document.getElementById("nav-links");

navToggle.addEventListener("click", () => {
  const open = navLinks.classList.toggle("is-open");
  navToggle.setAttribute("aria-expanded", String(open));
});

// Cierra al navegar por anclas, con Escape o al hacer clic fuera.
navLinks.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    navLinks.classList.remove("is-open");
    navToggle.setAttribute("aria-expanded", "false");
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && navLinks.classList.contains("is-open")) {
    navLinks.classList.remove("is-open");
    navToggle.setAttribute("aria-expanded", "false");
    navToggle.focus();
  }
});

document.addEventListener("click", (event) => {
  if (!navLinks.classList.contains("is-open")) return;
  if (!navLinks.contains(event.target) && event.target !== navToggle) {
    navLinks.classList.remove("is-open");
    navToggle.setAttribute("aria-expanded", "false");
  }
});

/* ---------- Filtro del menú ---------- */
const cards = Array.from(document.querySelectorAll("#cards .card"));
const chips = Array.from(document.querySelectorAll(".chip[data-filter]"));
const filterCount = document.getElementById("filter-count");
const emptyNote = document.getElementById("menu-empty");

function animateCard(card, index, delayStep) {
  if (prefersReducedMotion) return;
  card.classList.add("is-entering");
  setTimeout(() => card.classList.remove("is-entering"), 30 + index * delayStep);
}

function applyFilter(filter) {
  let visible = 0;

  cards.forEach((card, index) => {
    const matches = filter === "todos" || card.dataset.cat === filter;
    card.classList.toggle("is-hidden", !matches);
    if (matches) {
      visible += 1;
      animateCard(card, visible - 1, 45);
    }
  });

  const noun = visible === 1 ? "producto" : "productos";
  filterCount.textContent =
    visible === cards.length ? `${visible} productos en la carta` : `${visible} ${noun} en esta categoría`;
  emptyNote.hidden = visible > 0;
}

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    chips.forEach((c) => {
      const active = c === chip;
      c.classList.toggle("is-active", active);
      c.setAttribute("aria-pressed", String(active));
    });
    applyFilter(chip.dataset.filter);
  });
});

applyFilter("todos");

/* ---------- Estado abierto / cerrado ---------- */
// Horarios en minutos desde medianoche, por día (domingo = 0).
const HOURS = [
  { open: 9 * 60, close: 18 * 60 },   // domingo
  { open: 8 * 60, close: 20 * 60 },   // lunes
  { open: 8 * 60, close: 20 * 60 },
  { open: 8 * 60, close: 20 * 60 },
  { open: 8 * 60, close: 20 * 60 },
  { open: 8 * 60, close: 20 * 60 },
  { open: 9 * 60, close: 21 * 60 },   // sábado
];

const DAY_NAMES = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

function formatTime(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function updateOpenState() {
  const stateEl = document.getElementById("open-state");
  const detailEl = document.getElementById("open-detail");
  if (!stateEl || !detailEl) return;

  const now = new Date();
  const day = now.getDay();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  const today = HOURS[day];
  const tomorrow = HOURS[(day + 1) % 7];

  if (nowMin >= today.open && nowMin < today.close) {
    stateEl.textContent = "Abierto ahora";
    stateEl.classList.remove("is-closed");
    detailEl.textContent = `Hoy cerramos a las ${formatTime(today.close)}.`;
  } else if (nowMin < today.open) {
    stateEl.textContent = "Cerrado";
    stateEl.classList.add("is-closed");
    detailEl.textContent = `Hoy abrimos a las ${formatTime(today.open)}.`;
  } else {
    stateEl.textContent = "Cerrado";
    stateEl.classList.add("is-closed");
    detailEl.textContent = `Mañana (${DAY_NAMES[(day + 1) % 7]}) abrimos a las ${formatTime(tomorrow.open)}.`;
  }
}

updateOpenState();
setInterval(updateOpenState, 60000);

/* ---------- Año del pie de página ---------- */
const yearEl = document.getElementById("year");
if (yearEl) yearEl.textContent = String(new Date().getFullYear());
