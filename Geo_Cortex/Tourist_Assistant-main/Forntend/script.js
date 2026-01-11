document.getElementById('loginForm').addEventListener('submit', async function (e) {
  e.preventDefault();

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value.trim();
  const message = document.getElementById('message');
  message.textContent = 'Logging in...';

  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);

  try {
    const response = await fetch('http://127.0.0.1:8000/auth/token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: formData
    });

    const data = await response.json();

    if (response.ok) {
      localStorage.setItem('token', data.access_token);
      message.style.color = 'green';
      message.textContent = 'Login successful!';
      // Redirect to dashboard or another page
      // window.location.href = 'dashboard.html';
    } else {
      message.style.color = 'red';
      message.textContent = data.detail || 'Invalid credentials.';
    }
  } catch (error) {
    console.error(error);
    message.style.color = 'red';
    message.textContent = 'Error connecting to the server.';
  }
});
