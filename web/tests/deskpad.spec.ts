import { test, expect } from "@playwright/test";

test("pair, stream, control, reconnect, and forget a phone", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /a little closer/i }),
  ).toBeVisible();
  await page.getByLabel("Pairing code").fill("123456");
  await page.getByRole("button", { name: "Connect to laptop" }).click();
  await expect(page.locator("#status")).toHaveText("Connected to laptop");
  await expect
    .poll(() =>
      page
        .locator("#desktop")
        .evaluate((image: HTMLImageElement) => image.naturalWidth),
    )
    .toBeGreaterThan(0);
  const screen = await page.locator("#screen").boundingBox();
  const trackpad = await page.locator("#trackpad").boundingBox();
  expect(screen!.y + screen!.height).toBeLessThan(trackpad!.y);
  await page.getByRole("button", { name: "Keyboard", exact: true }).click();
  await page.locator("#typing").pressSequentially("Hello Deskpad");
  await page.locator("#typing").press("Backspace");
  await expect
    .poll(async () => {
      const events = await (await page.request.get("/test/events")).json();
      return events
        .filter((event: string[]) => event[0] === "text")
        .map((event: string[]) => event[1])
        .join("");
    })
    .toBe("Hello Deskpad");
  await page
    .getByRole("button", { name: "Hide keyboard", exact: true })
    .click();
  await page.getByRole("button", { name: "ctrl", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "ctrl", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Open settings" }).click();
  await expect(
    page.getByRole("button", { name: "ctrl", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.locator("#status")).toHaveText("Disconnected");
  await page.getByRole("button", { name: "Reconnect", exact: true }).click();
  await expect(page.locator("#status")).toHaveText("Connected to laptop");
  await page.setViewportSize({ width: 390, height: 530 });
  await expect
    .poll(async () => {
      const footer = await page.locator(".bottom-bar").boundingBox();
      return footer!.y + footer!.height;
    })
    .toBeLessThanOrEqual(530);
  await expect(page.locator("#trackpad")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: `test-results/deskpad-${test.info().project.name}.png`,
  });
  await page.getByRole("button", { name: "Open settings" }).click();
  await page.getByRole("button", { name: "Forget this phone" }).click();
  await expect(page.getByLabel("Pairing code")).toBeVisible();
  expect(errors).toEqual([]);
});
