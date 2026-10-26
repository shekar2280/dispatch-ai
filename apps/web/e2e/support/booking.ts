import { expect, type Page } from '@playwright/test';
import { type ClinicActor, type Visit } from './fixtures';
import { syntheticPatient } from './environment';

export async function openBooking(page: Page) {
  await page.getByRole('button', { name: /Book Appointment|Intake/ }).click();
  await expect(page.getByRole('heading', { name: 'Book a visit', exact: true })).toBeVisible();
  return page.locator('form[role="dialog"]');
}

export async function prepareScheduledBooking(actor: ClinicActor) {
  const slot = await actor.futureSlot();
  const patient = syntheticPatient();
  const form = await openBooking(actor.page);
  await selectBookingDate(actor.page, slot.date);
  await expect(form.getByText('Select doctor', { exact: true })).toHaveCount(0);
  await form.getByRole('radio', { name: slot.time, exact: true }).click();
  await form.getByLabel('Patient name', { exact: true }).fill(patient.name);
  await form.getByLabel('Contact number', { exact: true }).fill(patient.phone);
  await expect(form.getByRole('button', { name: 'Book appointment', exact: true })).toBeEnabled();
  return { form, patient, slot };
}

export async function submitScheduledBooking(actor: ClinicActor): Promise<Visit> {
  const { form, patient } = await prepareScheduledBooking(actor);
  const responsePromise = actor.page.waitForResponse(response => response.url().endsWith('/api/v1/appointments/book') && response.request().method() === 'POST');
  await form.getByRole('button', { name: 'Book appointment', exact: true }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(201);
  const visit: Visit = await response.json();
  actor.visits.add(visit.id);
  expect(visit.patient_name).toBe(patient.name);
  expect(visit.doctor_id).toBe(actor.doctorId);
  await expect(actor.page.getByRole('heading', { name: 'Book a visit', exact: true })).toBeHidden();
  expect((await actor.readVisit(visit.id)).patient_name).toBe(patient.name);
  return visit;
}

export async function selectBookingDate(page: Page, date: string) {
  const picker = page.getByRole('group', { name: 'Visit date picker', exact: true });
  await picker.getByRole('button', { name: 'Visit date', exact: true }).click();
  const day = picker.getByRole('button', { name: date, exact: true });
  for (let month = 0; month < 12 && await day.count() === 0; month++) {
    await picker.getByRole('button', { name: 'Next month', exact: true }).click();
  }
  await day.click();
}
