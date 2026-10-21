import {createRoot} from 'react-dom/client';
import {html, ErrorBoundary} from './ui.js';
import {Home, Dashboard} from './App.js';

createRoot(document.getElementById('root')).render(html`<${ErrorBoundary}>${location.pathname === '/covered-call-optimizer' ? html`<${Dashboard}/>` : html`<${Home}/>`}</${ErrorBoundary}>`);
