import assert from 'node:assert/strict';
import { test } from 'node:test';
import { normalizeWeeklySchedule, WEEKDAYS } from '../src/lib/weekly-schedule.ts';

test('a closed Sunday does not close weekdays stored as legacy time windows', () => {
  const saved = Object.fromEntries(WEEKDAYS.map(day => [day.toLowerCase(), day === 'Sunday' ? [] : [
    { start: '09:00', end: '13:00' },
    { start: '17:00', end: '20:00' },
  ]]));
  const result = normalizeWeeklySchedule(saved);
  for (const day of WEEKDAYS.slice(0, 6)) {
    assert.deepEqual(result[day], {
      isOpen: true,
      morningStart: '09:00 AM',
      morningEnd: '01:00 PM',
      eveningStart: '05:00 PM',
      eveningEnd: '08:00 PM',
    });
  }
  assert.equal(result.Sunday.isOpen, false);
  assert.deepEqual(saved.sunday, []);
});

test('explicit weekly days off retain their times without being reopened', () => {
  const result = normalizeWeeklySchedule({
    Monday: { isOpen: true, morningStart: '09:00 AM', morningEnd: '01:00 PM' },
    Tuesday: { isOpen: false, morningStart: '09:00 AM', morningEnd: '01:00 PM' },
  });
  assert.equal(result.Monday.isOpen, true);
  assert.equal(result.Tuesday.isOpen, false);
  assert.equal(result.Tuesday.morningStart, '09:00 AM');
  assert.equal(result.Sunday.isOpen, false);
});

test('nested sessions and named windows load into the time controls', () => {
  const result = normalizeWeeklySchedule({
    MONDAY: { isOpen: true, morning: { start: '08:30', end: '12:00' } },
    Tuesday: { isOpen: true, windows: [{ start: '00:00', end: '12:00' }, { start: '16:30', end: '23:45' }] },
  });
  assert.equal(result.Monday.morningStart, '08:30 AM');
  assert.equal(result.Monday.morningEnd, '12:00 PM');
  assert.equal(result.Tuesday.morningStart, '12:00 AM');
  assert.equal(result.Tuesday.eveningEnd, '11:45 PM');
});

test('missing and malformed schedules do not invent appointment hours', () => {
  for (const raw of [undefined, null, {}, [], { Monday: null, Tuesday: 'closed' }]) {
    const result = normalizeWeeklySchedule(raw);
    assert.equal(Object.keys(result).length, 7);
    assert.ok(Object.values(result).every(day => !day.isOpen && day.morningStart === '' && day.eveningEnd === ''));
  }
});

test('invalid saved times remain unset instead of showing a different time', () => {
  const result = normalizeWeeklySchedule({ Monday: {
    isOpen: true, morningStart: '25:00', morningEnd: '12:99', eveningStart: '00:00 PM', eveningEnd: 'unknown',
  } });
  assert.equal(result.Monday.morningStart, '');
  assert.equal(result.Monday.morningEnd, '');
  assert.equal(result.Monday.eveningStart, '');
  assert.equal(result.Monday.eveningEnd, '');
});

test('normalization does not mutate the stored schedule or share day objects', () => {
  const saved = { monday: [{ start: '09:00', end: '13:00' }] };
  const snapshot = structuredClone(saved);
  const result = normalizeWeeklySchedule(saved);
  result.Monday.morningStart = '10:00 AM';
  result.Sunday.isOpen = true;
  assert.deepEqual(saved, snapshot);
  assert.equal(result.Tuesday.isOpen, false);
  assert.equal(normalizeWeeklySchedule(saved).Sunday.isOpen, false);
});
