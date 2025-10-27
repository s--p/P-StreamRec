// Settings Modal Functions - Global
window.openSettingsModal = async function() {
  console.log('Opening settings modal...');
  const modal = document.getElementById('settingsModal');
  if (!modal) {
    console.error('Settings modal not found!');
    return;
  }
  modal.style.display = 'flex';
  
  // Load current cookie status
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    
    if (data.hasCbCookie) {
      showCookieStatus('✅ Cookie configuré', 'success');
    } else {
      showCookieStatus('⚠️ Aucun cookie configuré - Discovery ne fonctionnera pas', 'warning');
    }
  } catch (e) {
    console.error('Error loading settings:', e);
  }
};

window.closeSettingsModal = function() {
  document.getElementById('settingsModal').style.display = 'none';
  document.getElementById('cbCookieInput').value = '';
  document.getElementById('cookieStatus').style.display = 'none';
};

window.showCookieStatus = function(message, type) {
  const statusEl = document.getElementById('cookieStatus');
  statusEl.style.display = 'block';
  statusEl.textContent = message;
  
  if (type === 'success') {
    statusEl.style.background = 'rgba(16, 185, 129, 0.1)';
    statusEl.style.border = '1px solid rgba(16, 185, 129, 0.3)';
    statusEl.style.color = 'rgb(16, 185, 129)';
  } else if (type === 'error') {
    statusEl.style.background = 'rgba(239, 68, 68, 0.1)';
    statusEl.style.border = '1px solid rgba(239, 68, 68, 0.3)';
    statusEl.style.color = 'rgb(239, 68, 68)';
  } else if (type === 'warning') {
    statusEl.style.background = 'rgba(245, 158, 11, 0.1)';
    statusEl.style.border = '1px solid rgba(245, 158, 11, 0.3)';
    statusEl.style.color = 'rgb(245, 158, 11)';
  }
};

window.saveCbCookie = async function() {
  const cookie = document.getElementById('cbCookieInput').value.trim();
  
  if (!cookie) {
    showCookieStatus('❌ Veuillez entrer un cookie', 'error');
    return;
  }
  
  // Validation du format
  if (!cookie.includes('=')) {
    showCookieStatus('❌ Format invalide ! Utilisez : csrftoken=VOTRE_VALEUR', 'error');
    return;
  }
  
  // Vérifier que ça commence bien par un nom de cookie
  const cookieParts = cookie.split('=');
  if (cookieParts[0].trim().length === 0 || cookieParts[1].trim().length === 0) {
    showCookieStatus('❌ Format invalide ! Exemple : csrftoken=7ANxN3HaqQ1MDzCC1RlkqCwG18nK6MAk', 'error');
    return;
  }
  
  try {
    const res = await fetch('/api/settings/cb-cookie', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cookie })
    });
    
    if (res.ok) {
      showCookieStatus('✅ Cookie sauvegardé ! Rechargement de la page...', 'success');
      document.getElementById('cbCookieInput').value = '';
      
      // Reload page after 2 seconds
      setTimeout(() => {
        window.location.reload();
      }, 2000);
    } else {
      const data = await res.json();
      showCookieStatus(`❌ Erreur : ${data.detail || 'Erreur inconnue'}`, 'error');
    }
  } catch (e) {
    console.error('Error saving cookie:', e);
    showCookieStatus('❌ Erreur réseau', 'error');
  }
};

window.deleteCbCookie = async function() {
  if (!confirm('Supprimer le cookie Chaturbate ? Discovery ne fonctionnera plus.')) {
    return;
  }
  
  try {
    const res = await fetch('/api/settings/cb-cookie', {
      method: 'DELETE'
    });
    
    if (res.ok) {
      showCookieStatus('✅ Cookie supprimé', 'success');
      document.getElementById('cbCookieInput').value = '';
      
      // Reload after 2 seconds
      setTimeout(() => {
        window.location.reload();
      }, 2000);
    } else {
      showCookieStatus('❌ Erreur lors de la suppression', 'error');
    }
  } catch (e) {
    console.error('Error deleting cookie:', e);
    showCookieStatus('❌ Erreur réseau', 'error');
  }
};

// Close modal with ESC key
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    const modal = document.getElementById('settingsModal');
    if (modal && modal.style.display === 'flex') {
      closeSettingsModal();
    }
  }
});

console.log('Settings.js loaded - openSettingsModal is available');
