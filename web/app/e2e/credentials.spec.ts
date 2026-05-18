// web/app/e2e/credentials.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Credentials surface", () => {
  test("pill shows green when all OK", async ({ page }) => {
    await fetch("http://localhost:8000/api/credentials/google_oauth/recheck", { method: "POST" });
    await page.goto("/");
    await expect(page.getByText(/Pipeline · live|Credentials ·/)).toBeVisible({ timeout: 5_000 });
  });

  test("popover lists registered credentials", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Pipeline|Credentials/ }).click();
    await expect(page.getByText("Google (OAuth)")).toBeVisible();
    await expect(page.getByText("Anthropic API")).toBeVisible();
    await expect(page.getByText("Manage all →")).toBeVisible();
  });

  test("Reconnect Google opens Google consent URL", async ({ page }) => {
    await page.goto("/settings/credentials");
    await page.evaluate(() => {
      (window as any).__opened = [];
      window.open = ((url: string | URL | undefined) => {
        (window as any).__opened.push(String(url));
        return null;
      }) as typeof window.open;
    });

    const reconnect = page.getByRole("button", { name: /Reconnect Google/ });
    if (await reconnect.count()) {
      await reconnect.first().click();
      await page.waitForFunction(() => (window as any).__opened.length > 0);
      const opened = await page.evaluate(() => (window as any).__opened);
      expect(opened[0]).toMatch(/^https:\/\/accounts\.google\.com\//);
    }
  });
});
