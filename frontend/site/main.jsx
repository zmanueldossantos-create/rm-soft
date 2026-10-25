import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './site.css';
import Site from './Site.jsx';

// the theme before the first paint (no flash of the dark theme for a visitor who chose the light one)
try { if (localStorage.getItem('rmsoft_site_theme') === 'light') document.documentElement.classList.add('light'); } catch { /* private mode */ }

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Site />
  </StrictMode>,
);
