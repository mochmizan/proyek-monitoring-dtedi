import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

function Hello() {
  return <div>Hello SMSB</div>;
}

describe('smoke', () => {
  it('renders hello', () => {
    render(<Hello />);
    expect(screen.getByText('Hello SMSB')).toBeInTheDocument();
  });

  it('constants imported', async () => {
    const {
      POLL_MS,
      POLL_TIER1_COMMAND_MS,
      POLL_TIER2_ALERTS_MS,
      POLL_TIER3_PRESENCE_MS,
      POLL_TIER4_TRENDS_MS,
      GAP_FLOOR_MIN,
    } = await import('../lib/constants');
    expect(POLL_MS).toBe(6000);
    expect(POLL_TIER1_COMMAND_MS).toBe(1500);
    expect(POLL_TIER2_ALERTS_MS).toBe(6000);
    expect(POLL_TIER3_PRESENCE_MS).toBe(15000);
    expect(POLL_TIER4_TRENDS_MS).toBe(60000);
    expect(GAP_FLOOR_MIN).toBe(5);
  });

  it('chart utils gap floor', async () => {
    const { GAP_FLOOR_MS } = await import('../lib/chartUtils');
    expect(GAP_FLOOR_MS).toBe(5 * 60 * 1000);
  });
});
