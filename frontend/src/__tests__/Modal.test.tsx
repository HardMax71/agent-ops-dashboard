import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { Modal } from '../components/Modal'

describe('Modal', () => {
  afterEach(cleanup)

  it('returns null when isOpen=false', () => {
    const { container } = render(
      <Modal isOpen={false} onClose={vi.fn()} title="Test">
        Content
      </Modal>
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders title and children when open', () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} title="My Modal">
        <p>Hello world</p>
      </Modal>
    )
    expect(screen.getByText('My Modal')).toBeInTheDocument()
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('calls onClose on Escape key', () => {
    const onClose = vi.fn()
    render(
      <Modal isOpen={true} onClose={onClose} title="Test">
        Content
      </Modal>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose on close button click', () => {
    const onClose = vi.fn()
    render(
      <Modal isOpen={true} onClose={onClose} title="Test">
        Content
      </Modal>
    )
    fireEvent.click(screen.getByLabelText('Close modal'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('has correct ARIA attributes', () => {
    render(
      <Modal isOpen={true} onClose={vi.fn()} title="Accessible Modal">
        Content
      </Modal>
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title')
    expect(screen.getByText('Accessible Modal').id).toBe('modal-title')
  })
})
