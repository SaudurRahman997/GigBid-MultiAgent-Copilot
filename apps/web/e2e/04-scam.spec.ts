import { expect, test } from "@playwright/test";
import { analyze, SCAM_JOB, signUp } from "./helpers";

test("a scam job (upfront fee) is blocked and skipped without a draft", async ({ page }) => {
  await signUp(page);
  await analyze(page, SCAM_JOB);
  await expect(page.getByText("skipped").first()).toBeVisible();
  await expect(page.getByText(/upfront_fee/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Review & approve" })).toHaveCount(0);
});
