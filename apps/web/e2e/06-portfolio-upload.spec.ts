import { expect, test } from "@playwright/test";
import { signUp } from "./helpers";

test("a user uploads a case study, sees it listed, and deletes it", async ({ page }) => {
  await signUp(page);
  await page.goto("/settings");
  const section = page.getByRole("region", { name: "Portfolio" });
  await expect(section.getByText("No uploads yet")).toBeVisible();

  await section.getByLabel("Add a file").setInputFiles({
    name: "satellite.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Telemetry detector\n\nI built a telemetry anomaly detector in Python for a satellite operator."),
  });
  await expect(section.getByText("Added satellite.md")).toBeVisible();
  await expect(section.getByText(/ai_ml:upload:/)).toBeVisible();

  await section.getByRole("button", { name: "Delete upload satellite.md" }).click();
  await expect(section.getByText("No uploads yet")).toBeVisible();
});
