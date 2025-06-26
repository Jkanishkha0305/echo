document.addEventListener('DOMContentLoaded', function() {
  // Sidebar toggle
  const toggleSidebarBtn = document.getElementById('toggleSidebar');
  const sidebar = document.getElementById('sidebar');
  const contentWrapper = document.getElementById('content-wrapper');
  
  if (toggleSidebarBtn) {
    toggleSidebarBtn.addEventListener('click', function() {
      sidebar.classList.toggle('active');
      contentWrapper.classList.toggle('sidebar-active');
    });
  }
  
  // Close sidebar when clicking outside
  document.addEventListener('click', function(event) {
    if (sidebar && sidebar.classList.contains('active') && 
        !sidebar.contains(event.target) && 
        event.target !== toggleSidebarBtn) {
      sidebar.classList.remove('active');
      contentWrapper.classList.remove('sidebar-active');
    }
  });
  
  // Search form submit
  const searchForm = document.getElementById('searchForm');
  const searchResults = document.getElementById('searchResults');
  const searchLoading = document.getElementById('searchLoading');
  
  if (searchForm) {
    searchForm.addEventListener('submit', function(event) {
      if (searchLoading) {
        searchLoading.classList.remove('d-none');
      }
      
      // The actual submit will happen
      // No need to manually hide the loading indicator as the page will refresh
    });
  }
  
  // Company selection
  const companyItems = document.querySelectorAll('.company-card');
  
  companyItems.forEach(function(item) {
    item.addEventListener('click', function() {
      companyItems.forEach(function(company) {
        company.classList.remove('active');
      });
      
      this.classList.add('active');
      
      // Show contacts for selected company
      const companyId = this.getAttribute('data-company-id');
      const contactsContainer = document.getElementById('companyContacts');
      
      if (contactsContainer) {
        // In a real app, we would load contacts via AJAX
        // Here we just toggle the visibility
        const allCompanyContacts = document.querySelectorAll('.company-contacts');
        allCompanyContacts.forEach(function(contacts) {
          contacts.style.display = 'none';
        });
        
        const selectedCompanyContacts = document.getElementById('contacts-' + companyId);
        if (selectedCompanyContacts) {
          selectedCompanyContacts.style.display = 'block';
        }
      }
    });
  });
  
  // Contact expansion
  const contactHeaders = document.querySelectorAll('.contact-header');
  
  contactHeaders.forEach(function(header) {
    header.addEventListener('click', function() {
      const contactBody = this.nextElementSibling;
      const expandIcon = this.querySelector('.expand-icon');
      
      if (contactBody.classList.contains('show')) {
        contactBody.classList.remove('show');
        expandIcon.classList.remove('bi-chevron-up');
        expandIcon.classList.add('bi-chevron-down');
      } else {
        contactBody.classList.add('show');
        expandIcon.classList.remove('bi-chevron-down');
        expandIcon.classList.add('bi-chevron-up');
      }
    });
  });
  
  // Expand all contacts button
  const expandAllBtn = document.getElementById('expandAll');
  
  if (expandAllBtn) {
    expandAllBtn.addEventListener('click', function() {
      const contactBodies = document.querySelectorAll('.contact-body');
      const expandIcons = document.querySelectorAll('.expand-icon');
      
      if (this.getAttribute('data-expanded') === 'false') {
        contactBodies.forEach(function(body) {
          body.classList.add('show');
        });
        
        expandIcons.forEach(function(icon) {
          icon.classList.remove('bi-chevron-down');
          icon.classList.add('bi-chevron-up');
        });
        
        this.setAttribute('data-expanded', 'true');
        this.innerHTML = '<i class="bi bi-chevron-up me-1"></i> Collapse All';
      } else {
        contactBodies.forEach(function(body) {
          body.classList.remove('show');
        });
        
        expandIcons.forEach(function(icon) {
          icon.classList.remove('bi-chevron-up');
          icon.classList.add('bi-chevron-down');
        });
        
        this.setAttribute('data-expanded', 'false');
        this.innerHTML = '<i class="bi bi-chevron-down me-1"></i> Expand All';
      }
    });
  }
  
  // Form validation for registration
  const registerForm = document.getElementById('registerForm');
  if (registerForm) {
    registerForm.addEventListener('submit', function(event) {
      const password = document.getElementById('password').value;
      const confirmPassword = document.getElementById('confirmPassword').value;
      const termsAgreed = document.getElementById('termsAgreed').checked;
      
      if (password !== confirmPassword) {
        event.preventDefault();
        alert('Passwords do not match!');
        return false;
      }
      
      if (!termsAgreed) {
        event.preventDefault();
        alert('You must agree to the terms of service');
        return false;
      }
    });
  }
  
  // Initialize tooltips
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });
});


