import jsQR from "jsqr";

// QR contents are untrusted. Never follow arbitrary URLs or cross-origin links.
export function pairingLink(raw: string): string {
  const url = new URL(raw);
  const local =
    url.protocol === "http:" &&
    url.port === "8765" &&
    /^(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(
      url.hostname,
    ) &&
    !url.hash;
  const remote =
    url.origin === location.origin &&
    url.hash.startsWith("#deskpad=") &&
    url.hash.length <= 2060;
  if (
    (!local && !remote) ||
    url.pathname !== "/" ||
    url.search ||
    url.username ||
    url.password
  )
    throw new Error("Scan the QR shown in Deskpad on your laptop.");
  return url.href;
}

export async function scanQR() {
  const dialog = document.createElement("dialog");
  dialog.className = "qr-scanner";
  dialog.innerHTML = `<h2>Scan laptop QR</h2><p>Point your camera at the QR in Deskpad on your laptop.</p>
    <video autoplay muted playsinline aria-label="QR scanner preview"></video>
    <p role="status">Opening camera…</p><button class="primary">Cancel</button>`;
  document.body.append(dialog);
  const video = dialog.querySelector("video")!;
  const status = dialog.querySelector('[role="status"]')!;
  let stream: MediaStream | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let closed = false;
  const stop = () => {
    closed = true;
    clearTimeout(timer);
    stream?.getTracks().forEach((track) => track.stop());
    video.srcObject = null;
    document.removeEventListener("visibilitychange", visibility);
    dialog.remove();
  };
  dialog.querySelector("button")!.onclick = stop;
  dialog.oncancel = (event) => {
    event.preventDefault();
    stop();
  };
  const visibility = () => {
    if (document.hidden) stop();
  };
  document.addEventListener("visibilitychange", visibility);
  dialog.addEventListener("close", stop, { once: true });
  dialog.showModal();
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
    if (closed) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    video.srcObject = stream;
    await video.play();
    status.textContent = "Looking for a Deskpad QR…";
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    const scan = () => {
      if (closed) return;
      if (video.readyState >= 2 && video.videoWidth) {
        canvas.width = Math.min(960, video.videoWidth);
        canvas.height = Math.round(
          (canvas.width * video.videoHeight) / video.videoWidth,
        );
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const code = jsQR(pixels.data, pixels.width, pixels.height, {
          inversionAttempts: "dontInvert",
        });
        if (code) {
          try {
            const link = pairingLink(code.data);
            document.removeEventListener("visibilitychange", visibility);
            stop();
            location.replace(link);
            // Same-document fragments need to re-run the pairing bootstrap.
            if (new URL(link).origin === location.origin) location.reload();
            return;
          } catch (error) {
            status.textContent = (error as Error).message;
          }
        }
      }
      timer = setTimeout(scan, 180);
    };
    scan();
  } catch {
    stream?.getTracks().forEach((track) => track.stop());
    status.textContent =
      "Camera unavailable. Allow camera access in your browser, or scan with your phone's Camera app.";
  }
}
