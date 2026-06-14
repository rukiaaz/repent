"""
Repent - Premium Theme Manager
Centralized color palette and design tokens for enterprise-grade UI.
"""

class ThemeManager:
    """
    Manages the premium design system colors and styles.
    
    This is the single source of truth for all UI colors, ensuring
    consistency across all embeds and components.
    """
    
    # ═══════════════════════════════════════════════════════════════
    # PRIMARY BRAND COLORS
    # ═══════════════════════════════════════════════════════════════
    
    # Deep navy - Primary brand color for premium security feel
    color_primary = 0x1A1A2E
    
    # Light navy - UI accents and secondary elements
    color_primary_light = 0x16213E
    
    # Dark blue - Highlights and important elements
    color_accent = 0x0F3460
    
    # Purple accent - Premium feel for special features
    color_accent_light = 0x533483
    
    # Red-pink - Critical alerts and attention-grabbing elements
    color_highlight = 0xE94560
    
    # ═══════════════════════════════════════════════════════════════
    # SEMANTIC COLORS
    # ═══════════════════════════════════════════════════════════════
    
    # Success / Enabled / Protected states
    color_success = 0x10B981        # Modern emerald green (not generic 0x44FF88)
    color_success_dark = 0x059669   # Darker variant for text
    
    # Warning / Caution / Medium security
    color_warning = 0xF59E0B        # Modern amber (not generic 0xFFAA00)
    color_warning_dark = 0xD97706   # Darker variant for text
    
    # Danger / Critical / Disabled states
    color_danger = 0xEF4444         # Modern red (not generic 0xFF4444)
    color_danger_dark = 0xDC2626    # Darker variant for text
    
    # Info / Neutral / Default states
    color_info = 0x3B82F6          # Modern blue (not generic 0x4488FF)
    color_info_dark = 0x2563EB     # Darker variant for text
    
    # ═══════════════════════════════════════════════════════════════
    # SECURITY-SPECIFIC COLORS
    # ═══════════════════════════════════════════════════════════════
    
    # High security / Protected / Safe
    color_security_high = 0x10B981  # Light emerald green
    color_security = 0x059669       # Dark emerald green
    
    # Medium security / Warning / Caution
    color_security_med = 0xF59E0B   # Amber for medium security
    
    # Low security / Vulnerable / Risk
    color_security_low = 0xEF4444   # Red for low security
    
    # ═══════════════════════════════════════════════════════════════
    # BACKGROUND COLORS
    # ═══════════════════════════════════════════════════════════════
    
    # Dark slate - Premium dark mode background
    color_background = 0x0F172A
    
    # Card background - For card-style embeds
    color_card = 0x1E293B
    
    # Card hover state - Interactive elements
    color_card_hover = 0x334155
    
    # Border color - For visual separation
    color_border = 0x475569
    
    # ═══════════════════════════════════════════════════════════════
    # GRADIENTS
    # ═══════════════════════════════════════════════════════════════
    
    # Premium navy gradient - For brand elements
    gradient_premium = [0x1A1A2E, 0x16213E]
    
    # Success gradient - For positive actions
    gradient_success = [0x10B981, 0x059669]
    
    # Danger gradient - For critical alerts
    gradient_danger = [0xEF4444, 0xDC2626]
    
    # Security gradient - For security states
    gradient_security = [0x059669, 0x10B981]
    
    # ═══════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════
    
    @staticmethod
    def get_color_for_status(status: str) -> int:
        """
        Get appropriate color for a status string.
        
        Args:
            status: Status string (active, enabled, success, warning, etc.)
        
        Returns:
            Integer color value for Discord embeds
        """
        status_colors = {
            "active": color_success,
            "enabled": color_success,
            "success": color_success,
            "online": color_success,
            "warning": color_warning,
            "caution": color_warning,
            "danger": color_danger,
            "error": color_danger,
            "disabled": 0x6B7280,  # Gray
            "inactive": 0x6B7280,  # Gray
            "offline": 0x6B7280,  # Gray
            "info": color_info,
            "neutral": color_info,
        }
        return status_colors.get(status.lower(), color_info)
    
    @staticmethod
    def get_icon_for_status(status: str) -> str:
        """
        Get appropriate icon for a status string.
        
        Args:
            status: Status string (active, enabled, success, warning, etc.)
        
        Returns:
            Unicode character for status indicator
        """
        status_icons = {
            "active": "●",       # Solid circle
            "enabled": "✓",      # Checkmark
            "success": "✓",      # Checkmark
            "online": "●",       # Solid circle
            "warning": "!",      # Exclamation
            "caution": "!",      # Exclamation
            "danger": "✗",      # X mark
            "error": "✗",       # X mark
            "disabled": "○",     # Hollow circle
            "inactive": "○",     # Hollow circle
            "offline": "○",      # Hollow circle
            "info": "i",         # Information i
            "neutral": "i",      # Information i
        }
        return status_icons.get(status.lower(), "i")
    
    @staticmethod
    def get_color_for_security_level(level: str) -> int:
        """
        Get appropriate color for a security level.
        
        Args:
            level: Security level (maximum, high, medium, low)
        
        Returns:
            Integer color value for Discord embeds
        """
        level_colors = {
            "maximum": color_security_high,
            "high": color_security_high,
            "medium": color_security_med,
            "low": color_security_low,
        }
        return level_colors.get(level.lower(), color_info)
    
    @staticmethod
    def get_icon_for_security_level(level: str) -> str:
        """
        Get appropriate icon for a security level.
        
        Args:
            level: Security level (maximum, high, medium, low)
        
        Returns:
            Unicode character for security indicator
        """
        level_icons = {
            "maximum": "🛡️",      # Shield
            "high": "🔒",          # Locked
            "medium": "🔓",         # Unlocked
            "low": "⚠️",           # Warning
        }
        return level_icons.get(level.lower(), "🛡️")


# Singleton instance for consistent theme management
_theme_manager = None

def get_theme_manager() -> ThemeManager:
    """Get the global theme manager instance."""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager