import axios from 'axios';

// Create a configured axios instance
// In Vite development, we use proxy in vite.config.js to forward /api to backend
const api = axios.create({
    baseURL: '/api/v1',
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add response interceptor for error handling if needed
api.interceptors.response.use(
    (response) => response,
    (error) => {
        // Handle common errors like 401 Unauthorized here
        return Promise.reject(error);
    }
);

export default api;
