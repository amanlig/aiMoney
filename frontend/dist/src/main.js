import {createRoot} from 'react-dom/client';
import {html, ErrorBoundary} from './ui.js';
import {Home, Dashboard} from './App.js';
import {AuthGate} from './SignIn.js';

createRoot(document.getElementById('root')).render(html`<${ErrorBoundary}><${AuthGate}>${location.pathname === '/covered-call-optimizer' ? html`<${Dashboard}/>` : html`<${Home}/>`}</${AuthGate}></${ErrorBoundary}>`);
