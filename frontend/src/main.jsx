import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(e) { return { error: e }; }
  render() {
    if (this.state.error) return (
      <div style={{ fontFamily: 'monospace', padding: '2rem', color: '#f87171', background: '#0f172a', minHeight: '100vh' }}>
        <h2>⚠️ App Error</h2>
        <pre style={{ marginTop: '1rem', whiteSpace: 'pre-wrap' }}>{this.state.error.message}</pre>
      </div>
    );
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
)
