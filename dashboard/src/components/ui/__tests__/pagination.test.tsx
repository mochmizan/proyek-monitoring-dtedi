import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Pagination } from '../pagination';

describe('Pagination Component', () => {
  it('renders summary text correctly for the first page', () => {
    const { container } = render(
      <Pagination
        currentPage={1}
        totalPages={3}
        totalItems={45}
        pageSize={15}
        onPageChange={vi.fn()}
      />
    );

    expect(container).toHaveTextContent(/Showing 1–15 of 45 alerts/);
  });

  it('renders summary text correctly when totalItems is 0', () => {
    const { container } = render(
      <Pagination
        currentPage={1}
        totalPages={1}
        totalItems={0}
        pageSize={15}
        onPageChange={vi.fn()}
      />
    );

    expect(container).toHaveTextContent(/Showing 0–0 of 0 alerts/);
  });

  it('renders custom itemLabel correctly', () => {
    render(
      <Pagination
        currentPage={1}
        totalPages={2}
        totalItems={20}
        pageSize={10}
        itemLabel="events"
        onPageChange={vi.fn()}
      />
    );

    expect(screen.getByText(/events/)).toBeInTheDocument();
  });

  it('disables First and Prev buttons on the first page', () => {
    render(
      <Pagination
        currentPage={1}
        totalPages={5}
        totalItems={50}
        pageSize={10}
        onPageChange={vi.fn()}
      />
    );

    const firstBtn = screen.getByRole('button', { name: /first page/i });
    const prevBtn = screen.getByRole('button', { name: /previous page/i });
    const nextBtn = screen.getByRole('button', { name: /next page/i });
    const lastBtn = screen.getByRole('button', { name: /last page/i });

    expect(firstBtn).toBeDisabled();
    expect(prevBtn).toBeDisabled();
    expect(nextBtn).toBeEnabled();
    expect(lastBtn).toBeEnabled();
  });

  it('disables Next and Last buttons on the last page', () => {
    render(
      <Pagination
        currentPage={5}
        totalPages={5}
        totalItems={50}
        pageSize={10}
        onPageChange={vi.fn()}
      />
    );

    const firstBtn = screen.getByRole('button', { name: /first page/i });
    const prevBtn = screen.getByRole('button', { name: /previous page/i });
    const nextBtn = screen.getByRole('button', { name: /next page/i });
    const lastBtn = screen.getByRole('button', { name: /last page/i });

    expect(firstBtn).toBeEnabled();
    expect(prevBtn).toBeEnabled();
    expect(nextBtn).toBeDisabled();
    expect(lastBtn).toBeDisabled();
  });

  it('calls onPageChange with correct page numbers when navigation buttons are clicked', () => {
    const handlePageChange = vi.fn();
    render(
      <Pagination
        currentPage={2}
        totalPages={5}
        totalItems={50}
        pageSize={10}
        onPageChange={handlePageChange}
      />
    );

    // Prev -> page 1
    fireEvent.click(screen.getByRole('button', { name: /previous page/i }));
    expect(handlePageChange).toHaveBeenCalledWith(1);

    // Next -> page 3
    fireEvent.click(screen.getByRole('button', { name: /next page/i }));
    expect(handlePageChange).toHaveBeenCalledWith(3);

    // First -> page 1
    fireEvent.click(screen.getByRole('button', { name: /first page/i }));
    expect(handlePageChange).toHaveBeenCalledWith(1);

    // Last -> page 5
    fireEvent.click(screen.getByRole('button', { name: /last page/i }));
    expect(handlePageChange).toHaveBeenCalledWith(5);

    // Click direct page number 4
    fireEvent.click(screen.getByRole('button', { name: '4' }));
    expect(handlePageChange).toHaveBeenCalledWith(4);
  });

  it('disables all buttons when isLoading is true', () => {
    render(
      <Pagination
        currentPage={2}
        totalPages={5}
        totalItems={50}
        pageSize={10}
        onPageChange={vi.fn()}
        isLoading={true}
      />
    );

    expect(screen.getByRole('button', { name: /first page/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /previous page/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /next page/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /last page/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: '2' })).toBeDisabled();
  });

  it('highlights the active page with active styling', () => {
    render(
      <Pagination
        currentPage={3}
        totalPages={5}
        totalItems={50}
        pageSize={10}
        onPageChange={vi.fn()}
      />
    );

    const activeBtn = screen.getByRole('button', { name: '3' });
    expect(activeBtn).toHaveAttribute('aria-current', 'page');
    expect(activeBtn.className).toContain('bg-indigo-600');
  });
});
