(function(){
    const root = document.querySelector('[data-hero]');
    if(!root) return;
  
    const track = root.querySelector('.hero-track');
    const slides = Array.from(root.querySelectorAll('.hero-slide'));
    const prevBtn = root.querySelector('[data-hero-prev]');
    const nextBtn = root.querySelector('[data-hero-next]');
    const dots = Array.from(root.querySelectorAll('[data-hero-dot]'));
  
    let i = 0;
    let timer = null;
  
    function render(){
      track.style.transform = `translate3d(${-i * 100}%, 0, 0)`;
      slides.forEach((s, idx) => {
        s.classList.toggle('is-active', idx === i);
      });
      dots.forEach((d, idx) => d.setAttribute('aria-current', idx === i ? 'true' : 'false'));
    }
  
    function next(){
      i = (i + 1) % slides.length;
      render();
    }
    function prev(){
      i = (i - 1 + slides.length) % slides.length;
      render();
    }
  
    function start(){
      stop();
      timer = setInterval(next, 6000);
    }
    function stop(){
      if(timer) clearInterval(timer);
      timer = null;
    }
  
    nextBtn?.addEventListener('click', () => { next(); start(); });
    prevBtn?.addEventListener('click', () => { prev(); start(); });
  
    dots.forEach((d) => {
      d.addEventListener('click', () => {
        i = parseInt(d.getAttribute('data-hero-dot'), 10);
        render();
        start();
      });
    });
  
    root.addEventListener('mouseenter', stop);
    root.addEventListener('mouseleave', start);
  
    render();
    start();
  })();
  