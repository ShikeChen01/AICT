import React, { useState, useCallback } from 'react';
import { useAppDispatch } from '../../store/hooks';
import { addEntity, createBucket } from '../../store/slices/entitiesSlice';
import { setNodePosition } from '../../store/slices/canvasSlice';
import { setBucketCreationOpen } from '../../store/slices/uiSlice';
import { useAppSelector } from '../../store/hooks';
import { Modal } from '../shared/Modal';
import type { Bucket } from '../../../shared/types/entities';

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: 'var(--spacing-sm) var(--spacing-md)',
  marginBottom: 'var(--spacing-md)',
  fontSize: 'var(--font-size-md)',
  background: 'var(--color-input-background)',
  border: '1px solid var(--color-input-border)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-foreground)',
  boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  marginBottom: 'var(--spacing-xs)',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-description)',
};

const buttonRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--spacing-sm)',
  justifyContent: 'flex-end',
  marginTop: 'var(--spacing-lg)',
};

const btnStyle: React.CSSProperties = {
  padding: 'var(--spacing-sm) var(--spacing-md)',
  fontSize: 'var(--font-size-md)',
  cursor: 'pointer',
  border: 'none',
  borderRadius: 'var(--radius-md)',
  fontFamily: 'var(--font-family)',
};

const DEFAULT_PLACE_X = 120;
const DEFAULT_PLACE_Y = 120;

export function BucketCreationModal() {
  const dispatch = useAppDispatch();
  const open = useAppSelector((s) => s.ui.bucketCreationOpen);
  const entities = useAppSelector((s) => s.entities.allIds).length;

  const [name, setName] = useState('');
  const [summary, setSummary] = useState('');
  const [validationTest, setValidationTest] = useState('');

  const handleClose = useCallback(() => {
    dispatch(setBucketCreationOpen(false));
    setName('');
    setSummary('');
    setValidationTest('');
  }, [dispatch]);

  const handleSubmit = useCallback(() => {
    const nameTrim = name.trim();
    const summaryTrim = summary.trim();
    const validationTrim = validationTest.trim();
    if (!nameTrim || !summaryTrim || !validationTrim) return;

    const bucket = createBucket({
      name: nameTrim,
      purpose: summaryTrim,
      tests: { block_test: validationTrim },
    } as Partial<Bucket>);
    dispatch(addEntity(bucket));
    dispatch(
      setNodePosition({
        id: bucket.id,
        position: {
          x: DEFAULT_PLACE_X + (entities % 4) * 180,
          y: DEFAULT_PLACE_Y + Math.floor(entities / 4) * 120,
        },
      })
    );
    handleClose();
  }, [dispatch, name, summary, validationTest, entities, handleClose]);

  const valid = name.trim() && summary.trim() && validationTest.trim();

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Create Bucket"
    >
      <label style={labelStyle}>Name (required)</label>
      <input
        style={inputStyle}
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="e.g. backend, ui, infra"
        autoFocus
      />
      <label style={labelStyle}>Short summary (required, 1–2 lines)</label>
      <textarea
        style={{ ...inputStyle, minHeight: 56, resize: 'vertical' }}
        value={summary}
        onChange={(e) => setSummary(e.target.value)}
        placeholder="Brief description of this bucket"
        rows={2}
      />
      <label style={labelStyle}>Validation test (required)</label>
      <input
        style={inputStyle}
        value={validationTest}
        onChange={(e) => setValidationTest(e.target.value)}
        placeholder="e.g. pnpm -C backend test, pytest -q"
      />
      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-description)', marginTop: -8, marginBottom: 8 }}>
        Single command or checklist that proves the bucket is healthy.
      </div>
      <div style={buttonRowStyle}>
        <button
          type="button"
          style={{
            ...btnStyle,
            background: 'transparent',
            color: 'var(--color-foreground)',
            border: '1px solid var(--color-widget-border)',
          }}
          onClick={handleClose}
        >
          Cancel
        </button>
        <button
          type="button"
          style={{
            ...btnStyle,
            background: valid ? 'var(--color-button-background)' : 'var(--color-input-background)',
            color: valid ? 'var(--color-button-foreground)' : 'var(--color-description)',
            cursor: valid ? 'pointer' : 'not-allowed',
          }}
          onClick={handleSubmit}
          disabled={!valid}
        >
          Create Bucket
        </button>
      </div>
    </Modal>
  );
}
