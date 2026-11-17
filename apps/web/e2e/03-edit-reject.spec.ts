import { expect, test } from "@playwright/test";
import { analyze, BID_JOB, openStudio, signUp } from "./helpers";

test("an edit shows a diff; rejecting needs a reason and resumes the graph", async ({ page }) => {
  await signUp(page);
  const thread = await analyze(page, BID_JOB);
  await openStudio(page, thread);
  const panel = page.getByTestId("approval-panel");

  await panel.getByRole("button", { name: "Edit" }).click();
  const box = page.getByLabel("Edit draft");
  await box.fill(`${await box.inputValue()}\n\nI can start on Monday.`);
  await expect(page.getByTestId("diff")).toContainText("Monday");
  await panel.getByRole("button", { name: "Cancel" }).click();

  await panel.getByRole("button", { name: "Reject" }).click();
  const confirm = panel.getByRole("button", { name: "Confirm reject" });
  await expect(confirm).toBeDisabled(); // a reason is required
  await page.getByLabel(/Why reject/).fill("Not my niche right now");
  await expect(confirm).toBeEnabled();
  await confirm.click();

  await expect(page.getByTestId("approval-panel")).toHaveCount(0);
  await page.goto(`/runs/${thread}`);
  await expect(page.getByText("rejected").first()).toBeVisible();
});
