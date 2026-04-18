document.addEventListener("DOMContentLoaded", () => {
  const viewport = document.querySelector("[data-brands]");
  if (!viewport) return;

  const track = viewport.querySelector(".brands-track");
  const prevBtn = document.querySelector("[data-brands-prev]");
  const nextBtn = document.querySelector("[data-brands-next]");

  const cards = Array.from(track.children);
  if (cards.length < 2) return;

  let index = 0;

  function cardsPerView(){
    const w = viewport.clientWidth;
    if (w <= 560) return 1;
    if (w <= 900) return 2;
    return 3;
  }

  function step(){
    // širina jedne kartice + gap
    const gap = parseFloat(getComputedStyle(track).gap) || 0;
    const cardW = cards[0].getBoundingClientRect().width;
    return cardW + gap;
  }

  function maxIndex(){
    return Math.max(0, cards.length - cardsPerView());
  }

  function render(){
    const x = index * step();
    track.style.transform = `translate3d(${-x}px, 0, 0)`;
  }

  function next(){
    index++;
    if (index > maxIndex()) index = 0; // LOOP
    render();
  }

  function prev(){
    index--;
    if (index < 0) index = maxIndex(); // LOOP
    render();
  }

  nextBtn?.addEventListener("click", next);
  prevBtn?.addEventListener("click", prev);
  window.addEventListener("resize", () => {
    if (index > maxIndex()) index = maxIndex();
    render();
  });

  render();
});

// ===== PP Brands carousel (novi) =====
document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-pp-brands]");
  if (!root) return;

  const viewport = root.querySelector("[data-pp-brands-viewport]");
  const track = root.querySelector(".pp-brands__track");
  const prevBtn = root.querySelector("[data-pp-brands-prev]");
  const nextBtn = root.querySelector("[data-pp-brands-next]");

  let position = 0;

  function stepPx() {
    const first = track.querySelector(".pp-brand");
    if (!first) return 0;
    const gap = parseFloat(getComputedStyle(track).gap) || 0;
    const w = first.getBoundingClientRect().width;
    return w + gap;
  }

  function clampAndRender() {
    const maxScroll = track.scrollWidth - viewport.clientWidth;
    position = Math.max(-maxScroll, Math.min(0, position));
    track.style.transform = `translateX(${position}px)`; // OVO je jedino mjesto gdje transform postoji
  }

  nextBtn?.addEventListener("click", () => {
    position -= stepPx();
    clampAndRender();
  });

  prevBtn?.addEventListener("click", () => {
    position += stepPx();
    clampAndRender();
  });

  window.addEventListener("resize", clampAndRender);

  clampAndRender();
});

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-qty]").forEach((wrap) => {
    const input = wrap.querySelector("input");
    const minus = wrap.querySelector("[data-qty-minus]");
    const plus = wrap.querySelector("[data-qty-plus]");
    if (!input || !minus || !plus) return;

    const min = parseInt(input.min || "1", 10);
    const max = parseInt(input.max || "99", 10);

    function clamp(v){
      if (Number.isNaN(v)) v = min;
      return Math.max(min, Math.min(max, v));
    }

    minus.addEventListener("click", () => {
      const v = clamp(parseInt(input.value || String(min), 10) - 1);
      input.value = String(v);
    });

    plus.addEventListener("click", () => {
      const v = clamp(parseInt(input.value || String(min), 10) + 1);
      input.value = String(v);
    });

    input.addEventListener("input", () => {
      input.value = String(clamp(parseInt(input.value || String(min), 10)));
    });
  });
});


document.addEventListener("DOMContentLoaded", () => {
  const input = document.querySelector("[data-products-search]");
  const clearBtn = document.querySelector("[data-products-clear]");
  const cards = Array.from(document.querySelectorAll("[data-product-card]"));
  const countEl = document.querySelector("[data-products-count]");

  if (!input || cards.length === 0) return;

  function setCount(n){
    if (countEl) countEl.textContent = String(n);
  }

  function applyFilter(){
    const q = (input.value || "").trim().toLowerCase();
    let shown = 0;

    cards.forEach(card => {
      const name = card.dataset.name || "";
      const desc = card.dataset.desc || "";
      const ok = !q || name.includes(q) || desc.includes(q);

      card.style.display = ok ? "" : "none";
      if (ok) shown++;
    });

   
    setCount(shown);
  }

  input.addEventListener("input", applyFilter);
  clearBtn?.addEventListener("click", () => {
    input.value = "";
    input.focus();
    applyFilter();
  });

  // init count
  setCount(cards.length);
});



