// Small date helpers shared by the schedule screens. All dates are local (no timezone shifts).

export const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export function toIso(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

export function fromIso(iso: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) { return null; }
  const d = new Date(+match[1], +match[2] - 1, +match[3]);
  return isNaN(d.getTime()) ? null : d;
}

export function addDays(d: Date, days: number): Date {
  const r = new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);
  return r;
}

/** Monday of the Monday-to-Sunday week containing `d`. */
export function mondayOf(d: Date): Date {
  const offset = (d.getDay() + 6) % 7; // Mon=0 ... Sun=6
  return addDays(d, -offset);
}

/** "October 5–11, 2026" or "September 28 – October 4, 2026" */
export function formatWeekRange(monday: Date): string {
  const sunday = addDays(monday, 6);
  const mName = MONTHS[monday.getMonth()];
  const sName = MONTHS[sunday.getMonth()];
  if (monday.getFullYear() !== sunday.getFullYear()) {
    return `${mName} ${monday.getDate()}, ${monday.getFullYear()} – ${sName} ${sunday.getDate()}, ${sunday.getFullYear()}`;
  }
  if (monday.getMonth() === sunday.getMonth()) {
    return `${mName} ${monday.getDate()}–${sunday.getDate()}, ${sunday.getFullYear()}`;
  }
  return `${mName} ${monday.getDate()} – ${sName} ${sunday.getDate()}, ${sunday.getFullYear()}`;
}
