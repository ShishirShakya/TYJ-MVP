"""
Security JavaScript code for exam UI.

This module contains JavaScript code for client-side security detection:
- Tab focus/blur detection
- Clipboard copy/paste detection
- LocalStorage event tracking
"""


def get_security_javascript() -> str:
    """
    Get JavaScript code for security detection as HTML string.
    
    Returns:
        JavaScript code wrapped in <script> tags as HTML string
    """
    return """
        <script>
        (function() {
            // Tab focus/blur detection
            let tabBlurCount = 0;
            let lastBlurTime = null;
            
            window.addEventListener('blur', function() {
                tabBlurCount++;
                lastBlurTime = Date.now();
                // Store in localStorage for backend retrieval
                let events = JSON.parse(localStorage.getItem('security_events') || '[]');
                events.push({
                    type: 'TAB_BLUR',
                    timestamp: new Date().toISOString()
                });
                localStorage.setItem('security_events', JSON.stringify(events));
            });
            
            window.addEventListener('focus', function() {
                let events = JSON.parse(localStorage.getItem('security_events') || '[]');
                events.push({
                    type: 'TAB_FOCUS',
                    timestamp: new Date().toISOString()
                });
                localStorage.setItem('security_events', JSON.stringify(events));
            });
            
            // Clipboard detection (copy/paste)
            document.addEventListener('copy', function(e) {
                let events = JSON.parse(localStorage.getItem('security_events') || '[]');
                events.push({
                    type: 'CLIPBOARD_COPY',
                    timestamp: new Date().toISOString()
                });
                localStorage.setItem('security_events', JSON.stringify(events));
            });
            
            document.addEventListener('paste', function(e) {
                let events = JSON.parse(localStorage.getItem('security_events') || '[]');
                events.push({
                    type: 'CLIPBOARD_PASTE',
                    timestamp: new Date().toISOString()
                });
                localStorage.setItem('security_events', JSON.stringify(events));
            });
        })();
        </script>
        """


__all__ = ["get_security_javascript"]

