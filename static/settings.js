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
      showCookieStatus('✅ Cookie is configured', 'success');
    } else {
      showCookieStatus('⚠️ No cookie configured - Discovery will not work', 'warning');
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
    showCookieStatus('❌ Please enter a cookie', 'error');
    return;
  }
  
  try {
    const res = await fetch('/api/settings/cb-cookie', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cookie })
    });
    
    if (res.ok) {
      showCookieStatus('✅ Cookie saved successfully! Reloading page...', 'success');
      document.getElementById('cbCookieInput').value = '';
      
      // Reload page after 2 seconds
      setTimeout(() => {
        window.location.reload();
      }, 2000);
    } else {
      const data = await res.json();
      showCookieStatus(`❌ Error: ${data.detail || 'Unknown error'}`, 'error');
    }
  } catch (e) {
    console.error('Error saving cookie:', e);
    showCookieStatus('❌ Network error', 'error');
  }
};

window.deleteCbCookie = async function() {
  if (!confirm('Delete the Chaturbate cookie? Discovery will stop working.')) {
    return;
  }
  
  try {
    const res = await fetch('/api/settings/cb-cookie', {
      method: 'DELETE'
    });
    
    if (res.ok) {
      showCookieStatus('✅ Cookie deleted', 'success');
      document.getElementById('cbCookieInput').value = '';
      
      // Reload after 2 seconds
      setTimeout(() => {
        window.location.reload();
      }, 2000);
    } else {
      showCookieStatus('❌ Error deleting cookie', 'error');
    }
  } catch (e) {
    console.error('Error deleting cookie:', e);
    showCookieStatus('❌ Network error', 'error');
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
