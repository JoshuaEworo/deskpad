const installer =
  "https://github.com/JoshuaEworo/deskpad/releases/download/v0.2.0-alpha.3/Deskpad-Setup-Windows-x64.exe";
export function landing() {
  document.getElementById("app")!.innerHTML = `
    <div class="landing">
      <header><a class="brand" href="/" aria-label="Deskpad home"><img src="/icon.svg" alt="" width="30" height="30">deskpad</a>
        <a href="https://github.com/JoshuaEworo/deskpad">GitHub ↗</a></header>
      <section class="landing-hero">
        <div class="eyebrow">YOUR COMPUTER. WITHIN REACH.</div>
        <h1>Your laptop.<br>From your phone.</h1>
        <p>Stay comfortable. See your desktop, move your cursor, and type from your phone.</p>
        <div class="landing-actions"><a class="primary" href="${installer}">Download for Windows <span aria-hidden="true">↓</span></a>
          <a class="secondary" href="/?connect=1">Connect your phone <span aria-hidden="true">↗</span></a></div>
        <p class="landing-meta">Free & open source · Windows 10/11, 64-bit · Alpha</p>
        <p class="landing-meta">Windows may show a security prompt because this alpha is not code-signed.</p>
      </section>
      <section class="landing-steps" aria-label="Getting started">
        <article><span>01</span><h2>Install on your laptop</h2><p>Download Deskpad and open the desktop app.</p></article>
        <article><span>02</span><h2>Scan with your phone</h2><p>Open this site on your phone and scan the laptop’s QR.</p></article>
        <article><span>03</span><h2>Approve & settle in</h2><p>Match the code on your laptop. Your phone becomes your screen, trackpad, and keyboard.</p></article>
      </section>
      <footer>Pairing stays under your control. Use Local only on your Wi-Fi, or Anywhere when you’re away.<br>
        <a href="https://github.com/JoshuaEworo/deskpad/releases">All releases</a> · <a href="https://github.com/JoshuaEworo/deskpad/issues">Report an issue</a></footer>
    </div>`;
}
