document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-home-tabs]");
    if (!root) return;
  
    const btns = Array.from(root.querySelectorAll("[data-tab-btn]"));
    const panels = Array.from(root.querySelectorAll("[data-tab-panel]"));
  
    function activate(tab) {
      btns.forEach(b => b.classList.toggle("is-active", b.dataset.tabBtn === tab));
      panels.forEach(p => p.classList.toggle("is-active", p.dataset.tabPanel === tab));
    }
  
    btns.forEach(b => b.addEventListener("click", () => activate(b.dataset.tabBtn)));
  
    root.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-load-more]");
      if (!btn) return;
  
      const tab = btn.dataset.loadMore;
      const panel = root.querySelector(`[data-tab-panel="${tab}"]`);
      const grid = panel.querySelector("[data-products-grid]");
      let page = parseInt(btn.dataset.page || "1", 10);
  
      btn.disabled = true;
      const oldLabel = btn.textContent;
      btn.textContent = "Učitavanje…";
  
      try{
        page += 1;
        const res = await fetch(`/api/home-products/${tab}?page=${page}`);
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
  
        if (data.html) grid.insertAdjacentHTML("beforeend", data.html);
        btn.dataset.page = String(page);
  
        if (!data.has_more) btn.style.display = "none";
      } catch(err){
        console.error(err);
        btn.textContent = "Greška, pokušaj opet";
        setTimeout(() => { btn.textContent = oldLabel; }, 1200);
      } finally{
        btn.disabled = false;
      }
    });
  });

  