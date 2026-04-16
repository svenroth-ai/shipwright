import { describe, it, expect } from 'vitest';
import { DEFAULT_PHASE_MAPPING, resolvePhaseMapping, getKanbanStatus } from './phaseMapping';

describe('phaseMapping', () => {
  describe('DEFAULT_PHASE_MAPPING', () => {
    it('maps project to in_progress (new default)', () => {
      expect(DEFAULT_PHASE_MAPPING['project']).toBe('in_progress');
    });

    it('maps build to in_progress', () => {
      expect(DEFAULT_PHASE_MAPPING['build']).toBe('in_progress');
    });

    it('maps test to in_review', () => {
      expect(DEFAULT_PHASE_MAPPING['test']).toBe('in_review');
    });

    it('maps deploy to in_review (new default)', () => {
      expect(DEFAULT_PHASE_MAPPING['deploy']).toBe('in_review');
    });

    it('maps security to in_review', () => {
      expect(DEFAULT_PHASE_MAPPING['security']).toBe('in_review');
    });

    it('maps compliance to in_review', () => {
      expect(DEFAULT_PHASE_MAPPING['compliance']).toBe('in_review');
    });

    it('maps changelog to in_review (new default)', () => {
      expect(DEFAULT_PHASE_MAPPING['changelog']).toBe('in_review');
    });
  });

  describe('resolvePhaseMapping', () => {
    it('returns default when no overrides', () => {
      const result = resolvePhaseMapping();
      expect(result).toEqual(DEFAULT_PHASE_MAPPING);
    });

    it('merges overrides with defaults', () => {
      const result = resolvePhaseMapping({ build: 'in_review' });
      expect(result['build']).toBe('in_review');
      expect(result['test']).toBe('in_review'); // unchanged
    });
  });

  describe('getKanbanStatus', () => {
    it('returns mapped status for known phase', () => {
      expect(getKanbanStatus('test', DEFAULT_PHASE_MAPPING)).toBe('in_review');
    });

    it('returns backlog for unknown phase', () => {
      expect(getKanbanStatus('unknown_phase', DEFAULT_PHASE_MAPPING)).toBe('backlog');
    });
  });
});
