// ============================================
// Settings Page - Configuration and account management
// ============================================

// ============================================
// Check Chaturbate login status
// ============================================
async function checkChaturbateStatus() {
  var statusEl = document.getElementById('cbStatus');
  var usernameRow = document.getElementById('cbUsernameRow');
  var usernameEl = document.getElementById('cbUsername');
  var loginForm = document.getElementById('cbLoginForm');
  var loggedInActions = document.getElementById('cbLoggedInActions');

  try {
    var res = await fetch('/api/chaturbate/status');
    if (res.ok) {
      var data = await res.json();

      if (data.isLoggedIn) {
        statusEl.className = 'status-indicator connected';
        statusEl.textContent = 'Connected';
        usernameRow.style.display = 'flex';
        usernameEl.textContent = data.username || 'Unknown';
        loginForm.style.display = 'none';
        loggedInActions.style.display = 'block';
      } else {
        statusEl.className = 'status-indicator disconnected';
        statusEl.textContent = 'Not Connected';
        usernameRow.style.display = 'none';
        loginForm.style.display = 'block';
        loggedInActions.style.display = 'none';
      }
    } else if (res.status === 404) {
      // API endpoint does not exist
      statusEl.className = 'status-indicator unknown';
      statusEl.textContent = 'Not Available';
      loginForm.style.display = 'none';
      loggedInActions.style.display = 'none';
    } else {
      statusEl.className = 'status-indicator disconnected';
      statusEl.textContent = 'Error';
      loginForm.style.display = 'block';
      loggedInActions.style.display = 'none';
    }
  } catch (e) {
    console.error('Error checking Chaturbate status:', e);
    statusEl.className = 'status-indicator unknown';
    statusEl.textContent = 'Unavailable';
    loginForm.style.display = 'block';
    loggedInActions.style.display = 'none';
  }
}

// ============================================
// Login to Chaturbate
// ============================================
async function loginChaturbate(event) {
  event.preventDefault();

  var username = document.getElementById('cbUser').value.trim();
  var password = document.getElementById('cbPass').value;
  var loginBtn = document.getElementById('cbLoginBtn');

  if (!username || !password) {
    showNotification('Please enter both username and password', 'error');
    return;
  }

  loginBtn.disabled = true;
  loginBtn.textContent = 'Logging in...';

  try {
    var res = await fetch('/api/chaturbate/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username,
        password: password
      })
    });

    if (res.ok) {
      var data = await res.json();
      showNotification('Successfully connected to Chaturbate!', 'success');
      // Clear form
      document.getElementById('cbUser').value = '';
      document.getElementById('cbPass').value = '';
      // Refresh status
      await checkChaturbateStatus();
    } else {
      var err = {};
      try { err = await res.json(); } catch (e2) {}
      showNotification(err.detail || 'Login failed. Check your credentials.', 'error');
    }
  } catch (e) {
    console.error('Error logging in:', e);
    showNotification('Connection error', 'error');
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = 'Log In';
  }
}

// ============================================
// Logout from Chaturbate
// ============================================
async function logoutChaturbate() {
  if (!confirm('Disconnect your Chaturbate account?')) return;

  try {
    var res = await fetch('/api/chaturbate/logout', { method: 'POST' });
    if (res.ok) {
      showNotification('Chaturbate account disconnected', 'success');
      await checkChaturbateStatus();
    } else {
      showNotification('Failed to disconnect', 'error');
    }
  } catch (e) {
    console.error('Error logging out:', e);
    showNotification('Connection error', 'error');
  }
}

// ============================================
// Check FlareSolverr status
// ============================================
async function checkFlareSolverr() {
  var statusEl = document.getElementById('flareStatus');
  var versionRow = document.getElementById('flareVersionRow');
  var versionEl = document.getElementById('flareVersion');
  var urlEl = document.getElementById('flareUrl');

  try {
    // FlareSolverr status is included in the chaturbate status endpoint
    var res = await fetch('/api/chaturbate/status');
    if (res.ok) {
      var data = await res.json();

      if (data.flaresolverrAvailable) {
        statusEl.className = 'status-indicator connected';
        statusEl.textContent = 'Healthy';
      } else {
        statusEl.className = 'status-indicator disconnected';
        statusEl.textContent = 'Not Available';
      }
    } else {
      statusEl.className = 'status-indicator unknown';
      statusEl.textContent = 'Unknown';
    }
  } catch (e) {
    // FlareSolverr status check not available
    statusEl.className = 'status-indicator unknown';
    statusEl.textContent = 'Not Available';
  }
}

// ============================================
// Load app version and config
// ============================================
async function loadAppInfo() {
  try {
    var res = await fetch('/api/version');
    if (res.ok) {
      var data = await res.json();
      document.getElementById('appVersionSetting').textContent = 'v' + (data.version || 'unknown');

      // Populate config info if available
      if (data.output_dir || data.config) {
        var config = data.config || data;
        if (config.output_dir) document.getElementById('outputDir').textContent = config.output_dir;
        if (config.ffmpeg_path) document.getElementById('ffmpegPath').textContent = config.ffmpeg_path;
        if (config.check_interval) document.getElementById('checkInterval').textContent = config.check_interval + 's';
      }
    }
  } catch (e) {
    console.error('Error loading app info:', e);
    document.getElementById('apiStatus').className = 'status-indicator disconnected';
    document.getElementById('apiStatus').textContent = 'Disconnected';
  }
}

// ============================================
// Recording Settings (auto_convert, keep_ts)
// ============================================

async function loadRecordingSettings() {
  try {
    var res = await fetch('/api/settings/recording');
    if (res.ok) {
      var data = await res.json();
      var autoConvertToggle = document.getElementById('autoConvertToggle');
      var keepTsToggle = document.getElementById('keepTsToggle');
      if (autoConvertToggle) autoConvertToggle.checked = !!data.auto_convert;
      if (keepTsToggle) keepTsToggle.checked = !!data.keep_ts;
    }
  } catch (e) {
    console.error('Error loading recording settings:', e);
  }
}

async function updateRecordingSetting(key, value) {
  try {
    var body = {};
    body[key] = value;
    var res = await fetch('/api/settings/recording', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (res.ok) {
      showNotification('Setting updated', 'success');
    } else {
      showNotification('Failed to update setting', 'error');
      // Revert toggle
      loadRecordingSettings();
    }
  } catch (e) {
    console.error('Error updating recording setting:', e);
    showNotification('Connection error', 'error');
    loadRecordingSettings();
  }
}

// ============================================
// Notifications
// ============================================
function showNotification(message, type) {
  type = type || 'success';
  var notif = document.createElement('div');
  var bgColor = type === 'success' ? '#10b981' : '#ef4444';
  notif.style.cssText = 'position:fixed;top:20px;right:20px;background:' + bgColor + ';color:white;padding:1rem 1.5rem;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,0.3);z-index:9999;font-weight:500;animation:slideIn 0.3s ease-out;';
  notif.textContent = message;
  document.body.appendChild(notif);

  setTimeout(function() {
    notif.style.opacity = '0';
    notif.style.transform = 'translateX(100px)';
    notif.style.transition = 'all 0.3s ease-out';
    setTimeout(function() { notif.remove(); }, 300);
  }, 3000);
}

// ============================================
// Tag Blacklist Management
// ============================================

let blacklistedTags = [];

async function loadBlacklistedTags() {
  try {
    var res = await fetch('/api/settings/blacklisted-tags');
    if (res.ok) {
      var data = await res.json();
      blacklistedTags = data.tags || [];
      renderBlacklistedTags();
    }
  } catch (e) {
    console.error('Error loading blacklisted tags:', e);
  }
}

function renderBlacklistedTags() {
  var container = document.getElementById('blacklistedTagsList');
  if (!container) return;

  if (blacklistedTags.length === 0) {
    container.innerHTML = '<span style="font-size: 0.85rem; color: var(--text-muted);">No blacklisted tags yet.</span>';
    return;
  }

  container.innerHTML = blacklistedTags.map(function(tag) {
    return '<span style="display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0.7rem; border-radius: 6px; background: rgba(239, 68, 68, 0.15); color: #f87171; font-size: 0.85rem; font-weight: 500;">' +
      escapeHtml(tag) +
      '<button onclick="removeBlacklistedTag(\'' + escapeHtml(tag) + '\')" style="background: none; border: none; color: #f87171; cursor: pointer; font-size: 1.1rem; padding: 0; line-height: 1;">&times;</button>' +
    '</span>';
  }).join('');
}

async function addBlacklistedTag() {
  var input = document.getElementById('blacklistInput');
  var tag = input.value.trim().toLowerCase();
  if (!tag) return;
  if (blacklistedTags.indexOf(tag) !== -1) {
    showNotification('Tag already blacklisted', 'error');
    return;
  }

  blacklistedTags.push(tag);
  input.value = '';

  try {
    var res = await fetch('/api/settings/blacklisted-tags', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: blacklistedTags })
    });
    if (res.ok) {
      renderBlacklistedTags();
      showNotification('Tag "' + tag + '" blacklisted', 'success');
    } else {
      blacklistedTags.pop();
      showNotification('Failed to save', 'error');
    }
  } catch (e) {
    blacklistedTags.pop();
    showNotification('Connection error', 'error');
  }
}

async function removeBlacklistedTag(tag) {
  blacklistedTags = blacklistedTags.filter(function(t) { return t !== tag; });

  try {
    var res = await fetch('/api/settings/blacklisted-tags', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: blacklistedTags })
    });
    if (res.ok) {
      renderBlacklistedTags();
      showNotification('Tag removed', 'success');
    }
  } catch (e) {
    showNotification('Connection error', 'error');
  }
}

function escapeHtml(text) {
  if (!text) return '';
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ============================================
// Initialization
// ============================================
window.addEventListener('DOMContentLoaded', function() {
  // Add animation keyframes
  var style = document.createElement('style');
  style.textContent = '@keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }';
  document.head.appendChild(style);

  // Load all data in parallel
  checkChaturbateStatus();
  checkFlareSolverr();
  loadAppInfo();
  loadBlacklistedTags();
  loadRecordingSettings();

  // Set up blacklist input Enter key
  var blacklistInput = document.getElementById('blacklistInput');
  if (blacklistInput) {
    blacklistInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') addBlacklistedTag();
    });
  }
});
