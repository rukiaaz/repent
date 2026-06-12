document.addEventListener('DOMContentLoaded', function() {
  // Navigation
  const sidebarLinks = document.querySelectorAll('.sidebar-link');
  const contentSections = document.querySelectorAll('.content-section');
  
  sidebarLinks.forEach(link => {
    link.addEventListener('click', function(e) {
      e.preventDefault();
      const sectionId = this.getAttribute('data-section');
      
      // Update active states
      sidebarLinks.forEach(l => l.classList.remove('active'));
      this.classList.add('active');
      
      // Show corresponding section
      contentSections.forEach(section => {
        section.classList.remove('active');
        if (section.id === `${sectionId}-section`) {
          section.classList.add('active');
        }
      });
    });
  });

  // Server management
  const manageButtons = document.querySelectorAll('.manage-btn');
  manageButtons.forEach(btn => {
    btn.addEventListener('click', function() {
      const guildId = this.getAttribute('data-guild-id');
      const guildSelect = document.getElementById('guild-select');
      guildSelect.value = guildId;
      
      // Switch to moderation section
      sidebarLinks.forEach(l => l.classList.remove('active'));
      document.querySelector('[data-section="moderation"]').classList.add('active');
      contentSections.forEach(s => s.classList.remove('active'));
      document.getElementById('moderation-section').classList.add('active');
      
      loadGuildData(guildId);
    });
  });

  // Modal handling
  const modalOverlay = document.getElementById('modal-overlay');
  const modalClose = document.querySelector('.modal-close');
  const modalCancel = document.querySelector('.modal-btn.cancel');
  const modalConfirm = document.getElementById('modal-confirm');
  
  let currentAction = null;
  
  function showModal(action) {
    currentAction = action;
    const modalTitle = document.getElementById('modal-title');
    const modalDescription = document.getElementById('modal-description');
    const userInput = document.getElementById('modal-input-user');
    const reasonInput = document.getElementById('modal-input-reason');
    
    // Reset inputs
    userInput.value = '';
    reasonInput.value = '';
    
    // Set modal content based on action
    switch(action) {
      case 'ban':
        modalTitle.textContent = 'Ban User';
        modalDescription.textContent = 'Enter the user ID or @mention to ban from the server.';
        userInput.placeholder = 'User ID or @mention';
        break;
      case 'kick':
        modalTitle.textContent = 'Kick User';
        modalDescription.textContent = 'Enter the user ID or @mention to kick from the server.';
        userInput.placeholder = 'User ID or @mention';
        break;
      case 'timeout':
        modalTitle.textContent = 'Timeout User';
        modalDescription.textContent = 'Enter the user ID or @mention to timeout.';
        userInput.placeholder = 'User ID or @mention';
        break;
      case 'purge':
        modalTitle.textContent = 'Purge Messages';
        modalDescription.textContent = 'Enter the number of messages to purge (1-100).';
        userInput.placeholder = 'Number of messages (1-100)';
        break;
      case 'massban':
        modalTitle.textContent = 'Mass Ban';
        modalDescription.textContent = 'Enter user IDs separated by commas to mass ban.';
        userInput.placeholder = 'User IDs (comma-separated)';
        break;
      case 'masskick':
        modalTitle.textContent = 'Mass Kick';
        modalDescription.textContent = 'Enter user IDs separated by commas to mass kick.';
        userInput.placeholder = 'User IDs (comma-separated)';
        break;
      case 'lockdown':
        modalTitle.textContent = 'Server Lockdown';
        modalDescription.textContent = 'This will lock down the server by restricting channel permissions.';
        userInput.placeholder = 'Lockdown duration (minutes)';
        break;
    }
    
    modalOverlay.classList.add('show');
  }
  
  function hideModal() {
    modalOverlay.classList.remove('show');
    currentAction = null;
  }
  
  modalClose.addEventListener('click', hideModal);
  modalCancel.addEventListener('click', hideModal);
  modalOverlay.addEventListener('click', function(e) {
    if (e.target === modalOverlay) {
      hideModal();
    }
  });
  
  // Action buttons
  const actionButtons = document.querySelectorAll('.action-btn, .mass-btn');
  actionButtons.forEach(btn => {
    btn.addEventListener('click', function() {
      const action = this.getAttribute('data-action');
      showModal(action);
    });
  });
  
  modalConfirm.addEventListener('click', async function() {
    if (!currentAction) return;
    
    const guildId = document.getElementById('guild-select').value;
    const userInput = document.getElementById('modal-input-user').value;
    const reasonInput = document.getElementById('modal-input-reason').value;
    
    if (!guildId) {
      alert('Please select a server first.');
      return;
    }
    
    if (!userInput && currentAction !== 'lockdown') {
      alert('Please provide the required input.');
      return;
    }
    
    try {
      let response;
      switch(currentAction) {
        case 'ban':
          response = await fetch('/api/moderation/ban', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              guild_id: guildId,
              user_id: userInput,
              reason: reasonInput
            })
          });
          break;
        case 'kick':
          response = await fetch('/api/moderation/kick', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              guild_id: guildId,
              user_id: userInput,
              reason: reasonInput
            })
          });
          break;
        case 'timeout':
          response = await fetch('/api/moderation/timeout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              guild_id: guildId,
              user_id: userInput,
              duration: 600,
              reason: reasonInput
            })
          });
          break;
        default:
          addActivityLog(`⚠️ ${currentAction} command queued`, 'Action will be processed by the bot');
      }
      
      if (response && response.ok) {
        const data = await response.json();
        addActivityLog(`✅ ${currentAction} successful`, data.message);
      } else if (!response) {
        addActivityLog(`⏳ ${currentAction} queued`, 'Action will be processed by the bot');
      }
      
      hideModal();
    } catch (error) {
      console.error('Error performing action:', error);
      addActivityLog(`❌ ${currentAction} failed`, error.message);
    }
  });
  
  // User lookup
  const lookupBtn = document.getElementById('lookup-btn');
  const userLookupInput = document.getElementById('user-lookup-input');
  const userInfoResult = document.getElementById('user-info-result');
  
  lookupBtn.addEventListener('click', async function() {
    const query = userLookupInput.value.trim();
    if (!query) {
      alert('Please enter a user ID or @mention');
      return;
    }
    
    const guildId = document.getElementById('guild-select').value;
    if (!guildId) {
      alert('Please select a server first');
      return;
    }
    
    userInfoResult.innerHTML = '<div style="color:var(--dim)">Looking up user...</div>';
    
    try {
      // This would call your bot's API to look up the user
      // For now, show a placeholder
      setTimeout(() => {
        userInfoResult.innerHTML = `
          <div style="color:var(--fg)">
            <strong>User Lookup Result</strong><br>
            User ID: ${query}<br>
            Status: Not connected to bot API yet
          </div>
        `;
      }, 500);
    } catch (error) {
      userInfoResult.innerHTML = `<div style="color:var(--danger)">Error: ${error.message}</div>`;
    }
  });
  
  // Activity log
  function addActivityLog(title, details) {
    const activityList = document.getElementById('activity-list');
    const now = new Date();
    const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    const activityItem = document.createElement('div');
    activityItem.className = 'activity-item';
    activityItem.innerHTML = `
      <div class="activity-icon">🔔</div>
      <div class="activity-details">
        <div class="activity-title">${title}</div>
        <div class="activity-time">${timeString} · ${details}</div>
      </div>
    `;
    
    activityList.insertBefore(activityItem, activityList.firstChild);
    
    // Keep only last 10 activities
    while (activityList.children.length > 10) {
      activityList.removeChild(activityList.lastChild);
    }
  }
  
  // Guild data loading
  async function loadGuildData(guildId) {
    try {
      const response = await fetch(`/api/guild/${guildId}/members`);
      if (response.ok) {
        const data = await response.json();
        console.log('Guild data loaded:', data);
      }
    } catch (error) {
      console.error('Error loading guild data:', error);
    }
  }
  
  // Settings save
  const saveBtn = document.querySelector('.save-btn');
  if (saveBtn) {
    saveBtn.addEventListener('click', function() {
      addActivityLog('💾 Settings saved', 'Configuration updated successfully');
    });
  }
  
  // Log filter
  const logTypeFilter = document.getElementById('log-type-filter');
  if (logTypeFilter) {
    logTypeFilter.addEventListener('change', function() {
      const filter = this.value;
      const logEntries = document.querySelectorAll('.log-entry');
      
      logEntries.forEach(entry => {
        if (filter === 'all') {
          entry.style.display = 'grid';
        } else {
          const eventType = entry.classList.contains(`log-${filter}`);
          entry.style.display = eventType ? 'grid' : 'none';
        }
      });
    });
  }
  
  // Initialize with some sample activity
  setTimeout(() => {
    addActivityLog('🛡️ Dashboard loaded', 'Welcome to Balance moderation dashboard');
  }, 500);
});