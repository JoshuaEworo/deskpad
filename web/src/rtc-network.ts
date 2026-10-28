// Non-trickle negotiation must not wait forever on unreachable relay transports.
export function usableIceServers(servers: RTCIceServer[]): RTCIceServer[] {
  return servers.flatMap((server) => {
    const urls = (
      typeof server.urls === "string" ? [server.urls] : server.urls
    ).filter((url) => !/:53(?:\?|$)/.test(url));
    return urls.length ? [{ ...server, urls }] : [];
  });
}

export function gatherIce(
  pc: RTCPeerConnection,
  timeout = 15000,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const finish = (error?: Error) => {
      clearTimeout(timer);
      clearTimeout(partial);
      pc.removeEventListener("icegatheringstatechange", changed);
      pc.removeEventListener("signalingstatechange", changed);
      if (error) reject(error);
      else resolve();
    };
    const changed = () => {
      if (pc.signalingState === "closed")
        finish(new Error("Connection cancelled"));
      else if (pc.iceGatheringState === "complete") finish();
    };
    // Once viable candidates exist, do not spend the full watchdog waiting on
    // an unused TURN transport. Keep the full deadline for slow discovery.
    const partial = setTimeout(
      () => {
        if (/^a=candidate:/m.test(pc.localDescription?.sdp || "")) finish();
      },
      Math.min(4000, timeout),
    );
    const timer = setTimeout(() => {
      // Browsers update localDescription as candidates arrive. Send the routes
      // already discovered instead of discarding a viable offer because another
      // TURN transport is blocked. The connection watchdog still bounds setup.
      if (/^a=candidate:/m.test(pc.localDescription?.sdp || "")) finish();
      else
        finish(
          new Error(
            "No network route found. Try another Wi-Fi or cellular connection.",
          ),
        );
    }, timeout);
    pc.addEventListener("icegatheringstatechange", changed);
    pc.addEventListener("signalingstatechange", changed);
    changed();
  });
}
