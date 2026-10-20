'use client';

import { useCallback, useState } from 'react';
import { DaySchedule, DEFAULT_WEEKLY_HOURS } from '../constants';

export function useClinicSchedule(initialHours = DEFAULT_WEEKLY_HOURS) {
  const [weeklyHours, setWeeklyHours] = useState<Record<string, DaySchedule>>(initialHours);
  const [initialWeeklyHours, setInitialWeeklyHours] = useState<Record<string, DaySchedule>>(initialHours);

  const handleDayToggle = (day: string) =>
    setWeeklyHours((p) => ({ ...p, [day]: { ...p[day], isOpen: !p[day].isOpen } }));

  const handleTimeChange = (day: string, field: keyof DaySchedule, value: string) =>
    setWeeklyHours((p) => ({ ...p, [day]: { ...p[day], [field]: value } }));

  const copyMondayToWeekdays = () => {
    const m = weeklyHours.Monday;
    setWeeklyHours((p) => ({
      ...p,
      Tuesday: { ...m },
      Wednesday: { ...m },
      Thursday: { ...m },
      Friday: { ...m },
      Saturday: { ...m },
    }));
  };

  const syncSchedule = useCallback((newHours: Record<string, DaySchedule>) => {
    setWeeklyHours(newHours);
    setInitialWeeklyHours(newHours);
  }, []);

  const commitSchedule = () => {
    setInitialWeeklyHours(weeklyHours);
  };

  return {
    weeklyHours,
    setWeeklyHours,
    initialWeeklyHours,
    handleDayToggle,
    handleTimeChange,
    copyMondayToWeekdays,
    syncSchedule,
    commitSchedule,
  };
}
