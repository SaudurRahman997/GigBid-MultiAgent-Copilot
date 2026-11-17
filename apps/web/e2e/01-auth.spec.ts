import { expect, test } from "@playwright/test";
import { signUp } from "./helpers";

test("sign up lands on the inbox with marketplace jobs; sign out ends the session", async ({ page }) => {
  await signUp(page);
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open" }).first()).toBeVisible(); // jobs come from the marketplace tools

  await page.getByRole("button", { name: /sign out/i }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.goto("/inbox");
  await expect(page).toHaveURL(/\/onboarding/); // protected pages need a session
});
