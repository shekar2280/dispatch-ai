import {
  EmergencyBlock,
  DoctorLeave,
  DateOverride,
  RescheduleSuggestion,
  DaySchedule,
  AppointmentItem,
} from "./types";

export interface FindAvailableSlotsParams {
  startDate: string;
  maxDaysAhead?: number;
  existingAppointments: AppointmentItem[];
  weeklyHours: Record<string, DaySchedule>;
  dateOverrides?: DateOverride[];
  leaves?: DoctorLeave[];
  emergencyBlocks?: EmergencyBlock[];
  slotDuration?: number;
  slotBuffer?: number;
  maxDailyPatients?: number;
}

export function timeToMinutes(timeStr: string): number {
  if (!timeStr) return 0;
  const parts = timeStr.trim().split(" ");
  if (parts.length < 2) return 0;

  const [hoursStr, minsStr] = parts[0].split(":");
  let hours = parseInt(hoursStr, 10);
  const minutes = parseInt(minsStr, 10) || 0;
  const meridiem = parts[1].toUpperCase();

  if (meridiem === "PM" && hours < 12) hours += 12;
  if (meridiem === "AM" && hours === 12) hours = 0;

  return hours * 60 + minutes;
}

export function minutesToTime(totalMins: number): string {
  const normalized = ((totalMins % 1440) + 1440) % 1440;
  let hours = Math.floor(normalized / 60);
  const mins = normalized % 60;
  const meridiem = hours >= 12 ? "PM" : "AM";

  if (hours === 0) {
    hours = 12;
  } else if (hours > 12) {
    hours -= 12;
  }

  const paddedHours = hours < 10 ? `0${hours}` : `${hours}`;
  const paddedMins = mins < 10 ? `0${mins}` : `${mins}`;

  return `${paddedHours}:${paddedMins} ${meridiem}`;
}

export function getCurrentTime12(date: Date = new Date()): string {
  const hours = date.getHours();
  const mins = date.getMinutes();
  return minutesToTime(hours * 60 + mins);
}

export function roundToNextQuarterHour(date: Date = new Date()): string {
  const ms = 1000 * 60 * 15;
  const rounded = new Date(Math.ceil(date.getTime() / ms) * ms);
  return minutesToTime(rounded.getHours() * 60 + rounded.getMinutes());
}

export function addMinutesToTime(
  timeStr: string,
  minutesToAdd: number,
): string {
  const currentMins = timeToMinutes(timeStr);
  return minutesToTime(currentMins + minutesToAdd);
}

export function formatDateISO(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function addDaysISO(baseDateStr: string, days: number): string {
  const [y, m, d] = baseDateStr.split("-").map((v) => parseInt(v, 10));
  const date = new Date(y, m - 1, d);
  date.setDate(date.getDate() + days);
  return formatDateISO(date);
}

export function getDayName(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map((v) => parseInt(v, 10));
  const date = new Date(y, m - 1, d);
  const days = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
  ];
  return days[date.getDay()];
}

export function generateShiftSlots(
  shiftStart: string,
  shiftEnd: string,
  slotDuration: number,
  slotBuffer: number,
): string[] {
  const startMins = timeToMinutes(shiftStart);
  const endMins = timeToMinutes(shiftEnd);
  const step = slotDuration + slotBuffer;

  if (startMins >= endMins || step <= 0) return [];

  const slots: string[] = [];
  let current = startMins;

  while (current + slotDuration <= endMins) {
    slots.push(minutesToTime(current));
    current += step;
  }

  return slots;
}

export function isDateInLeave(
  dateStr: string,
  leaves?: DoctorLeave[],
): boolean {
  if (!leaves || leaves.length === 0) return false;
  return leaves.some((l) => dateStr >= l.startDate && dateStr <= l.endDate);
}

export function isSlotEmergencyBlocked(
  dateStr: string,
  slotTime: string,
  emergencyBlocks?: EmergencyBlock[],
): boolean {
  if (!emergencyBlocks || emergencyBlocks.length === 0) return false;

  return emergencyBlocks.some((block) => {
    if (block.date !== dateStr) return false;
    if (block.scope === "full_day") return true;
    if (block.scope === "remainder_of_day" && block.blockedFromTime) {
      return timeToMinutes(slotTime) >= timeToMinutes(block.blockedFromTime);
    }
    return false;
  });
}

export function getActiveScheduleForDate(
  dateStr: string,
  weeklyHours: Record<string, DaySchedule>,
  dateOverrides?: DateOverride[],
): {
  isOpen: boolean;
  morningStart: string;
  morningEnd: string;
  eveningStart: string;
  eveningEnd: string;
} {
  const override = dateOverrides?.find((o) => o.date === dateStr);

  if (override) {
    if (override.overrideType === "closed_special") {
      return {
        isOpen: false,
        morningStart: "",
        morningEnd: "",
        eveningStart: "",
        eveningEnd: "",
      };
    }
    return {
      isOpen: true,
      morningStart: override.morningStart || "10:00 AM",
      morningEnd: override.morningEnd || "01:30 PM",
      eveningStart: override.eveningStart || "05:30 PM",
      eveningEnd: override.eveningEnd || "08:30 PM",
    };
  }

  const dayName = getDayName(dateStr);
  const fallback = weeklyHours[dayName];

  if (!fallback || !fallback.isOpen) {
    return {
      isOpen: false,
      morningStart: "",
      morningEnd: "",
      eveningStart: "",
      eveningEnd: "",
    };
  }

  return {
    isOpen: true,
    morningStart: fallback.morningStart,
    morningEnd: fallback.morningEnd,
    eveningStart: fallback.eveningStart,
    eveningEnd: fallback.eveningEnd,
  };
}

export function findNextAvailableSlots(
  params: FindAvailableSlotsParams,
): RescheduleSuggestion[] {
  const {
    startDate,
    maxDaysAhead = 4,
    existingAppointments,
    weeklyHours,
    dateOverrides = [],
    leaves = [],
    emergencyBlocks = [],
    slotDuration = 15,
    slotBuffer = 5,
    maxDailyPatients = 30,
  } = params;

  const suggestions: RescheduleSuggestion[] = [];
  const spilloverCandidates: RescheduleSuggestion[] = [];

  for (let offset = 1; offset <= maxDaysAhead; offset += 1) {
    const candidateDate = addDaysISO(startDate, offset);

    if (isDateInLeave(candidateDate, leaves)) continue;

    const schedule = getActiveScheduleForDate(
      candidateDate,
      weeklyHours,
      dateOverrides,
    );
    if (!schedule.isOpen) continue;

    const dayAppointments = existingAppointments.filter((a) => {
      const matchesDate = a.appointment_date
        ? a.appointment_date === candidateDate
        : true;
      return matchesDate && a.status !== "cancelled";
    });

    const bookedTimes = new Set(
      dayAppointments
        .filter((a) => !!a.appointment_time)
        .map((a) => a.appointment_time!.trim().toUpperCase()),
    );

    const remainingCapacity = Math.max(
      0,
      maxDailyPatients - dayAppointments.length,
    );
    if (remainingCapacity <= 0) continue;

    const morningSlots =
      schedule.morningStart && schedule.morningEnd
        ? generateShiftSlots(
            schedule.morningStart,
            schedule.morningEnd,
            slotDuration,
            slotBuffer,
          )
        : [];

    const eveningSlots =
      schedule.eveningStart && schedule.eveningEnd
        ? generateShiftSlots(
            schedule.eveningStart,
            schedule.eveningEnd,
            slotDuration,
            slotBuffer,
          )
        : [];

    const allSlots = [...morningSlots, ...eveningSlots];

    for (const slot of allSlots) {
      const normalizedSlot = slot.trim().toUpperCase();

      if (bookedTimes.has(normalizedSlot)) continue;
      if (isSlotEmergencyBlocked(candidateDate, slot, emergencyBlocks))
        continue;

      suggestions.push({
        date: candidateDate,
        slotTime: slot,
        isSpilloverBuffer: false,
        availableRemainingCapacity: remainingCapacity,
      });

      if (suggestions.length >= 8) return suggestions;
    }

    if (schedule.eveningEnd && spilloverCandidates.length < 3) {
      const eveningEndMins = timeToMinutes(schedule.eveningEnd);
      const spilloverSlot1 = minutesToTime(eveningEndMins);
      const spilloverSlot2 = minutesToTime(
        eveningEndMins + slotDuration + slotBuffer,
      );

      spilloverCandidates.push({
        date: candidateDate,
        slotTime: spilloverSlot1,
        isSpilloverBuffer: true,
        availableRemainingCapacity: remainingCapacity,
      });
      spilloverCandidates.push({
        date: candidateDate,
        slotTime: spilloverSlot2,
        isSpilloverBuffer: true,
        availableRemainingCapacity: remainingCapacity,
      });
    }
  }

  if (suggestions.length === 0) {
    return spilloverCandidates.slice(0, 4);
  }

  return suggestions;
}

export function batchRescheduleDisplaced(
  displacedAppointments: AppointmentItem[],
  params: Omit<FindAvailableSlotsParams, "existingAppointments"> & {
    existingAppointments: AppointmentItem[];
  },
): Array<{
  appointment: AppointmentItem;
  suggestion: RescheduleSuggestion | null;
}> {
  const simulatedAppointments = [...params.existingAppointments];
  const results: Array<{
    appointment: AppointmentItem;
    suggestion: RescheduleSuggestion | null;
  }> = [];

  for (const apt of displacedAppointments) {
    const candidateSlots = findNextAvailableSlots({
      ...params,
      existingAppointments: simulatedAppointments,
    });

    if (candidateSlots.length > 0) {
      const chosenSlot = candidateSlots[0];
      results.push({
        appointment: apt,
        suggestion: chosenSlot,
      });

      simulatedAppointments.push({
        ...apt,
        appointment_date: chosenSlot.date,
        appointment_time: chosenSlot.slotTime,
        status: "scheduled",
      });
    } else {
      results.push({
        appointment: apt,
        suggestion: null,
      });
    }
  }

  return results;
}
