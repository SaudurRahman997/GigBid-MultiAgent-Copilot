import { expect, test } from "@playwright/test";
import { analyze, BID_JOB, openStudio, signUp } from "./helpers";

test("analyse -> live timeline -> evidence hover -> approve -> submitted once -> pipeline", async ({ page }) => {
  await signUp(page);
  const thread = await analyze(page, BID_JOB);

  // live run timeline (SSE), then the graph pauses for a human
  await expect(page.getByText("writer").first()).toBeVisible();
  await openStudio(page, thread);

  // every claim carries its evidence on hover / focus
  const claim = page.getByTestId("claim").first();
  await expect(claim).toBeVisible();
  await claim.hover();
  await expect(page.getByText(/ai_ml:(case|review|readme|cv|code)/).first()).toBeVisible();
  await expect(page.getByTestId("connects-cost")).not.toHaveText("—");

  await page.getByRole("button", { name: "Approve & send" }).click();
  await expect(page.getByTestId("submission")).toContainText("Submitted");
  await expect(page.getByTestId("submission")).toContainText(`${thread}:submit:v1`); // idempotency key

  await page.goto("/pipeline");
  const submitted = page.getByRole("listitem", { name: "submitted" });
  await expect(submitted).toContainText("(1)");
});
