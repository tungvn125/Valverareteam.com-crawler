/**
 * Desktop Notification System
 */

let permissionGranted = false;

export async function requestNotificationPermission() {
    if (!('Notification' in window)) {
        console.warn('This browser does not support desktop notification');
        return false;
    }

    if (Notification.permission === 'granted') {
        permissionGranted = true;
        return true;
    }

    if (Notification.permission !== 'denied') {
        const permission = await Notification.requestPermission();
        permissionGranted = permission === 'granted';
        return permissionGranted;
    }
    
    return false;
}

export function sendDesktopNotification(title, options = {}) {
    if (!permissionGranted) return;
    try {
        const notification = new Notification(title, {
            icon: 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"%3E%3Ccircle cx="50" cy="50" r="50" fill="%2300cfd5"/%3E%3Ctext y="50" x="50" fill="%23fff" font-size="40" font-family="Arial" font-weight="bold" dominant-baseline="central" text-anchor="middle"%3EV%3C/text%3E%3C/svg%3E',
            ...options
        });
        
        notification.onclick = function () {
            window.focus();
            notification.close();
        };
    } catch (e) {
        console.error('Failed to send notification', e);
    }
}

/**
 * Actionable Error Parser
 * Analyzes raw traceback or error messages and returns a user-friendly suggestion
 */
export function getActionableErrorSuggestion(errorMsg) {
    if (!errorMsg || typeof errorMsg !== 'string') return null;
    
    const msg = errorMsg.toLowerCase();
    
    if (msg.includes("no module named 'freesound'") || msg.includes("no module named freesound")) {
        return "Thiếu thư viện freesound-python. Hãy mở Terminal chạy lệnh: pip install freesound-python";
    }
    
    if (msg.includes("playwright") && (msg.includes("executable doesn't exist") || msg.includes("timeout"))) {
        return "Playwright lỗi trình duyệt. Hãy chạy lệnh: playwright install chromium";
    }
    
    if (msg.includes("connectionrefused") || msg.includes("socket.gaierror")) {
        return "Lỗi mạng. Vui lòng kiểm tra kết nối internet hoặc proxy của bạn.";
    }
    
    if (msg.includes("permission denied")) {
        return "Lỗi quyền ghi file. Vui lòng kiểm tra lại 'Thư mục đầu ra'.";
    }
    
    return null; // No specific suggestion
}
