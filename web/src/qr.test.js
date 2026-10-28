import { execFileSync } from "node:child_process";
import { expect, it } from "vitest";
import jsQR from "jsqr";

it("decodes the desktop's real pairing QR across Windows display scales", () => {
  const python =
    process.platform === "win32"
      ? "../.venv/Scripts/python.exe"
      : "../.venv/bin/python";
  const samples = JSON.parse(
    execFileSync(
      python,
      [
        "-c",
        `
import base64,json,tempfile
from pathlib import Path
from deskpad.qr import pairing_qr
from deskpad.identity import Identity
from deskpad.remote import Remote
from deskpad.settings import Settings
from deskpad.service import Service
with tempfile.TemporaryDirectory() as directory:
    remote=Remote(Identity(Path(directory)),Settings(service_url='https://deskpad.example'),Service(),None)
    url=remote.pairing_url()
    images=[pairing_qr(url,204*ratio) for ratio in (1,1.25,1.5,1.75,2)]
    print(json.dumps([dict(url=url,width=image.width,height=image.height,pixels=base64.b64encode(image.tobytes()).decode()) for image in images]))
`,
      ],
      { encoding: "utf8", maxBuffer: 8 * 1024 * 1024 },
    ),
  );
  for (const sample of samples) {
    const pixels = new Uint8ClampedArray(Buffer.from(sample.pixels, "base64"));
    expect(jsQR(pixels, sample.width, sample.height)?.data).toBe(sample.url);
  }
});
