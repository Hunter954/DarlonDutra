const header = document.querySelector('.site-header');
window.addEventListener('scroll', () => {
  header.style.background = window.scrollY > 40 ? 'rgba(0,0,0,.82)' : 'linear-gradient(180deg,rgba(0,0,0,.78),rgba(0,0,0,.05))';
});

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.animate([
        { opacity: 0, transform: 'translateY(24px)' },
        { opacity: 1, transform: 'translateY(0)' }
      ], { duration: 700, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'forwards' });
      observer.unobserve(entry.target);
    }
  });
}, { threshold: .16 });

document.querySelectorAll('.section, .banner-cta, .card, .stat-card').forEach(el => {
  el.style.opacity = 0;
  observer.observe(el);
});
