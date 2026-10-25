import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { FlowEditorPage } from '../src/pages/FlowEditorPage';
import { validateFlow } from '../src/api';

vi.mock('../src/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/api')>()),
  validateFlow: vi.fn(),
}));

const mockedValidateFlow = vi.mocked(validateFlow);

describe('FlowEditorPage', () => {
  it('renders the canvas and validates the draft', async () => {
    mockedValidateFlow.mockResolvedValue({
      valid: true,
      definition: {
        name: 'New Flow',
        inputs: [],
        steps: [],
      },
    });

    render(
      <MemoryRouter initialEntries={['/flows/new']}>
        <FlowEditorPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Analyze')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/flow name/i), {
      target: { value: 'Repository analysis' },
    });
    fireEvent.click(screen.getByRole('button', { name: /validate/i }));

    expect(mockedValidateFlow).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Repository analysis' }),
    );
    expect(await screen.findByText(/flow definition is valid/i)).toBeInTheDocument();
  });
});
