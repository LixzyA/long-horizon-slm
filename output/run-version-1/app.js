// Profile site JavaScript

// Initialize the site with date from seed file
const SITE_DATE = new Date().toISOString().split('T')[0];

// Load sources data
async function loadSources() {
  try {
    const response = await fetch('https://karpathy.ai/');
    if (!response.ok) throw new Error('Failed to load karpathy.ai profile');
    
    return await response.json();
  } catch (error) {
    console.error('Error loading sources:', error);
    return [];
  }
}

// Load timeline data
async function loadTimeline() {
  try {
    const response = await fetch('timeline.json');
    if (!response.ok) throw new Error('Failed to load timeline.json');
    
    return await response.json();
  } catch (error) {
    console.error('Error loading timeline:', error);
    return [];
  }
}

// Build category filter buttons
function buildCategoryButtons() {
  const categoryBtns = document.querySelectorAll('.filter-btn');
  
  categoryBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      categoryBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      
      const filterValue = btn.dataset.category;
      filterCategory(categoryFilterElement, filterValue);
    });
  });
}

// Load search results
async function loadSearchResults() {
  try {
    const response = await fetch('https://karpathy.ai/');
    if (!response.ok) throw new Error('Failed to load karpathy.ai profile');
    
    return await response.json();
  } catch (error) {
    console.error('Error loading search results:', error);
    return [];
  }
}

// Filter category
function filterCategory(element, value) {
  const allItems = document.querySelectorAll('.result-item');
  
  if (value === 'all') {
    allItems.forEach(item => {
      item.style.display = '';
    });
  } else {
    allItems.forEach(item => {
      const title = item.querySelector('.result-title').textContent.trim();
      if (title.includes(value)) {
        item.style.display = 'flex';
      } else {
        item.style.display = 'none';
      }
    });
  }
}

// Search function
function searchResults() {
  const input = document.getElementById('search-input');
  const resultsDiv = document.getElementById('search-results');
  
  if (!input) return;
  
  const searchTerm = input.value.toLowerCase();
  
  const filteredItems = allItems.filter(item => {
    const title = item.querySelector('.result-title').textContent.toLowerCase();
    const content = item.querySelector('.result-content').textContent.toLowerCase();
    const category = item.dataset.category;
    
    return (title.includes(searchTerm) || 
            content.includes(searchTerm) || 
            category === 'all' || 
            category !== searchTerm);
  });
  
  if (filteredItems.length > 0) {
    resultsDiv.innerHTML = '';
    
    filteredItems.forEach(item => {
      const resultItem = document.createElement('div');
      resultItem.className = 'result-item';
      
      const titleElement = item.querySelector('.result-title');
      const contentElement = item.querySelector('.result-content');
      
      if (titleElement) {
        resultItem.innerHTML = `
          <span class="result-title">${titleElement.textContent}</span>
          <div class="result-content">${contentElement.textContent}</div>
        `;
      } else {
        resultItem.innerHTML = '<span class="result-title">...</span><div class="result-content">...</div>';
      }
      
      if (item.dataset.category) {
        resultItem.dataset.category = item.dataset.category;
      }
      
      resultsDiv.appendChild(resultItem);
    });
  } else {
    resultsDiv.innerHTML = '<p>No results found</p>';
  }
}

// Render timeline items
function renderTimeline(items) {
  const timelineContainer = document.querySelector('.timeline-section');
  
  if (!timelineContainer) return;
  
  if (items.length === 0) {
    timelineContainer.innerHTML = '<p>No timeline data available</p>';
    return;
  }
  
  items.forEach(item => {
    const dateEl = document.createElement('div');
    dateEl.className = 'date';
    dateEl.textContent = item.date + ' ' + (item.date_precision ? item.date_precision : '');
    
    const titleEl = document.createElement('h3');
    titleEl.textContent = item.title;
    
    const descEl = document.createElement('p');
    descEl.textContent = item.description;
    
    timelineContainer.appendChild(dateEl);
    timelineContainer.appendChild(titleEl);
    timelineContainer.appendChild(descEl);
  });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  // Set date from seed file
  const seedDate = new Date().toISOString().split('T')[0];
  document.getElementById('date-1').textContent = SITE_DATE + ' ';
  
  loadSources();
  buildCategoryButtons();
  searchResults();
  
  // Add keyboard event for category filter
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' && !e.shiftKey) {
      e.preventDefault();
      const nextCategory = document.querySelector('.filter-btn.active').dataset.category;
      filterCategory(document.querySelector('.category-section'), nextCategory);
    }
  });
});
