import { test, expect } from "@playwright/test";

test("public landing provides GitHub Windows download and a phone connection entry", async ({
  page,
}) => {
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { remoteService: true } }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Your laptop. From your phone." }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Download for Windows" }),
  ).toHaveAttribute(
    "href",
    /github\.com\/JoshuaEworo\/deskpad\/releases\/download\/v/,
  );
  await page.getByRole("link", { name: "Connect your phone" }).click();
  await expect(
    page.getByRole("button", { name: "Scan laptop QR" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Scan laptop QR" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
