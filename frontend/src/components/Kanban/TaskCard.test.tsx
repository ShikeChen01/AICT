import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TaskCard } from './TaskCard';
import { mockTasks } from '../../test/mocks';

describe('TaskCard', () => {
  const mockTask = mockTasks[0];

  it('should render task title', () => {
    render(<TaskCard task={mockTask} />);
    
    expect(screen.getByText(mockTask.title)).toBeInTheDocument();
  });

  it('should render task description when present', () => {
    render(<TaskCard task={mockTask} />);
    
    expect(screen.getByText(mockTask.description!)).toBeInTheDocument();
  });

  it('should not render description when null', () => {
    const taskWithoutDescription = { ...mockTask, description: null };
    render(<TaskCard task={taskWithoutDescription} />);
    
    // Should still render title but no description element
    expect(screen.getByText(mockTask.title)).toBeInTheDocument();
  });

  it('should show Critical priority badge for low priority values', () => {
    const criticalTask = { ...mockTask, critical: 1, urgent: 1 };
    render(<TaskCard task={criticalTask} />);
    
    expect(screen.getByText('Critical')).toBeInTheDocument();
  });

  it('should show Low priority badge for high priority values', () => {
    const lowPriorityTask = { ...mockTask, critical: 8, urgent: 9 };
    render(<TaskCard task={lowPriorityTask} />);
    
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('should call onClick when card is clicked', () => {
    const onClick = vi.fn();
    render(<TaskCard task={mockTask} onClick={onClick} />);
    
    fireEvent.click(screen.getByText(mockTask.title));
    
    expect(onClick).toHaveBeenCalledWith(mockTask);
  });

  it('should show PR link when pr_url is present', () => {
    const taskWithPR = { ...mockTask, pr_url: 'https://github.com/example/repo/pull/1' };
    render(<TaskCard task={taskWithPR} />);
    
    const prLink = screen.getByText('PR');
    expect(prLink).toBeInTheDocument();
    expect(prLink).toHaveAttribute('href', taskWithPR.pr_url);
  });

  it('should show module path badge when present', () => {
    render(<TaskCard task={mockTask} />);
    
    // Module path is 'src/auth', should show 'auth'
    expect(screen.getByText('auth')).toBeInTheDocument();
  });

  it('should show Assigned indicator when agent is assigned', () => {
    const assignedTask = mockTasks[1]; // This one has assigned_agent_id
    render(<TaskCard task={assignedTask} />);
    
    expect(screen.getByText('Assigned')).toBeInTheDocument();
  });
});
