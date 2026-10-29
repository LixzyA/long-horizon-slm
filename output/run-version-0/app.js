const searchForm = document.querySelector('#searchForm');

searchForm.addEventListener('submit', function(e) {
  e.preventDefault();
  
  const query = searchForm.querySelector('input[name="q"]').value.trim();
  
  if (query.length > 0) {
    // Search functionality would be implemented here
    console.log('Searching for:', query);
    
    // In a real implementation, you would fetch from API or use browser's search() method
    // For now, show the user their own input in a modal
  }
});
