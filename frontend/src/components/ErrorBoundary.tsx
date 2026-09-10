import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary caught error]:', error, errorInfo);
    this.setState({ error, errorInfo });
  }

  private handleReload = () => {
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#08090a',
            color: '#f7f8f8',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            padding: '2rem',
            boxSizing: 'border-box',
          }}
        >
          <div
            style={{
              maxWidth: '600px',
              width: '100%',
              backgroundColor: '#121417',
              border: '1px solid rgba(244, 88, 110, 0.4)',
              borderRadius: '0.75rem',
              padding: '2rem',
              boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  backgroundColor: 'rgba(244, 88, 110, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#f4586e',
                  fontSize: '1.25rem',
                  fontWeight: 'bold',
                }}
              >
                !
              </div>
              <div>
                <h2 style={{ margin: 0, fontSize: '1.15rem', color: '#f7f8f8' }}>
                  UI Telemetry Display Glitch
                </h2>
                <span style={{ fontSize: '0.8rem', color: '#8b949e' }}>
                  The application caught an unexpected rendering error and prevented a black screen.
                </span>
              </div>
            </div>

            {this.state.error && (
              <pre
                style={{
                  backgroundColor: '#0a0c0e',
                  padding: '1rem',
                  borderRadius: '0.5rem',
                  fontSize: '0.8rem',
                  color: '#f4586e',
                  overflowX: 'auto',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  maxHeight: '160px',
                  overflowY: 'auto',
                }}
              >
                {this.state.error.toString()}
              </pre>
            )}

            <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem' }}>
              <button
                onClick={this.handleReload}
                style={{
                  padding: '0.6rem 1.2rem',
                  backgroundColor: '#6366f1',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '0.375rem',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Reload Dashboard
              </button>
              <button
                onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
                style={{
                  padding: '0.6rem 1.2rem',
                  backgroundColor: 'transparent',
                  color: '#8b949e',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  borderRadius: '0.375rem',
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                }}
              >
                Dismiss & Retry
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
