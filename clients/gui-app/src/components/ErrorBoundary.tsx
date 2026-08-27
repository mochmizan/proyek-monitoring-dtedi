import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-lg text-center space-y-3">
          <h2 className="text-sm font-semibold text-zinc-200">Something went wrong</h2>
          <p className="text-xs text-zinc-500">{this.state.error?.message ?? 'Unexpected error'}</p>
          <button
            onClick={this.handleReset}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-medium cursor-pointer"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
