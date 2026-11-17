import { expect, test } from "@playwright/test";
import { signUp } from "./helpers";

test.describe("mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the nav collapses into a menu and saved searches can be added in settings", async ({ page }) => {
    await signUp(page);
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav).toBeHidden();
    const menu = page.getByRole("button", { name: "Menu" });
    await menu.click();
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    await nav.getByRole("link", { name: "Settings" }).click();
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

    await page.getByRole("button", { name: /Add saved search/ }).click();
    await page.getByRole("button", { name: "Save settings" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Memory" })).toBeVisible();
  });
});

test("sign in works with the keyboard only", async ({ page, browser }) => {
  const email = await signUp(page);
  const fresh = await browser.newPage();
  await fresh.goto("/onboarding");
  await fresh.getByLabel("Email").focus();
  await fresh.keyboard.type(email);
  await fresh.keyboard.press("Tab");
  await fresh.keyboard.type("e2e-password-123");
  await fresh.keyboard.press("Enter");
  await expect(fresh).toHaveURL(/\/inbox/);
  await fresh.close();
});
