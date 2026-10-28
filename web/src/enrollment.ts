// One-time laptop setup runs only when explicitly opened from its desktop app.
export async function enrollment() {
  if (!location.hash.startsWith("#setup=")) return false;
  const fragment = location.hash.slice(7);
  history.replaceState(null, "", location.pathname);
  const body = JSON.parse(atob(fragment.replace(/-/g, "+").replace(/_/g, "/")));
  if (!/^[\w-]{43}$/.test(body.room) || !/^[\w-]{43}$/.test(body.owner))
    throw new Error("Invalid setup link");
  document.getElementById("app")!.innerHTML =
    `<section class="pairing"><div class="brand">deskpad</div><h1>Enable remote access.</h1><p>Complete this one-time check, then return to the Deskpad window.</p><div id="verification"></div><p id="verification-status" role="status"></p></section>`;
  const configuration = await (await fetch("/api/config")).json();
  if (!configuration.siteKey) {
    document.getElementById("verification-status")!.textContent =
      "The service operator still needs to configure verification.";
    return true;
  }
  const script = document.createElement("script");
  script.src =
    "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
  script.onload = () => {
    const turnstile = (
      window as unknown as {
        turnstile: { render: (selector: string, options: unknown) => void };
      }
    ).turnstile;
    turnstile.render("#verification", {
      sitekey: configuration.siteKey,
      action: "deskpad-enroll",
      theme: "dark",
      callback: async (token: string) => {
        const response = await fetch(`/api/rooms/${body.room}/activate`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${body.owner}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ token }),
        });
        document.getElementById("verification-status")!.textContent =
          response.ok
            ? "Remote access enabled. Return to Deskpad to pair your phone."
            : "Verification failed. Reopen setup from Deskpad to try again.";
      },
    });
  };
  document.head.append(script);
  return true;
}
