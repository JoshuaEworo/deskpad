import { test, expect, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.request.post("/test/reset");
});

async function pair(page: Page) {
  await page.addInitScript(() =>
    localStorage.setItem("deskpad.legacyVideo", "true"),
  );
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

async function portraitViewport(
  page: Page,
  height: number,
  browserName: string,
) {
  if (browserName === "chromium") {
    const session = await page.context().newCDPSession(page);
    await session.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height,
      deviceScaleFactor: 3,
      mobile: true,
      screenWidth: 390,
      screenHeight: 844,
      screenOrientation: { type: "portraitPrimary", angle: 0 },
    });
  } else await page.setViewportSize({ width: 390, height });
}

test("keyboard-first controls keep the desktop full width as the visible viewport shrinks", async ({
  page,
  browserName,
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
  for (const height of browserName === "chromium"
    ? [844, 530, 420, 320]
    : [844, 530, 420]) {
    await portraitViewport(page, height, browserName);
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
  await page.getByRole("button", { name: "End session", exact: true }).click();
  await expect(page.locator("#status")).toHaveText("Disconnected");
  await expect(
    page.getByRole("heading", { name: "Session ended" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Reconnect to laptop", exact: true })
    .click();
  await expect(page.locator("#status")).toHaveText("Connected to laptop");
  await page.getByRole("button", { name: "Open settings" }).click();
  await page.getByRole("button", { name: "Forget this phone" }).click();
  await expect(page.getByLabel("Pairing code")).toBeVisible();
  expect(errors).toEqual([]);
});

test("optional mouse controls and a resizable trackpad remain available without permanent rows", async ({
  page,
}) => {
  await page.addInitScript(() => localStorage.setItem("deskpad.speed", "1.5"));
  await pair(page);
  await page.getByRole("button", { name: "Open settings" }).click();
  await expect(page.getByLabel("Pointer speed")).toHaveValue("4");
  await expect(page.getByLabel("Pointer speed")).toHaveAttribute("min", "2.5");
  await expect(page.getByLabel("Pointer speed")).toHaveAttribute("max", "7");
  await page.getByLabel("Pointer speed").fill("7");
  await page.getByLabel("Show mouse buttons").check();
  await page.getByLabel("Show scroll wheel").check();
  await page.getByRole("button", { name: "Close settings" }).click();
  const wheel = (await page.locator("#scroll-wheel").boundingBox())!;
  const wheelBaseline = (await events(page)).length;
  await page.mouse.move(wheel.x + wheel.width / 2, wheel.y + 10);
  await page.mouse.down();
  await page.mouse.move(wheel.x + wheel.width / 2, wheel.y + 35);
  await page.mouse.up();
  await expect
    .poll(async () =>
      (await events(page))
        .slice(wheelBaseline)
        .some((event) => event[0] === "scroll" && event[2] !== 0),
    )
    .toBe(true);
  await expect(page.locator("#typing")).toBeFocused();
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
  await page.getByLabel("Show scroll wheel").uncheck();
  await page.getByRole("button", { name: "Close settings" }).click();
  await expect(page.locator("#mouse-buttons")).toBeHidden();
  await expect(page.locator("#scroll-wheel")).toBeHidden();
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
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
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
  const original = (await page.locator("#picture").boundingBox())!;
  await session.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [
      { x: 60, y: 200, id: 1 },
      { x: 140, y: 200, id: 2 },
    ],
  });
  await session.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [
      { x: 0, y: 200, id: 1 },
      { x: 200, y: 200, id: 2 },
    ],
  });
  await session.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  const enlarged = (await page.locator("#picture").boundingBox())!;
  const zoomed = enlarged.width;
  expect(zoomed).toBeGreaterThan(700);
  // The same desktop point stays beneath the off-center pinch midpoint.
  expect((100 - enlarged.x) / enlarged.width).toBeCloseTo(
    (100 - original.x) / original.width,
    2,
  );
  expect((200 - enlarged.y) / enlarged.height).toBeCloseTo(
    (200 - original.y) / original.height,
    2,
  );
  await portraitViewport(page, 360, browserName);
  await expect
    .poll(async () => (await page.locator("#picture").boundingBox())!.width)
    .toBeCloseTo(zoomed, 0);
  await page.getByRole("button", { name: "Open settings" }).click();
  await page.getByRole("button", { name: "Fit width", exact: true }).click();
  await expect
    .poll(async () => (await page.locator("#picture").boundingBox())!.width)
    .toBeCloseTo(390, 0);
});

test("landscape docks controls, isolates Mouse and View gestures, and restores portrait", async ({
  page,
  browserName,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await pair(page);
  if (browserName === "chromium") {
    const touch = await page.context().newCDPSession(page);
    await touch.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [
        { x: 90, y: 350, id: 1 },
        { x: 290, y: 350, id: 2 },
      ],
    });
    await touch.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [
        { x: 40, y: 350, id: 1 },
        { x: 340, y: 350, id: 2 },
      ],
    });
    await touch.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [],
    });
  }
  const portraitWidth = (await page.locator("#picture").boundingBox())!.width;
  await page.getByRole("button", { name: "ctrl", exact: true }).click();
  await page.setViewportSize({ width: 844, height: 390 });
  await expect(page.locator("#app")).toHaveClass(/landscape/);
  await expect(page.locator(".pointing-surface")).toBeHidden();
  await expect(page.locator(".screen-overlay")).toBeHidden();
  await expect(page.locator("#typing")).not.toBeFocused();
  await expect(
    page.getByRole("button", { name: "Mouse", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(async () =>
      (await events(page)).some(
        (e) => e[0] === "key" && e[1] === "Control" && e[2] === false,
      ),
    )
    .toBe(true);
  const image = (await page.locator("#picture").boundingBox())!;
  const screen = (await page.locator("#screen").boundingBox())!;
  const dock = (await page.locator(".controls").boundingBox())!;
  expect(image.x).toBeGreaterThanOrEqual(screen.x - 1);
  expect(image.y).toBeGreaterThanOrEqual(screen.y - 1);
  expect(image.x + image.width).toBeLessThanOrEqual(
    screen.x + screen.width + 1,
  );
  expect(image.y + image.height).toBeLessThanOrEqual(dock.y + 1);
  expect(image.width / image.height).toBeCloseTo(16 / 9, 2);
  expect(screen.y + screen.height).toBeLessThanOrEqual(dock.y);
  await page.screenshot({
    path: `test-results/landscape-expanded-${test.info().project.name}.png`,
  });
  const transform = await page
    .locator("#picture")
    .evaluate((el) => el.style.transform);
  const mouseBaseline = (await events(page)).length;
  await page.mouse.move(220, 150);
  await page.mouse.down();
  await page.mouse.move(245, 165);
  await page.mouse.up();
  await page.mouse.click(250, 165);
  await expect
    .poll(async () =>
      (await events(page)).slice(mouseBaseline).some((e) => e[0] === "move"),
    )
    .toBe(true);
  await expect
    .poll(async () =>
      (await events(page))
        .slice(mouseBaseline)
        .some((e) => e[0] === "button" && e[1] === "left" && e[2] === true),
    )
    .toBe(true);
  expect(
    await page.locator("#picture").evaluate((el) => el.style.transform),
  ).toBe(transform);
  await page.getByRole("button", { name: "View", exact: true }).click();
  const viewBaseline = (await events(page)).length;
  await page.mouse.move(200, 100);
  await page.mouse.down();
  await page.mouse.move(250, 130);
  await page.mouse.up();
  if (browserName === "chromium") {
    const touch = await page.context().newCDPSession(page);
    await touch.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [
        { x: 250, y: 150, id: 1 },
        { x: 450, y: 150, id: 2 },
      ],
    });
    await touch.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [
        { x: 180, y: 150, id: 1 },
        { x: 520, y: 150, id: 2 },
      ],
    });
    await touch.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [],
    });
    await expect
      .poll(async () => (await page.locator("#picture").boundingBox())!.width)
      .toBeGreaterThan(image.width * 1.4);
  }
  expect(
    (await events(page))
      .slice(viewBaseline)
      .filter((e) => ["move", "scroll", "button"].includes(String(e[0]))),
  ).toEqual([]);
  const beforeCollapse = (await page.locator("#screen").boundingBox())!.height;
  await page.getByRole("button", { name: "Collapse hotkeys" }).click();
  await expect(page.locator(".key-strip")).toBeHidden();
  await expect(page.locator("#rail-brand")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "View", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(async () => (await page.locator("#screen").boundingBox())!.height)
    .toBeGreaterThan(beforeCollapse);
  const collapsedDock = (await page.locator(".controls").boundingBox())!;
  const enlargedScreen = (await page.locator("#screen").boundingBox())!;
  expect(enlargedScreen.y + enlargedScreen.height).toBeLessThanOrEqual(
    collapsedDock.y,
  );
  await page.screenshot({
    path: `test-results/landscape-collapsed-${test.info().project.name}.png`,
  });
  await page.getByRole("button", { name: "Expand hotkeys" }).click();
  await expect(page.locator(".key-strip")).toBeVisible();
  await page.getByRole("button", { name: "Open keyboard" }).click();
  await expect(page.locator("#typing")).toBeFocused();
  await page.getByRole("button", { name: "Hide keyboard" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("#app")).not.toHaveClass(/landscape/);
  await expect(page.locator(".pointing-surface")).toBeVisible();
  await expect(page.locator("#typing")).toBeFocused();
  await expect
    .poll(async () => (await page.locator("#picture").boundingBox())!.width)
    .toBeCloseTo(portraitWidth, 0);
  expect(errors).toEqual([]);
});

test("WebRTC desktop carries video, ordered input, cursor updates, and releases on disconnect", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "WebRTC engine smoke test");
  await page.goto("/");
  const capabilities = await (await page.request.get("/api/status")).json();
  test.skip(!capabilities.rtc, "Media extra not installed");
  await page.getByLabel("Pairing code").fill("123456");
  await page.getByRole("button", { name: "Connect to laptop" }).click();
  await expect(page.locator("#status")).toHaveText("Connected to laptop", {
    timeout: 30000,
  });
  await expect
    .poll(
      () =>
        page
          .locator("#desktop-video")
          .evaluate((v: HTMLVideoElement) => v.videoWidth),
      { timeout: 15000 },
    )
    .toBeGreaterThan(0);
  await page.locator("#typing").evaluate((el) => {
    el.textContent = "hello";
    el.dispatchEvent(
      new InputEvent("input", {
        inputType: "insertText",
        data: "hello",
        bubbles: true,
      }),
    );
  });
  await expect
    .poll(async () => JSON.stringify(await events(page)))
    .toContain("hello");
  await page.locator("#settings-toggle").click();
  await page.locator("#disconnect").click();
  await expect
    .poll(
      async () => (await (await page.request.get("/api/status")).json()).busy,
    )
    .toBe(false);
});

test("remote QR pins identity, requires matching laptop approval, then streams over WebRTC", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "WebRTC remote handshake smoke test");
  test.setTimeout(45000);
  const config = await (await page.request.get("/test/remote")).json();
  const fragment = Buffer.from(JSON.stringify(config)).toString("base64url");
  await page.goto("/#deskpad=" + fragment);
  await page.getByRole("button", { name: "Request pairing" }).click();
  await expect(page.locator("#remote-pair-status")).toContainText(
    "Approve this code",
    { timeout: 10000 },
  );
  await expect(page.locator("#workspace")).toBeHidden();
  expect(new URL(page.url()).hash).toBe("");
  await page.request.post("/test/approve");
  await expect(page.locator("#status")).toHaveText("Connected to laptop", {
    timeout: 20000,
  });
  await expect
    .poll(() =>
      page
        .locator("#desktop-video")
        .evaluate((v: HTMLVideoElement) => v.videoWidth),
    )
    .toBeGreaterThan(0);
  // Simulate quitting the host, refreshing the phone while offline, then
  // reopening the same host identity. No new pairing approval is allowed.
  await page.request.post("/test/remote-offline");
  await page.reload();
  await expect(page.locator("#screen-empty")).toBeVisible();
  await page.request.post("/test/remote-online");
  await expect(page.locator("#status")).toHaveText("Connected to laptop", {
    timeout: 20000,
  });
  await expect
    .poll(() =>
      page
        .locator("#desktop-video")
        .evaluate((video: HTMLVideoElement) => video.videoWidth),
    )
    .toBeGreaterThan(0);
  await page.locator("#settings-toggle").click();
  await page.locator("#disconnect").click();
  await expect
    .poll(
      async () => (await (await page.request.get("/api/status")).json()).busy,
    )
    .toBe(false);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Session ended" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Reconnect to laptop", exact: true })
    .click();
  await expect(page.locator("#status")).toHaveText("Connected to laptop", {
    timeout: 20000,
  });
  await page.request.post("/test/revoke");
  await expect(
    page.getByRole("heading", { name: "Access removed" }),
  ).toBeVisible();
  await expect(page.locator("#workspace")).toBeHidden();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("deskpad.remote")))
    .toBe(null);
});

test("opt-in phone camera and microphone send media and stop capture on disconnect", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "Fake browser media devices");
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices,
    );
    (window as any).__captured = [];
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      const stream = await original(constraints);
      (window as any).__captured.push(...stream.getTracks());
      return stream;
    };
  });
  await page.request.post("/test/media/allow");
  await page.goto("/");
  await page.getByLabel("Pairing code").fill("123456");
  await page.getByRole("button", { name: "Connect to laptop" }).click();
  await expect(page.locator("#status")).toHaveText("Connected to laptop", {
    timeout: 20000,
  });
  await page.locator("#settings-toggle").click();
  await page.getByLabel("Use phone camera", { exact: true }).check();
  await page.getByLabel("Use phone microphone", { exact: true }).check();
  await expect
    .poll(
      async () => await (await page.request.get("/test/media/events")).json(),
    )
    .toContain("video");
  await expect
    .poll(
      async () => await (await page.request.get("/test/media/events")).json(),
    )
    .toContain("audio");
  await expect(page.locator("#camera-preview")).toBeVisible();
  await page.getByLabel("Use phone camera", { exact: true }).uncheck();
  await expect(page.locator("#camera-preview")).toBeHidden();
  await expect
    .poll(
      async () => await (await page.request.get("/test/media/events")).json(),
    )
    .toContain("closed:video");
  await page.locator("#disconnect").click();
  await expect
    .poll(() =>
      page.evaluate(() =>
        (window as any).__captured.every(
          (track: MediaStreamTrack) => track.readyState === "ended",
        ),
      ),
    )
    .toBe(true);
  await expect(page.locator("#camera-preview")).toBeHidden();
  await expect
    .poll(
      async () => await (await page.request.get("/test/media/events")).json(),
    )
    .toContain("closed:video");
});
