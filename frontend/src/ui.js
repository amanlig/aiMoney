import React from 'react';
import htm from '../vendor/htm.js';
export const html = htm.bind(React.createElement);
export {React};
export const {useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback} = React;

export class ErrorBoundary extends React.Component {
  state = {error: null};
  static getDerivedStateFromError(error) { return {error}; }
  render() {
    return this.state.error ? html`<main><h1>Dashboard unavailable</h1><p role="alert">${this.state.error.message}</p><a href="/covered-call-optimizer">Reload dashboard</a></main>` : this.props.children;
  }
}
