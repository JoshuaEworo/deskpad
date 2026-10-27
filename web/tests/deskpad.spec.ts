import { test, expect, type Page } from "@playwright/test";

async function pair(page: Page) {
  await page.goto("/");
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
}
async function events(page: Page) {
  return (await (await page.request.get("/test/events")).json()) as (
    string | boolean | number
  )[][];
}

test("keyboard-first controls keep the desktop full width as the visible viewport shrinks", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await pair(page);
  await expect(page.locator("#typing")).toBeFocused();
  await expect(page.locator(".topbar")).toBeHidden();
  await expect(page.locator("#mouse-buttons")).toBeHidden();
  await page.locator("#typing").pressSequentially("Keyboard-first Deskpad");
  await page.locator("#typing").press("Backspace");
  await expect
    .poll(async () =>
      (await events(page))
        .filter((event) => event[0] === "text")
        .map((event) => event[1])
        .join(""),
    )
    .toBe("Keyboard-first Deskpad");
  for (const height of [844, 530, 420, 320]) {
    await page.setViewportSize({ width: 390, height });
    await expect
      .poll(async () => (await page.locator("#picture").boundingBox())!.width)
      .toBeCloseTo(390, 0);
    const screen = (await page.locator("#screen").boundingBox())!;
    const pad = (await page.locator("#trackpad").boundingBox())!;
    const controls = (await page.locator(".controls").boundingBox())!;
    expect(screen.height / height).toBeGreaterThan(0.6);
    expect(screen.y + screen.height).toBeLessThanOrEqual(pad.y);
    expect(pad.height).toBeLessThanOrEqual(80);
    expect(controls.y + controls.height).toBeLessThanOrEqual(height);
    await expect(page.locator("#typing")).toBeFocused();
  }
  await page.setViewportSize({ width: 390, height: 530 });
  await page.screenshot({
    path: `test-results/keyboard-viewport-${test.info().project.name}.png`,
  });
  await page.getByRole("button", { name: "ctrl", exact: true }).click();
  await expect(page.locator("#typing")).toBeFocused();
  await expect(
    page.getByRole("button", { name: "ctrl", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Open settings" }).click();
  await expect(
    page.getByRole("button", { name: "ctrl", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.locator("#status")).toHaveText("Disconnected");
  await page.getByRole("button", { name: "Open settings" }).click();
  await page.getByRole("button", { name: "Reconnect", exact: true }).click();
  await expect(page.locator("#status")).toHaveText("Connected to laptop");
  await page.getByRole("button", { name: "Open settings" }).click();
  await page.getByRole("button", { name: "Forget this phone" }).click();
  await expect(page.getByLabel("Pairing code")).toBeVisible();
  expect(errors).toEqual([]);
});

test("optional mouse controls and a resizable trackpad remain available without permanent rows", async ({
  page,
}) => {
  await pair(page);
  await page.getByRole("button", { name: "Open settings" }).click();
  await page.getByLabel("Show mouse buttons").check();
  await page.getByRole("button", { name: "Close settings" }).click();
  await expect(page.locator("#mouse-buttons")).toBeVisible();
  await expect(page.locator("#typing")).toBeFocused();
  const before = (await page.locator("#trackpad").boundingBox())!.height;
  const divider = (await page.locator("#divider").boundingBox())!;
  await page.mouse.move(150, divider.y + divider.height / 2);
  await page.mouse.down();
  await page.mouse.move(150, divider.y - 50);
  await page.mouse.up();
  await expect
    .poll(async () => (await page.locator("#trackpad").boundingBox())!.height)
    .toBeGreaterThan(before + 30);
  await page.getByRole("button", { name: "Open settings" }).click();
  await page.getByRole("button", { name: "Drag lock", exact: true }).click();
  await expect(page.locator("#settings")).toBeHidden();
  const baseline = (await events(page)).length;
  const pad = (await page.locator("#trackpad").boundingBox())!;
  await page.mouse.move(80, pad.y + 20);
  await page.mouse.down();
  await page.waitForTimeout(400); // Deliberately cross the long-press gesture threshold.
  await page.mouse.move(100, pad.y + 25);
  await page.mouse.up();
  const after = (await events(page)).slice(baseline);
  expect(
    after.some(
      (event) =>
        event[0] === "button" && event[1] === "left" && event[2] === false,
    ),
  ).toBe(false);
  await page.getByRole("button", { name: "Open settings" }).click(); // Opening a menu releases held inputs.
  await page.getByLabel("Show mouse buttons").uncheck();
  await page.getByRole("button", { name: "Close settings" }).click();
  await expect(page.locator("#mouse-buttons")).toBeHidden();
});

test("two-finger right click retains keyboard focus; pinch scale survives keyboard-sized viewports", async ({
  page,
  browserName,
}) => {
  test.skip(
    browserName !== "chromium",
    "Chromium CDP supplies real multi-touch input for this regression.",
  );
  await pair(page);
  await page.setViewportSize({ width: 390, height: 530 });
  const session = await page.context().newCDPSession(page);
  const pad = (await page.locator("#trackpad").boundingBox())!;
  const baseline = (await events(page)).length;
  await session.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [
      { x: 100, y: pad.y + 20, id: 1 },
      { x: 180, y: pad.y + 20, id: 2 },
    ],
  });
  await session.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  await expect
    .poll(async () =>
      (await events(page))
        .slice(baseline)
        .some((e) => e[0] === "button" && e[1] === "right" && e[2] === true),
    )
    .toBe(true);
  await expect(page.locator("#typing")).toBeFocused();
  await session.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [
      { x: 100, y: 150, id: 1 },
      { x: 290, y: 150, id: 2 },
    ],
  });
  await session.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [
      { x: 60, y: 150, id: 1 },
      { x: 330, y: 150, id: 2 },
    ],
  });
  await session.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  const zoomed = (await page.locator("#picture").boundingBox())!.width;
  expect(zoomed).toBeGreaterThan(450);
  await page.setViewportSize({ width: 390, height: 360 });
  await expect
    .poll(async () => (await page.locator("#picture").boundingBox())!.width)
    .toBeCloseTo(zoomed, 0);
  await page.getByRole("button", { name: "Open settings" }).click();
  await page.getByRole("button", { name: "Fit width", exact: true }).click();
  await expect
    .poll(async () => (await page.locator("#picture").boundingBox())!.width)
    .toBeCloseTo(390, 0);
});
