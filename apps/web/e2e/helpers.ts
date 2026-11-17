import { expect, type Page } from "@playwright/test";

// Dev-set jobs with known behaviour (rules mode): see docs/DEPLOY.md and the video brief.
export const BID_JOB = "gj_16671e658f"; // bid-worthy: stops at the approval interrupt
export const SCAM_JOB = "gj_08aacce229"; // upfront fee: blocked and skipped

/** Register a fresh AI/ML freelancer so every spec has its own tenant. */
export async function signUp(page: Page): Promise<string> {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  await page.goto("/onboarding");
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByLabel("AI / ML engineer").check();
  await page.getByRole("button", { name: "Create account" }).last().click();
  await expect(page).toHaveURL(/\/inbox/);
  return email;
}

/** Start the bid graph on a job from its page; returns the run (thread) id. */
export async function analyze(page: Page, jobId: string): Promise<string> {
  await page.goto(`/jobs/${jobId}`);
  await page.getByRole("button", { name: "Analyse this job" }).click();
  await expect(page).toHaveURL(/\/runs\/bid-/);
  return page.url().split("/runs/")[1];
}

/** From a run that stops at approval, open the studio. */
export async function openStudio(page: Page, threadId: string): Promise<void> {
  await page.getByRole("link", { name: "Review & approve" }).click();
  await expect(page).toHaveURL(new RegExp(`/studio/${threadId}`));
  await expect(page.getByTestId("approval-panel")).toBeVisible();
}
