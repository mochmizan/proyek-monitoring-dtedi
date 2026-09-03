import { useState } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from '../ErrorBoundary';

function ProblemChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Simulation of catastrophic render error');
  }
  return <div>Safe child content rendered</div>;
}

function ResettableContainer() {
  const [hasError, setHasError] = useState(true);
  return (
    <div>
      <button onClick={() => setHasError(false)}>Fix Error</button>
      <ErrorBoundary>
        <ProblemChild shouldThrow={hasError} />
      </ErrorBoundary>
    </div>
  );
}

describe('ErrorBoundary Component', () => {
  let originalError: typeof console.error;

  beforeEach(() => {
    originalError = console.error;
    console.error = vi.fn(); // Suppress React boundary console noise
  });

  afterEach(() => {
    console.error = originalError;
  });

  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('Child content')).toBeInTheDocument();
  });

  it('catches render error and displays default error UI with error message and Try again button', () => {
    render(
      <ErrorBoundary>
        <ProblemChild shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Simulation of catastrophic render error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('renders custom fallback ReactNode when fallback prop is supplied', () => {
    render(
      <ErrorBoundary fallback={<div>Custom fallback node</div>}>
        <ProblemChild shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Custom fallback node')).toBeInTheDocument();
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });

  it('re-renders children when handleReset is triggered after underlying error is resolved', () => {
    render(<ResettableContainer />);

    // Initially in error state
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    // Fix the underlying condition
    fireEvent.click(screen.getByRole('button', { name: /fix error/i }));

    // Click "Try again" inside ErrorBoundary to trigger handleReset
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));

    // Safe child should now be rendered
    expect(screen.getByText('Safe child content rendered')).toBeInTheDocument();
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });
});
