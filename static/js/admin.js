// static/js/admin.js
document.addEventListener('DOMContentLoaded', function() {
    // Sidebar toggle functionality
    const sidebarToggle = document.getElementById('sidebar-toggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            const sidebar = document.getElementById('sidebar');
            if (sidebar.style.width === '250px' || sidebar.style.width === '') {
                sidebar.style.width = '80px';
                document.querySelectorAll('.sidebar-brand span, .sidebar-nav .nav-link span').forEach(el => {
                    el.style.display = 'none';
                });
            } else {
                sidebar.style.width = '250px';
                document.querySelectorAll('.sidebar-brand span, .sidebar-nav .nav-link span').forEach(el => {
                    el.style.display = 'inline';
                });
            }
        });
    }
    
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});