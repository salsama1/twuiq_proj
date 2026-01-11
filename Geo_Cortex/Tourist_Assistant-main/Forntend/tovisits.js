async function fetchPlaces() {
  const token = localStorage.getItem('token');
  const message = document.getElementById('message');
  const placesList = document.getElementById('placesList');

  if (!token) {
    message.textContent = 'Not authenticated. Redirecting to login...';
    setTimeout(() => {
      window.location.href = 'login.html';
    }, 2000);
    return;
  }

  try {
    const response = await fetch('http://127.0.0.1:8000/tovisits/', {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    const data = await response.json();

    if (response.ok) {
      if (data.length === 0) {
        message.textContent = 'No saved places.';
      } else {
        placesList.innerHTML = '';
        data.forEach(place => {
          const item = document.createElement('li');
          item.textContent = `📍 ${place.name || 'Unnamed'} – ${place.address || 'No address'}`;
          placesList.appendChild(item);
        });
      }
    } else {
      message.style.color = 'red';
      message.textContent = 'Failed to fetch places: ' + (data.detail || 'Error');
    }
  } catch (error) {
    console.error(error);
    message.style.color = 'red';
    message.textContent = 'Error connecting to server.';
  }
}

function logout() {
  localStorage.removeItem('token');
  window.location.href = 'login.html';
}

window.onload = fetchPlaces;
document.getElementById('logoutButton').addEventListener('click', logout);