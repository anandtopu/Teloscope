import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// Global reset styles injected at runtime
const style = document.createElement('style');
style.textContent = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body, #root { height: 100%; }
  body {
    background: #0F1117;
    color: #E2E8F0;
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: #1A1D27; }
  ::-webkit-scrollbar-thumb { background: #2A2D3A; border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: #3A3D4A; }
  input, select, button { font-family: inherit; }
  a { color: inherit; }
`;
document.head.appendChild(style);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
