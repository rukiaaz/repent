// Modern Dashboard JavaScript
// Handles all dashboard functionality and API integration

class BalanceDashboard {
    constructor() {
        this.currentServer = null;
        this.userData = null;
        this.init();
    }

    async init() {
        this.setupNavigation();
        this.setupModals();
        this.setupAPIIntegration();
        this.setupDynamicLoading();
        this.setupRealTimeUpdates();
    }

    // Navigation
    setupNavigation() {
        const sidebarLinks = document.querySelectorAll('.sidebar-link');
        const contentSections = document.querySelectorAll('.content-section');

        sidebarLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const sectionId = link.getAttribute('data-section');
                
                sidebarLinks.forEach(l => l.classList.remove('active'));
                link.classList.add('active');
                
                contentSections.forEach(section => {
                    section.classList.remove('active');
                    if (section.id === `${sectionId}-section`) {
                        section.classList.add('active');
                    }
                });
            });
        });

        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', function() {
                const parent = this.closest('.card') || this.closest('.section');
                const siblingTabs = parent.querySelectorAll('.tab');
                siblingTabs.forEach(t => t.classList.remove('active'));
                this.classList.add('active');
            });
        });
    }

    // Modals
    setupModals() {
        const modalOverlay = document.getElementById('action-modal');
        const modalClose = modalOverlay.querySelector('.modal-header button');
        const cancelBtn = modalOverlay.querySelector('.modal-footer .btn-secondary');

        const closeModal = () => {
            modalOverlay.classList.remove('show');
        };

        modalClose.addEventListener('click', closeModal);
        cancelBtn.addEventListener('click', closeModal);
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeModal();
        });

        // Expose closeModal globally
        window.closeModal = closeModal;
    }

    // API Integration
    setupAPIIntegration() {
        // Server select handlers
        document.querySelectorAll('select[id$="-select"]').forEach(select => {
            select.addEventListener('change', async (e) => {
                const guildId = e.target.value;
                if (guildId && (e.target.id.includes('channel') || e.target.id.includes('role') || e.target.id.includes('whitelist'))) {
                    await this.loadGuildData(guildId, e.target.id);
                }
            });
        });

        // Action buttons
        window.executeAction = (action) => this.executeModerationAction(action);
        window.channelAction = (action) => this.executeChannelAction(action);
        window.selectServer = (guildId) => this.selectServer(guildId);
        window.applySlowmode = () => this.applySlowmode();
    }

    async loadGuildData(guildId, selectId) {
        try {
            if (selectId.includes('channel')) {
                const response = await fetch(`/api/guild/${guildId}/channels`);
                const data = await response.json();
                this.populateSelect(selectId, data.channels);
            } else if (selectId.includes('role')) {
                const response = await fetch(`/api/guild/${guildId}/roles`);
                const data = await response.json();
                this.populateSelect(selectId, data.roles);
            } else if (selectId.includes('whitelist')) {
                const response = await fetch(`/api/whitelist/list/${guildId}`);
                const data = await response.json();
                this.populateWhitelistTable(data);
            }
        } catch (error) {
            console.error('Error loading guild data:', error);
        }
    }

    populateSelect(selectId, items) {
        const select = document.getElementById(selectId);
        if (!select) return;
        
        // Keep first option
        const firstOption = select.querySelector('option');
        select.innerHTML = '';
        select.appendChild(firstOption);

        items.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id || item;
            option.textContent = item.name || item;
            select.appendChild(option);
        });
    }

    populateWhitelistTable(data) {
        // Implementation for whitelist table population
        console.log('Whitelist data:', data);
    }

    selectServer(guildId) {
        this.currentServer = guildId;
        document.getElementById('server-select').value = guildId;
        
        // Update all server selects
        document.querySelectorAll('select[id$="-select"]').forEach(select => {
            if (select.id !== 'server-select') {
                select.value = guildId;
            }
        });

        // Navigate to actions section
        document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
        document.querySelector('[data-section="actions"]').classList.add('active');
        
        document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
        document.getElementById('actions-section').classList.add('active');
    }

    async executeModerationAction(action) {
        const server = document.getElementById('action-server-select').value;
        const target = document.getElementById('action-target').value;
        const reason = document.getElementById('action-reason').value;

        if (!server) {
            this.showNotification('error', 'Please select a server');
            return;
        }

        if (!target && action !== 'purge') {
            this.showNotification('error', 'Please enter a target user');
            return;
        }

        const modalBody = `
            <div style="margin-bottom: 16px;">
                <div style="margin-bottom: 12px;">
                    <label style="font-weight: 600; font-size: 13px;">Server:</label>
                    <div style="color: var(--text-secondary);">${server}</div>
                </div>
                ${target ? `
                <div style="margin-bottom: 12px;">
                    <label style="font-weight: 600; font-size: 13px;">Target:</label>
                    <div style="color: var(--text-secondary);">${target}</div>
                </div>
                ` : ''}
                <div>
                    <label style="font-weight: 600; font-size: 13px;">Reason:</label>
                    <div style="color: var(--text-secondary);">${reason || 'No reason provided'}</div>
                </div>
            </div>
        `;

        this.showModal(
            `Confirm ${action.charAt(0).toUpperCase() + action.slice(1)}`,
            `Are you sure you want to ${action} this user?`,
            modalBody,
            async () => {
                try {
                    const response = await fetch(`/api/moderation/${action}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            guild_id: server,
                            user_id: target,
                            reason: reason
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        this.showNotification('success', data.message);
                        this.logActivity(action, target, server);
                    } else {
                        this.showNotification('error', data.error || 'Action failed');
                    }
                } catch (error) {
                    this.showNotification('error', 'Action failed: ' + error.message);
                }
                closeModal();
            }
        );
    }

    async executeChannelAction(action) {
        const server = document.getElementById('channel-server-select').value;
        const channel = document.getElementById('channel-select').value;

        if (!server) {
            this.showNotification('error', 'Please select a server');
            return;
        }

        if (!channel && action !== 'slowmode' && action !== 'clearslowmode') {
            this.showNotification('error', 'Please select a channel');
            return;
        }

        if (action === 'slowmode') {
            document.getElementById('slowmode-settings').style.display = 'block';
            return;
        }

        try {
            const response = await fetch(`/api/channel/${action}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    guild_id: server,
                    channel_id: channel
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showNotification('success', data.message);
                this.logActivity(action, channel, server);
            } else {
                this.showNotification('error', data.error || 'Action failed');
            }
        } catch (error) {
            this.showNotification('error', 'Channel action failed: ' + error.message);
        }
    }

    async applySlowmode() {
        const server = document.getElementById('channel-server-select').value;
        const channel = document.getElementById('channel-select').value;
        const duration = document.getElementById('slowmode-duration').value;

        if (!server) {
            this.showNotification('error', 'Please select a server');
            return;
        }

        if (!channel) {
            this.showNotification('error', 'Please select a channel');
            return;
        }

        try {
            const response = await fetch('/api/channel/slowmode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    guild_id: server,
                    channel_id: channel,
                    seconds: parseInt(duration) || 0
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showNotification('success', data.message);
                this.logActivity('slowmode', `${channel}: ${duration}s`, server);
            } else {
                this.showNotification('error', data.error || 'Failed to set slowmode');
            }

            document.getElementById('slowmode-settings').style.display = 'none';
        } catch (error) {
            this.showNotification('error', 'Failed to set slowmode: ' + error.message);
        }
    }

    // Dynamic Loading
    setupDynamicLoading() {
        // User search functionality
        const userSearch = document.getElementById('user-search');
        if (userSearch) {
            let searchTimeout;
            userSearch.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    this.searchUsers(e.target.value);
                }, 500);
            });
        }

        // Server select for user management
        const userServerSelect = document.getElementById('user-server-select');
        if (userServerSelect) {
            userServerSelect.addEventListener('change', async (e) => {
                await this.loadServerMembers(e.target.value);
            });
        }
    }

    async searchUsers(query) {
        const server = document.getElementById('user-server-select').value;
        if (!server || !query) return;

        try {
            const response = await fetch(`/api/guild/${server}/members`);
            const data = await response.json();
            
            const filtered = data.members.filter(member => 
                member.username?.toLowerCase().includes(query.toLowerCase()) ||
                member.id?.includes(query)
            );
            
            this.populateUserTable(filtered);
        } catch (error) {
            console.error('Search failed:', error);
        }
    }

    async loadServerMembers(guildId) {
        try {
            const response = await fetch(`/api/guild/${guildId}/members`);
            const data = await response.json();
            this.populateUserTable(data.members);
        } catch (error) {
            console.error('Failed to load members:', error);
        }
    }

    populateUserTable(members) {
        const tbody = document.getElementById('user-table-body');
        if (!tbody) return;

        if (members.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; color: var(--text-secondary);">
                        No members found
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = members.map(member => `
            <tr>
                <td>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        ${member.avatar ? `<img src="${member.avatar}" style="width: 32px; height: 32px; border-radius: 50%;">` : ''}
                        <div>
                            <div style="font-weight: 600;">${member.username || 'Unknown'}</div>
                            <div style="font-size: 12px; color: var(--text-muted);">${member.global_name || ''}</div>
                        </div>
                    </div>
                </td>
                <td>${member.id}</td>
                <td>${member.joined_at || 'N/A'}</td>
                <td>${member.roles?.slice(0, 2).map(r => r.name).join(', ') || 'None'}</td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="showSection('actions')">Actions</button>
                </td>
            </tr>
        `).join('');
    }

    // Real-time Updates
    setupRealTimeUpdates() {
        // Poll for activity updates
        setInterval(async () => {
            await this.fetchRecentActivity();
        }, 10000); // Every 10 seconds

        // Poll for server stats
        setInterval(async () => {
            await this.fetchServerStats();
        }, 30000); // Every 30 seconds
    }

    async fetchRecentActivity() {
        // Implementation for real-time activity feed
    }

    async fetchServerStats() {
        // Implementation for real-time statistics
    }

    // Modal Management
    showModal(title, description, body, onConfirm) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-description').textContent = description;
        document.getElementById('modal-body').innerHTML = body || '';
        document.getElementById('modal-confirm').onclick = onConfirm;
        document.getElementById('action-modal').classList.add('show');
    }

    // Notifications
    showNotification(type, message) {
        // Create notification element
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: ${type === 'success' ? 'var(--brand-success)' : type === 'error' ? 'var(--brand-danger)' : 'var(--brand-info)'};
            color: white;
            padding: 16px 24px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 9999;
            animation: slideIn 0.3s ease;
        `;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transform = 'translateX(100%)';
            notification.style.transition = 'all 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    // Activity Logging
    logActivity(action, target, server) {
        const timestamp = new Date().toLocaleString();
        const activityItem = {
            action: action,
            target: target,
            server: server,
            timestamp: timestamp,
            user: this.userData?.username
        };

        // In production, this would send to a backend API
        console.log('Activity logged:', activityItem);
    }

    // Animation
    animateStats() {
        const statValues = document.querySelectorAll('.stat-value');
        statValues.forEach(stat => {
            const finalValue = parseInt(stat.textContent) || 0;
            if (finalValue === 0) return;
            
            let currentValue = 0;
            const increment = finalValue / 30;
            const timer = setInterval(() => {
                currentValue += increment;
                if (currentValue >= finalValue) {
                    currentValue = finalValue;
                    clearInterval(timer);
                }
                stat.textContent = Math.floor(currentValue);
            }, 30);
        });
    }
}

// CSS animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(100%);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
`;
document.head.appendChild(style);

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new BalanceDashboard();
    window.dashboard.animateStats();
});