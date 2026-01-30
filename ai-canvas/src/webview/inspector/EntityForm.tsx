import React, { useState, useEffect } from 'react';
import type { Entity, SizeHint, EntityStatus } from '../../shared/types/entities';
import { useAppStore } from '../store/appStore';

const SIZE_OPTIONS: SizeHint[] = ['xs', 's', 'm', 'l', 'xl'];
const STATUS_OPTIONS: EntityStatus[] = ['todo', 'doing', 'review', 'done'];

export function EntityForm({ entity }: { entity: Entity }) {
  const updateEntity = useAppStore((s) => s.updateEntity);
  const [name, setName] = useState(entity.name);
  const [purpose, setPurpose] = useState(entity.purpose);
  const [sizeHint, setSizeHint] = useState<SizeHint>(entity.size_hint);
  const [status, setStatus] = useState<EntityStatus>(entity.status);

  useEffect(() => {
    setName(entity.name);
    setPurpose(entity.purpose);
    setSizeHint(entity.size_hint);
    setStatus(entity.status);
  }, [entity.id, entity.name, entity.purpose, entity.size_hint, entity.status]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    updateEntity(entity.id, {
      name: name.trim(),
      purpose: purpose.trim(),
      size_hint: sizeHint,
      status
    });
  };

  const formStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    padding: '12px'
  };
  const labelStyle: React.CSSProperties = { fontSize: '11px', fontWeight: 600, color: '#555' };
  const inputStyle: React.CSSProperties = { padding: '6px 8px', fontSize: '12px' };
  const selectStyle: React.CSSProperties = { ...inputStyle, minWidth: '140px' };

  return (
    <form onSubmit={handleSubmit} style={formStyle}>
      <div>
        <label style={labelStyle}>Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={inputStyle}
          placeholder="Entity name"
        />
      </div>
      <div>
        <label style={labelStyle}>Purpose</label>
        <textarea
          value={purpose}
          onChange={(e) => setPurpose(e.target.value)}
          style={{ ...inputStyle, minHeight: '60px', resize: 'vertical' }}
          placeholder="One-sentence purpose"
          rows={3}
        />
      </div>
      <div>
        <label style={labelStyle}>Size</label>
        <select
          value={sizeHint}
          onChange={(e) => setSizeHint(e.target.value as SizeHint)}
          style={selectStyle}
        >
          {SIZE_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label style={labelStyle}>Status</label>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as EntityStatus)}
          style={selectStyle}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <button type="submit" style={{ padding: '8px', marginTop: '8px', cursor: 'pointer' }}>
        Save
      </button>
    </form>
  );
}
