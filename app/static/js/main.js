const header = document.querySelector('.site-header');
if (header) {
  window.addEventListener('scroll', () => {
    header.style.background = window.scrollY > 40 ? 'rgba(0,0,0,.82)' : 'linear-gradient(180deg,rgba(0,0,0,.78),rgba(0,0,0,.05))';
  });
}

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

const instaForm = document.getElementById('instaSupportForm');
const instaInput = document.getElementById('instagramSupport');
const instaMessage = document.getElementById('instaSupportMessage');
const supporterTracks = document.querySelectorAll('.supporter-logo-track');

function setInstaMessage(text, type = '') {
  if (!instaMessage) return;
  instaMessage.textContent = text;
  instaMessage.className = `insta-message ${type}`.trim();
}

function createSupporterAvatar(supporter) {
  const item = document.createElement('span');
  item.className = supporter.avatar_url ? 'supporter-logo-pill' : 'supporter-logo-pill no-photo';
  item.title = `@${supporter.instagram}`;

  if (supporter.avatar_url) {
    const img = document.createElement('img');
    img.src = supporter.avatar_url;
    img.alt = `@${supporter.instagram}`;
    img.loading = 'lazy';
    img.referrerPolicy = 'no-referrer';
    img.onerror = () => {
      item.classList.add('no-photo');
      img.remove();
    };
    item.appendChild(img);
  }

  const label = document.createElement('small');
  label.textContent = `@${supporter.instagram.slice(0, 18)}`;
  item.appendChild(label);
  return item;
}

if (instaForm && instaInput) {
  instaForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = instaForm.querySelector('button[type="submit"]');
    const instagram = instaInput.value.trim();

    if (!instagram) {
      setInstaMessage('Digite seu @ para confirmar o apoio.', 'error');
      return;
    }

    button.disabled = true;
    button.textContent = 'Confirmando...';
    setInstaMessage('Buscando sua foto e confirmando apoio...', '');

    try {
      const response = await fetch('/api/social-support', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instagram })
      });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        setInstaMessage(data.message || 'Não foi possível confirmar agora.', 'error');
        return;
      }

      setInstaMessage(data.message, 'success');

      if (supporterTracks.length && data.supporter) {
        supporterTracks.forEach((track, index) => {
          const avatarA = createSupporterAvatar(data.supporter);
          const avatarB = createSupporterAvatar(data.supporter);
          if (index % 2 === 0) {
            track.prepend(avatarA);
            track.appendChild(avatarB);
          } else {
            track.appendChild(avatarA);
            track.prepend(avatarB);
          }
        });
      }

      instaInput.value = '';
    } catch (error) {
      setInstaMessage('Instagram instável no momento. Tente de novo em instantes.', 'error');
    } finally {
      button.disabled = false;
      button.textContent = 'Eu apoio';
    }
  });
}
